from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "scripts" / "check_vdp_timing.py"

PACED = """
    00000038 0E BE            [ 7]  103 \tld\tc, #0xBE
    0000003A                        104 00050$:
    0000003A ED A3            [16]  105 \touti
    0000003C 00               [ 4]  106 \tnop
    0000003D C2r3Ar00         [10]  107 \tjp\tnz, 00050$
    00000040 C9               [10]  108 \tret
"""

UNROLLED = """
    00000038 0E BE            [ 7]  103 \tld\tc, #0xBE
    0000003A ED A3            [16]  105 \touti
    0000003C ED A3            [16]  106 \touti
    0000003E C9               [10]  107 \tret
"""


def load():
    spec = importlib.util.spec_from_file_location("check_vdp_timing", SCRIPT)
    if spec is None or spec.loader is None:
        msg = f"cannot import {SCRIPT}"
        raise AssertionError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_vdp_timing"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return load()


def listing(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


class TestTheGate:
    def test_it_exists(self):
        # Arrange
        script = SCRIPT

        # Act
        present = script.is_file()

        # Assert
        assert present is True

    def test_a_paced_loop_passes(self, gate, tmp_path):
        # Arrange
        path = listing(tmp_path, "paced.lst", PACED)

        # Act
        result = gate.main([str(path)])

        # Assert
        assert result == 0

    def test_an_unrolled_loop_fails(self, gate, tmp_path):
        # Arrange
        path = listing(tmp_path, "unrolled.lst", UNROLLED)

        # Act
        result = gate.main([str(path)])

        # Assert
        assert result == 1

    def test_the_failure_names_the_file(self, gate, tmp_path, capsys):
        # Arrange
        path = listing(tmp_path, "unrolled.lst", UNROLLED)

        # Act
        gate.main([str(path)])

        # Assert
        assert "unrolled.lst" in capsys.readouterr().err

    def test_the_failure_says_what_goes_wrong_on_hardware(self, gate, tmp_path, capsys):
        # Arrange
        path = listing(tmp_path, "unrolled.lst", UNROLLED)

        # Act
        gate.main([str(path)])

        # Assert
        assert "shreds" in capsys.readouterr().err

    def test_nothing_to_check_is_reported_rather_than_passed(self, gate, tmp_path):
        # Arrange
        arguments = ["--root", str(tmp_path)]

        # Act
        result = gate.main(arguments)

        # Assert
        assert result == 2

    def test_quiet_suppresses_the_summary_but_not_the_failure(self, gate, tmp_path, capsys):
        # Arrange
        path = listing(tmp_path, "unrolled.lst", UNROLLED)

        # Act
        gate.main([str(path), "--quiet"])

        # Assert
        captured = capsys.readouterr()
        assert "intervals" not in captured.out
        assert "TOO FAST" in captured.err

    def test_a_clean_run_says_so(self, gate, tmp_path, capsys):
        # Arrange
        path = listing(tmp_path, "paced.lst", PACED)

        # Act
        gate.main([str(path)])

        # Assert
        assert "clears" in capsys.readouterr().out

    def test_a_run_that_sees_no_data_port_write_fails_closed(self, gate, tmp_path):
        # Arrange
        path = listing(tmp_path, "quiet.lst", "    00000010 00               [ 4]   1 \tnop\n")

        # Act
        result = gate.main([str(path)])

        # Assert
        assert result == 2

    def test_a_run_that_sees_no_data_port_write_says_why(self, gate, tmp_path, capsys):
        # Arrange
        path = listing(tmp_path, "quiet.lst", "    00000010 00               [ 4]   1 \tnop\n")

        # Act
        gate.main([str(path)])

        # Assert
        assert "nothing was checked" in capsys.readouterr().err

    def test_a_listing_older_than_its_source_fails_closed(self, gate, tmp_path):
        # Arrange
        built = tmp_path / "build"
        built.mkdir()
        old = listing(built, "paced.lst", PACED)
        os.utime(old, (1_000_000, 1_000_000))
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "paced.s").write_text("        nop\n")

        # Act
        result = gate.main(["--root", str(tmp_path)])

        # Assert
        assert result == 2

    def test_an_unguarded_blank_copy_fails_the_gate(self, gate, tmp_path, capsys):
        # Arrange
        text = (
            "    00000000 D3 BF            [11]    1 \tout\t(#0xBF), a\n"
            "    00000002 0E BE            [ 7]    2 \tld\tc, #0xBE\n"
            "    00000004                          3 fmvcopy:\n"
            "    00000004 ED A3            [16]    4 \touti\n"
            "    00000006 ED A3            [16]    5 \touti\n"
            "    00000008                          6 fmvdone:\n"
            "    00000008 C9               [10]    7 \tret\n"
        )
        path = listing(tmp_path, "replay.lst", text)

        # Act
        result = gate.main([str(path)])

        # Assert
        assert result == 1
        assert "UNGUARDED" in capsys.readouterr().err
