from __future__ import annotations

from collections.abc import Callable
from typing import Final

from smsmovie import pattern, stream

NAME_GAP_FILL: Final = 1
ENTRY_BYTES: Final = 2


def merge_uploads(uploads: list[tuple[int, bytes]]) -> list[stream.Write]:
    if not uploads:
        return []
    slots = [slot for slot, _ in uploads]
    if len(set(slots)) != len(slots):
        msg = f"two uploads target the same slot among {sorted(slots)}"
        raise ValueError(msg)
    ordered = sorted(uploads)
    runs: list[stream.Write] = []
    start = ordered[0][0]
    payload = bytearray(ordered[0][1])
    previous = start
    for slot, data in ordered[1:]:
        if slot == previous + 1:
            payload += data
            previous = slot
            continue
        runs.append(_pattern_run(start, payload))
        start = slot
        previous = slot
        payload = bytearray(data)
    runs.append(_pattern_run(start, payload))
    return runs


def _pattern_run(slot: int, payload: bytearray) -> stream.Write:
    return stream.Write(
        target=stream.VRAM, address=slot * pattern.PATTERN_BYTES, data=bytes(payload)
    )


def merge_entries(entries: list[tuple[int, int]]) -> list[stream.Write]:
    if not entries:
        return []
    ordered = sorted(entries)
    runs: list[stream.Write] = []
    start = ordered[0][0]
    payload = bytearray(ordered[0][1].to_bytes(ENTRY_BYTES, "little"))
    previous = start
    for address, entry in ordered[1:]:
        if address == previous + ENTRY_BYTES:
            payload += entry.to_bytes(ENTRY_BYTES, "little")
            previous = address
            continue
        runs.append(stream.Write(target=stream.VRAM, address=start, data=bytes(payload)))
        start = address
        previous = address
        payload = bytearray(entry.to_bytes(ENTRY_BYTES, "little"))
    runs.append(stream.Write(target=stream.VRAM, address=start, data=bytes(payload)))
    return runs


def fill_gaps(changed: list[int], address_of: Callable[[int], int]) -> list[int]:
    filled: list[int] = []
    for cell in changed:
        if filled:
            previous = filled[-1]
            gap = cell - previous - 1
            span = address_of(cell) - address_of(previous)
            if 0 < gap <= NAME_GAP_FILL and span == ENTRY_BYTES * (cell - previous):
                filled += list(range(previous + 1, cell))
        filled.append(cell)
    return filled
