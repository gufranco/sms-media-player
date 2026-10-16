import pytest
from fmvcore.testing import seeded

from smsmedia import cartridge, flags, frames, limits, scout

FAKE = seeded()
FILM = FAKE.file_name(extension="mp4")


def refusal_code(parser, argv: list[str]) -> int | str | None:
    with pytest.raises(SystemExit) as refused:
        parser.parse_args(argv)
    return refused.value.code


class TestTheWindowFlags:
    @pytest.mark.parametrize("value", ["-1", "nan", "inf", "14401"])
    def test_an_out_of_range_start_is_refused(self, value):
        # Arrange
        parser = flags.build_parser()

        # Act
        code = refusal_code(parser, [FILM, "--start", value])

        # Assert
        assert code == 2

    @pytest.mark.parametrize("value", ["0", "-2", "nan", "0.01"])
    def test_a_duration_shorter_than_a_field_is_refused(self, value):
        # Arrange
        parser = flags.build_parser()

        # Act
        code = refusal_code(parser, [FILM, "--duration", value])

        # Assert
        assert code == 2

    def test_a_duration_of_one_field_is_accepted(self):
        # Arrange
        parser = flags.build_parser()

        # Act
        args = parser.parse_args([FILM, "--duration", "0.017"])

        # Assert
        assert args.duration == 0.017


class TestTheWindowInsideTheSource:
    def test_a_start_past_the_end_is_refused_by_name(self):
        # Arrange
        source_seconds = 12.5

        # Act
        with pytest.raises(ValueError) as refused:
            cartridge.window_seconds(start=12.5, duration=None, source_seconds=source_seconds)

        # Assert
        assert str(refused.value) == "--start 12.5 s is past the end of a 12.5 s source"

    def test_without_a_duration_the_rest_of_the_source_is_wanted(self):
        # Arrange
        source_seconds = 12.5

        # Act
        wanted = cartridge.window_seconds(start=2.5, duration=None, source_seconds=source_seconds)

        # Assert
        assert wanted == 10.0

    def test_a_named_duration_is_kept(self):
        # Arrange
        source_seconds = 12.5

        # Act
        wanted = cartridge.window_seconds(start=2.5, duration=4.0, source_seconds=source_seconds)

        # Assert
        assert wanted == 4.0


class TestTheScalerFlag:
    @pytest.mark.parametrize("build", [flags.build_parser, scout.build_parser])
    def test_a_filter_graph_in_place_of_a_scaler_is_refused(self, build):
        # Arrange
        parser = build()

        # Act
        code = refusal_code(parser, [FILM, "--scaler", "area,scale=128:96"])

        # Assert
        assert code == 2

    @pytest.mark.parametrize("build", [flags.build_parser, scout.build_parser])
    def test_a_known_scaler_is_accepted(self, build):
        # Arrange
        parser = build()

        # Act
        args = parser.parse_args([FILM, "--scaler", "lanczos"])

        # Assert
        assert args.scaler == "lanczos"

    def test_the_decoder_refuses_an_unknown_scaler_before_starting_ffmpeg(self):
        # Arrange
        decoding = frames.decode(FILM, width=256, height=192, fps=12.0, scaler="area,crop")

        # Act
        with pytest.raises(ValueError) as refused:
            next(decoding)

        # Assert
        assert str(refused.value).startswith("scaler 'area,crop' is not one of area, bicubic")


class TestTheBudgetFlag:
    def test_a_budget_past_the_measured_field_is_refused(self):
        # Arrange
        parser = flags.build_parser()

        # Act
        code = refusal_code(parser, [FILM, "--budget", "1901"])

        # Assert
        assert code == 2

    def test_the_measured_field_is_accepted(self):
        # Arrange
        parser = flags.build_parser()

        # Act
        args = parser.parse_args([FILM, "--budget", "1900"])

        # Assert
        assert args.budget == 1900


class TestTheSourceCeiling:
    def test_the_frame_ceiling_is_four_hours_of_fields(self):
        # Arrange
        expected = 862_888

        # Act
        ceiling = frames.MAX_FRAMES

        # Assert
        assert ceiling == expected

    def test_the_source_ceiling_is_four_hours(self):
        # Arrange
        hours = 4

        # Act
        seconds = limits.MAX_SOURCE_SECONDS

        # Assert
        assert seconds == hours * 3600


class TestTheSeekEveryFlag:
    @pytest.mark.parametrize("value", ["0", "-10", "nan", "inf", "14401"])
    def test_an_interval_the_film_cannot_use_is_refused(self, value):
        # Arrange
        parser = flags.build_parser()

        # Act
        code = refusal_code(parser, [FILM, "--seek-every", value])

        # Assert
        assert code == 2

    def test_the_refusal_names_the_flag_and_its_range(self, capsys):
        # Arrange
        parser = flags.build_parser()

        # Act
        refusal_code(parser, [FILM, "--seek-every", "0"])

        # Assert
        assert "--seek-every must lie between" in capsys.readouterr().err

    def test_the_longest_film_is_accepted(self):
        # Arrange
        parser = flags.build_parser()

        # Act
        args = parser.parse_args([FILM, "--seek-every", "14400"])

        # Assert
        assert args.seek_every == 14400.0


class TestTheHelp:
    def test_every_flag_explains_itself(self):
        # Arrange
        parser = flags.build_parser()

        # Act
        bare = [action.dest for action in parser._actions if not action.help]

        # Assert
        assert bare == []

    @pytest.mark.parametrize(
        ("flag", "text"),
        [
            ("source", "the video file to put on the cartridge"),
            ("--start", "seconds to skip at the front"),
            ("--duration", "seconds to take; defaults to the whole film"),
            ("--subtitles", "a SubRip .srt file; defaults to one sitting beside the source"),
            ("--denoise", "a strength, or auto to measure it on the film. Default: auto"),
        ],
    )
    def test_a_flag_shared_with_the_neo_geo_baker_reads_the_same(self, flag, text):
        # Arrange
        parser = flags.build_parser()

        # Act
        helps = {
            (action.option_strings or [action.dest])[0]: action.help for action in parser._actions
        }

        # Assert
        assert helps[flag] == text
