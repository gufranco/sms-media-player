import subprocess

import pytest

from smsggmedia import frames

pytestmark = pytest.mark.ffmpeg


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    path = tmp_path_factory.mktemp("clip") / "source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x240:rate=30:duration=2",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
    )
    return path


class TestDecode:
    def test_it_yields_frames_at_the_requested_size(self, clip):
        # Arrange
        source = clip

        # Act
        result = list(frames.decode(source, width=64, height=48, fps=5))

        # Assert
        assert result[0].shape == (48, 64, 3)

    def test_the_frame_count_follows_the_rate_and_duration(self, clip):
        # Arrange
        source = clip

        # Act
        result = list(frames.decode(source, width=64, height=48, fps=5))

        # Assert
        assert 8 <= len(result) <= 12

    def test_a_duration_limit_shortens_the_run(self, clip):
        # Arrange
        source = clip

        # Act
        result = list(frames.decode(source, width=64, height=48, fps=5, duration=1.0))

        # Assert
        assert 3 <= len(result) <= 7

    def test_an_odd_size_is_refused(self, clip):
        # Arrange
        source = clip

        # Act
        with pytest.raises(ValueError) as refused:
            list(frames.decode(source, width=63, height=48, fps=5))

        # Assert
        assert str(refused.value) == "the raster must be a multiple of 8 pixels"

    def test_a_rate_of_zero_is_refused(self, clip):
        # Arrange
        source = clip

        # Act
        with pytest.raises(ValueError) as refused:
            list(frames.decode(source, width=64, height=48, fps=0))

        # Assert
        assert str(refused.value) == "a frame rate must be positive"


class TestDecodeOptions:
    def test_a_scaler_choice_is_accepted(self, clip):
        # Arrange
        source = clip

        # Act
        result = list(frames.decode(source, width=64, height=48, fps=5, scaler="area"))

        # Assert
        assert result[0].shape == (48, 64, 3)

    def test_denoise_changes_the_output(self, clip):
        # Arrange
        plain = list(frames.decode(clip, width=64, height=48, fps=5))

        # Act
        soft = list(frames.decode(clip, width=64, height=48, fps=5, denoise=8.0))

        # Assert
        assert plain[0].tolist() != soft[0].tolist()

    def test_a_scaler_changes_the_output(self, clip):
        # Arrange
        lanczos = list(frames.decode(clip, width=64, height=48, fps=5, scaler="lanczos"))

        # Act
        area = list(frames.decode(clip, width=64, height=48, fps=5, scaler="area"))

        # Assert
        assert lanczos[0].tolist() != area[0].tolist()


class TestAspect:
    def test_a_wide_target_leaves_no_bar_down_the_side(self, clip):
        # Arrange
        source = clip

        # Act
        result = list(frames.decode(source, width=64, height=16, fps=5))

        # Assert
        assert result[0][:, 0].max() > 0
        assert result[0][:, -1].max() > 0

    def test_a_tall_target_leaves_no_bar_across_the_top(self, clip):
        # Arrange
        source = clip

        # Act
        result = list(frames.decode(source, width=16, height=64, fps=5))

        # Assert
        assert result[0][0].max() > 0
        assert result[0][-1].max() > 0

    def test_a_matching_aspect_is_unchanged(self, clip):
        # Arrange
        source = clip

        # Act
        result = list(frames.decode(source, width=64, height=48, fps=5))

        # Assert
        assert result[0].max() > 0

    def test_the_output_is_always_the_raster_that_was_asked_for(self, clip):
        # Arrange
        source = clip

        # Act
        result = list(frames.decode(source, width=64, height=16, fps=5))

        # Assert
        assert result[0].shape == (16, 64, 3)

    def test_a_wider_source_keeps_its_middle(self, clip):
        # Arrange
        square = next(iter(frames.decode(clip, width=64, height=48, fps=5)))

        # Act
        wide = next(iter(frames.decode(clip, width=64, height=16, fps=5)))

        # Assert
        assert wide.mean() == pytest.approx(square[16:32].mean(), abs=40)


class TestDecodeRefusals:
    def test_decoding_a_missing_file_is_refused(self, tmp_path):
        # Arrange
        absent = tmp_path / "absent.mp4"

        # Act
        with pytest.raises(FileNotFoundError) as refused:
            list(frames.decode(absent, width=8, height=8, fps=1.0))

        # Assert
        assert str(refused.value) == f"no such source file: {absent}"

    def test_a_file_ffmpeg_cannot_read_fails_rather_than_yielding_nothing(self, tmp_path):
        # Arrange
        broken = tmp_path / "broken.mp4"
        broken.write_bytes(b"this is not a film")

        # Act
        with pytest.raises(RuntimeError) as refused:
            list(frames.decode(broken, width=8, height=8, fps=1.0))

        # Assert
        assert "ffmpeg failed decoding" in str(refused.value)

    def test_stopping_early_closes_the_decoder_quietly(self, clip):
        # Arrange
        stream = frames.decode(clip, width=64, height=48, fps=12.0)
        first = next(stream)

        # Act
        stream.close()

        # Assert
        assert first.shape == (48, 64, 3)


BAR = 40


@pytest.fixture(scope="module")
def boxed(tmp_path_factory):
    path = tmp_path_factory.mktemp("boxed") / "boxed.mp4"
    picture = f"scale=320:{240 - 2 * BAR},pad=320:240:0:{BAR}:black"
    chain = f"testsrc2=size=320x240:rate=30:duration=2,{picture}"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            chain,
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
    )
    return path


class TestBakedInBars:
    def test_cropping_the_bars_leaves_no_black_row_at_the_top(self, boxed):
        # Arrange
        bars = (320, 240 - 2 * BAR, 0, BAR)

        # Act
        result = list(frames.decode(boxed, width=64, height=48, fps=5, bars=bars))

        # Assert
        assert int(result[0][0].max()) > 0

    def test_without_the_crop_the_bars_reach_the_picture(self, boxed):
        # Arrange
        bars = None

        # Act
        result = list(frames.decode(boxed, width=64, height=48, fps=5, bars=bars))

        # Assert
        assert int(result[0][0].max()) < 24
