from __future__ import annotations

import itertools

import numpy as np
import pytest
from fmvcore.testing import SEED

from smsmedia import bake, cartridge, output, replay, schedule, stream

GEOMETRY = bake.Geometry(columns=8, rows=6, top_row=0)
FPS = 10.0
SLOT = 6
FRAMES = 24
EVERY = 0.8
BANK = 1 << 10


def film() -> list[np.ndarray]:
    rng = np.random.default_rng(SEED)
    rows, columns = np.mgrid[0 : GEOMETRY.height, 0 : GEOMETRY.width]
    frames = []
    for index in range(FRAMES):
        base = np.stack(
            [(columns * 5 + index * 9) % 256, (rows * 7 + index * 4) % 256, (columns + rows) % 256],
            axis=-1,
        )
        frames.append(np.clip(base + rng.integers(-20, 21, base.shape), 0, 255).astype(np.uint8))
    return frames


def baked(every: float) -> tuple[schedule.Schedule, list[list[bytes]]]:
    encoder = bake.Encoder(geometry=GEOMETRY, budget=900, cap=12)
    timed = schedule.by_clock(
        film(), fps=FPS, slot=SLOT, encoder=encoder, pace=False, keyframe_every=every
    )
    return timed, stream.defer_closes(timed.frames)


def displays(chunks: list[bytes]) -> list[np.ndarray]:
    machine = replay.Machine()
    shown = []
    for chunk in chunks:
        machine.apply(chunk)
        shown.append(machine.display().copy())
    return shown


@pytest.fixture(scope="module")
def keyed():
    timed, fields = baked(EVERY)
    packed = stream.pack_frames(fields, bank_size=BANK)
    return timed, fields, packed, replay.frames_of(packed.blob, bank_size=BANK)


class TestKeyframes:
    def test_the_first_frame_and_then_one_per_interval_are_keyframes(self, keyed):
        # Arrange
        timed, _, _, _ = keyed

        # Act
        gaps = [
            round((timed.picks[later] - timed.picks[earlier]) / FPS, 3)
            for earlier, later in itertools.pairwise(timed.keys)
        ]

        # Assert
        assert (timed.keys[0], gaps) == (0, [0.8, 0.8])

    def test_no_interval_makes_no_keyframes(self):
        # Arrange
        every = 0.0

        # Act
        timed, _ = baked(every)

        # Assert
        assert timed.keys == []

    @pytest.mark.parametrize("key", [1, 2])
    def test_playing_on_from_a_seek_point_draws_what_continuous_play_draws(self, keyed, key):
        # Arrange
        timed, fields, _, chunks = keyed
        index = timed.keys[key]
        start = sum(len(frame) for frame in fields[:index])
        settled = start + len(fields[index])
        continuous = displays(chunks)

        # Act
        sought = displays(chunks[start:])

        # Assert
        assert all(
            np.array_equal(sought[at - start], continuous[at]) for at in range(settled, len(chunks))
        )

    def test_without_keyframes_a_seek_would_draw_something_else(self):
        # Arrange
        _, fields = baked(0.0)
        chunks = replay.frames_of(stream.pack_frames(fields, bank_size=BANK).blob, bank_size=BANK)
        start = sum(len(frame) for frame in fields[:8])
        continuous = displays(chunks)

        # Act
        sought = displays(chunks[start:])

        # Assert
        assert any(
            not np.array_equal(sought[at - start], continuous[at])
            for at in range(start, len(chunks))
        )


class TestSeekPoints:
    def test_each_point_names_where_its_frame_starts(self, keyed):
        # Arrange
        timed, fields, packed, _ = keyed
        result = cartridge.Baked(
            encoded=bake.Encoded(),
            fields=fields,
            decoded=FRAMES,
            lags=[0.0],
            lead=0,
            unshown_tail=0,
            dither=0.0,
            sources=[],
            keys=tuple(timed.keys),
        )

        # Act
        points = cartridge.seek_points(result, packed)

        # Assert
        assert [(p.bank, p.offset, p.frame) for p in points] == [
            (*packed.starts[index], index) for index in timed.keys
        ]

    def test_the_field_of_a_point_counts_every_chunk_before_it(self, keyed):
        # Arrange
        timed, fields, packed, _ = keyed
        result = cartridge.Baked(
            encoded=bake.Encoded(),
            fields=fields,
            decoded=FRAMES,
            lags=[0.0],
            lead=0,
            unshown_tail=0,
            dither=0.0,
            sources=[],
            keys=tuple(timed.keys),
        )

        # Act
        points = cartridge.seek_points(result, packed)

        # Assert
        assert points[0].field == 0
        assert points[1].field == sum(len(frame) for frame in fields[: timed.keys[1]])


class TestPackFrames:
    def test_a_frame_that_spills_starts_in_the_next_bank(self):
        # Arrange
        frames = [[bytes(700) + b"\x01"], [bytes(400) + b"\x01"]]

        # Act
        packed = stream.pack_frames(frames, bank_size=BANK)

        # Assert
        assert packed.starts == ((0, 0), (1, 0))

    def test_frames_sharing_a_bank_start_where_the_last_ended(self):
        # Arrange
        frames = [[bytes(100) + b"\x01"], [bytes(50) + b"\x01"]]

        # Act
        packed = stream.pack_frames(frames, bank_size=BANK)

        # Assert
        assert packed.starts == ((0, 0), (0, 101))


class TestHeader:
    def test_the_header_lists_every_seek_point(self, tmp_path):
        # Arrange
        path = tmp_path / "movie.h"
        keys = (output.Key(0, 0, 0, 0), output.Key(2, 0x123, 40, 300))

        # Act
        output.write_header(
            path,
            banks=3,
            frame_count=80,
            field_count=600,
            hold_fields=6,
            first_bank_symbol="b",
            keys=keys,
        )

        # Assert
        text = path.read_text()
        assert "#define MOVIE_KEYS 2u" in text
        assert "{b + 2u, 0x0123u, 40u, 300ul}" in text

    def test_a_film_with_no_seek_point_is_refused(self, tmp_path):
        # Arrange
        path = tmp_path / "movie.h"

        # Act
        with pytest.raises(ValueError) as refused:
            output.write_header(
                path,
                banks=1,
                frame_count=1,
                field_count=1,
                hold_fields=6,
                first_bank_symbol="b",
                keys=(),
            )

        # Assert
        assert str(refused.value) == "a film needs at least one seek point, its first frame"

    def test_more_seek_points_than_one_byte_indexes_are_refused(self, tmp_path):
        # Arrange
        keys = tuple(output.Key(0, 0, n, n) for n in range(output.MAX_KEYS + 1))

        # Act
        with pytest.raises(ValueError) as refused:
            output.write_header(
                tmp_path / "movie.h",
                banks=1,
                frame_count=300,
                field_count=300,
                hold_fields=6,
                first_bank_symbol="b",
                keys=keys,
            )

        # Assert
        assert (
            str(refused.value)
            == "the player indexes seek points in one byte, so 255 is more than 254"
        )

    def test_a_seek_point_past_the_frame_counter_is_refused(self, tmp_path):
        # Arrange
        keys = (output.Key(0, 0, 0, 0), output.Key(0, 0, 70000, 1))

        # Act
        with pytest.raises(ValueError) as refused:
            output.write_header(
                tmp_path / "movie.h",
                banks=1,
                frame_count=1,
                field_count=1,
                hold_fields=6,
                first_bank_symbol="b",
                keys=keys,
            )

        # Assert
        assert str(refused.value) == (
            "the player counts frames in 16 bits, so no seek point can pass 65535"
        )
