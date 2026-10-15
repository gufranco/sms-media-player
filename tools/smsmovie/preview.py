from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Final

import numpy as np
import numpy.typing as npt
from fmvcore import ffmpeg

from smsmovie import bake, capture, pattern

PREVIEW_FRAMES: Final = 4


def write(
    path: Path,
    *,
    blob: bytes,
    sources: list[npt.NDArray[np.uint8]],
    geometry: bake.Geometry,
) -> None:
    played = capture.replay_fields(blob)
    pictures = capture.picture_frames(
        played,
        top=geometry.top_row * pattern.TILE_PX,
        height=geometry.height,
        width=geometry.width,
        left=geometry.left_column * pattern.TILE_PX,
    )
    shown = min(len(pictures), len(sources))
    if shown == 0:
        msg = "a preview needs at least one frame shown and one source frame"
        raise ValueError(msg)
    picks = sorted(set(np.linspace(0, shown - 1, min(PREVIEW_FRAMES, shown)).astype(int)))
    rows = [np.concatenate([pictures[pick], sources[pick]], axis=1) for pick in picks]
    save_png(path, np.concatenate(rows, axis=0))


def save_png(path: Path, image: npt.NDArray[np.uint8]) -> None:
    height, width = image.shape[:2]
    subprocess.run(
        [
            ffmpeg.require_tool("ffmpeg"),
            "-y",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{width}x{height}",
            "-i",
            "-",
            str(path),
        ],
        input=np.ascontiguousarray(image).tobytes(),
        check=True,
    )
