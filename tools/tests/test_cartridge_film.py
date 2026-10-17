import json
import logging
import subprocess
import sys
from pathlib import Path

import pytest
from fmvcore.testing import seeded
from lavfi import bake_only_argv, lavfi_clip

from smsggmedia import cartridge, dials, flags, limits, tune

FAKE = seeded()
FILM = FAKE.file_name(extension="mp4")

pytestmark = pytest.mark.ffmpeg


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    return lavfi_clip(tmp_path_factory.mktemp("clip") / "source.mp4", size="320x240", rate=30)


class TestShortfall:
    def test_it_names_the_overshoot_in_banks(self):
        # Arrange
        seconds = 120.0

        # Act
        result = cartridge.shortfall(banks=200, max_banks=62, seconds=seconds)

        # Assert
        assert "138 banks" in result

    def test_it_names_the_runtime_that_would_fit(self):
        # Arrange
        seconds = 120.0

        # Act
        result = cartridge.shortfall(banks=200, max_banks=62, seconds=seconds)

        # Assert
        assert "62 banks hold 0m37s" in result

    def test_it_never_suggests_trimming_silently(self):
        # Arrange
        seconds = 120.0

        # Act
        result = cartridge.shortfall(banks=200, max_banks=62, seconds=seconds)

        # Assert
        assert "--duration" in result

    def test_under_one_second_never_suggests_a_zero_duration(self):
        # Arrange
        seconds = 2.0

        # Act
        result = cartridge.shortfall(banks=3, max_banks=1, seconds=seconds)

        # Assert
        assert result == (
            "the stream needs 3 banks and the ceiling is 1, so not even one second of this "
            "film fits. Re-run with a lower --fps; nothing here will shorten the film for you."
        )

    def test_a_zero_length_source_is_refused(self):
        # Arrange
        seconds = 0.0

        # Act
        with pytest.raises(ValueError) as refused:
            cartridge.shortfall(banks=100, max_banks=62, seconds=seconds)

        # Assert
        assert str(refused.value) == "a source duration must be positive"


class TestResolveDenoise:
    def test_a_number_is_taken_as_given(self):
        # Arrange
        geometry = cartridge.geometry_for(8, 6)

        # Act
        result = dials.resolve_denoise(
            "4.5",
            tune.Footage(Path("unused.mp4"), start=0.0, duration=1.0),
            tune.EncodeSettings(geometry, budget=1400, cap=60, reuse=0.008),
            fps=12.0,
            max_per_frame=1000.0,
        )

        # Assert
        assert result == 4.5

    def test_it_reports_when_nothing_fits(self, clip, caplog):
        # Arrange
        caplog.set_level(logging.INFO, logger=dials.LOG.name)
        geometry = cartridge.geometry_for(8, 6)

        # Act
        dials.resolve_denoise(
            "auto",
            tune.Footage(clip, start=0.0, duration=1.0, scaler="area"),
            tune.EncodeSettings(geometry, budget=1400, cap=60, reuse=0.008),
            fps=6.0,
            max_per_frame=1.0,
        )

        # Assert
        assert "none fit" in caplog.text


OVERSIZED = [
    "--columns",
    "32",
    "--rows",
    "18",
    "--fps",
    "12",
    "--cap",
    "220",
    "--reuse",
    "0.0",
    "--max-banks",
    "1",
]


class TestOversizedFilm:
    def test_a_film_that_cannot_fit_is_refused(self, clip, tmp_path):
        # Arrange
        argv = bake_only_argv(clip, tmp_path) + OVERSIZED

        # Act
        result = cartridge.main(argv)

        # Assert
        assert result == 2

    def test_a_film_too_big_for_one_second_asks_for_a_lower_rate(self, clip, tmp_path, capsys):
        # Arrange
        argv = bake_only_argv(clip, tmp_path) + OVERSIZED

        # Act
        cartridge.main(argv)

        # Assert
        out = capsys.readouterr().out
        assert "not even one second of this film fits" in out
        assert "--duration 0" not in out


class TestTheFieldBudget:
    def test_the_capacity_is_the_whole_field_at_the_paced_rate(self):
        # Arrange
        expected = limits.FIELD_CYCLES // limits.VDP_WRITE_CYCLES

        # Act
        capacity = limits.FIELD_PAYLOAD_BYTES

        # Assert
        assert capacity == expected

    def test_the_arithmetic_ceiling_is_only_an_upper_bound(self):
        # Arrange
        ceiling = limits.FIELD_PAYLOAD_BYTES

        # Act
        measured = limits.MEASURED_FIELD_BUDGET

        # Assert
        assert measured < ceiling

    def test_the_default_budget_is_under_what_was_measured(self):
        # Arrange
        measured = limits.MEASURED_FIELD_BUDGET

        # Act
        budget = limits.DEFAULT_BUDGET

        # Assert
        assert budget < measured

    def test_the_default_budget_keeps_headroom_below_the_highest_measured(self):
        # Arrange
        headroom = limits.MEASURED_FIELD_BUDGET * 0.95

        # Act
        budget = limits.DEFAULT_BUDGET

        # Assert
        assert budget <= headroom

    def test_the_budget_leaves_room_past_the_closing_run(self):
        # Arrange
        closing = limits.CLOSE_RESERVE * 4

        # Act
        budget = limits.DEFAULT_BUDGET

        # Assert
        assert budget > closing


class TestTheCommand:
    def test_running_the_module_reaches_the_baker(self):
        # Arrange
        command = [sys.executable, "-m", "smsggmedia.cartridge", "--help"]

        # Act
        result = subprocess.run(command, capture_output=True, text=True, check=False)

        # Assert
        assert result.returncode == 0
        assert "--fps" in result.stdout

    def test_running_the_module_without_a_source_fails(self):
        # Arrange
        command = [sys.executable, "-m", "smsggmedia.cartridge"]

        # Act
        result = subprocess.run(command, capture_output=True, text=True, check=False)

        # Assert
        assert result.returncode == 2


class TestTheDitherFlag:
    def test_the_default_is_the_measured_strength(self):
        # Arrange
        parser = flags.build_parser()

        # Act
        args = parser.parse_args([FILM])

        # Assert
        assert args.dither == limits.DEFAULT_DITHER

    def test_it_can_be_turned_off(self):
        # Arrange
        parser = flags.build_parser()

        # Act
        args = parser.parse_args([FILM, "--dither", "0"])

        # Assert
        assert args.dither == 0.0

    def test_a_strength_past_half_a_step_is_refused(self):
        # Arrange
        parser = flags.build_parser()

        # Act
        with pytest.raises(SystemExit) as refused:
            parser.parse_args([FILM, "--dither", "1.5"])

        # Assert
        assert refused.value.code == 2


class TestMostMerged:
    def test_the_worst_frames_come_first(self):
        # Arrange
        per_frame = [4, 0, 9, 2, 7]

        # Act
        result = cartridge.most_merged(per_frame)

        # Assert
        assert result == [2, 4, 0]

    def test_a_frame_that_merged_nothing_is_not_named(self):
        # Arrange
        per_frame = [0, 3, 0]

        # Act
        result = cartridge.most_merged(per_frame)

        # Assert
        assert result == [1]


@pytest.fixture(scope="module")
def sounded_clip(tmp_path_factory):
    path = tmp_path_factory.mktemp("sounded") / "source.mp4"
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
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
    )
    return path


class TestSound:
    def test_a_film_with_a_soundtrack_bakes_psg_writes(self, sounded_clip, tmp_path):
        # Arrange
        argv = bake_only_argv(sounded_clip, tmp_path)

        # Act
        cartridge.main(argv)

        # Assert
        report = json.loads((tmp_path / "report.json").read_text())
        assert report["sound_writes"] > 0

    def test_a_silent_build_bakes_no_sound(self, sounded_clip, tmp_path):
        # Arrange
        argv = [*bake_only_argv(sounded_clip, tmp_path), "--silent"]

        # Act
        cartridge.main(argv)

        # Assert
        report = json.loads((tmp_path / "report.json").read_text())
        assert report["sound_writes"] == 0

    def test_a_master_system_build_routes_no_channel(self, sounded_clip, tmp_path):
        # Arrange
        argv = bake_only_argv(sounded_clip, tmp_path)

        # Act
        cartridge.main(argv)

        # Assert
        report = json.loads((tmp_path / "report.json").read_text())
        assert report["pan_writes"] == 0

    def test_a_game_gear_build_centres_a_mono_soundtrack_once(self, sounded_clip, tmp_path):
        # Arrange
        argv = [*bake_only_argv(sounded_clip, tmp_path), "--target", "gg"]

        # Act
        cartridge.main(argv)

        # Assert
        report = json.loads((tmp_path / "report.json").read_text())
        assert (report["sound_writes"] > 0, report["pan_writes"]) == (True, 1)

    def test_a_film_without_a_soundtrack_bakes_no_sound(self, clip, tmp_path):
        # Arrange
        argv = bake_only_argv(clip, tmp_path)

        # Act
        cartridge.main(argv)

        # Assert
        report = json.loads((tmp_path / "report.json").read_text())
        assert report["sound_writes"] == 0


SILENCE = "carries no audio track, so the cartridge will be silent"


class TestASourceWithoutSound:
    def test_the_bake_says_why_the_cartridge_will_be_silent(self, clip, tmp_path, capsys):
        # Arrange
        argv = bake_only_argv(clip, tmp_path)

        # Act
        cartridge.main(argv)

        # Assert
        assert (
            f"{clip} carries no audio track, so the cartridge will be silent. "
            "Nothing is wrong with the video; there is simply no soundtrack to encode."
        ) in capsys.readouterr().err

    def test_a_source_with_sound_raises_no_notice(self, sounded_clip, tmp_path, capsys):
        # Arrange
        argv = bake_only_argv(sounded_clip, tmp_path)

        # Act
        cartridge.main(argv)

        # Assert
        assert SILENCE not in capsys.readouterr().err

    def test_a_silent_build_raises_no_notice(self, clip, tmp_path, capsys):
        # Arrange
        argv = [*bake_only_argv(clip, tmp_path), "--silent"]

        # Act
        cartridge.main(argv)

        # Assert
        assert SILENCE not in capsys.readouterr().err


class TestTheWindowOnTheCommand:
    def test_a_start_past_the_end_of_the_source_stops_the_bake(self, clip, tmp_path, capsys):
        # Arrange
        argv = [*bake_only_argv(clip, tmp_path), "--start", "5"]

        # Act
        with pytest.raises(SystemExit) as stopped:
            cartridge.main(argv)

        # Assert
        assert stopped.value.code == 2
        assert "is past the end of a 2.0 s source" in capsys.readouterr().err


@pytest.fixture(scope="module")
def boxed_clip(tmp_path_factory):
    path = tmp_path_factory.mktemp("boxed") / "source.mp4"
    chain = "testsrc2=size=320x240:rate=30:duration=2,scale=320:160,pad=320:240:0:40:black"
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


class TestBars:
    def test_bars_in_the_source_are_found_and_reported(self, boxed_clip, tmp_path):
        # Arrange
        argv = bake_only_argv(boxed_clip, tmp_path)

        # Act
        cartridge.main(argv)

        # Assert
        report = json.loads((tmp_path / "report.json").read_text())
        assert report["bars"] == [320, 160, 0, 40]

    def test_a_source_without_bars_reports_none(self, clip, tmp_path):
        # Arrange
        argv = bake_only_argv(clip, tmp_path)

        # Act
        cartridge.main(argv)

        # Assert
        report = json.loads((tmp_path / "report.json").read_text())
        assert report["bars"] is None
