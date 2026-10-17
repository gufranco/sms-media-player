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
    INSIDE,
    LATE,
    PAYLOAD,
    control_stamps,
    replay,
    without_guard,
)
from z80vdp import call, load_gg

from smsggmedia import console, stream

HEADER_REGION = 0x7FFF
GG_INTERNATIONAL = 0x7
WIDE_PALETTE = bytes(range(64))
FLIP = 0x82
INK_ADDRESS = 0x3C
INK_WORDS = bytes([0x00, 0x00, 0xFF, 0x0F])


@pytest.fixture(scope="module")
def built():
    return load_gg()


def wide_film() -> bytes:
    vram = bytes([stream.VRAM, 0x00, 0x10, len(PAYLOAD)]) + PAYLOAD
    register = console.TABLE_REGISTER[console.BACK_TABLE_BASE]
    close = bytes([stream.CLOSE_WIDE, register]) + WIDE_PALETTE
    return vram + close + bytes([stream.END_FRAME])


def narrow_film() -> bytes:
    register = console.TABLE_REGISTER[console.BACK_TABLE_BASE]
    return bytes([stream.CLOSE, register]) + bytes(32) + bytes([stream.END_FRAME])


class TestTheGameGearCartridge:
    def test_its_header_says_game_gear_international(self, built):
        # Arrange
        rom, _ = built

        # Act
        region = rom[HEADER_REGION] >> 4

        # Assert
        assert region == GG_INTERNATIONAL

    def test_a_wide_palette_reaches_the_data_port_after_the_payload(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        ports, _, _ = replay(built, lines, data=wide_film())

        # Assert
        assert ports.data()[len(PAYLOAD) :] == list(WIDE_PALETTE)

    def test_a_master_system_palette_run_is_refused(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        _, memory, names = replay(built, lines, data=narrow_film())

        # Assert
        assert memory.read8(names["_movie_kind"]) == BAD

    def test_the_overlay_inks_land_as_two_twelve_bit_entries(self, built):
        # Arrange
        routine = "_fmv_osd_inks"

        # Act
        vdp, _, _ = call(built, routine, gg=True)

        # Assert
        assert bytes(vdp.cram[INK_ADDRESS : INK_ADDRESS + 4]) == INK_WORDS


class TestThePanRun:
    def test_its_byte_reaches_the_stereo_port(self, built):
        # Arrange
        lines = [INSIDE]
        data = bytes([stream.PAN, 0xEF, stream.END_FRAME])

        # Act
        ports, _, _ = replay(built, lines, data=data)

        # Assert
        assert ports.pans() == [0xEF]

    def test_the_tones_after_it_still_reach_the_sound_port(self, built):
        # Arrange
        lines = [INSIDE]
        data = bytes([stream.PAN, 0xFE, stream.PSG, 1, 0x9F, stream.END_FRAME])

        # Act
        ports, _, _ = replay(built, lines, data=data)

        # Assert
        assert [value for _, value in ports.sound()] == [0x9F]

    def test_silencing_the_psg_centres_every_channel(self, built):
        # Arrange
        routine = "_fmv_psg_silence"

        # Act
        vdp, _, _ = call(built, routine, gg=True)

        # Assert
        assert vdp.pans == [0xFF]


class TestTheWidePaletteKeepsToTheBlank:
    @pytest.mark.parametrize("line", [ACTIVE, 0x00, 0xBF, 0xE0, LATE, 0xFF])
    def test_the_palette_and_the_flip_wait_outside_the_window(self, built, line):
        # Arrange
        lines = [line]

        # Act
        ports, _, _ = replay(built, lines, data=wide_film())

        # Assert
        control = [value for _, port, value in ports.writes if port == CONTROL_PORT]
        assert (ports.data(), FLIP in control) == (list(PAYLOAD), False)

    def test_without_the_guard_all_64_bytes_land_in_the_active_display(self, built):
        # Arrange
        rom, names = built
        unguarded = (without_guard(rom), names)

        # Act
        ports, _, _ = replay(unguarded, [ACTIVE], data=wide_film())

        # Assert
        assert ports.data() == list(PAYLOAD) + list(WIDE_PALETTE)

    def test_the_64_palette_bytes_keep_the_blanking_floor(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        ports, _, _ = replay(built, lines, data=wide_film())

        # Assert
        stamps = [cycle for cycle, port, _ in ports.writes if port == DATA_PORT]
        palette = stamps[len(PAYLOAD) : len(PAYLOAD) + len(WIDE_PALETTE)]
        assert min(later - earlier for earlier, later in pairwise(palette)) >= BLANK_FLOOR

    def test_every_control_write_keeps_the_active_display_floor(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        ports, _, _ = replay(built, lines, data=wide_film())

        # Assert
        stamps = control_stamps(ports)
        assert min(later - earlier for earlier, later in pairwise(stamps)) >= ACTIVE_FLOOR
