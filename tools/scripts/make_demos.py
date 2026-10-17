from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import numpy.typing as npt

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fmvcore import ffmpeg

from smsggmedia import capture, cartridge, target

Frames = npt.NDArray[np.uint8]


@dataclass(frozen=True, slots=True)
class Window:
    top: int
    left: int
    height: int
    width: int


WINDOWS: Final = {
    target.MASTER_SYSTEM.name: Window(top=0, left=0, height=192, width=256),
    target.GAME_GEAR.name: Window(top=24, left=48, height=144, width=160),
}
NAMES: Final = {target.MASTER_SYSTEM.name: "demo.gif", target.GAME_GEAR.name: "demo-gg.gif"}
PALETTE: Final = "[0:v][1:v]paletteuse=dither=none"
GIF_COLOURS: Final = 256
PALETTE_SIDE: Final = 16
RGB: Final = 3


def bake(
    source: Path,
    *,
    start: float,
    duration: float,
    system: str,
    folder: Path,
    flags: Sequence[str] = (),
) -> Path:
    window = ["--start", str(start), "--duration", str(duration), "--target", system]
    places = ["--assets", str(folder / "assets"), "--generated", str(folder / "generated")]
    report = ["--report", str(folder / "report.json"), "--bake-only"]
    status = cartridge.main([str(source), *window, *places, *report, *flags])
    if status != 0:
        msg = f"the {system} bake of {source} failed with status {status}"
        raise RuntimeError(msg)
    return folder / "assets" / "movie.bin"


def shown_frames(blob: bytes, window: Window) -> Frames:
    played = capture.replay_fields(blob)
    return capture.picture_frames(
        played, top=window.top, height=window.height, width=window.width, left=window.left
    )


def frame_rate(folder: Path) -> float:
    return float(json.loads((folder / "report.json").read_text())["fps"])


def same_length(frames: dict[str, Frames]) -> dict[str, Frames]:
    count = min(len(shown) for shown in frames.values())
    return {system: shown[:count] for system, shown in frames.items()}


def one_rate(rates: set[float]) -> float:
    if len(rates) != 1:
        msg = f"the consoles settled on different frame rates, {sorted(rates)}; pass the same --fps"
        raise ValueError(msg)
    return next(iter(rates))


def exact_palette(frames: Frames) -> Frames:
    colours = np.unique(frames.reshape(-1, RGB), axis=0)
    if len(colours) > GIF_COLOURS:
        msg = f"the demo shows {len(colours)} colours and a GIF holds {GIF_COLOURS}"
        raise ValueError(msg)
    padding = np.repeat(colours[:1], GIF_COLOURS - len(colours), axis=0)
    return np.concatenate([colours, padding]).reshape(PALETTE_SIDE, PALETTE_SIDE, RGB)


def write_gif(path: Path, frames: Frames, *, fps: float) -> None:
    height, width = frames.shape[1:3]
    with tempfile.NamedTemporaryFile(suffix=".rgb") as palette:
        palette.write(exact_palette(frames).tobytes())
        palette.flush()
        raw = ["-f", "rawvideo", "-pix_fmt", "rgb24"]
        moving = [*raw, "-s", f"{width}x{height}", "-r", f"{fps:g}", "-i", "-"]
        still = [*raw, "-s", f"{PALETTE_SIDE}x{PALETTE_SIDE}", "-i", palette.name]
        command = [ffmpeg.require_tool("ffmpeg"), "-v", "error", "-y", *moving, *still]
        command = [*command, "-lavfi", PALETTE, "-loop", "0", str(path)]
        subprocess.run(command, input=np.ascontiguousarray(frames).tobytes(), check=True)


def bake_all(
    args: argparse.Namespace, flags: Sequence[str], scratch: Path
) -> tuple[dict[str, Frames], float]:
    frames: dict[str, Frames] = {}
    rates: set[float] = set()
    for system, window in WINDOWS.items():
        folder = scratch / system
        window_args = {"start": args.start, "duration": args.duration, "system": system}
        stream = bake(args.source, folder=folder, flags=flags, **window_args)
        frames[system] = shown_frames(stream.read_bytes(), window)
        rates.add(frame_rate(folder))
    return same_length(frames), one_rate(rates)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="make_demos",
        epilog="Any other flag is passed to both bakes unchanged.",
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--out", type=Path, default=Path("readme"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args, flags = build_parser().parse_known_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as scratch:
        frames, fps = bake_all(args, flags, Path(scratch))
    for system, shown in frames.items():
        path = args.out / NAMES[system]
        write_gif(path, shown, fps=fps)
        print(f"{path}: {len(shown)} frames at {fps:g} fps")
    return 0


if __name__ == "__main__":
    sys.exit(main())
