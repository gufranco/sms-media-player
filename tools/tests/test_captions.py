from __future__ import annotations

import subprocess

import numpy as np
import pytest
from fmvcore.testing import SEED

from smsggmedia import captions, cartridge

HEIGHT = 48
WIDTH = 64
ONE = (
    "........",
    "...##...",
    "..###...",
    "...##...",
    "...##...",
    "...##...",
    "..####..",
    "........",
)
GLYPH_TOP = HEIGHT - captions.BOTTOM_MARGIN - 8
GLYPH_LEFT = (WIDTH - 8) // 2


def picture() -> np.ndarray:
    rng = np.random.default_rng(SEED)
    return rng.integers(60, 200, (HEIGHT, WIDTH, 3), dtype=np.uint8)


def cue(start: float, end: float, text: str) -> captions.subtitles.Cue:
    return captions.subtitles.Cue(start=start, end=end, lines=(text,))


def srt(start: str, end: str, text: str) -> str:
    return f"1\n{start} --> {end}\n{text}\n"


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    path = tmp_path_factory.mktemp("clip") / "source.mp4"
    chain = "testsrc2=size=320x240:rate=30:duration=2"
    command = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", chain]
    subprocess.run([*command, "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


class TestBurn:
    def test_the_ink_is_white_where_the_glyph_art_has_marks(self):
        # Arrange
        frame = picture()

        # Act
        burned = captions.burn(frame, "1")

        # Assert
        cell = burned[GLYPH_TOP : GLYPH_TOP + 8, GLYPH_LEFT : GLYPH_LEFT + 8]
        lit = ["".join("#" if pixel.min() == 255 else "." for pixel in row) for row in cell]
        assert lit == list(ONE)

    def test_a_pixel_beside_the_ink_is_outlined_in_black(self):
        # Arrange
        frame = picture()

        # Act
        burned = captions.burn(frame, "1")

        # Assert
        assert burned[GLYPH_TOP + 1, GLYPH_LEFT + 2].tolist() == [0, 0, 0]

    def test_the_picture_away_from_the_text_is_untouched(self):
        # Arrange
        frame = picture()

        # Act
        burned = captions.burn(frame, "1")

        # Assert
        assert np.array_equal(burned[: GLYPH_TOP - 1], frame[: GLYPH_TOP - 1])

    def test_a_long_line_wraps_onto_a_second_row_above_the_margin(self):
        # Arrange
        frame = picture()

        # Act
        burned = captions.burn(frame, "11111111 1")

        # Assert
        second_row = burned[GLYPH_TOP : GLYPH_TOP + 8]
        first_row = burned[GLYPH_TOP - 8 : GLYPH_TOP]
        assert (np.any(first_row == 255), np.any(second_row == 255)) == (True, True)


class TestCaption:
    def test_only_frames_inside_a_cue_carry_text(self):
        # Arrange
        frames = [picture(), picture(), picture()]
        cues = [cue(10.5, 11.0, "1")]

        # Act
        captioned = captions.caption(frames, cues, start=10.0, fps=2.0)

        # Assert
        changed = [not np.array_equal(a, b) for a, b in zip(captioned, frames, strict=True)]
        assert changed == [False, True, False]

    def test_no_cues_leaves_the_frames_as_they_are(self):
        # Arrange
        frames = [picture()]

        # Act
        captioned = captions.caption(frames, [], start=0.0, fps=2.0)

        # Assert
        assert captioned is frames


class TestLoad:
    def test_an_explicit_file_is_read(self, tmp_path):
        # Arrange
        path = tmp_path / "chosen.srt"
        path.write_text(srt("00:00:01,000", "00:00:02,000", "1"))

        # Act
        cues = captions.load(path, tmp_path / "film.mp4")

        # Assert
        assert [(c.start, c.end, c.lines) for c in cues] == [(1.0, 2.0, ("1",))]

    def test_a_file_beside_the_source_is_used_when_none_is_named(self, tmp_path):
        # Arrange
        (tmp_path / "film.srt").write_text(srt("00:00:03,000", "00:00:04,000", "1"))

        # Act
        cues = captions.load(None, tmp_path / "film.mp4")

        # Assert
        assert [c.start for c in cues] == [3.0]

    def test_no_file_anywhere_gives_no_cues(self, tmp_path):
        # Arrange
        source = tmp_path / "film.mp4"

        # Act
        cues = captions.load(None, source)

        # Assert
        assert cues == []

    def test_a_named_file_that_is_missing_is_refused(self, tmp_path):
        # Arrange
        path = tmp_path / "missing.srt"

        # Act
        with pytest.raises(FileNotFoundError) as refused:
            captions.load(path, tmp_path / "film.mp4")

        # Assert
        assert str(refused.value) == f"subtitle file not found: {path}"


@pytest.mark.ffmpeg
class TestTheCartridgeCommand:
    def test_a_missing_subtitle_file_stops_the_bake(self, clip, tmp_path, capsys):
        # Arrange
        argv = [str(clip), "--subtitles", str(tmp_path / "missing.srt")]

        # Act
        with pytest.raises(SystemExit) as stopped:
            cartridge.main(argv)

        # Assert
        assert (stopped.value.code, "subtitle file not found" in capsys.readouterr().err) == (
            2,
            True,
        )
