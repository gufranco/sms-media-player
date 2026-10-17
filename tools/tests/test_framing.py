from __future__ import annotations

import numpy as np
import pytest

from smsggmedia import bake, cartridge, console, limits, pattern, replay, smscolor

BUDGET = 1400
CAP = 220


FLOOR = 90
CEILING = 250
SPLIT = 86


def blocky_frames(count: int, geometry: bake.Geometry, *, seed: int) -> list[np.ndarray]:
    rng = np.random.default_rng(seed)
    frames = []
    for _ in range(count):
        blocks = rng.integers(
            FLOOR, CEILING, size=(geometry.rows, geometry.columns, 3), dtype=np.uint8
        )
        frame = np.kron(blocks, np.ones((pattern.TILE_PX, pattern.TILE_PX, 1), dtype=np.uint8))
        columns = np.arange(frame.shape[1]) % pattern.TILE_PX
        step = np.where(columns >= pattern.TILE_PX // 2, -SPLIT, 0)[None, :, None]
        frames.append((frame.astype(np.int16) + step).clip(0, 255).astype(np.uint8))
    return frames


def worst_framing(encoded: bake.Encoded, geometry: bake.Geometry) -> float:
    machine = replay.Machine()
    worst = 0.0
    for chunks in encoded.frames:
        for chunk in chunks:
            machine.apply(chunk)
        lit = replay.lit_fraction(
            replay.framing(
                machine.display(),
                rows=geometry.rows,
                top_row=geometry.top_row,
                columns=geometry.columns,
                left_column=geometry.left_column,
            )
        )
        worst = max(worst, lit)
    return worst


def played(encoded: bake.Encoded) -> replay.Machine:
    machine = replay.Machine()
    for chunks in encoded.frames:
        for chunk in chunks:
            machine.apply(chunk)
    return machine


def palette_zeros(encoded: bake.Encoded, entry: int) -> set[int]:
    machine = replay.Machine()
    seen = set()
    for chunks in encoded.frames:
        for chunk in chunks:
            machine.apply(chunk)
        seen.add(int(machine.cram[entry]))
    return seen


def bake_with(frames, geometry, *, reserved: int) -> bake.Encoded:
    return bake.encode_frames(frames, geometry=geometry, budget=BUDGET, cap=CAP, reserved=reserved)


def blank_display() -> np.ndarray:
    return np.zeros((console.VISIBLE_ROWS * pattern.TILE_PX, 256, 3), dtype=np.uint8)


@pytest.fixture
def geometry() -> bake.Geometry:
    return cartridge.geometry_for(limits.DEFAULT_COLUMNS, 18)


class TestTheCartridgeFillsTheScreen:
    def test_the_default_picture_covers_every_visible_row(self):
        # Arrange
        columns, rows = limits.DEFAULT_COLUMNS, limits.DEFAULT_ROWS

        # Act
        shipping = cartridge.geometry_for(columns, rows)

        # Assert
        assert shipping == bake.Geometry(columns=32, rows=24, top_row=0)

    def test_the_default_picture_is_the_whole_raster(self):
        # Arrange
        columns, rows = limits.DEFAULT_COLUMNS, limits.DEFAULT_ROWS

        # Act
        shipping = cartridge.geometry_for(columns, rows)

        # Assert
        assert (shipping.width, shipping.height) == (256, 192)

    def test_a_full_picture_has_no_framing_to_measure(self):
        # Arrange
        shipping = cartridge.geometry_for(limits.DEFAULT_COLUMNS, limits.DEFAULT_ROWS)
        display = blank_display()

        # Act
        bands = replay.framing(
            display,
            rows=shipping.rows,
            top_row=shipping.top_row,
            columns=shipping.columns,
            left_column=shipping.left_column,
        )

        # Assert
        assert bands.shape[0] == 0


class TestTheBandsStayEmpty:
    def test_a_smaller_picture_leaves_visible_rows_unused(self, geometry):
        # Arrange
        visible = console.VISIBLE_ROWS

        # Act
        bottom = geometry.top_row + geometry.rows

        # Assert
        assert geometry.top_row > 0
        assert bottom < visible

    def test_nothing_lights_the_bands(self, geometry):
        # Arrange
        frames = blocky_frames(4, geometry, seed=7)

        # Act
        encoded = bake_with(frames, geometry, reserved=console.RESERVED_PATTERNS)

        # Assert
        assert worst_framing(encoded, geometry) == 0.0

    def test_the_check_would_catch_the_defect_that_shipped(self, geometry):
        # Arrange
        frames = blocky_frames(4, geometry, seed=7)

        # Act
        encoded = bake_with(frames, geometry, reserved=0)

        # Assert
        assert worst_framing(encoded, geometry) > 0.0, (
            "the fixture stopped being adversarial: with the low pattern unreserved it "
            "must fill the bands, and it no longer does, so this guard can no longer "
            "show that it rejects the configuration that shipped"
        )

    def test_the_fixture_leaves_the_low_pattern_holding_picture(self, geometry):
        # Arrange
        frames = blocky_frames(4, geometry, seed=7)

        # Act
        encoded = bake_with(frames, geometry, reserved=0)

        # Assert
        low_pattern = played(encoded).vram[: console.PATTERN_BYTES]
        assert int(np.count_nonzero(low_pattern)) > 0

    def test_the_withheld_pattern_stays_blank(self, geometry):
        # Arrange
        frames = blocky_frames(4, geometry, seed=11)

        # Act
        encoded = bake_with(frames, geometry, reserved=console.RESERVED_PATTERNS)

        # Assert
        withheld = played(encoded).vram[: console.RESERVED_PATTERNS * console.PATTERN_BYTES]
        assert int(np.count_nonzero(withheld)) == 0

    def test_the_stream_never_writes_the_sprite_table(self, geometry):
        # Arrange
        frames = blocky_frames(4, geometry, seed=13)

        # Act
        encoded = bake_with(frames, geometry, reserved=console.RESERVED_PATTERNS)

        # Assert
        ys = played(encoded).vram[console.SAT_BASE :][: console.SPRITE_SLOTS]
        assert bool(np.all(ys == console.SPRITE_OFF)) is True

    def test_the_stream_never_writes_a_name_table_cell_outside_the_picture(self, geometry):
        # Arrange
        frames = blocky_frames(4, geometry, seed=17)

        # Act
        encoded = bake_with(frames, geometry, reserved=console.RESERVED_PATTERNS)

        # Assert
        table = played(encoded).vram[console.NAME_TABLE_BASE : console.SAT_BASE]
        entries = (table[0::2].astype(np.uint16) | (table[1::2].astype(np.uint16) << 8)).reshape(
            console.NAME_TABLE_ROWS, console.NAME_TABLE_COLUMNS
        )
        outside = np.concatenate(
            [entries[: geometry.top_row], entries[geometry.top_row + geometry.rows :]]
        )
        assert bool(np.all(outside == console.IDLE_CELL)) is True

    def test_the_first_palette_zero_is_not_reliably_black(self, geometry):
        # Arrange
        frames = blocky_frames(6, geometry, seed=7)

        # Act
        encoded = bake_with(frames, geometry, reserved=console.RESERVED_PATTERNS)

        # Assert
        assert palette_zeros(encoded, 0) != {console.BLACK}

    def test_the_second_palette_zero_is_always_black(self, geometry):
        # Arrange
        frames = blocky_frames(6, geometry, seed=7)

        # Act
        encoded = bake_with(frames, geometry, reserved=console.RESERVED_PATTERNS)

        # Assert
        assert palette_zeros(encoded, smscolor.PALETTE_ENTRIES) == {console.BLACK}

    def test_the_picture_itself_is_not_blank(self, geometry):
        # Arrange
        frames = blocky_frames(4, geometry, seed=19)

        # Act
        encoded = bake_with(frames, geometry, reserved=console.RESERVED_PATTERNS)

        # Assert
        picture = played(encoded).render(
            columns=geometry.columns, rows=geometry.rows, top_row=geometry.top_row
        )
        assert replay.lit_fraction(picture) > 0.5


class TestFraming:
    def test_the_framing_is_every_visible_pixel_outside_the_picture(self, geometry):
        # Arrange
        display = blank_display()

        # Act
        bands = replay.framing(
            display,
            rows=geometry.rows,
            top_row=geometry.top_row,
            columns=geometry.columns,
            left_column=geometry.left_column,
        )

        # Assert
        assert bands.shape[0] == (console.VISIBLE_ROWS - geometry.rows) * pattern.TILE_PX * 256

    def test_a_picture_taller_than_the_display_is_refused(self):
        # Arrange
        display = blank_display()
        rows = console.VISIBLE_ROWS

        # Act
        with pytest.raises(ValueError) as refused:
            replay.framing(display, rows=rows, top_row=1)

        # Assert
        assert str(refused.value) == (
            f"a picture of {rows} rows at row 1 is not inside {console.VISIBLE_ROWS} visible rows"
        )

    def test_a_picture_above_the_display_is_refused(self):
        # Arrange
        display = blank_display()

        # Act
        with pytest.raises(ValueError) as refused:
            replay.framing(display, rows=4, top_row=-1)

        # Assert
        assert str(refused.value) == (
            f"a picture of 4 rows at row -1 is not inside {console.VISIBLE_ROWS} visible rows"
        )

    def test_a_narrower_picture_counts_its_side_columns_as_framing(self):
        # Arrange
        display = blank_display()

        # Act
        bands = replay.framing(display, rows=24, top_row=0, columns=24, left_column=4)

        # Assert
        assert bands.shape[0] == 8 * pattern.TILE_PX * 24 * pattern.TILE_PX

    def test_a_picture_past_the_right_edge_of_the_raster_is_refused(self):
        # Arrange
        display = blank_display()

        # Act
        with pytest.raises(ValueError) as refused:
            replay.framing(display, rows=24, top_row=0, columns=24, left_column=9)

        # Assert
        assert str(refused.value) == "a picture of 24 columns at column 9 is not inside the raster"

    def test_a_narrower_picture_is_centred_by_column(self):
        # Arrange
        columns = 24

        # Act
        geometry = cartridge.geometry_for(columns, console.VISIBLE_ROWS)

        # Assert
        assert geometry == bake.Geometry(columns=24, rows=24, top_row=0, left_column=4)

    def test_an_empty_band_reads_as_dark(self):
        # Arrange
        pixels = np.zeros((0, 3), dtype=np.uint8)

        # Act
        lit = replay.lit_fraction(pixels)

        # Assert
        assert lit == 0.0

    def test_a_black_band_reads_as_dark(self):
        # Arrange
        pixels = np.zeros((100, 3), dtype=np.uint8)

        # Act
        lit = replay.lit_fraction(pixels)

        # Assert
        assert lit == 0.0

    def test_a_white_band_reads_as_fully_lit(self):
        # Arrange
        pixels = np.full((100, 3), 255, dtype=np.uint8)

        # Act
        lit = replay.lit_fraction(pixels)

        # Assert
        assert lit == 1.0

    def test_one_lit_pixel_in_four_reads_as_a_quarter(self):
        # Arrange
        pixels = np.zeros((4, 3), dtype=np.uint8)
        pixels[0] = 255

        # Act
        lit = replay.lit_fraction(pixels)

        # Assert
        assert lit == 0.25
