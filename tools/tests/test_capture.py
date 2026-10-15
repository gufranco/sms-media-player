from __future__ import annotations

import numpy as np
import pytest
from fmvcore import capture as core

from smsmedia import bake, capture, stream

GEOMETRY = bake.Geometry(columns=32, rows=24, top_row=0)


def picture(level: int) -> np.ndarray:
    return np.full((GEOMETRY.height, GEOMETRY.width, 3), level, dtype=np.uint8)


def gradient(shift: int) -> np.ndarray:
    columns = np.arange(GEOMETRY.width, dtype=np.int32)[None, :, None]
    rows = np.arange(GEOMETRY.height, dtype=np.int32)[:, None, None]
    return ((columns * 3 + rows + shift * 40) % 256).astype(np.uint8).repeat(3, axis=2)


@pytest.fixture(scope="module")
def blob():
    frames = [gradient(shift) for shift in range(4)]
    encoded = bake.encode_frames(frames, geometry=GEOMETRY, budget=400, cap=160)
    paced = [stream.pace(chunks, fields=6) for chunks in encoded.frames]
    packed, _ = stream.pack_banks(paced, bank_size=1 << 14)
    return packed


class TestReplay:
    def test_every_field_is_rendered(self, blob):
        # Arrange
        packed = blob

        # Act
        played = capture.replay_fields(packed)

        # Assert
        assert played.fields.shape[1:] == (GEOMETRY.height, GEOMETRY.width, 3)

    def test_the_completed_frames_are_counted(self, blob):
        # Arrange
        packed = blob

        # Act
        played = capture.replay_fields(packed)

        # Assert
        assert len(played.completes) == 4

    def test_the_padding_after_the_film_is_not_a_field(self, blob):
        # Arrange
        packed = blob

        # Act
        played = capture.replay_fields(packed)

        # Assert
        assert played.fields.shape[0] == played.completes[-1] + 1


class TestAlignment:
    def test_a_recording_of_the_replay_aligns_past_its_boot_fields(self, blob):
        # Arrange
        played = capture.replay_fields(blob)
        boot = np.zeros((3, GEOMETRY.height, GEOMETRY.width, 3), dtype=np.uint8)
        recorded = np.concatenate([boot, played.fields])

        # Act
        found = core.align(recorded, played.fields)

        # Assert
        assert (found.offset, found.mismatches) == (3, 0)


class TestError:
    def test_the_floor_of_a_console_colour_is_zero(self):
        # Arrange
        frame = picture(170)

        # Act
        floor = capture.lattice_floor(frame)

        # Assert
        assert floor == pytest.approx(0.0, abs=1e-6)


class TestEdges:
    def test_a_stream_that_completes_nothing_is_refused(self):
        # Arrange
        unfinished = bytes([stream.END_CHUNK]) * 4

        # Act
        with pytest.raises(ValueError) as refused:
            capture.replay_fields(unfinished)

        # Assert
        assert str(refused.value) == "the stream completes no frame"


class TestFlips:
    def test_a_frame_counts_as_shown_on_the_field_that_flips_to_it(self):
        # Arrange
        frames = [gradient(shift) for shift in range(3)]
        encoded = bake.encode_frames(frames, geometry=GEOMETRY, budget=400, cap=130)
        deferred = stream.defer_closes([stream.pace(chunks, fields=6) for chunks in encoded.frames])
        packed, _ = stream.pack_banks(deferred, bank_size=1 << 14)
        ends = [
            index
            for index, chunk in enumerate(c for f in deferred for c in f)
            if chunk[-1] == stream.END_FRAME
        ]

        # Act
        played = capture.replay_fields(packed)

        # Assert
        assert played.completes == [end + 1 for end in ends[:-1]]
