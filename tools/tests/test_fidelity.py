import numpy as np
import pytest

from smsmovie import fidelity, palettes, pattern, smscolor

CELL = pattern.TILE_PX


def cells(*pictures: np.ndarray) -> np.ndarray:
    return np.stack(pictures).reshape(len(pictures), -1).astype(np.float32)


def checker(first: float, second: float, *, phase: int = 0) -> np.ndarray:
    rows, columns = np.mgrid[0:CELL, 0:CELL]
    pick = (rows + columns + phase) % 2 == 0
    out = np.where(pick[..., None], first, second)
    return np.repeat(out, 3, axis=2)


class TestPerceivedCells:
    def test_the_shape_is_kept(self):
        # Arrange
        features = cells(checker(0.2, 0.8), checker(0.4, 0.6))

        # Act
        result = fidelity.perceived_cells(features)

        # Assert
        assert result.shape == features.shape

    def test_a_flat_cell_is_unchanged(self):
        # Arrange
        features = cells(np.full((CELL, CELL, 3), 0.5))

        # Act
        result = fidelity.perceived_cells(features)

        # Assert
        assert np.allclose(result, features)

    def test_two_phases_of_one_dither_end_up_close(self):
        # Arrange
        plain = cells(checker(0.2, 0.8), checker(0.2, 0.8, phase=1))
        before = float(np.abs(plain[0] - plain[1]).mean())

        # Act
        result = fidelity.perceived_cells(plain)

        # Assert
        after = float(np.abs(result[0] - result[1]).mean())
        assert after < before / 4

    def test_a_dither_stays_apart_from_a_different_colour(self):
        # Arrange
        features = cells(checker(0.2, 0.8), np.full((CELL, CELL, 3), 0.9))

        # Act
        result = fidelity.perceived_cells(features)

        # Assert
        assert float(np.abs(result[0] - result[1]).mean()) > 0.3

    def test_rows_that_are_not_whole_cells_are_refused(self):
        # Arrange
        features = np.zeros((2, 10), dtype=np.float32)

        # Act
        with pytest.raises(ValueError) as refused:
            fidelity.perceived_cells(features)

        # Assert
        assert str(refused.value) == "features must be whole cells of 192 values, got shape (2, 10)"


def two_cells(shown: list[int]) -> dict[str, object]:
    fitted = palettes.FramePalettes(
        cram=np.zeros(32, dtype=np.uint8),
        choice=np.zeros(2, dtype=np.uint8),
        indices=np.zeros((2, 8, 8), dtype=np.uint8),
        rows=1,
        columns=2,
    )
    return {
        "fitted": fitted,
        "lab": smscolor.oklab_palette(),
        "slots": np.array([1, 4], dtype=np.int32),
        "data": np.zeros((2, pattern.PATTERN_BYTES), dtype=np.uint8),
        "shown_slot": np.array(shown, dtype=np.int32),
        "flips": (np.zeros(2, dtype=np.bool_), np.zeros(2, dtype=np.bool_)),
    }


class TestWhatACellShows:
    def test_resident_slots_are_scored(self):
        # Arrange
        arguments = two_cells([4, 1])

        # Act
        shown = fidelity._shown_cells(**arguments)

        # Assert
        assert shown.shape == (2, pattern.TILE_PX, pattern.TILE_PX, 3)

    @pytest.mark.parametrize("slot", [2, 9])
    def test_a_slot_with_no_resident_pattern_is_refused(self, slot):
        # Arrange
        arguments = two_cells([1, slot])

        # Act
        with pytest.raises(ValueError) as refused:
            fidelity._shown_cells(**arguments)

        # Assert
        assert str(refused.value) == f"cell 1 shows slot {slot}, which holds no resident pattern"
