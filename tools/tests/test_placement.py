import numpy as np
import pytest

from smsmovie import fidelity, palettes, pattern, placement, workingset


def fresh_fit(frame, **options):
    return palettes.fit_or_keep(frame, None, margin=0.0, **options)


CELL = 8
DISTINCT_TILES = 8
FREE_SLOTS = 3


def fitted_frame(seed: int, *, columns: int = 4, rows: int = 2):
    rng = np.random.default_rng(seed)
    frame = rng.integers(0, 256, (rows * CELL, columns * CELL, 3), dtype=np.uint8)
    fitted = fresh_fit(frame)
    features = fidelity.cell_colours(fitted.indices, fitted, 1.0).reshape(columns * rows, -1)
    return fitted, features


def place(fitted, features, cache, committed_slot, *, cap=64, ceiling=None):
    return placement.place(
        fitted,
        features,
        source=features,
        cache=cache,
        committed_slot=committed_slot,
        cap=cap,
        chroma_weight=1.0,
        reuse_threshold=0.0,
        upload_ceiling=ceiling,
    )


class TestFreeSlots:
    def test_every_allocatable_slot_is_free_when_nothing_is_protected(self):
        # Arrange
        cache = workingset.WorkingSet(capacity=10, reserved=2)
        protected: set[int] = set()

        # Act
        result = placement.free_slots(cache, protected)

        # Assert
        assert result == 8

    def test_a_protected_reserved_slot_does_not_count_twice(self):
        # Arrange
        cache = workingset.WorkingSet(capacity=10, reserved=2)
        protected = {0, 1, 5}

        # Act
        result = placement.free_slots(cache, protected)

        # Assert
        assert result == 7

    def test_no_slot_is_free_when_every_one_is_protected(self):
        # Arrange
        cache = workingset.WorkingSet(capacity=10, reserved=2)
        protected = set(range(10))

        # Act
        result = placement.free_slots(cache, protected)

        # Assert
        assert result == 0


class TestPlace:
    def test_a_frame_that_fits_places_every_cell(self):
        # Arrange
        fitted, features = fitted_frame(3)
        cache = workingset.WorkingSet(capacity=64, reserved=1)
        committed = np.full(8, -1, dtype=np.int64)

        # Act
        result = place(fitted, features, cache, committed)

        # Assert
        assert (int((result.cell_slot == workingset.UNPLACED).sum()), result.collisions) == (0, 0)

    def test_a_frame_short_of_slots_merges_rather_than_dropping(self):
        # Arrange
        fitted, features = fitted_frame(4)
        cache = workingset.WorkingSet(capacity=4, reserved=1)
        committed = np.full(8, -1, dtype=np.int64)

        # Act
        result = place(fitted, features, cache, committed)

        # Assert
        assert (
            int((result.cell_slot == workingset.UNPLACED).sum()),
            len({int(slot) for slot in result.cell_slot}) <= 3,
        ) == (0, True)

    def test_no_free_slot_leaves_fresh_cells_unplaced_and_uploads_nothing(self):
        # Arrange
        fitted, features = fitted_frame(5)
        cache = workingset.WorkingSet(capacity=4, reserved=1)
        committed = np.array([1, 2, 3, 1, 2, 3, 1, 2], dtype=np.int64)

        # Act
        result = place(fitted, features, cache, committed)

        # Assert
        assert (int((result.cell_slot == workingset.UNPLACED).sum()), result.uploads) == (8, [])

    def test_an_upload_never_lands_on_a_slot_still_on_screen(self):
        # Arrange
        fitted, features = fitted_frame(6)
        cache = workingset.WorkingSet(capacity=8, reserved=1)
        on_screen = np.array([1, 2, 1, 2, 1, 2, 1, 2], dtype=np.int64)

        # Act
        result = place(fitted, features, cache, on_screen)

        # Assert
        assert {slot for slot, _ in result.uploads}.isdisjoint({1, 2})


class TestMergedCells:
    def test_a_frame_that_fits_merges_nothing(self):
        # Arrange
        fitted, features = fitted_frame(3)
        cache = workingset.WorkingSet(capacity=64, reserved=1)

        # Act
        result = place(fitted, features, cache, np.full(8, -1, dtype=np.int64))

        # Assert
        assert result.merged == 0

    def test_a_frame_short_of_slots_counts_the_cells_it_merged(self):
        # Arrange
        fitted, features = fitted_frame(4)
        cache = workingset.WorkingSet(capacity=4, reserved=1)

        # Act
        result = place(fitted, features, cache, np.full(8, -1, dtype=np.int64))

        # Assert
        assert result.merged == DISTINCT_TILES - FREE_SLOTS

    def test_no_free_slot_merges_nothing(self):
        # Arrange
        fitted, features = fitted_frame(4)
        cache = workingset.WorkingSet(capacity=4, reserved=1)
        on_screen = np.array([1, 2, 3, 1, 2, 3, 1, 2], dtype=np.int64)

        # Act
        result = place(fitted, features, cache, on_screen)

        # Assert
        assert result.merged == 0


class TestWithinCeiling:
    def test_the_most_demanded_patterns_survive(self):
        # Arrange
        keep = np.arange(3 * CELL * CELL, dtype=np.uint8).reshape(3, CELL, CELL)
        mapping = np.array([0, 2, 2, 2, 1, 2], dtype=np.intp)

        # Act
        result, remapped = placement.within_ceiling(keep, mapping, 1)

        # Assert
        assert (result.shape[0], remapped.tolist()) == (1, [-1, 0, 0, 0, -1, 0])


def views(features: np.ndarray) -> placement.CellViews:
    return placement.CellViews(features, features, features)


def tile(value: int) -> np.ndarray:
    return np.full((CELL, CELL), value, dtype=np.uint8)


class TestMergeByPalette:
    def test_a_merged_cell_only_takes_a_tile_from_its_own_palette(self):
        # Arrange
        tiles = np.stack([tile(1), tile(2), tile(9), tile(10)])
        features = np.stack(
            [np.full(CELL * CELL * 3, level, dtype=np.float32) for level in (0.0, 10.0, 1.0, 11.0)]
        )
        choice = np.array([0, 0, 1, 1], dtype=np.uint8)

        # Act
        keep, mapping = placement.merge_by_palette(tiles, views(features), choice, room=2)

        # Assert
        shown = [int(keep[mapping[cell]][0, 0]) for cell in range(4)]
        assert shown == [1, 1, 9, 9]

    def test_with_room_for_everything_every_cell_keeps_its_own_tile(self):
        # Arrange
        tiles = np.stack([tile(1), tile(2), tile(9)])
        features = np.repeat(tiles.reshape(3, -1), 3, axis=1).astype(np.float32)
        choice = np.array([0, 0, 1], dtype=np.uint8)

        # Act
        keep, mapping = placement.merge_by_palette(tiles, views(features), choice, room=8)

        # Assert
        assert [int(keep[mapping[cell]][0, 0]) for cell in range(3)] == [1, 2, 9]

    def test_one_pattern_used_under_both_palettes_takes_one_slot(self):
        # Arrange
        tiles = np.stack([tile(4), tile(4)])
        features = np.stack([np.zeros(CELL * CELL * 3), np.ones(CELL * CELL * 3)]).astype(
            np.float32
        )
        choice = np.array([0, 1], dtype=np.uint8)

        # Act
        keep, mapping = placement.merge_by_palette(tiles, views(features), choice, room=8)

        # Assert
        assert (keep.shape[0], mapping.tolist()) == (1, [0, 0])


class TestShareRoom:
    @pytest.mark.parametrize(
        ("distinct", "room", "expected"),
        [
            ([150, 10], 100, [93, 7]),
            ([5, 5], 1, [1, 0]),
            ([300, 300], 200, [100, 100]),
            ([2, 50], 200, [2, 50]),
            ([0, 7], 3, [0, 3]),
        ],
    )
    def test_the_room_is_split_by_demand_without_waste(self, distinct, room, expected):
        # Arrange
        demand = list(distinct)

        # Act
        shares = placement.share_room(demand, room)

        # Assert
        assert shares == expected


RED = 0x03
GREEN = 0x09
DARK_GREEN = 0x08


def one_cell(own_index: int) -> palettes.FramePalettes:
    cram = np.zeros(32, dtype=np.uint8)
    cram[1], cram[2], cram[3] = RED, GREEN, DARK_GREEN
    return palettes.FramePalettes(
        cram=cram,
        choice=np.zeros(1, dtype=np.uint8),
        indices=tile(own_index)[None],
        rows=1,
        columns=1,
    )


def resident(*indices: int) -> tuple[workingset.WorkingSet, list[int]]:
    cache = workingset.WorkingSet(capacity=8, reserved=1)
    patterns = pattern.pack_patterns(np.stack([tile(index) for index in indices]))
    allocation = cache.allocate(patterns, referenced=set())
    return cache, [int(slot) for slot in allocation.slots]


class TestBetterStandIns:
    def test_a_stand_in_gives_way_to_a_closer_tile_already_on_screen(self):
        # Arrange
        fitted = one_cell(3)
        features = fidelity.cell_colours(fitted.indices, fitted, 1.0).reshape(1, -1)
        cache, (red, green) = resident(1, 2)

        # Act
        result = placement.better_standins(
            fitted,
            features,
            features,
            cell_slot=np.array([red], dtype=np.int32),
            cache=cache,
            candidates={red, green},
            chroma_weight=1.0,
        )

        # Assert
        assert result.tolist() == [green]

    def test_a_closer_tile_still_too_far_from_the_source_is_not_taken(self):
        # Arrange
        fitted = one_cell(3)
        features = fidelity.cell_colours(fitted.indices, fitted, 1.0).reshape(1, -1)
        far = fidelity.cell_colours(one_cell(1).indices, one_cell(1), 1.0).reshape(1, -1)
        cache, (red, green) = resident(1, 2)

        # Act
        result = placement.better_standins(
            fitted,
            features,
            far + 1.0,
            cell_slot=np.array([red], dtype=np.int32),
            cache=cache,
            candidates={red, green},
            chroma_weight=1.0,
        )

        # Assert
        assert result.tolist() == [red]

    def test_a_stand_in_stays_when_nothing_on_screen_is_closer(self):
        # Arrange
        fitted = one_cell(3)
        features = fidelity.cell_colours(fitted.indices, fitted, 1.0).reshape(1, -1)
        cache, (red,) = resident(1)

        # Act
        result = placement.better_standins(
            fitted,
            features,
            features,
            cell_slot=np.array([red], dtype=np.int32),
            cache=cache,
            candidates={red},
            chroma_weight=1.0,
        )

        # Assert
        assert result.tolist() == [red]

    def test_a_cell_showing_its_own_tile_is_left_alone(self):
        # Arrange
        fitted = one_cell(1)
        features = fidelity.cell_colours(fitted.indices, fitted, 1.0).reshape(1, -1)
        cache, (red, green) = resident(1, 2)

        # Act
        result = placement.better_standins(
            fitted,
            features,
            features,
            cell_slot=np.array([red], dtype=np.int32),
            cache=cache,
            candidates={red, green},
            chroma_weight=1.0,
        )

        # Assert
        assert result.tolist() == [red]


def flat_views(
    perceived: tuple[float, ...], rendered: tuple[float, ...], source: tuple[float, ...]
) -> placement.CellViews:
    def lift(levels: tuple[float, ...]) -> np.ndarray:
        return np.stack([np.full(CELL * CELL * 3, level, dtype=np.float32) for level in levels])

    return placement.CellViews(lift(perceived), lift(rendered), lift(source))


class TestGuardedMerge:
    def test_a_cell_its_stand_in_would_spoil_keeps_its_own_tile(self):
        # Arrange
        tiles = np.stack([tile(1), tile(2), tile(3)])
        cells = flat_views(
            perceived=(0.0, 1.0, 100.0), rendered=(0.0, 0.0, 0.5), source=(0.0, 1.0, 0.1)
        )

        # Act
        keep, mapping = placement.guarded_merge(tiles, cells, cap=2)

        # Assert
        assert [int(keep[mapping[cell]][0, 0]) for cell in range(3)] == [1, 2, 1]

    def test_a_rescue_that_spoils_another_cell_is_not_taken(self):
        # Arrange
        tiles = np.stack([tile(1), tile(2), tile(3)])
        cells = flat_views(
            perceived=(0.0, 1.0, 100.0), rendered=(0.0, 0.0, 0.5), source=(0.0, 1.0, 0.5)
        )

        # Act
        keep, mapping = placement.guarded_merge(tiles, cells, cap=2)

        # Assert
        assert [int(keep[mapping[cell]][0, 0]) for cell in range(3)] == [1, 1, 3]


class TestRebalancingBetweenPalettes:
    def test_a_palette_with_wrong_cells_borrows_a_slot_from_one_that_can_spare_it(self):
        # Arrange
        tiles = np.stack([tile(value) for value in (1, 2, 3, 4, 5, 6, 9, 10)])
        cells = flat_views(
            perceived=(0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.0, 10.0),
            rendered=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0),
            source=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0),
        )
        choice = np.array([0, 0, 0, 0, 0, 0, 1, 1], dtype=np.uint8)

        # Act
        keep, mapping = placement.merge_by_palette(tiles, cells, choice, room=3)

        # Assert
        shown = [int(keep[mapping[cell]][0, 0]) for cell in range(8)]
        assert (len(set(shown[:6])), shown[6:]) == (1, [9, 10])
