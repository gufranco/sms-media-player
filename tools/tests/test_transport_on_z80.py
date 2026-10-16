from __future__ import annotations

import struct

import pytest
from z80vdp import WHERE, Session, load

UP = 0x0001
DOWN = 0x0002
LEFT = 0x0004
RIGHT = 0x0008
BUTTON_1 = 0x0010
BUTTON_2 = 0x0020
MUTE = 0x0001
BACK = 0x0002
AHEAD = 0x0004
DIAG = 0x0008
RESTART = 0x0010
STOP = 0x0020
SHOW = 0x0040
REFRESH = 0x0080
HIDE = 0x0100
TICK = 0x0200
RESUME = 0x0400
OVERLAY_FIELDS = 180
TICK_FIELDS = 60
OVERLAY_AT = WHERE + 3
TICK_AT = WHERE + 4


@pytest.fixture(scope="module")
def built():
    return load()


def state(*, pressed: int = 0, pause: int = 0, overlay: int = 0, tick: int = 0) -> bytes:
    return struct.pack("<HBBB", pressed, pause, overlay, tick)


def playing(built, payload: bytes) -> tuple[int, Session]:
    session = Session(built, payload)
    session.call("_fmv_transport_playing")
    return session.cpu.registers.de, session


def paused(built, payload: bytes) -> tuple[int, Session]:
    session = Session(built, payload)
    session.call("_fmv_transport_paused")
    return session.cpu.registers.de, session


def wakes(built, payload: bytes) -> int:
    session = Session(built, payload)
    session.call("_fmv_transport_wakes")
    return session.cpu.registers.a


def overlay_of(session: Session) -> int:
    return session.memory.read8(OVERLAY_AT)


class TestTheOverlayWhilePlaying:
    @pytest.mark.parametrize("key", [UP, DOWN, LEFT, RIGHT, BUTTON_1])
    def test_a_press_shows_the_hidden_overlay(self, built, key):
        # Arrange
        payload = state(pressed=key)

        # Act
        actions, _ = playing(built, payload)

        # Assert
        assert actions & (SHOW | REFRESH) == SHOW

    @pytest.mark.parametrize("key", [UP, DOWN, LEFT, RIGHT, BUTTON_1])
    def test_a_press_holds_the_overlay_for_180_fields(self, built, key):
        # Arrange
        payload = state(pressed=key, overlay=5)

        # Act
        _, session = playing(built, payload)

        # Assert
        assert overlay_of(session) == OVERLAY_FIELDS

    def test_a_press_while_shown_refreshes_rather_than_reopens(self, built):
        # Arrange
        payload = state(pressed=UP, overlay=40)

        # Act
        actions, _ = playing(built, payload)

        # Assert
        assert actions & (SHOW | REFRESH) == REFRESH

    def test_button_2_does_not_show_the_overlay(self, built):
        # Arrange
        payload = state(pressed=BUTTON_2)

        # Act
        actions, _ = playing(built, payload)

        # Assert
        assert actions & (SHOW | REFRESH | STOP) == STOP

    def test_the_last_overlay_field_hides_it(self, built):
        # Arrange
        payload = state(overlay=1)

        # Act
        actions, session = playing(built, payload)

        # Assert
        assert (actions & HIDE, overlay_of(session)) == (HIDE, 0)

    def test_a_shown_overlay_counts_down_without_hiding(self, built):
        # Arrange
        payload = state(overlay=OVERLAY_FIELDS)

        # Act
        actions, session = playing(built, payload)

        # Assert
        assert (actions & HIDE, overlay_of(session)) == (0, OVERLAY_FIELDS - 1)

    def test_a_hidden_overlay_stays_hidden_without_a_press(self, built):
        # Arrange
        payload = state()

        # Act
        actions, _ = playing(built, payload)

        # Assert
        assert actions & (SHOW | REFRESH | HIDE) == 0


class TestTheOnceASecondTick:
    def test_the_sixtieth_field_ticks(self, built):
        # Arrange
        payload = state(tick=TICK_FIELDS - 1)

        # Act
        actions, session = playing(built, payload)

        # Assert
        assert (actions & TICK, session.memory.read8(TICK_AT)) == (TICK, 0)

    def test_an_earlier_field_does_not_tick(self, built):
        # Arrange
        payload = state(tick=TICK_FIELDS - 2)

        # Act
        actions, _ = playing(built, payload)

        # Assert
        assert actions & TICK == 0


class TestTheKeysWhilePlaying:
    @pytest.mark.parametrize(
        ("key", "action"),
        [
            (UP, MUTE),
            (DOWN, DIAG),
            (LEFT, BACK),
            (RIGHT, AHEAD),
            (BUTTON_1, RESTART),
            (BUTTON_2, STOP),
        ],
    )
    def test_each_key_maps_to_its_action(self, built, key, action):
        # Arrange
        payload = state(pressed=key)

        # Act
        actions, _ = playing(built, payload)

        # Assert
        assert actions & (MUTE | DIAG | BACK | AHEAD | RESTART | STOP) == action


class TestWhilePaused:
    @pytest.mark.parametrize("key", [DOWN, BUTTON_1])
    def test_down_and_button_1_toggle_the_diagnostics(self, built, key):
        # Arrange
        payload = state(pressed=key)

        # Act
        actions, _ = paused(built, payload)

        # Assert
        assert actions == DIAG

    def test_pause_resumes(self, built):
        # Arrange
        payload = state(pause=1)

        # Act
        actions, _ = paused(built, payload)

        # Assert
        assert actions == RESUME

    def test_resuming_keeps_the_overlay_for_180_fields(self, built):
        # Arrange
        payload = state(pause=1)

        # Act
        _, session = paused(built, payload)

        # Assert
        assert overlay_of(session) == OVERLAY_FIELDS


class TestAfterAStop:
    @pytest.mark.parametrize(
        "payload", [state(pressed=BUTTON_1), state(pressed=BUTTON_2), state(pause=1)]
    )
    def test_button_1_button_2_or_pause_plays_again(self, built, payload):
        # Arrange
        expected = 1

        # Act
        woken = wakes(built, payload)

        # Assert
        assert woken == expected

    @pytest.mark.parametrize("key", [0, UP, DOWN, LEFT, RIGHT])
    def test_other_keys_stay_stopped(self, built, key):
        # Arrange
        payload = state(pressed=key)

        # Act
        woken = wakes(built, payload)

        # Assert
        assert woken == 0


class TestBeginning:
    def test_playback_starts_with_the_overlay_up_for_180_fields(self, built):
        # Arrange
        session = Session(built, state(tick=33))

        # Act
        session.call("_fmv_transport_begin")

        # Assert
        assert (overlay_of(session), session.memory.read8(TICK_AT)) == (OVERLAY_FIELDS, 0)
