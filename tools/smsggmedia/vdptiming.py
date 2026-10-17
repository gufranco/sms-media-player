from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from fmvcore import sdccz80, writetiming
from fmvcore.writetiming import Gap, Instruction, Listing

from smsggmedia import target as targets

ROOT: Final = Path(__file__).resolve().parents[2]
BUILDS: Final = {
    targets.MASTER_SYSTEM.name: Path("build"),
    targets.GAME_GEAR.name: Path("build/gg"),
}

MINIMUM_INTERVAL: Final = 29
VBLANK_INTERVAL: Final = 16
BLANK_COPY_START: Final = "fmvcopy"
BLANK_COPY_END: Final = "fmvdone"
GUARD_STEPS: Final = 3

DATA_PORT: Final = 0xBE
CONTROL_PORT: Final = 0xBF
DATA: Final = "data"
CONTROL: Final = "control"
PORTS: Final = {DATA_PORT: DATA, CONTROL_PORT: CONTROL}

GUARD_READ = re.compile(r"^in\s+a\s*,\s*\(\s*#?0x7[Ee]\s*\)")
GUARD_LOW = re.compile(r"^cp\s+a\s*,\s*#?0x[Cc]0\s*$")
GUARD_HIGH = re.compile(r"^cp\s+a\s*,\s*#?0x[Ee]0\s*$")


@dataclass(slots=True)
class Report:
    source: str
    gaps: list[Gap] = field(default_factory=list)
    violations: list[Gap] = field(default_factory=list)
    control_pairs: list[Gap] = field(default_factory=list)
    unguarded: list[Instruction] = field(default_factory=list)


def parse(text: str) -> Listing:
    return sdccz80.parse(text, ports=PORTS, unknown_port=DATA)


def check(text: str, *, source: str) -> Report:
    return check_program({source: text})[0]


def check_program(texts: dict[str, str]) -> list[Report]:
    program = writetiming.Program(
        listings={source: parse(text) for source, text in texts.items()}, unit=sdccz80.CYCLE_UNIT
    )
    regions = {source: blank_region(listing) for source, listing in program.listings.items()}
    reports = {source: Report(source=source) for source in texts}
    for gap in writetiming.gaps(program):
        report = reports[gap.source]
        report.gaps.append(gap)
        if gap.first.port == CONTROL and gap.second.port == CONTROL:
            report.control_pairs.append(gap)
            if gap.cycles < MINIMUM_INTERVAL:
                report.violations.append(gap)
            continue
        if gap.cycles < floor_for(gap, regions[gap.to_source or gap.source]):
            report.violations.append(gap)
    for source, text in texts.items():
        if regions[source] is not None:
            reports[source].unguarded = unguarded_setups(text, program.listings[source])
    return list(reports.values())


def blank_region(listing: Listing) -> tuple[int, int] | None:
    start = listing.labels.get(BLANK_COPY_START)
    end = listing.labels.get(BLANK_COPY_END)
    if start is None or end is None:
        return None
    return start, end


def floor_for(gap: Gap, region: tuple[int, int] | None) -> int:
    if region is None:
        return MINIMUM_INTERVAL
    start, end = region
    inside = start <= gap.second.address < end
    return VBLANK_INTERVAL if inside else MINIMUM_INTERVAL


def unguarded_setups(text: str, listing: Listing) -> list[Instruction]:
    by_address = {instruction.address: instruction for instruction in listing.instructions}
    found: list[Instruction] = []
    for block in _blocks(text):
        if not _reaches_copy(block):
            continue
        guard: list[str] = []
        for body, address in block.lines:
            guard = _advance_guard(guard, body)
            instruction = by_address.get(address)
            if instruction is not None and instruction.port == CONTROL and len(guard) < GUARD_STEPS:
                found.append(instruction)
    return found


@dataclass(frozen=True, slots=True)
class _Block:
    lines: list[tuple[str, int]]
    next_label: str | None


def _blocks(text: str) -> list[_Block]:
    blocks: list[_Block] = []
    lines: list[tuple[str, int]] = []
    for line in text.splitlines():
        label = sdccz80.LABEL.match(line)
        if label:
            blocks.append(_Block(lines=lines, next_label=label.group(2)))
            lines = []
            continue
        code = sdccz80.CODE.match(line)
        if code is not None:
            lines.append((code.group(4), int(code.group(1), 16)))
    blocks.append(_Block(lines=lines, next_label=None))
    return blocks


def _reaches_copy(block: _Block) -> bool:
    for body, _ in block.lines:
        branch = sdccz80.BRANCH.match(body)
        if branch and branch.group(3).strip() == BLANK_COPY_START:
            return True
    if block.next_label != BLANK_COPY_START or not block.lines:
        return False
    last = block.lines[-1][0]
    jump = sdccz80.BRANCH.match(last)
    leaves = jump is not None and jump.group(2) is None
    return not sdccz80.UNCONDITIONAL_END.match(last) and not leaves


def _advance_guard(guard: list[str], body: str) -> list[str]:
    if GUARD_READ.match(body):
        return ["read"]
    if guard == ["read"] and GUARD_LOW.match(body):
        return ["read", "low"]
    if guard == ["read", "low"] and GUARD_HIGH.match(body):
        return ["read", "low", "high"]
    return guard


def built_listings(root: Path = ROOT, target: str = targets.DEFAULT.name) -> list[Path]:
    build = root / BUILDS[targets.named(target).name]
    if not build.is_dir():
        return []
    sources = {path.stem for path in _sources(root, target)}
    return sorted(path for path in build.glob("*.lst") if path.stem in sources)


def stale_listings(
    listings: list[Path], root: Path = ROOT, target: str = targets.DEFAULT.name
) -> list[Path]:
    edited = {path.stem: path.stat().st_mtime for path in _sources(root, target)}
    return [
        listing for listing in listings if edited.get(listing.stem, 0.0) > listing.stat().st_mtime
    ]


def _sources(root: Path, target: str) -> list[Path]:
    shared = root / "src"
    own = shared / target
    return [*shared.glob("*.c"), *shared.glob("*.s"), *own.glob("*.c")]


def data_intervals(reports: list[Report]) -> int:
    return sum(
        1 for report in reports for gap in report.gaps if DATA in {gap.first.port, gap.second.port}
    )
