from __future__ import annotations

from pathlib import Path
from typing import Final

import numpy as np
import numpy.typing as npt
from fmvcore import font, subtitles

MAX_LINES: Final = 2
BOTTOM_MARGIN: Final = 8
INK_LEVEL: Final = 255
EDGE_LEVEL: Final = 0
NEIGHBOURS: Final = tuple((dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy, dx) != (0, 0))

Frame = npt.NDArray[np.uint8]
Mask = npt.NDArray[np.bool_]


def load(chosen: Path | None, source: Path) -> list[subtitles.Cue]:
    path = chosen if chosen is not None else subtitles.sidecar_for(source)
    if path is None:
        return []
    if not path.is_file():
        msg = f"subtitle file not found: {path}"
        raise FileNotFoundError(msg)
    return subtitles.trimmed(subtitles.parse(path.read_text(encoding="utf-8-sig")))


def caption(
    frames: list[Frame], cues: list[subtitles.Cue], *, start: float, fps: float
) -> list[Frame]:
    if not cues:
        return frames
    return [_captioned(frame, cues, start + index / fps) for index, frame in enumerate(frames)]


def burn(frame: Frame, text: str) -> Frame:
    height, width = frame.shape[:2]
    lines = subtitles.layout(text, columns=width // font.SIZE, max_lines=MAX_LINES)
    ink = _canvas(lines, height=height, width=width)
    edge = _grown(ink) & ~ink
    level = np.where(ink, INK_LEVEL, np.where(edge, EDGE_LEVEL, -1))[..., np.newaxis]
    return np.where(level >= 0, level, frame).astype(np.uint8)


def _captioned(frame: Frame, cues: list[subtitles.Cue], seconds: float) -> Frame:
    cue = subtitles.active(cues, seconds)
    return frame if cue is None else burn(frame, " ".join(cue.lines))


def _line(text: str) -> Mask:
    glyphs = [np.array(font.ink(character), dtype=np.bool_) for character in text]
    return np.hstack(glyphs) if glyphs else np.zeros((font.SIZE, 0), dtype=np.bool_)


def _canvas(lines: tuple[str, ...], *, height: int, width: int) -> Mask:
    block = np.vstack([_centred(_line(line), width) for line in lines])
    top = max(0, height - BOTTOM_MARGIN - block.shape[0])
    below = max(0, height - top - block.shape[0])
    return np.pad(block, ((top, below), (0, 0)))[:height]


def _centred(line: Mask, width: int) -> Mask:
    left = max(0, (width - line.shape[1]) // 2)
    right = max(0, width - left - line.shape[1])
    return np.pad(line, ((0, 0), (left, right)))[:, :width]


def _grown(mask: Mask) -> Mask:
    height, width = mask.shape
    padded = np.pad(mask, 1)
    shifted = [padded[1 + dy : 1 + dy + height, 1 + dx : 1 + dx + width] for dy, dx in NEIGHBOURS]
    return np.logical_or.reduce([mask, *shifted])
