from __future__ import annotations

from typing import Final

from smsggmedia import target

RGB_CHANNELS: Final = 3
IMAGE_RANK: Final = 3
PALETTE_ENTRIES: Final = 16
PALETTE_COUNT: Final = 2
CRAM_BYTES: Final = PALETTE_ENTRIES * PALETTE_COUNT * target.MASTER_SYSTEM.cram_entry_bytes
