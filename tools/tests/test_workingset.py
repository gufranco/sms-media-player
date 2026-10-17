import numpy as np
import pytest

from smsggmedia import workingset


def patterns(values: list[int]) -> np.ndarray:
    return np.array([[v] * 32 for v in values], dtype=np.uint8)


class TestAllocate:
    def test_the_first_frame_fills_from_the_bottom(self):
        # Arrange
        cache = workingset.WorkingSet(capacity=8)

        # Act
        result = cache.allocate(patterns([1, 2, 3]), referenced=set())

        # Assert
        assert result.slots.tolist() == [0, 1, 2]

    def test_a_pattern_already_resident_is_not_uploaded_again(self):
        # Arrange
        cache = workingset.WorkingSet(capacity=8)
        cache.allocate(patterns([1, 2, 3]), referenced=set())

        # Act
        result = cache.allocate(patterns([2, 3]), referenced=set())

        # Assert
        assert result.uploads == []
        assert result.slots.tolist() == [1, 2]

    def test_a_new_pattern_avoids_a_referenced_slot(self):
        # Arrange
        cache = workingset.WorkingSet(capacity=3)
        cache.allocate(patterns([1, 2, 3]), referenced=set())

        # Act
        result = cache.allocate(patterns([9]), referenced={0, 2})

        # Assert
        assert result.slots.tolist() == [1]

    def test_a_referenced_slot_is_never_overwritten(self):
        # Arrange
        cache = workingset.WorkingSet(capacity=3)
        cache.allocate(patterns([1, 2, 3]), referenced=set())

        # Act
        result = cache.allocate(patterns([7, 8]), referenced={0, 1, 2})

        # Assert
        assert result.slots.tolist() == [workingset.UNPLACED] * 2
        assert result.uploads == []

    def test_a_pattern_that_finds_no_slot_reports_unplaced(self):
        # Arrange
        cache = workingset.WorkingSet(capacity=2)
        cache.allocate(patterns([1, 2]), referenced=set())

        # Act
        result = cache.allocate(patterns([5, 6, 7]), referenced={0})

        # Assert
        assert (result.slots == workingset.UNPLACED).sum() == 2

    def test_uploads_carry_the_bytes_for_each_new_slot(self):
        # Arrange
        cache = workingset.WorkingSet(capacity=8)

        # Act
        result = cache.allocate(patterns([4]), referenced=set())

        # Assert
        assert result.uploads == [(0, bytes([4] * 32))]

    def test_consecutive_new_patterns_take_consecutive_slots(self):
        # Arrange
        cache = workingset.WorkingSet(capacity=8)

        # Act
        result = cache.allocate(patterns([1, 2, 3, 4]), referenced=set())

        # Assert
        assert result.slots.tolist() == [0, 1, 2, 3]

    def test_capacity_is_never_exceeded(self):
        # Arrange
        cache = workingset.WorkingSet(capacity=4)

        # Act
        result = cache.allocate(patterns(list(range(1, 10))), referenced=set())

        # Assert
        placed = [s for s in result.slots.tolist() if s != workingset.UNPLACED]
        assert len(placed) == 4
        assert max(placed) < 4

    def test_a_zero_capacity_set_is_refused(self):
        # Arrange
        capacity = 0

        # Act
        with pytest.raises(ValueError) as refused:
            workingset.WorkingSet(capacity=capacity)

        # Assert
        assert str(refused.value) == "a working set needs a capacity of at least one slot"

    def test_patterns_of_the_wrong_width_are_refused(self):
        # Arrange
        cache = workingset.WorkingSet(capacity=4)
        narrow = np.zeros((2, 16), dtype=np.uint8)

        # Act
        with pytest.raises(ValueError) as refused:
            cache.allocate(narrow, referenced=set())

        # Assert
        assert str(refused.value) == "patterns must be rows of 32 bytes, got (2, 16)"


class TestMergeToCap:
    def test_a_set_inside_the_cap_is_untouched(self):
        # Arrange
        tiles = np.zeros((3, 8, 8), dtype=np.uint8)
        tiles[1] = 7
        tiles[2] = 12

        # Act
        keep, mapping = workingset.merge_to_cap(tiles, cap=8)

        # Assert
        assert keep.shape[0] == 3
        assert sorted(mapping.tolist()) == [0, 1, 2]

    def test_a_set_above_the_cap_is_reduced_to_it(self):
        # Arrange
        rng = np.random.default_rng(3)
        tiles = rng.integers(0, 16, size=(40, 8, 8), dtype=np.uint8)

        # Act
        keep, mapping = workingset.merge_to_cap(tiles, cap=10)

        # Assert
        assert keep.shape[0] == 10
        assert int(mapping.max()) < 10

    def test_every_tile_still_maps_somewhere(self):
        # Arrange
        rng = np.random.default_rng(4)
        tiles = rng.integers(0, 16, size=(40, 8, 8), dtype=np.uint8)

        # Act
        _, mapping = workingset.merge_to_cap(tiles, cap=10)

        # Assert
        assert mapping.shape == (40,)
        assert int(mapping.min()) >= 0

    def test_identical_tiles_share_a_representative(self):
        # Arrange
        tiles = np.zeros((6, 8, 8), dtype=np.uint8)
        tiles[3:] = 5

        # Act
        _, mapping = workingset.merge_to_cap(tiles, cap=4)

        # Assert
        assert mapping[0] == mapping[1] == mapping[2]
        assert mapping[3] == mapping[4] == mapping[5]

    def test_a_cap_below_one_is_refused(self):
        # Arrange
        tiles = np.zeros((2, 8, 8), dtype=np.uint8)

        # Act
        with pytest.raises(ValueError) as refused:
            workingset.merge_to_cap(tiles, cap=0)

        # Assert
        assert str(refused.value) == "a cap of at least one tile is required"


class TestResidents:
    def test_an_empty_set_has_no_residents(self):
        # Arrange
        cache = workingset.WorkingSet(capacity=4)

        # Act
        slots, data = cache.residents()

        # Assert
        assert slots.size == 0
        assert data.shape == (0, workingset.PATTERN_BYTES)

    def test_it_reports_what_was_placed(self):
        # Arrange
        cache = workingset.WorkingSet(capacity=4)
        cache.allocate(patterns([1, 2]), referenced=set())

        # Act
        slots, data = cache.residents()

        # Assert
        assert slots.tolist() == [0, 1]
        assert data[0].tolist() == [1] * 32

    def test_an_evicted_pattern_stops_being_resident(self):
        # Arrange
        cache = workingset.WorkingSet(capacity=1)
        cache.allocate(patterns([1]), referenced=set())
        cache.allocate(patterns([2]), referenced=set())

        # Act
        _, data = cache.residents()

        # Assert
        assert data.shape[0] == 1
        assert data[0].tolist() == [2] * 32


class TestMatchResidents:
    def test_an_exact_match_is_found(self):
        # Arrange
        cells = np.zeros((2, 4), dtype=np.float64)
        residents = np.zeros((3, 4), dtype=np.float64)
        residents[1] = 5.0

        # Act
        result = workingset.match_residents(cells, residents, threshold=0.1)

        # Assert
        assert result.tolist() == [0, 0]

    def test_a_flat_resident_cannot_stand_for_a_textured_cell(self):
        # Arrange
        cells = np.array([[0.20, 0.0, 0.0, 0.24, 0.0, 0.0]], dtype=np.float32)
        residents = np.array([[0.22, 0.0, 0.0, 0.22, 0.0, 0.0]], dtype=np.float32)

        # Act
        result = workingset.match_residents(cells, residents, threshold=0.1, contrast=0.5)

        # Assert
        assert result.tolist() == [workingset.UNPLACED]

    def test_without_the_guard_the_flat_resident_stands_in(self):
        # Arrange
        cells = np.array([[0.20, 0.0, 0.0, 0.24, 0.0, 0.0]], dtype=np.float32)
        residents = np.array([[0.22, 0.0, 0.0, 0.22, 0.0, 0.0]], dtype=np.float32)

        # Act
        result = workingset.match_residents(cells, residents, threshold=0.1)

        # Assert
        assert result.tolist() == [0]

    def test_a_resident_keeping_the_texture_still_stands_in(self):
        # Arrange
        cells = np.array([[0.20, 0.0, 0.0, 0.24, 0.0, 0.0]], dtype=np.float32)
        residents = np.array([[0.21, 0.0, 0.0, 0.24, 0.0, 0.0]], dtype=np.float32)

        # Act
        result = workingset.match_residents(cells, residents, threshold=0.1, contrast=0.5)

        # Assert
        assert result.tolist() == [0]

    def test_a_distant_cell_matches_nothing(self):
        # Arrange
        cells = np.full((1, 4), 9.0, dtype=np.float64)
        residents = np.zeros((2, 4), dtype=np.float64)

        # Act
        result = workingset.match_residents(cells, residents, threshold=0.1)

        # Assert
        assert result.tolist() == [workingset.UNPLACED]

    def test_the_nearest_resident_wins(self):
        # Arrange
        cells = np.full((1, 2), 1.0, dtype=np.float64)
        residents = np.array([[0.0, 0.0], [1.1, 1.1]], dtype=np.float64)

        # Act
        result = workingset.match_residents(cells, residents, threshold=1.0)

        # Assert
        assert result.tolist() == [1]

    def test_no_residents_matches_nothing(self):
        # Arrange
        cells = np.zeros((3, 4), dtype=np.float64)
        residents = np.zeros((0, 4), dtype=np.float64)

        # Act
        result = workingset.match_residents(cells, residents, threshold=1.0)

        # Assert
        assert result.tolist() == [workingset.UNPLACED] * 3

    def test_a_negative_threshold_is_refused(self):
        # Arrange
        cells = np.zeros((1, 2))
        residents = np.zeros((1, 2))

        # Act
        with pytest.raises(ValueError) as refused:
            workingset.match_residents(cells, residents, threshold=-1.0)

        # Assert
        assert str(refused.value) == "a reuse threshold must not be negative"


class TestBookkeeping:
    def test_a_fresh_set_holds_nothing(self):
        # Arrange
        cache = workingset.WorkingSet(capacity=8)

        # Act
        result = cache.resident()

        # Assert
        assert result == 0

    def test_it_reports_how_many_slots_are_taken(self):
        # Arrange
        cache = workingset.WorkingSet(capacity=8)
        cache.allocate(
            np.zeros((2, 32), dtype=np.uint8) + np.arange(2, dtype=np.uint8)[:, None],
            referenced=set(),
        )

        # Act
        result = cache.resident()

        # Assert
        assert result == 2

    def test_merging_a_non_batch_is_refused(self):
        # Arrange
        tiles = np.zeros((8, 8), dtype=np.uint8)

        # Act
        with pytest.raises(ValueError) as refused:
            workingset.merge_to_cap(tiles, cap=2)

        # Assert
        assert str(refused.value) == "tiles must be a batch of 2-D cells, got shape (8, 8)"


class TestReservation:
    def test_a_reservation_larger_than_the_set_is_refused(self):
        # Arrange
        reserved = 4

        # Act
        with pytest.raises(ValueError) as refused:
            workingset.WorkingSet(capacity=4, reserved=reserved)

        # Assert
        assert str(refused.value) == "reserving 4 of 4 slots leaves nothing to allocate"

    def test_a_negative_reservation_is_refused(self):
        # Arrange
        reserved = -1

        # Act
        with pytest.raises(ValueError) as refused:
            workingset.WorkingSet(capacity=4, reserved=reserved)

        # Assert
        assert str(refused.value) == "a reservation cannot be negative"

    def test_no_reservation_is_the_default(self):
        # Arrange
        capacity = 4

        # Act
        result = workingset.WorkingSet(capacity=capacity)

        # Assert
        assert result.reserved == 0

    def test_no_pattern_lands_in_a_reserved_slot(self):
        # Arrange
        cache = workingset.WorkingSet(capacity=8, reserved=2)

        # Act
        result = cache.allocate(patterns([1, 2, 3, 4]), referenced=set())

        # Assert
        assert result.slots.tolist() == [2, 3, 4, 5]

    def test_a_reserved_slot_never_holds_a_resident(self):
        # Arrange
        cache = workingset.WorkingSet(capacity=8, reserved=3)
        cache.allocate(patterns([1, 2]), referenced=set())

        # Act
        slots, _ = cache.residents()

        # Assert
        assert int(slots.min()) >= 3

    def test_the_reservation_shrinks_what_can_be_placed(self):
        # Arrange
        cache = workingset.WorkingSet(capacity=4, reserved=3)

        # Act
        result = cache.allocate(patterns([1, 2, 3]), referenced=set())

        # Assert
        assert result.slots.tolist() == [3, workingset.UNPLACED, workingset.UNPLACED]

    def test_a_reserved_slot_is_not_freed_by_an_empty_reference_set(self):
        # Arrange
        cache = workingset.WorkingSet(capacity=4, reserved=1)
        cache.allocate(patterns([1, 2, 3]), referenced=set())

        # Act
        result = cache.allocate(patterns([9]), referenced=set())

        # Assert
        assert int(result.slots[0]) != 0


class TestAFrameNeverEvictsItsOwnPattern:
    def test_a_pattern_this_frame_reuses_keeps_its_slot(self):
        # Arrange
        cache = workingset.WorkingSet(capacity=3)
        kept = np.full((1, workingset.PATTERN_BYTES), 7, dtype=np.uint8)
        cache.allocate(kept, referenced=set())
        fresh = np.full((1, workingset.PATTERN_BYTES), 9, dtype=np.uint8)

        # Act
        result = cache.allocate(np.concatenate([kept, fresh]), referenced=set())

        # Assert
        assert result.slots.tolist() == [0, 1]
        assert result.uploads == [(1, fresh.tobytes())]
