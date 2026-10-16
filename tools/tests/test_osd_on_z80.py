from __future__ import annotations

import struct

import pytest
from z80vdp import (
    SAT_XN,
    SAT_Y,
    SPRITE_PATTERNS,
    TILE_BYTES,
    WHERE,
    Session,
    expected_pixels,
    load,
    pixels,
    run,
    sprites,
    tile,
    white_rows,
)

FIRST_TILE = 176
TEXT_TILES = 6
TEXT_NUMBERS = list(range(FIRST_TILE, FIRST_TILE + TEXT_TILES))
BAR_SPRITES = 8
OSD_SPRITES = 15
STATE_SPRITE = TEXT_TILES + BAR_SPRITES
STATE_TILE = 243
BLANK_TILE = 244
TEXT_Y = 167
BAR_Y = 179
TEXT_X = 112
BAR_X = 96
STATE_X = 96
FULL = FIRST_TILE + TEXT_TILES
EMPTY = FULL + 1
PARTIAL = FULL + 2
INK_BLACK = 0x00
INK_WHITE = 0x3F
INK_ENTRIES = slice(30, 32)
FIELDS_PER_SECOND = 59.9227
FRAME_INTERRUPT_LINE = 0xC1
FIELD_LINES = 262
FIELD_LIMIT = 12
LATE_LINE = 190
BLANK_LINE = 200
PAUSED_AT = WHERE + 8
IDLE_CELLS = bytes([0x00, 0x08])
OVERLAY_TILES = range(FIRST_TILE, BLANK_TILE + 1)


@pytest.fixture(scope="module")
def built():
    return load()


def view(*, elapsed: int, total: int, paused: int = 0, muted: int = 0) -> bytes:
    return struct.pack("<IIBB", elapsed, total, paused, muted)


def fields(seconds: int) -> int:
    return round(seconds * FIELDS_PER_SECOND)


def shown(built, payload: bytes) -> Session:
    session = Session(built, payload)
    session.call("_fmv_osd_show")
    return session


def work_over_fields(session: Session) -> None:
    for _ in range(FIELD_LIMIT):
        session.vdp.start_at(0)
        session.call("_fmv_osd_work")


def bar_tiles(session: Session) -> list[int]:
    return [number for _, _, number in sprites(session.vdp)[TEXT_TILES:STATE_SPRITE]]


def overlay_state(session: Session) -> tuple[bytes, bytes, bytes, bytes]:
    vram = session.vdp.vram
    first = SPRITE_PATTERNS + OVERLAY_TILES.start * TILE_BYTES
    last = SPRITE_PATTERNS + OVERLAY_TILES.stop * TILE_BYTES
    return (
        bytes(vram[first:last]),
        bytes(vram[SAT_Y : SAT_Y + OSD_SPRITES]),
        bytes(vram[SAT_XN : SAT_XN + 2 * OSD_SPRITES]),
        bytes(session.vdp.cram[INK_ENTRIES]),
    )


class TestShow:
    def test_the_ink_entries_are_black_and_white(self, built):
        # Arrange
        payload = view(elapsed=fields(1), total=fields(3))

        # Act
        vdp = run(built, "_fmv_osd_show", payload)

        # Assert
        assert (vdp.cram[30], vdp.cram[31]) == (INK_BLACK, INK_WHITE)

    def test_the_text_reads_elapsed_over_total(self, built):
        # Arrange
        payload = view(elapsed=fields(1), total=fields(3))

        # Act
        vdp = run(built, "_fmv_osd_show", payload)

        # Assert
        assert pixels(vdp, TEXT_NUMBERS) == expected_pixels("00:01/00:03 ")

    def test_the_text_sprites_sit_in_a_row_above_the_bar(self, built):
        # Arrange
        payload = view(elapsed=fields(1), total=fields(3))

        # Act
        vdp = run(built, "_fmv_osd_show", payload)

        # Assert
        assert sprites(vdp)[:TEXT_TILES] == [
            (TEXT_Y, TEXT_X + 8 * index, FIRST_TILE + index) for index in range(TEXT_TILES)
        ]

    def test_half_way_lights_half_the_bar(self, built):
        # Arrange
        payload = view(elapsed=90, total=180)

        # Act
        vdp = run(built, "_fmv_osd_show", payload)

        # Assert
        assert sprites(vdp)[TEXT_TILES:STATE_SPRITE] == [
            (BAR_Y, BAR_X + 8 * index, FULL if index < 4 else EMPTY) for index in range(BAR_SPRITES)
        ]

    def test_a_fill_between_sprites_uses_the_partial_tile(self, built):
        # Arrange
        payload = view(elapsed=13, total=64)

        # Act
        vdp = run(built, "_fmv_osd_show", payload)

        # Assert
        assert [number for _, _, number in sprites(vdp)[TEXT_TILES:STATE_SPRITE]][:3] == [
            FULL,
            PARTIAL,
            EMPTY,
        ]

    def test_the_partial_tile_lights_the_leftover_columns(self, built):
        # Arrange
        payload = view(elapsed=13, total=64)

        # Act
        vdp = run(built, "_fmv_osd_show", payload)

        # Assert
        assert white_rows(tile(vdp, PARTIAL))[2:6] == ["#####..."] * 4

    def test_the_end_of_the_film_fills_the_bar(self, built):
        # Arrange
        payload = view(elapsed=500, total=500)

        # Act
        vdp = run(built, "_fmv_osd_show", payload)

        # Assert
        assert [number for _, _, number in sprites(vdp)[TEXT_TILES:STATE_SPRITE]] == [
            FULL
        ] * BAR_SPRITES

    def test_the_total_rounds_to_the_nearest_second(self, built):
        # Arrange
        payload = view(elapsed=0, total=106)

        # Act
        vdp = run(built, "_fmv_osd_show", payload)

        # Assert
        assert pixels(vdp, TEXT_NUMBERS) == expected_pixels("00:00/00:02 ")

    def test_the_elapsed_time_counts_whole_seconds(self, built):
        # Arrange
        payload = view(elapsed=106, total=180)

        # Act
        vdp = run(built, "_fmv_osd_show", payload)

        # Assert
        assert pixels(vdp, TEXT_NUMBERS) == expected_pixels("00:01/00:03 ")

    def test_a_clock_past_99_minutes_holds_at_99_59(self, built):
        # Arrange
        payload = view(elapsed=fields(6000), total=fields(7200))

        # Act
        vdp = run(built, "_fmv_osd_show", payload)

        # Assert
        assert pixels(vdp, TEXT_NUMBERS) == expected_pixels("99:59/99:59 ")


class TestTheStateGlyph:
    def test_it_sits_left_of_the_clock_on_the_text_row(self, built):
        # Arrange
        payload = view(elapsed=0, total=180)

        # Act
        vdp = run(built, "_fmv_osd_show", payload)

        # Assert
        assert sprites(vdp)[STATE_SPRITE] == (TEXT_Y, STATE_X, STATE_TILE)

    def test_playing_shows_the_play_glyph(self, built):
        # Arrange
        payload = view(elapsed=0, total=180)

        # Act
        vdp = run(built, "_fmv_osd_show", payload)

        # Assert
        assert pixels(vdp, [STATE_TILE]) == expected_pixels("> ")

    def test_paused_shows_the_pause_glyph(self, built):
        # Arrange
        payload = view(elapsed=0, total=180, paused=1)

        # Act
        vdp = run(built, "_fmv_osd_show", payload)

        # Assert
        assert pixels(vdp, [STATE_TILE]) == expected_pixels("= ")

    def test_sound_off_adds_the_mute_mark(self, built):
        # Arrange
        payload = view(elapsed=0, total=180, muted=1)

        # Act
        vdp = run(built, "_fmv_osd_show", payload)

        # Assert
        assert pixels(vdp, [STATE_TILE]) == expected_pixels(">x")

    def test_a_state_change_redraws_the_glyph(self, built):
        # Arrange
        session = shown(built, view(elapsed=0, total=180))
        session.poke(PAUSED_AT, bytes([1]))

        # Act
        session.call("_fmv_osd_state")
        work_over_fields(session)

        # Assert
        assert pixels(session.vdp, [STATE_TILE]) == expected_pixels("= ")


class TestClose:
    def test_closing_points_every_overlay_sprite_at_the_blank_tile(self, built):
        # Arrange
        session = shown(built, view(elapsed=0, total=180))

        # Act
        session.call("_fmv_osd_close")
        work_over_fields(session)

        # Assert
        assert [number for _, _, number in sprites(session.vdp)[:OSD_SPRITES]] == [
            BLANK_TILE
        ] * OSD_SPRITES

    def test_the_blank_tile_is_cleared_over_the_idle_name_table_cells(self, built):
        # Arrange
        session = Session(built, view(elapsed=fields(59), total=fields(61), muted=1))
        start = SPRITE_PATTERNS + BLANK_TILE * TILE_BYTES
        session.vdp.vram[start : start + TILE_BYTES] = IDLE_CELLS * (TILE_BYTES // 2)
        session.call("_fmv_osd_show")

        # Act
        session.call("_fmv_osd_close")
        work_over_fields(session)

        # Assert
        assert tile(session.vdp, BLANK_TILE) == bytes(TILE_BYTES)

    def test_a_tick_while_closed_draws_nothing(self, built):
        # Arrange
        session = shown(built, view(elapsed=0, total=180))
        session.call("_fmv_osd_close")
        work_over_fields(session)
        before = session.vdp.writes

        # Act
        session.call("_fmv_osd_tick")
        work_over_fields(session)

        # Assert
        assert session.vdp.writes == before


class TestTheTick:
    def test_a_tick_redraws_the_elapsed_time(self, built):
        # Arrange
        session = shown(built, view(elapsed=fields(1), total=fields(10)))
        session.poke(WHERE, fields(5).to_bytes(4, "little"))

        # Act
        session.call("_fmv_osd_tick")
        work_over_fields(session)

        # Assert
        assert pixels(session.vdp, TEXT_NUMBERS) == expected_pixels("00:05/00:10 ")

    def test_a_tick_moves_the_bar(self, built):
        # Arrange
        session = shown(built, view(elapsed=0, total=180))
        session.poke(WHERE, (90).to_bytes(4, "little"))

        # Act
        session.call("_fmv_osd_tick")
        work_over_fields(session)

        # Assert
        assert bar_tiles(session) == [FULL] * 4 + [EMPTY] * 4


class TestTheFieldBudget:
    @pytest.mark.parametrize("line", [0, 40, 100, 150, 180, 191])
    def test_work_started_in_the_display_returns_before_the_frame_interrupt(self, built, line):
        # Arrange
        session = Session(built, view(elapsed=fields(3599), total=fields(7199), muted=1))
        session.call("_fmv_osd_open")
        session.vdp.start_at(line)

        # Act
        session.call("_fmv_osd_work")

        # Assert
        assert session.vdp.now() < FRAME_INTERRUPT_LINE

    def test_work_with_no_room_writes_nothing(self, built):
        # Arrange
        session = Session(built, view(elapsed=0, total=180))
        session.call("_fmv_osd_open")
        session.vdp.start_at(LATE_LINE)

        # Act
        session.call("_fmv_osd_work")

        # Assert
        assert session.vdp.writes == 0

    def test_work_in_the_vertical_blank_returns_before_the_next_one(self, built):
        # Arrange
        session = Session(built, view(elapsed=0, total=180))
        session.call("_fmv_osd_open")
        session.vdp.start_at(BLANK_LINE)

        # Act
        session.call("_fmv_osd_work")

        # Assert
        assert session.vdp.now() < FIELD_LINES + FRAME_INTERRUPT_LINE

    def test_work_spread_over_fields_draws_what_show_draws(self, built):
        # Arrange
        payload = view(elapsed=fields(61), total=fields(125), muted=1)
        session = Session(built, payload)
        session.call("_fmv_osd_open")

        # Act
        work_over_fields(session)

        # Assert
        assert overlay_state(session) == overlay_state(shown(built, payload))
