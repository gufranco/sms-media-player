import sys
from pathlib import Path

import pytest
from fakes import seeded

from smsmovie import frames

FAKE = seeded()
FILM = FAKE.file_name(extension="mp4")

SHAPE = (2, 2, 3)
STRIDE = 12
PIPE_BUFFER_OVERRUN = 1 << 20


def writer(*, stdout: int, stderr: int = 0, code: int = 0) -> list[str]:
    script = (
        "import sys\n"
        f"sys.stderr.write('e' * {stderr})\n"
        "sys.stderr.flush()\n"
        f"sys.stdout.buffer.write(bytes(i % 256 for i in range({stdout})))\n"
        f"sys.exit({code})\n"
    )
    return [sys.executable, "-I", "-c", script]


class TestTheDecodePipe:
    def test_whole_frames_arrive_in_order(self):
        # Arrange
        command = writer(stdout=STRIDE * 3)

        # Act
        decoded = list(frames._stream(command, path=Path(FILM), shape=SHAPE))

        # Assert
        assert len(decoded) == 3
        assert decoded[0].reshape(-1).tolist() == list(range(STRIDE))

    def test_a_decoder_that_fills_its_error_pipe_does_not_hang(self):
        # Arrange
        command = writer(stdout=STRIDE * 2, stderr=PIPE_BUFFER_OVERRUN)

        # Act
        decoded = list(frames._stream(command, path=Path(FILM), shape=SHAPE))

        # Assert
        assert len(decoded) == 2

    def test_a_partial_trailing_frame_is_refused(self):
        # Arrange
        command = writer(stdout=STRIDE * 2 + 5)

        # Act
        with pytest.raises(RuntimeError) as refused:
            list(frames._stream(command, path=Path(FILM), shape=SHAPE))

        # Assert
        assert str(refused.value) == (
            f"ffmpeg ended {FILM} on a partial frame of 5 bytes; a frame is 12"
        )

    def test_a_failed_decoder_is_reported_with_what_it_said(self):
        # Arrange
        command = writer(stdout=STRIDE, stderr=3, code=1)

        # Act
        with pytest.raises(RuntimeError) as refused:
            list(frames._stream(command, path=Path(FILM), shape=SHAPE))

        # Assert
        assert str(refused.value) == f"ffmpeg failed decoding {FILM} with exit code 1: eee"

    def test_a_decoder_past_the_frame_ceiling_is_stopped(self, monkeypatch):
        # Arrange
        monkeypatch.setattr(frames, "MAX_FRAMES", 2)
        command = writer(stdout=STRIDE * 3)

        # Act
        with pytest.raises(RuntimeError) as refused:
            list(frames._stream(command, path=Path(FILM), shape=SHAPE))

        # Assert
        assert str(refused.value) == (f"{FILM} decoded past 2 frames, four hours at the field rate")


def probed(*, streams: list[dict[str, object]], duration: object = "4.0") -> dict[str, object]:
    return {"streams": streams, "format": {"duration": duration}}


VIDEO = {"width": 320, "height": 240, "r_frame_rate": "30000/1001"}


class TestWhatTheProbeReports:
    def test_a_readable_source_is_described(self):
        # Arrange
        parsed = probed(streams=[VIDEO])

        # Act
        info = frames.source_info(parsed, path=Path(FILM))

        # Assert
        assert info == frames.SourceInfo(width=320, height=240, fps=30000 / 1001, duration=4.0)

    def test_a_source_with_no_video_stream_is_refused_by_name(self):
        # Arrange
        parsed = probed(streams=[])

        # Act
        with pytest.raises(ValueError) as refused:
            frames.source_info(parsed, path=Path("song.m4a"))

        # Assert
        assert str(refused.value) == "song.m4a has no video stream ffprobe can read"

    @pytest.mark.parametrize("rate", ["0/0", "0/1", "-30/1", "abc"])
    def test_an_unusable_frame_rate_is_refused(self, rate):
        # Arrange
        parsed = probed(streams=[{**VIDEO, "r_frame_rate": rate}])

        # Act
        with pytest.raises(ValueError) as refused:
            frames.source_info(parsed, path=Path(FILM))

        # Assert
        assert str(refused.value).startswith(f"{FILM} does not report a usable size")

    @pytest.mark.parametrize("duration", ["N/A", None, "0", "inf"])
    def test_an_unusable_duration_is_refused(self, duration):
        # Arrange
        parsed = probed(streams=[VIDEO], duration=duration)

        # Act
        with pytest.raises(ValueError) as refused:
            frames.source_info(parsed, path=Path(FILM))

        # Assert
        assert str(refused.value).startswith(f"{FILM} ")

    def test_a_missing_format_block_is_refused(self):
        # Arrange
        parsed = {"streams": [VIDEO]}

        # Act
        with pytest.raises(ValueError) as refused:
            frames.source_info(parsed, path=Path(FILM))

        # Assert
        assert str(refused.value).startswith(f"{FILM} does not report a usable size")
