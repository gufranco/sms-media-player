from __future__ import annotations

import struct

import pytest
from z80vdp import expected_pixels, load, pixels, run, sprites, tile, white_rows

FIRST_TILE = 176
TEXT_TILES = 6
TEXT_NUMBERS = list(range(FIRST_TILE, FIRST_TILE + TEXT_TILES))
BAR_SPRITES = 8
TEXT_Y = 167
BAR_Y = 179
TEXT_X = 104
BAR_X = 96
FULL = FIRST_TILE + TEXT_TILES
EMPTY = FULL + 1
PARTIAL = FULL + 2
INK_BLACK = 0x00
INK_WHITE = 0x3F
FIELDS_PER_SECOND = 59.9227


@pytest.fixture(scope="module")
def built():
    return load()


def position(*, elapsed: int, total: int) -> bytes:
    return struct.pack("<II", elapsed, total)


def fields(seconds: int) -> int:
    return round(seconds * FIELDS_PER_SECOND)


class TestShow:
    def test_the_ink_entries_are_black_and_white(self, built):
        # Arrange
        where = {"elapsed": fields(1), "total": fields(3)}

        # Act
        vdp = run(built, "_fmv_osd_show", position(**where))

        # Assert
        assert (vdp.cram[30], vdp.cram[31]) == (INK_BLACK, INK_WHITE)

    def test_the_text_reads_elapsed_over_total(self, built):
        # Arrange
        where = {"elapsed": fields(1), "total": fields(3)}

        # Act
        vdp = run(built, "_fmv_osd_show", position(**where))

        # Assert
        assert pixels(vdp, TEXT_NUMBERS) == expected_pixels("00:01/00:03 ")

    def test_the_text_sprites_sit_in_a_row_above_the_bar(self, built):
        # Arrange
        where = {"elapsed": fields(1), "total": fields(3)}

        # Act
        vdp = run(built, "_fmv_osd_show", position(**where))

        # Assert
        assert sprites(vdp)[:TEXT_TILES] == [
            (TEXT_Y, TEXT_X + 8 * index, FIRST_TILE + index) for index in range(TEXT_TILES)
        ]

    def test_half_way_lights_half_the_bar(self, built):
        # Arrange
        where = {"elapsed": 90, "total": 180}

        # Act
        vdp = run(built, "_fmv_osd_show", position(**where))

        # Assert
        assert sprites(vdp)[TEXT_TILES:] == [
            (BAR_Y, BAR_X + 8 * index, FULL if index < 4 else EMPTY) for index in range(BAR_SPRITES)
        ]

    def test_a_fill_between_sprites_uses_the_partial_tile(self, built):
        # Arrange
        where = {"elapsed": 13, "total": 64}

        # Act
        vdp = run(built, "_fmv_osd_show", position(**where))

        # Assert
        assert [number for _, _, number in sprites(vdp)[TEXT_TILES:]][:3] == [
            FULL,
            PARTIAL,
            EMPTY,
        ]

    def test_the_partial_tile_lights_the_leftover_columns(self, built):
        # Arrange
        where = {"elapsed": 13, "total": 64}

        # Act
        vdp = run(built, "_fmv_osd_show", position(**where))

        # Assert
        assert white_rows(tile(vdp, PARTIAL))[2:6] == ["#####..."] * 4

    def test_the_end_of_the_film_fills_the_bar(self, built):
        # Arrange
        where = {"elapsed": 500, "total": 500}

        # Act
        vdp = run(built, "_fmv_osd_show", position(**where))

        # Assert
        assert [number for _, _, number in sprites(vdp)[TEXT_TILES:]] == [FULL] * BAR_SPRITES

    def test_the_total_rounds_to_the_nearest_second(self, built):
        # Arrange
        where = {"elapsed": 0, "total": 106}

        # Act
        vdp = run(built, "_fmv_osd_show", position(**where))

        # Assert
        assert pixels(vdp, TEXT_NUMBERS) == expected_pixels("00:00/00:02 ")

    def test_the_elapsed_time_counts_whole_seconds(self, built):
        # Arrange
        where = {"elapsed": 106, "total": 180}

        # Act
        vdp = run(built, "_fmv_osd_show", position(**where))

        # Assert
        assert pixels(vdp, TEXT_NUMBERS) == expected_pixels("00:01/00:03 ")


class TestHide:
    def test_hiding_ends_the_sprite_list_at_the_first_entry(self, built):
        # Arrange
        routine = "_fmv_osd_hide"

        # Act
        vdp = run(built, routine)

        # Assert
        assert sprites(vdp) == []
