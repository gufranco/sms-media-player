from __future__ import annotations

import pytest
from test_replay_on_z80 import BAD, INSIDE, PAYLOAD, replay
from z80vdp import call, load_gg

from smsmedia import console, stream

HEADER_REGION = 0x7FFF
GG_INTERNATIONAL = 0x7
WIDE_PALETTE = bytes(range(64))
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
