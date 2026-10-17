from __future__ import annotations

from dataclasses import dataclass
from typing import Final

NARROW_CLOSE: Final = 0x05
WIDE_CLOSE: Final = 0x07


@dataclass(frozen=True, slots=True)
class Target:
    name: str
    console: str
    columns: int
    rows: int
    channel_levels: int
    cram_entry_bytes: int
    close_kind: int
    region: int
    extension: str
    stereo: bool


MASTER_SYSTEM: Final = Target(
    name="sms",
    console="Master System",
    columns=32,
    rows=24,
    channel_levels=4,
    cram_entry_bytes=1,
    close_kind=NARROW_CLOSE,
    region=0x4,
    extension=".sms",
    stereo=False,
)

GAME_GEAR: Final = Target(
    name="gg",
    console="Game Gear",
    columns=20,
    rows=18,
    channel_levels=16,
    cram_entry_bytes=2,
    close_kind=WIDE_CLOSE,
    region=0x7,
    extension=".gg",
    stereo=True,
)

TARGETS: Final = {each.name: each for each in (MASTER_SYSTEM, GAME_GEAR)}
DEFAULT: Final = MASTER_SYSTEM


def named(name: str) -> Target:
    found = TARGETS.get(name)
    if found is None:
        known = ", ".join(sorted(TARGETS))
        msg = f"no target named {name!r}; the targets are {known}"
        raise ValueError(msg)
    return found
