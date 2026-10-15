from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

import numpy as np
import numpy.typing as npt

from smsmovie import bake, console, stream

FIELD_HZ: Final = console.NTSC_FIELD_HZ


@dataclass(slots=True)
class Schedule:
    frames: list[list[bytes]] = field(default_factory=list)
    picks: list[int] = field(default_factory=list)
    lags: list[float] = field(default_factory=list)
    lead: int = 0
    unshown_tail: int = 0


def field_of(index: int, *, fps: float) -> float:
    return index * FIELD_HZ / fps


def due_at(position: int, *, fps: float, slot: int) -> int:
    return round((position + slot - 1) * fps / FIELD_HZ)


def by_clock(
    decoded: list[npt.NDArray[np.uint8]],
    *,
    fps: float,
    slot: int,
    encoder: bake.Encoder,
    pace: bool = True,
) -> Schedule:
    _check(decoded, slot=slot)
    result = Schedule()
    position = 0
    pick = min(due_at(position, fps=fps, slot=slot), len(decoded) - 1)
    for _ in range(len(decoded)):
        chunks = encoder.add(decoded[pick])
        shown = stream.pace(chunks, fields=slot) if pace else chunks
        if not result.frames:
            result.lead = max(len(shown) - slot, 0)
        completed = position + len(shown) - 1 - result.lead
        result.frames.append(shown)
        result.picks.append(pick)
        result.lags.append((completed - field_of(pick, fps=fps)) / FIELD_HZ)
        position += len(shown)
        pick = max(pick + 1, due_at(position - result.lead, fps=fps, slot=slot))
        if pick >= len(decoded):
            break
    result.unshown_tail = len(decoded) - 1 - result.picks[-1]
    return result


def _check(decoded: list[npt.NDArray[np.uint8]], *, slot: int) -> None:
    if not decoded:
        msg = "a movie needs at least one frame"
        raise ValueError(msg)
    if slot < 1:
        msg = "a frame must occupy at least one field"
        raise ValueError(msg)
