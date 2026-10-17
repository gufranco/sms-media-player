from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from typing import Final

import numpy as np
import numpy.typing as npt
from fmvcore import colour

from smsggmedia import smscolor, target

BYTE_MAX: Final = 255
MIN_LEVELS: Final = 2
ONE_BYTE_COLOURS: Final = 256
LITTLE_WORDS: Final = "<u2"


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
        self, rgb: npt.NDArray[np.uint8], *, dither: float = smscolor.NO_DITHER
    ) -> npt.NDArray[np.uint8]:
        return smscolor.quantise_levels(rgb, dither=dither, top=self.top)

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

    def oklab(self, chroma_weight: float = 1.0) -> npt.NDArray[np.float32]:
        return _oklab_table(self.levels, chroma_weight)

    def cram_bytes(self, entries: npt.NDArray[np.integer]) -> bytes:
        if self.wide:
            return entries.astype(LITTLE_WORDS).tobytes()
        return entries.astype(np.uint8).tobytes()


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
