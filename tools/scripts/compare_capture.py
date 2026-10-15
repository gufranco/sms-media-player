from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Final

import numpy as np
from fmvcore import capture as core
from fmvcore import colour
from fmvcore.capture import Played

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from smsmovie import capture, console, frames, limits, preview

CAPTURE_WIDTH: Final = 256
CAPTURE_HEIGHT: Final = 240
PICTURE_TOP: Final = 24
PICTURE_HEIGHT: Final = 192
SAMPLE_EVERY: Final = 8
LAG_WINDOW: Final = 600


def read_capture(path: Path) -> np.ndarray:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True,
        check=True,
    ).stdout
    frame_bytes = CAPTURE_HEIGHT * CAPTURE_WIDTH * 3
    if not raw or len(raw) % frame_bytes:
        msg = (
            f"{path} is not a {CAPTURE_WIDTH}x{CAPTURE_HEIGHT} mednafen recording "
            "of the Master System picture"
        )
        raise ValueError(msg)
    whole = np.frombuffer(raw, dtype=np.uint8).reshape(-1, CAPTURE_HEIGHT, CAPTURE_WIDTH, 3)
    return whole[:, PICTURE_TOP : PICTURE_TOP + PICTURE_HEIGHT]


def measure(played: Played, source: np.ndarray) -> dict[str, float]:
    usable = min(played.fields.shape[0], source.shape[0])
    sampled = range(played.completes[0], usable, SAMPLE_EVERY)
    lags = core.measured_lags(played.fields, source, completes=played.completes, window=LAG_WINDOW)
    pairs = list(zip(played.completes, lags, strict=False))
    matched = [
        colour.oklab_error(played.fields[field], source[field - lag]) for field, lag in pairs
    ]
    blurred = [
        colour.blurred_error(played.fields[[field]], source[[field - lag]]) for field, lag in pairs
    ]
    rate = console.NTSC_FIELD_HZ
    return {
        "fields": int(played.fields.shape[0]),
        "frames": len(played.completes),
        "on_screen_error": float(
            np.mean([colour.oklab_error(played.fields[i], source[i]) for i in sampled])
        ),
        "frame_error": float(np.mean(matched)),
        "blurred_frame_error": float(np.mean(blurred)),
        "lattice_floor": float(np.mean([capture.lattice_floor(source[i]) for i in sampled])),
        "mixed_share": core.mixed_share(played.fields, completes=played.completes),
        "lag_first_s": lags[0] / rate,
        "lag_median_s": float(np.median(lags)) / rate,
        "lag_last_s": lags[-1] / rate,
    }


def worst_mixed(played: Played) -> tuple[int, int, int]:
    best = (0.0, played.completes[0], played.completes[0], played.completes[0])
    for previous, current in zip(played.completes, played.completes[1:], strict=False):
        for index in range(previous + 1, current):
            share = core.mixed_share(played.fields[[previous, index, current]], completes=[0, 2])
            if share > best[0]:
                best = (share, previous, index, current)
    return best[1], best[2], best[3]


def worst_frame(played: Played, source: np.ndarray) -> tuple[int, int, int]:
    usable = [field for field in played.completes if field < source.shape[0]]
    errors = [colour.oklab_error(played.fields[field], source[field]) for field in usable]
    position = played.completes.index(usable[int(np.argmax(errors))])
    previous = played.completes[max(position - 1, 0)]
    following = played.completes[min(position + 1, len(played.completes) - 1)]
    return previous, played.completes[position], following


def write_sheet(path: Path, played: Played, source: np.ndarray) -> None:
    previous, middle, current = worst_mixed(played)
    if middle == previous:
        previous, middle, current = worst_frame(played, source)
    row = np.concatenate(
        [
            played.fields[previous],
            played.fields[middle],
            played.fields[current],
            source[min(middle, source.shape[0] - 1)],
        ],
        axis=1,
    )
    preview.save_png(path, row)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="compare_capture")
    parser.add_argument("--stream", type=Path, default=Path("assets/movie.bin"))
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--start", type=float, required=True)
    parser.add_argument("--lead", type=int, default=0)
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--sheet", type=Path, default=None)
    return parser


def decode_source(args: argparse.Namespace, played: Played) -> np.ndarray:
    seconds = played.fields.shape[0] / console.NTSC_FIELD_HZ
    source = np.stack(
        list(
            frames.decode(
                args.source,
                width=CAPTURE_WIDTH,
                height=PICTURE_HEIGHT,
                fps=console.NTSC_FIELD_HZ,
                start=args.start,
                duration=seconds,
                scaler=limits.DEFAULT_SCALER,
            )
        )
    )
    if not args.lead:
        return source
    return np.concatenate([np.repeat(source[:1], args.lead, axis=0), source])


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    played = capture.replay_fields(args.stream.read_bytes())
    found = core.align(read_capture(args.capture), played.fields)
    report: dict[str, float] = {
        "emulator_offset": found.offset,
        "emulator_mismatches": found.mismatches,
        "emulator_sampled": found.sampled,
    }
    if found.mismatches:
        print(json.dumps(report, indent=1))
        print(
            "the capture does not repeat this stream; record the ROM built from it", file=sys.stderr
        )
        return 1

    source = decode_source(args, played)
    report |= measure(played, source)
    if args.sheet is not None:
        write_sheet(args.sheet, played, source)
    text = json.dumps(report, indent=1)
    if args.json is not None:
        args.json.write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
