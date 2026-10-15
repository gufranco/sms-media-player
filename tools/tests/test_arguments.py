from __future__ import annotations

import argparse

import pytest

from smsmovie import arguments


class TestFinite:
    def test_a_value_inside_the_range_is_returned(self):
        # Arrange
        text = "2.5"

        # Act
        result = arguments.finite(text, low=0.0, high=4.0, name="--x")

        # Assert
        assert result == 2.5

    def test_text_that_is_not_a_number_is_refused_by_name(self):
        # Arrange
        text = "fast"

        # Act
        with pytest.raises(argparse.ArgumentTypeError) as refused:
            arguments.finite(text, low=0.0, high=4.0, name="--x")

        # Assert
        assert str(refused.value) == "--x must be a number, got 'fast'"

    def test_nan_is_refused(self):
        # Arrange
        text = "nan"

        # Act
        with pytest.raises(argparse.ArgumentTypeError) as refused:
            arguments.finite(text, low=0.0, high=4.0, name="--x")

        # Assert
        assert str(refused.value) == "--x must lie between 0 and 4, got nan"

    def test_a_value_outside_the_range_is_refused(self):
        # Arrange
        text = "-1"

        # Act
        with pytest.raises(argparse.ArgumentTypeError) as refused:
            arguments.finite(text, low=0.0, high=4.0, name="--x")

        # Assert
        assert str(refused.value) == "--x must lie between 0 and 4, got -1"


class TestWhole:
    def test_a_value_inside_the_range_is_returned(self):
        # Arrange
        text = "7"

        # Act
        result = arguments.whole(text, low=1, high=10, name="--n")

        # Assert
        assert result == 7

    def test_a_fraction_is_refused(self):
        # Arrange
        text = "7.5"

        # Act
        with pytest.raises(argparse.ArgumentTypeError) as refused:
            arguments.whole(text, low=1, high=10, name="--n")

        # Assert
        assert str(refused.value) == "--n must be a whole number, got '7.5'"

    def test_a_value_outside_the_range_is_refused(self):
        # Arrange
        text = "0"

        # Act
        with pytest.raises(argparse.ArgumentTypeError) as refused:
            arguments.whole(text, low=1, high=10, name="--n")

        # Assert
        assert str(refused.value) == "--n must lie between 1 and 10, got 0"


class TestTypes:
    def test_number_checks_its_range(self):
        # Arrange
        check = arguments.number(low=0.0, high=1.0, name="--r")

        # Act
        result = check("0.5")

        # Assert
        assert result == 0.5

    def test_count_checks_its_range(self):
        # Arrange
        check = arguments.count(low=1, high=3, name="--c")

        # Act
        result = check("3")

        # Assert
        assert result == 3

    def test_auto_passes_through(self):
        # Arrange
        check = arguments.number_or_auto(low=0.0, high=1.0, name="--r")

        # Act
        result = check(arguments.AUTO)

        # Assert
        assert result == arguments.AUTO

    def test_a_number_is_checked_and_kept_as_given(self):
        # Arrange
        check = arguments.number_or_auto(low=0.0, high=1.0, name="--r")

        # Act
        result = check("0.25")

        # Assert
        assert result == "0.25"

    def test_a_number_out_of_range_is_refused_even_beside_auto(self):
        # Arrange
        check = arguments.number_or_auto(low=0.0, high=1.0, name="--r")

        # Act
        with pytest.raises(argparse.ArgumentTypeError) as refused:
            check("2")

        # Assert
        assert str(refused.value) == "--r must lie between 0 and 1, got 2"
