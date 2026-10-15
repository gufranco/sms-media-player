from __future__ import annotations

import subprocess

import pytest
from fmvcore.testing import seeded

from smsmedia import cartridge, limits, scout, tune

FAKE = seeded()
FILM = FAKE.file_name(extension="mp4")


def sample(start: float, error: float, per_frame: float) -> scout.Probe:
    return scout.Probe(start=start, error=error, per_frame=per_frame)


class TestWindowStarts:
    def test_it_walks_the_film_at_the_given_stride(self):
        # Arrange
        expected = [0.0, 2.0, 4.0, 6.0]

        # Act
        result = scout.window_starts(begin=0.0, end=10.0, span=4.0, stride=2.0)

        # Assert
        assert result == expected

    def test_no_window_runs_past_the_end(self):
        # Arrange
        span = 4.0
        end = 10.0

        # Act
        result = scout.window_starts(begin=0.0, end=end, span=span, stride=3.0)

        # Assert
        assert all(start + span <= end for start in result)

    def test_a_film_shorter_than_the_window_yields_nothing(self):
        # Arrange
        end = 3.0

        # Act
        result = scout.window_starts(begin=0.0, end=end, span=4.0, stride=1.0)

        # Assert
        assert result == []

    def test_a_film_exactly_the_window_length_yields_one(self):
        # Arrange
        span = 4.0

        # Act
        result = scout.window_starts(begin=0.0, end=span, span=span, stride=1.0)

        # Assert
        assert result == [0.0]

    def test_it_honours_a_late_beginning(self):
        # Arrange
        begin = 5.0

        # Act
        result = scout.window_starts(begin=begin, end=11.0, span=2.0, stride=2.0)

        # Assert
        assert result[0] == 5.0

    def test_a_stride_of_zero_is_refused(self):
        # Arrange
        stride = 0.0

        # Act
        with pytest.raises(ValueError) as refused:
            scout.window_starts(begin=0.0, end=10.0, span=2.0, stride=stride)

        # Assert
        assert str(refused.value) == "a stride must be positive"

    def test_a_span_of_zero_is_refused(self):
        # Arrange
        span = 0.0

        # Act
        with pytest.raises(ValueError) as refused:
            scout.window_starts(begin=0.0, end=10.0, span=span, stride=1.0)

        # Assert
        assert str(refused.value) == "a span must be positive"


class TestSummariseWindow:
    def test_it_averages_the_probes_inside_the_window(self):
        # Arrange
        probes = [sample(0.0, 0.01, 1000.0), sample(2.0, 0.03, 3000.0), sample(9.0, 1.0, 9.0)]

        # Act
        result = scout.summarise_window(probes, start=0.0, duration=4.0)

        # Assert
        assert result.error == pytest.approx(0.02)
        assert result.per_frame == pytest.approx(2000.0)

    def test_a_probe_exactly_on_the_far_edge_is_excluded(self):
        # Arrange
        probes = [sample(0.0, 0.01, 1000.0), sample(4.0, 1.0, 9.0)]

        # Act
        result = scout.summarise_window(probes, start=0.0, duration=4.0)

        # Assert
        assert result.error == pytest.approx(0.01)

    def test_a_probe_exactly_on_the_near_edge_is_included(self):
        # Arrange
        probes = [sample(4.0, 0.02, 2000.0)]

        # Act
        result = scout.summarise_window(probes, start=4.0, duration=4.0)

        # Assert
        assert result.per_frame == pytest.approx(2000.0)

    def test_a_window_covering_no_probe_is_refused(self):
        # Arrange
        probes = [sample(9.0, 0.1, 1.0)]

        # Act
        with pytest.raises(ValueError) as refused:
            scout.summarise_window(probes, start=0.0, duration=4.0)

        # Assert
        assert str(refused.value) == "no probe falls inside the window at 0.0s"

    def test_it_carries_the_window_position(self):
        # Arrange
        probes = [sample(1.0, 0.1, 100.0)]

        # Act
        result = scout.summarise_window(probes, start=0.0, duration=4.0)

        # Assert
        assert (result.start, result.duration) == (0.0, 4.0)


class TestBanksFor:
    def test_it_converts_bytes_per_frame_into_banks(self):
        # Arrange
        per_frame = 2048.0

        # Act
        result = scout.banks_for(per_frame=per_frame, duration=8.0, fps=8.0)

        # Assert
        assert result == pytest.approx(8.0)

    def test_a_longer_film_needs_more_banks(self):
        # Arrange
        short = scout.banks_for(per_frame=2000.0, duration=10.0, fps=12.0)

        # Act
        long = scout.banks_for(per_frame=2000.0, duration=40.0, fps=12.0)

        # Assert
        assert long > short

    def test_a_film_of_no_length_is_refused(self):
        # Arrange
        duration = 0.0

        # Act
        with pytest.raises(ValueError) as refused:
            scout.banks_for(per_frame=2000.0, duration=duration, fps=12.0)

        # Assert
        assert str(refused.value) == "a duration must be positive"


class TestRankWindows:
    def test_the_cheapest_window_comes_first(self):
        # Arrange
        probes = [sample(0.0, 0.05, 5000.0), sample(4.0, 0.01, 1000.0)]

        # Act
        result = scout.rank_windows(probes, duration=2.0, stride=4.0, fps=12.0, end=8.0)

        # Assert
        assert result[0].start == 4.0

    def test_every_window_is_ranked(self):
        # Arrange
        probes = [sample(0.0, 0.05, 5000.0), sample(4.0, 0.01, 1000.0)]

        # Act
        result = scout.rank_windows(probes, duration=2.0, stride=4.0, fps=12.0, end=8.0)

        # Assert
        assert len(result) == 2

    def test_it_reports_whether_a_window_fits(self):
        # Arrange
        probes = [sample(0.0, 0.9, 100000.0)]

        # Act
        result = scout.rank_windows(
            probes, duration=2.0, stride=4.0, fps=12.0, end=2.0, max_banks=1
        )

        # Assert
        assert result[0].fits is False

    def test_a_cheap_window_fits(self):
        # Arrange
        probes = [sample(0.0, 0.01, 100.0)]

        # Act
        result = scout.rank_windows(
            probes, duration=2.0, stride=4.0, fps=12.0, end=2.0, max_banks=62
        )

        # Assert
        assert result[0].fits is True

    def test_windows_with_no_probe_are_skipped_rather_than_failing(self):
        # Arrange
        probes = [sample(0.0, 0.01, 100.0), sample(20.0, 0.02, 200.0)]

        # Act
        result = scout.rank_windows(probes, duration=2.0, stride=2.0, fps=12.0, end=24.0)

        # Assert
        assert len(result) >= 2
        assert all(window.per_frame > 0.0 for window in result)

    def test_no_rankable_window_yields_an_empty_list(self):
        # Arrange
        probes: list[scout.Probe] = []

        # Act
        result = scout.rank_windows(probes, duration=2.0, stride=2.0, fps=12.0, end=10.0)

        # Assert
        assert result == []


needs_ffmpeg = pytest.mark.ffmpeg


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    path = tmp_path_factory.mktemp("scout") / "source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x240:rate=30:duration=6",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
    )
    return path


@needs_ffmpeg
class TestProfile:
    def _probes(self, clip, **extra):
        return scout.profile(
            tune.Footage(clip, start=0.0, duration=4.0, scaler="area"),
            tune.EncodeSettings(
                cartridge.geometry_for(8, 6), budget=1400, cap=60, reuse=0.008, **extra
            ),
            fps=6.0,
            denoise=0.0,
            probing=scout.Probing(probe_seconds=0.5, stride_seconds=2.0),
        )

    def test_it_takes_one_probe_per_stride(self, clip):
        # Arrange
        source = clip

        # Act
        result = self._probes(source)

        # Assert
        assert len(result) == 2

    def test_every_probe_carries_a_cost(self, clip):
        # Arrange
        source = clip

        # Act
        result = self._probes(source)

        # Assert
        assert all(p.per_frame > 0.0 for p in result)

    def test_every_probe_carries_an_error(self, clip):
        # Arrange
        source = clip

        # Act
        result = self._probes(source)

        # Assert
        assert all(0.0 < p.error < 1.0 for p in result)

    def test_probes_are_ordered_by_position(self, clip):
        # Arrange
        source = clip

        # Act
        result = self._probes(source)

        # Assert
        starts = [p.start for p in result]
        assert starts == sorted(starts)

    def test_a_probe_dithers_like_the_bake_unless_told_otherwise(self, clip):
        # Arrange
        shipped = self._probes(clip)

        # Act
        explicit = self._probes(clip, dither=limits.DEFAULT_DITHER)

        # Assert
        assert [p.per_frame for p in shipped] == [p.per_frame for p in explicit]

    def test_turning_the_dither_off_changes_what_a_probe_costs(self, clip):
        # Arrange
        shipped = self._probes(clip)

        # Act
        plain = self._probes(clip, dither=0.0)

        # Assert
        assert [p.per_frame for p in shipped] != [p.per_frame for p in plain]


@needs_ffmpeg
class TestMain:
    def _argv(self, clip, extra=None):
        return [
            str(clip),
            "--duration",
            "2",
            "--fps",
            "6",
            "--probe",
            "0.5",
            "--stride",
            "1",
            "--columns",
            "8",
            "--rows",
            "6",
            "--cap",
            "60",
            "--denoise",
            "0",
            *(extra or []),
        ]

    def test_a_scan_succeeds(self, clip):
        # Arrange
        argv = self._argv(clip)

        # Act
        status = scout.main(argv)

        # Assert
        assert status == 0

    def test_it_reports_the_ranking(self, clip, capsys):
        # Arrange
        argv = self._argv(clip)

        # Act
        status = scout.main(argv)

        # Assert
        assert status == 0
        assert "banks" in capsys.readouterr().out

    def test_it_says_the_figures_are_estimates(self, clip, capsys):
        # Arrange
        argv = self._argv(clip)

        # Act
        status = scout.main(argv)

        # Assert
        assert status == 0
        assert "estimates" in capsys.readouterr().out

    def test_a_window_longer_than_the_film_is_refused(self, clip):
        # Arrange
        argv = [
            str(clip),
            "--duration",
            "999",
            "--fps",
            "6",
            "--probe",
            "0.5",
            "--stride",
            "1",
            "--columns",
            "8",
            "--rows",
            "6",
            "--cap",
            "60",
            "--denoise",
            "0",
        ]

        # Act
        status = scout.main(argv)

        # Assert
        assert status == 2


class TestArguments:
    def test_a_dither_past_half_a_step_is_refused(self):
        # Arrange
        parser = scout.build_parser()

        # Act
        with pytest.raises(SystemExit) as refused:
            parser.parse_args([FILM, "--dither", "1.5"])

        # Assert
        assert refused.value.code == 2

    def test_a_negative_denoise_is_refused(self):
        # Arrange
        parser = scout.build_parser()

        # Act
        with pytest.raises(SystemExit) as refused:
            parser.parse_args([FILM, "--denoise", "-1"])

        # Assert
        assert refused.value.code == 2

    def test_the_defaults_match_the_bake(self):
        # Arrange
        parser = scout.build_parser()

        # Act
        args = parser.parse_args([FILM])

        # Assert
        assert (args.dither, args.scaler, args.max_banks) == (
            limits.DEFAULT_DITHER,
            limits.DEFAULT_SCALER,
            limits.DEFAULT_MAX_BANKS,
        )
