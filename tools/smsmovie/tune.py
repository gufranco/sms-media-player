from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final

import numpy as np
import numpy.typing as npt

from smsmovie import bake, capture, frames, limits, pattern, stream

DEFAULT_CANDIDATES: Final = (0.0, 2.0, 4.0, 8.0)
DEFAULT_REUSE_CANDIDATES: Final = (0.016, 0.008, 0.004, 0.002, 0.001)
DEFAULT_WINDOWS: Final = 3
DEFAULT_WINDOW_SECONDS: Final = 2.0
STALE_TOLERANCE: Final = 0.005
SCORE_TIE: Final = 0.05
P90: Final = 90


@dataclass(frozen=True, slots=True)
class Footage:
    source: Path
    start: float
    duration: float
    scaler: str = limits.DEFAULT_SCALER


@dataclass(frozen=True, slots=True)
class Sampling:
    windows: int = DEFAULT_WINDOWS
    window_seconds: float = DEFAULT_WINDOW_SECONDS

    def spread(self, footage: Footage) -> list[tuple[float, float]]:
        return sample_windows(
            start=footage.start,
            duration=footage.duration,
            windows=self.windows,
            window_seconds=self.window_seconds,
        )


@dataclass(frozen=True, slots=True)
class Bar:
    max_per_frame: float | None = None
    stale_tolerance: float | None = None
    tie: float = 0.0


SAMPLED: Final = Sampling()
REUSE_BAR: Final = Bar(stale_tolerance=STALE_TOLERANCE, tie=SCORE_TIE)


@dataclass(frozen=True, slots=True)
class Score:
    error: float
    per_frame: float
    working_set: float = 0.0
    stale: int = 0
    stale_share: float = 0.0
    on_time: float = 0.0
    median_fields: float = 0.0
    blurred: float = 0.0
    working_set_p90: float = 0.0


@dataclass(frozen=True, slots=True)
class Choice:
    value: float
    fits: bool
    scores: dict[float, Score]
    label: str = "denoise"
    digits: int = 1
    stale_waived: bool = False

    def table(self) -> str:
        return "\n".join(
            f"    {self.label} {value:7.{self.digits}f}  error {score.error:.5f}  "
            f"blurred {score.blurred:.5f}  "
            f"working set {score.working_set:.5f}  p90 {score.working_set_p90:.5f}  "
            f"{score.per_frame:6.0f} B/frame  "
            f"{score.stale:6d} stale ({score.stale_share * 100:.2f}%)  "
            f"{score.on_time * 100:3.0f}% on time  median {score.median_fields:4.1f} fields"
            for value, score in self.scores.items()
        )


def sample_windows(
    *, start: float, duration: float, windows: int, window_seconds: float
) -> list[tuple[float, float]]:
    if windows < 1:
        msg = "at least one sample window is required"
        raise ValueError(msg)
    if duration <= 0.0:
        msg = "a clip duration must be positive"
        raise ValueError(msg)

    span = min(window_seconds, duration)
    if windows == 1 or duration <= span:
        return [(start, span)]

    step = (duration - span) / (windows - 1)
    return [(start + index * step, span) for index in range(windows)]


def decode_windows(
    footage: Footage,
    *,
    geometry: bake.Geometry,
    fps: float,
    denoise: float,
    windows: list[tuple[float, float]],
) -> list[list[npt.NDArray[np.uint8]]]:
    decoded = [
        list(
            frames.decode(
                footage.source,
                width=geometry.width,
                height=geometry.height,
                fps=fps,
                start=window_start,
                duration=window_duration,
                scaler=footage.scaler,
                denoise=denoise,
            )
        )
        for window_start, window_duration in windows
    ]
    return [window for window in decoded if window]


@dataclass(frozen=True, slots=True)
class EncodeSettings:
    geometry: bake.Geometry
    budget: int
    cap: int
    reuse: float = bake.DEFAULT_REUSE
    upload_ceiling: int | None = None
    dither: float = bake.DEFAULT_DITHER


def score_windows(
    decoded: list[list[npt.NDArray[np.uint8]]],
    *,
    settings: EncodeSettings,
    reference: list[list[npt.NDArray[np.uint8]]] | None = None,
) -> Score:
    costs = window_costs(decoded, settings=settings, reference=reference)
    return summarise(costs, cells=sum(len(window) for window in decoded) * settings.geometry.cells)


@dataclass(frozen=True, slots=True)
class WindowCost:
    error: float
    working_set: float
    size: float
    stale: int
    blurred: float
    chunk_counts: tuple[int, ...]
    per_frame_working_set: tuple[float, ...]


def window_costs(
    decoded: list[list[npt.NDArray[np.uint8]]],
    *,
    settings: EncodeSettings,
    reference: list[list[npt.NDArray[np.uint8]]] | None = None,
) -> list[WindowCost]:
    if not decoded:
        msg = "no frames decoded while scoring"
        raise ValueError(msg)
    if reference is not None and len(reference) != len(decoded):
        msg = f"{len(reference)} reference windows for {len(decoded)} decoded ones"
        raise ValueError(msg)
    references = reference if reference is not None else [None] * len(decoded)
    return [
        _window_cost(window, wanted, settings=settings)
        for window, wanted in zip(decoded, references, strict=True)
    ]


def summarise(costs: list[WindowCost], *, cells: int) -> Score:
    stale = sum(cost.stale for cost in costs)
    return Score(
        error=float(np.mean([cost.error for cost in costs])),
        per_frame=float(np.mean([cost.size for cost in costs])),
        working_set=float(np.mean([cost.working_set for cost in costs])),
        stale=stale,
        stale_share=stale / cells if cells else 0.0,
        blurred=float(np.mean([cost.blurred for cost in costs])),
        working_set_p90=float(
            np.percentile([value for cost in costs for value in cost.per_frame_working_set], P90)
        ),
    )


def _window_cost(
    window: list[npt.NDArray[np.uint8]],
    wanted: list[npt.NDArray[np.uint8]] | None,
    *,
    settings: EncodeSettings,
) -> WindowCost:
    encoded = bake.encode_frames(
        window,
        geometry=settings.geometry,
        budget=settings.budget,
        cap=settings.cap,
        reuse_threshold=settings.reuse,
        upload_ceiling=settings.upload_ceiling,
        dither=settings.dither,
    )
    sizes = [sum(len(chunk) for chunk in chunks) for chunks in encoded.frames]
    blurred = 0.0 if wanted is None else replayed_error(encoded, wanted, geometry=settings.geometry)
    return WindowCost(
        error=encoded.error,
        working_set=encoded.working_set,
        size=float(np.mean(sizes)),
        stale=encoded.unplaced,
        blurred=blurred,
        chunk_counts=tuple(len(chunks) for chunks in encoded.frames),
        per_frame_working_set=tuple(encoded.per_frame_working_set),
    )


def replayed_error(
    encoded: bake.Encoded, wanted: list[npt.NDArray[np.uint8]], *, geometry: bake.Geometry
) -> float:
    if not wanted:
        msg = "no reference frames to score the replay against"
        raise ValueError(msg)
    blob, _ = stream.pack_banks(stream.defer_closes(encoded.frames), bank_size=limits.BANK_BYTES)
    played = capture.replay_fields(blob)
    if len(played.completes) < len(wanted):
        msg = f"the replay completed {len(played.completes)} of {len(wanted)} frames"
        raise ValueError(msg)
    shown = capture.picture_frames(
        played,
        top=geometry.top_row * pattern.TILE_PX,
        height=geometry.height,
        width=geometry.width,
        left=geometry.left_column * pattern.TILE_PX,
    )
    return capture.blurred_error(shown[: len(wanted)], np.stack(wanted))


def decide(
    scores: dict[float, Score],
    *,
    key: Callable[[Score], float],
    bar: Bar,
    label: str,
    digits: int,
) -> Choice:
    if bar.tie < 0.0:
        msg = f"a tie tolerance must not be negative, got {bar.tie}"
        raise ValueError(msg)
    affordable = [
        value
        for value, score in scores.items()
        if bar.max_per_frame is None or score.per_frame <= bar.max_per_frame
    ]
    clean = [
        value
        for value in affordable
        if bar.stale_tolerance is None or scores[value].stale_share <= bar.stale_tolerance
    ]
    pool = clean or affordable
    if not pool:
        cheapest = min(scores, key=lambda value: scores[value].per_frame)
        return Choice(value=cheapest, fits=False, scores=scores, label=label, digits=digits)
    best = _best_in(pool, scores, key=key, tie=bar.tie)
    return Choice(
        value=best, fits=True, scores=scores, label=label, digits=digits, stale_waived=not clean
    )


def _best_in(
    pool: list[float], scores: dict[float, Score], *, key: Callable[[Score], float], tie: float
) -> float:
    floor = min(key(scores[value]) for value in pool)
    tied = [value for value in pool if key(scores[value]) <= floor * (1.0 + tie)]
    return min(tied, key=lambda value: (scores[value].per_frame, key(scores[value])))


def pick_denoise(
    footage: Footage,
    settings: EncodeSettings,
    *,
    fps: float,
    candidates: tuple[float, ...] = DEFAULT_CANDIDATES,
    sampling: Sampling = SAMPLED,
    max_per_frame: float | None = None,
) -> Choice:
    _require(candidates, "denoise")
    sampled = sampling.spread(footage)
    reference = decode_windows(
        footage, geometry=settings.geometry, fps=fps, denoise=0.0, windows=sampled
    )
    cells = sum(len(window) for window in reference) * settings.geometry.cells
    scores = {
        value: summarise(
            window_costs(
                _decoded_at(footage, value, settings=settings, fps=fps, windows=sampled),
                settings=settings,
                reference=reference,
            ),
            cells=cells,
        )
        for value in candidates
    }
    bar = Bar(max_per_frame=max_per_frame, tie=SCORE_TIE)
    return decide(scores, key=lambda score: score.blurred, bar=bar, label="denoise", digits=1)


def pick_reuse(
    footage: Footage,
    settings: EncodeSettings,
    *,
    fps: float,
    denoise: float,
    candidates: tuple[float, ...] = DEFAULT_REUSE_CANDIDATES,
    sampling: Sampling = SAMPLED,
    bar: Bar = REUSE_BAR,
) -> Choice:
    _require(candidates, "reuse")
    decoded = decode_windows(
        footage,
        geometry=settings.geometry,
        fps=fps,
        denoise=denoise,
        windows=sampling.spread(footage),
    )
    scores = {
        value: score_windows(decoded, settings=replace(settings, reuse=value))
        for value in candidates
    }
    return decide(scores, key=lambda score: score.working_set_p90, bar=bar, label="reuse", digits=4)


def _require(candidates: tuple[float, ...], dial: str) -> None:
    if not candidates:
        msg = f"at least one {dial} candidate is required"
        raise ValueError(msg)


def _decoded_at(
    footage: Footage,
    denoise: float,
    *,
    settings: EncodeSettings,
    fps: float,
    windows: list[tuple[float, float]],
) -> list[list[npt.NDArray[np.uint8]]]:
    decoded = decode_windows(
        footage, geometry=settings.geometry, fps=fps, denoise=denoise, windows=windows
    )
    if not decoded:
        msg = f"no frames decoded while scoring denoise {denoise}"
        raise ValueError(msg)
    return decoded
