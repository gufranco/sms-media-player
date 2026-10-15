from __future__ import annotations

from typing import Final

from smsmovie import console, smscolor, stream

BANK_BYTES: Final = 16 * 1024

CYCLES_PER_LINE: Final = console.CYCLES_PER_LINE
FIELD_CYCLES: Final = console.NTSC_LINES * CYCLES_PER_LINE
VDP_WRITE_CYCLES: Final = 30
FIELD_PAYLOAD_BYTES: Final = FIELD_CYCLES // VDP_WRITE_CYCLES
CLOSE_RESERVE: Final = stream.CLOSE_HEADER + stream.CLOSE_BYTES

DEFAULT_BUDGET: Final = 1800
MEASURED_FIELD_BUDGET: Final = 1900
DEFAULT_CAP: Final = 200
DEFAULT_DITHER: Final = 1.0
PALETTE_KEEP_MARGIN: Final = 0.3
MAX_DITHER: Final = smscolor.MAX_DITHER
DEFAULT_SCALER: Final = "area"
SCALERS: Final = (
    "area",
    "bicubic",
    "bilinear",
    "fast_bilinear",
    "gauss",
    "lanczos",
    "neighbor",
    "sinc",
    "spline",
)
MAX_DENOISE: Final = 64.0
MAX_SOURCE_SECONDS: Final = 4 * 60 * 60
DEFAULT_FPS: Final = 12.0
DEFAULT_COLUMNS: Final = 32
DEFAULT_ROWS: Final = 24
NTSC_FIELD_HZ: Final = console.NTSC_FIELD_HZ
FIELD_SECONDS: Final = 1.0 / NTSC_FIELD_HZ
CODE_BANKS: Final = 2
DEFAULT_MAX_BANKS: Final = 64 - CODE_BANKS
