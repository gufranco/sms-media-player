from __future__ import annotations

import argparse
from pathlib import Path
from typing import Final

from fmvcore import arguments, ffmpeg
from fmvcore.arguments import AUTO

from smsggmedia import bake, limits, target

SEEK_EVERY_SECONDS: Final = 10.0


def add_picture_flags(parser: argparse.ArgumentParser) -> None:
    slots = bake.PATTERN_SLOTS
    parser.add_argument(
        "--cap",
        type=arguments.count(low=1, high=slots, name="--cap"),
        default=limits.DEFAULT_CAP,
        help=f"patterns one frame may upload. Default: {limits.DEFAULT_CAP}",
    )
    parser.add_argument(
        "--upload-ceiling",
        type=arguments.count(low=1, high=slots, name="--upload-ceiling"),
        default=None,
        help="the most new patterns a frame keeps after merging; defaults to no ceiling",
    )
    parser.add_argument(
        "--dither",
        type=arguments.number(low=0.0, high=limits.MAX_DITHER, name="--dither"),
        default=limits.DEFAULT_DITHER,
        help="ordered dither strength across palette entries, to break up banding; 0 turns it off",
    )
    parser.add_argument(
        "--scaler",
        choices=ffmpeg.SCALERS,
        default=limits.DEFAULT_SCALER,
        help=f"the ffmpeg filter that shrinks the source. Default: {limits.DEFAULT_SCALER}",
    )
    parser.add_argument(
        "--max-banks",
        type=arguments.count(low=1, high=limits.DEFAULT_MAX_BANKS, name="--max-banks"),
        default=limits.DEFAULT_MAX_BANKS,
        help=f"16 KB banks the film may fill. Default: {limits.DEFAULT_MAX_BANKS}",
    )
    add_size_flags(parser)


def add_size_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--target",
        type=_named_target,
        default=target.DEFAULT,
        help=f"the console to build for: {', '.join(sorted(target.TARGETS))}. "
        f"Default: {target.DEFAULT.name}",
    )
    parser.add_argument(
        "--columns",
        type=arguments.count(low=1, high=limits.DEFAULT_COLUMNS, name="--columns"),
        default=None,
        help="picture width in 8-pixel cells. Default: the target's whole screen",
    )
    parser.add_argument(
        "--rows",
        type=arguments.count(low=1, high=bake.VISIBLE_ROWS, name="--rows"),
        default=None,
        help="picture height in 8-pixel cells. Default: the target's whole screen",
    )


def picture_size(args: argparse.Namespace) -> tuple[int, int]:
    system: target.Target = args.target
    columns = args.columns if args.columns is not None else system.columns
    rows = args.rows if args.rows is not None else system.rows
    return columns, rows


def _named_target(name: str) -> target.Target:
    try:
        return target.named(name)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def add_window_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--start",
        type=arguments.number(low=0.0, high=limits.MAX_SOURCE_SECONDS, name="--start"),
        default=0.0,
        help="seconds to skip at the front",
    )
    parser.add_argument(
        "--duration",
        type=arguments.number(
            low=limits.FIELD_SECONDS, high=limits.MAX_SOURCE_SECONDS, name="--duration"
        ),
        default=None,
        help="seconds to take; defaults to the whole film",
    )


def add_dial_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--fps",
        type=arguments.number_or_auto(low=0.1, high=limits.NTSC_FIELD_HZ, name="--fps"),
        default=AUTO,
        help="a frame rate, or auto to measure it on the film. Default: auto",
    )
    parser.add_argument(
        "--reuse",
        type=arguments.number_or_auto(low=0.0, high=1.0, name="--reuse"),
        default=AUTO,
        help="how far a tile may differ from a pattern in video memory and still reuse it, "
        "or auto. Default: auto",
    )
    parser.add_argument(
        "--denoise",
        type=arguments.number_or_auto(low=0.0, high=limits.MAX_DENOISE, name="--denoise"),
        default=AUTO,
        help="a strength, or auto to measure it on the film. Default: auto",
    )


def add_stream_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--budget",
        type=arguments.count(
            low=limits.CLOSE_RESERVE * 2, high=limits.MEASURED_FIELD_BUDGET, name="--budget"
        ),
        default=limits.DEFAULT_BUDGET,
        help=f"bytes the player may write to video memory in one field. "
        f"Default: {limits.DEFAULT_BUDGET}",
    )
    parser.add_argument(
        "--no-pace",
        action="store_true",
        help="send each frame as soon as it is ready instead of padding it to its slot",
    )
    parser.add_argument(
        "--silent",
        action="store_true",
        help="leave sound out and give its share of each field to the picture",
    )
    parser.add_argument(
        "--seek-every",
        type=arguments.number(
            low=limits.FIELD_SECONDS, high=limits.MAX_SOURCE_SECONDS, name="--seek-every"
        ),
        default=SEEK_EVERY_SECONDS,
        help=f"seconds between the points Left and Right jump to. Default: {SEEK_EVERY_SECONDS:g}",
    )


def add_output_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--assets",
        type=Path,
        default=Path("assets"),
        help="where the baked film goes for the ROM build. Default: assets",
    )
    parser.add_argument(
        "--generated",
        type=Path,
        default=Path("build/generated"),
        help="where the header describing the film goes. Default: build/generated",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("build/report.json"),
        help="where the bake report goes. Default: build/report.json",
    )
    parser.add_argument(
        "--bundle",
        type=Path,
        default=None,
        help="a folder to write a drop-in copy of the player library and this film into",
    )
    parser.add_argument(
        "--preview",
        type=Path,
        default=None,
        help="a .mp4 for every field the console draws, or a .png for four frames",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="smsggmedia",
        description="Bake a movie and build the cartridge that plays it.",
    )
    parser.add_argument("source", type=Path, help="the video file to put on the cartridge")
    parser.add_argument(
        "--subtitles",
        type=Path,
        default=None,
        help="a SubRip .srt file; defaults to one sitting beside the source",
    )
    add_dial_flags(parser)
    add_window_flags(parser)
    add_stream_flags(parser)
    add_picture_flags(parser)
    add_output_flags(parser)
    parser.add_argument(
        "--bake-only", action="store_true", help="stop after the bake, before the ROM build"
    )
    parser.set_defaults(bars=None, cues=[])
    return parser
