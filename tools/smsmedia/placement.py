from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

from smsmedia import fidelity, palettes, pattern, smscolor, workingset

BADLY_OFF: Final = 0.25
DISTANCE_CHUNK: Final = 16
GUARD_ROUNDS: Final = 4
REBALANCE_ROUNDS: Final = 4
REBALANCE_SCALES: Final = (1, 2, 4, 8)


@dataclass(frozen=True, slots=True)
class CellViews:
    perceived: npt.NDArray[np.float32]
    rendered: npt.NDArray[np.float32]
    source: npt.NDArray[np.float32]

    def of(self, cells: npt.NDArray[np.intp]) -> CellViews:
        return CellViews(self.perceived[cells], self.rendered[cells], self.source[cells])


@dataclass(frozen=True, slots=True)
class Placement:
    cell_slot: npt.NDArray[np.int32]
    uploads: list[tuple[int, bytes]]
    collisions: int
    merged: int


def place(
    fitted: palettes.FramePalettes,
    features: npt.NDArray[np.float32],
    *,
    source: npt.NDArray[np.float32],
    cache: workingset.WorkingSet,
    committed_slot: npt.NDArray[np.int64],
    cap: int,
    chroma_weight: float,
    reuse_threshold: float,
    upload_ceiling: int | None,
) -> Placement:
    referenced = {int(slot) for slot in committed_slot if slot >= 0}
    reused = reuse_residents(
        fitted, features, cache, chroma_weight=chroma_weight, threshold=reuse_threshold
    )
    protected = referenced | {int(slot) for slot in reused if slot >= 0}
    fresh = np.flatnonzero(reused == workingset.UNPLACED)
    room = min(cap, free_slots(cache, protected))
    if fresh.size == 0 or room == 0:
        return Placement(cell_slot=reused, uploads=[], collisions=0, merged=0)
    plan = _Fresh(cells=fresh, room=room, protected=protected, ceiling=upload_ceiling)
    return _place_fresh(
        fitted, (features, source), reused, cache=cache, plan=plan, weight=chroma_weight
    )


@dataclass(frozen=True, slots=True)
class _Fresh:
    cells: npt.NDArray[np.intp]
    room: int
    protected: set[int]
    ceiling: int | None


def _place_fresh(
    fitted: palettes.FramePalettes,
    views: tuple[npt.NDArray[np.float32], npt.NDArray[np.float32]],
    reused: npt.NDArray[np.int32],
    *,
    cache: workingset.WorkingSet,
    plan: _Fresh,
    weight: float,
) -> Placement:
    features, source = views
    placed, uploads, merged = _upload_fresh(fitted, views, plan, cache=cache)
    cell_slot = reused.copy()
    cell_slot[plan.cells] = placed
    candidates = plan.protected | {int(slot) for slot in placed if slot >= 0}
    settled = better_standins(
        fitted,
        features,
        source,
        cell_slot=cell_slot,
        cache=cache,
        candidates=candidates,
        chroma_weight=weight,
    )
    collisions = sum(1 for slot, _ in uploads if slot in plan.protected)
    return Placement(cell_slot=settled, uploads=uploads, collisions=collisions, merged=merged)


def _upload_fresh(
    fitted: palettes.FramePalettes,
    views: tuple[npt.NDArray[np.float32], npt.NDArray[np.float32]],
    plan: _Fresh,
    *,
    cache: workingset.WorkingSet,
) -> tuple[npt.NDArray[np.int32], list[tuple[int, bytes]], int]:
    features, source = views[0][plan.cells], views[1][plan.cells]
    cells = CellViews(fidelity.perceived_cells(features), features, source)
    tiles = fitted.indices[plan.cells]
    keep, mapping = merge_by_palette(tiles, cells, fitted.choice[plan.cells], room=plan.room)
    keep, mapping = within_ceiling(keep, mapping, plan.ceiling)
    allocation = cache.allocate(pattern.pack_patterns(keep), referenced=plan.protected)
    served = mapping >= 0
    placed = np.full(mapping.shape, workingset.UNPLACED, dtype=np.int32)
    if keep.shape[0]:
        placed[served] = allocation.slots[mapping[served]]
    substituted = served.copy()
    if keep.shape[0]:
        own = keep[mapping[served]].reshape(int(served.sum()), -1)
        substituted[served] = np.any(own != tiles[served].reshape(own.shape), axis=1)
    return placed, allocation.uploads, int(substituted.sum())


def free_slots(cache: workingset.WorkingSet, protected: set[int]) -> int:
    allocatable = range(cache.reserved, cache.capacity)
    return sum(1 for slot in allocatable if slot not in protected)


def within_ceiling(
    keep: npt.NDArray[np.uint8],
    mapping: npt.NDArray[np.intp],
    ceiling: int | None,
) -> tuple[npt.NDArray[np.uint8], npt.NDArray[np.intp]]:
    if ceiling is None or keep.shape[0] <= ceiling:
        return keep, mapping

    demand = np.bincount(mapping, minlength=keep.shape[0])
    survivors = np.sort(np.argsort(-demand, kind="stable")[:ceiling])
    remap = np.full(keep.shape[0], -1, dtype=np.intp)
    remap[survivors] = np.arange(survivors.size)
    return keep[survivors], remap[mapping]


def reuse_residents(
    fitted: palettes.FramePalettes,
    features: npt.NDArray[np.float32],
    cache: workingset.WorkingSet,
    *,
    chroma_weight: float,
    threshold: float,
) -> npt.NDArray[np.int32]:
    slots, data = cache.residents()
    result = np.full(fitted.choice.shape[0], workingset.UNPLACED, dtype=np.int32)
    if slots.size == 0:
        return result

    lab = smscolor.oklab_palette(chroma_weight)
    table = fitted.cram.reshape(smscolor.PALETTE_COUNT, smscolor.PALETTE_ENTRIES)
    indices = pattern.unpack_patterns(data).reshape(data.shape[0], -1)

    for palette in range(smscolor.PALETTE_COUNT):
        members = np.flatnonzero(fitted.choice == palette)
        if members.size == 0:
            continue
        rendered = lab[table[palette][indices].astype(np.intp)].reshape(indices.shape[0], -1)
        matched = workingset.match_residents(features[members], rendered, threshold=threshold)
        found = matched != workingset.UNPLACED
        result[members[found]] = slots[matched[found]]

    return result


def merge_by_palette(
    tiles: npt.NDArray[np.uint8],
    views: CellViews,
    choice: npt.NDArray[np.uint8],
    *,
    room: int,
) -> tuple[npt.NDArray[np.uint8], npt.NDArray[np.intp]]:
    groups = [np.flatnonzero(choice == palette) for palette in np.unique(choice)]
    distinct = [
        np.unique(tiles[group].reshape(group.size, -1), axis=0).shape[0] for group in groups
    ]
    shares = share_room(distinct, room)
    merged = [
        _merge_group(tiles, views, group, share)
        for group, share in zip(groups, shares, strict=True)
    ]
    for _ in range(REBALANCE_ROUNDS):
        moved = _rebalanced(tiles, views, groups, shares=shares, merged=merged, distinct=distinct)
        if moved is None:
            break
        shares, merged = moved
    return _combined(tiles, groups, merged)


@dataclass(frozen=True, slots=True)
class _GroupMerge:
    keep: npt.NDArray[np.uint8]
    local: npt.NDArray[np.intp]
    wrong: int


def _merge_group(
    tiles: npt.NDArray[np.uint8], views: CellViews, group: npt.NDArray[np.intp], share: int
) -> _GroupMerge:
    if share == 0:
        return _GroupMerge(tiles[:0], np.full(group.size, -1, dtype=np.intp), group.size)
    keep, local = guarded_merge(tiles[group], views.of(group), cap=share)
    _, wrong = _judged(tiles[group], views.of(group), keep, local)
    return _GroupMerge(keep, local, int(wrong.sum()))


def _rebalanced(
    tiles: npt.NDArray[np.uint8],
    views: CellViews,
    groups: list[npt.NDArray[np.intp]],
    *,
    shares: list[int],
    merged: list[_GroupMerge],
    distinct: list[int],
) -> tuple[list[int], list[_GroupMerge]] | None:
    needy = max(range(len(groups)), key=lambda index: merged[index].wrong)
    donors = [index for index in range(len(groups)) if index != needy and shares[index] > 1]
    if merged[needy].wrong == 0 or not donors:
        return None
    donor = min(donors, key=lambda index: (merged[index].wrong, -shares[index]))
    most = min(shares[donor] - 1, distinct[needy] - shares[needy])
    before = sum(item.wrong for item in merged)
    for step in sorted({min(most, merged[needy].wrong * scale) for scale in REBALANCE_SCALES}):
        if step < 1:
            continue
        trial = [*shares]
        trial[needy], trial[donor] = shares[needy] + step, shares[donor] - step
        again = [*merged]
        for index in (needy, donor):
            again[index] = _merge_group(tiles, views, groups[index], trial[index])
        if sum(item.wrong for item in again) < before:
            return trial, again
    return None


def _combined(
    tiles: npt.NDArray[np.uint8], groups: list[npt.NDArray[np.intp]], merged: list[_GroupMerge]
) -> tuple[npt.NDArray[np.uint8], npt.NDArray[np.intp]]:
    mapping = np.full(tiles.shape[0], -1, dtype=np.intp)
    kept: list[npt.NDArray[np.uint8]] = []
    offset = 0
    for group, item in zip(groups, merged, strict=True):
        if item.keep.shape[0] == 0:
            continue
        mapping[group] = np.where(item.local >= 0, item.local + offset, -1)
        kept = [*kept, item.keep]
        offset += item.keep.shape[0]
    if not kept:
        return tiles[:0], mapping
    return _shared_patterns(np.concatenate(kept), mapping)


def share_room(distinct: list[int], room: int) -> list[int]:
    if sum(distinct) <= room:
        return list(distinct)
    largest = sorted(range(len(distinct)), key=lambda index: -distinct[index])[:room]
    shares = [1 if index in largest and count else 0 for index, count in enumerate(distinct)]
    for _ in range(room - sum(shares)):
        wanting = [index for index, count in enumerate(distinct) if shares[index] < count]
        neediest = max(
            wanting,
            key=lambda index: distinct[index] / shares[index] if shares[index] else float("inf"),
        )
        shares = [*shares[:neediest], shares[neediest] + 1, *shares[neediest + 1 :]]
    return shares


def _shared_patterns(
    keep: npt.NDArray[np.uint8], mapping: npt.NDArray[np.intp]
) -> tuple[npt.NDArray[np.uint8], npt.NDArray[np.intp]]:
    unique, inverse = np.unique(keep.reshape(keep.shape[0], -1), axis=0, return_inverse=True)
    remapped = np.where(mapping >= 0, inverse.reshape(-1)[np.maximum(mapping, 0)], -1)
    return unique.reshape(-1, *keep.shape[1:]), remapped.astype(np.intp)


def better_standins(
    fitted: palettes.FramePalettes,
    features: npt.NDArray[np.float32],
    source: npt.NDArray[np.float32],
    *,
    cell_slot: npt.NDArray[np.int32],
    cache: workingset.WorkingSet,
    candidates: set[int],
    chroma_weight: float,
) -> npt.NDArray[np.int32]:
    slots, data = cache.residents()
    rows = np.flatnonzero(np.isin(slots, sorted(candidates)))
    if rows.size == 0:
        return cell_slot
    tiles = pattern.unpack_patterns(data[rows]).reshape(rows.size, -1)
    table = fitted.cram.reshape(smscolor.PALETTE_COUNT, smscolor.PALETTE_ENTRIES)
    lab = smscolor.oklab_palette(chroma_weight)
    current, stand_in = _stand_ins(fitted, tiles, slots[rows], cell_slot=cell_slot)
    result = cell_slot.copy()
    for palette in range(smscolor.PALETTE_COUNT):
        members = np.flatnonzero(stand_in & (fitted.choice == palette))
        if members.size == 0:
            continue
        raw = lab[table[palette][tiles].astype(np.intp)].reshape(rows.size, -1)
        best = _closer_on_both(features[members], source[members], raw, current[members])
        found = best >= 0
        result[members[found]] = slots[rows][best[found]]
    return result


def _stand_ins(
    fitted: palettes.FramePalettes,
    tiles: npt.NDArray[np.uint8],
    candidate_slots: npt.NDArray[np.int32],
    *,
    cell_slot: npt.NDArray[np.int32],
) -> tuple[npt.NDArray[np.intp], npt.NDArray[np.bool_]]:
    own = fitted.indices.reshape(fitted.indices.shape[0], -1)
    row_of = np.full(int(max(candidate_slots.max(), cell_slot.max())) + 1, -1, dtype=np.intp)
    row_of[candidate_slots] = np.arange(candidate_slots.size)
    current = np.where(cell_slot >= 0, row_of[np.maximum(cell_slot, 0)], -1)
    stand_in = current >= 0
    stand_in[stand_in] = np.any(tiles[current[stand_in]] != own[stand_in], axis=1)
    return current, stand_in


def _closer_on_both(
    cells: npt.NDArray[np.float32],
    source: npt.NDArray[np.float32],
    candidates: npt.NDArray[np.float32],
    current: npt.NDArray[np.intp],
) -> npt.NDArray[np.intp]:
    exact = _squared_distances(cells, candidates)
    seen = _squared_distances(fidelity.perceived_cells(cells), fidelity.perceived_cells(candidates))
    picked = np.arange(cells.shape[0])
    allowed = (exact < exact[picked, current][:, None]) & (seen < seen[picked, current][:, None])
    allowed = allowed & (_mean_distances(source, candidates) <= BADLY_OFF)
    masked = np.where(allowed, seen, np.inf)
    best = np.argmin(masked, axis=1)
    return np.where(np.isfinite(masked[picked, best]), best, -1)


def _squared_distances(
    left: npt.NDArray[np.float32], right: npt.NDArray[np.float32]
) -> npt.NDArray[np.float64]:
    a = left.astype(np.float64)
    b = right.astype(np.float64)
    return (a * a).sum(axis=1)[:, None] - 2.0 * (a @ b.T) + (b * b).sum(axis=1)[None, :]


def guarded_merge(
    tiles: npt.NDArray[np.uint8],
    views: CellViews,
    *,
    cap: int,
) -> tuple[npt.NDArray[np.uint8], npt.NDArray[np.intp]]:
    best = workingset.merge_to_cap(tiles, cap=cap, features=views.perceived)
    error, wrong = _judged(tiles, views, *best)
    forced = np.zeros(tiles.shape[0], dtype=bool)
    for _ in range(GUARD_ROUNDS):
        if not wrong.any():
            break
        widened = _worst_within(tiles, forced | wrong, error, limit=cap // 2)
        if np.array_equal(widened, forced):
            break
        forced = widened
        trial = _own_tiles_first(tiles, views.perceived, forced, cap=cap)
        trial_error, trial_wrong = _judged(tiles, views, *trial)
        if int(trial_wrong.sum()) >= int(wrong.sum()):
            break
        best, error, wrong = trial, trial_error, trial_wrong
    return best


def _judged(
    tiles: npt.NDArray[np.uint8],
    views: CellViews,
    keep: npt.NDArray[np.uint8],
    mapping: npt.NDArray[np.intp],
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.bool_]]:
    flat = tiles.reshape(tiles.shape[0], -1)
    error = cell_error(views.source, _appearance(tiles, views.rendered, keep, mapping))
    stand_in = np.any(keep[mapping].reshape(flat.shape) != flat, axis=1)
    return error, (error > BADLY_OFF) & stand_in


def cell_error(
    raw: npt.NDArray[np.float32], shown: npt.NDArray[np.float32]
) -> npt.NDArray[np.float64]:
    pixels = (raw - shown).reshape(raw.shape[0], -1, 3).astype(np.float64)
    return np.sqrt((pixels * pixels).sum(axis=2)).mean(axis=1)


def _appearance(
    tiles: npt.NDArray[np.uint8],
    raw: npt.NDArray[np.float32],
    keep: npt.NDArray[np.uint8],
    mapping: npt.NDArray[np.intp],
) -> npt.NDArray[np.float32]:
    first = {tile.tobytes(): cell for cell, tile in reversed(list(enumerate(tiles)))}
    source = np.array([first[tile.tobytes()] for tile in keep], dtype=np.intp)
    return raw[source[mapping]]


def _worst_within(
    tiles: npt.NDArray[np.uint8],
    candidates: npt.NDArray[np.bool_],
    error: npt.NDArray[np.float64],
    *,
    limit: int,
) -> npt.NDArray[np.bool_]:
    chosen = np.zeros(tiles.shape[0], dtype=bool)
    seen: set[bytes] = set()
    for cell in np.flatnonzero(candidates)[np.argsort(-error[candidates], kind="stable")]:
        key = tiles[cell].tobytes()
        if key not in seen and len(seen) >= limit:
            continue
        seen = seen | {key}
        chosen[cell] = True
    return chosen


def _own_tiles_first(
    tiles: npt.NDArray[np.uint8],
    features: npt.NDArray[np.float32],
    forced: npt.NDArray[np.bool_],
    *,
    cap: int,
) -> tuple[npt.NDArray[np.uint8], npt.NDArray[np.intp]]:
    own, inverse = np.unique(
        tiles[forced].reshape(int(forced.sum()), -1), axis=0, return_inverse=True
    )
    mapping = np.full(tiles.shape[0], -1, dtype=np.intp)
    mapping[forced] = inverse.reshape(-1)
    rest = np.flatnonzero(~forced)
    kept = own.reshape(-1, *tiles.shape[1:])
    if rest.size:
        others, local = workingset.merge_to_cap(
            tiles[rest], cap=cap - own.shape[0], features=features[rest]
        )
        mapping[rest] = local + own.shape[0]
        kept = np.concatenate([kept, others])
    return _shared_patterns(kept, mapping)


def _mean_distances(
    cells: npt.NDArray[np.float32], candidates: npt.NDArray[np.float32]
) -> npt.NDArray[np.float64]:
    right = candidates.reshape(1, candidates.shape[0], -1, 3).astype(np.float64)
    rows = [
        np.sqrt(
            (
                (cells[start : start + DISTANCE_CHUNK].reshape(-1, 1, right.shape[2], 3) - right)
                ** 2
            ).sum(axis=3)
        ).mean(axis=2)
        for start in range(0, cells.shape[0], DISTANCE_CHUNK)
    ]
    return np.concatenate(rows) if rows else np.zeros((0, candidates.shape[0]))
