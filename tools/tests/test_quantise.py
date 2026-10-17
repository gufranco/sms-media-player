from __future__ import annotations

import numpy as np
import pytest
from fmvcore import colour, dither

from smsggmedia import lattice

SMS = lattice.MASTER_SYSTEM
GG = lattice.GAME_GEAR


class TestTheMasterSystemLevels:
    def test_the_four_levels_span_the_full_range(self):
        # Arrange
        entries = np.array([0x00, 0x15, 0x2A, 0x3F], dtype=np.uint8)

        # Act
        rgb = SMS.to_rgb(entries)

        # Assert
        assert rgb.tolist() == [[0, 0, 0], [85, 85, 85], [170, 170, 170], [255, 255, 255]]

    def test_an_entry_names_red_low_and_blue_high(self):
        # Arrange
        entries = np.array([0b00_10_01], dtype=np.uint8)

        # Act
        rgb = SMS.to_rgb(entries)

        # Assert
        assert rgb.tolist() == [[85, 170, 0]]


class TestQuantiseLevels:
    def test_black_and_white_land_on_the_end_stops(self):
        # Arrange
        rgb = np.array([[0, 0, 0], [255, 255, 255]], dtype=np.uint8)

        # Act
        result = SMS.quantise(rgb)

        # Assert
        assert result.tolist() == [[0, 0, 0], [3, 3, 3]]

    def test_a_midpoint_rounds_to_the_nearest_level(self):
        # Arrange
        rgb = np.array([[128, 85, 170]], dtype=np.uint8)

        # Act
        result = SMS.quantise(rgb)

        # Assert
        assert result.tolist() == [[2, 1, 2]]

    def test_a_flat_area_stays_flat_wherever_it_is(self):
        # Arrange
        rgb = np.full((16, 32, 3), 40, dtype=np.uint8)

        # Act
        result = SMS.quantise(rgb)

        # Assert
        assert len(np.unique(result.reshape(-1, 3), axis=0)) == 1

    def test_each_pixel_takes_the_level_nearest_itself(self):
        # Arrange
        rgb = np.full((4, 4, 3), 100, dtype=np.uint8)
        expected = np.full((4, 4, 3), 1).tolist()

        # Act
        result = SMS.quantise(rgb)

        # Assert
        assert result.tolist() == expected

    def test_an_array_without_an_rgb_axis_is_refused(self):
        # Arrange
        rgb = np.zeros((4, 2), dtype=np.uint8)

        # Act
        with pytest.raises(ValueError) as refused:
            SMS.quantise(rgb)

        # Assert
        assert str(refused.value) == "expected a trailing RGB axis, got shape (4, 2)"


class TestOrderedDither:
    def test_no_dither_rounds_to_the_nearest_level(self):
        # Arrange
        rgb = np.full((8, 8, 3), 120, dtype=np.uint8)

        # Act
        result = SMS.quantise(rgb, dither=dither.NO_DITHER)

        # Assert
        assert np.unique(result).tolist() == [1]

    def test_a_value_between_two_levels_mixes_both(self):
        # Arrange
        rgb = np.full((8, 8, 3), 128, dtype=np.uint8)

        # Act
        result = SMS.quantise(rgb, dither=1.0)

        # Assert
        assert np.unique(result).tolist() == [1, 2]

    def test_the_mix_tracks_the_value(self):
        # Arrange
        rgb = np.full((8, 8, 3), 100, dtype=np.uint8)

        # Act
        result = SMS.quantise(rgb, dither=1.0)

        # Assert
        assert float(result.mean()) == pytest.approx(100 * 3 / 255, abs=0.07)

    def test_the_pattern_repeats_inside_every_tile(self):
        # Arrange
        rgb = np.full((16, 16, 3), 140, dtype=np.uint8)

        # Act
        result = SMS.quantise(rgb, dither=1.0)

        # Assert
        assert np.array_equal(result[:8, :8], result[8:, 8:])

    def test_a_level_on_the_grid_is_left_alone(self):
        # Arrange
        rgb = np.full((8, 8, 3), 170, dtype=np.uint8)

        # Act
        result = SMS.quantise(rgb, dither=1.0)

        # Assert
        assert np.unique(result).tolist() == [2]

    def test_a_strength_past_half_a_step_is_refused(self):
        # Arrange
        rgb = np.zeros((8, 8, 3), dtype=np.uint8)
        strength = dither.MAX_DITHER + 0.5

        # Act
        with pytest.raises(ValueError) as refused:
            SMS.quantise(rgb, dither=strength)

        # Assert
        assert str(refused.value) == "a dither strength lies between 0 and 1, got 1.5"

    def test_the_largest_strength_is_accepted(self):
        # Arrange
        rgb = np.full((8, 8, 3), 128, dtype=np.uint8)

        # Act
        result = SMS.quantise(rgb, dither=dither.MAX_DITHER)

        # Assert
        assert np.unique(result).tolist() == [1, 2]

    def test_a_negative_strength_is_refused(self):
        # Arrange
        rgb = np.zeros((8, 8, 3), dtype=np.uint8)

        # Act
        with pytest.raises(ValueError) as refused:
            SMS.quantise(rgb, dither=-0.5)

        # Assert
        assert str(refused.value) == "a dither strength lies between 0 and 1, got -0.5"

    def test_dithering_needs_a_picture(self):
        # Arrange
        rgb = np.zeros((4, 3), dtype=np.uint8)

        # Act
        with pytest.raises(ValueError) as refused:
            SMS.quantise(rgb, dither=1.0)

        # Assert
        assert str(refused.value) == "dithering needs a height and width axis, got shape (4, 3)"


class TestPackColour:
    def test_the_layout_puts_red_low_and_blue_high(self):
        # Arrange
        levels = np.array([[3, 0, 0], [0, 3, 0], [0, 0, 3]], dtype=np.uint8)

        # Act
        result = SMS.pack(levels)

        # Assert
        assert result.tolist() == [0x03, 0x0C, 0x30]

    def test_the_top_two_bits_are_never_set(self):
        # Arrange
        levels = np.array([[3, 3, 3]], dtype=np.uint8)

        # Act
        result = SMS.pack(levels)

        # Assert
        assert result.tolist() == [0x3F]

    def test_a_level_above_the_channel_maximum_is_refused(self):
        # Arrange
        levels = np.array([[4, 0, 0]], dtype=np.uint8)

        # Act
        with pytest.raises(ValueError) as refused:
            SMS.pack(levels)

        # Assert
        assert str(refused.value) == "channel levels must lie in 0 to 3"


class TestUnpackColour:
    def test_unpacking_reverses_packing_across_the_whole_space(self):
        # Arrange
        every = np.arange(64, dtype=np.uint8)

        # Act
        result = SMS.pack(SMS.unpack(every))

        # Assert
        assert result.tolist() == every.tolist()


class TestReadingCram:
    def test_a_game_gear_word_reads_back_as_its_colour(self):
        # Arrange
        cram = bytes([0x05, 0x0A])

        # Act
        rgb = GG.to_rgb(GG.from_cram(cram))

        # Assert
        assert rgb.tolist() == [[85, 0, 170]]

    def test_a_master_system_byte_reads_back_as_its_colour(self):
        # Arrange
        cram = bytes([0x3F, 0x03])

        # Act
        rgb = SMS.to_rgb(SMS.from_cram(cram))

        # Assert
        assert rgb.tolist() == [[255, 255, 255], [255, 0, 0]]

    def test_an_odd_number_of_game_gear_bytes_is_refused(self):
        # Arrange
        cram = bytes(3)

        # Act
        with pytest.raises(ValueError) as refused:
            GG.from_cram(cram)

        # Assert
        assert str(refused.value) == "a 4096-colour palette holds 2 bytes an entry, got 3"


class TestTheFloor:
    def test_a_picture_made_of_console_colours_sits_on_the_floor(self):
        # Arrange
        picture = SMS.to_rgb(np.arange(64, dtype=np.uint8)).reshape(8, 8, 3)

        # Act
        floor = SMS.floor(picture)

        # Assert
        assert floor == pytest.approx(0.0, abs=1e-6)

    def test_the_game_gear_floor_lies_below_the_master_system_floor(self):
        # Arrange
        rng = np.random.default_rng(9)
        picture = rng.integers(0, 256, size=(40, 40, 3), dtype=np.uint8)

        # Act
        floors = (GG.floor(picture), SMS.floor(picture))

        # Assert
        assert floors[0] < floors[1]


class TestNearestColour:
    def test_black_and_white_map_to_the_end_stops(self):
        # Arrange
        rgb = np.array([[[0, 0, 0], [255, 255, 255]]], dtype=np.uint8)

        # Act
        result = SMS.nearest(rgb)

        # Assert
        assert result.tolist() == [[0x00, 0x3F]]

    def test_every_result_is_a_console_colour(self):
        # Arrange
        rng = np.random.default_rng(41)
        rgb = rng.integers(0, 256, size=(8, 8, 3), dtype=np.uint8)

        # Act
        result = SMS.nearest(rgb)

        # Assert
        assert int(result.max()) < 64

    def test_it_beats_per_channel_rounding_in_oklab(self):
        # Arrange
        rng = np.random.default_rng(42)
        rgb = rng.integers(0, 256, size=(16, 16, 3), dtype=np.uint8)
        lab = SMS.oklab()
        source = colour.srgb_to_oklab(rgb.astype(np.float32) / 255.0).reshape(-1, 3)
        rounded = SMS.pack(SMS.quantise(rgb)).reshape(-1)
        rounded_error = source - lab[rounded]

        # Act
        result = SMS.nearest(rgb).reshape(-1)

        # Assert
        nearest_error = source - lab[result]
        assert float((nearest_error * nearest_error).sum()) <= float(
            (rounded_error * rounded_error).sum()
        )

    def test_the_shape_is_preserved(self):
        # Arrange
        rgb = np.zeros((4, 7, 3), dtype=np.uint8)

        # Act
        result = SMS.nearest(rgb)

        # Assert
        assert result.shape == (4, 7)

    def test_chroma_weight_can_change_the_choice(self):
        # Arrange
        rgb = np.array([[[0, 0, 204]]], dtype=np.uint8)
        plain = SMS.nearest(rgb, chroma_weight=1.0)

        # Act
        weighted = SMS.nearest(rgb, chroma_weight=0.1)

        # Assert
        assert plain.tolist() != weighted.tolist()

    def test_a_game_gear_answer_is_a_cram_word(self):
        # Arrange
        rgb = np.array([[255, 255, 255]], dtype=np.uint8)

        # Act
        result = GG.nearest(rgb)

        # Assert
        assert result.tolist() == [0x0FFF]

    def test_an_array_without_an_rgb_axis_is_refused(self):
        # Arrange
        rgb = np.zeros((4, 2), dtype=np.uint8)

        # Act
        with pytest.raises(ValueError) as refused:
            SMS.nearest(rgb)

        # Assert
        assert str(refused.value) == "expected a trailing RGB axis, got shape (4, 2)"
