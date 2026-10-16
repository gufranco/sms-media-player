from __future__ import annotations

import math
from collections.abc import Iterator
from pathlib import Path
from typing import Final

import numpy as np
import numpy.typing as npt
from fmvcore import ffmpeg
from fmvcore import source as source_mod

from smsmedia import limits, pattern, smscolor

CHANNELS: Final = smscolor.RGB_CHANNELS
MAX_FRAMES: Final = math.ceil(limits.MAX_SOURCE_SECONDS * limits.NTSC_FIELD_HZ)


def decode(
    source: Path,
    *,
    width: int,
    height: int,
    fps: float,
    start: float = 0.0,
    duration: float | None = None,
    scaler: str = limits.DEFAULT_SCALER,
    denoise: float = 0.0,
    bars: source_mod.Bars | None = None,
) -> Iterator[npt.NDArray[np.uint8]]:
    _check_request(width=width, height=height, fps=fps, scaler=scaler)
    path = Path(source)
    if not path.is_file():
        msg = f"no such source file: {path}"
        raise FileNotFoundError(msg)

    denoising = [f"hqdn3d={denoise}:{denoise}:{denoise * 2}:{denoise * 2}"] if denoise > 0.0 else []
    cropping = ["crop={}:{}:{}:{}".format(*bars)] if bars is not None else []
    stages = [
        *cropping,
        f"fps={fps}",
        *denoising,
        f"scale={width}:{height}:flags={scaler}:force_original_aspect_ratio=increase",
        f"crop={width}:{height}",
    ]
    command = ffmpeg.frame_command(path, start=start, duration=duration, stages=stages)
    yield from ffmpeg.stream_frames(
        command, path=path, shape=(height, width, CHANNELS), max_frames=MAX_FRAMES
    )


def _check_request(*, width: int, height: int, fps: float, scaler: str) -> None:
    if width % pattern.TILE_PX or height % pattern.TILE_PX:
        msg = f"the raster must be a multiple of {pattern.TILE_PX} pixels"
        raise ValueError(msg)
    if fps <= 0.0:
        msg = "a frame rate must be positive"
        raise ValueError(msg)
    ffmpeg.check_scaler(scaler)
