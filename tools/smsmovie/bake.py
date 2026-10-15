from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

import numpy as np
import numpy.typing as npt

from smsmovie import (
    console,
    fidelity,
    limits,
    palettes,
    pattern,
    placement,
    stream,
    tablewrites,
    workingset,
)

NAME_TABLE_BASE: Final = console.NAME_TABLE_BASE
NAME_TABLE_COLUMNS: Final = console.NAME_TABLE_COLUMNS
NAME_TABLE_ROWS: Final = console.NAME_TABLE_ROWS
VISIBLE_ROWS: Final = console.VISIBLE_ROWS
PATTERN_SLOTS: Final = console.PATTERN_SLOTS
RESERVED_SLOTS: Final = console.RESERVED_PATTERNS
DEFAULT_REUSE: Final = 0.008
DEFAULT_DITHER: Final = limits.DEFAULT_DITHER
PALETTE_KEEP_MARGIN: Final = limits.PALETTE_KEEP_MARGIN


@dataclass(frozen=True, slots=True)
class Geometry:
    columns: int
    rows: int
    top_row: int
    left_column: int = 0

    def __post_init__(self) -> None:
        if (
            self.columns < 1
            or self.left_column < 0
            or self.left_column + self.columns > NAME_TABLE_COLUMNS
        ):
            msg = (
                f"a picture of {self.columns} columns at column {self.left_column} "
                "does not fit the name table"
            )
            raise ValueError(msg)
        if self.rows < 1 or self.top_row < 0 or self.top_row + self.rows > VISIBLE_ROWS:
            msg = (
                f"a picture of {self.rows} rows at row {self.top_row} does not fit "
                f"the {VISIBLE_ROWS} rows the console draws"
            )
            raise ValueError(msg)

    @property
    def width(self) -> int:
        return self.columns * pattern.TILE_PX

    @property
    def height(self) -> int:
        return self.rows * pattern.TILE_PX

    @property
    def cells(self) -> int:
        return self.columns * self.rows


@dataclass(slots=True)
class Encoded:
    frames: list[list[bytes]] = field(default_factory=list)
    unplaced: int = 0
    collisions: int = 0
    uploaded: int = 0
    error: float = 0.0
    working_set: float = 0.0
    per_frame_uploads: list[int] = field(default_factory=list)
    per_frame_merged: list[int] = field(default_factory=list)
    per_frame_working_set: list[float] = field(default_factory=list)


def name_table_address(geometry: Geometry, cell: int, base: int = NAME_TABLE_BASE) -> int:
    row = geometry.top_row + cell // geometry.columns
    column = geometry.left_column + cell % geometry.columns
    return base + (row * NAME_TABLE_COLUMNS + column) * 2


@dataclass(slots=True)
class Encoder:
    geometry: Geometry
    budget: int
    cap: int
    capacity: int = PATTERN_SLOTS
    reserved: int = RESERVED_SLOTS
    chroma_weight: float = 1.0
    reuse_threshold: float = DEFAULT_REUSE
    upload_ceiling: int | None = None
    dither: float = DEFAULT_DITHER
    palette_margin: float = PALETTE_KEEP_MARGIN
    cram: npt.NDArray[np.uint8] | None = field(default=None, init=False)
    cache: workingset.WorkingSet = field(init=False)
    committed: npt.NDArray[np.int64] = field(init=False)
    committed_slot: npt.NDArray[np.int64] = field(init=False)
    back: npt.NDArray[np.int64] = field(init=False)
    front: int = field(default=NAME_TABLE_BASE, init=False)
    encoded: Encoded = field(default_factory=Encoded, init=False)
    total_error: float = field(default=0.0, init=False)
    total_working_set: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        if self.upload_ceiling is not None and self.upload_ceiling < 1:
            msg = f"an upload ceiling of {self.upload_ceiling} would never draw a pattern"
            raise ValueError(msg)
        if self.budget <= limits.CLOSE_RESERVE + stream.VRAM_HEADER + stream.TERMINATOR:
            msg = (
                f"a budget of {self.budget} bytes leaves no room for a run beside the "
                f"{limits.CLOSE_RESERVE} every chunk keeps for a deferred closing run"
            )
            raise ValueError(msg)
        self.cache = workingset.WorkingSet(capacity=self.capacity, reserved=self.reserved)
        self.committed = np.full(self.geometry.cells, console.IDLE_CELL, dtype=np.int64)
        self.committed_slot = np.full(self.geometry.cells, -1, dtype=np.int64)
        self.back = np.full(self.geometry.cells, console.IDLE_CELL, dtype=np.int64)

    def add(self, frame: npt.NDArray[np.uint8]) -> list[bytes]:
        self._check_shape(frame)
        back_base = _other_table(self.front)
        fitted = palettes.fit_or_keep(
            frame,
            self.cram,
            margin=self.palette_margin,
            chroma_weight=self.chroma_weight,
            ordered_dither=self.dither,
        )
        self.cram = fitted.cram
        writes, shown, stats = self._encode(frame, fitted, back_base)
        self.back, self.committed, self.front = self.committed, shown, back_base
        chunks = stream.encode_chunks(writes, budget=self.budget, reserve=limits.CLOSE_RESERVE)
        self._record(chunks, stats)
        return chunks

    def _encode(
        self, frame: npt.NDArray[np.uint8], fitted: palettes.FramePalettes, back_base: int
    ) -> tuple[list[stream.Write], npt.NDArray[np.int64], tuple[int, int, int, float, float, int]]:
        features = fidelity.cell_colours(fitted.indices, fitted, self.chroma_weight)
        features = features.reshape(self.geometry.cells, -1)
        placed = self._place(frame, fitted, features)
        shown, next_slot, unplaced = _commit(
            placed.cell_slot, fitted, self.committed, self.committed_slot
        )
        writes = [
            *tablewrites.merge_uploads(placed.uploads),
            *_entry_writes(shown, self.back, geometry=self.geometry, base=back_base),
            _closing(fitted, back_base),
        ]
        error, working_set = self._measure(frame, fitted, placed.cell_slot, features)
        self.committed_slot = next_slot
        stats = (
            unplaced,
            placed.collisions,
            len(placed.uploads),
            error,
            working_set,
            placed.merged,
        )
        return writes, shown, stats

    def _place(
        self,
        frame: npt.NDArray[np.uint8],
        fitted: palettes.FramePalettes,
        features: npt.NDArray[np.float32],
    ) -> placement.Placement:
        source = fidelity.source_cells(frame, self.chroma_weight)
        return placement.place(
            fitted,
            features,
            source=source.reshape(self.geometry.cells, -1),
            cache=self.cache,
            committed_slot=self.committed_slot,
            cap=self.cap,
            chroma_weight=self.chroma_weight,
            reuse_threshold=self.reuse_threshold,
            upload_ceiling=self.upload_ceiling,
        )

    def _measure(
        self,
        frame: npt.NDArray[np.uint8],
        fitted: palettes.FramePalettes,
        cell_slot: npt.NDArray[np.int32],
        features: npt.NDArray[np.float32],
    ) -> tuple[float, float]:
        unflipped = np.zeros(cell_slot.shape[0], dtype=np.bool_)
        return fidelity.displayed_error(
            frame,
            fitted,
            shown_slot=np.where(cell_slot >= 0, cell_slot, self.committed_slot.astype(np.int32)),
            cache=self.cache,
            chroma_weight=self.chroma_weight,
            flips=(unflipped, unflipped),
            floor=features,
        )

    def _check_shape(self, frame: npt.NDArray[np.uint8]) -> None:
        geometry = self.geometry
        if frame.shape[0] != geometry.height or frame.shape[1] != geometry.width:
            msg = (
                f"frame {len(self.encoded.frames)} is {frame.shape[1]}x{frame.shape[0]}, "
                f"which does not match the geometry {geometry.width}x{geometry.height}"
            )
            raise ValueError(msg)

    def _record(self, chunks: list[bytes], stats: tuple[int, int, int, float, float, int]) -> None:
        unplaced, collisions, uploads, error, working_set, merged = stats
        self.encoded.per_frame_uploads.append(uploads)
        self.encoded.per_frame_merged.append(merged)
        self.encoded.per_frame_working_set.append(working_set)
        self.encoded.unplaced += unplaced
        self.encoded.collisions += collisions
        self.encoded.uploaded += uploads
        self.total_error += error
        self.total_working_set += working_set
        self.encoded.frames.append(chunks)

    def result(self) -> Encoded:
        count = len(self.encoded.frames)
        if count == 0:
            msg = "a movie needs at least one frame"
            raise ValueError(msg)
        self.encoded.error = self.total_error / count
        self.encoded.working_set = self.total_working_set / count
        return self.encoded


def encode_frames(
    frames: list[npt.NDArray[np.uint8]],
    *,
    geometry: Geometry,
    budget: int,
    cap: int,
    capacity: int = PATTERN_SLOTS,
    reserved: int = RESERVED_SLOTS,
    chroma_weight: float = 1.0,
    reuse_threshold: float = DEFAULT_REUSE,
    upload_ceiling: int | None = None,
    dither: float = DEFAULT_DITHER,
) -> Encoded:
    if not frames:
        msg = "a movie needs at least one frame"
        raise ValueError(msg)
    encoder = Encoder(
        geometry=geometry,
        budget=budget,
        cap=cap,
        capacity=capacity,
        reserved=reserved,
        chroma_weight=chroma_weight,
        reuse_threshold=reuse_threshold,
        upload_ceiling=upload_ceiling,
        dither=dither,
    )
    for frame in frames:
        encoder.add(frame)
    return encoder.result()


def _commit(
    cell_slot: npt.NDArray[np.int32],
    fitted: palettes.FramePalettes,
    committed: npt.NDArray[np.int64],
    committed_slot: npt.NDArray[np.int64],
) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.int64], int]:
    placed = cell_slot >= 0
    entries = np.array(
        [
            pattern.name_table_entry(index=int(slot), palette=int(choice)) if slot >= 0 else 0
            for slot, choice in zip(cell_slot, fitted.choice, strict=True)
        ],
        dtype=np.int64,
    )
    shown = np.where(placed, entries, committed)
    next_slot = np.where(placed, cell_slot.astype(np.int64), committed_slot)
    return shown, next_slot, int((~placed).sum())


def _entry_writes(
    shown: npt.NDArray[np.int64],
    back: npt.NDArray[np.int64],
    *,
    geometry: Geometry,
    base: int,
) -> list[stream.Write]:
    changed = [cell for cell in range(geometry.cells) if int(shown[cell]) != int(back[cell])]
    cells = tablewrites.fill_gaps(changed, lambda cell: name_table_address(geometry, cell))
    entries = [(name_table_address(geometry, cell, base), int(shown[cell])) for cell in cells]
    return tablewrites.merge_entries(entries)


def _closing(fitted: palettes.FramePalettes, back_base: int) -> stream.Write:
    return stream.Write(
        target=stream.CLOSE,
        address=console.TABLE_REGISTER[back_base],
        data=bytes(fitted.cram.tolist()),
    )


def _other_table(front: int) -> int:
    return console.BACK_TABLE_BASE if front == NAME_TABLE_BASE else NAME_TABLE_BASE
