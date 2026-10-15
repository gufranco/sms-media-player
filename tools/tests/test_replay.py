import numpy as np
import pytest

from smsmedia import console, pattern, replay, stream


def vram_write(addr, data):
    return stream.Write(target=stream.VRAM, address=addr, data=data)


class TestMachine:
    def test_vram_starts_as_the_player_leaves_it(self):
        # Arrange
        expected = console.boot_vram()

        # Act
        m = replay.Machine()

        # Assert
        assert np.array_equal(m.vram, expected) is True

    def test_no_pattern_slot_holds_anything_at_boot(self):
        # Arrange
        reserved_end = console.BACK_TABLE_BASE

        # Act
        m = replay.Machine()

        # Assert
        assert int(np.count_nonzero(m.vram[:reserved_end])) == 0

    def test_a_vram_run_lands_at_its_address(self):
        # Arrange
        m = replay.Machine()
        chunk = stream.encode_chunks([vram_write(0x100, bytes([1, 2, 3]))], budget=600)[0]

        # Act
        m.apply(chunk)

        # Assert
        assert m.vram[0x100:0x103].tolist() == [1, 2, 3]

    def test_an_unknown_kind_is_refused_by_name(self):
        # Arrange
        m = replay.Machine()
        chunk = bytes([0x04, 2, 5, 5, stream.END_FRAME])

        # Act
        with pytest.raises(ValueError) as refused:
            m.apply(chunk)

        # Assert
        assert str(refused.value) == "run kind 0x04 at offset 0 is not one the player knows"

    def test_a_refused_chunk_writes_nothing(self):
        # Arrange
        m = replay.Machine()
        chunk = bytes([0x04, 2, 5, 5, stream.END_FRAME])

        # Act
        with pytest.raises(ValueError) as refused:
            m.apply(chunk)

        # Assert
        assert str(refused.value) == "run kind 0x04 at offset 0 is not one the player knows"
        assert np.array_equal(m.vram, console.boot_vram()) is True

    def test_cutting_a_stream_with_an_unknown_kind_is_refused(self):
        # Arrange
        blob = bytes([0x04, 1, 2, stream.END_FRAME])

        # Act
        with pytest.raises(ValueError) as refused:
            replay.frames_of(blob)

        # Assert
        assert str(refused.value) == "run kind 0x04 at offset 0 is not one the player knows"

    def test_a_frame_terminator_is_reported(self):
        # Arrange
        m = replay.Machine()
        chunk = stream.encode_chunks([vram_write(0, bytes(4))], budget=600)[0]

        # Act
        done = m.apply(chunk)

        # Assert
        assert done is True

    def test_a_chunk_terminator_is_not_a_frame(self):
        # Arrange
        m = replay.Machine()
        chunks = stream.encode_chunks([vram_write(0, bytes(900))], budget=300)

        # Act
        done = m.apply(chunks[0])

        # Assert
        assert done is False

    def test_writes_wrap_at_the_end_of_vram(self):
        # Arrange
        m = replay.Machine()
        chunk = bytes([stream.VRAM, 0xFF, 0x3F, 2, 7, 8, stream.END_FRAME])

        # Act
        m.apply(chunk)

        # Assert
        assert m.vram[0x3FFF] == 7
        assert m.vram[0] == 8


class TestRender:
    def test_it_produces_the_picture_geometry(self):
        # Arrange
        m = replay.Machine()

        # Act
        out = m.render(columns=32, rows=18, top_row=3)

        # Assert
        assert out.shape == (144, 256, 3)

    def test_a_blank_machine_renders_the_first_colour(self):
        # Arrange
        m = replay.Machine()

        # Act
        out = m.render(columns=4, rows=2, top_row=0)

        # Assert
        assert out.max() == 0

    def test_a_set_palette_entry_shows_through(self):
        # Arrange
        m = replay.Machine()
        m.cram[15] = 0x3F
        m.vram[0x3800] = 0x01
        m.vram[0x3801] = 0x00
        m.vram[32:64] = 0xFF

        # Act
        out = m.render(columns=1, rows=1, top_row=0)

        # Assert
        assert out.reshape(-1, 3).tolist() == [[255, 255, 255]] * 64

    def test_a_row_beyond_the_table_is_refused(self):
        # Arrange
        m = replay.Machine()

        # Act
        with pytest.raises(ValueError) as refused:
            m.render(columns=32, rows=30, top_row=0)

        # Assert
        assert str(refused.value) == "a 32x30 picture at row 0 does not fit the name table"


def asymmetric_tile():
    cell = np.zeros((pattern.TILE_PX, pattern.TILE_PX), dtype=np.uint8)
    cell[:, : pattern.TILE_PX // 2] = 1
    cell[: pattern.TILE_PX // 2, :] += 2
    return pattern.pack_patterns(cell[None, ...])[0]


def machine_showing(entry: int) -> replay.Machine:
    m = replay.Machine()
    m.cram[:4] = [0x00, 0x03, 0x0C, 0x30]
    m.vram[0:32] = asymmetric_tile()
    m.vram[0x3800] = entry & 0xFF
    m.vram[0x3801] = (entry >> 8) & 0xFF
    return m


class TestRenderFlips:
    def test_an_unflipped_cell_keeps_its_left_edge(self):
        # Arrange
        m = machine_showing(0)

        # Act
        plain = m.render(columns=1, rows=1, top_row=0)

        # Assert
        assert np.array_equal(plain[0, 0], plain[0, 7]) is False

    def test_the_horizontal_flip_mirrors_the_columns(self):
        # Arrange
        plain = machine_showing(0).render(columns=1, rows=1, top_row=0)
        m = machine_showing(pattern.HFLIP_BIT)

        # Act
        flipped = m.render(columns=1, rows=1, top_row=0)

        # Assert
        assert np.array_equal(flipped, plain[:, ::-1]) is True

    def test_the_vertical_flip_mirrors_the_rows(self):
        # Arrange
        plain = machine_showing(0).render(columns=1, rows=1, top_row=0)
        m = machine_showing(pattern.VFLIP_BIT)

        # Act
        flipped = m.render(columns=1, rows=1, top_row=0)

        # Assert
        assert np.array_equal(flipped, plain[::-1, :]) is True

    def test_both_flips_together_rotate_the_cell(self):
        # Arrange
        plain = machine_showing(0).render(columns=1, rows=1, top_row=0)
        m = machine_showing(pattern.HFLIP_BIT | pattern.VFLIP_BIT)

        # Act
        both = m.render(columns=1, rows=1, top_row=0)

        # Assert
        assert np.array_equal(both, plain[::-1, ::-1]) is True


def carried(chunks: list[bytes]) -> list[bytes]:
    return [chunk for chunk in chunks if chunk != bytes([stream.END_CHUNK])]


class TestFramesOf:
    def test_it_cuts_a_frame_out_of_a_packed_stream(self):
        # Arrange
        frame = stream.encode_chunks([vram_write(0, bytes([1, 2, 3]))], budget=600)
        blob, _ = stream.pack_banks([frame], bank_size=1 << 14)

        # Act
        recovered = replay.frames_of(blob, bank_size=1 << 14)

        # Assert
        assert carried(recovered) == carried(frame)

    def test_a_frame_spanning_several_chunks_comes_back_whole(self):
        # Arrange
        frame = stream.encode_chunks([vram_write(0, bytes(900))], budget=300)
        blob, _ = stream.pack_banks([frame], bank_size=1 << 14)

        # Act
        recovered = replay.frames_of(blob, bank_size=1 << 14)

        # Assert
        assert carried(recovered) == carried(frame)

    def test_a_bank_marker_skips_to_the_next_bank(self):
        # Arrange
        small = 64
        frames = [stream.encode_chunks([vram_write(0, bytes(40))], budget=60) for _ in range(3)]
        blob, banks = stream.pack_banks(frames, bank_size=small)

        # Act
        recovered = replay.frames_of(blob, bank_size=small)

        # Assert
        assert banks >= 2
        assert carried(recovered) == carried([c for f in frames for c in f])

    def test_replaying_what_it_returns_reaches_the_same_vram(self):
        # Arrange
        frame = stream.encode_chunks([vram_write(0x40, bytes([9, 8, 7, 6]))], budget=600)
        blob, _ = stream.pack_banks([frame], bank_size=1 << 14)
        m = replay.Machine()

        # Act
        for chunk in replay.frames_of(blob, bank_size=1 << 14):
            m.apply(chunk)

        # Assert
        assert list(m.vram[0x40:0x44]) == [9, 8, 7, 6]

    def test_an_empty_stream_yields_no_chunks(self):
        # Arrange
        blob = b""

        # Act
        chunks = replay.frames_of(blob, bank_size=1 << 14)

        # Assert
        assert chunks == []
