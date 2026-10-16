from __future__ import annotations

import struct
from collections import Counter

import pytest
from z80vdp import SAT_Y, Session, expected_pixels, load, pixels, run, sprites

TOP_ROW = [185, 186, 187, 188, 189]
BOTTOM_ROW = [190, 191, 240, 241, 242]
FIRST_SPRITE = 15
ROW_X = [108, 116, 124, 132, 140]
TOP_Y = 143
BOTTOM_Y = 155
SPRITE_HEIGHT = 8
SPRITES_PER_LINE = 8
FRAME_INTERRUPT_LINE = 0xC1
FIELD_LIMIT = 12
LATE_LINE = 190
SPRITE_END = 0xD0
SECOND_PAYLOAD = 0xD010


@pytest.fixture(scope="module")
def built():
    return load()


def seen(*, frame: int, total: int, bank: int, defers: int) -> bytes:
    return struct.pack("<HHBH", frame, total, bank, defers)


def view() -> bytes:
    return struct.pack("<IIBB", 600, 1800, 0, 1)


def work_over_fields(session: Session) -> None:
    for _ in range(FIELD_LIMIT):
        session.vdp.start_at(0)
        session.call("_fmv_diag_work")


def busiest_line(entries: list[tuple[int, int, int]]) -> int:
    lines: Counter[int] = Counter()
    for y, _, _ in entries:
        lines.update(range(y + 1, y + 1 + SPRITE_HEIGHT))
    return max(lines.values())


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

    def test_no_line_carries_more_than_eight_sprites_with_both_overlays_up(self, built):
        # Arrange
        session = Session(built, view())
        session.call("_fmv_osd_show")
        session.poke(SECOND_PAYLOAD, seen(frame=1, total=2, bank=2, defers=0))

        # Act
        session.call("_fmv_diag_show", hl=SECOND_PAYLOAD)

        # Assert
        assert busiest_line(sprites(session.vdp)) <= SPRITES_PER_LINE


class TestHide:
    def test_hiding_ends_the_sprite_list_after_the_position_overlay(self, built):
        # Arrange
        routine = "_fmv_diag_hide"

        # Act
        vdp = run(built, routine)

        # Assert
        assert vdp.vram[SAT_Y + FIRST_SPRITE] == SPRITE_END

    def test_hiding_drops_work_still_pending(self, built):
        # Arrange
        session = Session(built, seen(frame=1, total=2, bank=2, defers=0))
        session.call("_fmv_diag_open")
        session.call("_fmv_diag_hide")
        before = session.vdp.writes

        # Act
        work_over_fields(session)

        # Assert
        assert session.vdp.writes == before


class TestTheFieldBudget:
    @pytest.mark.parametrize("line", [0, 60, 120, 160, 185, 191])
    def test_work_started_in_the_display_returns_before_the_frame_interrupt(self, built, line):
        # Arrange
        session = Session(built, seen(frame=9999, total=9999, bank=99, defers=9999))
        session.call("_fmv_diag_open")
        session.vdp.start_at(line)

        # Act
        session.call("_fmv_diag_work")

        # Assert
        assert session.vdp.now() < FRAME_INTERRUPT_LINE

    def test_work_with_no_room_writes_nothing(self, built):
        # Arrange
        session = Session(built, seen(frame=1, total=2, bank=2, defers=0))
        session.call("_fmv_diag_open")
        session.vdp.start_at(LATE_LINE)

        # Act
        session.call("_fmv_diag_work")

        # Assert
        assert session.vdp.writes == 0

    def test_work_spread_over_fields_draws_what_show_draws(self, built):
        # Arrange
        payload = seen(frame=12, total=240, bank=3, defers=5)
        session = Session(built, payload)
        session.call("_fmv_diag_open")

        # Act
        work_over_fields(session)

        # Assert
        assert pixels(session.vdp, TOP_ROW + BOTTOM_ROW) == pixels(
            run(built, "_fmv_diag_show", payload), TOP_ROW + BOTTOM_ROW
        )
