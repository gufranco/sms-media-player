from __future__ import annotations

import numpy as np
import pytest

from smsggmedia import lattice, smscolor, target

SMS = lattice.MASTER_SYSTEM
GG = lattice.GAME_GEAR


class TestTheMasterSystemLattice:
    def test_it_renders_every_colour_as_the_colour_module_does(self):
        # Arrange
        index = np.arange(64, dtype=np.uint8)

        # Act
        rgb = SMS.to_rgb(index)

        # Assert
        assert np.array_equal(rgb, smscolor.colour_to_rgb(index))

    def test_it_packs_levels_as_the_colour_module_does(self):
        # Arrange
        levels = SMS.unpack(np.arange(64, dtype=np.uint8))

        # Act
        packed = SMS.pack(levels)

        # Assert
        assert np.array_equal(packed, smscolor.pack_colour(levels))

    def test_its_oklab_table_matches_the_colour_module(self):
        # Arrange
        weight = 0.5

        # Act
        lab = SMS.oklab(weight)

        # Assert
        assert np.allclose(lab, smscolor.oklab_palette(weight))

    def test_its_cram_holds_one_byte_an_entry(self):
        # Arrange
        entries = np.array([0x3F, 0x03], dtype=np.uint8)

        # Act
        cram = SMS.cram_bytes(entries)

        # Assert
        assert cram == bytes([0x3F, 0x03])


class TestTheGameGearLattice:
    def test_it_has_four_thousand_and_ninety_six_colours(self):
        # Arrange
        console = GG

        # Act
        count = console.count

        # Assert
        assert count == 4096

    def test_white_packs_to_every_nibble_lit(self):
        # Arrange
        levels = np.array([15, 15, 15], dtype=np.uint8)

        # Act
        packed = GG.pack(levels)

        # Assert
        assert int(packed) == 0x0FFF

    def test_a_colour_index_is_its_cram_word(self):
        # Arrange
        entries = np.array([0x0FFF, 0x000F, 0x0A50], dtype=np.uint16)

        # Act
        cram = GG.cram_bytes(entries)

        # Assert
        assert cram == bytes([0xFF, 0x0F, 0x0F, 0x00, 0x50, 0x0A])

    def test_each_level_lands_on_a_seventeenth_of_full_scale(self):
        # Arrange
        levels = np.array([[1, 8, 15]], dtype=np.uint8)

        # Act
        rgb = GG.to_rgb(GG.pack(levels))

        # Assert
        assert rgb.tolist() == [[17, 136, 255]]

    def test_quantising_keeps_sixteen_steps_of_grey(self):
        # Arrange
        ramp = np.repeat(np.arange(256, dtype=np.uint8)[None, :, None], 3, axis=2)

        # Act
        levels = GG.quantise(ramp)

        # Assert
        assert len(np.unique(levels[..., 0])) == 16

    def test_a_target_names_its_lattice(self):
        # Arrange
        console = target.GAME_GEAR

        # Act
        found = lattice.for_target(console)

        # Assert
        assert found is GG

    def test_a_level_outside_the_lattice_is_refused(self):
        # Arrange
        levels = np.array([16, 0, 0], dtype=np.uint8)

        # Act
        with pytest.raises(ValueError) as refused:
            GG.pack(levels)

        # Assert
        assert str(refused.value) == "channel levels must lie in 0 to 15"
