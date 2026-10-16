from __future__ import annotations

from smsmedia import stepdown

Rung = stepdown.Rung


def banks_at(rung: stepdown.Rung) -> int:
    return round(rung.fps) - (2 if rung.silent else 0)


class TestRungs:
    def test_slower_rates_come_first_then_one_silent_rung(self):
        # Arrange
        settled = 10.0

        # Act
        steps = stepdown.rungs(settled, sound=True)

        # Assert
        assert steps == [
            Rung(8.0, False),
            Rung(6.0, False),
            Rung(5.0, False),
            Rung(4.0, False),
            Rung(3.0, False),
            Rung(3.0, True),
        ]

    def test_a_silent_film_steps_down_the_rate_alone(self):
        # Arrange
        settled = 5.0

        # Act
        steps = stepdown.rungs(settled, sound=False)

        # Assert
        assert steps == [Rung(4.0, True), Rung(3.0, True)]

    def test_at_the_slowest_rate_only_dropping_sound_is_left(self):
        # Arrange
        settled = 3.0

        # Act
        steps = stepdown.rungs(settled, sound=True)

        # Assert
        assert steps == [Rung(3.0, True)]

    def test_a_silent_film_at_the_slowest_rate_has_nowhere_to_go(self):
        # Arrange
        settled = 3.0

        # Act
        steps = stepdown.rungs(settled, sound=False)

        # Assert
        assert steps == []


class TestSearch:
    def test_the_best_rung_that_fits_is_chosen(self):
        # Arrange
        steps = stepdown.rungs(12.0, sound=True)

        # Act
        found = stepdown.search(steps, banks_at, lambda banks: banks <= 5)

        # Assert
        assert found == (Rung(5.0, False), 5)

    def test_dropping_sound_is_the_last_resort(self):
        # Arrange
        steps = stepdown.rungs(12.0, sound=True)

        # Act
        found = stepdown.search(steps, banks_at, lambda banks: banks <= 1)

        # Assert
        assert found == (Rung(3.0, True), 1)

    def test_nothing_fitting_finds_nothing(self):
        # Arrange
        steps = stepdown.rungs(12.0, sound=True)

        # Act
        found = stepdown.search(steps, banks_at, lambda banks: banks <= 0)

        # Assert
        assert found is None

    def test_each_rung_is_baked_at_most_once(self):
        # Arrange
        steps = stepdown.rungs(12.0, sound=True)
        baked: list[stepdown.Rung] = []

        def bake(rung: stepdown.Rung) -> int:
            baked.append(rung)
            return banks_at(rung)

        # Act
        stepdown.search(steps, bake, lambda banks: banks <= 4)

        # Assert
        assert len(baked) == len(set(baked))
