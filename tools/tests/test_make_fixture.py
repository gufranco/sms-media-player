from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "scripts" / "make_fixture.py"


def load():
    spec = importlib.util.spec_from_file_location("make_fixture", SCRIPT)
    if spec is None or spec.loader is None:
        msg = f"cannot import {SCRIPT}"
        raise AssertionError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules["make_fixture"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def maker():
    return load()


def field(maker):
    return maker.block_field()


class TestTheScriptExists:
    def test_the_generator_is_in_the_repository(self):
        # Arrange
        script = SCRIPT

        # Act
        exists = script.is_file()

        # Assert
        assert exists is True

    def test_the_clip_it_writes_is_committed(self, maker):
        # Arrange
        target = maker.TARGET

        # Act
        exists = target.is_file()

        # Assert
        assert exists is True

    def test_the_clip_is_small_enough_to_carry(self, maker):
        # Arrange
        target = maker.TARGET

        # Act
        size = target.stat().st_size

        # Assert
        assert size < 128 * 1024


class TestTheFrames:
    def test_a_frame_is_the_console_raster(self, maker):
        # Arrange
        base, grid = field(maker)

        # Act
        frame = maker.frame_at(0, base, grid)

        # Assert
        assert frame.shape == (maker.HEIGHT, maker.WIDTH, 3)

    def test_the_same_index_gives_the_same_frame(self, maker):
        # Arrange
        base, grid = field(maker)
        first = maker.frame_at(5, base, grid)

        # Act
        second = maker.frame_at(5, base, grid)

        # Assert
        assert np.array_equal(first, second) is True

    def test_successive_frames_differ(self, maker):
        # Arrange
        base, grid = field(maker)
        first = maker.frame_at(0, base, grid)

        # Act
        second = maker.frame_at(1, base, grid)

        # Assert
        assert np.array_equal(first, second) is False

    def test_no_eight_by_eight_cell_is_flat(self, maker):
        # Arrange
        base, grid = field(maker)

        # Act
        frame = maker.frame_at(3, base, grid)

        # Assert
        cells = frame.reshape(maker.HEIGHT // 8, 8, maker.WIDTH // 8, 8, 3).transpose(0, 2, 1, 3, 4)
        flat = cells.reshape(-1, 64, 3)
        assert bool(np.any(flat.min(axis=1) == flat.max(axis=1))) is False

    def test_the_frame_uses_the_whole_range(self, maker):
        # Arrange
        base, grid = field(maker)

        # Act
        frame = maker.frame_at(7, base, grid)

        # Assert
        assert int(frame.min()) < 40
        assert int(frame.max()) > 215


needs_ffmpeg = pytest.mark.ffmpeg


@needs_ffmpeg
class TestTheClipIsReproducible:
    def test_two_builds_write_the_same_bytes(self, maker, tmp_path):
        # Arrange
        first = maker.build(tmp_path / "first.mp4")

        # Act
        second = maker.build(tmp_path / "second.mp4")

        # Assert
        assert (
            hashlib.sha256(first.read_bytes()).hexdigest()
            == hashlib.sha256(second.read_bytes()).hexdigest()
        )

    def test_the_command_reports_where_it_wrote(self, maker, tmp_path, capsys):
        # Arrange
        target = tmp_path / "fixture.mp4"

        # Act
        code = maker.main(target)

        # Assert
        assert code == 0
        assert f"wrote {target}" in capsys.readouterr().out

    def test_a_failing_encoder_is_reported_with_its_exit_code(self, maker, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setattr(
            maker, "encoder_command", lambda _target: ["sh", "-c", "cat >/dev/null; exit 3"]
        )

        # Act
        with pytest.raises(RuntimeError) as refused:
            maker.build(tmp_path / "broken.mp4")

        # Assert
        assert str(refused.value) == "ffmpeg exited 3"
