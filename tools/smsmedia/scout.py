from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final

import numpy as np
from fmvcore import arguments, ffmpeg

from smsmedia import bake, cartridge, limits, tune

SCOUT_DENOISE: Final = 4.0
DEFAULT_SCOUT_SECONDS: Final = 40.0
DEFAULT_TOP: Final = 10
MAX_TOP: Final = 1000
MAX_SCOUT_SECONDS: Final = 3600.0
DEFAULT_PROBE_SECONDS: Final = 1.5
DEFAULT_STRIDE_SECONDS: Final = 15.0


@dataclass(frozen=True, slots=True)
class Probe:
    start: float
    error: float
    per_frame: float


@dataclass(frozen=True, slots=True)
class Window:
    start: float
    duration: float
    error: float
    per_frame: float
    banks: float
    fits: bool

    def line(self) -> str:
        mark = " " if self.fits else " (over)"
        return (
            f"    {int(self.start) // 60:d}m{int(self.start) % 60:02d}s  "
            f"error {self.error:.5f}  {self.per_frame:6.0f} B/frame  "
            f"{self.banks:5.1f} banks{mark}"
        )


def window_starts(*, begin: float, end: float, span: float, stride: float) -> list[float]:
    if stride <= 0.0:
        msg = "a stride must be positive"
        raise ValueError(msg)
    if span <= 0.0:
        msg = "a span must be positive"
        raise ValueError(msg)

    out: list[float] = []
    start = begin
    while start + span <= end + 1e-9:
        out.append(start)
        start += stride
    return out


def covers(probes: list[Probe], *, start: float, duration: float) -> bool:
    return any(start <= p.start < start + duration for p in probes)


def summarise_window(probes: list[Probe], *, start: float, duration: float) -> Window:
    inside = [p for p in probes if start <= p.start < start + duration]
    if not inside:
        msg = f"no probe falls inside the window at {start}s"
        raise ValueError(msg)

    return Window(
        start=start,
        duration=duration,
        error=float(np.mean([p.error for p in inside])),
        per_frame=float(np.mean([p.per_frame for p in inside])),
        banks=0.0,
        fits=True,
    )


def banks_for(*, per_frame: float, duration: float, fps: float) -> float:
    if duration <= 0.0:
        msg = "a duration must be positive"
        raise ValueError(msg)
    return per_frame * duration * fps / limits.BANK_BYTES


def rank_windows(
    probes: list[Probe],
    *,
    duration: float,
    stride: float,
    fps: float,
    end: float,
    max_banks: int = limits.DEFAULT_MAX_BANKS,
    begin: float = 0.0,
) -> list[Window]:
    ranked: list[Window] = []
    for start in window_starts(begin=begin, end=end, span=duration, stride=stride):
        if not covers(probes, start=start, duration=duration):
            continue
        summary = summarise_window(probes, start=start, duration=duration)
        banks = banks_for(per_frame=summary.per_frame, duration=duration, fps=fps)
        ranked.append(
            Window(
                start=summary.start,
                duration=summary.duration,
                error=summary.error,
                per_frame=summary.per_frame,
                banks=banks,
                fits=banks <= max_banks,
            )
        )
    return sorted(ranked, key=lambda w: w.per_frame)


@dataclass(frozen=True, slots=True)
class Probing:
    probe_seconds: float = DEFAULT_PROBE_SECONDS
    stride_seconds: float = DEFAULT_STRIDE_SECONDS


PROBING: Final = Probing()


def profile(
    footage: tune.Footage,
    settings: tune.EncodeSettings,
    *,
    fps: float,
    denoise: float,
    probing: Probing = PROBING,
) -> list[Probe]:
    starts = window_starts(
        begin=footage.start,
        end=footage.start + footage.duration,
        span=probing.probe_seconds,
        stride=probing.stride_seconds,
    )
    window = tune.Sampling(windows=1, window_seconds=probing.probe_seconds)
    probes = [
        _probe(replace(footage, start=start), settings, fps=fps, denoise=denoise, window=window)
        for start in starts
    ]
    return [probe for probe in probes if probe is not None]


def _probe(
    footage: tune.Footage,
    settings: tune.EncodeSettings,
    *,
    fps: float,
    denoise: float,
    window: tune.Sampling,
) -> Probe | None:
    decoded = tune.decode_windows(
        footage,
        geometry=settings.geometry,
        fps=fps,
        denoise=denoise,
        windows=[(footage.start, window.window_seconds)],
    )
    if not decoded:
        return None
    encoded = bake.encode_frames(
        decoded[0],
        geometry=settings.geometry,
        budget=settings.budget,
        cap=settings.cap,
        reuse_threshold=settings.reuse,
        upload_ceiling=settings.upload_ceiling,
        dither=settings.dither,
    )
    sizes = [sum(len(chunk) for chunk in chunks) for chunks in encoded.frames]
    return Probe(start=footage.start, error=encoded.error, per_frame=float(np.mean(sizes)))


def add_scan_flags(parser: argparse.ArgumentParser) -> None:
    seconds = arguments.number(low=0.1, high=MAX_SCOUT_SECONDS, name="seconds")
    parser.add_argument("--duration", type=seconds, default=DEFAULT_SCOUT_SECONDS)
    parser.add_argument(
        "--begin",
        type=arguments.number(low=0.0, high=MAX_SCOUT_SECONDS, name="--begin"),
        default=0.0,
    )
    parser.add_argument("--end", type=seconds, default=None)
    parser.add_argument("--probe", type=seconds, default=DEFAULT_PROBE_SECONDS)
    parser.add_argument("--stride", type=seconds, default=DEFAULT_STRIDE_SECONDS)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="smsmedia.scout")
    parser.add_argument("source", type=Path)
    add_scan_flags(parser)
    parser.add_argument(
        "--fps",
        type=arguments.number(low=0.1, high=limits.NTSC_FIELD_HZ, name="--fps"),
        default=limits.DEFAULT_FPS,
    )
    parser.add_argument(
        "--reuse",
        type=arguments.number(low=0.0, high=1.0, name="--reuse"),
        default=bake.DEFAULT_REUSE,
    )
    parser.add_argument(
        "--denoise",
        type=arguments.number(low=0.0, high=limits.MAX_DENOISE, name="--denoise"),
        default=SCOUT_DENOISE,
    )
    parser.add_argument(
        "--top", type=arguments.count(low=1, high=MAX_TOP, name="--top"), default=DEFAULT_TOP
    )
    cartridge.add_picture_flags(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    info = ffmpeg.probe(args.source)
    end = args.end if args.end is not None else info.duration
    print(f"source {args.source.name}: {info.duration:.1f} s")
    print(
        f"probing {args.probe:.1f}s every {args.stride:.0f}s "
        f"for a {args.duration:.0f}s window at {args.fps:g} fps"
    )
    footage = tune.Footage(
        args.source, start=args.begin, duration=end - args.begin, scaler=args.scaler
    )
    settings = tune.EncodeSettings(
        cartridge.geometry_for(args.columns, args.rows),
        budget=limits.DEFAULT_BUDGET,
        cap=args.cap,
        reuse=args.reuse,
        upload_ceiling=args.upload_ceiling,
        dither=args.dither,
    )
    probing = Probing(probe_seconds=args.probe, stride_seconds=args.stride)
    probes = profile(footage, settings, fps=args.fps, denoise=args.denoise, probing=probing)
    if not probes:
        print("no probe fit inside the film; lower --probe or --stride")
        return 2
    print(f"took {len(probes)} probes, {len(probes) * args.probe:.0f}s of film decoded")
    return report(probes, args=args, end=end)


def report(probes: list[Probe], *, args: argparse.Namespace, end: float) -> int:
    ranked = rank_windows(
        probes,
        duration=args.duration,
        stride=args.stride,
        fps=args.fps,
        end=end,
        max_banks=args.max_banks,
        begin=args.begin,
    )
    if not ranked:
        print("no window of that length fits inside the film")
        return 2
    print(f"cheapest {min(args.top, len(ranked))} of {len(ranked)} windows:")
    for window in ranked[: args.top]:
        print(window.line())
    best = min(ranked, key=lambda w: w.error)
    print(
        f"lowest error is at {int(best.start) // 60}m{int(best.start) % 60:02d}s "
        f"({best.error:.5f}, {best.banks:.1f} banks)"
    )
    print("These are estimates from samples. Bake the window to get the real figure.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
