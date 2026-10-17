from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from smsggmedia import target

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "scripts" / "check_rom.py"
BANK = 16 * 1024


def load():
    spec = importlib.util.spec_from_file_location("check_rom", SCRIPT)
    if spec is None or spec.loader is None:
        msg = f"cannot import {SCRIPT}"
        raise AssertionError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_rom"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return load()


def cartridge(*, region: int, banks: int = 2, body: int = 0x5A) -> bytearray:
    rom = bytearray([body]) * (banks * BANK)
    rom[0x7FF0:0x7FF8] = b"TMR SEGA"
    rom[0x7FFF] = (region << 4) | 0x0C
    total = (sum(rom[:0x7FF0]) & 0xFFFF).to_bytes(2, "little")
    rom[0x7FFA:0x7FFC] = total
    return rom


class TestAHeader:
    @pytest.mark.parametrize("system", [target.MASTER_SYSTEM, target.GAME_GEAR])
    def test_a_well_formed_cartridge_has_no_problem(self, gate, system):
        # Arrange
        rom = bytes(cartridge(region=system.region))

        # Act
        found = gate.problems(rom, system)

        # Assert
        assert found == []

    def test_a_game_gear_region_on_a_master_system_cartridge_is_named(self, gate):
        # Arrange
        rom = bytes(cartridge(region=0x7))

        # Act
        found = gate.problems(rom, target.MASTER_SYSTEM)

        # Assert
        assert found == ["region 0x7 is not the Master System's 0x4"]

    def test_a_body_changed_after_the_checksum_is_named(self, gate):
        # Arrange
        rom = cartridge(region=0x4)
        rom[0x100] ^= 0x01

        # Act
        found = gate.problems(bytes(rom), target.MASTER_SYSTEM)

        # Assert
        assert found == ["checksum 0xFA60 does not match the body's 0xFA61"]

    def test_a_cartridge_without_the_signature_is_refused(self, gate):
        # Arrange
        rom = cartridge(region=0x4)
        rom[0x7FF0:0x7FF8] = bytes(8)

        # Act
        found = gate.problems(bytes(rom), target.MASTER_SYSTEM)

        # Assert
        assert found == ["no TMR SEGA header at 0x7FF0"]

    def test_a_partial_bank_is_refused(self, gate):
        # Arrange
        rom = bytes(cartridge(region=0x4))[:-1]

        # Act
        found = gate.problems(rom, target.MASTER_SYSTEM)

        # Assert
        assert found == ["a cartridge is a whole number of 16 KB banks, got 32767 bytes"]

    def test_a_header_that_widens_the_checksum_is_named(self, gate):
        # Arrange
        rom = cartridge(region=0x4)
        rom[0x7FFF] = 0x4F

        # Act
        found = gate.problems(bytes(rom), target.MASTER_SYSTEM)

        # Assert
        assert found[0].startswith("size code 0xF widens the checksum past 0x8000")


class TestTheCommand:
    def test_a_clean_pair_exits_zero(self, gate, tmp_path):
        # Arrange
        sms = tmp_path / "film.sms"
        sms.write_bytes(bytes(cartridge(region=0x4)))
        gg = tmp_path / "film.gg"
        gg.write_bytes(bytes(cartridge(region=0x7)))

        # Act
        code = gate.main([str(sms), str(gg)])

        # Assert
        assert code == 0

    def test_a_problem_exits_one(self, gate, tmp_path):
        # Arrange
        gg = tmp_path / "film.gg"
        gg.write_bytes(bytes(cartridge(region=0x4)))

        # Act
        code = gate.main([str(gg)])

        # Assert
        assert code == 1

    def test_an_unknown_extension_is_refused_by_name(self, gate, tmp_path):
        # Arrange
        rom = tmp_path / "film.bin"

        # Act
        with pytest.raises(ValueError) as refused:
            gate.system_of(rom)

        # Assert
        assert (
            str(refused.value) == "film.bin is not a cartridge this gate knows; it reads .sms, .gg"
        )
