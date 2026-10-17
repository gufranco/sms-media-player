from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from smsggmedia import (
    bake,
    cartridge,
    clips,
    console,
    dials,
    flags,
    limits,
    rate,
    replay,
    schedule,
    stream,
    tune,
)


@pytest.fixture(scope="module")
def geometry() -> bake.Geometry:
    return cartridge.geometry_for(limits.DEFAULT_COLUMNS, limits.DEFAULT_ROWS)


def shipping_argv(clip: clips.Clip, path: Path, *, measured: bool = False) -> list[str]:
    window = [str(path), "--start", str(clip.start), "--duration", str(clip.duration)]
    if measured:
        return window
    return [
        *window,
        "--fps",
        str(clip.fps),
        "--denoise",
        str(clip.denoise),
        "--reuse",
        str(clip.reuse),
    ]


def absent(clip: clips.Clip) -> None:
    reason = f"{clip.key} is not on this machine; fetch it with {clips.FETCH_COMMAND}"
    if clips.required():
        pytest.fail(reason)
    pytest.skip(reason)


def baked(clip: clips.Clip, geometry: bake.Geometry):
    path = clips.resolve(clip)
    if path is None:
        absent(clip)

    verdict = clips.verify(path, clip)
    assert verdict.ok, verdict.diagnosis

    args = flags.build_parser().parse_args(shipping_argv(clip, path))
    settled = dials.settle_dials(args, geometry=geometry, wanted=clip.duration)
    baked = cartridge.bake_film(args, geometry=geometry, settled=settled)
    assert baked.decoded, f"{clip.key} decoded to nothing"
    encoded, paced = baked.encoded, baked.fields
    blob, banks = stream.pack_banks(paced, bank_size=limits.BANK_BYTES)
    return (encoded, paced, blob, banks), baked.lags


class Bakes:
    def __init__(self, geometry: bake.Geometry) -> None:
        self.geometry = geometry
        self.done: dict[str, tuple[clips.Clip, tuple]] = {}
        self.lags: dict[str, list[float]] = {}

    def __getitem__(self, key: str) -> tuple[clips.Clip, tuple]:
        if key not in self.done:
            clip = clips.by_key(key)
            outcome, lags = baked(clip, self.geometry)
            self.done = {**self.done, key: (clip, outcome)}
            self.lags = {**self.lags, key: lags}
        return self.done[key]


@pytest.fixture(scope="module")
def bakes(geometry):
    return Bakes(geometry)


def result(bakes, key):
    clip, outcome = bakes[key]
    return clip, outcome


KEYS = [clip.key for clip in clips.load()]


@pytest.mark.parametrize("key", KEYS)
class TestEveryClip:
    def test_the_clip_is_the_one_the_manifest_names(self, bakes, key):
        # Arrange
        clip, _ = result(bakes, key)

        # Act
        path = clips.resolve(clip)

        # Assert
        assert path is not None
        assert clips.verify(path, clip).ok is True

    def test_nothing_is_drawn_outside_the_picture(self, bakes, geometry, key):
        # Arrange
        _, (_, paced, _, _) = result(bakes, key)

        # Act
        worst = worst_outside_picture(paced, geometry)

        # Assert
        assert worst == 0.0

    def test_no_cell_is_left_showing_the_previous_frame(self, bakes, key):
        # Arrange
        _, (encoded, _, _, _) = result(bakes, key)

        # Act
        unplaced = encoded.unplaced

        # Assert
        assert unplaced == 0

    def test_no_pattern_lands_in_a_slot_the_picture_still_uses(self, bakes, key):
        # Arrange
        _, (encoded, _, _, _) = result(bakes, key)

        # Act
        collisions = encoded.collisions

        # Assert
        assert collisions == 0

    def test_the_stream_stays_inside_its_bandwidth_budget(self, bakes, key):
        # Arrange
        clip, (_, _, _, banks) = result(bakes, key)

        # Act
        banks_per_second = banks / clip.duration

        # Assert
        assert banks_per_second <= clip.max_banks_per_second

    def test_a_film_of_useful_length_would_still_fit(self, bakes, key):
        # Arrange
        clip, (_, _, _, banks) = result(bakes, key)

        # Act
        seconds = clips.BANK_CEILING / (banks / clip.duration)

        # Assert
        assert seconds >= 10.0

    def test_the_displayed_error_is_inside_the_clips_budget(self, bakes, key):
        # Arrange
        clip, (encoded, _, _, _) = result(bakes, key)

        # Act
        error = encoded.error

        # Assert
        assert error <= clip.max_error

    def test_the_withheld_pattern_is_never_written(self, bakes, key):
        # Arrange
        _, (_, paced, _, _) = result(bakes, key)

        # Act
        machine = replayed(paced)

        # Assert
        withheld = machine.vram[: console.RESERVED_PATTERNS * console.PATTERN_BYTES]
        assert np.count_nonzero(withheld) == 0

    def test_the_sprite_list_stays_terminated(self, bakes, key):
        # Arrange
        _, (_, paced, _, _) = result(bakes, key)

        # Act
        machine = replayed(paced)

        # Assert
        parked = machine.vram[console.SAT_BASE : console.SAT_BASE + console.SPRITE_SLOTS]
        assert np.all(parked == console.SPRITE_OFF)

    def test_the_picture_is_actually_drawn(self, bakes, geometry, key):
        # Arrange
        _, (_, paced, _, _) = result(bakes, key)

        # Act
        brightest = brightest_frame(paced, geometry)

        # Assert
        assert brightest > 0.2

    def test_no_chunk_outgrows_a_field(self, bakes, key):
        # Arrange
        _, (_, paced, _, _) = result(bakes, key)

        # Act
        largest = max(len(chunk) for chunks in paced for chunk in chunks)

        # Assert
        assert largest <= limits.DEFAULT_BUDGET

    def test_the_picture_keeps_pace_with_the_clock(self, bakes, key):
        # Arrange
        _, (_, paced, _, _) = result(bakes, key)
        lags = bakes.lags[key]
        longest = max(len(chunks) for chunks in paced)
        fps = clips.by_key(key).fps
        rounding = schedule.field_of(1, fps=fps) / 2
        slot = rate.fields_for(fps)

        # Act
        worst = max(lags) * limits.NTSC_FIELD_HZ

        # Assert
        assert worst <= longest - slot + 1 + rounding

    def test_a_frame_in_transfer_changes_nothing_on_screen_until_it_closes(self, bakes, key):
        # Arrange
        _, (_, paced, _, _) = result(bakes, key)
        checked = paced[:FRAMES_CHECKED_FOR_MIXING]

        # Act
        changed_early = changes_before_close(checked)

        # Assert
        assert changed_early == 0


FRAMES_CHECKED_FOR_MIXING = 8


def becomes_visible(chunk: bytes) -> bool:
    pos = 0
    while pos < len(chunk) and chunk[pos] in (stream.VRAM, stream.CLOSE):
        if chunk[pos] == stream.CLOSE:
            return True
        pos += 4 + chunk[pos + 3]
    return False


def replayed(paced: list[list[bytes]]) -> replay.Machine:
    machine = replay.Machine()
    for chunks in paced:
        for chunk in chunks:
            machine.apply(chunk)
    return machine


def worst_outside_picture(paced: list[list[bytes]], geometry: bake.Geometry) -> float:
    machine = replay.Machine()
    worst = 0.0
    for chunks in paced:
        for chunk in chunks:
            machine.apply(chunk)
        worst = max(
            worst,
            replay.lit_fraction(
                replay.framing(
                    machine.display(),
                    rows=geometry.rows,
                    top_row=geometry.top_row,
                    columns=geometry.columns,
                    left_column=geometry.left_column,
                )
            ),
        )
    return worst


def brightest_frame(paced: list[list[bytes]], geometry: bake.Geometry) -> float:
    machine = replay.Machine()
    brightest = 0.0
    for chunks in paced:
        for chunk in chunks:
            machine.apply(chunk)
        brightest = max(
            brightest,
            replay.lit_fraction(
                machine.render(
                    columns=geometry.columns, rows=geometry.rows, top_row=geometry.top_row
                )
            ),
        )
    return brightest


def changes_before_close(paced: list[list[bytes]]) -> int:
    machine = replay.Machine()
    shown = machine.display()
    changed_early = 0
    for chunks in paced:
        naming = False
        for chunk in chunks:
            naming = naming or becomes_visible(chunk)
            completed = machine.apply(chunk)
            if not naming and not completed:
                changed_early += int(not np.array_equal(machine.display(), shown))
        shown = machine.display()
    return changed_early


def error_at(path: Path, clip: clips.Clip, geometry: bake.Geometry, dial: dials.Dials) -> float:
    argv = [
        str(path),
        "--start",
        str(clip.start),
        "--duration",
        str(clip.duration),
        "--fps",
        str(dial.fps),
        "--denoise",
        str(dial.denoise),
        "--reuse",
        str(dial.reuse),
    ]
    args = flags.build_parser().parse_args(argv)
    settled = dials.settle_dials(args, geometry=geometry, wanted=clip.duration)
    return cartridge.bake_film(args, geometry=geometry, settled=settled).encoded.error


def search_against_record(
    clip: clips.Clip, path: Path, geometry: bake.Geometry
) -> tuple[dials.Dials, float, float]:
    args = flags.build_parser().parse_args(shipping_argv(clip, path, measured=True))
    found = dials.settle_dials(args, geometry=geometry, wanted=clip.duration)
    recorded = dials.Dials(fps=clip.fps, denoise=clip.denoise, reuse=clip.reuse)
    if found == recorded:
        return found, 0.0, 0.0
    return found, error_at(path, clip, geometry, recorded), error_at(path, clip, geometry, found)


@pytest.mark.slow
@pytest.mark.parametrize("key", KEYS)
def test_the_recorded_dials_are_still_as_good_as_what_the_search_finds(geometry, key):
    # Arrange
    clip = clips.by_key(key)
    path = clips.resolve(clip)
    if path is None:
        absent(clip)

    # Act
    found, recorded_error, found_error = search_against_record(clip, path, geometry)

    # Assert
    assert found.fps == clip.fps
    assert recorded_error <= found_error * (1.0 + tune.SCORE_TIE)


class TestTheSetItself:
    def test_the_committed_clip_always_runs(self):
        # Arrange
        clip = clips.by_key("synthetic")

        # Act
        resolved = clips.resolve(clip)

        # Assert
        assert resolved is not None

    def test_every_manifest_clip_is_present_when_required(self):
        # Arrange
        if not clips.required():
            pytest.skip("set SMSGGMEDIA_CLIPS_REQUIRED=1 to demand the whole set")
        manifest = clips.load()

        # Act
        missing = [clip.key for clip in manifest if clips.resolve(clip) is None]

        # Assert
        assert missing == []

    def test_more_than_one_kind_of_content_is_covered(self):
        # Arrange
        if not clips.required():
            pytest.skip("set SMSGGMEDIA_CLIPS_REQUIRED=1 to demand the whole set")
        minimum = 2

        # Act
        available = clips.available()

        # Assert
        present = {clip.content for clip, _ in available}
        assert len(present) >= minimum
