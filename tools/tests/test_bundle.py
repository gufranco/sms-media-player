from __future__ import annotations

import pytest
from fmvcore.testing import seeded

from smsmedia import bundle

FAKE = seeded()


def figures(*, sound: bool = True) -> bundle.Figures:
    return bundle.Figures(
        seconds=12.34, frames=96, fields=740, banks=5, columns=32, rows=24, keys=2, sound=sound
    )


@pytest.fixture
def film(tmp_path):
    assets, generated = tmp_path / "assets", tmp_path / "generated"
    assets.mkdir()
    generated.mkdir()
    payload = FAKE.binary(length=64)
    (assets / "movie.bin").write_bytes(payload)
    (generated / "movie.h").write_text("#define MOVIE_BANKS 5u\n")
    return assets, generated, payload


class TestWrite:
    def test_the_library_headers_film_and_fragment_are_all_copied(self, tmp_path, film):
        # Arrange
        assets, generated, _ = film
        target = tmp_path / "bundle"

        # Act
        bundle.write(target=target, assets=assets, generated=generated, figures=figures())

        # Assert
        copied = sorted(
            str(path.relative_to(target)) for path in target.rglob("*") if path.is_file()
        )
        assert copied == sorted(
            [
                *(f"src/{name}" for name in bundle.LIBRARY_SOURCES),
                *(f"include/fmv/{name}" for name in bundle.LIBRARY_HEADERS),
                "movie/movie.h",
                "movie/assets/movie.bin",
                "fmv.mk",
                "README.md",
            ]
        )

    def test_the_film_is_copied_byte_for_byte(self, tmp_path, film):
        # Arrange
        assets, generated, payload = film
        target = tmp_path / "bundle"

        # Act
        bundle.write(target=target, assets=assets, generated=generated, figures=figures())

        # Assert
        assert (target / "movie" / "assets" / "movie.bin").read_bytes() == payload

    def test_the_guide_states_the_films_figures(self, tmp_path, film):
        # Arrange
        assets, generated, _ = film

        # Act
        guide = bundle.write(
            target=tmp_path / "bundle",
            assets=assets,
            generated=generated,
            figures=figures(sound=False),
        )

        # Assert
        text = guide.read_text()
        assert (
            "12.3 seconds, 96 frames over 740 fields, 5 banks of 16 KB, "
            "a picture of 32 by 24 cells, 2 seek points, sound off" in text
        )

    def test_a_missing_film_is_refused(self, tmp_path, film):
        # Arrange
        assets, generated, _ = film
        (assets / "movie.bin").unlink()

        # Act
        with pytest.raises(FileNotFoundError) as refused:
            bundle.write(
                target=tmp_path / "bundle", assets=assets, generated=generated, figures=figures()
            )

        # Assert
        assert str(refused.value) == f"the bundle needs movie.bin, which is not in {assets}"


class TestVersion:
    def test_the_version_comes_from_the_player_header(self):
        # Arrange
        header = bundle.VERSION_HEADER.read_text()

        # Act
        found = bundle.version()

        # Assert
        assert f'#define FMV_VERSION "{found}"' in header

    def test_a_header_without_a_version_is_refused(self, tmp_path):
        # Arrange
        header = tmp_path / "version.h"
        header.write_text("#define NOTHING 1\n")

        # Act
        with pytest.raises(ValueError) as refused:
            bundle.version(header)

        # Assert
        assert str(refused.value) == f"{header} does not define FMV_VERSION"
