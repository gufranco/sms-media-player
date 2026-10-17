from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import pytest
from lavfi import lavfi_clip
from tunecases import (
    GEOMETRY,
    SMALL,
    pick,
)

from smsggmedia import tune

needs_ffmpeg = pytest.mark.ffmpeg


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    return lavfi_clip(tmp_path_factory.mktemp("tune") / "source.mp4", size="64x48")


def test_a_single_window_covers_the_whole_clip_when_the_clip_is_short():
    # Arrange
    duration = 1.0

    # Act
    windows = tune.sample_windows(start=4.0, duration=duration, windows=3, window_seconds=2.0)

    # Assert
    assert windows == [(4.0, 1.0)]


def test_windows_span_the_clip_and_stay_inside_it():
    # Arrange
    start = 10.0
    duration = 20.0

    # Act
    windows = tune.sample_windows(start=start, duration=duration, windows=3, window_seconds=2.0)

    # Assert
    assert len(windows) == 3
    assert windows[0][0] == 10.0
    assert windows[-1][0] + windows[-1][1] == pytest.approx(30.0)
    assert all(span == 2.0 for _, span in windows)


def test_windows_are_ordered_and_do_not_overlap():
    # Arrange
    duration = 30.0

    # Act
    windows = tune.sample_windows(start=0.0, duration=duration, windows=4, window_seconds=2.0)

    # Assert
    starts = [start for start, _ in windows]
    assert starts == sorted(starts)
    assert all(a + span <= b for (a, span), (b, _) in pairwise(windows))


def test_a_clip_of_no_length_is_refused():
    # Arrange
    duration = 0.0

    # Act
    with pytest.raises(ValueError) as refused:
        tune.sample_windows(start=0.0, duration=duration, windows=2, window_seconds=1.0)

    # Assert
    assert str(refused.value) == "a clip duration must be positive"


def test_asking_for_no_windows_is_refused():
    # Arrange
    windows = 0

    # Act
    with pytest.raises(ValueError) as refused:
        tune.sample_windows(start=0.0, duration=10.0, windows=windows, window_seconds=1.0)

    # Assert
    assert str(refused.value) == "at least one sample window is required"


def test_the_lowest_error_wins_when_no_byte_ceiling_applies():
    # Arrange
    table = {
        0.0: tune.Score(error=0.9, per_frame=1000.0),
        2.0: tune.Score(error=0.4, per_frame=3000.0),
        4.0: tune.Score(error=0.7, per_frame=2000.0),
    }

    # Act
    choice = pick(table)

    # Assert
    assert choice.value == 2.0
    assert choice.fits is True


def test_a_candidate_over_the_byte_ceiling_never_wins():
    # Arrange
    table = {
        0.0: tune.Score(error=0.9, per_frame=1000.0),
        2.0: tune.Score(error=0.4, per_frame=3000.0),
        4.0: tune.Score(error=0.7, per_frame=2000.0),
    }

    # Act
    choice = pick(table, max_per_frame=2500.0)

    # Assert
    assert choice.value == 4.0
    assert choice.fits is True


def test_the_cheapest_candidate_wins_when_none_of_them_fit():
    # Arrange
    table = {
        0.0: tune.Score(error=0.9, per_frame=4000.0),
        2.0: tune.Score(error=0.4, per_frame=5000.0),
        4.0: tune.Score(error=0.7, per_frame=3500.0),
    }

    # Act
    choice = pick(table, max_per_frame=1000.0)

    # Assert
    assert choice.value == 4.0
    assert choice.fits is False


def test_a_candidate_exactly_on_the_ceiling_still_fits():
    # Arrange
    table = {
        0.0: tune.Score(error=0.9, per_frame=1000.0),
        2.0: tune.Score(error=0.4, per_frame=2000.0),
    }

    # Act
    choice = pick(table, max_per_frame=2000.0)

    # Assert
    assert choice.value == 2.0
    assert choice.fits is True


@needs_ffmpeg
def test_every_candidate_is_scored(clip):
    # Arrange
    candidates = (0.0, 4.0)

    # Act
    choice = tune.pick_denoise(
        tune.Footage(clip, start=0.0, duration=1.0, scaler="area"),
        tune.EncodeSettings(SMALL, budget=1400, cap=60, reuse=0.008),
        fps=6.0,
        candidates=candidates,
        sampling=tune.Sampling(windows=1, window_seconds=0.5),
    )

    # Assert
    assert sorted(choice.scores) == [0.0, 4.0]


def test_an_empty_candidate_set_is_refused():
    # Arrange
    source = Path("unused.mp4")

    # Act
    with pytest.raises(ValueError) as refused:
        tune.pick_denoise(
            tune.Footage(source, start=0.0, duration=10.0, scaler="area"),
            tune.EncodeSettings(GEOMETRY, budget=1400, cap=220, reuse=0.008),
            fps=12.0,
            candidates=(),
        )

    # Assert
    assert str(refused.value) == "at least one denoise candidate is required"


def test_the_choice_reports_every_score_it_considered():
    # Arrange
    choice = tune.Choice(
        value=2.0,
        fits=True,
        scores={
            0.0: tune.Score(error=0.9, per_frame=1000.0),
            2.0: tune.Score(error=0.4, per_frame=2000.0),
        },
    )

    # Act
    rendered = choice.table()

    # Assert
    assert "0.90000" in rendered
    assert "0.40000" in rendered
    assert "1000" in rendered
    assert "2000" in rendered


@needs_ffmpeg
class TestPickReuse:
    def test_it_returns_one_of_the_candidates(self, clip):
        # Arrange
        candidates = (0.008, 0.001)

        # Act
        choice = tune.pick_reuse(
            tune.Footage(clip, start=0.0, duration=2.0, scaler="area"),
            tune.EncodeSettings(SMALL, budget=600, cap=40),
            fps=6.0,
            denoise=0.0,
            candidates=candidates,
            sampling=tune.Sampling(windows=1, window_seconds=0.6),
        )

        # Assert
        assert choice.value in (0.008, 0.001)

    def test_it_scores_every_candidate(self, clip):
        # Arrange
        candidates = (0.008, 0.002, 0.001)

        # Act
        choice = tune.pick_reuse(
            tune.Footage(clip, start=0.0, duration=2.0, scaler="area"),
            tune.EncodeSettings(SMALL, budget=600, cap=40),
            fps=6.0,
            denoise=0.0,
            candidates=candidates,
            sampling=tune.Sampling(windows=1, window_seconds=0.6),
        )

        # Assert
        assert len(choice.scores) == 3

    def test_a_byte_ceiling_rules_out_the_expensive_ones(self, clip):
        # Arrange
        candidates = (0.016, 0.001)

        # Act
        choice = tune.pick_reuse(
            tune.Footage(clip, start=0.0, duration=2.0, scaler="area"),
            tune.EncodeSettings(SMALL, budget=600, cap=40),
            fps=6.0,
            denoise=0.0,
            candidates=candidates,
            sampling=tune.Sampling(windows=1, window_seconds=0.6),
            bar=tune.Bar(
                max_per_frame=1.0, stale_tolerance=tune.STALE_TOLERANCE, tie=tune.SCORE_TIE
            ),
        )

        # Assert
        assert choice.fits is False

    def test_nothing_affordable_takes_the_cheapest(self, clip):
        # Arrange
        candidates = (0.016, 0.001)

        # Act
        choice = tune.pick_reuse(
            tune.Footage(clip, start=0.0, duration=2.0, scaler="area"),
            tune.EncodeSettings(SMALL, budget=600, cap=40),
            fps=6.0,
            denoise=0.0,
            candidates=candidates,
            sampling=tune.Sampling(windows=1, window_seconds=0.6),
            bar=tune.Bar(
                max_per_frame=1.0, stale_tolerance=tune.STALE_TOLERANCE, tie=tune.SCORE_TIE
            ),
        )

        # Assert
        cheapest = min(choice.scores, key=lambda v: choice.scores[v].per_frame)
        assert choice.value == cheapest

    def test_no_candidates_is_refused(self, clip):
        # Arrange
        candidates: tuple[float, ...] = ()

        # Act
        with pytest.raises(ValueError) as refused:
            tune.pick_reuse(
                tune.Footage(clip, start=0.0, duration=2.0, scaler="area"),
                tune.EncodeSettings(GEOMETRY, budget=600, cap=40),
                fps=6.0,
                denoise=0.0,
                candidates=candidates,
                sampling=tune.Sampling(windows=1, window_seconds=0.6),
            )

        # Assert
        assert str(refused.value) == "at least one reuse candidate is required"

    def test_a_candidate_that_leaves_cells_stale_cannot_win(self):
        # Arrange
        scores = {
            0.008: tune.Score(error=0.1, per_frame=100.0, stale_share=0.2),
            0.001: tune.Score(error=0.3, per_frame=100.0, stale_share=0.0),
        }

        # Act
        choice = tune.decide(
            scores,
            key=lambda score: score.error,
            bar=tune.Bar(max_per_frame=None, stale_tolerance=0.01),
            label="reuse",
            digits=4,
        )

        # Assert
        assert (choice.value, choice.stale_waived) == (0.001, False)

    def test_the_table_names_the_working_set_number(self, clip):
        # Arrange
        candidates = (0.008,)

        # Act
        choice = tune.pick_reuse(
            tune.Footage(clip, start=0.0, duration=2.0, scaler="area"),
            tune.EncodeSettings(SMALL, budget=600, cap=40),
            fps=6.0,
            denoise=0.0,
            candidates=candidates,
            sampling=tune.Sampling(windows=1, window_seconds=0.6),
        )

        # Assert
        assert "working set" in choice.table()


@needs_ffmpeg
class TestScoreCarriesBothErrors:
    def test_a_score_reports_what_the_working_set_cost(self, clip):
        # Arrange
        candidates = (0.008,)

        # Act
        choice = tune.pick_reuse(
            tune.Footage(clip, start=0.0, duration=2.0, scaler="area"),
            tune.EncodeSettings(SMALL, budget=600, cap=40),
            fps=6.0,
            denoise=0.0,
            candidates=candidates,
            sampling=tune.Sampling(windows=1, window_seconds=0.6),
        )

        # Assert
        assert 0.0 < choice.scores[0.008].working_set < choice.scores[0.008].error

    def test_a_score_still_reports_the_total(self, clip):
        # Arrange
        candidates = (0.008,)

        # Act
        choice = tune.pick_reuse(
            tune.Footage(clip, start=0.0, duration=2.0, scaler="area"),
            tune.EncodeSettings(SMALL, budget=600, cap=40),
            fps=6.0,
            denoise=0.0,
            candidates=candidates,
            sampling=tune.Sampling(windows=1, window_seconds=0.6),
        )

        # Assert
        assert choice.scores[0.008].error > 0.0
