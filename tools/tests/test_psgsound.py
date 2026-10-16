from __future__ import annotations

import numpy as np
import pytest

from smsmedia import psgsound, replay, stream

RATE = 22050
FIELD_HZ = 59.9227


def tone(hz: float, seconds: float, *, level: float = 0.5) -> np.ndarray:
    times = np.arange(int(RATE * seconds)) / RATE
    return (level * np.sin(2 * np.pi * hz * times)).astype(np.float32)


def registers(writes: list[bytes]) -> dict[str, int]:
    state: dict[str, int] = {}
    latched = None
    for field in writes:
        for byte in field:
            if byte & 0x80:
                channel = (byte >> 5) & 0x03
                if byte & 0x10:
                    state[f"att{channel}"] = byte & 0x0F
                    latched = None
                else:
                    state[f"low{channel}"] = byte & 0x0F
                    latched = channel
            elif latched is not None:
                state[f"high{latched}"] = byte & 0x3F
    return state


def divider(state: dict[str, int], channel: int) -> int:
    return state[f"low{channel}"] | (state[f"high{channel}"] << 4)


class TestSynthesis:
    def test_a_440_hz_tone_sets_the_divider_the_clock_gives(self):
        # Arrange
        samples = tone(440.0, 0.5)

        # Act
        writes = psgsound.synthesize(samples, rate=RATE, fields=20)

        # Assert
        assert divider(registers(writes), 0) == round(3_579_545 / (32 * 440.0))

    def test_the_loudest_tone_plays_at_full_volume(self):
        # Arrange
        samples = tone(440.0, 0.5)

        # Act
        writes = psgsound.synthesize(samples, rate=RATE, fields=20)

        # Assert
        assert registers(writes)["att0"] == 0

    def test_silence_mutes_every_channel(self):
        # Arrange
        samples = np.zeros(RATE, dtype=np.float32)

        # Act
        writes = psgsound.synthesize(samples, rate=RATE, fields=30)

        # Assert
        state = registers(writes)
        assert [state[f"att{channel}"] for channel in range(4)] == [15, 15, 15, 15]

    def test_one_list_of_writes_comes_out_per_field(self):
        # Arrange
        samples = tone(220.0, 1.0)

        # Act
        writes = psgsound.synthesize(samples, rate=RATE, fields=45)

        # Assert
        assert len(writes) == 45

    def test_a_held_tone_writes_nothing_once_it_is_set(self):
        # Arrange
        samples = tone(330.0, 1.0)

        # Act
        writes = psgsound.synthesize(samples, rate=RATE, fields=40)

        # Assert
        assert writes[20] == b""

    def test_a_held_tone_is_written_again_once_a_second(self):
        # Arrange
        samples = tone(330.0, 2.0)

        # Act
        writes = psgsound.synthesize(samples, rate=RATE, fields=90)

        # Assert
        assert writes[60] == writes[0]

    def test_a_field_never_writes_more_than_the_reserve_allows(self):
        # Arrange
        rng = np.random.default_rng(3)
        samples = rng.uniform(-1, 1, RATE).astype(np.float32)

        # Act
        writes = psgsound.synthesize(samples, rate=RATE, fields=59)

        # Assert
        assert max(len(field) for field in writes) <= psgsound.MAX_FIELD_WRITES

    def test_a_quiet_passage_long_after_a_loud_one_is_still_heard(self):
        # Arrange
        samples = np.concatenate(
            [tone(440.0, 1.0), np.zeros(RATE * 9, dtype=np.float32), tone(440.0, 2.0, level=0.02)]
        )

        # Act
        writes = psgsound.synthesize(samples, rate=RATE, fields=int(11.5 * FIELD_HZ))

        # Assert
        assert registers(writes)["att0"] <= 2

    def test_a_harmonic_of_a_note_gets_no_channel_of_its_own(self):
        # Arrange
        samples = tone(220.0, 0.5) + tone(440.0, 0.5, level=0.25)

        # Act
        writes = psgsound.synthesize(samples, rate=RATE, fields=20)

        # Assert
        assert registers(writes)["att1"] == 15

    def test_a_held_note_keeps_its_channel_when_another_grows_louder(self):
        # Arrange
        times = np.arange(RATE) / RATE
        rising = (0.1 + 0.4 * times) * np.sin(2 * np.pi * 523.0 * times)
        samples = (tone(330.0, 1.0, level=0.3) + rising).astype(np.float32)
        held = round(3_579_545 / (32 * 330.0))

        # Act
        writes = psgsound.synthesize(samples, rate=RATE, fields=55)

        # Assert
        assert [divider(registers(writes[:end]), 0) for end in (10, 55)] == [held, held]

    def test_fields_past_the_end_of_the_soundtrack_are_silent(self):
        # Arrange
        samples = tone(440.0, 0.1)

        # Act
        writes = psgsound.synthesize(samples, rate=RATE, fields=60)

        # Assert
        assert registers(writes)["att0"] == 15

    def test_no_fields_is_refused(self):
        # Arrange
        samples = tone(440.0, 0.1)

        # Act
        with pytest.raises(ValueError) as refused:
            psgsound.synthesize(samples, rate=RATE, fields=0)

        # Assert
        assert str(refused.value) == "a film needs at least one field of sound"


class TestTheStream:
    def test_a_sound_run_follows_a_carried_close(self):
        # Arrange
        close = bytes([stream.CLOSE, 0xFF]) + bytes(stream.CLOSE_BYTES)
        vram = bytes([stream.VRAM, 0x00, 0x00, 1, 7])
        fields = [[close + vram + bytes([stream.END_CHUNK])]]

        # Act
        sounded = stream.add_sound(fields, [b"\x9f"])

        # Assert
        assert sounded[0][0] == close + bytes([stream.PSG, 1, 0x9F]) + vram + bytes(
            [stream.END_CHUNK]
        )

    def test_a_field_with_no_writes_is_left_alone(self):
        # Arrange
        fields = [[bytes([stream.END_CHUNK])]]

        # Act
        sounded = stream.add_sound(fields, [b""])

        # Assert
        assert sounded == fields

    def test_the_oracle_records_what_the_player_writes_to_the_psg(self):
        # Arrange
        chunk = bytes([stream.PSG, 2, 0x9F, 0xBF, stream.END_FRAME])
        machine = replay.Machine()

        # Act
        machine.apply(chunk)

        # Assert
        assert machine.psg == [0x9F, 0xBF]

    def test_the_chunk_splitter_steps_over_a_sound_run(self):
        # Arrange
        blob = bytes([stream.PSG, 1, 0x9F, stream.END_FRAME])

        # Act
        chunks = replay.frames_of(blob, bank_size=len(blob))

        # Assert
        assert chunks == [blob]
