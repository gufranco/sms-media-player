from __future__ import annotations

import numpy as np
import pytest

from smsmovie import bake, capture, stream

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
    def test_a_capture_that_matches_from_an_offset_is_found(self, blob):
        # Arrange
        played = capture.replay_fields(blob)
        boot = np.zeros((3, GEOMETRY.height, GEOMETRY.width, 3), dtype=np.uint8)
        recorded = np.concatenate([boot, played.fields])

        # Act
        found = capture.align(recorded, played.fields)

        # Assert
        assert (found.offset, found.mismatches) == (3, 0)

    def test_a_capture_that_never_matches_reports_every_sample(self, blob):
        # Arrange
        played = capture.replay_fields(blob)
        recorded = np.full_like(played.fields, 7)

        # Act
        found = capture.align(recorded, played.fields)

        # Assert
        assert found.mismatches == found.sampled


class TestMixing:
    def test_a_clean_transfer_mixes_nothing(self):
        # Arrange
        before, after = picture(10), picture(200)
        fields = np.stack([before, before, after])

        # Act
        share = capture.mixed_share(fields, completes=[0, 2])

        # Assert
        assert share == 0.0

    def test_a_field_matching_neither_frame_is_counted(self):
        # Arrange
        before, after, wrong = picture(10), picture(200), picture(90)
        fields = np.stack([before, wrong, after])

        # Act
        share = capture.mixed_share(fields, completes=[0, 2])

        # Assert
        assert share == 1.0


class TestError:
    def test_the_floor_of_a_console_colour_is_zero(self):
        # Arrange
        frame = picture(170)

        # Act
        floor = capture.lattice_floor(frame)

        # Assert
        assert floor == pytest.approx(0.0, abs=1e-6)


class TestLag:
    def test_a_frame_shown_on_time_has_no_lag(self):
        # Arrange
        source = np.stack([gradient(shift) for shift in range(10)])
        shown = source.copy()

        # Act
        lags = capture.measured_lags(shown, source, completes=[2, 5, 8], window=4)

        # Assert
        assert lags == [0, 0, 0]

    def test_a_frame_shown_late_reports_how_late(self):
        # Arrange
        source = np.stack([gradient(shift) for shift in range(10)])
        shown = np.roll(source, 2, axis=0)

        # Act
        lags = capture.measured_lags(shown, source, completes=[4, 6, 8], window=4)

        # Assert
        assert lags == [2, 2, 2]


class TestEdges:
    def test_a_stream_that_completes_nothing_is_refused(self):
        # Arrange
        unfinished = bytes([stream.END_CHUNK]) * 4

        # Act
        with pytest.raises(ValueError) as refused:
            capture.replay_fields(unfinished)

        # Assert
        assert str(refused.value) == "the stream completes no frame"

    def test_a_capture_shorter_than_the_stream_stops_the_search(self, blob):
        # Arrange
        played = capture.replay_fields(blob)
        recorded = played.fields[:2]

        # Act
        found = capture.align(recorded, played.fields)

        # Assert
        assert found.mismatches == found.sampled

    def test_a_completion_past_the_capture_is_not_measured(self):
        # Arrange
        source = np.stack([gradient(shift) for shift in range(6)])

        # Act
        lags = capture.measured_lags(source, source, completes=[2, 9], window=2)

        # Assert
        assert lags == [0]


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
