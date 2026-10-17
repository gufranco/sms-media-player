from __future__ import annotations

from typing import Final

import numpy as np
import numpy.typing as npt

from smsggmedia import console, limits, pattern, smscolor, stream

VRAM_BYTES: Final = console.VRAM_BYTES
CRAM_BYTES: Final = console.CRAM_BYTES
NAME_TABLE_BASE: Final = console.NAME_TABLE_BASE
NAME_TABLE_COLUMNS: Final = console.NAME_TABLE_COLUMNS
NAME_TABLE_ROWS: Final = console.NAME_TABLE_ROWS
VISIBLE_ROWS: Final = console.VISIBLE_ROWS
BLACK_LEVEL: Final = 16


class Machine:
    def __init__(self) -> None:
        self.vram = console.boot_vram()
        self.cram = np.zeros(stream.WIDE_CLOSE_BYTES, dtype=np.uint8)
        self.cram[:CRAM_BYTES] = console.boot_cram()
        self.wide = False
        self.table = NAME_TABLE_BASE
        self.flips = 0
        self.psg: list[int] = []
        self.pans: list[int] = []

    def apply(self, chunk: bytes) -> bool:
        pos = 0
        for _ in range(len(chunk)):
            if pos >= len(chunk):
                return False
            kind = chunk[pos]
            if kind == stream.END_FRAME:
                return True
            if kind == stream.END_CHUNK:
                return False
            pos = self._run(kind, chunk, pos)
        return False

    def _run(self, kind: int, chunk: bytes, pos: int) -> int:
        body = pos + 1
        if kind == stream.VRAM:
            address = chunk[body] | (chunk[body + 1] << 8)
            return self._copy(self.vram, address, chunk, body + stream.VRAM_HEADER - 1, VRAM_BYTES)
        if kind in stream.CLOSE_KINDS:
            return self._close(kind, chunk, body)
        if kind == stream.PSG:
            length = chunk[body]
            start = body + stream.PSG_HEADER - 1
            self.psg = [*self.psg, *chunk[start : start + length]]
            return start + length
        if kind == stream.PAN:
            self.pans = [*self.pans, chunk[body]]
            return body + 1
        raise ValueError(unknown_kind(kind, pos))

    def _close(self, kind: int, chunk: bytes, body: int) -> int:
        self.flips += 1
        self.table = console.table_at(chunk[body])
        self.wide = kind == stream.CLOSE_WIDE
        size = stream.close_bytes(kind)
        start = body + stream.CLOSE_HEADER - 1
        self.cram[:size] = np.frombuffer(chunk[start : start + size], dtype=np.uint8)
        return start + size

    def palette_rgb(self) -> npt.NDArray[np.uint8]:
        if self.wide:
            rgb = smscolor.wide_to_rgb(self.cram)
        else:
            rgb = smscolor.colour_to_rgb(self.cram[:CRAM_BYTES])
        return rgb.reshape(smscolor.PALETTE_COUNT, smscolor.PALETTE_ENTRIES, 3)

    @staticmethod
    def _copy(
        memory: npt.NDArray[np.uint8], address: int, chunk: bytes, data: int, size: int
    ) -> int:
        length = chunk[data - 1]
        for offset in range(length):
            memory[(address + offset) % size] = chunk[data + offset]
        return data + length

    def render(
        self, *, columns: int, rows: int, top_row: int, left_column: int = 0
    ) -> npt.NDArray[np.uint8]:
        if top_row + rows > NAME_TABLE_ROWS or left_column + columns > NAME_TABLE_COLUMNS:
            msg = f"a {columns}x{rows} picture at row {top_row} does not fit the name table"
            raise ValueError(msg)

        patterns = pattern.unpack_patterns(
            self.vram[: console.PATTERN_SLOTS * pattern.PATTERN_BYTES].reshape(
                -1, pattern.PATTERN_BYTES
            )
        )
        table = self.palette_rgb()

        out = np.zeros((rows * pattern.TILE_PX, columns * pattern.TILE_PX, 3), dtype=np.uint8)
        for row in range(rows):
            for column in range(columns):
                base = (
                    self.table + ((top_row + row) * NAME_TABLE_COLUMNS + left_column + column) * 2
                )
                entry = int(self.vram[base]) | (int(self.vram[base + 1]) << 8)
                colours = _entry_pixels(entry, patterns, table)
                top = row * pattern.TILE_PX
                left = column * pattern.TILE_PX
                out[top : top + pattern.TILE_PX, left : left + pattern.TILE_PX] = colours
        return out

    def display(self) -> npt.NDArray[np.uint8]:
        return self.render(columns=NAME_TABLE_COLUMNS, rows=VISIBLE_ROWS, top_row=0)


def _entry_pixels(
    entry: int, patterns: npt.NDArray[np.uint8], table: npt.NDArray[np.uint8]
) -> npt.NDArray[np.uint8]:
    cell = patterns[(entry & pattern.INDEX_MASK) % patterns.shape[0]]
    if entry & pattern.HFLIP_BIT:
        cell = cell[:, ::-1]
    if entry & pattern.VFLIP_BIT:
        cell = cell[::-1, :]
    palette = table[1 if entry & pattern.PALETTE_BIT else 0]
    return palette[cell]


def framing(
    display: npt.NDArray[np.uint8],
    *,
    rows: int,
    top_row: int,
    columns: int = NAME_TABLE_COLUMNS,
    left_column: int = 0,
) -> npt.NDArray[np.uint8]:
    if rows < 1 or top_row < 0 or top_row + rows > VISIBLE_ROWS:
        msg = f"a picture of {rows} rows at row {top_row} is not inside {VISIBLE_ROWS} visible rows"
        raise ValueError(msg)

    if columns < 1 or left_column < 0 or left_column + columns > NAME_TABLE_COLUMNS:
        msg = f"a picture of {columns} columns at column {left_column} is not inside the raster"
        raise ValueError(msg)

    outside = np.ones(display.shape[:2], dtype=np.bool_)
    px = pattern.TILE_PX
    outside[
        top_row * px : (top_row + rows) * px, left_column * px : (left_column + columns) * px
    ] = False
    return display[outside]


def lit_fraction(pixels: npt.NDArray[np.uint8], *, level: int = BLACK_LEVEL) -> float:
    if pixels.size == 0:
        return 0.0
    return float((pixels.reshape(-1, 3).max(axis=1) > level).mean())


def unknown_kind(kind: int, pos: int) -> str:
    return f"run kind {kind:#04x} at offset {pos} is not one the player knows"


def frames_of(blob: bytes, *, bank_size: int = limits.BANK_BYTES) -> list[bytes]:
    chunks: list[bytes] = []
    current = bytearray()
    pos = 0
    while pos < len(blob):
        kind = blob[pos]
        if kind == stream.NEXT_BANK:
            pos = ((pos // bank_size) + 1) * bank_size
            continue
        if kind in (stream.END_CHUNK, stream.END_FRAME):
            current.append(kind)
            chunks.append(bytes(current))
            current = bytearray()
            pos += 1
            continue
        if kind == stream.VRAM:
            size = stream.VRAM_HEADER + blob[pos + 3]
        elif kind in stream.CLOSE_KINDS:
            size = stream.CLOSE_HEADER + stream.close_bytes(kind)
        elif kind == stream.PSG:
            size = stream.PSG_HEADER + blob[pos + 1]
        elif kind == stream.PAN:
            size = stream.PAN_BYTES
        else:
            raise ValueError(unknown_kind(kind, pos))
        current += blob[pos : pos + size]
        pos += size
    return chunks
