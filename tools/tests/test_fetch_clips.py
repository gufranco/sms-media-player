from __future__ import annotations

import dataclasses
import http.client
import importlib.util
import sys
import urllib.error
from pathlib import Path

import pytest
from fakes import seeded

from smsmovie import clips

FAKE = seeded()
PRETEND_FILM = FAKE.binary(length=12)
JUNK = FAKE.binary(length=4)
SENT = FAKE.binary(length=10)
OVERLONG = FAKE.binary(length=24)

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "scripts" / "fetch_clips.py"


def load():
    spec = importlib.util.spec_from_file_location("fetch_clips", SCRIPT)
    if spec is None or spec.loader is None:
        msg = f"cannot import {SCRIPT}"
        raise AssertionError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules["fetch_clips"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def fetcher():
    return load()


class TestTheScript:
    def test_it_exists(self):
        # Arrange
        script = SCRIPT

        # Act
        exists = script.is_file()

        # Assert
        assert exists is True

    def test_it_skips_a_committed_clip(self, fetcher, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv(clips.DIRECTORY_ENV, str(tmp_path))
        clip = clips.by_key("synthetic")

        # Act
        outcome = fetcher.acquire(clip, download=_never)

        # Assert
        assert outcome.action == "committed"
        assert outcome.ok is True

    def test_it_skips_a_clip_already_verified(self, fetcher, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv(clips.DIRECTORY_ENV, str(tmp_path))
        clip = clips.by_key("sintel-trailer")
        payload = PRETEND_FILM
        (tmp_path / clip.file).write_bytes(payload)
        pinned = dataclasses.replace(
            clip, bytes=len(payload), sha256=clips.digests(payload)["sha256"]
        )

        # Act
        outcome = fetcher.acquire(pinned, download=_never)

        # Assert
        assert outcome.action == "present"

    def test_it_downloads_a_clip_that_is_absent(self, fetcher, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv(clips.DIRECTORY_ENV, str(tmp_path))
        clip = clips.by_key("sintel-trailer")
        payload = PRETEND_FILM
        pinned = dataclasses.replace(
            clip, bytes=len(payload), sha256=clips.digests(payload)["sha256"]
        )

        # Act
        outcome = fetcher.acquire(
            pinned, download=lambda _url, target, _limit: target.write_bytes(payload)
        )

        # Assert
        assert outcome.action == "fetched"
        assert outcome.ok is True

    def test_a_bad_download_is_refused_and_removed(self, fetcher, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv(clips.DIRECTORY_ENV, str(tmp_path))
        clip = clips.by_key("sintel-trailer")
        pinned = dataclasses.replace(clip, bytes=4, sha256="0" * 64)

        # Act
        outcome = fetcher.acquire(
            pinned, download=lambda _url, target, _limit: target.write_bytes(JUNK)
        )

        # Assert
        assert outcome.ok is False
        assert (tmp_path / clip.file).exists() is False

    def test_a_bad_download_says_what_arrived(self, fetcher, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv(clips.DIRECTORY_ENV, str(tmp_path))
        pinned = dataclasses.replace(clips.by_key("sintel-trailer"), bytes=4, sha256="0" * 64)
        arrived = clips.digests(JUNK)["sha256"]

        # Act
        outcome = fetcher.acquire(
            pinned, download=lambda _url, target, _limit: target.write_bytes(JUNK)
        )

        # Assert
        assert arrived in outcome.diagnosis

    def test_a_stale_copy_is_replaced_rather_than_kept(self, fetcher, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv(clips.DIRECTORY_ENV, str(tmp_path))
        clip = clips.by_key("sintel-trailer")
        (tmp_path / clip.file).write_bytes(b"an older cut")
        payload = PRETEND_FILM
        pinned = dataclasses.replace(
            clip, bytes=len(payload), sha256=clips.digests(payload)["sha256"]
        )

        # Act
        outcome = fetcher.acquire(
            pinned, download=lambda _url, target, _limit: target.write_bytes(payload)
        )

        # Assert
        assert outcome.action == "fetched"
        assert (tmp_path / clip.file).read_bytes() == payload

    def test_a_clip_with_no_url_cannot_be_fetched(self, fetcher, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv(clips.DIRECTORY_ENV, str(tmp_path))
        orphan = dataclasses.replace(clips.by_key("sintel-trailer"), url=None)

        # Act
        outcome = fetcher.acquire(orphan, download=_never)

        # Assert
        assert outcome.ok is False
        assert outcome.diagnosis == "sintel-trailer has no url in the manifest"

    def test_a_committed_clip_that_has_changed_is_refused(self, fetcher):
        # Arrange
        altered = dataclasses.replace(clips.by_key("synthetic"), sha256="0" * 64)

        # Act
        outcome = fetcher.acquire(altered, download=_never)

        # Assert
        assert outcome.ok is False

    def test_a_network_failure_is_reported_and_leaves_nothing(self, fetcher, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv(clips.DIRECTORY_ENV, str(tmp_path))
        clip = clips.by_key("sintel-trailer")

        # Act
        outcome = fetcher.acquire(clip, download=_unreachable, wait=_no_wait)

        # Assert
        assert outcome.action == "failed"
        assert list(tmp_path.iterdir()) == []

    def test_an_oversized_download_is_refused_and_leaves_nothing(
        self, fetcher, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv(clips.DIRECTORY_ENV, str(tmp_path))
        clip = clips.by_key("sintel-trailer")
        oversized = _oversized(fetcher)

        # Act
        outcome = fetcher.acquire(clip, download=oversized, wait=_no_wait)

        # Assert
        assert outcome.action == "failed"
        assert list(tmp_path.iterdir()) == []

    def test_a_rejected_download_leaves_no_partial_file(self, fetcher, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv(clips.DIRECTORY_ENV, str(tmp_path))
        pinned = dataclasses.replace(clips.by_key("sintel-trailer"), bytes=4, sha256="0" * 64)

        # Act
        fetcher.acquire(pinned, download=lambda _url, target, _limit: target.write_bytes(JUNK))

        # Assert
        assert list(tmp_path.iterdir()) == []

    def test_an_unknown_key_is_refused_by_name(self, fetcher, capsys):
        # Arrange
        argv = ["sintel-trailer", "no-such-film"]

        # Act
        code = fetcher.main(argv)

        # Assert
        assert code == 2
        assert "no-such-film" in capsys.readouterr().err


class TestTheDownload:
    def test_it_copies_what_the_server_sends(self, fetcher, tmp_path):
        # Arrange
        source = tmp_path / "source.bin"
        source.write_bytes(SENT)
        target = tmp_path / "copy.bin"

        # Act
        fetcher.download(source.as_uri(), target, 10)

        # Assert
        assert target.read_bytes() == SENT

    def test_it_stops_at_the_size_the_manifest_names(self, fetcher, tmp_path):
        # Arrange
        source = tmp_path / "source.bin"
        source.write_bytes(OVERLONG)
        target = tmp_path / "copy.bin"

        # Act
        with pytest.raises(fetcher.TooLargeError) as refused:
            fetcher.download(source.as_uri(), target, 10)

        # Assert
        assert str(refused.value) == (
            f"{source.as_uri()} sent more than the 10 bytes the manifest names"
        )


def _unreachable(url: str, _target: Path, _limit: int | None) -> None:
    raise urllib.error.URLError(f"cannot reach {url}")


def _oversized(fetcher):
    def write(url: str, target: Path, _limit: int | None) -> None:
        target.write_bytes(b"partial")
        msg = f"{url} sent too much"
        raise fetcher.TooLargeError(msg)

    return write


def _never(_url: str, _target: Path, _limit: int | None) -> None:
    msg = "this case must not download"
    raise AssertionError(msg)


def _no_wait(_seconds: float) -> None:
    return None


class Flaky:
    def __init__(self, error: Exception, *, failures: int) -> None:
        self.error = error
        self.failures = failures
        self.calls = 0

    def __call__(self, _url: str, target: Path, _limit: int | None) -> None:
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error
        target.write_bytes(b"film")


class Waits:
    def __init__(self) -> None:
        self.seen: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.seen = [*self.seen, seconds]


class TestATransientFailure:
    def test_a_reset_connection_is_retried_until_it_lands(self, fetcher, tmp_path):
        # Arrange
        flaky = Flaky(ConnectionResetError("reset by peer"), failures=2)
        target = tmp_path / "film.part"

        # Act
        fetcher.fetch("https://example.invalid/film", target, None, download=flaky, wait=_no_wait)

        # Assert
        assert (flaky.calls, target.read_bytes()) == (3, b"film")

    def test_a_torn_read_on_every_attempt_gives_up_after_three(self, fetcher, tmp_path):
        # Arrange
        flaky = Flaky(http.client.IncompleteRead(b"fi"), failures=9)
        waits = Waits()
        target = tmp_path / "film.part"

        # Act
        with pytest.raises(http.client.IncompleteRead):
            fetcher.fetch("https://example.invalid/film", target, None, download=flaky, wait=waits)

        # Assert
        assert (flaky.calls, waits.seen) == (3, [5.0, 10.0])

    def test_an_oversized_download_is_never_retried(self, fetcher, tmp_path):
        # Arrange
        flaky = Flaky(fetcher.TooLargeError("too big"), failures=9)
        target = tmp_path / "film.part"

        # Act
        with pytest.raises(fetcher.TooLargeError):
            fetcher.fetch(
                "https://example.invalid/film", target, None, download=flaky, wait=_no_wait
            )

        # Assert
        assert flaky.calls == 1


class TestTheCommand:
    def test_a_committed_clip_is_ready_without_a_download(self, fetcher, capsys):
        # Arrange
        argv = ["synthetic"]

        # Act
        code = fetcher.main(argv)

        # Assert
        out = capsys.readouterr().out
        assert code == 0
        assert "1 of 1 clips are ready" in out

    def test_a_stream_that_never_ends_is_stopped(self, fetcher, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setattr(fetcher, "MAX_BLOCKS", 2)
        monkeypatch.setattr(fetcher, "CHUNK", 4)
        source = tmp_path / "source.bin"
        source.write_bytes(bytes(12))

        # Act
        with pytest.raises(fetcher.TooLargeError) as refused:
            fetcher.download(source.as_uri(), tmp_path / "copy.bin", None)

        # Assert
        assert str(refused.value).endswith("sent more than 2 blocks without ending")
