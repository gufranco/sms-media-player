from __future__ import annotations

from dataclasses import replace
from typing import Final

import numpy as np

from smsmedia import console
from smsmedia.tune import (
    Choice,
    EncodeSettings,
    Footage,
    Sampling,
    Score,
    decode_windows,
    summarise,
    window_costs,
)

DEFAULT_RATE_CANDIDATES: Final = (12.0, 10.0, 8.0, 6.0, 5.0, 4.0, 3.0)
ON_TIME_TARGET: Final = 0.5
RATE_WINDOWS: Final = 2
RATE_WINDOW_SECONDS: Final = 1.5
RATE_SAMPLING: Final = Sampling(windows=RATE_WINDOWS, window_seconds=RATE_WINDOW_SECONDS)


def fields_for(fps: float) -> int:
    return max(1, round(console.NTSC_FIELD_HZ / fps))


def score_rate(
    footage: Footage,
    fps: float,
    *,
    settings: EncodeSettings,
    denoise: float,
    windows: list[tuple[float, float]],
) -> Score:
    decoded = decode_windows(
        footage, geometry=settings.geometry, fps=fps, denoise=denoise, windows=windows
    )
    if not decoded:
        msg = f"no frames decoded while scoring {fps} fps"
        raise ValueError(msg)

    slot = fields_for(fps)
    costs = window_costs(decoded, settings=settings)
    counts = [count for cost in costs for count in cost.chunk_counts]
    cells = sum(len(window) for window in decoded) * settings.geometry.cells
    return replace(
        summarise(costs, cells=cells),
        on_time=float(np.mean([count <= slot for count in counts])),
        median_fields=float(np.median([max(count, slot) for count in counts])),
    )


def pick_rate(
    footage: Footage,
    settings: EncodeSettings,
    *,
    denoise: float,
    candidates: tuple[float, ...] = DEFAULT_RATE_CANDIDATES,
    sampling: Sampling = RATE_SAMPLING,
    on_time_target: float = ON_TIME_TARGET,
) -> Choice:
    if not candidates:
        msg = "at least one frame rate candidate is required"
        raise ValueError(msg)

    sampled = sampling.spread(footage)
    scores: dict[float, Score] = {}
    for value in sorted(candidates, reverse=True):
        score = score_rate(footage, value, settings=settings, denoise=denoise, windows=sampled)
        scores[value] = score
        if score.median_fields <= fields_for(value) and score.on_time >= on_time_target:
            return Choice(value=value, fits=True, scores=scores, label="fps", digits=1)

    return Choice(value=min(scores), fits=False, scores=scores, label="fps", digits=1)
