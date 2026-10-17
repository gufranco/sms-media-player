from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

from smsggmedia import console, pattern

PATTERN_BYTES: Final = console.PATTERN_BYTES
UNPLACED: Final = -1
LLOYD_ROUNDS: Final = 6


@dataclass(frozen=True, slots=True)
class Allocation:
    slots: npt.NDArray[np.int32]
    uploads: list[tuple[int, bytes]]


class WorkingSet:
    def __init__(self, *, capacity: int, reserved: int = 0) -> None:
        if capacity < 1:
            msg = "a working set needs a capacity of at least one slot"
            raise ValueError(msg)
        if reserved < 0:
            msg = "a reservation cannot be negative"
            raise ValueError(msg)
        if reserved >= capacity:
            msg = f"reserving {reserved} of {capacity} slots leaves nothing to allocate"
            raise ValueError(msg)
        self.capacity = capacity
        self.reserved = reserved
        self._occupant: list[bytes | None] = [None] * capacity
        self._where: dict[bytes, int] = {}

    def resident(self) -> int:
        return len(self._where)

    def allocate(
        self,
        patterns: npt.NDArray[np.uint8],
        *,
        referenced: set[int],
    ) -> Allocation:
        if patterns.ndim != pattern.BATCH_RANK or patterns.shape[1] != PATTERN_BYTES:
            msg = f"patterns must be rows of {PATTERN_BYTES} bytes, got {patterns.shape}"
            raise ValueError(msg)

        payloads = [patterns[row].tobytes() for row in range(patterns.shape[0])]
        kept = {self._where[payload] for payload in payloads if payload in self._where}
        free = [
            slot
            for slot in range(self.reserved, self.capacity)
            if slot not in referenced and slot not in kept
        ]
        slots = np.full(len(payloads), UNPLACED, dtype=np.int32)
        uploads: list[tuple[int, bytes]] = []
        for row, payload in enumerate(payloads):
            existing = self._where.get(payload)
            if existing is not None:
                slots[row] = existing
            elif len(uploads) < len(free):
                slots[row] = self._claim(free[len(uploads)], payload)
                uploads = [*uploads, (int(slots[row]), payload)]
        return Allocation(slots=slots, uploads=uploads)

    def _claim(self, slot: int, payload: bytes) -> int:
        previous = self._occupant[slot]
        if previous is not None:
            del self._where[previous]
        self._occupant[slot] = payload
        self._where[payload] = slot
        return slot

    def payload_of(self, slot: int) -> bytes | None:
        return self._occupant[slot]

    def keep_only(self, slots: set[int]) -> None:
        self._occupant = [
            payload if slot in slots else None for slot, payload in enumerate(self._occupant)
        ]
        self._where = {
            payload: slot for slot, payload in enumerate(self._occupant) if payload is not None
        }

    def residents(self) -> tuple[npt.NDArray[np.int32], npt.NDArray[np.uint8]]:
        slots = sorted(self._where.values())
        data = np.zeros((len(slots), PATTERN_BYTES), dtype=np.uint8)
        for row, slot in enumerate(slots):
            payload = self._occupant[slot]
            if payload is not None:
                data[row] = np.frombuffer(payload, dtype=np.uint8)
        return np.array(slots, dtype=np.int32), data


def match_residents(
    cells: npt.NDArray[np.floating],
    residents: npt.NDArray[np.floating],
    *,
    threshold: float,
) -> npt.NDArray[np.intp]:
    if threshold < 0.0:
        msg = "a reuse threshold must not be negative"
        raise ValueError(msg)
    if residents.shape[0] == 0:
        return np.full(cells.shape[0], UNPLACED, dtype=np.intp)

    best = np.full(cells.shape[0], UNPLACED, dtype=np.intp)
    error = np.full(cells.shape[0], np.inf, dtype=np.float64)
    width = cells.shape[1]

    for row in range(residents.shape[0]):
        difference = cells - residents[row]
        cost = (difference * difference).sum(axis=1) / width
        closer = cost < error
        error[closer] = cost[closer]
        best[closer] = row

    best[error > threshold] = UNPLACED
    return best


def merge_to_cap(
    tiles: npt.NDArray[np.uint8],
    *,
    cap: int,
    features: npt.NDArray[np.floating] | None = None,
    rounds: int = LLOYD_ROUNDS,
) -> tuple[npt.NDArray[np.uint8], npt.NDArray[np.intp]]:
    if cap < 1:
        msg = "a cap of at least one tile is required"
        raise ValueError(msg)
    if tiles.ndim != pattern.TILE_STACK_RANK:
        msg = f"tiles must be a batch of 2-D cells, got shape {tiles.shape}"
        raise ValueError(msg)

    flat = tiles.reshape(tiles.shape[0], -1)
    unique, index, inverse = np.unique(flat, axis=0, return_index=True, return_inverse=True)
    inverse = inverse.reshape(-1)
    if unique.shape[0] <= cap:
        return unique.reshape(-1, *tiles.shape[1:]), inverse

    if features is None:
        points = unique.astype(np.float64)
    else:
        points = features.reshape(features.shape[0], -1)[index].astype(np.float64)
    centres, assignment = _medoids(points, _farthest_first(points, cap), rounds=rounds)
    keep = unique[centres]
    mapping = assignment[inverse].astype(np.intp)
    return keep.reshape(-1, *tiles.shape[1:]), mapping


def _medoids(
    points: npt.NDArray[np.float64], seeds: npt.NDArray[np.intp], *, rounds: int
) -> tuple[npt.NDArray[np.intp], npt.NDArray[np.intp]]:
    centres = seeds.copy()
    assignment = _nearest(points, points[centres])
    for _ in range(rounds):
        moved = False
        for slot in range(centres.size):
            members = np.flatnonzero(assignment == slot)
            if members.size == 0:
                continue
            local = points[members]
            cost = ((local[:, None, :] - local[None, :, :]) ** 2).sum(axis=2).sum(axis=1)
            best = int(members[int(np.argmin(cost))])
            if best != centres[slot]:
                centres[slot] = best
                moved = True
        assignment = _nearest(points, points[centres])
        if not moved:
            break
    return centres, assignment


def _farthest_first(points: npt.NDArray[np.float64], count: int) -> npt.NDArray[np.intp]:
    chosen = [0]
    distance = ((points - points[0]) ** 2).sum(axis=1)
    for _ in range(count - 1):
        nxt = int(np.argmax(distance))
        if nxt in chosen:
            nxt = next(i for i in range(points.shape[0]) if i not in chosen)
        chosen = [*chosen, nxt]
        distance = np.minimum(distance, ((points - points[nxt]) ** 2).sum(axis=1))
    return np.array(chosen, dtype=np.intp)


def _nearest(
    points: npt.NDArray[np.float64], centres: npt.NDArray[np.float64]
) -> npt.NDArray[np.intp]:
    difference = points[:, None, :] - centres[None, :, :]
    return np.argmin((difference**2).sum(axis=2), axis=1).astype(np.intp)
