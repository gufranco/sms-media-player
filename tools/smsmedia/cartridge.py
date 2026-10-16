from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import numpy.typing as npt
from fmvcore import ffmpeg, source
from fmvcore.arguments import AUTO

from smsmedia import (
    bake,
    bundle,
    captions,
    dials,
    flags,
    frames,
    limits,
    output,
    preview,
    psgsound,
    rate,
    schedule,
    stepdown,
    stream,
)

P90: Final = 0.9
MOST_MERGED_SHOWN: Final = 3
BAR_ANALYSIS_SECONDS: Final = 8.0
ROM: Final = Path("build") / "smsmedia.sms"


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
    sound_writes: int = 0
    bars: source.Bars | None = None
    keys: tuple[int, ...] = (0,)


def most_merged(per_frame: list[int]) -> list[int]:
    ranked = sorted(range(len(per_frame)), key=lambda index: -per_frame[index])
    return [index for index in ranked[:MOST_MERGED_SHOWN] if per_frame[index] > 0]


def build_report(
    *, baked: Baked, blob: bytes, banks: int, settled: dials.Dials
) -> dict[str, float | list[int] | None]:
    return {
        **_timing_report(baked, blob=blob, banks=banks),
        **_picture_report(baked),
        "denoise": settled.denoise,
        "reuse": settled.reuse,
        "dither": baked.dither,
        "fps": settled.fps,
        "sound_writes": baked.sound_writes,
        "bars": list(baked.bars) if baked.bars is not None else None,
    }


def _timing_report(baked: Baked, *, blob: bytes, banks: int) -> dict[str, float | list[int] | None]:
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


def _picture_report(baked: Baked) -> dict[str, float | list[int] | None]:
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
    sound = not args.silent and ffmpeg.has_audio(args.source)
    decoded = captions.caption(
        _decode(args, geometry=geometry, settled=settled),
        args.cues,
        start=args.start,
        fps=settled.fps,
    )
    encoder = bake.Encoder(
        geometry=geometry,
        budget=args.budget - (limits.SOUND_RESERVE if sound else 0),
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
        keyframe_every=args.seek_every,
    )
    fields = stream.defer_closes(timed.frames)
    writes = _sound(args, fields) if sound else []
    return Baked(
        encoded=encoder.result(),
        fields=stream.add_sound(fields, writes),
        decoded=len(decoded),
        lags=timed.lags,
        lead=timed.lead,
        unshown_tail=timed.unshown_tail,
        sources=[decoded[pick] for pick in timed.picks],
        dither=args.dither,
        sound_writes=sum(len(field) for field in writes),
        bars=args.bars,
        keys=tuple(timed.keys) or (0,),
    )


def _sound(args: argparse.Namespace, fields: list[list[bytes]]) -> list[bytes]:
    count = sum(len(chunks) for chunks in fields)
    samples = psgsound.decode(args.source, start=args.start, duration=args.duration)
    return psgsound.synthesize(samples, rate=psgsound.DECODE_RATE, fields=count)


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
            bars=args.bars,
        )
    )


def show_dial_reports() -> None:
    for stale in tuple(dials.LOG.handlers):
        dials.LOG.removeHandler(stale)
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
    parser = flags.build_parser()
    args = parser.parse_args(argv)
    print(f"baking {args.source}", file=sys.stderr)
    status = bake_cartridge(parser, args)
    if status != 0:
        return status
    if args.bake_only:
        print(f"baked into {args.assets}", file=sys.stderr)
        return 0
    return _build_cartridge()


def _build_cartridge() -> int:
    print("building the cartridge", file=sys.stderr)
    completed = subprocess.run(["make", "--no-print-directory", "rom"], check=False)
    if completed.returncode != 0:
        return completed.returncode
    if ROM.exists():
        print(f"{ROM}  {ROM.stat().st_size} bytes")
    return 0


def bake_cartridge(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    show_dial_reports()
    info = ffmpeg.probe(args.source)
    geometry = geometry_for(args.columns, args.rows)
    _describe_source(args.source, info=info, geometry=geometry)
    _announce_silence(args)

    try:
        wanted = window_seconds(
            start=args.start, duration=args.duration, source_seconds=info.duration
        )
    except ValueError as error:
        parser.error(str(error))
    _analyse_source(parser, args, wanted=wanted)
    settled, baked, packed = bake_to_fit(args, geometry=geometry, wanted=wanted)
    blob, banks = packed.blob, packed.banks
    report = build_report(baked=baked, blob=blob, banks=banks, settled=settled)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")

    refused = _refusal(args, baked=baked, banks=banks, settled=settled)
    if refused is not None:
        output.clear(assets=args.assets, generated=args.generated)
        return refused
    _publish(args, baked=baked, packed=packed, settled=settled, geometry=geometry)
    _summarise(baked.encoded, blob=blob, banks=banks, report=report)
    return 0


Attempt = tuple[dials.Dials, Baked, stream.Packed]


def bake_to_fit(args: argparse.Namespace, *, geometry: bake.Geometry, wanted: float) -> Attempt:
    first = _attempt(args, geometry=geometry, wanted=wanted)
    if _fits_cartridge(args, first) or args.fps != AUTO:
        return first
    found = stepdown.search(
        stepdown.rungs(first[0].fps, sound=not args.silent),
        lambda rung: _attempt(_on_rung(args, rung), geometry=geometry, wanted=wanted),
        lambda attempt: _fits_cartridge(args, attempt),
    )
    if found is None:
        return first
    rung, attempt = found
    quiet = " without sound" if rung.silent and not args.silent else ""
    banks = "bank" if args.max_banks == 1 else "banks"
    print(f"stepped down to {rung.fps:g} fps{quiet} to fit {args.max_banks} {banks}")
    return attempt


def _attempt(args: argparse.Namespace, *, geometry: bake.Geometry, wanted: float) -> Attempt:
    settled = dials.settle_dials(args, geometry=geometry, wanted=wanted)
    baked = bake_film(args, geometry=geometry, settled=settled)
    _describe_bake(baked, fps=settled.fps)
    return settled, baked, stream.pack_frames(baked.fields, bank_size=limits.BANK_BYTES)


def _fits_cartridge(args: argparse.Namespace, attempt: Attempt) -> bool:
    return fits(banks=attempt[2].banks, max_banks=args.max_banks)


def _on_rung(args: argparse.Namespace, rung: stepdown.Rung) -> argparse.Namespace:
    return argparse.Namespace(**{**vars(args), "fps": str(rung.fps), "silent": rung.silent})


def _analyse_source(
    parser: argparse.ArgumentParser, args: argparse.Namespace, *, wanted: float
) -> None:
    args.bars = source.analyse(
        args.source, start=args.start, duration=min(wanted, BAR_ANALYSIS_SECONDS)
    ).crop
    if args.bars is not None:
        print("cropping bars baked into the source: {}x{} at {},{}".format(*args.bars))
    try:
        args.cues = captions.load(args.subtitles, args.source)
    except FileNotFoundError as error:
        parser.error(str(error))
    if args.cues:
        print(f"burning {len(args.cues)} subtitles into the picture")


def _describe_bake(baked: Baked, *, fps: float) -> None:
    print(f"decoded {baked.decoded} frames at {fps} fps")
    if baked.unshown_tail:
        print(f"the clock passed the last {baked.unshown_tail} decoded frames before they fit")


def _announce_silence(args: argparse.Namespace) -> None:
    if not args.silent and not ffmpeg.has_audio(args.source):
        print(
            f"{args.source} carries no audio track, so the cartridge will be silent. "
            "Nothing is wrong with the video; there is simply no soundtrack to encode.",
            file=sys.stderr,
        )


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
    packed: stream.Packed,
    settled: dials.Dials,
    geometry: bake.Geometry,
) -> None:
    output.publish(
        assets=args.assets,
        generated=args.generated,
        blob=packed.blob,
        banks=packed.banks,
        frame_count=len(baked.fields),
        field_count=sum(len(frame) for frame in baked.fields),
        hold_fields=rate.fields_for(settled.fps),
        keys=seek_points(baked, packed),
    )
    if args.bundle is not None:
        _write_bundle(args, baked=baked, packed=packed, geometry=geometry)
    if args.preview is not None:
        _write_preview(args.preview, blob=packed.blob, sources=baked.sources, geometry=geometry)
        print(f"preview written to {args.preview}")


def _write_bundle(
    args: argparse.Namespace, *, baked: Baked, packed: stream.Packed, geometry: bake.Geometry
) -> None:
    fields = sum(len(frame) for frame in baked.fields)
    figures = bundle.Figures(
        seconds=fields / limits.NTSC_FIELD_HZ,
        frames=len(baked.fields),
        fields=fields,
        banks=packed.banks,
        columns=geometry.columns,
        rows=geometry.rows,
        keys=len(baked.keys),
        sound=baked.sound_writes > 0,
    )
    guide = bundle.write(
        target=args.bundle, assets=args.assets, generated=args.generated, figures=figures
    )
    print(f"bundle written to {args.bundle}; start with {guide}")


def seek_points(baked: Baked, packed: stream.Packed) -> tuple[output.Key, ...]:
    fields_before = [sum(len(frame) for frame in baked.fields[:index]) for index in baked.keys]
    return tuple(
        output.Key(
            bank=packed.starts[index][0],
            offset=packed.starts[index][1],
            frame=index,
            field=fields,
        )
        for index, fields in zip(baked.keys, fields_before, strict=True)
    )


def _write_preview(
    path: Path, *, blob: bytes, sources: list[np.ndarray], geometry: bake.Geometry
) -> None:
    if preview.wants_video(path):
        preview.write_video(path, blob=blob, geometry=geometry)
        return
    preview.write(path, blob=blob, sources=sources, geometry=geometry)


def _summarise(
    encoded: bake.Encoded, *, blob: bytes, banks: int, report: dict[str, float | list[int] | None]
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
