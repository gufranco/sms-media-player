from __future__ import annotations

import pytest

from smsmedia import target


class TestTheMasterSystem:
    def test_it_draws_the_whole_raster_in_cells(self):
        # Arrange
        console = target.MASTER_SYSTEM

        # Act
        cells = (console.columns, console.rows)

        # Assert
        assert cells == (32, 24)

    def test_it_has_four_levels_a_channel_in_one_cram_byte(self):
        # Arrange
        console = target.MASTER_SYSTEM

        # Act
        colour = (console.channel_levels, console.cram_entry_bytes)

        # Assert
        assert colour == (4, 1)

    def test_its_header_says_master_system_export(self):
        # Arrange
        console = target.MASTER_SYSTEM

        # Act
        header = (console.region, console.extension)

        # Assert
        assert header == (0x4, ".sms")


class TestTheGameGear:
    def test_it_draws_the_window_its_panel_shows(self):
        # Arrange
        console = target.GAME_GEAR

        # Act
        cells = (console.columns, console.rows)

        # Assert
        assert cells == (20, 18)

    def test_it_writes_two_cram_bytes_an_entry_in_its_own_close_run(self):
        # Arrange
        console = target.GAME_GEAR

        # Act
        palette = (console.cram_entry_bytes, console.close_kind)

        # Assert
        assert palette == (2, 0x07)

    def test_its_header_says_game_gear_international(self):
        # Arrange
        console = target.GAME_GEAR

        # Act
        header = (console.region, console.extension)

        # Assert
        assert header == (0x7, ".gg")

    def test_the_master_system_keeps_its_close_run(self):
        # Arrange
        console = target.MASTER_SYSTEM

        # Act
        kind = console.close_kind

        # Assert
        assert kind == 0x05


class TestStereo:
    def test_only_the_game_gear_routes_channels_left_and_right(self):
        # Arrange
        consoles = (target.MASTER_SYSTEM, target.GAME_GEAR)

        # Act
        stereo = [console.stereo for console in consoles]

        # Assert
        assert stereo == [False, True]


class TestNamed:
    def test_a_known_name_gives_its_target(self):
        # Arrange
        name = "sms"

        # Act
        found = target.named(name)

        # Assert
        assert found is target.MASTER_SYSTEM

    def test_an_unknown_name_is_refused_with_the_known_ones(self):
        # Arrange
        name = "nes"

        # Act
        with pytest.raises(ValueError) as refused:
            target.named(name)

        # Assert
        assert str(refused.value) == "no target named 'nes'; the targets are gg, sms"

    def test_the_default_is_the_master_system(self):
        # Arrange
        default = target.DEFAULT

        # Act
        name = default.name

        # Assert
        assert name == "sms"
