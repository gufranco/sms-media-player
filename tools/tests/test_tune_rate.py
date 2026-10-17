from __future__ import annotations

import numpy as np
import pytest
from lavfi import lavfi_clip
from tunecases import (
    SMALL,
    pick_on_working_set,
)

from smsggmedia import rate, tune

needs_ffmpeg = pytest.mark.ffmpeg


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    return lavfi_clip(tmp_path_factory.mktemp("tune") / "source.mp4", size="64x48")


@needs_ffmpeg
class TestPickRate:
    def test_it_returns_one_of_the_candidates(self, clip):
        # Arrange
        candidates = (12.0, 6.0)

        # Act
        choice = rate.pick_rate(
            tune.Footage(clip, start=0.0, duration=2.0, scaler="area"),
            tune.EncodeSettings(SMALL, budget=600, cap=40, reuse=0.008),
            denoise=0.0,
            candidates=candidates,
            sampling=tune.Sampling(windows=1, window_seconds=0.8),
        )

        # Assert
        assert choice.value in (12.0, 6.0)

    def test_it_prefers_the_fastest_rate_that_keeps_time(self, clip):
        # Arrange
        candidates = (12.0, 6.0)

        # Act
        choice = rate.pick_rate(
            tune.Footage(clip, start=0.0, duration=2.0, scaler="area"),
            tune.EncodeSettings(SMALL, budget=4000, cap=40, reuse=0.008),
            denoise=0.0,
            candidates=candidates,
            sampling=tune.Sampling(windows=1, window_seconds=0.8),
        )

        # Assert
        assert choice.value == 12.0

    def test_a_starved_budget_never_picks_a_faster_rate(self, clip):
        # Arrange
        footage = tune.Footage(clip, start=0.0, duration=2.0, scaler="area")
        common = {
            "denoise": 0.0,
            "candidates": (12.0, 6.0, 3.0),
            "sampling": tune.Sampling(windows=1, window_seconds=0.8),
        }
        rich_settings = tune.EncodeSettings(SMALL, budget=4000, cap=40, reuse=0.008)
        starved_settings = tune.EncodeSettings(SMALL, budget=60, cap=40, reuse=0.008)
        rich = rate.pick_rate(footage, rich_settings, **common)

        # Act
        starved = rate.pick_rate(footage, starved_settings, **common)

        # Assert
        assert starved.value <= rich.value

    def test_a_starved_budget_leaves_frames_late(self, clip):
        # Arrange
        candidates = (12.0,)

        # Act
        choice = rate.pick_rate(
            tune.Footage(clip, start=0.0, duration=2.0, scaler="area"),
            tune.EncodeSettings(SMALL, budget=60, cap=40, reuse=0.008),
            denoise=0.0,
            candidates=candidates,
            sampling=tune.Sampling(windows=1, window_seconds=0.8),
        )

        # Assert
        assert choice.scores[12.0].on_time < 1.0

    def test_it_scores_until_one_holds(self, clip):
        # Arrange
        candidates = (12.0, 8.0, 6.0)

        # Act
        choice = rate.pick_rate(
            tune.Footage(clip, start=0.0, duration=2.0, scaler="area"),
            tune.EncodeSettings(SMALL, budget=600, cap=40, reuse=0.008),
            denoise=0.0,
            candidates=candidates,
            sampling=tune.Sampling(windows=1, window_seconds=0.8),
        )

        # Assert
        scored = list(choice.scores)
        assert scored == sorted(candidates, reverse=True)[: len(scored)]
        assert choice.value == scored[-1]

    def test_a_score_reports_the_share_that_kept_time(self, clip):
        # Arrange
        candidates = (6.0,)

        # Act
        choice = rate.pick_rate(
            tune.Footage(clip, start=0.0, duration=2.0, scaler="area"),
            tune.EncodeSettings(SMALL, budget=600, cap=40, reuse=0.008),
            denoise=0.0,
            candidates=candidates,
            sampling=tune.Sampling(windows=1, window_seconds=0.8),
        )

        # Assert
        assert 0.0 <= choice.scores[6.0].on_time <= 1.0

    def test_no_candidates_is_refused(self, clip):
        # Arrange
        candidates: tuple[float, ...] = ()

        # Act
        with pytest.raises(ValueError) as refused:
            rate.pick_rate(
                tune.Footage(clip, start=0.0, duration=2.0, scaler="area"),
                tune.EncodeSettings(SMALL, budget=600, cap=40, reuse=0.008),
                denoise=0.0,
                candidates=candidates,
                sampling=tune.Sampling(windows=1, window_seconds=0.8),
            )

        # Assert
        assert str(refused.value) == "at least one frame rate candidate is required"

    def test_the_table_names_the_share_that_kept_time(self, clip):
        # Arrange
        candidates = (6.0,)

        # Act
        choice = rate.pick_rate(
            tune.Footage(clip, start=0.0, duration=2.0, scaler="area"),
            tune.EncodeSettings(SMALL, budget=600, cap=40, reuse=0.008),
            denoise=0.0,
            candidates=candidates,
            sampling=tune.Sampling(windows=1, window_seconds=0.8),
        )

        # Assert
        assert "on time" in choice.table()


def test_the_scoring_encodes_at_the_dither_it_is_given():
    # Arrange
    rng = np.random.default_rng(41)
    windows = [[rng.integers(100, 160, (48, 64, 3), dtype=np.uint8) for _ in range(2)]]
    plain = tune.score_windows(
        windows, settings=tune.EncodeSettings(SMALL, budget=1400, cap=60, reuse=0.0, dither=0.0)
    )

    # Act
    dithered = tune.score_windows(
        windows, settings=tune.EncodeSettings(SMALL, budget=1400, cap=60, reuse=0.0)
    )

    # Assert
    assert plain.error != dithered.error


class TestTiedScores:
    def test_the_cheapest_candidate_wins_among_scores_inside_the_tie(self):
        # Arrange
        scores = {
            0.004: tune.Score(error=0.0164, per_frame=3491.0, working_set=0.00501),
            0.002: tune.Score(error=0.0170, per_frame=4409.0, working_set=0.00497),
            0.001: tune.Score(error=0.0174, per_frame=5488.0, working_set=0.00570),
        }

        # Act
        choice = tune.decide(
            scores,
            key=lambda score: score.working_set,
            bar=tune.Bar(max_per_frame=None, stale_tolerance=None, tie=tune.SCORE_TIE),
            label="reuse",
            digits=4,
        )

        # Assert
        assert choice.value == 0.004

    def test_a_cheaper_candidate_outside_the_tie_does_not_win(self):
        # Arrange
        scores = {
            0.004: tune.Score(error=0.0163, per_frame=6725.0, working_set=0.00740),
            0.002: tune.Score(error=0.0164, per_frame=7108.0, working_set=0.00677),
        }

        # Act
        choice = tune.decide(
            scores,
            key=lambda score: score.working_set,
            bar=tune.Bar(max_per_frame=None, stale_tolerance=None, tie=tune.SCORE_TIE),
            label="reuse",
            digits=4,
        )

        # Assert
        assert choice.value == 0.002

    def test_without_a_tie_the_lowest_score_wins_however_close(self):
        # Arrange
        scores = {
            0.004: tune.Score(error=0.0164, per_frame=3491.0, working_set=0.00501),
            0.002: tune.Score(error=0.0170, per_frame=4409.0, working_set=0.00497),
        }

        # Act
        choice = tune.decide(
            scores,
            key=lambda score: score.working_set,
            bar=tune.Bar(max_per_frame=None, stale_tolerance=None),
            label="reuse",
            digits=4,
        )

        # Assert
        assert choice.value == 0.002

    def test_a_negative_tie_is_refused(self):
        # Arrange
        scores = {0.004: tune.Score(error=0.0164, per_frame=3491.0)}

        # Act
        with pytest.raises(ValueError) as refused:
            tune.decide(
                scores,
                key=lambda score: score.error,
                bar=tune.Bar(max_per_frame=None, stale_tolerance=None, tie=-0.01),
                label="reuse",
                digits=4,
            )

        # Assert
        assert str(refused.value) == "a tie tolerance must not be negative, got -0.01"


class TestTieBoundaries:
    def test_a_score_exactly_at_the_tie_edge_still_ties(self):
        # Arrange
        scores = {
            0.004: tune.Score(error=0.0, per_frame=1000.0, working_set=0.105),
            0.002: tune.Score(error=0.0, per_frame=2000.0, working_set=0.100),
        }

        # Act
        choice = pick_on_working_set(scores, tie=0.05)

        # Assert
        assert choice.value == 0.004

    def test_a_tied_candidate_over_the_byte_ceiling_cannot_win(self):
        # Arrange
        scores = {
            0.004: tune.Score(error=0.0, per_frame=1000.0, working_set=0.101),
            0.002: tune.Score(error=0.0, per_frame=2000.0, working_set=0.100),
        }

        # Act
        choice = pick_on_working_set(scores, tie=0.05, max_per_frame=1500.0)

        # Assert
        assert choice.value == 0.004

    def test_with_nothing_under_the_ceiling_the_cheapest_wins_whatever_the_tie(self):
        # Arrange
        scores = {
            0.008: tune.Score(error=0.0, per_frame=500.0, working_set=0.101),
            0.002: tune.Score(error=0.0, per_frame=2000.0, working_set=0.100),
            0.004: tune.Score(error=0.0, per_frame=1000.0, working_set=0.300),
        }

        # Act
        choice = pick_on_working_set(scores, tie=0.05, max_per_frame=400.0)

        # Assert
        assert (choice.value, choice.fits) == (0.008, False)

    def test_a_perfect_score_ties_only_with_another_perfect_one(self):
        # Arrange
        scores = {
            0.004: tune.Score(error=0.0, per_frame=1000.0, working_set=0.001),
            0.002: tune.Score(error=0.0, per_frame=2000.0, working_set=0.0),
        }

        # Act
        choice = pick_on_working_set(scores, tie=0.05)

        # Assert
        assert choice.value == 0.002
