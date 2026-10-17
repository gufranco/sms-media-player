from __future__ import annotations

import subprocess
from itertools import pairwise
from pathlib import Path

import numpy as np
import pytest

from smsmedia import rate, target, tune

needs_ffmpeg = pytest.mark.ffmpeg

GEOMETRY = tune.bake.Geometry(columns=32, rows=18, top_row=3)

SMALL = tune.bake.Geometry(columns=8, rows=6, top_row=0)


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    path = tmp_path_factory.mktemp("tune") / "source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=64x48:rate=12:duration=2",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
    )
    return path


def pick(table, *, max_per_frame=None):
    return tune.decide(
        table,
        key=lambda score: score.error,
        bar=tune.Bar(max_per_frame=max_per_frame, stale_tolerance=None),
        label="denoise",
        digits=1,
    )


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

    def test_a_candidate_that_leaves_cells_stale_cannot_win(self, clip):
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
        assert choice.scores[choice.value].stale == 0 or all(
            score.stale > 0 for score in choice.scores.values()
        )

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


OFFSET = tune.bake.Geometry(columns=8, rows=6, top_row=2)
ORANGE = (170, 85, 0)
BLUE = (0, 85, 255)


def split_frame(left: tuple[int, int, int], right: tuple[int, int, int]) -> np.ndarray:
    frame = np.zeros((OFFSET.height, OFFSET.width, 3), dtype=np.uint8)
    frame[:, : OFFSET.width // 2] = left
    frame[:, OFFSET.width // 2 :] = right
    return frame


def two_frames() -> list[np.ndarray]:
    return [split_frame(ORANGE, BLUE), split_frame(BLUE, ORANGE)]


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


def pick_on_working_set(
    scores: dict[float, tune.Score], *, tie: float, max_per_frame: float | None = None
) -> tune.Choice:
    return tune.decide(
        scores,
        key=lambda score: score.working_set,
        bar=tune.Bar(max_per_frame=max_per_frame, stale_tolerance=None, tie=tie),
        label="reuse",
        digits=4,
    )


class TestScoringAgainstAReference:
    def test_a_replay_scores_no_error_against_its_own_picture_below_the_top_rows(self):
        # Arrange
        frames = two_frames()
        encoded = tune.bake.encode_frames(frames, geometry=OFFSET, budget=1400, cap=60)

        # Act
        error = tune.replayed_error(encoded, frames, geometry=OFFSET)

        # Assert
        assert error == 0.0

    def test_frames_scored_in_the_wrong_order_carry_error(self):
        # Arrange
        frames = two_frames()
        encoded = tune.bake.encode_frames(frames, geometry=OFFSET, budget=1400, cap=60)

        # Act
        error = tune.replayed_error(encoded, frames[::-1], geometry=OFFSET)

        # Assert
        assert error > 0.1

    def test_the_reference_sets_the_blurred_score_and_leaves_the_encoder_error_alone(self):
        # Arrange
        frames = two_frames()
        own = tune.score_windows(
            [frames], settings=tune.EncodeSettings(OFFSET, budget=1400, cap=60, reuse=0.0)
        )

        # Act
        charged = tune.score_windows(
            [frames],
            settings=tune.EncodeSettings(OFFSET, budget=1400, cap=60, reuse=0.0),
            reference=[frames[::-1]],
        )

        # Assert
        assert (charged.error, own.blurred) == (own.error, 0.0)
        assert charged.blurred > 0.1

    def test_no_reference_frames_are_refused(self):
        # Arrange
        frames = two_frames()
        encoded = tune.bake.encode_frames(frames, geometry=OFFSET, budget=1400, cap=60)

        # Act
        with pytest.raises(ValueError) as refused:
            tune.replayed_error(encoded, [], geometry=OFFSET)

        # Assert
        assert str(refused.value) == "no reference frames to score the replay against"

    def test_more_reference_frames_than_the_replay_completed_are_refused(self):
        # Arrange
        frames = two_frames()
        encoded = tune.bake.encode_frames(frames, geometry=OFFSET, budget=1400, cap=60)

        # Act
        with pytest.raises(ValueError) as refused:
            tune.replayed_error(encoded, [*frames, *frames], geometry=OFFSET)

        # Assert
        assert str(refused.value) == "the replay completed 2 of 4 frames"

    def test_a_reference_of_another_length_is_refused(self):
        # Arrange
        frames = two_frames()

        # Act
        with pytest.raises(ValueError) as refused:
            tune.score_windows(
                [frames],
                settings=tune.EncodeSettings(OFFSET, budget=1400, cap=60, reuse=0.0),
                reference=[],
            )

        # Assert
        assert str(refused.value) == "0 reference windows for 1 decoded ones"


@needs_ffmpeg
class TestDenoiseAgainstAReference:
    def test_every_strength_is_scored_on_the_replayed_picture(self, clip):
        # Arrange
        candidates = (0.0, 8.0)

        # Act
        choice = tune.pick_denoise(
            tune.Footage(clip, start=0.0, duration=1.0, scaler="area"),
            tune.EncodeSettings(SMALL, budget=1400, cap=60, reuse=0.008),
            fps=6.0,
            candidates=candidates,
            sampling=tune.Sampling(windows=1, window_seconds=1.0),
        )

        # Assert
        assert min(score.blurred for score in choice.scores.values()) > 0.0

    def test_the_cheapest_strength_tied_with_the_best_blurred_score_wins(self, clip):
        # Arrange
        candidates = (0.0, 8.0)

        # Act
        choice = tune.pick_denoise(
            tune.Footage(clip, start=0.0, duration=1.0, scaler="area"),
            tune.EncodeSettings(SMALL, budget=1400, cap=60, reuse=0.008),
            fps=6.0,
            candidates=candidates,
            sampling=tune.Sampling(windows=1, window_seconds=1.0),
        )

        # Assert
        floor = min(score.blurred for score in choice.scores.values())
        tied = [
            value
            for value, score in choice.scores.items()
            if score.blurred <= floor * (1.0 + tune.SCORE_TIE)
        ]
        assert choice.value == min(tied, key=lambda value: choice.scores[value].per_frame)


class TestAWaivedStaleGate:
    def test_a_choice_made_past_the_stale_tolerance_says_so(self):
        # Arrange
        scores = {
            0.004: tune.Score(error=0.1, per_frame=100.0, stale_share=0.2),
            0.002: tune.Score(error=0.2, per_frame=200.0, stale_share=0.3),
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
        assert (choice.value, choice.stale_waived) == (0.004, True)

    def test_a_choice_inside_the_stale_tolerance_waives_nothing(self):
        # Arrange
        scores = {0.004: tune.Score(error=0.1, per_frame=100.0, stale_share=0.0)}

        # Act
        choice = tune.decide(
            scores,
            key=lambda score: score.error,
            bar=tune.Bar(max_per_frame=None, stale_tolerance=0.01),
            label="reuse",
            digits=4,
        )

        # Assert
        assert choice.stale_waived is False


class TestWorkingSetTail:
    def test_the_ninetieth_percentile_runs_across_every_frame_of_every_window(self):
        # Arrange
        costs = [
            tune.WindowCost(
                error=0.0,
                working_set=0.0,
                size=100.0,
                stale=0,
                blurred=0.0,
                chunk_counts=(1,) * 5,
                per_frame_working_set=(0.1, 0.2, 0.3, 0.4, 0.5),
            ),
            tune.WindowCost(
                error=0.0,
                working_set=0.0,
                size=100.0,
                stale=0,
                blurred=0.0,
                chunk_counts=(1,) * 5,
                per_frame_working_set=(0.6, 0.7, 0.8, 0.9, 1.0),
            ),
        ]

        # Act
        score = tune.summarise(costs, cells=10)

        # Assert
        assert score.working_set_p90 == pytest.approx(0.91)


def grey_ramp_window() -> list[list[np.ndarray]]:
    ramp = np.linspace(0, 255, SMALL.width).astype(np.uint8)
    frame = np.repeat(np.repeat(ramp[None, :, None], SMALL.height, axis=0), 3, axis=2)
    return [[frame, frame]]


def test_a_game_gear_score_is_measured_on_its_own_colours():
    # Arrange
    window = grey_ramp_window()
    narrow = tune.score_windows(
        window, settings=tune.EncodeSettings(SMALL, budget=1400, cap=60, dither=0.0)
    )

    # Act
    wide = tune.score_windows(
        window,
        settings=tune.EncodeSettings(
            SMALL, budget=1400, cap=60, dither=0.0, system=target.GAME_GEAR
        ),
    )

    # Assert
    assert wide.error < narrow.error / 2
