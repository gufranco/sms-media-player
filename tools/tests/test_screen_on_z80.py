from __future__ import annotations

import pytest
from z80vdp import call, load, load_gg

SILENCE = [0x9F, 0xBF, 0xDF, 0xFF]
NAME_TABLE = 0x3800
IDLE_CELL = bytes([0x00, 0x08])
SPRITE_TABLE = 0x3F00
SPRITE_END = 0xD0
ROUTINE = "_fmv_screen_rest"


@pytest.fixture(scope="module", params=["sms", "gg"])
def console(request):
    built = load() if request.param == "sms" else load_gg()
    return built, request.param == "gg"


class TestPuttingTheConsoleAtRest:
    def test_every_psg_channel_is_attenuated_fully(self, console):
        # Arrange
        built, gg = console

        # Act
        vdp, _, _ = call(built, ROUTINE, gg=gg)

        # Assert
        assert vdp.sounds == SILENCE

    def test_the_name_table_draws_the_idle_cell(self, console):
        # Arrange
        built, gg = console

        # Act
        vdp, _, _ = call(built, ROUTINE, gg=gg)

        # Assert
        assert bytes(vdp.vram[NAME_TABLE : NAME_TABLE + 2]) == IDLE_CELL

    def test_every_sprite_is_parked_on_the_terminator(self, console):
        # Arrange
        built, gg = console

        # Act
        vdp, _, _ = call(built, ROUTINE, gg=gg)

        # Assert
        assert vdp.vram[SPRITE_TABLE] == SPRITE_END
