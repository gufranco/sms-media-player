import pytest

from smsmedia import pattern, stream, tablewrites

TILE = bytes(range(pattern.PATTERN_BYTES))


def address_of(cell: int) -> int:
    return 0x3800 + cell * tablewrites.ENTRY_BYTES


class TestMergeUploads:
    def test_consecutive_slots_become_one_run(self):
        # Arrange
        uploads = [(5, TILE), (4, TILE)]

        # Act
        result = tablewrites.merge_uploads(uploads)

        # Assert
        assert [(run.address, len(run.data)) for run in result] == [
            (4 * pattern.PATTERN_BYTES, 2 * pattern.PATTERN_BYTES)
        ]

    def test_a_gap_in_the_slots_starts_a_new_run(self):
        # Arrange
        uploads = [(4, TILE), (6, TILE)]

        # Act
        result = tablewrites.merge_uploads(uploads)

        # Assert
        assert [run.address for run in result] == [
            4 * pattern.PATTERN_BYTES,
            6 * pattern.PATTERN_BYTES,
        ]

    def test_nothing_to_upload_writes_nothing(self):
        # Arrange
        uploads: list[tuple[int, bytes]] = []

        # Act
        result = tablewrites.merge_uploads(uploads)

        # Assert
        assert result == []


class TestMergeEntries:
    def test_neighbouring_entries_become_one_run(self):
        # Arrange
        entries = [(0x3802, 0x0102), (0x3800, 0x0304)]

        # Act
        result = tablewrites.merge_entries(entries)

        # Assert
        assert result == [
            stream.Write(target=stream.VRAM, address=0x3800, data=bytes([4, 3, 2, 1]))
        ]

    def test_distant_entries_stay_apart(self):
        # Arrange
        entries = [(0x3800, 1), (0x3810, 2)]

        # Act
        result = tablewrites.merge_entries(entries)

        # Assert
        assert [run.address for run in result] == [0x3800, 0x3810]

    def test_no_entries_write_nothing(self):
        # Arrange
        entries: list[tuple[int, int]] = []

        # Act
        result = tablewrites.merge_entries(entries)

        # Assert
        assert result == []


class TestFillGaps:
    def test_one_unchanged_cell_between_two_changes_is_rewritten(self):
        # Arrange
        changed = [3, 5]

        # Act
        result = tablewrites.fill_gaps(changed, address_of)

        # Assert
        assert result == [3, 4, 5]

    def test_a_wider_gap_is_left_alone(self):
        # Arrange
        changed = [3, 6]

        # Act
        result = tablewrites.fill_gaps(changed, address_of)

        # Assert
        assert result == [3, 6]

    def test_cells_that_are_not_adjacent_in_vram_are_not_joined(self):
        # Arrange
        changed = [3, 5]

        # Act
        result = tablewrites.fill_gaps(changed, lambda cell: cell * 64)

        # Assert
        assert result == [3, 5]


class TestDuplicateUploads:
    def test_two_uploads_to_one_slot_are_refused(self):
        # Arrange
        uploads = [(5, bytes(32)), (5, bytes(range(32)))]

        # Act
        with pytest.raises(ValueError) as refused:
            tablewrites.merge_uploads(uploads)

        # Assert
        assert str(refused.value) == "two uploads target the same slot among [5, 5]"
