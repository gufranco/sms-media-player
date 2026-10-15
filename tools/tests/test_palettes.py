import numpy as np
import pytest

from smsmovie import palettes, pattern, smscolor


def fresh_fit(frame, **options):
    return palettes.fit_or_keep(frame, None, margin=0.0, **options)


def tiles_of(colours: list[int], count: int = 1) -> np.ndarray:
    out = np.zeros((len(colours) * count, pattern.TILE_PX, pattern.TILE_PX), dtype=np.uint8)
    for i, colour in enumerate(colours):
        out[i * count : (i + 1) * count] = colour
    return out


class TestChooseEntries:
    def test_it_returns_the_requested_number_of_entries(self):
        # Arrange
        present = np.arange(40, dtype=np.uint8)
        counts = np.ones(40, dtype=np.int64)

        # Act
        result = palettes.choose_entries(present, counts, smscolor.oklab_palette(), 16)

        # Assert
        assert result.shape == (16,)

    def test_fewer_present_colours_than_slots_are_all_kept(self):
        # Arrange
        present = np.array([0, 5, 63], dtype=np.uint8)
        counts = np.array([10, 10, 10], dtype=np.int64)

        # Act
        result = palettes.choose_entries(present, counts, smscolor.oklab_palette(), 16)

        # Assert
        assert set(result.tolist()) >= {0, 5, 63}

    def test_entries_are_unique(self):
        # Arrange
        present = np.arange(64, dtype=np.uint8)
        counts = np.ones(64, dtype=np.int64)

        # Act
        result = palettes.choose_entries(present, counts, smscolor.oklab_palette(), 16)

        # Assert
        assert len(set(result.tolist())) == 16

    def test_it_is_deterministic(self):
        # Arrange
        present = np.arange(64, dtype=np.uint8)
        counts = np.arange(1, 65, dtype=np.int64)
        lab = smscolor.oklab_palette()
        first = palettes.choose_entries(present, counts, lab, 16)

        # Act
        second = palettes.choose_entries(present, counts, lab, 16)

        # Assert
        assert first.tolist() == second.tolist()

    def test_asking_for_no_entries_is_refused(self):
        # Arrange
        present = np.array([0], dtype=np.uint8)
        counts = np.array([1], dtype=np.int64)
        lab = smscolor.oklab_palette()

        # Act
        with pytest.raises(ValueError) as refused:
            palettes.choose_entries(present, counts, lab, 0)

        # Assert
        assert str(refused.value) == "a palette needs at least one entry"


class TestFitFrame:
    def test_it_produces_two_palettes_of_sixteen(self):
        # Arrange
        rng = np.random.default_rng(7)
        frame = rng.integers(0, 256, size=(16, 32, 3), dtype=np.uint8)

        # Act
        result = fresh_fit(frame)

        # Assert
        assert result.cram.shape == (smscolor.CRAM_BYTES,)

    def test_every_cram_entry_is_a_console_colour(self):
        # Arrange
        rng = np.random.default_rng(8)
        frame = rng.integers(0, 256, size=(16, 32, 3), dtype=np.uint8)

        # Act
        result = fresh_fit(frame)

        # Assert
        assert int(result.cram.max()) < smscolor.COLOUR_COUNT

    def test_each_cell_picks_one_of_the_two_palettes(self):
        # Arrange
        rng = np.random.default_rng(9)
        frame = rng.integers(0, 256, size=(16, 32, 3), dtype=np.uint8)

        # Act
        result = fresh_fit(frame)

        # Assert
        assert set(np.unique(result.choice).tolist()) <= {0, 1}

    def test_indices_stay_inside_a_palette(self):
        # Arrange
        rng = np.random.default_rng(10)
        frame = rng.integers(0, 256, size=(16, 32, 3), dtype=np.uint8)

        # Act
        result = fresh_fit(frame)

        # Assert
        assert int(result.indices.max()) < smscolor.PALETTE_ENTRIES

    def test_a_flat_frame_reproduces_its_own_colour(self):
        # Arrange
        frame = np.full((16, 32, 3), 255, dtype=np.uint8)

        # Act
        result = fresh_fit(frame)

        # Assert
        assert result.render().min() == 255

    def test_a_two_colour_frame_survives_the_round_trip(self):
        # Arrange
        frame = np.zeros((16, 32, 3), dtype=np.uint8)
        frame[:, 16:] = 255

        # Act
        result = fresh_fit(frame)

        # Assert
        rendered = result.render()
        assert rendered[0, 0].tolist() == [0, 0, 0]
        assert rendered[0, 31].tolist() == [255, 255, 255]

    def test_the_cell_count_matches_the_frame_geometry(self):
        # Arrange
        frame = np.zeros((24, 32, 3), dtype=np.uint8)

        # Act
        result = fresh_fit(frame)

        # Assert
        assert result.choice.shape == (3 * 4,)

    def test_a_frame_without_a_colour_axis_is_refused(self):
        # Arrange
        frame = np.zeros((16, 32), dtype=np.uint8)

        # Act
        with pytest.raises(ValueError) as refused:
            fresh_fit(frame)

        # Assert
        assert str(refused.value) == "expected a trailing RGB axis, got shape (16, 32)"


class TestBackdropEntry:
    def test_the_border_entry_is_held_at_black(self):
        # Arrange
        frame = (np.arange(64 * 64 * 3, dtype=np.uint8) % 251).reshape(64, 64, 3)

        # Act
        fitted = fresh_fit(frame, chroma_weight=1.0)

        # Assert
        table = fitted.cram.reshape(smscolor.PALETTE_COUNT, smscolor.PALETTE_ENTRIES)
        assert table[1][palettes.BACKDROP_ENTRY] == palettes.BACKDROP_COLOUR

    def test_it_holds_on_a_bright_frame_too(self):
        # Arrange
        frame = np.full((64, 64, 3), 240, dtype=np.uint8)

        # Act
        fitted = fresh_fit(frame, chroma_weight=1.0)

        # Assert
        table = fitted.cram.reshape(smscolor.PALETTE_COUNT, smscolor.PALETTE_ENTRIES)
        assert table[1][palettes.BACKDROP_ENTRY] == palettes.BACKDROP_COLOUR

    def test_the_first_palette_is_left_alone(self):
        # Arrange
        frame = np.full((64, 64, 3), 240, dtype=np.uint8)

        # Act
        fitted = fresh_fit(frame, chroma_weight=1.0)

        # Assert
        table = fitted.cram.reshape(smscolor.PALETTE_COUNT, smscolor.PALETTE_ENTRIES)
        assert table[0][palettes.BACKDROP_ENTRY] != palettes.BACKDROP_COLOUR


class TestOrderedDither:
    def test_a_pale_gradient_takes_more_than_one_colour_per_cell(self):
        # Arrange
        frame = np.full((8, 8, 3), 128, dtype=np.uint8)

        # Act
        result = fresh_fit(frame, ordered_dither=1.0)

        # Assert
        assert np.unique(result.indices).size == 2

    def test_no_ordered_dither_keeps_a_flat_cell_flat(self):
        # Arrange
        frame = np.full((8, 8, 3), 128, dtype=np.uint8)

        # Act
        result = fresh_fit(frame, ordered_dither=smscolor.NO_DITHER)

        # Assert
        assert np.unique(result.indices).size == 1


NUDGE_SEED = 5
WHITE = (255, 255, 255)


def flat_frame(colour: tuple[int, int, int], noise_seed: int | None = None) -> np.ndarray:
    frame = np.zeros((16, 32, 3), dtype=np.uint8)
    frame[:] = colour
    frame[:, 16:] = (colour[2], colour[0], colour[1])
    if noise_seed is not None:
        rng = np.random.default_rng(noise_seed)
        frame = np.clip(frame.astype(np.int16) + rng.integers(-6, 7, frame.shape), 0, 255)
    return frame.astype(np.uint8)


def nudged_pair() -> tuple[palettes.FramePalettes, np.ndarray]:
    rng = np.random.default_rng(NUDGE_SEED)
    base = rng.integers(0, 256, (16, 16, 3), dtype=np.uint8)
    frame = base.copy()
    frame[:1, :8] = WHITE
    return fresh_fit(base), frame


class TestKeepingPalettes:
    def test_with_nothing_to_keep_the_frame_is_fitted_fresh(self):
        # Arrange
        frame = flat_frame((170, 85, 0))

        # Act
        result = palettes.fit_or_keep(frame, None, margin=0.3)

        # Assert
        assert result.render().tolist() == frame.tolist()

    def test_palettes_that_still_fit_are_kept_over_a_slightly_better_fit(self):
        # Arrange
        previous, frame = nudged_pair()

        # Act
        result = palettes.fit_or_keep(frame, previous.cram, margin=0.3)

        # Assert
        assert result.cram.tolist() == previous.cram.tolist()

    def test_with_no_margin_the_slightly_better_fit_wins(self):
        # Arrange
        previous, frame = nudged_pair()

        # Act
        result = palettes.fit_or_keep(frame, previous.cram, margin=0.0)

        # Assert
        assert result.cram.tolist() != previous.cram.tolist()

    def test_the_nudged_frame_really_fits_differently(self):
        # Arrange
        previous, frame = nudged_pair()

        # Act
        fresh = fresh_fit(frame)

        # Assert
        assert fresh.cram.tolist() != previous.cram.tolist()

    def test_palettes_from_a_different_picture_are_refitted(self):
        # Arrange
        previous = fresh_fit(flat_frame((170, 85, 0)))
        frame = flat_frame((0, 85, 255))

        # Act
        result = palettes.fit_or_keep(frame, previous.cram, margin=0.3)

        # Assert
        assert result.render().tolist() == frame.tolist()

    def test_a_negative_margin_is_refused(self):
        # Arrange
        frame = flat_frame((0, 0, 0))

        # Act
        with pytest.raises(ValueError) as raised:
            palettes.fit_or_keep(frame, None, margin=-0.1)

        # Assert
        assert str(raised.value) == "a palette keep margin must not be negative, got -0.1"
