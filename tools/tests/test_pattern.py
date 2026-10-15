import numpy as np
import pytest

from smsmovie import pattern


def solid(value: int) -> np.ndarray:
    return np.full((1, pattern.TILE_PX, pattern.TILE_PX), value, dtype=np.uint8)


class TestPackPatterns:
    def test_a_pattern_is_thirty_two_bytes(self):
        # Arrange
        tiles = solid(0)

        # Act
        result = pattern.pack_patterns(tiles)

        # Assert
        assert result.shape == (1, pattern.PATTERN_BYTES)

    def test_colour_zero_leaves_every_plane_clear(self):
        # Arrange
        tiles = solid(0)

        # Act
        result = pattern.pack_patterns(tiles)

        # Assert
        assert result.tolist() == [[0] * pattern.PATTERN_BYTES]

    def test_colour_one_sets_only_the_first_plane(self):
        # Arrange
        tiles = solid(1)

        # Act
        result = pattern.pack_patterns(tiles)

        # Assert
        assert result[0].tolist() == [0xFF, 0x00, 0x00, 0x00] * pattern.TILE_PX

    def test_colour_fifteen_sets_every_plane(self):
        # Arrange
        tiles = solid(15)

        # Act
        result = pattern.pack_patterns(tiles)

        # Assert
        assert result[0].tolist() == [0xFF] * pattern.PATTERN_BYTES

    def test_colour_eight_sets_only_the_last_plane(self):
        # Arrange
        tiles = solid(8)

        # Act
        result = pattern.pack_patterns(tiles)

        # Assert
        assert result[0].tolist() == [0x00, 0x00, 0x00, 0xFF] * pattern.TILE_PX

    def test_the_leftmost_pixel_is_the_most_significant_bit(self):
        # Arrange
        tiles = np.zeros((1, pattern.TILE_PX, pattern.TILE_PX), dtype=np.uint8)
        tiles[0, 0, 0] = 1

        # Act
        result = pattern.pack_patterns(tiles)

        # Assert
        assert result[0, 0] == 0x80

    def test_the_rightmost_pixel_is_the_least_significant_bit(self):
        # Arrange
        tiles = np.zeros((1, pattern.TILE_PX, pattern.TILE_PX), dtype=np.uint8)
        tiles[0, 0, pattern.TILE_PX - 1] = 1

        # Act
        result = pattern.pack_patterns(tiles)

        # Assert
        assert result[0, 0] == 0x01

    def test_rows_are_stored_in_order(self):
        # Arrange
        tiles = np.zeros((1, pattern.TILE_PX, pattern.TILE_PX), dtype=np.uint8)
        tiles[0, 3, 0] = 1

        # Act
        result = pattern.pack_patterns(tiles)

        # Assert
        assert result[0, 3 * pattern.PLANES] == 0x80

    def test_a_pixel_above_fifteen_is_refused(self):
        # Arrange
        tiles = solid(16)

        # Act
        with pytest.raises(ValueError) as refused:
            pattern.pack_patterns(tiles)

        # Assert
        assert (
            str(refused.value) == "tile pixels must be 4-bit palette indices in the range 0 to 15"
        )

    def test_a_tile_of_the_wrong_shape_is_refused(self):
        # Arrange
        tiles = np.zeros((1, 4, 4), dtype=np.uint8)

        # Act
        with pytest.raises(ValueError) as refused:
            pattern.pack_patterns(tiles)

        # Assert
        assert str(refused.value) == "tiles must be a batch of 8x8 arrays, got shape (1, 4, 4)"


class TestUnpackPatterns:
    def test_unpacking_reverses_packing(self):
        # Arrange
        rng = np.random.default_rng(12345)
        tiles = rng.integers(0, 16, size=(7, pattern.TILE_PX, pattern.TILE_PX), dtype=np.uint8)
        packed = pattern.pack_patterns(tiles)

        # Act
        result = pattern.unpack_patterns(packed)

        # Assert
        assert result.tolist() == tiles.tolist()

    def test_an_empty_batch_round_trips(self):
        # Arrange
        tiles = np.zeros((0, pattern.TILE_PX, pattern.TILE_PX), dtype=np.uint8)
        packed = pattern.pack_patterns(tiles)

        # Act
        result = pattern.unpack_patterns(packed)

        # Assert
        assert result.shape == (0, pattern.TILE_PX, pattern.TILE_PX)


class TestNameTableEntry:
    def test_a_plain_entry_is_just_the_index(self):
        # Arrange
        index = 5

        # Act
        result = pattern.name_table_entry(index=index, palette=0)

        # Assert
        assert result == 5

    def test_the_palette_select_is_bit_eleven(self):
        # Arrange
        palette = 1

        # Act
        result = pattern.name_table_entry(index=0, palette=palette)

        # Assert
        assert result == 0x0800

    def test_horizontal_flip_is_bit_nine(self):
        # Arrange
        hflip = True

        # Act
        result = pattern.name_table_entry(index=0, palette=0, hflip=hflip)

        # Assert
        assert result == 0x0200

    def test_vertical_flip_is_bit_ten(self):
        # Arrange
        vflip = True

        # Act
        result = pattern.name_table_entry(index=0, palette=0, vflip=vflip)

        # Assert
        assert result == 0x0400

    def test_the_index_uses_nine_bits(self):
        # Arrange
        index = 511

        # Act
        result = pattern.name_table_entry(index=index, palette=0)

        # Assert
        assert result == 0x01FF

    def test_an_index_past_the_ninth_bit_is_refused(self):
        # Arrange
        index = 512

        # Act
        with pytest.raises(ValueError) as refused:
            pattern.name_table_entry(index=index, palette=0)

        # Assert
        assert str(refused.value) == "pattern index 512 does not fit the 9-bit field"

    def test_a_palette_past_the_second_is_refused(self):
        # Arrange
        palette = 2

        # Act
        with pytest.raises(ValueError) as refused:
            pattern.name_table_entry(index=0, palette=palette)

        # Assert
        assert str(refused.value) == "palette 2 is not one of the two hardware palettes"


class TestTileFrame:
    def test_a_frame_splits_into_eight_by_eight_cells(self):
        # Arrange
        frame = np.zeros((16, 24), dtype=np.uint8)

        # Act
        result = pattern.tile_frame(frame)

        # Assert
        assert result.shape == (2 * 3, pattern.TILE_PX, pattern.TILE_PX)

    def test_cells_are_ordered_left_to_right_then_top_to_bottom(self):
        # Arrange
        frame = np.zeros((16, 16), dtype=np.uint8)
        frame[0, 8] = 9

        # Act
        result = pattern.tile_frame(frame)

        # Assert
        assert result[1, 0, 0] == 9

    def test_a_frame_that_is_not_a_whole_number_of_cells_is_refused(self):
        # Arrange
        frame = np.zeros((16, 20), dtype=np.uint8)

        # Act
        with pytest.raises(ValueError) as refused:
            pattern.tile_frame(frame)

        # Assert
        assert str(refused.value) == "a frame must be a whole number of 8x8 cells, got (16, 20)"


class TestRefusals:
    def test_unpacking_a_wrongly_shaped_batch_is_refused(self):
        # Arrange
        packed = np.zeros((4, 7), dtype=np.uint8)

        # Act
        with pytest.raises(ValueError) as refused:
            pattern.unpack_patterns(packed)

        # Assert
        assert str(refused.value) == "patterns must be a batch of 32-byte rows, got (4, 7)"

    def test_tiling_a_non_two_dimensional_frame_is_refused(self):
        # Arrange
        frame = np.zeros((8, 8, 3), dtype=np.uint8)

        # Act
        with pytest.raises(ValueError) as refused:
            pattern.tile_frame(frame)

        # Assert
        assert str(refused.value) == "a frame must be two dimensional, got shape (8, 8, 3)"


class TestPriorityBit:
    def test_the_priority_bit_is_set_when_asked(self):
        # Arrange
        priority = True

        # Act
        entry = pattern.name_table_entry(index=1, palette=0, priority=priority)

        # Assert
        assert entry & pattern.PRIORITY_BIT == pattern.PRIORITY_BIT

    def test_the_priority_bit_is_clear_by_default(self):
        # Arrange
        index = 1

        # Act
        entry = pattern.name_table_entry(index=index, palette=0)

        # Assert
        assert entry & pattern.PRIORITY_BIT == 0
