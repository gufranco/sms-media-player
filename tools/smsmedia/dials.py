from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, replace
from typing import Final

from fmvcore.arguments import AUTO

from smsmedia import bake, limits, rate, stream, tune

LOG: Final = logging.getLogger(__name__)

RATE_SEARCH_DENOISE: Final = 2.0


@dataclass(frozen=True, slots=True)
class Dials:
    fps: float
    denoise: float
    reuse: float


def resolve_denoise(
    requested: str,
    footage: tune.Footage,
    settings: tune.EncodeSettings,
    *,
    fps: float,
    max_per_frame: float,
) -> float:
    if requested != AUTO:
        return float(requested)

    choice = tune.pick_denoise(footage, settings, fps=fps, max_per_frame=max_per_frame)
    LOG.info(f"denoise auto: chose {choice.value:.1f} of {len(choice.scores)} candidates")
    LOG.info(choice.table())
    if not choice.fits:
        LOG.info(f"    none fit {max_per_frame:.0f} B/frame; took the cheapest")
    return choice.value


def resolve_rate(
    requested: str,
    footage: tune.Footage,
    settings: tune.EncodeSettings,
    *,
    denoise: float,
) -> float:
    if requested != AUTO:
        return float(requested)

    choice = rate.pick_rate(footage, settings, denoise=denoise)
    LOG.info(f"fps auto: chose {choice.value:.0f} of {len(choice.scores)} candidates")
    LOG.info(choice.table())
    if not choice.fits:
        LOG.info(
            f"    none held {rate.ON_TIME_TARGET * 100:.0f}% of frames on time; took the slowest"
        )
    return choice.value


def resolve_reuse(
    requested: str,
    footage: tune.Footage,
    settings: tune.EncodeSettings,
    *,
    fps: float,
    denoise: float,
    max_per_frame: float,
) -> float:
    if requested != AUTO:
        return float(requested)

    bar = replace(tune.REUSE_BAR, max_per_frame=max_per_frame)
    choice = tune.pick_reuse(footage, settings, fps=fps, denoise=denoise, bar=bar)
    LOG.info(f"reuse auto: chose {choice.value:.4f} of {len(choice.scores)} candidates")
    LOG.info(choice.table())
    if not choice.fits:
        LOG.info(f"    none fit {max_per_frame:.0f} B/frame; took the cheapest")
    if choice.stale_waived:
        LOG.info("    every candidate left too many cells stale; chose among them anyway")
    return choice.value


def room_per_frame(*, max_banks: int, frame_count: float, fields: int) -> float:
    if frame_count <= 0.0:
        msg = "a film needs at least one frame"
        raise ValueError(msg)

    total = max_banks * limits.BANK_BYTES / frame_count
    return max(total - (fields - 1) * stream.TERMINATOR, 1.0)


def settle_dials(args: argparse.Namespace, *, geometry: bake.Geometry, wanted: float) -> Dials:
    footage = tune.Footage(args.source, start=args.start, duration=wanted, scaler=args.scaler)
    settings = tune.EncodeSettings(
        geometry,
        budget=int(args.budget),
        cap=args.cap,
        reuse=bake.DEFAULT_REUSE if args.reuse == AUTO else float(args.reuse),
        upload_ceiling=args.upload_ceiling,
        dither=args.dither,
    )
    rate_denoise = RATE_SEARCH_DENOISE if args.denoise == AUTO else float(args.denoise)
    fps = resolve_rate(args.fps, footage, settings, denoise=rate_denoise)
    room = room_per_frame(
        max_banks=args.max_banks, frame_count=wanted * fps, fields=rate.fields_for(fps)
    )
    denoise = resolve_denoise(args.denoise, footage, settings, fps=fps, max_per_frame=room)
    reuse = resolve_reuse(
        args.reuse, footage, settings, fps=fps, denoise=denoise, max_per_frame=room
    )
    return Dials(fps=fps, denoise=denoise, reuse=reuse)
