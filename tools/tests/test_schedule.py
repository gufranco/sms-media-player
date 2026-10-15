from __future__ import annotations

import numpy as np
import pytest

from smsmovie import bake, schedule

GEOMETRY = bake.Geometry(columns=8, rows=6, top_row=0)
SLOT = 6
FPS = 10.0


def flat(level: int) -> np.ndarray:
    return np.full((GEOMETRY.height, GEOMETRY.width, 3), level, dtype=np.uint8)


def noisy(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(0, 255, (GEOMETRY.height, GEOMETRY.width, 3), dtype=np.uint8)


def encoder(budget: int) -> bake.Encoder:
    return bake.Encoder(geometry=GEOMETRY, budget=budget, cap=40)


class TestCheapFrames:
    def test_every_frame_is_shown_when_each_fits_its_slot(self):
        # Arrange
        decoded = [flat(level) for level in range(0, 200, 20)]
        cheap = encoder(4000)

        # Act
        result = schedule.by_clock(decoded, fps=FPS, slot=SLOT, encoder=cheap)

        # Assert
        assert result.picks == list(range(1, 10))

    def test_a_frame_that_fits_lands_within_its_slot(self):
        # Arrange
        decoded = [flat(level) for level in range(0, 200, 20)]
        cheap = encoder(4000)

        # Act
        result = schedule.by_clock(decoded, fps=FPS, slot=SLOT, encoder=cheap)

        # Assert
        assert max(abs(lag) for lag in result.lags) * schedule.FIELD_HZ <= 1


class TestTheEndOfTheFilm:
    def test_cheap_frames_reach_the_last_decoded_frame(self):
        # Arrange
        decoded = [flat(level) for level in range(0, 200, 20)]
        cheap = encoder(4000)

        # Act
        result = schedule.by_clock(decoded, fps=FPS, slot=SLOT, encoder=cheap)

        # Assert
        assert (result.picks[-1], result.unshown_tail) == (9, 0)

    def test_frames_the_clock_passed_at_the_end_are_counted(self):
        # Arrange
        decoded = [noisy(seed) for seed in range(30)]
        tight = encoder(60)

        # Act
        result = schedule.by_clock(decoded, fps=FPS, slot=SLOT, encoder=tight)

        # Assert
        assert result.unshown_tail > 0


class TestExpensiveFrames:
    def test_frames_are_skipped_rather_than_falling_behind(self):
        # Arrange
        decoded = [noisy(seed) for seed in range(30)]
        tight = encoder(60)

        # Act
        result = schedule.by_clock(decoded, fps=FPS, slot=SLOT, encoder=tight)

        # Assert
        assert len(result.picks) < len(decoded)

    def test_the_lag_never_grows_past_one_transfer(self):
        # Arrange
        decoded = [noisy(seed) for seed in range(30)]
        tight = encoder(60)
        rounding = schedule.field_of(1, fps=FPS) / 2

        # Act
        result = schedule.by_clock(decoded, fps=FPS, slot=SLOT, encoder=tight)

        # Assert
        longest = max(len(chunks) for chunks in result.frames)
        assert max(result.lags) * schedule.FIELD_HZ <= longest - SLOT + 1 + rounding

    def test_the_stream_lasts_about_as_long_as_the_film(self):
        # Arrange
        decoded = [noisy(seed) for seed in range(30)]
        tight = encoder(60)
        film = schedule.field_of(len(decoded), fps=FPS)

        # Act
        result = schedule.by_clock(decoded, fps=FPS, slot=SLOT, encoder=tight)

        # Assert
        fields = sum(len(chunks) for chunks in result.frames)
        assert fields <= film + max(len(chunks) for chunks in result.frames)

    def test_picks_only_move_forward(self):
        # Arrange
        decoded = [noisy(seed) for seed in range(30)]
        tight = encoder(60)

        # Act
        result = schedule.by_clock(decoded, fps=FPS, slot=SLOT, encoder=tight)

        # Assert
        assert result.picks == sorted(set(result.picks))


class TestPacing:
    def test_without_pacing_a_cheap_frame_takes_its_own_length(self):
        # Arrange
        decoded = [flat(level) for level in range(0, 60, 20)]
        cheap = encoder(4000)

        # Act
        result = schedule.by_clock(decoded, fps=FPS, slot=SLOT, encoder=cheap, pace=False)

        # Assert
        assert len(result.frames[1]) < SLOT


class TestRefusals:
    def test_no_frames_is_refused(self):
        # Arrange
        decoded: list[np.ndarray] = []
        plain = encoder(400)

        # Act
        with pytest.raises(ValueError) as refused:
            schedule.by_clock(decoded, fps=FPS, slot=SLOT, encoder=plain)

        # Assert
        assert str(refused.value) == "a movie needs at least one frame"

    def test_a_slot_under_one_field_is_refused(self):
        # Arrange
        decoded = [flat(0)]
        plain = encoder(400)

        # Act
        with pytest.raises(ValueError) as refused:
            schedule.by_clock(decoded, fps=FPS, slot=0, encoder=plain)

        # Assert
        assert str(refused.value) == "a frame must occupy at least one field"


class TestDue:
    def test_the_first_slot_shows_the_frame_for_its_last_field(self):
        # Arrange
        field = 0

        # Act
        result = schedule.due_at(field, fps=FPS, slot=SLOT)

        # Assert
        assert result == 1

    def test_a_later_slot_shows_the_frame_for_its_last_field(self):
        # Arrange
        field = 60

        # Act
        result = schedule.due_at(field, fps=FPS, slot=SLOT)

        # Assert
        assert result == 11


class TestTheStart:
    def test_an_expensive_first_frame_is_a_lead_in_rather_than_a_lag(self):
        # Arrange
        decoded = [noisy(seed) for seed in range(30)]
        tight = encoder(60)
        one_frame = schedule.field_of(1, fps=FPS)

        # Act
        result = schedule.by_clock(decoded, fps=FPS, slot=SLOT, encoder=tight)

        # Assert
        assert result.lead == len(result.frames[0]) - SLOT
        assert abs(result.lags[0]) * schedule.FIELD_HZ <= one_frame

    def test_a_cheap_first_frame_needs_no_lead_in(self):
        # Arrange
        decoded = [flat(level) for level in range(0, 200, 20)]
        cheap = encoder(4000)

        # Act
        result = schedule.by_clock(decoded, fps=FPS, slot=SLOT, encoder=cheap)

        # Assert
        assert result.lead == 0


class TestASingleFrame:
    def test_a_one_frame_decode_shows_that_frame(self):
        # Arrange
        decoded = [flat(3)]

        # Act
        result = schedule.by_clock(decoded, fps=FPS, slot=SLOT, encoder=encoder(1800))

        # Assert
        assert result.picks == [0]
