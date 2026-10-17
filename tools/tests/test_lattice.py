from __future__ import annotations

import numpy as np
import pytest

from smsggmedia import lattice, target

SMS = lattice.MASTER_SYSTEM
GG = lattice.GAME_GEAR


class TestTheMasterSystemLattice:
    def test_it_has_sixty_four_colours(self):
        # Arrange
        console = SMS

        # Act
        count = console.count

        # Assert
        assert count == 64

    def test_its_oklab_table_has_a_coordinate_for_every_colour(self):
        # Arrange
        expected = (64, 3)

        # Act
        lab = SMS.oklab()

        # Assert
        assert lab.shape == expected

    def test_the_chroma_weight_scales_only_the_colour_axes(self):
        # Arrange
        full = SMS.oklab(1.0)

        # Act
        halved = SMS.oklab(0.5)

        # Assert
        assert np.allclose(halved, full * np.array([1.0, 0.5, 0.5], dtype=np.float32))

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


class TestRefusals:
    def test_levels_that_do_not_divide_a_byte_evenly_are_refused(self):
        # Arrange
        levels = 3

        # Act
        with pytest.raises(ValueError) as refused:
            lattice.Lattice(levels)

        # Assert
        assert str(refused.value) == "3 levels do not divide a byte into equal steps"

    def test_levels_without_a_trailing_rgb_axis_are_refused(self):
        # Arrange
        levels = np.array([1, 2], dtype=np.uint8)

        # Act
        with pytest.raises(ValueError) as refused:
            GG.pack(levels)

        # Assert
        assert str(refused.value) == "expected a trailing RGB axis, got shape (2,)"

    def test_a_negative_chroma_weight_is_refused(self):
        # Arrange
        weight = -0.5

        # Act
        with pytest.raises(ValueError) as refused:
            GG.oklab(weight)

        # Assert
        assert str(refused.value) == "chroma weight must not be negative"


class TestReuseOnEachLattice:
    def test_a_master_system_threshold_is_taken_as_given(self):
        # Arrange
        console = SMS

        # Act
        scale = console.reuse_scale

        # Assert
        assert scale == 1.0

    def test_a_game_gear_threshold_shrinks_with_the_square_of_its_finer_step(self):
        # Arrange
        console = GG

        # Act
        scale = console.reuse_scale

        # Assert
        assert scale == pytest.approx(1 / 25)

    def test_only_the_wide_lattice_guards_texture(self):
        # Arrange
        consoles = (SMS, GG)

        # Act
        guards = [console.reuse_contrast for console in consoles]

        # Assert
        assert guards == [0.0, 0.5]
