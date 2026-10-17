from __future__ import annotations

from typing import Final

from smsmedia import console, psgsound, smscolor, stream, target

BANK_BYTES: Final = 16 * 1024

CYCLES_PER_LINE: Final = console.CYCLES_PER_LINE
FIELD_CYCLES: Final = console.NTSC_LINES * CYCLES_PER_LINE
VDP_WRITE_CYCLES: Final = 30
FIELD_PAYLOAD_BYTES: Final = FIELD_CYCLES // VDP_WRITE_CYCLES
CLOSE_RESERVE: Final = stream.CLOSE_HEADER + stream.CLOSE_BYTES

SOUND_WRITE_CYCLES: Final = 34
SOUND_RESERVE: Final = -(
    -(stream.PSG_HEADER + psgsound.MAX_FIELD_WRITES) * SOUND_WRITE_CYCLES // VDP_WRITE_CYCLES
)

DEFAULT_BUDGET: Final = 1800
MEASURED_FIELD_BUDGET: Final = 1900
DEFAULT_CAP: Final = 200
DEFAULT_DITHER: Final = 1.0
PALETTE_KEEP_MARGIN: Final = 0.3
MAX_DITHER: Final = smscolor.MAX_DITHER
DEFAULT_SCALER: Final = "area"
MAX_DENOISE: Final = 64.0
MAX_SOURCE_SECONDS: Final = 4 * 60 * 60
DEFAULT_FPS: Final = 12.0
DEFAULT_COLUMNS: Final = target.DEFAULT.columns
DEFAULT_ROWS: Final = target.DEFAULT.rows
NTSC_FIELD_HZ: Final = console.NTSC_FIELD_HZ
FIELD_SECONDS: Final = 1.0 / NTSC_FIELD_HZ
CODE_BANKS: Final = 2
DEFAULT_MAX_BANKS: Final = 64 - CODE_BANKS


def sound_reserve(system: target.Target) -> int:
    return SOUND_RESERVE + (stream.PAN_BYTES if system.stereo else 0)


def close_reserve(system: target.Target) -> int:
    return stream.CLOSE_HEADER + stream.close_bytes(system.close_kind)
