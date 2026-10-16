import io
import json
import logging
import subprocess
import sys
from pathlib import Path

import pytest
from fmvcore.testing import seeded

from smsmedia import bake, cartridge, dials, limits, output, tune

FAKE = seeded()
FILM = FAKE.file_name(extension="mp4")

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


class TestRoomPerFrame:
    def test_it_shares_the_cartridge_across_the_frames(self):
        # Arrange
        frame_count = 480

        # Act
        result = dials.room_per_frame(max_banks=62, frame_count=frame_count, fields=1)

        # Assert
        assert result == pytest.approx(62 * 16384 / 480)

    def test_padding_comes_out_of_the_share(self):
        # Arrange
        fields = 5

        # Act
        padded = dials.room_per_frame(max_banks=62, frame_count=480, fields=fields)

        # Assert
        assert padded == pytest.approx(62 * 16384 / 480 - 4)

    def test_a_longer_film_leaves_each_frame_less(self):
        # Arrange
        short = dials.room_per_frame(max_banks=62, frame_count=240, fields=5)

        # Act
        long = dials.room_per_frame(max_banks=62, frame_count=960, fields=5)

        # Assert
        assert long < short

    def test_it_never_returns_a_share_below_one_byte(self):
        # Arrange
        frame_count = 1_000_000

        # Act
        result = dials.room_per_frame(max_banks=1, frame_count=frame_count, fields=5)

        # Assert
        assert result >= 1.0

    def test_a_film_with_no_frames_is_refused(self):
        # Arrange
        frame_count = 0

        # Act
        with pytest.raises(ValueError) as refused:
            dials.room_per_frame(max_banks=62, frame_count=frame_count, fields=5)

        # Assert
        assert str(refused.value) == "a film needs at least one frame"


class TestGeometryFor:
    def test_the_picture_is_centred_in_the_visible_rows(self):
        # Arrange
        rows = 18

        # Act
        result = cartridge.geometry_for(32, rows)

        # Assert
        assert result.top_row == 3

    def test_a_full_height_picture_starts_at_the_top(self):
        # Arrange
        rows = 24

        # Act
        result = cartridge.geometry_for(32, rows)

        # Assert
        assert result.top_row == 0

    def test_the_geometry_carries_the_requested_shape(self):
        # Arrange
        rows = 18

        # Act
        result = cartridge.geometry_for(32, rows)

        # Assert
        assert (result.columns, result.rows) == (32, 18)


class TestWriteHeader:
    def test_it_states_the_bank_count(self, tmp_path):
        # Arrange
        target = tmp_path / "movie.h"

        # Act
        output.write_header(
            target,
            banks=7,
            frame_count=3,
            field_count=9,
            hold_fields=6,
            first_bank_symbol="movie_bin_PART0_bank",
        )

        # Assert
        assert "#define MOVIE_BANKS 7u" in target.read_text()

    def test_it_states_the_frame_count(self, tmp_path):
        # Arrange
        target = tmp_path / "movie.h"

        # Act
        output.write_header(
            target,
            banks=7,
            frame_count=3,
            field_count=9,
            hold_fields=6,
            first_bank_symbol="movie_bin_PART0_bank",
        )

        # Assert
        assert "#define MOVIE_FRAMES 3u" in target.read_text()

    def test_it_names_the_first_bank_symbol(self, tmp_path):
        # Arrange
        target = tmp_path / "movie.h"

        # Act
        output.write_header(
            target,
            banks=1,
            frame_count=1,
            field_count=9,
            hold_fields=6,
            first_bank_symbol="movie_bin_PART0_bank",
        )

        # Assert
        assert "#define MOVIE_FIRST_BANK movie_bin_PART0_bank" in target.read_text()

    def test_it_creates_the_directory(self, tmp_path):
        # Arrange
        target = tmp_path / "generated" / "movie.h"

        # Act
        output.write_header(
            target, banks=1, frame_count=1, field_count=9, hold_fields=6, first_bank_symbol="b"
        )

        # Assert
        assert target.is_file() is True


class TestMain:
    def test_it_writes_the_stream(self, clip, tmp_path):
        # Arrange
        argv = _argv(clip, tmp_path)

        # Act
        cartridge.main(argv)

        # Assert
        assert (tmp_path / "assets" / "movie.bin").stat().st_size > 0

    def test_the_stream_is_a_whole_number_of_banks(self, clip, tmp_path):
        # Arrange
        argv = _argv(clip, tmp_path)

        # Act
        cartridge.main(argv)

        # Assert
        size = (tmp_path / "assets" / "movie.bin").stat().st_size
        assert size % limits.BANK_BYTES == 0

    def test_it_writes_the_generated_header(self, clip, tmp_path):
        # Arrange
        argv = _argv(clip, tmp_path)

        # Act
        cartridge.main(argv)

        # Assert
        assert (tmp_path / "generated" / "movie.h").is_file() is True

    def test_the_report_counts_the_frames(self, clip, tmp_path):
        # Arrange
        argv = _argv(clip, tmp_path)

        # Act
        cartridge.main(argv)

        # Assert
        report = json.loads((tmp_path / "report.json").read_text())
        assert report["frames"] > 0

    def test_the_report_names_the_dither_it_baked_with(self, clip, tmp_path):
        # Arrange
        argv = [*_argv(clip, tmp_path), "--dither", "0.5"]

        # Act
        cartridge.main(argv)

        # Assert
        report = json.loads((tmp_path / "report.json").read_text())
        assert report["dither"] == 0.5

    def test_the_report_names_where_detail_was_merged_away(self, clip, tmp_path):
        # Arrange
        argv = _argv(clip, tmp_path)

        # Act
        cartridge.main(argv)

        # Assert
        report = json.loads((tmp_path / "report.json").read_text())
        named = report["most_merged_frames"]
        assert len(named) <= cartridge.MOST_MERGED_SHOWN
        assert all(0 <= frame < report["frames"] for frame in named)
        assert len(set(named)) == len(named)

    def test_a_preview_is_written_when_asked(self, clip, tmp_path):
        # Arrange
        path = tmp_path / "preview.png"

        # Act
        cartridge.main([*_argv(clip, tmp_path), "--preview", str(path)])

        # Assert
        assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    def test_no_slot_collision_survives_a_bake(self, clip, tmp_path):
        # Arrange
        argv = _argv(clip, tmp_path)

        # Act
        cartridge.main(argv)

        # Assert
        report = json.loads((tmp_path / "report.json").read_text())
        assert report["slot_collisions"] == 0

    def test_a_clean_bake_reports_success(self, clip, tmp_path):
        # Arrange
        argv = _argv(clip, tmp_path)

        # Act
        result = cartridge.main(argv)

        # Assert
        assert result == 0


class TestBundle:
    def test_a_bundle_carries_the_film_the_cartridge_baked(self, clip, tmp_path):
        # Arrange
        argv = [*_argv(clip, tmp_path), "--bundle", str(tmp_path / "bundle")]

        # Act
        cartridge.main(argv)

        # Assert
        baked = (tmp_path / "assets" / "movie.bin").read_bytes()
        assert (tmp_path / "bundle" / "movie" / "assets" / "movie.bin").read_bytes() == baked

    def test_the_bundle_guide_names_the_picture_it_was_baked_for(self, clip, tmp_path):
        # Arrange
        argv = [*_argv(clip, tmp_path), "--bundle", str(tmp_path / "bundle")]

        # Act
        cartridge.main(argv)

        # Assert
        assert "a picture of 8 by 6 cells" in (tmp_path / "bundle" / "README.md").read_text()


UNCAPPED_FPS = 12.0


class TestDialReports:
    def test_reports_go_to_the_output_of_the_run_that_asked(self):
        # Arrange
        dials.LOG.addHandler(logging.StreamHandler(io.StringIO()))

        # Act
        cartridge.show_dial_reports()

        # Assert
        assert [handler.stream for handler in dials.LOG.handlers] == [sys.stdout]


def _tight(clip, tmp_path, *extra: str) -> list[str]:
    return [
        str(clip),
        "--duration",
        "1",
        "--max-banks",
        "1",
        "--denoise",
        "0",
        "--reuse",
        "0.008",
        "--assets",
        str(tmp_path / "assets"),
        "--generated",
        str(tmp_path / "generated"),
        "--report",
        str(tmp_path / "report.json"),
        *extra,
    ]


class TestStepDown:
    def test_a_film_too_big_for_the_cartridge_steps_down_until_it_fits(self, clip, tmp_path):
        # Arrange
        argv = _tight(clip, tmp_path)

        # Act
        code = cartridge.main(argv)

        # Assert
        report = json.loads((tmp_path / "report.json").read_text())
        assert (code, report["banks"], report["fps"] < UNCAPPED_FPS) == (0, 1, True)

    def test_a_fixed_frame_rate_is_never_stepped_down(self, clip, tmp_path):
        # Arrange
        argv = _tight(clip, tmp_path, "--fps", "12")

        # Act
        code = cartridge.main(argv)

        # Assert
        report = json.loads((tmp_path / "report.json").read_text())
        assert (code, report["fps"]) == (2, 12.0)


def _argv(clip, tmp_path) -> list[str]:
    return [
        str(clip),
        "--fps",
        "4",
        "--duration",
        "1",
        "--columns",
        "8",
        "--rows",
        "6",
        "--cap",
        "60",
        "--assets",
        str(tmp_path / "assets"),
        "--generated",
        str(tmp_path / "generated"),
        "--report",
        str(tmp_path / "report.json"),
    ]


def test_the_name_table_base_is_where_smslib_puts_it():
    # Arrange
    expected = 0x3800

    # Act
    base = bake.NAME_TABLE_BASE

    # Assert
    assert base == expected


class TestCapacity:
    def test_a_stream_inside_the_ceiling_fits(self):
        # Arrange
        banks = 40

        # Act
        result = cartridge.fits(banks=banks, max_banks=62)

        # Assert
        assert result is True

    def test_a_stream_over_the_ceiling_does_not(self):
        # Arrange
        banks = 200

        # Act
        result = cartridge.fits(banks=banks, max_banks=62)

        # Assert
        assert result is False

    def test_a_stream_exactly_at_the_ceiling_fits(self):
        # Arrange
        banks = 62

        # Act
        result = cartridge.fits(banks=banks, max_banks=62)

        # Assert
        assert result is True


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
        assert "37s" in result or "0:37" in result

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
        argv = _argv(clip, tmp_path) + OVERSIZED

        # Act
        result = cartridge.main(argv)

        # Assert
        assert result == 2

    def test_a_film_too_big_for_one_second_asks_for_a_lower_rate(self, clip, tmp_path, capsys):
        # Arrange
        argv = _argv(clip, tmp_path) + OVERSIZED

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
        command = [sys.executable, "-m", "smsmedia.cartridge", "--help"]

        # Act
        result = subprocess.run(command, capture_output=True, text=True, check=False)

        # Assert
        assert result.returncode == 0
        assert "--fps" in result.stdout

    def test_running_the_module_without_a_source_fails(self):
        # Arrange
        command = [sys.executable, "-m", "smsmedia.cartridge"]

        # Act
        result = subprocess.run(command, capture_output=True, text=True, check=False)

        # Assert
        assert result.returncode == 2


class TestTheDitherFlag:
    def test_the_default_is_the_measured_strength(self):
        # Arrange
        parser = cartridge.build_parser()

        # Act
        args = parser.parse_args([FILM])

        # Assert
        assert args.dither == limits.DEFAULT_DITHER

    def test_it_can_be_turned_off(self):
        # Arrange
        parser = cartridge.build_parser()

        # Act
        args = parser.parse_args([FILM, "--dither", "0"])

        # Assert
        assert args.dither == 0.0

    def test_a_strength_past_half_a_step_is_refused(self):
        # Arrange
        parser = cartridge.build_parser()

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
        argv = _argv(sounded_clip, tmp_path)

        # Act
        cartridge.main(argv)

        # Assert
        report = json.loads((tmp_path / "report.json").read_text())
        assert report["sound_writes"] > 0

    def test_a_silent_build_bakes_no_sound(self, sounded_clip, tmp_path):
        # Arrange
        argv = [*_argv(sounded_clip, tmp_path), "--silent"]

        # Act
        cartridge.main(argv)

        # Assert
        report = json.loads((tmp_path / "report.json").read_text())
        assert report["sound_writes"] == 0

    def test_a_film_without_a_soundtrack_bakes_no_sound(self, clip, tmp_path):
        # Arrange
        argv = _argv(clip, tmp_path)

        # Act
        cartridge.main(argv)

        # Assert
        report = json.loads((tmp_path / "report.json").read_text())
        assert report["sound_writes"] == 0


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
        argv = _argv(boxed_clip, tmp_path)

        # Act
        cartridge.main(argv)

        # Assert
        report = json.loads((tmp_path / "report.json").read_text())
        assert report["bars"] == [320, 160, 0, 40]

    def test_a_source_without_bars_reports_none(self, clip, tmp_path):
        # Arrange
        argv = _argv(clip, tmp_path)

        # Act
        cartridge.main(argv)

        # Assert
        report = json.loads((tmp_path / "report.json").read_text())
        assert report["bars"] is None
