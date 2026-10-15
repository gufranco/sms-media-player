from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from smsmedia import console, smscolor

END_CHUNK: Final = 0x00
END_FRAME: Final = 0x01
VRAM: Final = 0x02
CLOSE: Final = 0x05
NEXT_BANK: Final = 0xFF

MAX_RUN: Final = 255
VRAM_HEADER: Final = 4
CLOSE_HEADER: Final = 2
TERMINATOR: Final = 1

CLOSE_BYTES: Final = smscolor.CRAM_BYTES
REGISTER_VALUES: Final = 0x100
SMALLEST_BANK: Final = 2


@dataclass(frozen=True, slots=True)
class Write:
    target: int
    address: int
    data: bytes

    def __post_init__(self) -> None:
        if self.target not in (VRAM, CLOSE):
            msg = f"target {self.target} is not a destination the player knows"
            raise ValueError(msg)
        if self.address < 0:
            msg = f"address {self.address} is negative"
            raise ValueError(msg)
        ceiling = console.VRAM_BYTES if self.target == VRAM else REGISTER_VALUES
        if self.address + (len(self.data) if self.target == VRAM else 1) > ceiling:
            msg = f"a run at {self.address:#06x} of {len(self.data)} bytes passes {ceiling:#06x}"
            raise ValueError(msg)


def header_bytes(target: int) -> int:
    if target == VRAM:
        return VRAM_HEADER
    return CLOSE_HEADER


def split_runs(writes: list[Write], *, max_run: int = MAX_RUN) -> list[Write]:
    if max_run < 1 or max_run > MAX_RUN:
        msg = f"a run length must lie in 1 to {MAX_RUN}"
        raise ValueError(msg)

    runs: list[Write] = []
    for write in writes:
        offset = 0
        step = max_run if write.target == VRAM else len(write.data)
        while offset < len(write.data):
            piece = write.data[offset : offset + step]
            runs.append(Write(target=write.target, address=write.address + offset, data=piece))
            offset += len(piece)
    return runs


def encode_chunks(writes: list[Write], *, budget: int, reserve: int = 0) -> list[bytes]:
    longest = budget - reserve - VRAM_HEADER - TERMINATOR
    runs = split_runs(writes, max_run=max(1, min(MAX_RUN, longest)))
    smallest = min((header_bytes(run.target) + 1 for run in runs), default=0)
    if runs and budget < smallest + TERMINATOR:
        msg = f"a budget of {budget} bytes cannot hold even one run"
        raise ValueError(msg)

    chunks: list[bytes] = []
    current = bytearray()
    for run in runs:
        cost = header_bytes(run.target) + len(run.data)
        room = budget - (reserve if not chunks else 0)
        if current and len(current) + cost + TERMINATOR > room:
            current.append(END_CHUNK)
            chunks.append(bytes(current))
            current = bytearray()
        current += _emit(run)

    current.append(END_FRAME)
    chunks.append(bytes(current))
    return chunks


def defer_closes(frames: list[list[bytes]]) -> list[list[bytes]]:
    out: list[list[bytes]] = []
    carried = b""
    for chunks in frames:
        built: list[bytes] = []
        for chunk in chunks:
            body, closing = _split_close(chunk)
            built.append(carried + body)
            carried = closing
        out.append(built)
    if carried:
        out.append([carried + bytes([END_FRAME])])
    return out


def _split_close(chunk: bytes) -> tuple[bytes, bytes]:
    pos = 0
    while pos < len(chunk):
        kind = chunk[pos]
        if kind == CLOSE:
            size = CLOSE_HEADER + CLOSE_BYTES
            return chunk[:pos] + chunk[pos + size :], chunk[pos : pos + size]
        if kind != VRAM:
            break
        pos += VRAM_HEADER + chunk[pos + 3]
    return chunk, b""


def pack_banks(frames: list[list[bytes]], *, bank_size: int) -> tuple[bytes, int]:
    if bank_size < SMALLEST_BANK:
        msg = "a bank must hold at least a chunk and a marker"
        raise ValueError(msg)

    blob = bytearray()
    room = bank_size
    for chunks in frames:
        for chunk in chunks:
            if len(chunk) + TERMINATOR > bank_size:
                msg = f"a chunk of {len(chunk)} bytes does not fit a {bank_size}-byte bank"
                raise ValueError(msg)
            if len(chunk) + TERMINATOR > room:
                blob.append(NEXT_BANK)
                blob += bytes(room - TERMINATOR)
                room = bank_size
            blob += chunk
            room -= len(chunk)

    if room:
        blob += bytes(room)
    banks = len(blob) // bank_size
    return bytes(blob), banks


def _emit(run: Write) -> bytes:
    if run.target == VRAM:
        return (
            bytes([VRAM, run.address & 0xFF, (run.address >> 8) & 0xFF, len(run.data)]) + run.data
        )
    return bytes([CLOSE, run.address & 0xFF]) + run.data


def pace(chunks: list[bytes], *, fields: int) -> list[bytes]:
    if fields < 1:
        msg = "a frame must occupy at least one field"
        raise ValueError(msg)
    if len(chunks) >= fields:
        return chunks
    padding = [bytes([END_CHUNK])] * (fields - len(chunks))
    return padding + chunks
