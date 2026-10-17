from __future__ import annotations

from typing import Final

import numpy as np
import numpy.typing as npt
from fmvcore import colour

from smsmedia import target

LEVELS: Final = target.MASTER_SYSTEM.channel_levels
RGB_CHANNELS: Final = 3
IMAGE_RANK: Final = 3
CHANNEL_MAX: Final = LEVELS - 1
PALETTE_ENTRIES: Final = 16
PALETTE_COUNT: Final = 2
CRAM_BYTES: Final = PALETTE_ENTRIES * PALETTE_COUNT * target.MASTER_SYSTEM.cram_entry_bytes
COLOUR_COUNT: Final = LEVELS**3

_LEVEL_TO_BYTE: Final = np.array([0, 85, 170, 255], dtype=np.uint8)


def level_to_byte(level: npt.NDArray[np.integer]) -> npt.NDArray[np.uint8]:
    if np.any(level < 0) or np.any(level > CHANNEL_MAX):
        msg = f"channel levels must lie in 0 to {CHANNEL_MAX}"
        raise ValueError(msg)
    return np.asarray(_LEVEL_TO_BYTE[level], dtype=np.uint8)


NO_DITHER: Final = 0.0
MAX_DITHER: Final = 1.0
DITHER_SIDE: Final = 4
_BAYER_ORDER: Final = np.array(
    [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], dtype=np.float32
)
_BAYER: Final = (_BAYER_ORDER + 0.5) / _BAYER_ORDER.size - 0.5


def quantise_levels(
    rgb: npt.NDArray[np.uint8], *, dither: float = NO_DITHER
) -> npt.NDArray[np.uint8]:
    if rgb.shape[-1] != RGB_CHANNELS:
        msg = f"expected a trailing RGB axis, got shape {rgb.shape}"
        raise ValueError(msg)
    if dither < NO_DITHER:
        msg = "a dither strength must not be negative"
        raise ValueError(msg)
    if dither > MAX_DITHER:
        msg = f"a dither strength must be at most {MAX_DITHER:g}, past it a level moves"
        raise ValueError(msg)
    if dither > NO_DITHER and rgb.ndim != IMAGE_RANK:
        msg = f"dithering needs a height and width axis, got shape {rgb.shape}"
        raise ValueError(msg)
    scaled = rgb.astype(np.float32) * (CHANNEL_MAX / 255.0)
    if dither > NO_DITHER:
        height, width = rgb.shape[0], rgb.shape[1]
        repeats = (height // DITHER_SIDE + 1, width // DITHER_SIDE + 1)
        scaled = scaled + (np.tile(_BAYER, repeats)[:height, :width, None] * dither)
    return np.clip(np.rint(scaled), 0, CHANNEL_MAX).astype(np.uint8)


def pack_colour(levels: npt.NDArray[np.integer]) -> npt.NDArray[np.uint8]:
    if levels.shape[-1] != RGB_CHANNELS:
        msg = f"expected a trailing RGB axis, got shape {levels.shape}"
        raise ValueError(msg)
    if np.any(levels < 0) or np.any(levels > CHANNEL_MAX):
        msg = f"channel levels must lie in 0 to {CHANNEL_MAX}"
        raise ValueError(msg)
    red = levels[..., 0].astype(np.uint8)
    green = levels[..., 1].astype(np.uint8)
    blue = levels[..., 2].astype(np.uint8)
    return (red | (green << 2) | (blue << 4)).astype(np.uint8)


def unpack_colour(byte: npt.NDArray[np.uint8]) -> npt.NDArray[np.uint8]:
    red = byte & 0x03
    green = (byte >> 2) & 0x03
    blue = (byte >> 4) & 0x03
    return np.stack([red, green, blue], axis=-1).astype(np.uint8)


def colour_to_rgb(byte: npt.NDArray[np.uint8]) -> npt.NDArray[np.uint8]:
    return level_to_byte(unpack_colour(byte))


def oklab_palette(chroma_weight: float = 1.0) -> npt.NDArray[np.float32]:
    if chroma_weight < 0.0:
        msg = "chroma weight must not be negative"
        raise ValueError(msg)

    index = np.arange(COLOUR_COUNT, dtype=np.uint8)
    rgb = colour_to_rgb(index).astype(np.float32) / 255.0
    lab = colour.srgb_to_oklab(rgb)
    lab[..., 1] *= chroma_weight
    lab[..., 2] *= chroma_weight
    return lab


def nearest_colour(
    rgb: npt.NDArray[np.uint8],
    *,
    chroma_weight: float = 1.0,
) -> npt.NDArray[np.uint8]:
    if rgb.ndim < 1 or rgb.shape[-1] != RGB_CHANNELS:
        msg = f"expected a trailing RGB axis, got shape {rgb.shape}"
        raise ValueError(msg)

    lab = oklab_palette(chroma_weight)
    source = colour.srgb_to_oklab(rgb.astype(np.float32) / 255.0)
    flat = source.reshape(-1, 3).astype(np.float32)

    best = np.zeros(flat.shape[0], dtype=np.uint8)
    error = np.full(flat.shape[0], np.inf, dtype=np.float32)
    for index in range(COLOUR_COUNT):
        difference = flat - lab[index]
        cost = (difference * difference).sum(axis=1)
        closer = cost < error
        error[closer] = cost[closer]
        best[closer] = index
    return best.reshape(rgb.shape[:-1])
