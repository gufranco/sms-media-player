from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from typing import Final

import numpy as np
import numpy.typing as npt
from fmvcore import colour
from fmvcore.dither import NO_DITHER, check_strength

from smsggmedia import smscolor, target

BYTE_MAX: Final = 255
MIN_LEVELS: Final = 2
ONE_BYTE_COLOURS: Final = 256
LITTLE_WORDS: Final = "<u2"
WIDE_REUSE_CONTRAST: Final = 0.5
MASTER_SYSTEM_TOP: Final = target.MASTER_SYSTEM.channel_levels - 1
DITHER_SIDE: Final = 4
FLOOR_CHUNK: Final = 1024
_BAYER_ORDER: Final = np.array(
    [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], dtype=np.float32
)
_BAYER: Final = (_BAYER_ORDER + 0.5) / _BAYER_ORDER.size - 0.5


@dataclass(frozen=True, slots=True)
class Lattice:
    levels: int

    def __post_init__(self) -> None:
        if self.levels < MIN_LEVELS or BYTE_MAX % (self.levels - 1):
            msg = f"{self.levels} levels do not divide a byte into equal steps"
            raise ValueError(msg)

    @property
    def top(self) -> int:
        return self.levels - 1

    @property
    def bits(self) -> int:
        return self.top.bit_length()

    @property
    def count(self) -> int:
        return int(self.levels**smscolor.RGB_CHANNELS)

    @property
    def wide(self) -> bool:
        return self.count > ONE_BYTE_COLOURS

    def quantise(
        self, rgb: npt.NDArray[np.uint8], *, dither: float = NO_DITHER
    ) -> npt.NDArray[np.uint8]:
        return quantise_levels(rgb, dither=dither, top=self.top)

    def pack(self, levels: npt.NDArray[np.integer]) -> npt.NDArray[np.unsignedinteger]:
        if levels.shape[-1] != smscolor.RGB_CHANNELS:
            msg = f"expected a trailing RGB axis, got shape {levels.shape}"
            raise ValueError(msg)
        if np.any(levels < 0) or np.any(levels > self.top):
            msg = f"channel levels must lie in 0 to {self.top}"
            raise ValueError(msg)
        wide = levels.astype(np.uint16)
        packed = wide[..., 0] | (wide[..., 1] << self.bits) | (wide[..., 2] << (2 * self.bits))
        return packed.astype(np.uint16 if self.wide else np.uint8)

    def unpack(self, index: npt.NDArray[np.integer]) -> npt.NDArray[np.uint8]:
        wide = index.astype(np.uint16)
        channels = [(wide >> (shift * self.bits)) & self.top for shift in range(3)]
        return np.stack(channels, axis=-1).astype(np.uint8)

    def to_rgb(self, index: npt.NDArray[np.integer]) -> npt.NDArray[np.uint8]:
        levels = self.unpack(index).astype(np.uint16)
        return (levels * (BYTE_MAX // self.top)).astype(np.uint8)

    @property
    def reuse_scale(self) -> float:
        return float((MASTER_SYSTEM_TOP / self.top) ** 2)

    @property
    def reuse_contrast(self) -> float:
        return WIDE_REUSE_CONTRAST if self.wide else 0.0

    def oklab(self, chroma_weight: float = 1.0) -> npt.NDArray[np.float32]:
        return _oklab_table(self.levels, chroma_weight)

    def cram_bytes(self, entries: npt.NDArray[np.integer]) -> bytes:
        if self.wide:
            return entries.astype(LITTLE_WORDS).tobytes()
        return entries.astype(np.uint8).tobytes()

    def from_cram(self, cram: bytes) -> npt.NDArray[np.unsignedinteger]:
        width = np.dtype(LITTLE_WORDS).itemsize if self.wide else 1
        if len(cram) % width:
            msg = f"a {self.count}-colour palette holds {width} bytes an entry, got {len(cram)}"
            raise ValueError(msg)
        return np.frombuffer(cram, dtype=LITTLE_WORDS if self.wide else np.uint8)

    def nearest(
        self, rgb: npt.NDArray[np.uint8], *, chroma_weight: float = 1.0
    ) -> npt.NDArray[np.unsignedinteger]:
        if rgb.ndim < 1 or rgb.shape[-1] != smscolor.RGB_CHANNELS:
            msg = f"expected a trailing RGB axis, got shape {rgb.shape}"
            raise ValueError(msg)
        index, _ = self._closest(rgb, chroma_weight)
        return index.reshape(rgb.shape[:-1]).astype(np.uint16 if self.wide else np.uint8)

    def floor(self, wanted: npt.NDArray[np.uint8]) -> float:
        _, distance = self._closest(wanted, 1.0)
        return float(distance.mean())

    def _closest(
        self, rgb: npt.NDArray[np.uint8], chroma_weight: float
    ) -> tuple[npt.NDArray[np.intp], npt.NDArray[np.float32]]:
        lab = colour.srgb_to_oklab(rgb.astype(np.float32) / BYTE_MAX).reshape(-1, 3)
        table = self.oklab(chroma_weight)
        costs = [
            ((part[:, None, :] - table[None, :, :]) ** 2).sum(-1)
            for part in np.array_split(lab, max(1, -(-lab.shape[0] // FLOOR_CHUNK)))
        ]
        index = np.concatenate([np.argmin(cost, axis=1) for cost in costs])
        distance = np.sqrt(np.concatenate([cost.min(axis=1) for cost in costs]))
        return index, distance.astype(np.float32)


def quantise_levels(
    rgb: npt.NDArray[np.uint8], *, dither: float = NO_DITHER, top: int
) -> npt.NDArray[np.uint8]:
    if rgb.shape[-1] != smscolor.RGB_CHANNELS:
        msg = f"expected a trailing RGB axis, got shape {rgb.shape}"
        raise ValueError(msg)
    check_strength(dither)
    if dither > NO_DITHER and rgb.ndim != smscolor.IMAGE_RANK:
        msg = f"dithering needs a height and width axis, got shape {rgb.shape}"
        raise ValueError(msg)
    scaled = rgb.astype(np.float32) * (top / BYTE_MAX)
    if dither > NO_DITHER:
        height, width = rgb.shape[0], rgb.shape[1]
        repeats = (height // DITHER_SIDE + 1, width // DITHER_SIDE + 1)
        scaled = scaled + (np.tile(_BAYER, repeats)[:height, :width, None] * dither)
    return np.clip(np.rint(scaled), 0, top).astype(np.uint8)


@cache
def _oklab_table(levels: int, chroma_weight: float) -> npt.NDArray[np.float32]:
    if chroma_weight < 0.0:
        msg = "chroma weight must not be negative"
        raise ValueError(msg)
    space = Lattice(levels)
    rgb = space.to_rgb(np.arange(space.count, dtype=np.uint16)).astype(np.float32) / BYTE_MAX
    lab = colour.srgb_to_oklab(rgb)
    lab[..., 1] *= chroma_weight
    lab[..., 2] *= chroma_weight
    lab.flags.writeable = False
    return lab


MASTER_SYSTEM: Final = Lattice(target.MASTER_SYSTEM.channel_levels)
GAME_GEAR: Final = Lattice(target.GAME_GEAR.channel_levels)
_BY_TARGET: Final = {target.MASTER_SYSTEM.name: MASTER_SYSTEM, target.GAME_GEAR.name: GAME_GEAR}


def for_target(system: target.Target) -> Lattice:
    return _BY_TARGET[system.name]
