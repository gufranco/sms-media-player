from __future__ import annotations

import numpy as np

from smsggmedia import tune

GEOMETRY = tune.bake.Geometry(columns=32, rows=18, top_row=3)


SMALL = tune.bake.Geometry(columns=8, rows=6, top_row=0)


def pick(table, *, max_per_frame=None):
    return tune.decide(
        table,
        key=lambda score: score.error,
        bar=tune.Bar(max_per_frame=max_per_frame, stale_tolerance=None),
        label="denoise",
        digits=1,
    )


OFFSET = tune.bake.Geometry(columns=8, rows=6, top_row=2)


ORANGE = (170, 85, 0)


BLUE = (0, 85, 255)


def split_frame(left: tuple[int, int, int], right: tuple[int, int, int]) -> np.ndarray:
    frame = np.zeros((OFFSET.height, OFFSET.width, 3), dtype=np.uint8)
    frame[:, : OFFSET.width // 2] = left
    frame[:, OFFSET.width // 2 :] = right
    return frame


def two_frames() -> list[np.ndarray]:
    return [split_frame(ORANGE, BLUE), split_frame(BLUE, ORANGE)]


def pick_on_working_set(
    scores: dict[float, tune.Score], *, tie: float, max_per_frame: float | None = None
) -> tune.Choice:
    return tune.decide(
        scores,
        key=lambda score: score.working_set,
        bar=tune.Bar(max_per_frame=max_per_frame, stale_tolerance=None, tie=tie),
        label="reuse",
        digits=4,
    )


def grey_ramp_window() -> list[list[np.ndarray]]:
    ramp = np.linspace(0, 255, SMALL.width).astype(np.uint8)
    frame = np.repeat(np.repeat(ramp[None, :, None], SMALL.height, axis=0), 3, axis=2)
    return [[frame, frame]]
