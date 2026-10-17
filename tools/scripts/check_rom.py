from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Final

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from smsggmedia import target

BANK_BYTES: Final = 16 * 1024
HEADER: Final = 0x7FF0
SIGNATURE: Final = b"TMR SEGA"
CHECKSUM: Final = 0x7FFA
SIZE_AND_REGION: Final = 0x7FFF
CHECKED_32K: Final = 0x0C
NIBBLE: Final = 4
LOW_NIBBLE: Final = 0x0F


def problems(rom: bytes, system: target.Target) -> list[str]:
    if not rom or len(rom) % BANK_BYTES:
        return [f"a cartridge is a whole number of 16 KB banks, got {len(rom)} bytes"]
    if rom[HEADER : HEADER + len(SIGNATURE)] != SIGNATURE:
        return [f"no {SIGNATURE.decode()} header at 0x{HEADER:04X}"]
    found = []
    size_code = rom[SIZE_AND_REGION] & LOW_NIBBLE
    if size_code != CHECKED_32K:
        found.append(
            f"size code 0x{size_code:X} widens the checksum past 0x8000, which this gate has "
            "only been confirmed against for 32 KB; confirm the wider range on a built ROM first"
        )
    region = rom[SIZE_AND_REGION] >> NIBBLE
    if region != system.region:
        found.append(f"region 0x{region:X} is not the {system.console}'s 0x{system.region:X}")
    stored = int.from_bytes(rom[CHECKSUM : CHECKSUM + 2], "little")
    computed = sum(rom[:HEADER]) & 0xFFFF
    if stored != computed:
        found.append(f"checksum 0x{stored:04X} does not match the body's 0x{computed:04X}")
    return found


def system_of(path: Path) -> target.Target:
    for system in target.TARGETS.values():
        if path.suffix == system.extension:
            return system
    known = ", ".join(system.extension for system in target.TARGETS.values())
    msg = f"{path.name} is not a cartridge this gate knows; it reads {known}"
    raise ValueError(msg)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="check_rom")
    parser.add_argument("roms", nargs="+", type=Path)
    args = parser.parse_args(argv)
    failed = 0
    for path in args.roms:
        found = problems(path.read_bytes(), system_of(path))
        for problem in found:
            print(f"{path}: {problem}", file=sys.stderr)
        if not found:
            print(f"{path}: header, region and checksum agree")
        failed += len(found)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
