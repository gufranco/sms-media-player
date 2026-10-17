from __future__ import annotations

import pytest
from lavfi import lavfi_clip
from tunecases import (
    OFFSET,
    SMALL,
    grey_ramp_window,
    two_frames,
)

from smsggmedia import target, tune

needs_ffmpeg = pytest.mark.ffmpeg


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    return lavfi_clip(tmp_path_factory.mktemp("tune") / "source.mp4", size="64x48")


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
