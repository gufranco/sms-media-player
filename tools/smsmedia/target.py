from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class Target:
    name: str
    console: str
    columns: int
    rows: int
    channel_levels: int
    cram_entry_bytes: int
    region: int
    extension: str


MASTER_SYSTEM: Final = Target(
    name="sms",
    console="Master System",
    columns=32,
    rows=24,
    channel_levels=4,
    cram_entry_bytes=1,
    region=0x4,
    extension=".sms",
)

TARGETS: Final = {MASTER_SYSTEM.name: MASTER_SYSTEM}
DEFAULT: Final = MASTER_SYSTEM


def named(name: str) -> Target:
    found = TARGETS.get(name)
    if found is None:
        known = ", ".join(sorted(TARGETS))
        msg = f"no target named {name!r}; the targets are {known}"
        raise ValueError(msg)
    return found
