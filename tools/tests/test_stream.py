import pytest

from smsggmedia import stream


def vram(addr: int, length: int) -> stream.Write:
    return stream.Write(target=stream.VRAM, address=addr, data=bytes(length))


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


def closing(register: int = 0xFD) -> stream.Write:
    return stream.Write(target=stream.CLOSE, address=register, data=bytes(stream.CLOSE_BYTES))


class TestDeferCloses:
    def test_a_closing_run_moves_to_the_start_of_the_next_field(self):
        # Arrange
        first = stream.encode_chunks([closing()], budget=600)
        second = stream.encode_chunks([stream.Write(stream.VRAM, 0, bytes(4))], budget=600)

        # Act
        result = stream.defer_closes([first, second])

        # Assert
        assert result[1][0][0] == stream.CLOSE

    def test_the_field_it_left_keeps_its_end_marker(self):
        # Arrange
        first = stream.encode_chunks([closing()], budget=600)
        second = stream.encode_chunks([stream.Write(stream.VRAM, 0, bytes(4))], budget=600)

        # Act
        result = stream.defer_closes([first, second])

        # Assert
        assert result[0] == [bytes([stream.END_FRAME])]

    def test_the_last_frame_gets_a_field_for_its_closing_run(self):
        # Arrange
        only = stream.encode_chunks([closing()], budget=600)

        # Act
        result = stream.defer_closes([only])

        # Assert
        assert result[-1] == [bytes([stream.CLOSE, 0xFD]) + bytes(32) + bytes([stream.END_FRAME])]

    def test_a_stream_without_closing_runs_is_unchanged(self):
        # Arrange
        frames = [stream.encode_chunks([stream.Write(stream.VRAM, 0, bytes(9))], budget=600)]

        # Act
        result = stream.defer_closes(frames)

        # Assert
        assert result == frames

    def test_runs_before_the_closing_run_stay_in_their_field(self):
        # Arrange
        first = stream.encode_chunks(
            [stream.Write(stream.VRAM, 0x20, bytes([7, 7])), closing()], budget=600
        )

        # Act
        result = stream.defer_closes([first])

        # Assert
        assert result[0][0] == bytes([stream.VRAM, 0x20, 0x00, 2, 7, 7, stream.END_FRAME])


def wide_closing(register: int = 0xFD) -> stream.Write:
    return stream.Write(
        target=stream.CLOSE_WIDE, address=register, data=bytes(stream.WIDE_CLOSE_BYTES)
    )


class TestTheWideCloseRun:
    def test_it_carries_two_cram_bytes_an_entry(self):
        # Arrange
        kind = stream.CLOSE_WIDE

        # Act
        size = stream.close_bytes(kind)

        # Assert
        assert size == 64

    def test_it_is_emitted_under_its_own_kind(self):
        # Arrange
        run = wide_closing()

        # Act
        chunks = stream.encode_chunks([run], budget=600)

        # Assert
        assert chunks == [bytes([0x07, 0xFD]) + bytes(64) + bytes([stream.END_FRAME])]

    def test_it_moves_whole_to_the_next_field(self):
        # Arrange
        first = stream.encode_chunks([wide_closing()], budget=600)
        second = stream.encode_chunks([stream.Write(stream.VRAM, 0, bytes(4))], budget=600)

        # Act
        result = stream.defer_closes([first, second])

        # Assert
        assert result[1][0][: 2 + 64] == bytes([0x07, 0xFD]) + bytes(64)

    def test_a_sound_run_follows_it_rather_than_splitting_it(self):
        # Arrange
        close = bytes([stream.CLOSE_WIDE, 0xFD]) + bytes(64)
        fields = [[close + bytes([stream.END_FRAME])]]

        # Act
        sounded = stream.add_sound(fields, [b"\x9f"])

        # Assert
        assert sounded[0][0] == close + bytes([stream.PSG, 1, 0x9F, stream.END_FRAME])


class TestThePanRun:
    def test_a_pan_is_its_kind_and_one_byte(self):
        # Arrange
        value = 0xFE

        # Act
        run = stream.pan_run(value)

        # Assert
        assert run == bytes([0x08, 0xFE])

    def test_a_pan_past_one_byte_is_refused(self):
        # Arrange
        value = 0x100

        # Act
        with pytest.raises(ValueError) as refused:
            stream.pan_run(value)

        # Assert
        assert str(refused.value) == "a pan is one byte, got 256"

    def test_a_pan_comes_before_the_tones_of_its_field(self):
        # Arrange
        fields = [[bytes([stream.END_FRAME])]]

        # Act
        sounded = stream.add_sound(fields, [b"\x9f"], [0xEF])

        # Assert
        assert sounded[0][0] == bytes([0x08, 0xEF, stream.PSG, 1, 0x9F, stream.END_FRAME])

    def test_a_field_with_a_pan_and_no_tones_carries_the_pan_alone(self):
        # Arrange
        fields = [[bytes([stream.END_FRAME])]]

        # Act
        sounded = stream.add_sound(fields, [b""], [0xFF])

        # Assert
        assert sounded[0][0] == bytes([0x08, 0xFF, stream.END_FRAME])

    def test_no_pans_leaves_a_master_system_stream_as_it_was(self):
        # Arrange
        fields = [[bytes([stream.END_FRAME])]]

        # Act
        sounded = stream.add_sound(fields, [b"\x9f"])

        # Assert
        assert sounded[0][0] == bytes([stream.PSG, 1, 0x9F, stream.END_FRAME])


class TestTheReserve:
    def test_only_the_first_chunk_keeps_room_for_a_closing_run(self):
        # Arrange
        writes = [stream.Write(stream.VRAM, 0x100 * index, bytes(40)) for index in range(6)]

        # Act
        chunks = stream.encode_chunks(writes, budget=100, reserve=40)

        # Assert
        assert len(chunks[0]) <= 100 - 40
        assert max(len(chunk) for chunk in chunks[1:]) > 100 - 40

    def test_no_reserve_packs_the_first_chunk_full(self):
        # Arrange
        writes = [stream.Write(stream.VRAM, 0x100 * index, bytes(40)) for index in range(6)]

        # Act
        chunks = stream.encode_chunks(writes, budget=100)

        # Assert
        assert len(chunks[0]) > 100 - 40


class TestTheBoundsOfAWrite:
    def test_a_run_past_the_end_of_vram_is_refused(self):
        # Arrange
        address = 0x3FF0

        # Act
        with pytest.raises(ValueError) as refused:
            stream.Write(target=stream.VRAM, address=address, data=bytes(17))

        # Assert
        assert str(refused.value) == "a run at 0x3ff0 of 17 bytes passes 0x4000"

    def test_a_run_ending_on_the_last_vram_byte_is_accepted(self):
        # Arrange
        address = 0x3FF0

        # Act
        write = stream.Write(target=stream.VRAM, address=address, data=bytes(16))

        # Assert
        assert write.address + len(write.data) == 0x4000

    def test_a_table_register_past_one_byte_is_refused(self):
        # Arrange
        register = 0x100

        # Act
        with pytest.raises(ValueError) as refused:
            stream.Write(target=stream.CLOSE, address=register, data=bytes(32))

        # Assert
        assert str(refused.value) == "a run at 0x0100 of 32 bytes passes 0x0100"


class TestARunInsideItsBudget:
    @pytest.mark.parametrize(("budget", "reserve"), [(68, 34), (68, 0), (300, 34), (1800, 34)])
    def test_no_chunk_passes_the_budget(self, budget, reserve):
        # Arrange
        writes = [vram(0, 600)]

        # Act
        chunks = stream.encode_chunks(writes, budget=budget, reserve=reserve)

        # Assert
        assert max(len(chunk) for chunk in chunks[1:] or [b""]) <= budget
        assert len(chunks[0]) <= budget - reserve

    def test_a_closing_run_is_never_split(self):
        # Arrange
        writes = [stream.Write(target=stream.CLOSE, address=0xFF, data=bytes(32))]

        # Act
        chunks = stream.encode_chunks(writes, budget=68)

        # Assert
        assert chunks == [bytes([stream.CLOSE, 0xFF]) + bytes(32) + bytes([stream.END_FRAME])]


class TestRefusedInputs:
    def test_a_negative_address_is_refused(self):
        # Arrange
        address = -1

        # Act
        with pytest.raises(ValueError) as refused:
            stream.Write(stream.VRAM, address, b"\x00")

        # Assert
        assert str(refused.value) == "address -1 is negative"

    @pytest.mark.parametrize("length", [0, stream.MAX_RUN + 1])
    def test_a_run_length_outside_one_byte_is_refused(self, length):
        # Arrange
        writes = [vram(0, 4)]

        # Act
        with pytest.raises(ValueError) as refused:
            stream.split_runs(writes, max_run=length)

        # Assert
        assert str(refused.value) == f"a run length must lie in 1 to {stream.MAX_RUN}"

    def test_a_bank_too_small_for_a_chunk_and_a_marker_is_refused(self):
        # Arrange
        frames = [[bytes([stream.END_FRAME])]]

        # Act
        with pytest.raises(ValueError) as refused:
            stream.pack_frames(frames, bank_size=1)

        # Assert
        assert str(refused.value) == "a bank must hold at least a chunk and a marker"

    def test_a_sound_run_past_one_length_byte_is_refused(self):
        # Arrange
        data = bytes(stream.MAX_RUN + 1)

        # Act
        with pytest.raises(ValueError) as refused:
            stream.psg_run(data)

        # Assert
        assert str(refused.value) == f"a sound run holds at most {stream.MAX_RUN} writes, got 256"
