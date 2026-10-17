from __future__ import annotations

import numpy as np
import pytest

from smsmedia import limits, psgpan, psgsound, stream, target

RATE = 22050
FIELD_HZ = 59.9227
CENTRE = (True, True)


def tone(hz: float, seconds: float, *, level: float = 0.5) -> np.ndarray:
    times = np.arange(int(RATE * seconds)) / RATE
    return (level * np.sin(2 * np.pi * hz * times)).astype(np.float32)


def stereo(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    return np.stack([left, right], axis=1)


def settled(values: list[int | None], field: int) -> int | None:
    written = [value for value in values[: field + 1] if value is not None]
    return written[-1] if written else None


def routed(left: np.ndarray, right: np.ndarray, fields: int) -> list[int | None]:
    writes = psgsound.synthesize((left + right) / 2, rate=RATE, fields=fields)
    return psgpan.pans(stereo(left, right), rate=RATE, writes=writes)


class TestPacking:
    def test_every_channel_on_both_sides_is_all_bits_set(self):
        # Arrange
        routes = [CENTRE] * psgpan.CHANNELS

        # Act
        value = psgpan.pack(routes)

        # Assert
        assert value == 0xFF

    def test_tone_zero_on_the_left_only_clears_its_right_bit(self):
        # Arrange
        routes = [(True, False), CENTRE, CENTRE, CENTRE]

        # Act
        value = psgpan.pack(routes)

        # Assert
        assert value == 0xFE

    def test_noise_on_the_right_only_clears_its_left_bit(self):
        # Arrange
        routes = [CENTRE, CENTRE, CENTRE, (False, True)]

        # Act
        value = psgpan.pack(routes)

        # Assert
        assert value == 0x7F

    def test_a_route_per_channel_is_required(self):
        # Arrange
        routes = [CENTRE] * 3

        # Act
        with pytest.raises(ValueError) as refused:
            psgpan.pack(routes)

        # Assert
        assert str(refused.value) == "a pan routes 4 channels, got 3"


class TestRegisterModel:
    def test_a_latched_tone_and_its_data_byte_give_the_divider(self):
        # Arrange
        writes = [bytes([0x8E, 0x0F, 0x90])]

        # Act
        tones = psgpan.sounding(writes)

        # Assert
        assert tones == [(0xFE, None, None, None)]

    def test_a_muted_channel_has_no_tone(self):
        # Arrange
        writes = [bytes([0x8E, 0x0F, 0x90]), bytes([0x9F])]

        # Act
        tones = psgpan.sounding(writes)

        # Assert
        assert tones[1] == (None, None, None, None)

    def test_a_noise_write_releases_the_latch(self):
        # Arrange
        writes = [bytes([0x8E, 0xE4, 0x0F, 0x90])]

        # Act
        tones = psgpan.sounding(writes)

        # Assert
        assert tones == [(0x0E, None, None, None)]

    def test_sounding_noise_is_reported_apart_from_the_tones(self):
        # Arrange
        writes = [bytes([0xE4, 0xF0])]

        # Act
        tones = psgpan.sounding(writes)

        # Assert
        assert tones == [(None, None, None, psgpan.NOISE_SOUNDING)]

    def test_a_data_byte_with_nothing_latched_changes_nothing(self):
        # Arrange
        writes = [bytes([0x0F])]

        # Act
        tones = psgpan.sounding(writes)

        # Assert
        assert tones == [(None, None, None, None)]


class TestRouting:
    def test_a_melody_on_the_left_is_routed_to_the_left_only(self):
        # Arrange
        melody = tone(440.0, 0.5)

        # Act
        values = routed(melody, np.zeros_like(melody), fields=20)

        # Assert
        assert (values[0], settled(values, 10)) == (0xFF, 0xFE)

    def test_a_melody_on_the_right_is_routed_to_the_right_only(self):
        # Arrange
        melody = tone(440.0, 0.5)

        # Act
        values = routed(np.zeros_like(melody), melody, fields=20)

        # Assert
        assert (values[0], settled(values, 10)) == (0xFF, 0xEF)

    def test_a_centred_melody_writes_only_on_refresh_fields(self):
        # Arrange
        melody = tone(440.0, 2.2)

        # Act
        values = routed(melody, melody, fields=125)

        # Assert
        written = {field: value for field, value in enumerate(values) if value is not None}
        assert written == {0: 0xFF, 60: 0xFF, 120: 0xFF}

    def test_a_move_from_left_to_right_writes_once_at_the_change(self):
        # Arrange
        melody = tone(440.0, 1.0)
        half = melody.shape[0] // 2
        silent = np.zeros(half, dtype=np.float32)
        left = np.concatenate([melody[:half], silent])
        right = np.concatenate([silent, melody[half:]])

        # Act
        values = routed(left, right, fields=50)

        # Assert
        written = [value for value in values if value is not None]
        assert written == [0xFF, 0xFE, 0xEF]

    def test_mono_samples_are_refused(self):
        # Arrange
        melody = tone(440.0, 0.2)

        # Act
        with pytest.raises(ValueError) as refused:
            psgpan.pans(melody, rate=RATE, writes=[b""])

        # Assert
        assert str(refused.value) == (
            f"stereo samples need a left and a right column, got shape {melody.shape}"
        )


class TestTheReserve:
    def test_a_master_system_field_keeps_room_for_the_tones_alone(self):
        # Arrange
        console = target.MASTER_SYSTEM

        # Act
        reserve = limits.sound_reserve(console)

        # Assert
        assert reserve == limits.SOUND_RESERVE

    def test_a_game_gear_field_also_keeps_room_for_a_pan_run(self):
        # Arrange
        console = target.GAME_GEAR

        # Act
        reserve = limits.sound_reserve(console)

        # Assert
        assert reserve == limits.SOUND_RESERVE + stream.PAN_BYTES


class TestTheHold:
    def test_a_routing_held_for_six_fields_takes_effect_on_the_sixth(self):
        # Arrange
        wanted = [0xFF, 0xFE, 0xFE, 0xFE, 0xFE, 0xFE, 0xFE, 0xFE]

        # Act
        routing = psgpan.held(wanted)

        # Assert
        assert routing == [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFE, 0xFE]

    def test_a_routing_that_flickers_never_takes_effect(self):
        # Arrange
        wanted = [0xFE, 0xFF] * 10

        # Act
        routing = psgpan.held(wanted)

        # Assert
        assert set(routing) == {0xFF}
