from __future__ import annotations

import os
from pathlib import Path

import pytest
from z80 import Cpu, Memory

ROOT = Path(__file__).resolve().parents[2]
ROM = ROOT / "build" / "sms-media-player.sms"
SYMBOLS = ROOT / "build" / "sms-media-player.noi"
ROM_REQUIRED_ENV = "SMSMEDIA_ROM_REQUIRED"
CODE_WINDOW = 0x8000
RETURN = 0xFFF0
STACK = 0xDFF0
WHERE = 0xD000
HALT = 0x76
STEP_LIMIT = 2_000_000
DATA_PORT = 0xBE
CONTROL_PORT = 0xBF
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
    "B": ("##.", "#.#", "##.", "#.#", "##."),
    "D": ("##.", "#.#", "#.#", "#.#", "##."),
    "F": ("###", "#..", "##.", "#..", "#.."),
}


def symbols() -> dict[str, int]:
    found = {}
    for line in SYMBOLS.read_text().splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0] == "DEF":
            found[parts[1]] = int(parts[2], 16)
    return found


def load() -> tuple[bytes, dict[str, int]]:
    if not ROM.is_file() or not SYMBOLS.is_file():
        if os.environ.get(ROM_REQUIRED_ENV) == "1":
            pytest.fail(f"{ROM.name} or its symbols are missing and {ROM_REQUIRED_ENV}=1")
        pytest.skip("run `make rom` first; this executes the ROM's own code")
    return ROM.read_bytes(), symbols()


class Vdp:
    def __init__(self) -> None:
        self.vram = bytearray(0x4000)
        self.cram = bytearray(32)
        self.address = 0
        self.code = 0
        self.latch: int | None = None

    def read(self, _address: int) -> int:
        return 0xFF

    def write(self, address: int, value: int) -> None:
        port = address & 0xFF
        if port == CONTROL_PORT:
            self._control(value)
        elif port == DATA_PORT:
            self._data(value)

    def _control(self, value: int) -> None:
        if self.latch is None:
            self.latch = value
            return
        self.address = ((value & 0x3F) << 8) | self.latch
        self.code = value >> 6
        self.latch = None

    def _data(self, value: int) -> None:
        if self.code == CRAM_WRITE:
            self.cram[self.address & 0x1F] = value
        elif self.code == VRAM_WRITE:
            self.vram[self.address & 0x3FFF] = value
        self.address += 1


def call(
    built: tuple[bytes, dict[str, int]],
    routine: str,
    payload: bytes = b"",
    pokes: dict[int, int] | None = None,
) -> tuple[Vdp, Cpu, Memory]:
    rom, names = built
    image = bytearray(0x10000)
    image[:CODE_WINDOW] = rom[:CODE_WINDOW]
    image[WHERE : WHERE + len(payload)] = payload
    for address, value in (pokes or {}).items():
        image[address] = value
    image[RETURN] = HALT
    image[STACK : STACK + 2] = RETURN.to_bytes(2, "little")
    vdp = Vdp()
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
