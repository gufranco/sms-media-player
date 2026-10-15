from __future__ import annotations

import pytest

from smsmedia import output


class TestNearestRank:
    def test_it_returns_a_member_of_the_values(self):
        # Arrange
        values = [5, 1, 9, 3, 7, 2, 8, 4, 6, 10, 11]

        # Act
        result = output.nearest_rank(values, 0.9)

        # Assert
        assert result == 10

    def test_a_single_value_is_its_own_percentile(self):
        # Arrange
        values = [4]

        # Act
        result = output.nearest_rank(values, 0.9)

        # Assert
        assert result == 4

    def test_no_values_is_refused(self):
        # Arrange
        values: list[int] = []

        # Act
        with pytest.raises(ValueError) as refused:
            output.nearest_rank(values, 0.9)

        # Assert
        assert str(refused.value) == "a percentile needs at least one value"


class TestPublish:
    def test_it_writes_the_film(self, tmp_path):
        # Arrange
        assets = tmp_path / "a"
        generated = tmp_path / "g"

        # Act
        output.publish(
            assets=assets,
            generated=generated,
            blob=b"film",
            banks=1,
            frame_count=2,
            hold_fields=6,
        )

        # Assert
        assert (assets / output.FILM).read_bytes() == b"film"

    def test_it_writes_the_header(self, tmp_path):
        # Arrange
        assets = tmp_path / "a"
        generated = tmp_path / "g"

        # Act
        output.publish(
            assets=assets,
            generated=generated,
            blob=b"film",
            banks=3,
            frame_count=2,
            hold_fields=6,
        )

        # Assert
        assert "#define MOVIE_BANKS 3u" in (generated / output.HEADER).read_text()

    def test_the_header_says_how_long_to_hold_the_last_frame(self, tmp_path):
        # Arrange
        assets = tmp_path / "a"
        generated = tmp_path / "g"

        # Act
        output.publish(
            assets=assets,
            generated=generated,
            blob=b"film",
            banks=1,
            frame_count=2,
            hold_fields=10,
        )

        # Assert
        assert "#define MOVIE_HOLD_FIELDS 10u" in (generated / output.HEADER).read_text()

    def test_it_leaves_no_staged_file_behind(self, tmp_path):
        # Arrange
        assets = tmp_path / "a"
        generated = tmp_path / "g"

        # Act
        output.publish(
            assets=assets,
            generated=generated,
            blob=b"film",
            banks=1,
            frame_count=2,
            hold_fields=6,
        )

        # Assert
        left = [path.name for path in tmp_path.rglob("*") if path.name.endswith(output.STAGED)]
        assert left == []


class TestAnInterruptedPublish:
    def test_the_old_film_is_gone_before_the_new_header_lands(self, tmp_path, monkeypatch):
        # Arrange
        assets = tmp_path / "a"
        generated = tmp_path / "g"
        output.publish(
            assets=assets, generated=generated, blob=b"old", banks=1, frame_count=1, hold_fields=6
        )
        real_replace = output.Path.replace

        def killed_before_the_film(self, target):
            if self.name == output.FILM + output.STAGED:
                raise KeyboardInterrupt
            return real_replace(self, target)

        monkeypatch.setattr(output.Path, "replace", killed_before_the_film)

        # Act
        with pytest.raises(KeyboardInterrupt):
            output.publish(
                assets=assets,
                generated=generated,
                blob=b"new",
                banks=2,
                frame_count=9,
                hold_fields=6,
            )

        # Assert
        assert (assets / output.FILM).exists() is False
        assert "#define MOVIE_BANKS 2u" in (generated / output.HEADER).read_text()


class TestClear:
    def test_it_removes_staged_leftovers(self, tmp_path):
        # Arrange
        assets = tmp_path / "a"
        generated = tmp_path / "g"
        assets.mkdir()
        generated.mkdir()
        (assets / (output.FILM + output.STAGED)).write_bytes(b"torn")
        (generated / (output.HEADER + output.STAGED)).write_text("torn")

        # Act
        output.clear(assets=assets, generated=generated)

        # Assert
        assert sorted(path.name for path in tmp_path.rglob("*")) == ["a", "g"]

    def test_it_removes_a_previous_film(self, tmp_path):
        # Arrange
        assets = tmp_path / "a"
        generated = tmp_path / "g"
        output.publish(
            assets=assets,
            generated=generated,
            blob=b"old",
            banks=1,
            frame_count=1,
            hold_fields=6,
        )

        # Act
        output.clear(assets=assets, generated=generated)

        # Assert
        assert (assets / output.FILM).exists() is False
        assert (generated / output.HEADER).exists() is False

    def test_nothing_to_clear_is_not_an_error(self, tmp_path):
        # Arrange
        assets = tmp_path / "a"
        generated = tmp_path / "g"

        # Act
        output.clear(assets=assets, generated=generated)

        # Assert
        assert list(tmp_path.iterdir()) == []


class TestHoldLimits:
    def test_a_hold_past_one_byte_is_written_whole(self, tmp_path):
        # Arrange
        path = tmp_path / "movie.h"

        # Act
        output.write_header(path, banks=1, frame_count=2, hold_fields=599, first_bank_symbol="bank")

        # Assert
        assert "#define MOVIE_HOLD_FIELDS 599u\n" in path.read_text()

    @pytest.mark.parametrize("fields", [0, 0x10000])
    def test_a_hold_the_player_cannot_count_is_refused(self, tmp_path, fields):
        # Arrange
        path = tmp_path / "movie.h"

        # Act
        with pytest.raises(ValueError) as refused:
            output.write_header(
                path, banks=1, frame_count=2, hold_fields=fields, first_bank_symbol="bank"
            )

        # Assert
        assert str(refused.value) == (
            f"the player counts the hold in 16 bits, so {fields} fields cannot be held"
        )
