from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import numpy.typing as npt
from fmvcore import arguments, ffmpeg
from fmvcore.arguments import AUTO

from smsmedia import (
    bake,
    dials,
    frames,
    limits,
    output,
    preview,
    rate,
    schedule,
    stream,
)

P90: Final = 0.9
MOST_MERGED_SHOWN: Final = 3


def fits(*, banks: int, max_banks: int) -> bool:
    return banks <= max_banks


def shortfall(*, banks: int, max_banks: int, seconds: float) -> str:
    if seconds <= 0.0:
        msg = "a source duration must be positive"
        raise ValueError(msg)
    holds = seconds * max_banks / banks
    if holds < 1.0:
        return (
            f"the stream needs {banks} banks and the ceiling is {max_banks}, "
            f"so not even one second of this film fits. Re-run with a lower --fps; "
            "nothing here will shorten the film for you."
        )
    return (
        f"the stream needs {banks} banks and the ceiling is {max_banks}, "
        f"over by {banks - max_banks} banks. "
        f"At this rate {max_banks} banks hold {int(holds) // 60}m{int(holds) % 60:02d}s. "
        f"Re-run with --duration {int(holds)} or a lower --fps; "
        "nothing here will shorten the film for you."
    )


def geometry_for(columns: int, rows: int) -> bake.Geometry:
    top = (bake.VISIBLE_ROWS - rows) // 2
    left = (bake.NAME_TABLE_COLUMNS - columns) // 2
    return bake.Geometry(columns=columns, rows=rows, top_row=max(top, 0), left_column=max(left, 0))


def add_picture_flags(parser: argparse.ArgumentParser) -> None:
    slots = bake.PATTERN_SLOTS
    parser.add_argument(
        "--cap", type=arguments.count(low=1, high=slots, name="--cap"), default=limits.DEFAULT_CAP
    )
    parser.add_argument(
        "--upload-ceiling",
        type=arguments.count(low=1, high=slots, name="--upload-ceiling"),
        default=None,
    )
    parser.add_argument(
        "--dither",
        type=arguments.number(low=0.0, high=limits.MAX_DITHER, name="--dither"),
        default=limits.DEFAULT_DITHER,
    )
    parser.add_argument("--scaler", choices=ffmpeg.SCALERS, default=limits.DEFAULT_SCALER)
    parser.add_argument(
        "--max-banks",
        type=arguments.count(low=1, high=limits.DEFAULT_MAX_BANKS, name="--max-banks"),
        default=limits.DEFAULT_MAX_BANKS,
    )
    add_size_flags(parser)


def add_size_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--columns",
        type=arguments.count(low=1, high=limits.DEFAULT_COLUMNS, name="--columns"),
        default=limits.DEFAULT_COLUMNS,
    )
    parser.add_argument(
        "--rows",
        type=arguments.count(low=1, high=bake.VISIBLE_ROWS, name="--rows"),
        default=limits.DEFAULT_ROWS,
    )


def add_window_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--start",
        type=arguments.number(low=0.0, high=limits.MAX_SOURCE_SECONDS, name="--start"),
        default=0.0,
    )
    parser.add_argument(
        "--duration",
        type=arguments.number(
            low=limits.FIELD_SECONDS, high=limits.MAX_SOURCE_SECONDS, name="--duration"
        ),
        default=None,
    )


def add_dial_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--fps",
        type=arguments.number_or_auto(low=0.1, high=limits.NTSC_FIELD_HZ, name="--fps"),
        default=AUTO,
    )
    parser.add_argument(
        "--reuse", type=arguments.number_or_auto(low=0.0, high=1.0, name="--reuse"), default=AUTO
    )
    parser.add_argument(
        "--denoise",
        type=arguments.number_or_auto(low=0.0, high=limits.MAX_DENOISE, name="--denoise"),
        default=AUTO,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="smsmedia.cartridge")
    parser.add_argument("source", type=Path)
    add_dial_flags(parser)
    add_window_flags(parser)
    parser.add_argument(
        "--budget",
        type=arguments.count(
            low=limits.CLOSE_RESERVE * 2, high=limits.MEASURED_FIELD_BUDGET, name="--budget"
        ),
        default=limits.DEFAULT_BUDGET,
    )
    parser.add_argument("--no-pace", action="store_true")
    add_picture_flags(parser)
    parser.add_argument("--assets", type=Path, default=Path("assets"))
    parser.add_argument("--generated", type=Path, default=Path("build/generated"))
    parser.add_argument("--report", type=Path, default=Path("build/report.json"))
    parser.add_argument(
        "--preview",
        type=Path,
        default=None,
        help="a .mp4 for every field the console draws, or a .png for four frames",
    )
    return parser


@dataclass(frozen=True, slots=True)
class Baked:
    encoded: bake.Encoded
    fields: list[list[bytes]]
    decoded: int
    lags: list[float]
    lead: int
    unshown_tail: int
    dither: float
    sources: list[npt.NDArray[np.uint8]]


def most_merged(per_frame: list[int]) -> list[int]:
    ranked = sorted(range(len(per_frame)), key=lambda index: -per_frame[index])
    return [index for index in ranked[:MOST_MERGED_SHOWN] if per_frame[index] > 0]


def build_report(
    *, baked: Baked, blob: bytes, banks: int, settled: dials.Dials
) -> dict[str, float | list[int]]:
    return {
        **_timing_report(baked, blob=blob, banks=banks),
        **_picture_report(baked),
        "denoise": settled.denoise,
        "reuse": settled.reuse,
        "dither": baked.dither,
        "fps": settled.fps,
    }


def _timing_report(baked: Baked, *, blob: bytes, banks: int) -> dict[str, float | list[int]]:
    frames_shown = len(baked.encoded.frames)
    per_frame = [len(chunks) for chunks in baked.fields]
    chunks = sum(per_frame)
    played = chunks / limits.NTSC_FIELD_HZ
    return {
        "frames": frames_shown,
        "frames_decoded": baked.decoded,
        "chunks": chunks,
        "banks": banks,
        "bytes": len(blob),
        "fields_per_frame": round(chunks / frames_shown, 2),
        "effective_fps": round(frames_shown / played, 2) if played else 0.0,
        "lag_median_s": round(float(np.median(baked.lags)), 3),
        "lag_max_s": round(max(baked.lags), 3),
        "lead_fields": baked.lead,
        "frames_unshown_at_end": baked.unshown_tail,
        "worst_frame_fields": max(per_frame),
        "fields_p90": output.nearest_rank(per_frame, P90),
    }


def _picture_report(baked: Baked) -> dict[str, float | list[int]]:
    encoded = baked.encoded
    return {
        "patterns_uploaded": encoded.uploaded,
        "cells_left_stale": encoded.unplaced,
        "slot_collisions": encoded.collisions,
        "cells_merged": sum(encoded.per_frame_merged),
        "most_merged_frames": most_merged(encoded.per_frame_merged),
        "displayed_error": round(encoded.error, 5),
        "working_set_error": round(encoded.working_set, 5),
    }


def bake_film(args: argparse.Namespace, *, geometry: bake.Geometry, settled: dials.Dials) -> Baked:
    decoded = _decode(args, geometry=geometry, settled=settled)
    encoder = bake.Encoder(
        geometry=geometry,
        budget=args.budget,
        cap=args.cap,
        reuse_threshold=settled.reuse,
        upload_ceiling=args.upload_ceiling,
        dither=args.dither,
    )
    timed = schedule.by_clock(
        decoded,
        fps=settled.fps,
        slot=rate.fields_for(settled.fps),
        encoder=encoder,
        pace=not args.no_pace,
    )
    return Baked(
        encoded=encoder.result(),
        fields=stream.defer_closes(timed.frames),
        decoded=len(decoded),
        lags=timed.lags,
        lead=timed.lead,
        unshown_tail=timed.unshown_tail,
        sources=[decoded[pick] for pick in timed.picks],
        dither=args.dither,
    )


def _decode(
    args: argparse.Namespace, *, geometry: bake.Geometry, settled: dials.Dials
) -> list[npt.NDArray[np.uint8]]:
    return list(
        frames.decode(
            args.source,
            width=geometry.width,
            height=geometry.height,
            fps=settled.fps,
            start=args.start,
            duration=args.duration,
            scaler=args.scaler,
            denoise=settled.denoise,
        )
    )


def _show_dial_reports() -> None:
    if not dials.LOG.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        dials.LOG.addHandler(handler)
    dials.LOG.setLevel(logging.INFO)


def window_seconds(*, start: float, duration: float | None, source_seconds: float) -> float:
    if start >= source_seconds:
        msg = f"--start {start:g} s is past the end of a {source_seconds:.1f} s source"
        raise ValueError(msg)
    return duration if duration is not None else source_seconds - start


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _show_dial_reports()
    info = ffmpeg.probe(args.source)
    geometry = geometry_for(args.columns, args.rows)
    _describe_source(args.source, info=info, geometry=geometry)

    try:
        wanted = window_seconds(
            start=args.start, duration=args.duration, source_seconds=info.duration
        )
    except ValueError as error:
        parser.error(str(error))
    settled = dials.settle_dials(args, geometry=geometry, wanted=wanted)
    baked = bake_film(args, geometry=geometry, settled=settled)
    _describe_bake(baked, fps=settled.fps)
    blob, banks = stream.pack_banks(baked.fields, bank_size=limits.BANK_BYTES)
    report = build_report(baked=baked, blob=blob, banks=banks, settled=settled)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")

    refused = _refusal(args, baked=baked, banks=banks, settled=settled)
    if refused is not None:
        output.clear(assets=args.assets, generated=args.generated)
        return refused
    _publish(args, baked=baked, blob=blob, banks=banks, settled=settled, geometry=geometry)
    _summarise(baked.encoded, blob=blob, banks=banks, report=report)
    return 0


def _describe_bake(baked: Baked, *, fps: float) -> None:
    print(f"decoded {baked.decoded} frames at {fps} fps")
    if baked.unshown_tail:
        print(f"the clock passed the last {baked.unshown_tail} decoded frames before they fit")


def _describe_source(source: Path, *, info: ffmpeg.SourceInfo, geometry: bake.Geometry) -> None:
    print(
        f"source {source.name}: {info.width}x{info.height}, "
        f"{info.fps:.2f} fps, {info.duration:.1f} s"
    )
    print(
        f"picture {geometry.width}x{geometry.height} "
        f"at row {geometry.top_row}, column {geometry.left_column}"
    )


def _refusal(
    args: argparse.Namespace, *, baked: Baked, banks: int, settled: dials.Dials
) -> int | None:
    if not fits(banks=banks, max_banks=args.max_banks):
        print(shortfall(banks=banks, max_banks=args.max_banks, seconds=baked.decoded / settled.fps))
        return 2
    if baked.encoded.collisions:
        print(f"{baked.encoded.collisions} slot collisions; no film was written")
        return 1
    return None


def _publish(
    args: argparse.Namespace,
    *,
    baked: Baked,
    blob: bytes,
    banks: int,
    settled: dials.Dials,
    geometry: bake.Geometry,
) -> None:
    output.publish(
        assets=args.assets,
        generated=args.generated,
        blob=blob,
        banks=banks,
        frame_count=len(baked.fields),
        hold_fields=rate.fields_for(settled.fps),
    )
    if args.preview is not None:
        _write_preview(args.preview, blob=blob, sources=baked.sources, geometry=geometry)
        print(f"preview written to {args.preview}")


def _write_preview(
    path: Path, *, blob: bytes, sources: list[np.ndarray], geometry: bake.Geometry
) -> None:
    if preview.wants_video(path):
        preview.write_video(path, blob=blob, geometry=geometry)
        return
    preview.write(path, blob=blob, sources=sources, geometry=geometry)


def _summarise(
    encoded: bake.Encoded, *, blob: bytes, banks: int, report: dict[str, float | list[int]]
) -> None:
    print(
        f"stream {len(blob)} bytes across {banks} banks, "
        f"{report['fields_per_frame']} fields per frame, "
        f"{report['effective_fps']} fps on NTSC, "
        f"lag median {report['lag_median_s']} s, worst {report['lag_max_s']} s"
    )
    print(
        f"uploaded {encoded.uploaded} patterns, "
        f"{encoded.unplaced} cells left stale, "
        f"{encoded.collisions} slot collisions, "
        f"error {encoded.error:.5f}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
