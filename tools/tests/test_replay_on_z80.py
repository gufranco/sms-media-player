from __future__ import annotations

from itertools import pairwise

import pytest
from replayz80 import (
    ACTIVE,
    ACTIVE_FLOOR,
    BAD,
    BLANK_FLOOR,
    CONTROL_PORT,
    DATA_PORT,
    FIRST_BANK,
    INSIDE,
    LATE,
    PALETTE,
    PAYLOAD,
    RETIRED_KINDS,
    WINDOW,
    control_stamps,
    cursor_of,
    replay,
    without_guard,
    word_at,
)
from z80vdp import load

from smsggmedia import console, stream


@pytest.fixture(scope="module")
def built():
    return load()


class TestInsideTheWindow:
    def test_the_payload_reaches_the_data_port_in_order(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        ports, _, _ = replay(built, lines)

        # Assert
        assert ports.data()[: len(PAYLOAD)] == list(PAYLOAD)

    def test_the_palette_follows_the_payload(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        ports, _, _ = replay(built, lines)

        # Assert
        assert ports.data()[len(PAYLOAD) :] == list(PALETTE)

    def test_the_closing_run_selects_the_other_table(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        ports, _, _ = replay(built, lines)

        # Assert
        control = [value for _, port, value in ports.writes if port == CONTROL_PORT]
        assert [console.TABLE_REGISTER[console.BACK_TABLE_BASE], 0x82] == control[2:4]

    def test_payload_bytes_keep_the_active_display_floor(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        ports, _, _ = replay(built, lines)

        # Assert
        stamps = [cycle for cycle, port, _ in ports.writes if port == DATA_PORT]
        assert (
            min(after - before for before, after in pairwise(stamps[: len(PAYLOAD)]))
            >= ACTIVE_FLOOR
        )

    def test_palette_bytes_keep_the_blanking_floor(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        ports, _, _ = replay(built, lines)

        # Assert
        stamps = [cycle for cycle, port, _ in ports.writes if port == DATA_PORT]
        assert (
            min(after - before for before, after in pairwise(stamps[len(PAYLOAD) :])) >= BLANK_FLOOR
        )

    def test_the_frame_completes(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        _, memory, names = replay(built, lines)

        # Assert
        assert memory.read8(names["_movie_kind"]) == stream.END_FRAME


class TestControlPortSpacing:
    def test_every_control_write_keeps_the_active_display_floor(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        ports, _, _ = replay(built, lines)

        # Assert
        stamps = control_stamps(ports)
        assert min(after - before for before, after in pairwise(stamps)) >= ACTIVE_FLOOR


class TestTheGuardIsWhatHoldsTheWindow:
    def test_without_the_guard_the_palette_lands_in_the_active_display(self, built):
        # Arrange
        rom, names = built
        unguarded = (without_guard(rom), names)

        # Act
        ports, _, _ = replay(unguarded, [ACTIVE])

        # Assert
        assert ports.data() == list(PAYLOAD) + list(PALETTE)


class TestOutsideTheWindow:
    @pytest.mark.parametrize("line", [ACTIVE, 0x00, 0xBF, 0xE0, LATE, 0xFF])
    def test_the_palette_and_the_flip_wait_for_the_blank(self, built, line):
        # Arrange
        lines = [line]

        # Act
        ports, _, _ = replay(built, lines)

        # Assert
        control = [value for _, port, value in ports.writes if port == CONTROL_PORT]
        assert ports.data() == list(PAYLOAD)
        assert 0x82 not in control

    def test_the_closing_run_is_left_for_the_next_field(self, built):
        # Arrange
        lines = [ACTIVE]

        # Act
        _, memory, names = replay(built, lines)

        # Assert
        assert cursor_of(memory, names) == WINDOW + 4 + len(PAYLOAD)

    def test_a_deferred_field_completes_no_frame(self, built):
        # Arrange
        lines = [ACTIVE]

        # Act
        _, memory, names = replay(built, lines)

        # Assert
        assert memory.read8(names["_movie_kind"]) == stream.END_CHUNK

    def test_a_deferred_field_is_counted(self, built):
        # Arrange
        lines = [ACTIVE]

        # Act
        _, memory, names = replay(built, lines)

        # Assert
        assert word_at(memory, names["_movie_defers"]) == 1

    def test_a_field_inside_the_window_is_not_counted(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        _, memory, names = replay(built, lines)

        # Assert
        assert word_at(memory, names["_movie_defers"]) == 0


class TestACorruptStream:
    @pytest.mark.parametrize("kind", RETIRED_KINDS)
    def test_an_unknown_run_kind_stops_the_replay(self, built, kind):
        # Arrange
        data = bytes([kind, 2, 0, 0x10, 1])

        # Act
        _, memory, names = replay(built, [INSIDE], data=data)

        # Assert
        assert memory.read8(names["_movie_kind"]) == BAD

    @pytest.mark.parametrize("kind", RETIRED_KINDS)
    def test_an_unknown_run_kind_writes_nothing(self, built, kind):
        # Arrange
        data = bytes([kind, 2, 0, 0x10, 1])

        # Act
        ports, _, _ = replay(built, [INSIDE], data=data)

        # Assert
        assert ports.writes == []

    @pytest.mark.parametrize("kind", RETIRED_KINDS)
    def test_an_unknown_run_kind_leaves_the_cursor_on_it(self, built, kind):
        # Arrange
        data = bytes([kind])

        # Act
        _, memory, names = replay(built, [INSIDE], data=data)

        # Assert
        assert cursor_of(memory, names) == WINDOW

    def test_a_bank_marker_past_the_last_bank_stops_the_replay(self, built):
        # Arrange
        data = bytes([stream.NEXT_BANK])

        # Act
        _, memory, names = replay(built, [INSIDE], data=data)

        # Assert
        assert (memory.read8(names["_movie_kind"]), memory.read8(names["_movie_bank"])) == (
            BAD,
            FIRST_BANK,
        )

    def test_a_bank_marker_inside_the_film_moves_on(self, built):
        # Arrange
        data = bytes([stream.NEXT_BANK])

        # Act
        _, memory, names = replay(built, [INSIDE], data=data, banks=2)

        # Assert
        assert memory.read8(names["_movie_bank"]) == FIRST_BANK + 1
