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

INK_REWRITE = (
    ("ED A3", 16, "outi"),
    ("ED A3", 16, "outi"),
    None,
    ("3A 00 00", 13, "ld\ta, (_movie_inks)"),
    ("B7", 4, "or\ta, a"),
    ("E5", 11, "push\thl"),
    ("F3", 4, "di"),
    ("3E 1E", 7, "ld\ta, #0x1E"),
    ("D3 BF", 11, "out\t(#0xBF), a"),
    ("3E C0", 7, "ld\ta, #0xC0"),
    ("00", 4, "nop"),
    ("00", 4, "nop"),
    ("00", 4, "nop"),
    ("D3 BF", 11, "out\t(#0xBF), a"),
    ("FB", 4, "ei"),
    ("C9", 10, "ret"),
)

UNPADDED_INK_REWRITE = (
    ("ED A3", 16, "outi"),
    ("ED A3", 16, "outi"),
    None,
    ("3E 1E", 7, "ld\ta, #0x1E"),
    ("D3 BF", 11, "out\t(#0xBF), a"),
    ("3E C0", 7, "ld\ta, #0xC0"),
    ("D3 BF", 11, "out\t(#0xBF), a"),
    ("C9", 10, "ret"),
)


def after_the_blank_copy(rows: tuple[tuple[str, int, str] | None, ...]) -> str:
    lines = [f"    {0:08X}{1:>27} fmvcopy:"]
    address = 0
    for number, row in enumerate(rows, start=2):
        if row is None:
            lines.append(f"    {address:08X}{number:>27} fmvdone:")
            continue
        code, cycles, text = row
        lines.append(f"    {address:08X} {code:<17}[{cycles:>2}]{number:>5} \t{text}")
        address += len(code.split())
    return "\n".join(lines) + "\n"


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

    def test_a_game_gear_listing_older_than_its_own_source_fails_closed(self, gate, tmp_path):
        # Arrange
        built = tmp_path / "build" / "gg"
        built.mkdir(parents=True)
        old = listing(built, "paced.lst", PACED)
        os.utime(old, (1_000_000, 1_000_000))
        (tmp_path / "src" / "gg").mkdir(parents=True)
        (tmp_path / "src" / "gg" / "paced.c").write_text("void f(void) {}\n")

        # Act
        result = gate.main(["--root", str(tmp_path), "--target", "gg"])

        # Assert
        assert result == 2

    def test_the_game_gear_run_reads_its_own_build(self, gate, tmp_path):
        # Arrange
        built = tmp_path / "build" / "gg"
        built.mkdir(parents=True)
        listing(tmp_path / "build", "paced.lst", UNROLLED)
        listing(built, "paced.lst", PACED)
        (tmp_path / "src").mkdir()
        source = tmp_path / "src" / "paced.s"
        source.write_text("        nop\n")
        os.utime(source, (1_000, 1_000))

        # Act
        result = gate.main(["--root", str(tmp_path), "--target", "gg"])

        # Assert
        assert result == 0

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

    def test_an_ink_rewrite_after_the_blank_copy_padded_to_the_floor_passes(self, gate, tmp_path):
        # Arrange
        path = listing(tmp_path, "replay.lst", after_the_blank_copy(INK_REWRITE))

        # Act
        result = gate.main([str(path)])

        # Assert
        assert result == 0

    def test_an_ink_rewrite_after_the_blank_copy_without_padding_fails(self, gate, tmp_path):
        # Arrange
        path = listing(tmp_path, "replay.lst", after_the_blank_copy(UNPADDED_INK_REWRITE))

        # Act
        result = gate.main([str(path)])

        # Assert
        assert result == 1
