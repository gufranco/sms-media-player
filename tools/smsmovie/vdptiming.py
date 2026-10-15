from __future__ import annotations

import heapq
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[2]
BUILD: Final = ROOT / "build"

MINIMUM_INTERVAL: Final = 29
VBLANK_INTERVAL: Final = 16
BLANK_COPY_START: Final = "fmvcopy"
BLANK_COPY_END: Final = "fmvdone"
GUARD_STEPS: Final = 3

DATA_PORT: Final = 0xBE
CONTROL_PORT: Final = 0xBF
DATA: Final = "data"
CONTROL: Final = "control"

CODE = re.compile(
    r"^\s*([0-9A-Fa-f]{8})\s+((?:[0-9A-Fa-fr]{2}\s?)+?)\s+\[\s*(\d+)\s*\]\s+\d+\s+(.*?)\s*$"
)
LABEL = re.compile(r"^\s*([0-9A-Fa-f]{8})\s+\d+\s+(\S+):\s*$")
PORT_IMMEDIATE = re.compile(r"^out\s*\(\s*#?(0x[0-9A-Fa-f]+|\d+)\s*\)\s*,")
PORT_REGISTER = re.compile(r"^out\s*\(\s*c\s*\)\s*,")
BLOCK_OUTPUT = re.compile(r"^(outi|outd|otir|otdr)\b")
REPEATING_OUTPUT = re.compile(r"^(otir|otdr)\b")
REPEAT_INTERVAL: Final = 21
LOAD_C = re.compile(r"^ld\s+c\s*,\s*#?(0x[0-9A-Fa-f]+|\d+)\s*$")
CLOBBER_C = re.compile(
    r"^(ld\s+(c|bc)\s*,|pop\s+bc\b|inc\s+(c|bc)\b|dec\s+(c|bc)\b|exx\b|in\s+c\s*,)"
)
NOT_TAKEN_CYCLES: Final = {"jr": 7, "djnz": 8, "call": 10, "ret": 5}
BRANCH = re.compile(r"^(jp|jr|djnz)\b\s*(?:([A-Za-z]+)\s*,\s*)?(\S+)\s*$")
CALL = re.compile(r"^call\b\s*(?:([A-Za-z]+)\s*,\s*)?(\S+)\s*$")
FUNCTION_PREFIX: Final = "_"
LOCAL_SUFFIX: Final = "$"
UNCONDITIONAL_END = re.compile(r"^(ret|reti|retn)\b")
GUARD_READ = re.compile(r"^in\s+a\s*,\s*\(\s*#?0x7[Ee]\s*\)")
GUARD_LOW = re.compile(r"^cp\s+a\s*,\s*#?0x[Cc]0\s*$")
GUARD_HIGH = re.compile(r"^cp\s+a\s*,\s*#?0x[Ee]0\s*$")


@dataclass(frozen=True, slots=True)
class Instruction:
    address: int
    cycles: int
    text: str
    port: str | None

    @property
    def mnemonic(self) -> str:
        return self.text.split()[0] if self.text else ""


@dataclass(frozen=True, slots=True)
class Listing:
    instructions: list[Instruction]
    labels: dict[str, int]
    owners: list[str | None] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Gap:
    source: str
    first: Instruction
    second: Instruction
    cycles: int
    wrapped: bool
    to_source: str = ""

    def describe(self) -> str:
        route = "around the loop" if self.wrapped else "falling through"
        landing = (
            f" in {self.to_source}" if self.to_source and self.to_source != self.source else ""
        )
        return (
            f"{self.source}: {self.cycles} T-states from {self.first.port} write at "
            f"0x{self.first.address:04X} to {self.second.port} write at "
            f"0x{self.second.address:04X}{landing}, {route}"
        )


@dataclass(slots=True)
class Report:
    source: str
    gaps: list[Gap] = field(default_factory=list)
    violations: list[Gap] = field(default_factory=list)
    control_pairs: list[Gap] = field(default_factory=list)
    unguarded: list[Instruction] = field(default_factory=list)


def parse(text: str) -> Listing:
    instructions: list[Instruction] = []
    owners: list[str | None] = []
    labels: dict[str, int] = {}
    owner: str | None = None
    port_register: int | None = None
    entered = _entered(text)
    for line in text.splitlines():
        label = LABEL.match(line)
        if label:
            name = label.group(2).rstrip(":")
            owner = name if label.group(2).endswith(":") or name in entered else owner
            labels = {**labels, _scoped(name, owner): int(label.group(1), 16)}
            port_register = port_register if name.endswith(LOCAL_SUFFIX) else None
            continue
        read = _instruction(line, port_register)
        if read is not None:
            instruction, port_register = read
            instructions = [*instructions, instruction]
            owners = [*owners, owner]
    return Listing(instructions=instructions, labels=labels, owners=owners)


def _entered(text: str) -> set[str]:
    bodies = [code.group(4) for code in map(CODE.match, text.splitlines()) if code]
    called = {call.group(2) for call in map(CALL.match, bodies) if call}
    jumped = {jump.group(3) for jump in map(BRANCH.match, bodies) if jump}
    return {name for name in called | jumped if name.startswith(FUNCTION_PREFIX)}


def _instruction(line: str, port_register: int | None) -> tuple[Instruction, int | None] | None:
    code = CODE.match(line)
    body = code.group(4) if code else ""
    if code is None or not body or body.startswith(";"):
        return None
    register = _port_register_after(body, port_register)
    instruction = Instruction(
        address=int(code.group(1), 16),
        cycles=int(code.group(3)),
        text=body,
        port=_port_of(body, register),
    )
    return instruction, register


def _scoped(name: str, owner: str | None) -> str:
    return f"{owner}/{name}" if name.endswith(LOCAL_SUFFIX) and owner else name


def _port_register_after(body: str, port_register: int | None) -> int | None:
    loaded = LOAD_C.match(body)
    if loaded:
        return int(loaded.group(1), 0)
    if CLOBBER_C.match(body):
        return None
    return port_register


def check(text: str, *, source: str) -> Report:
    return check_program({source: text})[0]


def check_program(texts: dict[str, str]) -> list[Report]:
    program = Program(listings={source: parse(text) for source, text in texts.items()})
    regions = {source: blank_region(listing) for source, listing in program.listings.items()}
    reports = {source: Report(source=source) for source in texts}
    for gap in _repeating_all(program) + _cheapest_paths(program):
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
        label = LABEL.match(line)
        if label:
            blocks.append(_Block(lines=lines, next_label=label.group(2)))
            lines = []
            continue
        code = CODE.match(line)
        if code is not None:
            lines.append((code.group(4), int(code.group(1), 16)))
    blocks.append(_Block(lines=lines, next_label=None))
    return blocks


def _reaches_copy(block: _Block) -> bool:
    for body, _ in block.lines:
        branch = BRANCH.match(body)
        if branch and branch.group(3).strip() == BLANK_COPY_START:
            return True
    if block.next_label != BLANK_COPY_START or not block.lines:
        return False
    last = block.lines[-1][0]
    jump = BRANCH.match(last)
    leaves = jump is not None and jump.group(2) is None
    return not UNCONDITIONAL_END.match(last) and not leaves


def _advance_guard(guard: list[str], body: str) -> list[str]:
    if GUARD_READ.match(body):
        return ["read"]
    if guard == ["read"] and GUARD_LOW.match(body):
        return ["read", "low"]
    if guard == ["read", "low"] and GUARD_HIGH.match(body):
        return ["read", "low", "high"]
    return guard


def built_listings(root: Path = ROOT) -> list[Path]:
    build = root / BUILD.name
    if not build.is_dir():
        return []
    sources = {path.stem for path in (root / "src").glob("*.c")}
    sources |= {path.stem for path in (root / "src").glob("*.s")}
    return sorted(path for path in build.glob("*.lst") if path.stem in sources)


def stale_listings(listings: list[Path], root: Path = ROOT) -> list[Path]:
    stale: list[Path] = []
    for listing in listings:
        sources = [
            root / "src" / f"{listing.stem}{suffix}"
            for suffix in (".c", ".s")
            if (root / "src" / f"{listing.stem}{suffix}").is_file()
        ]
        if any(source.stat().st_mtime > listing.stat().st_mtime for source in sources):
            stale.append(listing)
    return stale


def data_intervals(reports: list[Report]) -> int:
    return sum(
        1 for report in reports for gap in report.gaps if DATA in {gap.first.port, gap.second.port}
    )


def _port_of(body: str, port_register: int | None) -> str | None:
    immediate = PORT_IMMEDIATE.match(body)
    if immediate:
        return _kind(int(immediate.group(1), 0))
    if BLOCK_OUTPUT.match(body) or PORT_REGISTER.match(body):
        return _kind(port_register) if port_register is not None else DATA
    return None


def _kind(port: int) -> str | None:
    low = port & 0xFF
    if low == DATA_PORT:
        return DATA
    if low == CONTROL_PORT:
        return CONTROL
    return None


def _repeating_all(program: Program) -> list[Gap]:
    return [
        gap for source, listing in program.listings.items() for gap in _repeating(listing, source)
    ]


def _repeating(listing: Listing, source: str) -> list[Gap]:
    return [
        Gap(source, instruction, instruction, REPEAT_INTERVAL, wrapped=True)
        for instruction in listing.instructions
        if instruction.port is not None and REPEATING_OUTPUT.match(instruction.text)
    ]


def _not_taken(instruction: Instruction) -> int:
    if not _conditional(instruction):
        return instruction.cycles
    return NOT_TAKEN_CYCLES.get(instruction.mnemonic.lower(), instruction.cycles)


def _conditional(instruction: Instruction) -> bool:
    mnemonic = instruction.mnemonic.lower()
    operands = instruction.text[len(instruction.mnemonic) :].strip()
    if mnemonic == "djnz":
        return True
    if mnemonic in {"jr", "jp", "call"}:
        return "," in operands
    return mnemonic == "ret" and bool(operands)


Node = tuple[str, int]


@dataclass(frozen=True, slots=True)
class Program:
    listings: dict[str, Listing]

    def at(self, node: Node) -> Instruction:
        source, index = node
        return self.listings[source].instructions[index]

    def entry(self, name: str) -> Node | None:
        for source, listing in self.listings.items():
            address = listing.labels.get(name)
            if address is None:
                continue
            for index, instruction in enumerate(listing.instructions):
                if instruction.address >= address:
                    return (source, index)
        return None

    def return_sites(self, function: str | None) -> list[Node]:
        owners = self._tail_callers(function)
        return [
            (source, index + 1)
            for source, listing in self.listings.items()
            for index, instruction in enumerate(listing.instructions)
            if _called(instruction) in owners and index + 1 < len(listing.instructions)
        ]

    def _tail_callers(self, function: str | None) -> set[str]:
        found: set[str] = set()
        pending = [function] if function else []
        for _ in range(self.size() + 2):
            if not pending:
                return found
            name = pending.pop()
            if name in found:
                continue
            found = {*found, name}
            pending = [*pending, *self._jumping_to(name)]
        msg = f"tail calls into {function} do not settle"
        raise ValueError(msg)

    def _jumping_to(self, name: str) -> list[str]:
        return [
            owner
            for listing in self.listings.values()
            for instruction, owner in zip(listing.instructions, listing.owners, strict=True)
            if owner is not None and _jumped(instruction) == name
        ]

    def size(self) -> int:
        return sum(len(listing.instructions) for listing in self.listings.values())


def _cheapest_paths(program: Program) -> list[Gap]:
    budget = _walk_budget(program)
    starts = [
        (source, index)
        for source, listing in program.listings.items()
        for index, first in enumerate(listing.instructions)
        if first.port is not None
    ]
    return [gap for start in starts for gap in _paths_from(program, start, budget)]


def _walk_budget(program: Program) -> int:
    nodes = [
        (source, index)
        for source, listing in program.listings.items()
        for index in range(len(listing.instructions))
    ]
    return sum(len(_edges(program, node)) for node in nodes) + 1


def _paths_from(program: Program, start: Node, budget: int) -> list[Gap]:
    first = program.at(start)
    reached: dict[Node, tuple[int, bool]] = {}
    best: dict[Node, int] = {}
    pending = [(cost, back, node) for node, cost, back in _edges(program, start)]
    heapq.heapify(pending)
    for _ in range(budget):
        if not pending:
            break
        cycles, wrapped, node = heapq.heappop(pending)
        if best.get(node, cycles + 1) <= cycles:
            continue
        best[node] = cycles
        if program.at(node).port is not None:
            reached[node] = (cycles, wrapped)
            continue
        for after, cost, back in _edges(program, node):
            heapq.heappush(pending, (cycles + cost, wrapped or back, after))
    else:
        msg = f"the walk from 0x{first.address:04X} in {start[0]} did not settle"
        raise ValueError(msg)
    return [
        Gap(start[0], first, program.at(node), cycles, wrapped=wrapped, to_source=node[0])
        for node, (cycles, wrapped) in sorted(reached.items())
    ]


def _edges(program: Program, node: Node) -> list[tuple[Node, int, bool]]:
    source, index = node
    listing = program.listings[source]
    current = listing.instructions[index]
    owner = listing.owners[index] if index < len(listing.owners) else None
    callee = _called(current)
    entry = program.entry(callee) if callee else None
    edges: list[tuple[Node, int, bool]] = []
    if entry is not None:
        edges = [(entry, current.cycles, False)]
    falls = index + 1 < len(listing.instructions) and not _leaves(current)
    if falls and (entry is None or _conditional(current)):
        edges = [*edges, ((source, index + 1), _not_taken(current), False)]
    if current.mnemonic.lower() == "ret":
        edges = [*edges, *((site, current.cycles, True) for site in program.return_sites(owner))]
    target = _target(current, listing.labels, owner)
    landing = _index_at(listing, target) if target is not None else None
    if target is not None and landing is not None:
        edges = [*edges, ((source, landing), current.cycles, target <= current.address)]
    tail = _jumped(current) if target is None else None
    elsewhere = program.entry(tail) if tail else None
    if elsewhere is not None:
        edges = [*edges, (elsewhere, current.cycles, False)]
    if tail and elsewhere is None:
        edges = [*edges, *((site, current.cycles, True) for site in program.return_sites(owner))]
    return edges


def _jumped(instruction: Instruction) -> str | None:
    branch = BRANCH.match(instruction.text)
    name = branch.group(3).strip() if branch else ""
    return name if name.startswith(FUNCTION_PREFIX) else None


def _index_at(listing: Listing, address: int) -> int | None:
    for index, instruction in enumerate(listing.instructions):
        if instruction.address >= address:
            return index
    return None


def _called(instruction: Instruction) -> str | None:
    call = CALL.match(instruction.text)
    return call.group(2) if call else None


def _target(
    instruction: Instruction, labels: dict[str, int], owner: str | None = None
) -> int | None:
    branch = BRANCH.match(instruction.text)
    if branch is None:
        return None
    name = branch.group(3).strip()
    return labels.get(_scoped(name, owner), labels.get(name))


def _leaves(instruction: Instruction) -> bool:
    if UNCONDITIONAL_END.match(instruction.text):
        return not _conditional(instruction)
    branch = BRANCH.match(instruction.text)
    return bool(branch and branch.group(1) in {"jp", "jr"} and branch.group(2) is None)
