from __future__ import annotations

import struct

import pytest
from z80vdp import WHERE, call, load

KEYS_AT = WHERE + 0x40
FIELDS = (0, 600, 1200, 1800)
AHEAD = 1
BACK = -1
NONE = 0xFF
BANK_SELECT = 0xFFFF
WINDOW = 0x8000


@pytest.fixture(scope="module")
def built():
    return load()


def key(bank: int, offset: int, frame: int, field: int) -> bytes:
    return struct.pack("<BHHI", bank, offset, frame, field)


def table() -> bytes:
    return b"".join(key(2 + n, 0x100 * n, 40 * n, field) for n, field in enumerate(FIELDS))


def target(built, *, elapsed: int, direction: int) -> int:
    query = struct.pack("<HBIb", KEYS_AT, len(FIELDS), elapsed, direction)
    pokes = {KEYS_AT + n: byte for n, byte in enumerate(table())}
    _, cpu, _ = call(built, "_fmv_seek_target", query, pokes)
    return cpu.registers.a


def word(memory, address: int) -> int:
    return memory.read8(address) | (memory.read8(address + 1) << 8)


class TestTarget:
    def test_ahead_goes_to_the_next_point(self, built):
        # Arrange
        elapsed = 700

        # Act
        found = target(built, elapsed=elapsed, direction=AHEAD)

        # Assert
        assert found == 2

    def test_ahead_from_the_last_point_goes_nowhere(self, built):
        # Arrange
        elapsed = 1900

        # Act
        found = target(built, elapsed=elapsed, direction=AHEAD)

        # Assert
        assert found == NONE

    def test_back_well_into_a_section_returns_to_its_start(self, built):
        # Arrange
        elapsed = 1500

        # Act
        found = target(built, elapsed=elapsed, direction=BACK)

        # Assert
        assert found == 2

    def test_back_just_after_a_point_goes_to_the_one_before(self, built):
        # Arrange
        elapsed = 1250

        # Act
        found = target(built, elapsed=elapsed, direction=BACK)

        # Assert
        assert found == 1

    def test_back_at_the_start_stays_at_the_start(self, built):
        # Arrange
        elapsed = 30

        # Act
        found = target(built, elapsed=elapsed, direction=BACK)

        # Assert
        assert found == 0


class TestSeek:
    def test_the_replay_resumes_at_the_point(self, built):
        # Arrange
        _, names = built
        pokes = {names["_movie_last_bank"]: 9}

        # Act
        _, _, memory = call(built, "_fmv_movie_seek", key(5, 0x1234, 77, 900), pokes)

        # Assert
        assert (
            memory.read8(names["_movie_bank"]),
            memory.read8(BANK_SELECT),
            word(memory, names["_movie_cursor"]),
            memory.read8(names["_movie_kind"]),
        ) == (5, 5, WINDOW + 0x1234, 0)
