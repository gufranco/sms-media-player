import subprocess
from pathlib import Path

import numpy as np
import pytest

from smsggmedia import bake, preview, stream

GEOMETRY = bake.Geometry(columns=32, rows=24, top_row=0)
LATTICE_COLOURS = ((170, 85, 0), (0, 85, 255), (255, 255, 255))


def png_size(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[16:24]
    return int.from_bytes(header[:4], "big"), int.from_bytes(header[4:], "big")


def read_png(path: Path) -> np.ndarray:
    width, height = png_size(path)
    raw = subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 3)


def lattice_film(count: int) -> tuple[bytes, list[np.ndarray]]:
    sources = []
    for index in range(count):
        frame = np.zeros((GEOMETRY.height, GEOMETRY.width, 3), dtype=np.uint8)
        frame[:, : GEOMETRY.width // 2] = LATTICE_COLOURS[index % len(LATTICE_COLOURS)]
        frame[:, GEOMETRY.width // 2 :] = LATTICE_COLOURS[(index + 1) % len(LATTICE_COLOURS)]
        sources.append(frame)
    encoded = bake.encode_frames(sources, geometry=GEOMETRY, budget=1800, cap=60)
    blob, _ = stream.pack_banks(stream.defer_closes(encoded.frames), bank_size=1 << 14)
    return blob, sources


def baked_film(count: int) -> tuple[bytes, list[np.ndarray]]:
    rng = np.random.default_rng(31)
    sources = [rng.integers(0, 256, (192, 256, 3), dtype=np.uint8) for _ in range(count)]
    encoded = bake.encode_frames(sources, geometry=GEOMETRY, budget=1800, cap=60)
    blob, _ = stream.pack_banks(stream.defer_closes(encoded.frames), bank_size=1 << 14)
    return blob, sources


class TestPreview:
    @pytest.mark.ffmpeg
    def test_it_writes_a_picture_beside_its_source_for_each_sampled_frame(self, tmp_path):
        # Arrange
        blob, sources = baked_film(6)
        path = tmp_path / "preview.png"

        # Act
        preview.write(path, blob=blob, sources=sources, geometry=GEOMETRY)

        # Assert
        assert png_size(path) == (2 * GEOMETRY.width, preview.PREVIEW_FRAMES * GEOMETRY.height)

    @pytest.mark.ffmpeg
    def test_a_short_film_shows_every_frame_it_has(self, tmp_path):
        # Arrange
        blob, sources = baked_film(2)
        path = tmp_path / "preview.png"

        # Act
        preview.write(path, blob=blob, sources=sources, geometry=GEOMETRY)

        # Assert
        assert png_size(path) == (2 * GEOMETRY.width, 2 * GEOMETRY.height)

    @pytest.mark.ffmpeg
    def test_each_row_shows_the_console_picture_beside_its_source(self, tmp_path):
        # Arrange
        blob, sources = lattice_film(3)
        path = tmp_path / "preview.png"

        # Act
        preview.write(path, blob=blob, sources=sources, geometry=GEOMETRY)

        # Assert
        sheet = read_png(path)
        expected = np.concatenate(
            [np.concatenate([source, source], axis=1) for source in sources], axis=0
        )
        assert np.array_equal(sheet, expected)

    def test_a_film_with_no_source_frames_is_refused(self, tmp_path):
        # Arrange
        blob, _ = lattice_film(1)
        path = tmp_path / "preview.png"

        # Act
        with pytest.raises(ValueError) as refused:
            preview.write(path, blob=blob, sources=[], geometry=GEOMETRY)

        # Assert
        assert str(refused.value) == (
            "a preview needs at least one frame shown and one source frame"
        )


def video_shape(path: Path) -> tuple[int, int, int]:
    probed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-count_frames",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,nb_read_frames",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()
    width, height, count = (int(value) for value in probed.split(","))
    return width, height, count


class TestPreviewVideo:
    @pytest.mark.ffmpeg
    def test_the_video_holds_one_frame_per_replayed_field(self, tmp_path):
        # Arrange
        blob, _ = baked_film(4)
        path = tmp_path / "preview.mp4"
        fields = preview.field_count(blob)

        # Act
        preview.write_video(path, blob=blob, geometry=GEOMETRY)

        # Assert
        assert video_shape(path) == (GEOMETRY.width, GEOMETRY.height, fields)

    def test_a_video_suffix_chooses_the_video(self):
        # Arrange
        path = Path("out.mp4")

        # Act
        wanted = preview.wants_video(path)

        # Assert
        assert wanted is True

    def test_an_image_suffix_chooses_the_sheet(self):
        # Arrange
        path = Path("out.png")

        # Act
        wanted = preview.wants_video(path)

        # Assert
        assert wanted is False
