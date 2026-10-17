import numpy as np
import pytest
from fmvcore import colour

from smsggmedia import bake, capture, limits, stream

GOLDEN_STREAM_BYTES = 51303
GOLDEN_BANKS = 4
GOLDEN_BLURRED_ERROR = 0.04230
GOLDEN_TOLERANCE = 0.005
GEOMETRY = bake.Geometry(columns=32, rows=24, top_row=0)
SEED = 2026
FRAME_COUNT = 12


def golden_frames() -> list[np.ndarray]:
    rng = np.random.default_rng(SEED)
    rows, columns = np.mgrid[0 : GEOMETRY.height, 0 : GEOMETRY.width]
    frames = []
    for index in range(FRAME_COUNT):
        frame = np.zeros((GEOMETRY.height, GEOMETRY.width, 3), dtype=np.int16)
        frame[..., 0] = (columns + 6 * index) % 256
        frame[..., 1] = (rows * 2 + 3 * index) % 256
        frame[..., 2] = ((columns + rows) // 2) % 256
        frame[40:100, 30 + 8 * index : 90 + 8 * index] = (230, 40, 40)
        frame = frame + rng.integers(-5, 6, frame.shape)
        frames.append(np.clip(frame, 0, 255).astype(np.uint8))
    return frames


def baked_fields(frames: list[np.ndarray]) -> list[list[bytes]]:
    encoded = bake.encode_frames(
        frames, geometry=GEOMETRY, budget=limits.DEFAULT_BUDGET, cap=limits.DEFAULT_CAP
    )
    return stream.defer_closes(encoded.frames)


def measured(frames: list[np.ndarray]) -> tuple[int, int, int, float]:
    fields = baked_fields(frames)
    blob, banks = stream.pack_banks(fields, bank_size=limits.BANK_BYTES)
    played = capture.replay_fields(blob)
    shown = capture.picture_frames(played, top=0, height=GEOMETRY.height, width=GEOMETRY.width)
    error = colour.blurred_error(shown[: len(frames)], np.stack(frames))
    size = sum(len(chunk) for frame in fields for chunk in frame)
    return size, banks, len(played.completes), error


class TestGoldenStream:
    def test_the_encoder_output_matches_the_blessed_stream(self):
        # Arrange
        frames = golden_frames()

        # Act
        size, banks, completed, error = measured(frames)

        # Assert
        assert (banks, completed) == (GOLDEN_BANKS, FRAME_COUNT)
        assert size == pytest.approx(GOLDEN_STREAM_BYTES, rel=GOLDEN_TOLERANCE)
        assert error == pytest.approx(GOLDEN_BLURRED_ERROR, rel=GOLDEN_TOLERANCE)
