from __future__ import annotations

import json
import math
import shutil
import subprocess
import tempfile
from collections.abc import Generator, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Final

import numpy as np
import numpy.typing as npt

from smsmovie import limits, pattern, smscolor

CHANNELS: Final = smscolor.RGB_CHANNELS
MAX_FRAMES: Final = math.ceil(limits.MAX_SOURCE_SECONDS * limits.NTSC_FIELD_HZ)


@dataclass(frozen=True, slots=True)
class SourceInfo:
    width: int
    height: int
    fps: float
    duration: float


def require_tool(name: str) -> str:
    found = shutil.which(name)
    if found is None:
        msg = f"{name} is not on the path, and the decode path needs it"
        raise RuntimeError(msg)
    return found


def _ffprobe(path: Path) -> str:
    return subprocess.run(
        [
            require_tool("ffprobe"),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate:format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        check=True,
        text=True,
    ).stdout


def probe(source: Path) -> SourceInfo:
    path = Path(source)
    if not path.is_file():
        msg = f"no such source file: {path}"
        raise FileNotFoundError(msg)

    return source_info(json.loads(_ffprobe(path)), path=path)


def source_info(parsed: object, *, path: Path) -> SourceInfo:
    if not isinstance(parsed, dict) or not parsed.get("streams"):
        msg = f"{path} has no video stream ffprobe can read"
        raise ValueError(msg)
    try:
        video = parsed["streams"][0]
        info = SourceInfo(
            width=int(video["width"]),
            height=int(video["height"]),
            fps=_frame_rate(str(video["r_frame_rate"])),
            duration=float(parsed["format"]["duration"]),
        )
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        msg = f"{path} does not report a usable size, frame rate and duration: {error!r}"
        raise ValueError(msg) from error
    if info.width <= 0 or info.height <= 0 or not 0.0 < info.duration < math.inf:
        msg = f"{path} reports {info.width}x{info.height} for {info.duration} s, which is no film"
        raise ValueError(msg)
    return info


def _frame_rate(text: str) -> float:
    numerator, _, denominator = text.partition("/")
    rate = float(numerator) / float(denominator or 1)
    if not 0.0 < rate < math.inf:
        msg = f"frame rate {text} is not positive"
        raise ValueError(msg)
    return rate


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
) -> Iterator[npt.NDArray[np.uint8]]:
    _check_request(width=width, height=height, fps=fps, scaler=scaler)
    path = Path(source)
    if not path.is_file():
        msg = f"no such source file: {path}"
        raise FileNotFoundError(msg)

    denoising = [f"hqdn3d={denoise}:{denoise}:{denoise * 2}:{denoise * 2}"] if denoise > 0.0 else []
    stages = [
        f"fps={fps}",
        *denoising,
        f"scale={width}:{height}:flags={scaler}:force_original_aspect_ratio=increase",
        f"crop={width}:{height}",
    ]
    command = _command(path, start=start, duration=duration, stages=stages)
    yield from _stream(command, path=path, shape=(height, width, CHANNELS))


def _check_request(*, width: int, height: int, fps: float, scaler: str) -> None:
    if width % pattern.TILE_PX or height % pattern.TILE_PX:
        msg = f"the raster must be a multiple of {pattern.TILE_PX} pixels"
        raise ValueError(msg)
    if fps <= 0.0:
        msg = "a frame rate must be positive"
        raise ValueError(msg)
    if scaler not in limits.SCALERS:
        msg = f"scaler {scaler!r} is not one of {', '.join(limits.SCALERS)}"
        raise ValueError(msg)


def _command(path: Path, *, start: float, duration: float | None, stages: list[str]) -> list[str]:
    window = ["-ss", f"{start}"] if start else []
    limit = ["-t", f"{duration}"] if duration is not None else []
    return [
        require_tool("ffmpeg"),
        "-v",
        "error",
        *window,
        "-i",
        str(path),
        *limit,
        "-vf",
        ",".join(stages),
        "-pix_fmt",
        "rgb24",
        "-f",
        "rawvideo",
        "-",
    ]


def _stream(
    command: list[str], *, path: Path, shape: tuple[int, int, int]
) -> Iterator[npt.NDArray[np.uint8]]:
    stride = shape[0] * shape[1] * shape[2]
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors)
        if process.stdout is None:
            msg = "ffmpeg produced no output stream"
            raise RuntimeError(msg)
        try:
            leftover = yield from _whole_frames(process.stdout, path=path, shape=shape)
        finally:
            process.stdout.close()
            code = process.wait()
            errors.seek(0)
            complaint = errors.read().decode(errors="replace").strip()
    if code != 0:
        msg = f"ffmpeg failed decoding {path} with exit code {code}: {complaint}"
        raise RuntimeError(msg)
    if leftover:
        msg = f"ffmpeg ended {path} on a partial frame of {leftover} bytes; a frame is {stride}"
        raise RuntimeError(msg)


def _whole_frames(
    pipe: IO[bytes], *, path: Path, shape: tuple[int, int, int]
) -> Generator[npt.NDArray[np.uint8], None, int]:
    stride = shape[0] * shape[1] * shape[2]
    for _ in range(MAX_FRAMES):
        raw = pipe.read(stride)
        if len(raw) < stride:
            return len(raw)
        yield np.frombuffer(raw, dtype=np.uint8).reshape(shape)
    msg = f"{path} decoded past {MAX_FRAMES} frames, four hours at the field rate"
    raise RuntimeError(msg)
