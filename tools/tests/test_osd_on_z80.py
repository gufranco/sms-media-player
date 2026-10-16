from __future__ import annotations

import os
import struct
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
SAT_Y = 0x3F00
SAT_XN = 0x3F80
SPRITE_END = 0xD0
FIRST_TILE = 176
TILE_VRAM = 0x3600
TILE_BYTES = 32
TEXT_TILES = 6
BAR_SPRITES = 8
TEXT_Y = 167
BAR_Y = 179
TEXT_X = 104
BAR_X = 96
FULL = FIRST_TILE + TEXT_TILES
EMPTY = FULL + 1
PARTIAL = FULL + 2
INK_BLACK = 0x00
INK_WHITE = 0x3F
FIELDS_PER_SECOND = 59.9227
GLYPHS = {
    "0": ("###", "#.#", "#.#", "#.#", "###"),
    "1": (".#.", "##.", ".#.", ".#.", "###"),
    "2": ("###", "..#", "###", "#..", "###"),
    "3": ("###", "..#", ".##", "..#", "###"),
    ":": ("...", ".#.", "...", ".#.", "..."),
    "/": ("..#", "..#", ".#.", "#..", "#.."),
    " ": ("...", "...", "...", "...", "..."),
}


def symbols() -> dict[str, int]:
    found = {}
    for line in SYMBOLS.read_text().splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0] == "DEF":
            found[parts[1]] = int(parts[2], 16)
    return found


@pytest.fixture(scope="module")
def built():
    if not ROM.is_file() or not SYMBOLS.is_file():
        if os.environ.get(ROM_REQUIRED_ENV) == "1":
            pytest.fail(f"{ROM.name} or its symbols are missing and {ROM_REQUIRED_ENV}=1")
        pytest.skip("run `make rom` first; this executes the ROM's own overlay")
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


def run(built, routine: str, *, elapsed: int = 0, total: int = 1) -> Vdp:
    rom, names = built
    image = bytearray(0x10000)
    image[:CODE_WINDOW] = rom[:CODE_WINDOW]
    image[WHERE : WHERE + 8] = struct.pack("<II", elapsed, total)
    image[RETURN] = HALT
    image[STACK : STACK + 2] = RETURN.to_bytes(2, "little")
    vdp = Vdp()
    cpu = Cpu("z80", Memory(image=bytes(image)), ports=vdp)
    cpu.reset()
    cpu.registers.pc = names[routine]
    cpu.registers.sp = STACK
    cpu.registers.hl = WHERE
    for _ in range(STEP_LIMIT):
        if cpu.halted:
            return vdp
        cpu.step()
    pytest.fail(f"{routine} did not return within {STEP_LIMIT} steps")
    return vdp


def fields(seconds: int) -> int:
    return round(seconds * FIELDS_PER_SECOND)


def tile(vdp: Vdp, number: int) -> bytes:
    start = TILE_VRAM + (number - FIRST_TILE) * TILE_BYTES
    return bytes(vdp.vram[start : start + TILE_BYTES])


def white_rows(data: bytes) -> list[str]:
    return [
        "".join("#" if data[row * 4] & (0x80 >> column) else "." for column in range(8))
        for row in range(8)
    ]


def text_pixels(vdp: Vdp) -> list[str]:
    rows = [white_rows(tile(vdp, FIRST_TILE + index)) for index in range(TEXT_TILES)]
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


class TestShow:
    def test_the_ink_entries_are_black_and_white(self, built):
        # Arrange
        where = {"elapsed": fields(1), "total": fields(3)}

        # Act
        vdp = run(built, "_fmv_osd_show", **where)

        # Assert
        assert (vdp.cram[30], vdp.cram[31]) == (INK_BLACK, INK_WHITE)

    def test_the_text_reads_elapsed_over_total(self, built):
        # Arrange
        where = {"elapsed": fields(1), "total": fields(3)}

        # Act
        vdp = run(built, "_fmv_osd_show", **where)

        # Assert
        assert text_pixels(vdp) == expected_pixels("00:01/00:03 ")

    def test_the_text_sprites_sit_in_a_row_above_the_bar(self, built):
        # Arrange
        where = {"elapsed": fields(1), "total": fields(3)}

        # Act
        vdp = run(built, "_fmv_osd_show", **where)

        # Assert
        assert sprites(vdp)[:TEXT_TILES] == [
            (TEXT_Y, TEXT_X + 8 * index, FIRST_TILE + index) for index in range(TEXT_TILES)
        ]

    def test_half_way_lights_half_the_bar(self, built):
        # Arrange
        where = {"elapsed": 90, "total": 180}

        # Act
        vdp = run(built, "_fmv_osd_show", **where)

        # Assert
        assert sprites(vdp)[TEXT_TILES:] == [
            (BAR_Y, BAR_X + 8 * index, FULL if index < 4 else EMPTY) for index in range(BAR_SPRITES)
        ]

    def test_a_fill_between_sprites_uses_the_partial_tile(self, built):
        # Arrange
        where = {"elapsed": 13, "total": 64}

        # Act
        vdp = run(built, "_fmv_osd_show", **where)

        # Assert
        assert [number for _, _, number in sprites(vdp)[TEXT_TILES:]][:3] == [
            FULL,
            PARTIAL,
            EMPTY,
        ]

    def test_the_partial_tile_lights_the_leftover_columns(self, built):
        # Arrange
        where = {"elapsed": 13, "total": 64}

        # Act
        vdp = run(built, "_fmv_osd_show", **where)

        # Assert
        assert white_rows(tile(vdp, PARTIAL))[2:6] == ["#####..."] * 4

    def test_the_end_of_the_film_fills_the_bar(self, built):
        # Arrange
        where = {"elapsed": 500, "total": 500}

        # Act
        vdp = run(built, "_fmv_osd_show", **where)

        # Assert
        assert [number for _, _, number in sprites(vdp)[TEXT_TILES:]] == [FULL] * BAR_SPRITES

    def test_the_total_rounds_to_the_nearest_second(self, built):
        # Arrange
        where = {"elapsed": 0, "total": 106}

        # Act
        vdp = run(built, "_fmv_osd_show", **where)

        # Assert
        assert text_pixels(vdp) == expected_pixels("00:00/00:02 ")

    def test_the_elapsed_time_counts_whole_seconds(self, built):
        # Arrange
        where = {"elapsed": 106, "total": 180}

        # Act
        vdp = run(built, "_fmv_osd_show", **where)

        # Assert
        assert text_pixels(vdp) == expected_pixels("00:01/00:03 ")


class TestHide:
    def test_hiding_ends_the_sprite_list_at_the_first_entry(self, built):
        # Arrange
        routine = "_fmv_osd_hide"

        # Act
        vdp = run(built, routine)

        # Assert
        assert sprites(vdp) == []
