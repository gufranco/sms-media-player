import numpy as np
import pytest
from bakeframes import (
    gradient_frame,
    write_kinds,
)

from smsggmedia import bake, lattice, limits, stream, target


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
