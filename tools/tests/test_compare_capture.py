from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from smsggmedia import bake, capture, lattice, stream, target

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "scripts" / "compare_capture.py"
GEOMETRY = bake.Geometry(columns=32, rows=24, top_row=0)
BOOT_FIELDS = 3
FIELD_RATE = "60000/1001"
pytestmark = pytest.mark.ffmpeg


def load():
    spec = importlib.util.spec_from_file_location("compare_capture", SCRIPT)
    if spec is None or spec.loader is None:
        msg = f"cannot import {SCRIPT}"
        raise AssertionError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules["compare_capture"] = module
    spec.loader.exec_module(module)
    return module


def gradient(shift: int) -> np.ndarray:
    columns = np.arange(GEOMETRY.width, dtype=np.int32)[None, :, None]
    rows = np.arange(GEOMETRY.height, dtype=np.int32)[:, None, None]
    return ((columns * 3 + rows + shift * 40) % 256).astype(np.uint8).repeat(3, axis=2)


def lossless(path: Path, frames: np.ndarray) -> None:
    height, width = frames.shape[1:3]
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{width}x{height}",
            "-r",
            FIELD_RATE,
            "-i",
            "-",
            "-c:v",
            "ffv1",
            "-pix_fmt",
            "bgr0",
            str(path),
        ],
        input=frames.tobytes(),
        check=True,
    )


@pytest.fixture(scope="module")
def gate():
    return load()


@pytest.fixture(scope="module")
def made(tmp_path_factory):
    folder = tmp_path_factory.mktemp("compare")
    film = np.stack([gradient(shift // 6) for shift in range(48)])
    encoded = bake.encode_frames(list(film[::6]), geometry=GEOMETRY, budget=400, cap=160)
    paced = [stream.pace(chunks, fields=6) for chunks in encoded.frames]
    blob, _ = stream.pack_banks(paced, bank_size=1 << 14)
    (folder / "movie.bin").write_bytes(blob)
    played = capture.replay_fields(blob)
    border = np.zeros((played.fields.shape[0] + BOOT_FIELDS, 240, 256, 3), dtype=np.uint8)
    border[BOOT_FIELDS:, 24:216] = played.fields
    lossless(folder / "capture.mkv", border)
    lossless(folder / "elsewhere.mkv", np.full_like(border, 33))
    lossless(folder / "source.mkv", film)
    return folder


class TestReading:
    def test_a_capture_is_cut_to_the_picture(self, gate, made):
        # Arrange
        recording = made / "capture.mkv"

        # Act
        frames = gate.read_capture(recording)

        # Assert
        assert frames.shape[1:] == (192, 256, 3)


class TestTheReport:
    def test_the_emulator_matches_the_oracle(self, gate, made, tmp_path):
        # Arrange
        out = tmp_path / "report.json"
        argv = _argv(made, out)

        # Act
        gate.main(argv)

        # Assert
        report = json.loads(out.read_text())
        assert (report["emulator_offset"], report["emulator_mismatches"]) == (BOOT_FIELDS, 0)

    def test_every_measure_is_reported(self, gate, made, tmp_path):
        # Arrange
        out = tmp_path / "report.json"
        argv = _argv(made, out)

        # Act
        gate.main(argv)

        # Assert
        report = json.loads(out.read_text())
        assert set(report) >= {
            "on_screen_error",
            "frame_error",
            "blurred_frame_error",
            "lattice_floor",
            "mixed_share",
            "lag_first_s",
            "lag_median_s",
            "lag_last_s",
        }

    def test_a_clean_run_exits_zero(self, gate, made, tmp_path):
        # Arrange
        argv = _argv(made, tmp_path / "report.json")

        # Act
        code = gate.main(argv)

        # Assert
        assert code == 0

    def test_a_sheet_of_the_worst_field_is_written(self, gate, made, tmp_path):
        # Arrange
        sheet = tmp_path / "sheet.png"
        argv = [*_argv(made, tmp_path / "report.json"), "--sheet", str(sheet)]

        # Act
        gate.main(argv)

        # Assert
        assert sheet.stat().st_size > 0

    def test_a_capture_that_is_not_this_stream_fails(self, gate, made, tmp_path):
        # Arrange
        argv = _argv(made, tmp_path / "report.json")
        argv[argv.index("--capture") + 1] = str(made / "elsewhere.mkv")

        # Act
        code = gate.main(argv)

        # Assert
        assert code == 1

    def test_a_video_that_is_not_a_capture_is_refused_by_name(self, gate, made):
        # Arrange
        video = made / "source.mkv"

        # Act
        with pytest.raises(ValueError) as refused:
            gate.read_capture(video)

        # Assert
        assert str(refused.value) == (
            f"{video} is not a 256x240 mednafen recording of the Master System picture"
        )


def _argv(made: Path, out: Path) -> list[str]:
    return [
        "--stream",
        str(made / "movie.bin"),
        "--capture",
        str(made / "capture.mkv"),
        "--source",
        str(made / "source.mkv"),
        "--start",
        "0",
        "--json",
        str(out),
    ]


class TestTheLeadIn:
    def test_a_lead_in_shifts_the_source_rather_than_counting_as_lag(self, gate, made, tmp_path):
        # Arrange
        out = tmp_path / "report.json"
        argv = [*_argv(made, out), "--lead", "6"]

        # Act
        gate.main(argv)

        # Assert
        report = json.loads(out.read_text())
        assert report["lag_first_s"] > 0.0


class TestTheSheetWithoutMixing:
    def test_a_clean_film_still_shows_a_frame_beside_its_source(self, gate, made):
        # Arrange
        played = gate.capture.replay_fields((made / "movie.bin").read_bytes())
        source = played.fields.copy()

        # Act
        previous, middle, following = gate.worst_frame(played, source)

        # Assert
        assert previous <= middle <= following
        assert middle in played.completes


GG_GEOMETRY = bake.Geometry(columns=20, rows=18, top_row=3, left_column=6)


@pytest.fixture(scope="module")
def made_gg(tmp_path_factory):
    folder = tmp_path_factory.mktemp("compare-gg")
    film = np.stack([gradient(shift // 6)[:144, :160] for shift in range(48)])
    encoded = bake.encode_frames(
        list(film[::6]), geometry=GG_GEOMETRY, budget=400, cap=160, system=target.GAME_GEAR
    )
    paced = [stream.pace(chunks, fields=6) for chunks in encoded.frames]
    blob, _ = stream.pack_banks(paced, bank_size=1 << 14)
    (folder / "movie.bin").write_bytes(blob)
    played = capture.replay_fields(blob)
    window = np.zeros((played.fields.shape[0] + BOOT_FIELDS, 144, 160, 3), dtype=np.uint8)
    window[BOOT_FIELDS:] = played.fields[:, 24:168, 48:208]
    lossless(folder / "capture.mkv", window)
    lossless(folder / "source.mkv", film)
    return folder


class TestAGameGearCapture:
    def test_its_window_matches_the_oracle(self, gate, made_gg, tmp_path):
        # Arrange
        out = tmp_path / "report.json"
        argv = [*_argv(made_gg, out), "--target", "gg"]

        # Act
        gate.main(argv)

        # Assert
        report = json.loads(out.read_text())
        assert (report["emulator_offset"], report["emulator_mismatches"]) == (BOOT_FIELDS, 0)

    def test_its_floor_is_measured_on_the_game_gear_colours(self, gate, made_gg, tmp_path):
        # Arrange
        out = tmp_path / "report.json"
        argv = [*_argv(made_gg, out), "--target", "gg"]
        film = gradient(0)[:144, :160]

        # Act
        gate.main(argv)

        # Assert
        report = json.loads(out.read_text())
        assert report["lattice_floor"] < capture.lattice_floor(film, lattice.MASTER_SYSTEM) / 2

    def test_a_master_system_recording_is_refused_by_name(self, gate, made):
        # Arrange
        recording = made / "capture.mkv"

        # Act
        with pytest.raises(ValueError) as refused:
            gate.read_capture(recording, gate.SCREENS["gg"])

        # Assert
        assert str(refused.value) == (
            f"{recording} is not a 160x144 mednafen recording of the Game Gear picture"
        )
