import numpy as np
import pytest
from bakeframes import (
    displays_before_the_palette,
    gradient_frame,
    replayed_working_set,
    walk,
    write_kinds,
    write_targets,
)

from smsggmedia import bake, console, replay, stream


class TestGeometry:
    def test_the_picture_is_a_whole_number_of_cells(self):
        # Arrange
        columns, rows = 32, 18

        # Act
        result = bake.Geometry(columns=columns, rows=rows, top_row=3)

        # Assert
        assert result.width == 256
        assert result.height == 144

    def test_cells_count_columns_times_rows(self):
        # Arrange
        columns, rows = 32, 18

        # Act
        result = bake.Geometry(columns=columns, rows=rows, top_row=3)

        # Assert
        assert result.cells == 576

    def test_a_picture_taller_than_the_raster_is_refused(self):
        # Arrange
        columns, rows, top_row = 32, 28, 3

        # Act
        with pytest.raises(ValueError) as refused:
            bake.Geometry(columns=columns, rows=rows, top_row=top_row)

        # Assert
        assert (
            str(refused.value)
            == "a picture of 28 rows at row 3 does not fit the 24 rows the console draws"
        )

    def test_a_picture_pushed_off_the_bottom_is_refused(self):
        # Arrange
        columns, rows, top_row = 32, 24, 1

        # Act
        with pytest.raises(ValueError) as refused:
            bake.Geometry(columns=columns, rows=rows, top_row=top_row)

        # Assert
        assert (
            str(refused.value)
            == "a picture of 24 rows at row 1 does not fit the 24 rows the console draws"
        )

    def test_a_picture_above_the_first_row_is_refused(self):
        # Arrange
        columns, rows, top_row = 32, 4, -1

        # Act
        with pytest.raises(ValueError) as refused:
            bake.Geometry(columns=columns, rows=rows, top_row=top_row)

        # Assert
        assert (
            str(refused.value)
            == "a picture of 4 rows at row -1 does not fit the 24 rows the console draws"
        )

    def test_a_picture_wider_than_the_name_table_is_refused(self):
        # Arrange
        columns, rows, top_row = 40, 18, 0

        # Act
        with pytest.raises(ValueError) as refused:
            bake.Geometry(columns=columns, rows=rows, top_row=top_row)

        # Assert
        assert (
            str(refused.value) == "a picture of 40 columns at column 0 does not fit the name table"
        )


class TestNameTableAddress:
    def test_the_first_cell_sits_at_the_table_base(self):
        # Arrange
        geometry = bake.Geometry(columns=32, rows=18, top_row=0)

        # Act
        result = bake.name_table_address(geometry, 0)

        # Assert
        assert result == bake.NAME_TABLE_BASE

    def test_a_cell_advances_two_bytes(self):
        # Arrange
        geometry = bake.Geometry(columns=32, rows=18, top_row=0)

        # Act
        result = bake.name_table_address(geometry, 1)

        # Assert
        assert result == bake.NAME_TABLE_BASE + 2

    def test_the_top_row_offsets_the_whole_picture(self):
        # Arrange
        geometry = bake.Geometry(columns=32, rows=18, top_row=3)

        # Act
        result = bake.name_table_address(geometry, 0)

        # Assert
        assert result == bake.NAME_TABLE_BASE + 3 * 32 * 2

    def test_a_narrower_picture_starts_at_its_column(self):
        # Arrange
        geometry = bake.Geometry(columns=24, rows=24, top_row=0, left_column=4)

        # Act
        result = bake.name_table_address(geometry, 25)

        # Assert
        assert result == 0x3800 + (1 * 32 + 5) * 2

    def test_a_picture_past_the_right_edge_is_refused(self):
        # Arrange
        columns, left_column = 24, 9

        # Act
        with pytest.raises(ValueError) as refused:
            bake.Geometry(columns=columns, rows=24, top_row=0, left_column=left_column)

        # Assert
        assert (
            str(refused.value) == "a picture of 24 columns at column 9 does not fit the name table"
        )


class TestEncodeFrames:
    def test_it_produces_one_chunk_list_per_frame(self):
        # Arrange
        frames = [gradient_frame(48, 64, shift) for shift in (0, 4)]
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)

        # Act
        result = bake.encode_frames(frames, geometry=geometry, budget=600, cap=40)

        # Assert
        assert len(result.frames) == 2

    def test_every_chunk_stays_inside_the_budget(self):
        # Arrange
        frames = [gradient_frame(48, 64, shift) for shift in range(4)]
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)

        # Act
        result = bake.encode_frames(frames, geometry=geometry, budget=300, cap=40)

        # Assert
        widest = max(len(chunk) for chunks in result.frames for chunk in chunks)
        assert widest <= 300

    def test_the_first_frame_uploads_a_palette(self):
        # Arrange
        frames = [gradient_frame(48, 64)]
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)

        # Act
        result = bake.encode_frames(frames, geometry=geometry, budget=600, cap=40)

        # Assert
        assert stream.CLOSE in write_kinds(result.frames[0])

    def test_a_frame_closes_with_its_palette_after_everything_else(self):
        # Arrange
        frames = [gradient_frame(48, 64)]
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)

        # Act
        result = bake.encode_frames(frames, geometry=geometry, budget=600, cap=40)

        # Assert
        kinds = write_targets(result.frames[0])
        assert kinds[-1] == "palette"
        assert kinds.count("palette") == 1

    def test_names_are_written_into_the_table_not_on_screen(self):
        # Arrange
        frames = [gradient_frame(48, 64), gradient_frame(48, 64, shift=9)]
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)

        # Act
        result = bake.encode_frames(frames, geometry=geometry, budget=600, cap=40)

        # Assert
        first = {address for kind, address in walk(result.frames[0]) if kind == stream.VRAM}
        second = {address for kind, address in walk(result.frames[1]) if kind == stream.VRAM}
        assert min(a for a in first if a >= console.BACK_TABLE_BASE) < console.NAME_TABLE_BASE
        assert any(a >= console.NAME_TABLE_BASE for a in second)

    def test_a_frame_in_transfer_shows_the_previous_frame_until_its_palette_lands(self):
        # Arrange
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)
        rng = np.random.default_rng(11)
        first = gradient_frame(48, 64)
        second = rng.integers(0, 255, (48, 64, 3), dtype=np.uint8)
        result = bake.encode_frames([first, second], geometry=geometry, budget=120, cap=40)
        machine = replay.Machine()
        for chunk in result.frames[0]:
            machine.apply(chunk)
        before = machine.display()

        # Act
        untouched = displays_before_the_palette(machine, result.frames[1], before)

        # Assert
        assert len(untouched) >= 2
        assert all(untouched)

    def test_a_repeated_frame_costs_less_than_the_first(self):
        # Arrange
        frames = [gradient_frame(48, 64), gradient_frame(48, 64)]
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)

        # Act
        result = bake.encode_frames(frames, geometry=geometry, budget=600, cap=40)

        # Assert
        first = sum(len(c) for c in result.frames[0])
        second = sum(len(c) for c in result.frames[1])
        assert second < first

    def test_a_bake_with_room_for_every_cell_leaves_none_unplaced(self):
        # Arrange
        frames = [gradient_frame(48, 64, shift) for shift in range(3)]
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)

        # Act
        result = bake.encode_frames(frames, geometry=geometry, budget=600, cap=40)

        # Assert
        assert result.unplaced == 0

    def test_a_ceiling_of_one_upload_leaves_cells_unplaced(self):
        # Arrange
        rng = np.random.default_rng(3)
        frames = [rng.integers(0, 255, (48, 64, 3), dtype=np.uint8) for _ in range(3)]
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)

        # Act
        result = bake.encode_frames(frames, geometry=geometry, budget=600, cap=40, upload_ceiling=1)

        # Assert
        assert result.unplaced > 0

    def test_no_frame_writes_a_pattern_over_a_referenced_slot(self):
        # Arrange
        frames = [gradient_frame(48, 64, shift) for shift in range(6)]
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)

        # Act
        result = bake.encode_frames(frames, geometry=geometry, budget=600, cap=30)

        # Assert
        assert result.collisions == 0

    def test_a_frame_of_the_wrong_size_is_refused(self):
        # Arrange
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)
        frames = [gradient_frame(40, 64)]

        # Act
        with pytest.raises(ValueError) as refused:
            bake.encode_frames(frames, geometry=geometry, budget=600, cap=40)

        # Assert
        assert str(refused.value) == ("frame 0 is 64x40, which does not match the geometry 64x48")

    def test_no_frames_is_refused(self):
        # Arrange
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)
        frames: list[np.ndarray] = []

        # Act
        with pytest.raises(ValueError) as refused:
            bake.encode_frames(frames, geometry=geometry, budget=600, cap=40)

        # Assert
        assert str(refused.value) == "a movie needs at least one frame"


class TestReusedSlotsSurvive:
    def _stream(self, count: int = 24):
        rng = np.random.default_rng(7)
        base = rng.integers(0, 255, size=(48, 64, 3), dtype=np.uint8)
        out = []
        for step in range(count):
            frame = base.copy()
            frame[:8, step % 56 : (step % 56) + 8] = 255
            out.append(frame)
        return out

    def test_no_upload_lands_on_a_slot_a_cell_is_reusing(self):
        # Arrange
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)
        frames = self._stream()

        # Act
        encoded = bake.encode_frames(
            frames, geometry=geometry, budget=1400, cap=40, reuse_threshold=0.02
        )

        # Assert
        assert encoded.collisions == 0

    def test_no_cell_is_left_unplaced(self):
        # Arrange
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)
        frames = self._stream()

        # Act
        encoded = bake.encode_frames(
            frames, geometry=geometry, budget=1400, cap=40, reuse_threshold=0.02
        )

        # Assert
        assert encoded.unplaced == 0

    def test_a_tiny_working_set_still_refuses_to_evict_a_reused_slot(self):
        # Arrange
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)
        frames = self._stream()

        # Act
        encoded = bake.encode_frames(
            frames,
            geometry=geometry,
            budget=1400,
            cap=40,
            capacity=60,
            reuse_threshold=0.02,
        )

        # Assert
        assert encoded.collisions == 0


class TestWorkingSetError:
    def test_a_bake_reports_it(self):
        # Arrange
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)
        frames = [
            np.random.default_rng(3).integers(0, 255, (48, 64, 3), dtype=np.uint8) for _ in range(2)
        ]

        # Act
        result = bake.encode_frames(frames, geometry=geometry, budget=900, cap=4)

        # Assert
        assert result.working_set > 0.0

    def test_it_is_zero_when_every_cell_keeps_its_own_tile(self):
        # Arrange
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)
        frames = [
            np.random.default_rng(3).integers(0, 255, (48, 64, 3), dtype=np.uint8) for _ in range(2)
        ]

        # Act
        result = bake.encode_frames(frames, geometry=geometry, budget=900, cap=48)

        # Assert
        assert result.working_set == 0.0

    def test_it_is_no_larger_than_the_total(self):
        # Arrange
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)
        frames = [
            np.random.default_rng(5).integers(0, 255, (48, 64, 3), dtype=np.uint8) for _ in range(3)
        ]

        # Act
        result = bake.encode_frames(frames, geometry=geometry, budget=900, cap=48)

        # Assert
        assert result.working_set <= result.error + 1e-9

    def test_a_cell_per_pattern_costs_nothing(self):
        # Arrange
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)
        frames = [np.random.default_rng(7).integers(0, 255, (48, 64, 3), dtype=np.uint8)]

        # Act
        result = bake.encode_frames(
            frames, geometry=geometry, budget=4000, cap=geometry.cells, reuse_threshold=0.0
        )

        # Assert
        assert result.working_set == pytest.approx(0.0, abs=1e-9)

    def test_a_loose_threshold_costs_more_than_a_tight_one(self):
        # Arrange
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)
        rng = np.random.default_rng(11)
        frames = [rng.integers(0, 255, (48, 64, 3), dtype=np.uint8) for _ in range(4)]
        tight = bake.encode_frames(
            frames, geometry=geometry, budget=900, cap=48, reuse_threshold=0.0001
        )

        # Act
        loose = bake.encode_frames(
            frames, geometry=geometry, budget=900, cap=48, reuse_threshold=0.5
        )

        # Assert
        assert loose.working_set > tight.working_set

    def test_it_agrees_with_replaying_the_stream(self):
        # Arrange
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)
        rng = np.random.default_rng(13)
        frames = [rng.integers(0, 255, (48, 64, 3), dtype=np.uint8) for _ in range(3)]

        # Act
        result = bake.encode_frames(
            frames, geometry=geometry, budget=900, cap=32, reuse_threshold=0.02
        )

        # Assert
        measured = replayed_working_set(result.frames, frames, geometry)
        assert result.working_set == pytest.approx(measured, rel=0.02, abs=1e-6)
