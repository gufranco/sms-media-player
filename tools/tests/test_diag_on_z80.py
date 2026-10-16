from __future__ import annotations

import struct

import pytest
from z80vdp import expected_pixels, load, pixels, run, sprites

TOP_ROW = [185, 186, 187, 188, 189]
BOTTOM_ROW = [190, 191, 240, 241, 242]
FIRST_SPRITE = 14
ROW_X = [108, 116, 124, 132, 140]
TOP_Y = 143
BOTTOM_Y = 155


@pytest.fixture(scope="module")
def built():
    return load()


def seen(*, frame: int, total: int, bank: int, defers: int) -> bytes:
    return struct.pack("<HHBH", frame, total, bank, defers)


class TestShow:
    def test_the_top_row_reads_frame_over_total(self, built):
        # Arrange
        payload = seen(frame=12, total=240, bank=3, defers=5)

        # Act
        vdp = run(built, "_fmv_diag_show", payload)

        # Assert
        assert pixels(vdp, TOP_ROW) == expected_pixels("F0012/0240")

    def test_the_bottom_row_reads_bank_and_deferred_fields(self, built):
        # Arrange
        payload = seen(frame=12, total=240, bank=3, defers=5)

        # Act
        vdp = run(built, "_fmv_diag_show", payload)

        # Assert
        assert pixels(vdp, BOTTOM_ROW) == expected_pixels("B03 D0005 ")

    def test_a_count_past_four_digits_is_held_at_9999(self, built):
        # Arrange
        payload = seen(frame=12, total=240, bank=3, defers=40000)

        # Act
        vdp = run(built, "_fmv_diag_show", payload)

        # Assert
        assert pixels(vdp, BOTTOM_ROW) == expected_pixels("B03 D9999 ")

    def test_the_rows_follow_the_position_overlay_in_the_sprite_table(self, built):
        # Arrange
        payload = seen(frame=1, total=2, bank=2, defers=0)

        # Act
        vdp = run(built, "_fmv_diag_show", payload)

        # Assert
        assert sprites(vdp)[FIRST_SPRITE:] == [
            (TOP_Y, x, number) for x, number in zip(ROW_X, TOP_ROW, strict=True)
        ] + [(BOTTOM_Y, x, number) for x, number in zip(ROW_X, BOTTOM_ROW, strict=True)]


class TestHide:
    def test_hiding_ends_the_sprite_list_after_the_position_overlay(self, built):
        # Arrange
        routine = "_fmv_diag_hide"

        # Act
        vdp = run(built, routine)

        # Assert
        assert vdp.vram[0x3F00 + FIRST_SPRITE] == 0xD0
