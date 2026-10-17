from __future__ import annotations

import numpy as np
from fmvcore.capture import Frames, Played

from smsggmedia import lattice, replay


def replay_fields(blob: bytes) -> Played:
    machine = replay.Machine()
    shown: list[Frames] = []
    completes: list[int] = []
    picture = machine.display()
    flipped: list[int] = []
    for index, chunk in enumerate(replay.frames_of(blob)):
        flips = machine.flips
        done = machine.apply(chunk)
        if len(chunk) > 1:
            picture = machine.display()
        shown.append(picture)
        if done:
            completes.append(index)
        if machine.flips > flips:
            flipped.append(index)
    if flipped:
        completes = flipped
    if not completes:
        msg = "the stream completes no frame"
        raise ValueError(msg)
    return Played(fields=np.stack(shown[: completes[-1] + 1]), completes=completes)


def picture_frames(played: Played, *, top: int, height: int, width: int, left: int = 0) -> Frames:
    return played.fields[played.completes, top : top + height, left : left + width]


def lattice_floor(wanted: Frames, space: lattice.Lattice = lattice.MASTER_SYSTEM) -> float:
    return space.floor(wanted)
