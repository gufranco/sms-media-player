from __future__ import annotations

import re
from itertools import pairwise

import pytest
from replayz80 import (
    ACTIVE,
    ACTIVE_FLOOR,
    ASSERT_COLOUR,
    ASSERT_LINE,
    BACKDROP_ENTRY,
    BAD,
    BANK_END,
    CONTROL_PORT,
    DATA_PORT,
    FIRST_BANK,
    INK_ADDRESS,
    INSIDE,
    OVERLAY_INKS,
    PALETTE,
    PAYLOAD,
    PSG_ATTENUATE_ALL,
    SOUND_FLOOR,
    SOUND_PORT,
    SOUND_WRITES,
    palette_writes,
    replay,
    run_until_halted,
    silence,
    sounded_film,
)
from z80vdp import ROOT, call, load

from smsggmedia import stream


@pytest.fixture(scope="module")
def built():
    return load()


VERSION_HEADER = ROOT / "include" / "fmv" / "version.h"

SDSC_SIGNATURE = 0x7FE0


def bcd(value: int) -> int:
    return (value // 10) * 16 + value % 10


class TestTheOverlayInks:
    def test_with_the_overlay_up_black_and_white_follow_the_palette(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        ports, _, _ = replay(built, lines, inks=True)

        # Assert
        assert ports.data() == list(PAYLOAD) + list(PALETTE) + OVERLAY_INKS

    def test_they_land_on_the_last_two_sprite_palette_entries(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        ports, _, _ = replay(built, lines, inks=True)

        # Assert
        control = [value for _, port, value in ports.writes if port == CONTROL_PORT]
        assert control[-2:] == INK_ADDRESS

    def test_without_the_overlay_nothing_follows_the_palette(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        ports, _, _ = replay(built, lines, inks=False)

        # Assert
        assert ports.data() == list(PAYLOAD) + list(PALETTE)

    def test_a_deferred_field_writes_no_inks(self, built):
        # Arrange
        lines = [ACTIVE]

        # Act
        ports, _, _ = replay(built, lines, inks=True)

        # Assert
        assert ports.data() == list(PAYLOAD)

    def test_every_write_after_the_palette_keeps_the_active_display_floor(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        ports, _, _ = replay(built, lines, inks=True)

        # Assert
        stamps = [cycle for cycle, port, _ in ports.writes if port in (DATA_PORT, CONTROL_PORT)]
        after = stamps[len(stamps) - len(OVERLAY_INKS) - len(INK_ADDRESS) - 1 :]
        assert min(later - earlier for earlier, later in pairwise(after)) >= ACTIVE_FLOOR

    def test_the_frame_still_completes(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        _, memory, names = replay(built, lines, inks=True)

        # Assert
        assert memory.read8(names["_movie_kind"]) == stream.END_FRAME


class TestTheSoundChipIsSilenced:
    def test_every_channel_is_attenuated_fully_on_the_psg_port(self, built):
        # Arrange
        expected = [(SOUND_PORT, value) for value in PSG_ATTENUATE_ALL]

        # Act
        speaker = silence(built)

        # Assert
        assert speaker.writes == expected


class TestAnAssertionHalt:
    def test_the_halt_colour_lands_on_the_backdrop_entry(self, built):
        # Arrange
        expected = (BACKDROP_ENTRY, ASSERT_COLOUR)

        # Act
        speaker = run_until_halted(built, "_fmv_assert_fail", pokes={}, hl=ASSERT_LINE)

        # Assert
        assert palette_writes(speaker)[0] == expected

    def test_a_cursor_past_the_bank_window_halts_before_the_replay(self, built):
        # Arrange
        pokes = {"_movie_cursor": BANK_END, "_movie_bank": FIRST_BANK}

        # Act
        speaker = run_until_halted(built, "_fmv_movie_chunk", pokes=pokes)

        # Assert
        assert [entry for entry, _ in palette_writes(speaker)][:1] == [BACKDROP_ENTRY]


class TestTheRomHeader:
    def test_the_sdsc_version_is_the_one_the_release_stamps(self, built):
        # Arrange
        rom, _ = built
        declared = re.search(r'#define FMV_VERSION "(\d+)\.(\d+)\.\d+"', VERSION_HEADER.read_text())

        # Act
        stamped = rom[SDSC_SIGNATURE : SDSC_SIGNATURE + 6]

        # Assert
        assert declared is not None
        assert stamped == b"SDSC" + bytes([bcd(int(declared[1])), bcd(int(declared[2]))])


class TestASoundRun:
    def test_the_writes_reach_the_sound_port_in_order(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        ports, _, _ = replay(built, lines, data=sounded_film())

        # Assert
        assert [value for _, value in ports.sound()] == list(SOUND_WRITES)

    def test_consecutive_sound_writes_keep_the_floor(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        ports, _, _ = replay(built, lines, data=sounded_film())

        # Assert
        stamps = [cycle for cycle, _ in ports.sound()]
        assert min(later - earlier for earlier, later in pairwise(stamps)) >= SOUND_FLOOR

    def test_the_picture_after_the_sound_still_arrives(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        ports, _, _ = replay(built, lines, data=sounded_film())

        # Assert
        assert ports.data()[: len(PAYLOAD)] == list(PAYLOAD)


class TestAMutedSoundRun:
    def test_nothing_reaches_the_sound_port(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        ports, _, _ = replay(built, lines, data=sounded_film(), muted=True)

        # Assert
        assert ports.sound() == []

    def test_the_picture_after_the_skipped_run_still_arrives(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        ports, _, _ = replay(built, lines, data=sounded_film(), muted=True)

        # Assert
        assert ports.data() == list(PAYLOAD) + list(PALETTE)


class TestAPanRunOnTheMasterSystem:
    def test_it_is_refused_as_a_kind_the_player_does_not_know(self, built):
        # Arrange
        lines = [INSIDE]
        data = bytes([stream.PAN, 0xEF, stream.END_FRAME])

        # Act
        ports, memory, names = replay(built, lines, data=data)

        # Assert
        assert (memory.read8(names["_movie_kind"]), ports.pans()) == (BAD, [])

    def test_silencing_the_psg_never_writes_the_memory_control_mirror(self, built):
        # Arrange
        routine = "_fmv_psg_silence"

        # Act
        vdp, _, _ = call(built, routine)

        # Assert
        assert vdp.pans == []
