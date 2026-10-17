from __future__ import annotations

import os
from pathlib import Path

import pytest
from z80 import Cpu, Memory, core

ROOT = Path(__file__).resolve().parents[2]
ROM = ROOT / "build" / "smsmedia.sms"
SYMBOLS = ROOT / "build" / "smsmedia.noi"
GG_ROM = ROOT / "build" / "smsmedia.gg"
GG_SYMBOLS = ROOT / "build" / "gg" / "smsmedia.noi"
CRAM_BYTES = 32
GG_CRAM_BYTES = 64
ROM_REQUIRED_ENV = "SMSMEDIA_ROM_REQUIRED"
CODE_WINDOW = 0x8000
RETURN = 0xFFF0
STACK = 0xDFF0
WHERE = 0xD000
HALT = 0x76
STEP_LIMIT = 2_000_000
DATA_PORT = 0xBE
CONTROL_PORT = 0xBF
PAN_PORT = 0x06
V_COUNTER = 0x7E
CYCLES_PER_LINE = 228
LINES_PER_FIELD = 262
LAST_UNREPEATED_LINE = 0xDA
REPEATED_LINES = 6
VRAM_WRITE = 1
CRAM_WRITE = 3
SPRITE_PATTERNS = 0x2000
TILE_BYTES = 32
SAT_Y = 0x3F00
SAT_XN = 0x3F80
SPRITE_END = 0xD0
GLYPHS = {
    "0": ("###", "#.#", "#.#", "#.#", "###"),
    "1": (".#.", "##.", ".#.", ".#.", "###"),
    "2": ("###", "..#", "###", "#..", "###"),
    "3": ("###", "..#", ".##", "..#", "###"),
    "4": ("#.#", "#.#", "###", "..#", "..#"),
    "5": ("###", "#..", "###", "..#", "###"),
    "7": ("###", "..#", "..#", ".#.", ".#."),
    "9": ("###", "#.#", "###", "..#", "###"),
    ":": ("...", ".#.", "...", ".#.", "..."),
    "/": ("..#", "..#", ".#.", "#..", "#.."),
    " ": ("...", "...", "...", "...", "..."),
    ">": ("#..", "##.", "###", "##.", "#.."),
    "=": ("#.#", "#.#", "#.#", "#.#", "#.#"),
    "x": ("...", "#.#", ".#.", "#.#", "..."),
    "B": ("##.", "#.#", "##.", "#.#", "##."),
    "D": ("##.", "#.#", "#.#", "#.#", "##."),
    "F": ("###", "#..", "##.", "#..", "#.."),
}


def symbols(path: Path = SYMBOLS) -> dict[str, int]:
    found = {}
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0] == "DEF":
            found[parts[1]] = int(parts[2], 16)
    return found


def load(rom: Path = ROM, names: Path = SYMBOLS) -> tuple[bytes, dict[str, int]]:
    if not rom.is_file() or not names.is_file():
        if os.environ.get(ROM_REQUIRED_ENV) == "1":
            pytest.fail(f"{rom.name} or its symbols are missing and {ROM_REQUIRED_ENV}=1")
        pytest.skip("run `make rom` first; this executes the ROM's own code")
    return rom.read_bytes(), symbols(names)


def load_gg() -> tuple[bytes, dict[str, int]]:
    return load(GG_ROM, GG_SYMBOLS)


def counter(line: int) -> int:
    within = line % LINES_PER_FIELD
    return within if within <= LAST_UNREPEATED_LINE else within - REPEATED_LINES


class Vdp:
    def __init__(self, *, gg: bool = False) -> None:
        self.gg = gg
        self.vram = bytearray(0x4000)
        self.cram = bytearray(GG_CRAM_BYTES if gg else CRAM_BYTES)
        self.cram_latch = 0
        self.address = 0
        self.code = 0
        self.latch: int | None = None
        self.clock: core.Cpu | None = None
        self.line = 0
        self.since = 0
        self.writes = 0
        self.pans: list[int] = []

    def start_at(self, line: int) -> None:
        self.line = line
        self.since = self.cycles()

    def now(self) -> int:
        return self.line + (self.cycles() - self.since) // CYCLES_PER_LINE

    def cycles(self) -> int:
        return 0 if self.clock is None else self.clock.cycles

    def read(self, address: int) -> int:
        if self.clock is None or address & 0xFF != V_COUNTER:
            return 0xFF
        return counter(self.now())

    def write(self, address: int, value: int) -> None:
        port = address & 0xFF
        if port == CONTROL_PORT:
            self._control(value)
        elif port == DATA_PORT:
            self._data(value)
        elif port == PAN_PORT:
            self.pans = [*self.pans, value]

    def _control(self, value: int) -> None:
        if self.latch is None:
            self.latch = value
            return
        self.address = ((value & 0x3F) << 8) | self.latch
        self.code = value >> 6
        self.latch = None

    def _data(self, value: int) -> None:
        self.writes += 1
        if self.code == CRAM_WRITE:
            self._cram(value)
        elif self.code == VRAM_WRITE:
            self.vram[self.address & 0x3FFF] = value
        self.address += 1

    def _cram(self, value: int) -> None:
        if not self.gg:
            self.cram[self.address % CRAM_BYTES] = value
            return
        if self.address % 2 == 0:
            self.cram_latch = value
            return
        self.cram[(self.address - 1) % GG_CRAM_BYTES] = self.cram_latch
        self.cram[self.address % GG_CRAM_BYTES] = value


def call(
    built: tuple[bytes, dict[str, int]],
    routine: str,
    payload: bytes = b"",
    pokes: dict[int, int] | None = None,
    *,
    gg: bool = False,
) -> tuple[Vdp, Cpu, Memory]:
    rom, names = built
    image = bytearray(0x10000)
    image[:CODE_WINDOW] = rom[:CODE_WINDOW]
    image[WHERE : WHERE + len(payload)] = payload
    for address, value in (pokes or {}).items():
        image[address] = value
    image[RETURN] = HALT
    image[STACK : STACK + 2] = RETURN.to_bytes(2, "little")
    vdp = Vdp(gg=gg)
    memory = Memory(image=bytes(image))
    cpu = Cpu("z80", memory, ports=vdp)
    cpu.reset()
    cpu.registers.pc = names[routine]
    cpu.registers.sp = STACK
    cpu.registers.hl = WHERE
    for _ in range(STEP_LIMIT):
        if cpu.halted:
            return vdp, cpu, memory
        cpu.step()
    pytest.fail(f"{routine} did not return within {STEP_LIMIT} steps")
    return vdp, cpu, memory


def run(built: tuple[bytes, dict[str, int]], routine: str, payload: bytes = b"") -> Vdp:
    return call(built, routine, payload)[0]


class Session:
    def __init__(self, built: tuple[bytes, dict[str, int]], payload: bytes = b"") -> None:
        rom, names = built
        image = bytearray(0x10000)
        image[:CODE_WINDOW] = rom[:CODE_WINDOW]
        image[WHERE : WHERE + len(payload)] = payload
        image[RETURN] = HALT
        self.names = names
        self.vdp = Vdp()
        self.memory = Memory(image=bytes(image))
        self.cpu = Cpu("z80", self.memory, ports=self.vdp)
        self.cpu.reset()
        self.vdp.clock = self.cpu

    def poke(self, address: int, data: bytes) -> None:
        for offset, value in enumerate(data):
            self.memory.write8(address + offset, value)

    def call(self, routine: str, *, a: int = 0, hl: int = WHERE) -> int:
        self.poke(STACK, RETURN.to_bytes(2, "little"))
        self.cpu.halted = False
        self.cpu.registers.pc = self.names[routine]
        self.cpu.registers.sp = STACK
        self.cpu.registers.a = a
        self.cpu.registers.hl = hl
        start = self.cpu.cycles
        for _ in range(STEP_LIMIT):
            if self.cpu.halted:
                return self.cpu.cycles - start
            self.cpu.step()
        pytest.fail(f"{routine} did not return within {STEP_LIMIT} steps")
        return 0


def tile(vdp: Vdp, number: int) -> bytes:
    start = SPRITE_PATTERNS + number * TILE_BYTES
    return bytes(vdp.vram[start : start + TILE_BYTES])


def white_rows(data: bytes) -> list[str]:
    return [
        "".join("#" if data[row * 4] & (0x80 >> column) else "." for column in range(8))
        for row in range(8)
    ]


def pixels(vdp: Vdp, numbers: list[int]) -> list[str]:
    rows = [white_rows(tile(vdp, number)) for number in numbers]
    return ["".join(tile_rows[row] for tile_rows in rows) for row in range(8)]


def expected_pixels(text: str) -> list[str]:
    cells = [GLYPHS[character] for character in text]
    middle = ["".join(cell[row] + "." for cell in cells) for row in range(5)]
    blank = "." * len(middle[0])
    return [blank, *middle, blank, blank]


def sprites(vdp: Vdp) -> list[tuple[int, int, int]]:
    found = []
    for index in range(64):
        y = vdp.vram[SAT_Y + index]
        if y == SPRITE_END:
            break
        found.append((y, vdp.vram[SAT_XN + 2 * index], vdp.vram[SAT_XN + 2 * index + 1]))
    return found
