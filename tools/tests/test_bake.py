import numpy as np
import pytest
from fmvcore import colour

from smsggmedia import bake, console, lattice, limits, palettes, replay, stream, target


def gradient_frame(height: int, width: int, shift: int = 0) -> np.ndarray:
    y, x = np.mgrid[0:height, 0:width]
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[..., 0] = ((x + shift) * 3) % 256
    frame[..., 1] = (y * 5) % 256
    frame[..., 2] = ((x + y + shift) * 7) % 256
    return frame


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
        first = {address for kind, address in _walk(result.frames[0]) if kind == stream.VRAM}
        second = {address for kind, address in _walk(result.frames[1]) if kind == stream.VRAM}
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


class TestUploadCeiling:
    def _cut(self, geometry, count=6):
        rng = np.random.default_rng(23)
        a = rng.integers(0, 255, (geometry.height, geometry.width, 3), dtype=np.uint8)
        b = rng.integers(0, 255, (geometry.height, geometry.width, 3), dtype=np.uint8)
        return [a] * (count // 2) + [b] * (count - count // 2)

    def test_no_ceiling_is_the_default(self):
        # Arrange
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)
        frames = self._cut(geometry)

        # Act
        result = bake.encode_frames(frames, geometry=geometry, budget=900, cap=48)

        # Assert
        assert result.uploaded > 0

    def test_a_ceiling_caps_what_one_frame_uploads(self):
        # Arrange
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)
        frames = self._cut(geometry)

        # Act
        result = bake.encode_frames(frames, geometry=geometry, budget=900, cap=48, upload_ceiling=4)

        # Assert
        assert max(result.per_frame_uploads) <= 4

    def test_a_ceiling_shortens_the_worst_frame(self):
        # Arrange
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)
        frames = self._cut(geometry)
        loose = bake.encode_frames(frames, geometry=geometry, budget=300, cap=48)

        # Act
        tight = bake.encode_frames(frames, geometry=geometry, budget=300, cap=48, upload_ceiling=4)

        # Assert
        assert max(len(c) for c in tight.frames) < max(len(c) for c in loose.frames)

    def test_the_cells_it_could_not_serve_are_reported(self):
        # Arrange
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)
        frames = self._cut(geometry)

        # Act
        result = bake.encode_frames(frames, geometry=geometry, budget=900, cap=48, upload_ceiling=2)

        # Assert
        assert result.unplaced > 0

    def test_the_patterns_kept_are_the_ones_most_cells_want(self):
        # Arrange
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)
        flat = np.zeros((geometry.height, geometry.width, 3), dtype=np.uint8)
        flat[:, :16] = 200
        rng = np.random.default_rng(5)
        noisy = rng.integers(0, 255, (geometry.height, geometry.width, 3), dtype=np.uint8)

        # Act
        result = bake.encode_frames(
            [flat, noisy], geometry=geometry, budget=900, cap=48, upload_ceiling=3
        )

        # Assert
        assert result.unplaced < geometry.cells

    def test_a_ceiling_of_zero_is_refused_because_it_never_draws(self):
        # Arrange
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)
        frames = self._cut(geometry)

        # Act
        with pytest.raises(ValueError) as refused:
            bake.encode_frames(frames, geometry=geometry, budget=900, cap=48, upload_ceiling=0)

        # Assert
        assert str(refused.value) == "an upload ceiling of 0 would never draw a pattern"

    def test_a_ceiling_of_one_scores_a_number(self):
        # Arrange
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)
        frames = self._cut(geometry)

        # Act
        result = bake.encode_frames(frames, geometry=geometry, budget=900, cap=48, upload_ceiling=1)

        # Assert
        assert bool(np.isfinite(result.error)) is True

    def test_a_negative_ceiling_is_refused(self):
        # Arrange
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)
        frames = self._cut(geometry)

        # Act
        with pytest.raises(ValueError) as refused:
            bake.encode_frames(frames, geometry=geometry, budget=900, cap=48, upload_ceiling=-1)

        # Assert
        assert str(refused.value) == "an upload ceiling of -1 would never draw a pattern"

    def test_every_frame_reports_what_it_uploaded(self):
        # Arrange
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)
        frames = self._cut(geometry)

        # Act
        result = bake.encode_frames(frames, geometry=geometry, budget=900, cap=48)

        # Assert
        assert len(result.per_frame_uploads) == len(frames)


def displays_before_the_palette(
    machine: replay.Machine, chunks: list[bytes], before: np.ndarray
) -> list[bool]:
    untouched = []
    for chunk in chunks:
        if "palette" in write_targets([chunk]):
            break
        machine.apply(chunk)
        untouched.append(np.array_equal(machine.display(), before))
    return untouched


def replayed_working_set(
    encoded_frames: list[list[bytes]], frames: list[np.ndarray], geometry: bake.Geometry
) -> float:
    machine = replay.Machine()
    measured = []
    kept = None
    for index, chunks in enumerate(encoded_frames):
        for chunk in chunks:
            machine.apply(chunk)
        shown = machine.render(
            columns=geometry.columns, rows=geometry.rows, top_row=geometry.top_row
        )
        fitted = palettes.fit_or_keep(
            frames[index],
            kept,
            margin=limits.PALETTE_KEEP_MARGIN,
            ordered_dither=limits.DEFAULT_DITHER,
        )
        kept = fitted.cram
        floor = fitted.render()
        a = colour.srgb_to_oklab(shown.astype(np.float32) / 255.0)
        b = colour.srgb_to_oklab(floor.astype(np.float32) / 255.0)
        measured.append(float(((a - b) ** 2).sum(axis=-1).mean()))
    return float(np.mean(measured))


def write_kinds(chunks: list[bytes]) -> list[int]:
    return [kind for kind, _ in _walk(chunks)]


def write_targets(chunks: list[bytes]) -> list[str]:
    names = []
    for kind, address in _walk(chunks):
        if kind in stream.CLOSE_KINDS:
            names.append("palette")
        else:
            names.append("names" if address >= console.BACK_TABLE_BASE else "patterns")
    return names


def _walk(chunks: list[bytes]) -> list[tuple[int, int]]:
    found = []
    for chunk in chunks:
        pos = 0
        while pos < len(chunk) and chunk[pos] in (stream.VRAM, *stream.CLOSE_KINDS):
            kind = chunk[pos]
            if kind == stream.VRAM:
                found.append((kind, chunk[pos + 1] | (chunk[pos + 2] << 8)))
                pos += 4 + chunk[pos + 3]
            else:
                found.append((kind, chunk[pos + 1]))
                pos += 2 + stream.close_bytes(kind)
    return found


class TestTheBudgetFloor:
    def test_a_budget_with_no_room_beside_the_closing_run_is_refused(self):
        # Arrange
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)
        budget = 30

        # Act
        with pytest.raises(ValueError) as refused:
            bake.Encoder(geometry=geometry, budget=budget, cap=40)

        # Assert
        assert str(refused.value) == (
            "a budget of 30 bytes leaves no room for a run beside the "
            "34 every chunk keeps for a deferred closing run"
        )


class TestSlotPressure:
    def test_a_frame_short_of_free_slots_merges_instead_of_leaving_stale_cells(self):
        # Arrange
        rng = np.random.default_rng(29)
        geometry = bake.Geometry(columns=32, rows=24, top_row=0)
        frames = [rng.integers(0, 256, (192, 256, 3), dtype=np.uint8) for _ in range(2)]

        # Act
        result = bake.encode_frames(frames, geometry=geometry, budget=1800, cap=300)

        # Assert
        assert result.unplaced == 0


class TestTheShippedDither:
    def test_the_encoder_dithers_at_the_shipped_strength_unless_told_otherwise(self):
        # Arrange
        geometry = bake.Geometry(columns=4, rows=3, top_row=0)
        frames = [np.full((24, 32, 3), 128, dtype=np.uint8)]
        explicit = bake.encode_frames(
            frames, geometry=geometry, budget=1800, cap=60, dither=limits.DEFAULT_DITHER
        )

        # Act
        result = bake.encode_frames(frames, geometry=geometry, budget=1800, cap=60)

        # Assert
        assert result.frames == explicit.frames


def closing_palettes(chunks: list[bytes]) -> bytes:
    last = chunks[-1]
    run = last[-(stream.CLOSE_HEADER + stream.CLOSE_BYTES + 1) : -1]
    if run[0] != stream.CLOSE:
        msg = "the frame does not end with its closing run"
        raise AssertionError(msg)
    return run[stream.CLOSE_HEADER :]


class TestPalettesCarryOver:
    def test_a_still_picture_keeps_its_palettes(self):
        # Arrange
        rng = np.random.default_rng(17)
        base = gradient_frame(48, 64)
        frames = [
            np.clip(base.astype(np.int16) + rng.integers(-4, 5, base.shape), 0, 255).astype(
                np.uint8
            )
            for _ in range(3)
        ]
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)

        # Act
        result = bake.encode_frames(frames, geometry=geometry, budget=1800, cap=60)

        # Assert
        assert len({closing_palettes(chunks) for chunks in result.frames}) == 1

    def test_a_cut_refits_the_palettes(self):
        # Arrange
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)
        frames = [
            np.full((48, 64, 3), (200, 40, 40), np.uint8),
            np.full((48, 64, 3), (40, 40, 200), np.uint8),
        ]

        # Act
        result = bake.encode_frames(frames, geometry=geometry, budget=1800, cap=60)

        # Assert
        assert closing_palettes(result.frames[0]) != closing_palettes(result.frames[1])


class TestMergeReport:
    def test_each_frame_reports_the_cells_it_merged(self):
        # Arrange
        rng = np.random.default_rng(23)
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)
        frames = [rng.integers(0, 256, (48, 64, 3), dtype=np.uint8) for _ in range(2)]

        # Act
        result = bake.encode_frames(frames, geometry=geometry, budget=1800, cap=8)

        # Assert
        assert result.per_frame_merged == [6 * 8 - 8, 6 * 8 - 8]


class TestTheGameGearTarget:
    def test_a_frame_closes_with_a_wide_palette_run(self):
        # Arrange
        frames = [gradient_frame(48, 64)]
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)

        # Act
        result = bake.encode_frames(
            frames, geometry=geometry, budget=600, cap=40, system=target.GAME_GEAR
        )

        # Assert
        assert stream.CLOSE_WIDE in write_kinds(result.frames[0])

    def test_its_palette_run_carries_every_entry_widened(self):
        # Arrange
        frames = [gradient_frame(48, 64)]
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)
        encoder = bake.Encoder(geometry=geometry, budget=600, cap=40, system=target.GAME_GEAR)

        # Act
        chunks = encoder.add(frames[0])

        # Assert
        assert chunks[-1][-(64 + 1) : -1] == lattice.GAME_GEAR.cram_bytes(encoder.cram)

    def test_its_budget_floor_keeps_room_for_the_wider_run(self):
        # Arrange
        geometry = bake.Geometry(columns=8, rows=6, top_row=0)

        # Act
        with pytest.raises(ValueError) as refused:
            bake.Encoder(geometry=geometry, budget=70, cap=40, system=target.GAME_GEAR)

        # Assert
        assert str(refused.value) == (
            "a budget of 70 bytes leaves no room for a run beside the "
            "66 every chunk keeps for a deferred closing run"
        )
