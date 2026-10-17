import pytest
from streamwrites import vram

from smsggmedia import stream


class TestSplitRuns:
    def test_a_short_write_stays_one_run(self):
        # Arrange
        writes = [vram(0x1000, 32)]

        # Act
        result = stream.split_runs(writes)

        # Assert
        assert len(result) == 1
        assert result[0].address == 0x1000

    def test_a_write_longer_than_a_run_is_divided(self):
        # Arrange
        writes = [vram(0x0000, 600)]

        # Act
        result = stream.split_runs(writes)

        # Assert
        assert [len(run.data) for run in result] == [255, 255, 90]

    def test_divided_runs_carry_advancing_addresses(self):
        # Arrange
        writes = [vram(0x0100, 300)]

        # Act
        result = stream.split_runs(writes)

        # Assert
        assert [run.address for run in result] == [0x0100, 0x0100 + 255]

    def test_an_empty_write_produces_nothing(self):
        # Arrange
        writes = [vram(0x0000, 0)]

        # Act
        result = stream.split_runs(writes)

        # Assert
        assert result == []


class TestEncodeChunks:
    def test_a_frame_inside_the_budget_is_one_chunk(self):
        # Arrange
        writes = [vram(0x0000, 100)]

        # Act
        result = stream.encode_chunks(writes, budget=600)

        # Assert
        assert len(result) == 1

    def test_the_last_chunk_reports_the_frame_complete(self):
        # Arrange
        writes = [vram(0x0000, 100)]

        # Act
        result = stream.encode_chunks(writes, budget=600)

        # Assert
        assert result[-1][-1] == stream.END_FRAME

    def test_an_earlier_chunk_reports_the_frame_incomplete(self):
        # Arrange
        writes = [vram(0x0000, 1000)]

        # Act
        result = stream.encode_chunks(writes, budget=300)

        # Assert
        assert result[0][-1] == stream.END_CHUNK
        assert result[-1][-1] == stream.END_FRAME

    def test_no_chunk_exceeds_the_budget(self):
        # Arrange
        writes = [vram(0x0000, 4000)]

        # Act
        result = stream.encode_chunks(writes, budget=400)

        # Assert
        assert max(len(chunk) for chunk in result) <= 400

    def test_every_payload_byte_survives_the_split(self):
        # Arrange
        payload = bytes(range(256)) * 4
        writes = [stream.Write(target=stream.VRAM, address=0, data=payload)]

        # Act
        result = stream.encode_chunks(writes, budget=300)

        # Assert
        assert _payload_of(result) == payload

    def test_a_retired_palette_target_is_refused(self):
        # Arrange
        retired = 0x03

        # Act
        with pytest.raises(ValueError) as refused:
            stream.Write(target=retired, address=0, data=bytes(32))

        # Assert
        assert str(refused.value) == "target 3 is not a destination the player knows"

    def test_a_frame_with_no_writes_still_ends(self):
        # Arrange
        writes: list[stream.Write] = []

        # Act
        result = stream.encode_chunks(writes, budget=600)

        # Assert
        assert result == [bytes([stream.END_FRAME])]

    def test_a_budget_too_small_for_one_run_is_refused(self):
        # Arrange
        writes = [vram(0, 32)]

        # Act
        with pytest.raises(ValueError) as refused:
            stream.encode_chunks(writes, budget=4)

        # Assert
        assert str(refused.value) == "a budget of 4 bytes cannot hold even one run"


class TestPackBanks:
    def test_a_small_movie_fits_one_bank(self):
        # Arrange
        frames = [stream.encode_chunks([vram(0, 32)], budget=600)]

        # Act
        blob, banks = stream.pack_banks(frames, bank_size=1024)

        # Assert
        assert banks == 1
        assert len(blob) == 1024

    def test_a_chunk_never_straddles_a_bank(self):
        # Arrange
        frames = [stream.encode_chunks([vram(0, 200)], budget=600) for _ in range(20)]

        # Act
        blob, banks = stream.pack_banks(frames, bank_size=512)

        # Assert
        assert len(blob) == banks * 512

    def test_the_bank_marker_appears_where_a_bank_ends_early(self):
        # Arrange
        frames = [stream.encode_chunks([vram(0, 200)], budget=600) for _ in range(20)]

        # Act
        blob, banks = stream.pack_banks(frames, bank_size=512)

        # Assert
        assert banks > 1
        assert stream.NEXT_BANK in blob

    def test_a_chunk_larger_than_a_bank_is_refused(self):
        # Arrange
        frames = [stream.encode_chunks([vram(0, 4000)], budget=3000)]

        # Act
        with pytest.raises(ValueError) as refused:
            stream.pack_banks(frames, bank_size=512)

        # Assert
        assert "does not fit a 512-byte bank" in str(refused.value)


def _payload_of(chunks: list[bytes]) -> bytes:
    out = bytearray()
    for chunk in chunks:
        pos = 0
        while pos < len(chunk):
            kind = chunk[pos]
            pos += 1
            if kind in (stream.END_CHUNK, stream.END_FRAME):
                break
            if kind == stream.VRAM:
                length = chunk[pos + 2]
                pos += 3
            else:
                length = chunk[pos + 1]
                pos += 2
            out += chunk[pos : pos + length]
            pos += length
    return bytes(out)


class TestPace:
    def test_a_short_frame_is_padded_to_the_target(self):
        # Arrange
        chunks = stream.encode_chunks([vram(0, 32)], budget=600)

        # Act
        result = stream.pace(chunks, fields=5)

        # Assert
        assert len(result) == 5

    def test_padding_keeps_the_frame_marker_last(self):
        # Arrange
        chunks = stream.encode_chunks([vram(0, 32)], budget=600)

        # Act
        result = stream.pace(chunks, fields=5)

        # Assert
        assert result[-1][-1] == stream.END_FRAME
        assert [c[-1] for c in result[:-1]] == [stream.END_CHUNK] * 4

    def test_a_frame_already_at_the_target_is_unchanged(self):
        # Arrange
        chunks = stream.encode_chunks([vram(0, 900)], budget=300)
        before = len(chunks)

        # Act
        result = stream.pace(chunks, fields=before)

        # Assert
        assert result == chunks

    def test_a_frame_over_the_target_is_left_alone(self):
        # Arrange
        chunks = stream.encode_chunks([vram(0, 2000)], budget=300)
        before = len(chunks)

        # Act
        result = stream.pace(chunks, fields=2)

        # Assert
        assert len(result) == before

    def test_padding_costs_one_byte_a_field(self):
        # Arrange
        chunks = stream.encode_chunks([vram(0, 32)], budget=600)

        # Act
        result = stream.pace(chunks, fields=4)

        # Assert
        assert [len(c) for c in result[:3]] == [1, 1, 1]

    def test_a_target_below_one_is_refused(self):
        # Arrange
        chunks = [bytes([stream.END_FRAME])]

        # Act
        with pytest.raises(ValueError) as refused:
            stream.pace(chunks, fields=0)

        # Assert
        assert str(refused.value) == "a frame must occupy at least one field"


class TestTargets:
    def test_an_unknown_target_is_refused(self):
        # Arrange
        target = 0x77

        # Act
        with pytest.raises(ValueError) as refused:
            stream.Write(target=target, address=0, data=b"")

        # Assert
        assert str(refused.value) == "target 119 is not a destination the player knows"

    def test_the_retired_sound_run_is_refused(self):
        # Arrange
        target = 0x04

        # Act
        with pytest.raises(ValueError) as refused:
            stream.Write(target=target, address=0, data=b"")

        # Assert
        assert str(refused.value) == "target 4 is not a destination the player knows"
