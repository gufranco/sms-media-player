from __future__ import annotations

from typing import Final

import numpy as np
import numpy.typing as npt

from smsmedia import console

TILE_PX: Final = 8
BATCH_RANK: Final = 2
TILE_STACK_RANK: Final = 3
PLANES: Final = 4
PATTERN_BYTES: Final = console.PATTERN_BYTES
COLOURS: Final = 1 << PLANES
MAX_PATTERNS: Final = 1 << 9
VRAM_BYTES: Final = console.VRAM_BYTES

INDEX_BITS: Final = 9
INDEX_MASK: Final = (1 << INDEX_BITS) - 1
HFLIP_BIT: Final = 1 << INDEX_BITS
VFLIP_BIT: Final = 1 << 10
PALETTE_BIT: Final = console.PALETTE_BIT
PRIORITY_BIT: Final = 1 << 12


def pack_patterns(tiles: npt.NDArray[np.uint8]) -> npt.NDArray[np.uint8]:
    if tiles.ndim != TILE_STACK_RANK or tiles.shape[1:] != (TILE_PX, TILE_PX):
        msg = f"tiles must be a batch of 8x8 arrays, got shape {tiles.shape}"
        raise ValueError(msg)
    if tiles.size and int(tiles.max()) >= COLOURS:
        msg = "tile pixels must be 4-bit palette indices in the range 0 to 15"
        raise ValueError(msg)

    count = tiles.shape[0]
    packed = np.zeros((count, TILE_PX, PLANES), dtype=np.uint8)
    if count == 0:
        return packed.reshape(count, PATTERN_BYTES)

    weight = (1 << np.arange(TILE_PX - 1, -1, -1, dtype=np.uint16)).astype(np.uint16)
    for plane in range(PLANES):
        bit = ((tiles >> plane) & 1).astype(np.uint16)
        packed[:, :, plane] = (bit * weight).sum(axis=2).astype(np.uint8)

    return packed.reshape(count, PATTERN_BYTES)


def unpack_patterns(packed: npt.NDArray[np.uint8]) -> npt.NDArray[np.uint8]:
    if packed.ndim != BATCH_RANK or packed.shape[1] != PATTERN_BYTES:
        msg = f"patterns must be a batch of {PATTERN_BYTES}-byte rows, got {packed.shape}"
        raise ValueError(msg)

    count = packed.shape[0]
    rows = packed.reshape(count, TILE_PX, PLANES)
    tiles = np.zeros((count, TILE_PX, TILE_PX), dtype=np.uint8)
    for plane in range(PLANES):
        plane_byte = rows[:, :, plane]
        for column in range(TILE_PX):
            bit = (plane_byte >> (TILE_PX - 1 - column)) & 1
            tiles[:, :, column] |= (bit << plane).astype(np.uint8)
    return tiles


def name_table_entry(
    *,
    index: int,
    palette: int,
    hflip: bool = False,
    vflip: bool = False,
    priority: bool = False,
) -> int:
    if not 0 <= index < MAX_PATTERNS:
        msg = f"pattern index {index} does not fit the {INDEX_BITS}-bit field"
        raise ValueError(msg)
    if palette not in (0, 1):
        msg = f"palette {palette} is not one of the two hardware palettes"
        raise ValueError(msg)

    word = index
    if hflip:
        word |= HFLIP_BIT
    if vflip:
        word |= VFLIP_BIT
    if palette:
        word |= PALETTE_BIT
    if priority:
        word |= PRIORITY_BIT
    return word


def tile_frame(frame: npt.NDArray[np.uint8]) -> npt.NDArray[np.uint8]:
    if frame.ndim != BATCH_RANK:
        msg = f"a frame must be two dimensional, got shape {frame.shape}"
        raise ValueError(msg)
    height, width = frame.shape
    if height % TILE_PX or width % TILE_PX:
        msg = f"a frame must be a whole number of {TILE_PX}x{TILE_PX} cells, got {frame.shape}"
        raise ValueError(msg)

    rows = height // TILE_PX
    columns = width // TILE_PX
    cells = frame.reshape(rows, TILE_PX, columns, TILE_PX)
    return cells.transpose(0, 2, 1, 3).reshape(rows * columns, TILE_PX, TILE_PX)
