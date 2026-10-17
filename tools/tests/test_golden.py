from dataclasses import dataclass

import numpy as np
import pytest
from fmvcore import colour

from smsggmedia import bake, capture, limits, stream, target

GOLDEN_TOLERANCE = 0.005
GEOMETRY = bake.Geometry(columns=32, rows=24, top_row=0)
SEED = 2026
FRAME_COUNT = 12


@dataclass(frozen=True, slots=True)
class Golden:
    system: target.Target
    geometry: bake.Geometry
    stream_bytes: int
    banks: int
    blurred_error: float


GOLDENS = (
    Golden(target.MASTER_SYSTEM, GEOMETRY, 52041, 4, 0.04276),
    Golden(
        target.GAME_GEAR,
        bake.Geometry(columns=20, rows=18, top_row=3, left_column=6),
        80501,
        6,
        0.02383,
    ),
)


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


def measured(golden: Golden) -> tuple[int, int, int, float]:
    geometry = golden.geometry
    frames = [frame[: geometry.height, : geometry.width] for frame in golden_frames()]
    encoded = bake.encode_frames(
        frames,
        geometry=geometry,
        budget=limits.DEFAULT_BUDGET,
        cap=limits.DEFAULT_CAP,
        system=golden.system,
    )
    fields = stream.defer_closes(encoded.frames)
    blob, banks = stream.pack_banks(fields, bank_size=limits.BANK_BYTES)
    played = capture.replay_fields(blob)
    shown = capture.picture_frames(
        played,
        top=geometry.top_row * 8,
        height=geometry.height,
        width=geometry.width,
        left=geometry.left_column * 8,
    )
    error = colour.blurred_error(shown[: len(frames)], np.stack(frames))
    size = sum(len(chunk) for frame in fields for chunk in frame)
    return size, banks, len(played.completes), error


@pytest.mark.parametrize("golden", GOLDENS, ids=[golden.system.name for golden in GOLDENS])
class TestGoldenStream:
    def test_the_encoder_output_matches_the_blessed_stream(self, golden):
        # Arrange
        expected = (golden.banks, FRAME_COUNT)

        # Act
        size, banks, completed, error = measured(golden)

        # Assert
        assert (banks, completed) == expected
        assert size == pytest.approx(golden.stream_bytes, rel=GOLDEN_TOLERANCE)
        assert error == pytest.approx(golden.blurred_error, rel=GOLDEN_TOLERANCE)
