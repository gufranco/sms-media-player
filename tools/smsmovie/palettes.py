from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

from smsmovie import pattern, smscolor

LLOYD_ROUNDS: Final = 8
ASSIGN_ROUNDS: Final = 6
FEWEST_TO_SPLIT: Final = 2


@dataclass(frozen=True, slots=True)
class FramePalettes:
    cram: npt.NDArray[np.uint8]
    choice: npt.NDArray[np.uint8]
    indices: npt.NDArray[np.uint8]
    rows: int
    columns: int

    def render(self) -> npt.NDArray[np.uint8]:
        table = self.cram.reshape(smscolor.PALETTE_COUNT, smscolor.PALETTE_ENTRIES)
        chosen = table[self.choice]
        colours = np.take_along_axis(
            chosen.reshape(-1, 1, 1, smscolor.PALETTE_ENTRIES),
            self.indices[..., None].astype(np.intp),
            axis=3,
        )[..., 0]
        rgb = smscolor.colour_to_rgb(colours.astype(np.uint8))
        cells = rgb.reshape(self.rows, self.columns, pattern.TILE_PX, pattern.TILE_PX, 3)
        return cells.transpose(0, 2, 1, 3, 4).reshape(
            self.rows * pattern.TILE_PX, self.columns * pattern.TILE_PX, 3
        )


def choose_entries(
    present: npt.NDArray[np.uint8],
    counts: npt.NDArray[np.integer],
    lab: npt.NDArray[np.float32],
    slots: int,
) -> npt.NDArray[np.uint8]:
    if slots < 1:
        msg = "a palette needs at least one entry"
        raise ValueError(msg)
    if present.size == 0:
        return np.zeros(slots, dtype=np.uint8)

    points = lab[present]
    weight = counts.astype(np.float64)
    seeds = _seed_centres(points, weight, count=min(slots, present.size))
    centres = _refine_centres(points, weight, seeds)
    return _padded(present[centres].astype(np.uint8), slots)


def _seed_centres(
    points: npt.NDArray[np.float32], weight: npt.NDArray[np.float64], *, count: int
) -> npt.NDArray[np.intp]:
    order = np.argsort(-weight, kind="stable")
    chosen = [int(order[0])]
    distance = _squared(points, points[chosen[0]])
    for _ in range(count - 1):
        scored = distance * weight
        nxt = int(np.argmax(scored))
        if nxt in chosen:
            nxt = next(i for i in range(points.shape[0]) if i not in chosen)
        chosen = [*chosen, nxt]
        distance = np.minimum(distance, _squared(points, points[nxt]))
    return np.array(chosen, dtype=np.intp)


def _refine_centres(
    points: npt.NDArray[np.float32],
    weight: npt.NDArray[np.float64],
    seeds: npt.NDArray[np.intp],
) -> npt.NDArray[np.intp]:
    centres = seeds.copy()
    for _ in range(LLOYD_ROUNDS):
        assignment = _nearest(points, points[centres])
        moved = False
        for slot in range(centres.size):
            members = np.flatnonzero(assignment == slot)
            if members.size == 0:
                continue
            local = points[members]
            spread = ((local[:, None, :] - local[None, :, :]) ** 2).sum(axis=2)
            cost = (spread * weight[members][None, :]).sum(axis=1)
            best = int(members[int(np.argmin(cost))])
            if best != centres[slot]:
                centres[slot] = best
                moved = True
        if not moved:
            break
    return centres


def _padded(entries: npt.NDArray[np.uint8], slots: int) -> npt.NDArray[np.uint8]:
    if entries.size >= slots:
        return entries
    padding = np.full(slots - entries.size, entries[0], dtype=np.uint8)
    return np.concatenate([entries, padding])


def fit_or_keep(
    frame: npt.NDArray[np.uint8],
    previous: npt.NDArray[np.uint8] | None,
    *,
    margin: float,
    chroma_weight: float = 1.0,
    ordered_dither: float = smscolor.NO_DITHER,
) -> FramePalettes:
    if margin < 0.0:
        msg = f"a palette keep margin must not be negative, got {margin}"
        raise ValueError(msg)
    lab = smscolor.oklab_palette(chroma_weight)
    cells = _cells_of(frame, ordered_dither)
    columns = frame.shape[1] // pattern.TILE_PX
    fresh, fresh_error = _quantise(cells, _fit(cells, lab), lab, columns=columns)
    if previous is None:
        return fresh
    table = previous.reshape(smscolor.PALETTE_COUNT, smscolor.PALETTE_ENTRIES)
    kept, kept_error = _quantise(cells, table, lab, columns=columns)
    return kept if kept_error <= fresh_error * (1.0 + margin) else fresh


def _cells_of(frame: npt.NDArray[np.uint8], ordered_dither: float) -> npt.NDArray[np.uint8]:
    if frame.ndim != smscolor.IMAGE_RANK or frame.shape[2] != smscolor.RGB_CHANNELS:
        msg = f"expected a trailing RGB axis, got shape {frame.shape}"
        raise ValueError(msg)
    colours = smscolor.pack_colour(smscolor.quantise_levels(frame, dither=ordered_dither))
    return pattern.tile_frame(colours)


def _fit(cells: npt.NDArray[np.uint8], lab: npt.NDArray[np.float32]) -> npt.NDArray[np.uint8]:
    cell_lab = lab[cells].reshape(cells.shape[0], -1, 3).mean(axis=1)
    group = _split(cell_lab)
    table = _fit_tables(cells, group, lab)
    flat = cells.reshape(cells.shape[0], -1)
    for _ in range(ASSIGN_ROUNDS):
        moved = _assign(flat, table, lab)
        if np.array_equal(moved, group):
            break
        group = moved
        table = _fit_tables(cells, group, lab)
    return table


def _quantise(
    cells: npt.NDArray[np.uint8],
    table: npt.NDArray[np.uint8],
    lab: npt.NDArray[np.float32],
    *,
    columns: int,
) -> tuple[FramePalettes, float]:
    flat = cells.reshape(cells.shape[0], -1)
    best_index = np.zeros((smscolor.PALETTE_COUNT, *flat.shape), dtype=np.uint8)
    best_error = np.zeros((smscolor.PALETTE_COUNT, cells.shape[0]), dtype=np.float64)
    for index in range(smscolor.PALETTE_COUNT):
        distance = _squared_matrix(lab[flat], lab[table[index]])
        nearest = np.argmin(distance, axis=2)
        best_index[index] = nearest.astype(np.uint8)
        best_error[index] = np.take_along_axis(distance, nearest[..., None], axis=2)[..., 0].sum(
            axis=1
        )
    choice = np.argmin(best_error, axis=0).astype(np.uint8)
    indices = np.take_along_axis(best_index, choice[None, :, None], axis=0)[0]
    fitted = FramePalettes(
        cram=table.reshape(-1).astype(np.uint8),
        choice=choice,
        indices=indices.reshape(cells.shape).astype(np.uint8),
        rows=cells.shape[0] // columns,
        columns=columns,
    )
    return fitted, float(best_error.min(axis=0).sum())


def _squared(
    points: npt.NDArray[np.float32], centre: npt.NDArray[np.float32]
) -> npt.NDArray[np.float64]:
    return ((points.astype(np.float64) - centre.astype(np.float64)) ** 2).sum(axis=1)


def _squared_matrix(
    points: npt.NDArray[np.float32], centres: npt.NDArray[np.float32]
) -> npt.NDArray[np.float64]:
    difference = points.astype(np.float64)[..., None, :] - centres.astype(np.float64)
    return (difference**2).sum(axis=-1)


def _nearest(
    points: npt.NDArray[np.float32], centres: npt.NDArray[np.float32]
) -> npt.NDArray[np.intp]:
    return np.argmin(_squared_matrix(points, centres), axis=-1)


def _split(cell_lab: npt.NDArray[np.float32]) -> npt.NDArray[np.intp]:
    if cell_lab.shape[0] < FEWEST_TO_SPLIT:
        return np.zeros(cell_lab.shape[0], dtype=np.intp)

    axis = int(np.argmax(cell_lab.max(axis=0) - cell_lab.min(axis=0)))
    pivot = float(np.median(cell_lab[:, axis]))
    group = (cell_lab[:, axis] > pivot).astype(np.intp)
    if group.min() == group.max():
        group = np.zeros(cell_lab.shape[0], dtype=np.intp)
        group[cell_lab.shape[0] // 2 :] = 1

    for _ in range(LLOYD_ROUNDS):
        centres = np.stack(
            [
                cell_lab[group == 0].mean(axis=0) if np.any(group == 0) else cell_lab.mean(axis=0),
                cell_lab[group == 1].mean(axis=0) if np.any(group == 1) else cell_lab.mean(axis=0),
            ]
        )
        moved = _nearest(cell_lab, centres)
        if np.array_equal(moved, group):
            break
        group = moved
    return group


BACKDROP_ENTRY: Final = 0
BACKDROP_COLOUR: Final = 0


def _fit_tables(
    cells: npt.NDArray[np.uint8],
    group: npt.NDArray[np.intp],
    lab: npt.NDArray[np.float32],
) -> npt.NDArray[np.uint8]:
    table = np.zeros((smscolor.PALETTE_COUNT, smscolor.PALETTE_ENTRIES), dtype=np.uint8)
    for index in range(smscolor.PALETTE_COUNT):
        members = cells[group == index]
        if members.size == 0:
            members = cells
        present, counts = np.unique(members.reshape(-1), return_counts=True)
        table[index] = choose_entries(
            present.astype(np.uint8), counts, lab, smscolor.PALETTE_ENTRIES
        )
    table[1][BACKDROP_ENTRY] = BACKDROP_COLOUR
    return table


def _assign(
    flat: npt.NDArray[np.uint8],
    table: npt.NDArray[np.uint8],
    lab: npt.NDArray[np.float32],
) -> npt.NDArray[np.intp]:
    error = np.zeros((smscolor.PALETTE_COUNT, flat.shape[0]), dtype=np.float64)
    for index in range(smscolor.PALETTE_COUNT):
        distance = _squared_matrix(lab[flat], lab[table[index]])
        error[index] = np.min(distance, axis=2).sum(axis=1)
    return np.argmin(error, axis=0).astype(np.intp)
