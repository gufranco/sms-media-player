from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import numpy as np
import pytest

from smsmovie import cartridge, clips, dials, rate, tune

SMALL = tune.bake.Geometry(columns=8, rows=6, top_row=0)
FULL = tune.bake.Geometry(columns=32, rows=24, top_row=0)
FAST = ["--duration", "1"]


@pytest.fixture(scope="module")
def source():
    return clips.path_of(clips.by_key("synthetic"))


@pytest.fixture(scope="module")
def noise(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("noise") / "noise.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "nullsrc=size=256x192:rate=12:duration=2,geq=lum='random(1)*255':cb='random(2)*255':cr='random(3)*255'",
            "-pix_fmt",
            "yuv444p",
            "-c:v",
            "libx264",
            "-qp",
            "0",
            str(path),
        ],
        check=True,
    )
    return path


def parsed(source, *extra: str):
    return cartridge.build_parser().parse_args([str(source), *FAST, *extra])


class TestSettle:
    def test_given_values_are_taken_as_given(self, source):
        # Arrange
        args = parsed(source, "--fps", "6", "--denoise", "1", "--reuse", "0.004")

        # Act
        settled = dials.settle_dials(args, geometry=SMALL, wanted=1.0)

        # Assert
        assert settled == dials.Dials(fps=6.0, denoise=1.0, reuse=0.004)

    def test_an_automatic_rate_is_one_of_the_candidates(self, source, caplog):
        # Arrange
        caplog.set_level(logging.INFO, logger=dials.LOG.name)
        args = parsed(source, "--denoise", "0", "--reuse", "0.008")

        # Act
        settled = dials.settle_dials(args, geometry=SMALL, wanted=1.0)

        # Assert
        assert settled.fps in rate.DEFAULT_RATE_CANDIDATES
        assert "fps auto" in caplog.text

    def test_every_dial_can_be_measured_in_one_bake(self, source, caplog):
        # Arrange
        caplog.set_level(logging.INFO, logger=dials.LOG.name)
        args = parsed(source, "--fps", "6")

        # Act
        settled = dials.settle_dials(args, geometry=SMALL, wanted=1.0)

        # Assert
        assert settled.denoise in tune.DEFAULT_CANDIDATES
        assert settled.reuse in tune.DEFAULT_REUSE_CANDIDATES
        assert "denoise auto" in caplog.text
        assert "reuse auto" in caplog.text


class TestReuseThatCannotFit:
    def test_it_says_nothing_fit_and_takes_the_cheapest(self, source, caplog):
        # Arrange
        caplog.set_level(logging.INFO, logger=dials.LOG.name)
        budget = 400

        # Act
        value = dials.resolve_reuse(
            "auto",
            tune.Footage(source, start=0.0, duration=1.0, scaler="area"),
            tune.EncodeSettings(SMALL, budget=budget, cap=40),
            fps=6.0,
            denoise=0.0,
            max_per_frame=1.0,
        )

        # Assert
        assert value in tune.DEFAULT_REUSE_CANDIDATES
        assert "none fit" in caplog.text


class TestTheRateSearch:
    def test_a_rate_nothing_can_hold_falls_to_the_slowest(self, source):
        # Arrange
        candidates = (12.0, 10.0)

        # Act
        choice = rate.pick_rate(
            tune.Footage(source, start=0.0, duration=1.0, scaler="area"),
            tune.EncodeSettings(SMALL, budget=40, cap=40, reuse=0.008),
            denoise=0.0,
            candidates=candidates,
            sampling=tune.Sampling(windows=1, window_seconds=0.5),
        )

        # Assert
        assert choice.fits is False
        assert choice.value == 10.0

    def test_it_reports_when_nothing_held(self, noise, caplog):
        # Arrange
        caplog.set_level(logging.INFO, logger=dials.LOG.name)
        budget = 40

        # Act
        dials.resolve_rate(
            "auto",
            tune.Footage(noise, start=0.0, duration=0.5, scaler="area"),
            tune.EncodeSettings(FULL, budget=budget, cap=380, reuse=0.008),
            denoise=0.0,
        )

        # Assert
        assert "took the slowest" in caplog.text

    def test_a_window_past_the_end_is_refused(self, source):
        # Arrange
        windows = [(600.0, 0.5)]

        # Act
        with pytest.raises(ValueError) as refused:
            rate.score_rate(
                tune.Footage(source, start=0.0, duration=0.0, scaler="area"),
                6.0,
                settings=tune.EncodeSettings(SMALL, budget=400, cap=40, reuse=0.008),
                denoise=0.0,
                windows=windows,
            )

        # Assert
        assert str(refused.value) == "no frames decoded while scoring 6.0 fps"


class TestScoringNothing:
    def test_scoring_no_windows_is_refused(self):
        # Arrange
        decoded: list[list[np.ndarray]] = []

        # Act
        with pytest.raises(ValueError) as refused:
            tune.score_windows(
                decoded, settings=tune.EncodeSettings(SMALL, budget=400, cap=40, reuse=0.008)
            )

        # Assert
        assert str(refused.value) == "no frames decoded while scoring"

    def test_denoise_past_the_end_is_refused(self, source):
        # Arrange
        start = 600.0

        # Act
        with pytest.raises(ValueError) as refused:
            tune.pick_denoise(
                tune.Footage(source, start=start, duration=0.5, scaler="area"),
                tune.EncodeSettings(SMALL, budget=400, cap=40, reuse=0.008),
                fps=6.0,
                sampling=tune.Sampling(windows=1, window_seconds=0.5),
            )

        # Assert
        assert str(refused.value) == "no frames decoded while scoring denoise 0.0"

    def test_reuse_past_the_end_is_refused(self, source):
        # Arrange
        start = 600.0

        # Act
        with pytest.raises(ValueError) as refused:
            tune.pick_reuse(
                tune.Footage(source, start=start, duration=1.0, scaler="area"),
                tune.EncodeSettings(SMALL, budget=400, cap=40),
                fps=6.0,
                denoise=0.0,
                sampling=tune.Sampling(windows=1),
            )

        # Assert
        assert str(refused.value) == "no frames decoded while scoring"
