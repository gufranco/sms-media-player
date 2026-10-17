from __future__ import annotations

import re
from pathlib import Path

import pytest

from smsmedia import console

ROOT = Path(__file__).resolve().parents[2]
SCREEN_HEADER = ROOT / "include" / "fmv" / "screen.h"
CONSOLE_HEADER = ROOT / "include" / "fmv" / "console.h"
PSG_SOURCE = ROOT / "src" / "psg.s"
MAIN_SOURCE = ROOT / "src" / "main.c"
SCREEN_SOURCE = ROOT / "src" / "screen.c"

PSG_ATTENUATE_ALL = ("#0x9F", "#0xBF", "#0xDF", "#0xFF")


def define(name: str, *, header: Path = SCREEN_HEADER) -> int:
    text = header.read_text()
    found = re.search(rf"^#define\s+{name}\s+(0[xX][0-9a-fA-F]+|\d+)u?\s*$", text, re.MULTILINE)
    if found is None:
        msg = f"{name} is not defined in {header.name}"
        raise AssertionError(msg)
    return int(found.group(1), 0)


def screen(name: str) -> int:
    return define(name, header=SCREEN_HEADER)


class TestHeaderIsReadable:
    def test_the_header_exists(self):
        # Arrange
        header = SCREEN_HEADER

        # Act
        present = header.is_file()

        # Assert
        assert present is True

    def test_an_absent_define_is_reported(self):
        # Arrange
        name = "FMV_NOT_A_REAL_CONSTANT"

        # Act
        with pytest.raises(AssertionError) as refused:
            define(name)

        # Assert
        assert str(refused.value) == "FMV_NOT_A_REAL_CONSTANT is not defined in screen.h"


class TestTheSoundChipIsSilent:
    def test_every_channel_is_attenuated_fully(self):
        # Arrange
        source = PSG_SOURCE

        # Act
        text = source.read_text()

        # Assert
        assert [value for value in PSG_ATTENUATE_ALL if value in text] == list(PSG_ATTENUATE_ALL)

    def test_the_player_silences_it_before_the_screen_comes_up(self):
        # Arrange
        text = MAIN_SOURCE.read_text()

        # Act
        boot = text[text.index("static void boot(void)") :]

        # Assert
        assert -1 < boot.index("fmv_psg_silence();") < boot.index("fmv_screen_reset();")

    def test_nothing_enables_the_line_interrupt(self):
        # Arrange
        sources = sorted((ROOT / "src").glob("*.c"))

        # Act
        offenders = [
            path.name
            for path in sources
            if "SMS_setLineInterruptHandler" in path.read_text()
            or "SMS_enableLineInterrupt" in path.read_text()
        ]

        # Assert
        assert offenders == []


class TestScreenContract:
    def test_the_player_and_the_oracle_agree_on_vram(self):
        # Arrange
        expected = console.VRAM_BYTES

        # Act
        value = screen("FMV_SCREEN_VRAM_BYTES")

        # Assert
        assert value == expected

    def test_the_player_and_the_oracle_agree_on_the_name_table(self):
        # Arrange
        expected = console.NAME_TABLE_BASE

        # Act
        value = screen("FMV_SCREEN_NAME_TABLE")

        # Assert
        assert value == expected

    def test_the_player_and_the_oracle_agree_on_the_back_table(self):
        # Arrange
        expected = console.BACK_TABLE_BASE

        # Act
        value = screen("FMV_SCREEN_BACK_TABLE")

        # Assert
        assert value == expected

    def test_the_player_resets_to_the_front_table(self):
        # Arrange
        expected = console.TABLE_REGISTER[console.NAME_TABLE_BASE]

        # Act
        value = screen("FMV_SCREEN_FRONT_REGISTER")

        # Assert
        assert value == expected

    def test_the_player_clears_every_name_table_cell(self):
        # Arrange
        expected = console.NAME_TABLE_BYTES

        # Act
        value = screen("FMV_SCREEN_NAME_TABLE_BYTES")

        # Assert
        assert value == expected

    def test_the_player_and_the_oracle_agree_on_the_idle_cell(self):
        # Arrange
        expected = console.IDLE_CELL

        # Act
        value = screen("FMV_SCREEN_IDLE_CELL")

        # Assert
        assert value == expected

    def test_the_player_and_the_oracle_agree_on_the_sprite_table(self):
        # Arrange
        expected = console.SAT_BASE

        # Act
        value = screen("FMV_SCREEN_SAT")

        # Assert
        assert value == expected

    def test_the_player_parks_every_sprite(self):
        # Arrange
        expected = console.SPRITE_SLOTS

        # Act
        value = screen("FMV_SCREEN_SPRITES")

        # Assert
        assert value == expected

    def test_the_player_and_the_oracle_agree_on_the_off_screen_row(self):
        # Arrange
        expected = console.SPRITE_OFF

        # Act
        value = screen("FMV_SCREEN_SPRITE_OFF")

        # Assert
        assert value == expected

    def test_the_player_withholds_what_the_encoder_reserves(self):
        # Arrange
        expected = console.RESERVED_PATTERNS

        # Act
        value = screen("FMV_SCREEN_RESERVED")

        # Assert
        assert value == expected

    def test_the_idle_cell_points_inside_the_reservation(self):
        # Arrange
        reserved = screen("FMV_SCREEN_RESERVED")

        # Act
        idle = screen("FMV_SCREEN_IDLE_CELL")

        # Assert
        assert (idle & 0x01FF) < reserved


class TestScreenResetDoesTheWork:
    def test_the_source_exists(self):
        # Arrange
        source = SCREEN_SOURCE

        # Act
        present = source.is_file()

        # Assert
        assert present is True

    def test_the_name_table_is_filled_with_the_idle_cell(self):
        # Arrange
        call = "SMS_VRAMmemsetW(FMV_SCREEN_NAME_TABLE, FMV_SCREEN_IDLE_CELL"

        # Act
        text = SCREEN_SOURCE.read_text()

        # Assert
        assert call in text

    def test_every_sprite_is_parked_off_screen(self):
        # Arrange
        call = "SMS_VRAMmemset(FMV_SCREEN_SAT, FMV_SCREEN_SPRITE_OFF"

        # Act
        text = SCREEN_SOURCE.read_text()

        # Assert
        assert call in text

    def test_the_sprite_list_is_terminated(self):
        # Arrange
        source = SCREEN_SOURCE

        # Act
        text = source.read_text()

        # Assert
        assert "SMS_initSprites();" in text
        assert "SMS_copySpritestoSAT();" in text

    def test_both_palette_zeros_are_pinned_black(self):
        # Arrange
        source = SCREEN_SOURCE

        # Act
        text = source.read_text()

        # Assert
        assert "fmv_set_bg_colour(0u, FMV_COLOUR_BLACK);" in text
        assert "fmv_set_sprite_colour(0u, FMV_COLOUR_BLACK);" in text

    def test_nothing_else_prepares_the_screen(self):
        # Arrange
        allowed = {"screen.c", "assert.c"}

        # Act
        offenders = [
            path.name
            for path in (ROOT / "src").glob("*.c")
            if path.name not in allowed and "SMS_displayOff()" in path.read_text()
        ]

        # Assert
        assert offenders == []


class TestTheEndOfAFilm:
    def test_the_hold_is_counted_wide_enough_for_any_rate(self):
        # Arrange
        text = MAIN_SOURCE.read_text()

        # Act
        counter = re.search(
            r"(\w+) field;\n\n    for \(field = 0u; field < \((\w+)\)MOVIE_HOLD_FIELDS", text
        )

        # Assert
        assert counter is not None
        assert (counter.group(1), counter.group(2)) == ("u16", "u16")

    def test_a_fault_turns_the_screen_red_rather_than_black(self):
        # Arrange
        text = SCREEN_SOURCE.read_text()

        # Act
        fault = re.search(r"void fmv_screen_fault\(void\)\n\{\n(.*?)\n\}", text, re.DOTALL)

        # Assert
        assert fault is not None
        assert fault.group(1).strip() == "fmv_set_sprite_colour(0u, FMV_COLOUR_RED);"

    def test_the_fault_colour_is_a_red_the_console_can_show(self):
        # Arrange
        text = CONSOLE_HEADER.read_text()

        # Act
        reds = re.findall(r"^#define\s+FMV_COLOUR_RED\s+(0x[0-9A-Fa-f]+)u", text, re.MULTILINE)

        # Assert
        assert [int(red, 16) for red in reds] == [0x000F, 0b00_00_11]

    def test_the_player_shows_the_fault_only_after_a_fault(self):
        # Arrange
        text = MAIN_SOURCE.read_text()

        # Act
        guarded = "if (outcome == FMV_OUTCOME_FAULT) {\n            fmv_screen_fault();" in text

        # Assert
        assert guarded is True
