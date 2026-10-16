from __future__ import annotations

import argparse
from pathlib import Path
from typing import Final

from fmvcore import arguments, ffmpeg
from fmvcore.arguments import AUTO

from smsmedia import bake, limits

SEEK_EVERY_SECONDS: Final = 10.0


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
    parser.add_argument(
        "--silent",
        action="store_true",
        help="leave sound out and give its share of each field to the picture",
    )
    add_picture_flags(parser)
    parser.add_argument("--assets", type=Path, default=Path("assets"))
    parser.add_argument("--generated", type=Path, default=Path("build/generated"))
    parser.add_argument("--report", type=Path, default=Path("build/report.json"))
    parser.add_argument(
        "--bundle",
        type=Path,
        default=None,
        help="a folder to write a drop-in copy of the player library and this film into",
    )
    parser.add_argument(
        "--seek-every",
        type=float,
        default=SEEK_EVERY_SECONDS,
        help="seconds between the points Left and Right jump to; 0 leaves only the start",
    )
    parser.add_argument(
        "--subtitles",
        type=Path,
        default=None,
        help="a SubRip .srt burned into the picture; defaults to one beside the source",
    )
    parser.add_argument(
        "--preview",
        type=Path,
        default=None,
        help="a .mp4 for every field the console draws, or a .png for four frames",
    )
    parser.set_defaults(bars=None, cues=[])
    return parser
