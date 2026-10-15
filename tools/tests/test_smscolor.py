import numpy as np
import pytest

from smsmovie import smscolor


class TestLevelToByte:
    def test_the_four_levels_span_the_full_range(self):
        # Arrange
        levels = np.array([0, 1, 2, 3], dtype=np.uint8)

        # Act
        result = smscolor.level_to_byte(levels)

        # Assert
        assert result.tolist() == [0, 85, 170, 255]

    def test_a_level_above_the_channel_maximum_is_refused(self):
        # Arrange
        levels = np.array([4], dtype=np.uint8)

        # Act
        with pytest.raises(ValueError) as refused:
            smscolor.level_to_byte(levels)

        # Assert
        assert str(refused.value) == "channel levels must lie in 0 to 3"


class TestQuantiseLevels:
    def test_black_and_white_land_on_the_end_stops(self):
        # Arrange
        rgb = np.array([[0, 0, 0], [255, 255, 255]], dtype=np.uint8)

        # Act
        result = smscolor.quantise_levels(rgb)

        # Assert
        assert result.tolist() == [[0, 0, 0], [3, 3, 3]]

    def test_a_midpoint_rounds_to_the_nearest_level(self):
        # Arrange
        rgb = np.array([[128, 85, 170]], dtype=np.uint8)

        # Act
        result = smscolor.quantise_levels(rgb)

        # Assert
        assert result.tolist() == [[2, 1, 2]]

    def test_a_flat_area_stays_flat_wherever_it_is(self):
        # Arrange
        rgb = np.full((16, 32, 3), 40, dtype=np.uint8)

        # Act
        result = smscolor.quantise_levels(rgb)

        # Assert
        assert len(np.unique(result.reshape(-1, 3), axis=0)) == 1

    def test_each_pixel_takes_the_level_nearest_itself(self):
        # Arrange
        rgb = np.full((4, 4, 3), 100, dtype=np.uint8)
        expected = np.full((4, 4, 3), 1).tolist()

        # Act
        result = smscolor.quantise_levels(rgb)

        # Assert
        assert result.tolist() == expected

    def test_an_array_without_an_rgb_axis_is_refused(self):
        # Arrange
        rgb = np.zeros((4, 2), dtype=np.uint8)

        # Act
        with pytest.raises(ValueError) as refused:
            smscolor.quantise_levels(rgb)

        # Assert
        assert str(refused.value) == "expected a trailing RGB axis, got shape (4, 2)"


class TestOrderedDither:
    def test_no_dither_rounds_to_the_nearest_level(self):
        # Arrange
        rgb = np.full((8, 8, 3), 120, dtype=np.uint8)

        # Act
        result = smscolor.quantise_levels(rgb, dither=smscolor.NO_DITHER)

        # Assert
        assert np.unique(result).tolist() == [1]

    def test_a_value_between_two_levels_mixes_both(self):
        # Arrange
        rgb = np.full((8, 8, 3), 128, dtype=np.uint8)

        # Act
        result = smscolor.quantise_levels(rgb, dither=1.0)

        # Assert
        assert np.unique(result).tolist() == [1, 2]

    def test_the_mix_tracks_the_value(self):
        # Arrange
        rgb = np.full((8, 8, 3), 100, dtype=np.uint8)

        # Act
        result = smscolor.quantise_levels(rgb, dither=1.0)

        # Assert
        assert float(result.mean()) == pytest.approx(100 * 3 / 255, abs=0.07)

    def test_the_pattern_repeats_inside_every_tile(self):
        # Arrange
        rgb = np.full((16, 16, 3), 140, dtype=np.uint8)

        # Act
        result = smscolor.quantise_levels(rgb, dither=1.0)

        # Assert
        assert np.array_equal(result[:8, :8], result[8:, 8:])

    def test_a_level_on_the_grid_is_left_alone(self):
        # Arrange
        rgb = np.full((8, 8, 3), 170, dtype=np.uint8)

        # Act
        result = smscolor.quantise_levels(rgb, dither=1.0)

        # Assert
        assert np.unique(result).tolist() == [2]

    def test_a_strength_past_half_a_step_is_refused(self):
        # Arrange
        rgb = np.zeros((8, 8, 3), dtype=np.uint8)
        strength = smscolor.MAX_DITHER + 0.5

        # Act
        with pytest.raises(ValueError) as refused:
            smscolor.quantise_levels(rgb, dither=strength)

        # Assert
        assert str(refused.value) == "a dither strength must be at most 1, past it a level moves"

    def test_the_largest_strength_is_accepted(self):
        # Arrange
        rgb = np.full((8, 8, 3), 128, dtype=np.uint8)

        # Act
        result = smscolor.quantise_levels(rgb, dither=smscolor.MAX_DITHER)

        # Assert
        assert np.unique(result).tolist() == [1, 2]

    def test_a_negative_strength_is_refused(self):
        # Arrange
        rgb = np.zeros((8, 8, 3), dtype=np.uint8)

        # Act
        with pytest.raises(ValueError) as refused:
            smscolor.quantise_levels(rgb, dither=-0.5)

        # Assert
        assert str(refused.value) == "a dither strength must not be negative"

    def test_dithering_needs_a_picture(self):
        # Arrange
        rgb = np.zeros((4, 3), dtype=np.uint8)

        # Act
        with pytest.raises(ValueError) as refused:
            smscolor.quantise_levels(rgb, dither=1.0)

        # Assert
        assert str(refused.value) == "dithering needs a height and width axis, got shape (4, 3)"


class TestPackColour:
    def test_the_layout_puts_red_low_and_blue_high(self):
        # Arrange
        levels = np.array([[3, 0, 0], [0, 3, 0], [0, 0, 3]], dtype=np.uint8)

        # Act
        result = smscolor.pack_colour(levels)

        # Assert
        assert result.tolist() == [0x03, 0x0C, 0x30]

    def test_the_top_two_bits_are_never_set(self):
        # Arrange
        levels = np.array([[3, 3, 3]], dtype=np.uint8)

        # Act
        result = smscolor.pack_colour(levels)

        # Assert
        assert result.tolist() == [0x3F]

    def test_a_level_above_the_channel_maximum_is_refused(self):
        # Arrange
        levels = np.array([[4, 0, 0]], dtype=np.uint8)

        # Act
        with pytest.raises(ValueError) as refused:
            smscolor.pack_colour(levels)

        # Assert
        assert str(refused.value) == "channel levels must lie in 0 to 3"


class TestUnpackColour:
    def test_unpacking_reverses_packing_across_the_whole_space(self):
        # Arrange
        every = np.arange(smscolor.COLOUR_COUNT, dtype=np.uint8)

        # Act
        result = smscolor.pack_colour(smscolor.unpack_colour(every))

        # Assert
        assert result.tolist() == every.tolist()


class TestColourToRgb:
    def test_the_darkest_and_brightest_entries_are_black_and_white(self):
        # Arrange
        entries = np.array([0x00, 0x3F], dtype=np.uint8)

        # Act
        result = smscolor.colour_to_rgb(entries)

        # Assert
        assert result.tolist() == [[0, 0, 0], [255, 255, 255]]


class TestSrgbToOklab:
    def test_black_sits_at_the_origin(self):
        # Arrange
        rgb = np.zeros((1, 3), dtype=np.float32)

        # Act
        result = smscolor.srgb_to_oklab(rgb)

        # Assert
        assert result[0, 0] == pytest.approx(0.0, abs=1e-6)

    def test_white_has_unit_lightness_and_no_chroma(self):
        # Arrange
        rgb = np.ones((1, 3), dtype=np.float32)

        # Act
        result = smscolor.srgb_to_oklab(rgb)

        # Assert
        assert result[0, 0] == pytest.approx(1.0, abs=1e-3)
        assert result[0, 1] == pytest.approx(0.0, abs=1e-3)
        assert result[0, 2] == pytest.approx(0.0, abs=1e-3)

    def test_an_array_without_an_rgb_axis_is_refused(self):
        # Arrange
        rgb = np.zeros((4, 2), dtype=np.float32)

        # Act
        with pytest.raises(ValueError) as refused:
            smscolor.srgb_to_oklab(rgb)

        # Assert
        assert str(refused.value) == "expected a trailing RGB axis, got shape (4, 2)"


class TestOklabPalette:
    def test_every_console_colour_has_a_coordinate(self):
        # Arrange
        expected_shape = (smscolor.COLOUR_COUNT, 3)

        # Act
        result = smscolor.oklab_palette()

        # Assert
        assert result.shape == expected_shape

    def test_the_chroma_weight_scales_only_the_colour_axes(self):
        # Arrange
        full = smscolor.oklab_palette(1.0)

        # Act
        halved = smscolor.oklab_palette(0.5)

        # Assert
        assert np.allclose(halved[:, 0], full[:, 0])
        assert np.allclose(halved[:, 1], full[:, 1] * 0.5)
        assert np.allclose(halved[:, 2], full[:, 2] * 0.5)

    def test_a_negative_chroma_weight_is_refused(self):
        # Arrange
        weight = -0.1

        # Act
        with pytest.raises(ValueError) as refused:
            smscolor.oklab_palette(weight)

        # Assert
        assert str(refused.value) == "chroma weight must not be negative"


class TestConstants:
    def test_cram_holds_two_palettes_of_sixteen(self):
        # Arrange
        expected = (16, 2, 32)

        # Act
        result = (smscolor.PALETTE_ENTRIES, smscolor.PALETTE_COUNT, smscolor.CRAM_BYTES)

        # Assert
        assert result == expected

    def test_two_bits_a_channel_gives_sixty_four_colours(self):
        # Arrange
        expected = 64

        # Act
        result = smscolor.COLOUR_COUNT

        # Assert
        assert result == expected


class TestNearestColour:
    def test_black_and_white_map_to_the_end_stops(self):
        # Arrange
        rgb = np.array([[[0, 0, 0], [255, 255, 255]]], dtype=np.uint8)

        # Act
        result = smscolor.nearest_colour(rgb)

        # Assert
        assert result[0, 0] == 0x00
        assert result[0, 1] == 0x3F

    def test_every_result_is_a_console_colour(self):
        # Arrange
        rng = np.random.default_rng(41)
        rgb = rng.integers(0, 256, size=(8, 8, 3), dtype=np.uint8)

        # Act
        result = smscolor.nearest_colour(rgb)

        # Assert
        assert int(result.max()) < smscolor.COLOUR_COUNT

    def test_it_beats_per_channel_rounding_in_oklab(self):
        # Arrange
        rng = np.random.default_rng(42)
        rgb = rng.integers(0, 256, size=(16, 16, 3), dtype=np.uint8)
        lab = smscolor.oklab_palette()
        source = smscolor.srgb_to_oklab(rgb.astype(np.float32) / 255.0).reshape(-1, 3)
        rounded = smscolor.pack_colour(smscolor.quantise_levels(rgb)).reshape(-1)
        rounded_error = source - lab[rounded]

        # Act
        result = smscolor.nearest_colour(rgb).reshape(-1)

        # Assert
        nearest_error = source - lab[result]
        assert float((nearest_error * nearest_error).sum()) <= float(
            (rounded_error * rounded_error).sum()
        )

    def test_the_shape_is_preserved(self):
        # Arrange
        rgb = np.zeros((4, 7, 3), dtype=np.uint8)

        # Act
        result = smscolor.nearest_colour(rgb)

        # Assert
        assert result.shape == (4, 7)

    def test_chroma_weight_can_change_the_choice(self):
        # Arrange
        rgb = np.array([[[0, 0, 204]]], dtype=np.uint8)
        plain = smscolor.nearest_colour(rgb, chroma_weight=1.0)

        # Act
        weighted = smscolor.nearest_colour(rgb, chroma_weight=0.1)

        # Assert
        assert plain.tolist() != weighted.tolist()

    def test_an_array_without_an_rgb_axis_is_refused(self):
        # Arrange
        rgb = np.zeros((4, 2), dtype=np.uint8)

        # Act
        with pytest.raises(ValueError) as refused:
            smscolor.nearest_colour(rgb)

        # Assert
        assert str(refused.value) == "expected a trailing RGB axis, got shape (4, 2)"
