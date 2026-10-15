from __future__ import annotations

from typing import Final

import numpy as np
import numpy.typing as npt

from smsmedia import smscolor

VRAM_BYTES: Final = 1 << 14

NTSC_CPU_HZ: Final = 3_579_545
NTSC_LINES: Final = 262
CYCLES_PER_LINE: Final = 228
NTSC_FIELD_HZ: Final = NTSC_CPU_HZ / (NTSC_LINES * CYCLES_PER_LINE)
CRAM_BYTES: Final = smscolor.CRAM_BYTES

NAME_TABLE_BASE: Final = 0x3800
BACK_TABLE_BASE: Final = 0x3000
NAME_TABLES: Final = (NAME_TABLE_BASE, BACK_TABLE_BASE)
TABLE_REGISTER: Final = {NAME_TABLE_BASE: 0xFF, BACK_TABLE_BASE: 0xFD}
NAME_TABLE_COLUMNS: Final = 32
NAME_TABLE_ROWS: Final = 28
NAME_TABLE_BYTES: Final = NAME_TABLE_ROWS * NAME_TABLE_COLUMNS * 2
VISIBLE_ROWS: Final = 24

SAT_BASE: Final = NAME_TABLE_BASE + NAME_TABLE_BYTES
SPRITE_SLOTS: Final = 64
SPRITE_OFF: Final = 0xD0

PATTERN_BYTES: Final = 32
PATTERN_SLOTS: Final = BACK_TABLE_BASE // PATTERN_BYTES
RESERVED_PATTERNS: Final = 1

PALETTE_BIT: Final = 1 << 11
IDLE_CELL: Final = PALETTE_BIT
BLACK: Final = 0x00


def boot_vram() -> npt.NDArray[np.uint8]:
    vram = np.zeros(VRAM_BYTES, dtype=np.uint8)
    cell = np.array([IDLE_CELL & 0xFF, IDLE_CELL >> 8], dtype=np.uint8)
    for base in NAME_TABLES:
        vram[base : base + NAME_TABLE_BYTES] = np.tile(cell, NAME_TABLE_BYTES // 2)
    vram[SAT_BASE : SAT_BASE + SPRITE_SLOTS] = SPRITE_OFF
    return vram


def boot_cram() -> npt.NDArray[np.uint8]:
    return np.full(CRAM_BYTES, BLACK, dtype=np.uint8)


def table_at(register: int) -> int:
    for base, value in TABLE_REGISTER.items():
        if value == register:
            return base
    msg = f"register 2 value 0x{register:02X} selects no table this player uses"
    raise ValueError(msg)
