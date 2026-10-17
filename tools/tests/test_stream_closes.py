import pytest
from streamwrites import vram

from smsggmedia import stream


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

    def test_an_empty_sound_run_is_refused(self):
        # Arrange
        data = b""

        # Act
        with pytest.raises(ValueError) as refused:
            stream.psg_run(data)

        # Assert
        assert str(refused.value) == (
            "a sound run holds at least one write; the player would send 256 for an empty one"
        )
