from __future__ import annotations

from typing import Final

import numpy as np
import numpy.typing as npt

LEVELS: Final = 4
RGB_CHANNELS: Final = 3
IMAGE_RANK: Final = 3
SRGB_LINEAR_LIMIT: Final = 0.04045
CHANNEL_MAX: Final = LEVELS - 1
PALETTE_ENTRIES: Final = 16
PALETTE_COUNT: Final = 2
CRAM_BYTES: Final = PALETTE_ENTRIES * PALETTE_COUNT
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


def srgb_to_oklab(rgb: npt.NDArray[np.floating]) -> npt.NDArray[np.float32]:
    if rgb.shape[-1] != RGB_CHANNELS:
        msg = f"expected a trailing RGB axis, got shape {rgb.shape}"
        raise ValueError(msg)
    value = np.asarray(rgb, dtype=np.float32)
    linear = np.where(
        value <= SRGB_LINEAR_LIMIT,
        value / 12.92,
        np.power((value + 0.055) / 1.055, 2.4),
    ).astype(np.float32)

    red = linear[..., 0]
    green = linear[..., 1]
    blue = linear[..., 2]

    long_cone = 0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue
    medium_cone = 0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue
    short_cone = 0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue

    long_root = np.cbrt(long_cone)
    medium_root = np.cbrt(medium_cone)
    short_root = np.cbrt(short_cone)

    lightness = 0.2104542553 * long_root + 0.7936177850 * medium_root - 0.0040720468 * short_root
    green_red = 1.9779984951 * long_root - 2.4285922050 * medium_root + 0.4505937099 * short_root
    blue_yellow = 0.0259040371 * long_root + 0.7827717662 * medium_root - 0.8086757660 * short_root

    return np.stack([lightness, green_red, blue_yellow], axis=-1).astype(np.float32)


def oklab_palette(chroma_weight: float = 1.0) -> npt.NDArray[np.float32]:
    if chroma_weight < 0.0:
        msg = "chroma weight must not be negative"
        raise ValueError(msg)

    index = np.arange(COLOUR_COUNT, dtype=np.uint8)
    rgb = colour_to_rgb(index).astype(np.float32) / 255.0
    lab = srgb_to_oklab(rgb)
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
    source = srgb_to_oklab(rgb.astype(np.float32) / 255.0)
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
