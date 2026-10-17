from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from lavfi import lavfi_clip

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "scripts" / "make_demos.py"
FIXED = ["--fps", "6", "--denoise", "0", "--reuse", "0.008"]

pytestmark = pytest.mark.ffmpeg


def load():
    spec = importlib.util.spec_from_file_location("make_demos", SCRIPT)
    if spec is None or spec.loader is None:
        msg = f"cannot import {SCRIPT}"
        raise AssertionError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules["make_demos"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def demos():
    return load()


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    return lavfi_clip(tmp_path_factory.mktemp("demo") / "source.mp4", size="320x240", rate=30)


@pytest.fixture(scope="module")
def made(demos, clip, tmp_path_factory):
    out = tmp_path_factory.mktemp("readme")
    demos.main([str(clip), "--duration", "1", "--out", str(out), *FIXED])
    return out


def gif_frames(path: Path) -> list[tuple[int, int, int]]:
    probed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-count_frames",
            "-show_entries",
            "stream=width,height,nb_read_frames",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        check=True,
    )
    streams = json.loads(probed.stdout)["streams"]
    return [(s["width"], s["height"], int(s["nb_read_frames"])) for s in streams]


class TestTheDemos:
    def test_the_master_system_demo_is_the_whole_raster(self, made):
        # Arrange
        path = made / "demo.gif"

        # Act
        shape = gif_frames(path)[0][:2]

        # Assert
        assert shape == (256, 192)

    def test_the_game_gear_demo_is_its_panel(self, made):
        # Arrange
        path = made / "demo-gg.gif"

        # Act
        shape = gif_frames(path)[0][:2]

        # Assert
        assert shape == (160, 144)

    def test_both_demos_carry_the_same_number_of_frames(self, made):
        # Arrange
        paths = (made / "demo.gif", made / "demo-gg.gif")

        # Act
        counts = [gif_frames(path)[0][2] for path in paths]

        # Assert
        assert counts[0] == counts[1]
        assert counts[0] > 0


class TestCuttingToOneLength:
    def test_the_longer_film_is_cut_to_the_shorter(self, demos):
        # Arrange
        frames = {"sms": np.zeros((5, 2, 2, 3), np.uint8), "gg": np.zeros((3, 2, 2, 3), np.uint8)}

        # Act
        cut = demos.same_length(frames)

        # Assert
        assert {system: len(shown) for system, shown in cut.items()} == {"sms": 3, "gg": 3}


class TestOneFrameRate:
    def test_one_rate_is_returned(self, demos):
        # Arrange
        rates = {6.0}

        # Act
        rate = demos.one_rate(rates)

        # Assert
        assert rate == 6.0

    def test_two_rates_are_refused_by_name(self, demos):
        # Arrange
        rates = {6.0, 12.0}

        # Act
        with pytest.raises(ValueError) as refused:
            demos.one_rate(rates)

        # Assert
        assert str(refused.value) == (
            "the consoles settled on different frame rates, [6.0, 12.0]; pass the same --fps"
        )


class TestARefusedBake:
    def test_a_bake_that_does_not_fit_is_named(self, demos, clip, tmp_path):
        # Arrange
        flags = ["--fps", "12", "--denoise", "0", "--reuse", "0.008", "--max-banks", "1"]

        # Act
        with pytest.raises(RuntimeError) as refused:
            demos.bake(clip, start=0.0, duration=2.0, system="sms", folder=tmp_path, flags=flags)

        # Assert
        assert str(refused.value).startswith(f"the sms bake of {clip} failed with status ")


class TestTheGifPalette:
    def test_every_colour_the_demo_shows_is_kept_exactly(self, demos, tmp_path):
        # Arrange
        rng = np.random.default_rng(5)
        frames = rng.integers(0, 256, size=(3, 8, 8, 3), dtype=np.uint8)
        path = tmp_path / "exact.gif"

        # Act
        demos.write_gif(path, frames, fps=12.0)

        # Assert
        assert np.array_equal(gif_pixels(path, 8, 8), frames)

    def test_more_colours_than_a_gif_holds_are_refused(self, demos):
        # Arrange
        index = np.arange(257)
        colours = np.stack([index % 256, index // 256, np.zeros_like(index)], axis=-1)
        frames = colours.astype(np.uint8).reshape(1, 1, 257, 3)

        # Act
        with pytest.raises(ValueError) as refused:
            demos.exact_palette(frames)

        # Assert
        assert str(refused.value) == "the demo shows 257 colours and a GIF holds 256"


def gif_pixels(path: Path, height: int, width: int) -> np.ndarray:
    raw = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-fps_mode",
            "passthrough",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.uint8).reshape(-1, height, width, 3)
