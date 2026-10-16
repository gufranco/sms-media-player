from __future__ import annotations

import dataclasses
import os
import subprocess

import pytest

from smsmedia import clips


class TestTheManifestIsWellFormed:
    def test_it_loads(self):
        # Arrange
        loader = clips.load

        # Act
        manifest = loader()

        # Assert
        assert len(manifest) > 0

    def test_every_key_is_unique(self):
        # Arrange
        loader = clips.load

        # Act
        manifest = loader()

        # Assert
        keys = [clip.key for clip in manifest]
        assert len(keys) == len(set(keys))

    def test_every_content_class_is_covered(self):
        # Arrange
        expected = {
            "synthetic",
            "3d-animation",
            "hand-drawn-cartoon",
            "live-action",
            "animals",
            "people",
        }

        # Act
        manifest = clips.load()

        # Assert
        covered = {clip.content for clip in manifest}
        assert covered >= expected

    def test_exactly_one_clip_is_committed(self):
        # Arrange
        loader = clips.load

        # Act
        manifest = loader()

        # Assert
        committed = [clip for clip in manifest if clip.committed]
        assert len(committed) == 1

    def test_the_committed_clip_is_on_disk(self):
        # Arrange
        committed = next(clip for clip in clips.load() if clip.committed)

        # Act
        resolved = clips.resolve(committed)

        # Assert
        assert resolved is not None

    def test_every_fetched_clip_names_a_source_and_a_licence(self):
        # Arrange
        loader = clips.load

        # Act
        manifest = loader()

        # Assert
        unnamed = [
            clip.key
            for clip in manifest
            if not clip.committed
            and (
                clip.url is None
                or clip.url == ""
                or clip.source == ""
                or clip.license == ""
                or clip.license_url == ""
            )
        ]
        assert unnamed == []

    def test_every_fetched_clip_carries_an_authoritative_digest(self):
        # Arrange
        loader = clips.load

        # Act
        manifest = loader()

        # Assert
        undigested = [
            clip.key
            for clip in manifest
            if not clip.committed
            and (clip.sha256 is None or len(clip.sha256) != 64 or clip.bytes is None)
        ]
        assert undigested == []

    def test_every_fetched_clip_carries_its_provenance(self):
        # Arrange
        loader = clips.load

        # Act
        manifest = loader()

        # Assert
        unsourced = [
            clip.key
            for clip in manifest
            if not clip.committed and (clip.provenance is None or clip.provenance == "")
        ]
        assert unsourced == []

    @pytest.mark.parametrize("clip", clips.load(), ids=lambda clip: clip.key)
    def test_every_clip_carries_a_measured_budget(self, clip):
        # Arrange
        entry = clip

        # Act
        budget = (entry.max_error, entry.max_banks_per_second)

        # Assert
        assert (budget[0] > 0.0, budget[1] > 0.0) == (True, True)

    @pytest.mark.parametrize("clip", clips.load(), ids=lambda clip: clip.key)
    def test_every_clip_budget_holds_a_whole_opening(self, clip):
        # Arrange
        rate = clip.max_banks_per_second

        # Act
        seconds = clips.BANK_CEILING / rate

        # Assert
        assert seconds >= clips.OPENING_SECONDS

    def test_a_named_clip_can_be_looked_up(self):
        # Arrange
        key = "synthetic"

        # Act
        clip = clips.by_key(key)

        # Assert
        assert clip.content == "synthetic"

    def test_an_unknown_key_is_refused(self):
        # Arrange
        key = "no-such-clip"

        # Act
        with pytest.raises(KeyError) as refused:
            clips.by_key(key)

        # Assert
        assert "no-such-clip is not in the manifest" in str(refused.value)


class TestVerification:
    def test_an_absent_file_says_how_to_get_it(self, tmp_path):
        # Arrange
        clip = dataclasses.replace(clips.by_key("synthetic"), bytes=1, sha256="0" * 64)
        path = tmp_path / "absent.mp4"

        # Act
        verdict = clips.verify(path, clip)

        # Assert
        assert verdict.ok is False
        assert "fetch_clips" in verdict.diagnosis

    def test_every_clip_carries_a_digest_including_the_committed_one(self):
        # Arrange
        loader = clips.load

        # Act
        manifest = loader()

        # Assert
        undigested = [
            clip.key
            for clip in manifest
            if clip.sha256 is None or clip.sha256 == "" or clip.bytes is None or clip.bytes == 0
        ]
        assert undigested == []

    def test_the_committed_clip_matches_its_digest(self):
        # Arrange
        clip = clips.by_key("synthetic")
        path = clips.path_of(clip)

        # Act
        verdict = clips.verify(path, clip)

        # Assert
        assert verdict.ok is True


class TestResolution:
    def test_a_missing_clip_resolves_to_nothing(self, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv(clips.DIRECTORY_ENV, str(tmp_path))
        clip = clips.by_key("sintel-trailer")

        # Act
        resolved = clips.resolve(clip)

        # Assert
        assert resolved is None

    def test_the_directory_can_be_moved(self, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv(clips.DIRECTORY_ENV, str(tmp_path))

        # Act
        result = clips.directory()

        # Assert
        assert result == tmp_path

    def test_the_directory_defaults_inside_the_repository(self, monkeypatch):
        # Arrange
        monkeypatch.delenv(clips.DIRECTORY_ENV, raising=False)

        # Act
        result = clips.directory()

        # Assert
        assert result.name == "clips"

    def test_a_committed_clip_resolves_regardless_of_the_directory(self, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv(clips.DIRECTORY_ENV, str(tmp_path))
        clip = clips.by_key("synthetic")

        # Act
        resolved = clips.resolve(clip)

        # Assert
        assert resolved is not None

    def test_available_reports_what_is_on_this_machine(self):
        # Arrange
        wanted = "synthetic"

        # Act
        available = clips.available()

        # Assert
        assert any(clip.key == wanted for clip, _ in available)


GIT_HOOK_VARIABLES = frozenset({"GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE", "GIT_PREFIX"})


class TestCommittedFilms:
    def test_every_committed_film_is_tracked_by_git(self):
        # Arrange
        committed = [clip for clip in clips.load() if clip.committed]

        # Act
        untracked = [clip.key for clip in committed if not tracked(clips.path_of(clip))]

        # Assert
        assert untracked == []


def tracked(path) -> bool:
    outside_a_hook = {k: v for k, v in os.environ.items() if k not in GIT_HOOK_VARIABLES}
    done = subprocess.run(
        ("git", "-C", str(path.parent), "ls-files", "--error-unmatch", path.name),
        capture_output=True,
        check=False,
        env=outside_a_hook,
    )
    return done.returncode == 0
