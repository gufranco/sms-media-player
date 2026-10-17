from __future__ import annotations

import os
import textwrap

import pytest
from fmvcore import sdccz80

from smsggmedia import vdptiming

PACED_LOOP = """
    0000002A F3               [ 4]   92 \tdi
    0000002B 7E               [ 7]   93 \tld\ta, (hl)
    0000002C 23               [ 6]   94 \tinc\thl
    0000002D D3 BF            [11]   95 \tout\t(#0xBF), a
    0000002F 7E               [ 7]   96 \tld\ta, (hl)
    00000030 23               [ 6]   97 \tinc\thl
    00000031 F6 40            [ 7]   98 \tor\ta, #0x40
    00000033 D3 BF            [11]   99 \tout\t(#0xBF), a
    00000035 FB               [ 4]  100 \tei
    00000036 46               [ 7]  101 \tld\tb, (hl)
    00000037 23               [ 6]  102 \tinc\thl
    00000038 0E BE            [ 7]  103 \tld\tc, #0xBE
    0000003A                        104 00050$:
    0000003A ED A3            [16]  105 \touti
    0000003C 00               [ 4]  106 \tnop
    0000003D C2r3Ar00         [10]  107 \tjp\tnz, 00050$
    00000040 C9               [10]  108 \tret
"""

SHIPPED_UNTIL_THE_DOCUMENTED_FLOOR = """
    00000038 0E BE            [ 7]  103 \tld\tc, #0xBE
    0000003A                        104 00050$:
    0000003A ED A3            [16]  105 \touti
    0000003C C2r3Ar00         [10]  106 \tjp\tnz, 00050$
    0000003F C9               [10]  107 \tret
"""

UNROLLED_LOOP = """
    00000038 0E BE            [ 7]  103 \tld\tc, #0xBE
    0000003A ED A3            [16]  105 \touti
    0000003C ED A3            [16]  106 \touti
    0000003E ED A3            [16]  107 \touti
    00000040 C9               [10]  108 \tret
"""

REPEATING = """
    00000038 0E BE            [ 7]  103 \tld\tc, #0xBE
    0000003A ED B3            [21]  104 \totir
    0000003C C9               [10]  105 \tret
"""

CONTROL_PAIR = """
    00000041 F3               [ 4]  109 \tdi
    00000042 7E               [ 7]  110 \tld\ta, (hl)
    00000043 23               [ 6]  111 \tinc\thl
    00000044 D3 BF            [11]  112 \tout\t(#0xBF), a
    00000046 3E C0            [ 7]  113 \tld\ta, #0xC0
    00000048 D3 BF            [11]  114 \tout\t(#0xBF), a
    0000004A C9               [10]  115 \tret
"""

PADDED_CONTROL_PAIR = """
    00000041 F3               [ 4]  109 \tdi
    00000042 7E               [ 7]  110 \tld\ta, (hl)
    00000043 23               [ 6]  111 \tinc\thl
    00000044 D3 BF            [11]  112 \tout\t(#0xBF), a
    00000046 3E C0            [ 7]  113 \tld\ta, #0xC0
    00000048 00               [ 4]  114 \tnop
    00000049 00               [ 4]  115 \tnop
    0000004A 00               [ 4]  116 \tnop
    0000004B D3 BF            [11]  117 \tout\t(#0xBF), a
    0000004D C9               [10]  118 \tret
"""


class TestClassification:
    def test_an_explicit_data_port_write_is_data(self):
        # Arrange
        text = "    00000010 D3 BE            [11]   1 \tout\t(#0xBE), a\n"

        # Act
        listing = vdptiming.parse(text)

        # Assert
        assert listing.instructions[0].port == vdptiming.DATA

    def test_an_explicit_control_port_write_is_control(self):
        # Arrange
        text = textwrap.dedent(CONTROL_PAIR)

        # Act
        listing = vdptiming.parse(text)

        # Assert
        writes = [i for i in listing.instructions if i.port]
        assert {i.port for i in writes} == {vdptiming.CONTROL}

    def test_a_block_output_follows_the_port_register(self):
        # Arrange
        text = textwrap.dedent(UNROLLED_LOOP)

        # Act
        listing = vdptiming.parse(text)

        # Assert
        writes = [i for i in listing.instructions if i.port]
        assert [i.port for i in writes] == [vdptiming.DATA] * 3

    def test_an_ordinary_instruction_touches_no_port(self):
        # Arrange
        text = textwrap.dedent(PACED_LOOP)

        # Act
        listing = vdptiming.parse(text)

        # Assert
        assert listing.instructions[0].port is None


class TestIntervals:
    def test_the_paced_loop_holds_the_minimum(self):
        # Arrange
        listing = textwrap.dedent(PACED_LOOP)

        # Act
        report = vdptiming.check(listing, source="paced")

        # Assert
        assert report.violations == []

    def test_the_paced_loop_measures_exactly_the_branch_plus_the_write(self):
        # Arrange
        listing = textwrap.dedent(PACED_LOOP)

        # Act
        report = vdptiming.check(listing, source="paced")

        # Assert
        wrap = [gap for gap in report.gaps if gap.wrapped]
        assert [gap.cycles for gap in wrap] == [30]

    def test_the_unrolled_loop_is_rejected(self):
        # Arrange
        listing = textwrap.dedent(UNROLLED_LOOP)

        # Act
        report = vdptiming.check(listing, source="unrolled")

        # Assert
        assert [gap.cycles for gap in report.violations] == [16, 16]

    def test_the_unrolled_loop_is_rejected_at_sixteen_cycles(self):
        # Arrange
        listing = textwrap.dedent(UNROLLED_LOOP)

        # Act
        report = vdptiming.check(listing, source="unrolled")

        # Assert
        assert min(v.cycles for v in report.violations) == 16

    def test_a_block_repeat_paces_itself_too_fast(self):
        # Arrange
        listing = textwrap.dedent(REPEATING)

        # Act
        report = vdptiming.check(listing, source="repeating")

        # Assert
        assert [v.cycles for v in report.violations] == [sdccz80.REPEAT_INTERVAL]

    def test_the_paced_loop_clears_the_documented_floor_by_one_cycle(self):
        # Arrange
        listing = textwrap.dedent(PACED_LOOP)

        # Act
        report = vdptiming.check(listing, source="paced")

        # Assert
        assert min(gap.cycles for gap in report.gaps) == vdptiming.MINIMUM_INTERVAL + 1

    def test_the_loop_without_the_pad_is_rejected_at_twenty_six(self):
        # Arrange
        listing = textwrap.dedent(SHIPPED_UNTIL_THE_DOCUMENTED_FLOOR)

        # Act
        report = vdptiming.check(listing, source="community")

        # Assert
        assert [v.cycles for v in report.violations] == [26]

    def test_the_address_setup_clears_the_minimum(self):
        # Arrange
        listing = textwrap.dedent(PACED_LOOP)

        # Act
        report = vdptiming.check(listing, source="paced")

        # Assert
        setup = [gap for gap in report.gaps if not gap.wrapped]
        assert min(gap.cycles for gap in setup) >= vdptiming.MINIMUM_INTERVAL

    def test_a_control_pair_under_the_documented_floor_fails(self):
        # Arrange
        listing = textwrap.dedent(CONTROL_PAIR)

        # Act
        report = vdptiming.check(listing, source="cram")

        # Assert
        assert [gap.cycles for gap in report.violations] == [18]

    def test_a_control_pair_padded_to_the_floor_passes(self):
        # Arrange
        listing = textwrap.dedent(PADDED_CONTROL_PAIR)

        # Act
        report = vdptiming.check(listing, source="cram")

        # Assert
        assert ([gap.cycles for gap in report.control_pairs], report.violations) == ([30], [])

    def test_a_control_pair_carries_its_measured_spacing(self):
        # Arrange
        listing = textwrap.dedent(CONTROL_PAIR)

        # Act
        report = vdptiming.check(listing, source="cram")

        # Assert
        assert [pair.cycles for pair in report.control_pairs] == [18]

    def test_a_violation_names_where_it_is(self):
        # Arrange
        listing = textwrap.dedent(UNROLLED_LOOP)

        # Act
        report = vdptiming.check(listing, source="unrolled")

        # Assert
        assert "unrolled" in report.violations[0].describe()

    def test_a_violation_names_the_cycles_it_measured(self):
        # Arrange
        listing = textwrap.dedent(UNROLLED_LOOP)

        # Act
        report = vdptiming.check(listing, source="unrolled")

        # Assert
        assert "16" in report.violations[0].describe()

    def test_a_listing_with_no_port_write_has_nothing_to_check(self):
        # Arrange
        listing = "    00000010 00               [ 4]   1 \tnop\n"

        # Act
        report = vdptiming.check(listing, source="quiet")

        # Assert
        assert report.gaps == []
        assert report.violations == []


class TestTheShippedPlayer:
    def test_the_player_listing_is_checked_when_it_has_been_built(self):
        # Arrange
        listings = vdptiming.built_listings()
        if not listings:
            reason = "run `make rom` first; this reads the assembler's own output"
            if os.environ.get("SMSGGMEDIA_ROM_REQUIRED") == "1":
                pytest.fail(reason)
            pytest.skip(reason)

        # Act
        reports = vdptiming.check_program({path.name: path.read_text() for path in listings})

        # Assert
        assert [v.describe() for report in reports for v in report.violations] == []


class TestWhatTheGateCanSee:
    def test_a_listing_that_touches_no_data_port_counts_nothing(self):
        # Arrange
        report = vdptiming.check(textwrap.dedent(CONTROL_PAIR), source="cram")

        # Act
        seen = vdptiming.data_intervals([report])

        # Assert
        assert seen == 0

    def test_the_paced_loop_counts_as_seen(self):
        # Arrange
        report = vdptiming.check(textwrap.dedent(PACED_LOOP), source="paced")

        # Act
        seen = vdptiming.data_intervals([report])

        # Assert
        assert seen > 0

    def test_a_listing_older_than_its_source_is_stale(self, tmp_path):
        # Arrange
        (tmp_path / "src").mkdir()
        listing = tmp_path / "player.lst"
        listing.write_text("")
        source = tmp_path / "src" / "player.c"
        source.write_text("")
        os.utime(listing, (1_000, 1_000))
        os.utime(source, (2_000, 2_000))

        # Act
        result = vdptiming.stale_listings([listing], tmp_path)

        # Assert
        assert result == [listing]

    def test_a_listing_newer_than_its_source_is_current(self, tmp_path):
        # Arrange
        (tmp_path / "src").mkdir()
        listing = tmp_path / "player.lst"
        listing.write_text("")
        source = tmp_path / "src" / "player.s"
        source.write_text("")
        os.utime(source, (1_000, 1_000))
        os.utime(listing, (2_000, 2_000))

        # Act
        result = vdptiming.stale_listings([listing], tmp_path)

        # Assert
        assert result == []


GUARDED_COPY = """
    00000000                          1 mvvram:
    00000000 DB 7E            [11]    2 \tin\ta, (#0x7E)
    00000002 FE C0            [ 7]    3 \tcp\ta, #0xC0
    00000004 38 20            [12]    4 \tjr\tc, mvdefer
    00000006 FE E0            [ 7]    5 \tcp\ta, #0xE0
    00000008 30 1C            [12]    6 \tjr\tnc, mvdefer
    0000000A 7E               [ 7]    7 \tld\ta, (hl)
    0000000B D3 BF            [11]    8 \tout\t(#0xBF), a
    0000000D 7E               [ 7]    9 \tld\ta, (hl)
    0000000E 00               [ 4]   10 \tnop
    0000000F 00               [ 4]   11 \tnop
    00000010 00               [ 4]   12 \tnop
    00000011 D3 BF            [11]   13 \tout\t(#0xBF), a
    00000013 0E BE            [ 7]   14 \tld\tc, #0xBE
    00000015 00               [ 4]   15 \tnop
    00000016                         16 fmvcopy:
    00000016 ED A3            [16]   17 \touti
    00000018 ED A3            [16]   18 \touti
    0000001A ED A3            [16]   19 \touti
    0000001C                         20 fmvdone:
    0000001C C9               [10]   21 \tret
    0000001D                         22 mvdefer:
    0000001D C9               [10]   23 \tret
"""


class TestTheBlankCopy:
    def test_back_to_back_writes_inside_the_guarded_copy_pass(self):
        # Arrange
        listing = textwrap.dedent(GUARDED_COPY)

        # Act
        report = vdptiming.check(listing, source="replay")

        # Assert
        assert report.violations == []

    def test_the_guarded_copy_is_measured_at_sixteen(self):
        # Arrange
        listing = textwrap.dedent(GUARDED_COPY)

        # Act
        report = vdptiming.check(listing, source="replay")

        # Assert
        inside = [gap.cycles for gap in report.gaps if gap.first.port == vdptiming.DATA]
        assert min(inside) == vdptiming.VBLANK_INTERVAL

    def test_a_guarded_setup_is_accepted(self):
        # Arrange
        listing = textwrap.dedent(GUARDED_COPY)

        # Act
        report = vdptiming.check(listing, source="replay")

        # Assert
        assert report.unguarded == []

    def test_a_setup_without_the_guard_is_reported(self):
        # Arrange
        unguarded = textwrap.dedent(GUARDED_COPY).replace("\tin\ta, (#0x7E)", "\tnop")

        # Act
        report = vdptiming.check(unguarded, source="replay")

        # Assert
        assert len(report.unguarded) == 2

    def test_a_label_between_the_guard_and_the_setup_voids_the_guard(self):
        # Arrange
        split = textwrap.dedent(
            GUARDED_COPY.replace(
                "    0000000A 7E               [ 7]    7 \tld\ta, (hl)",
                "    0000000A                          7 elsewhere:\n"
                "    0000000A 7E               [ 7]    7 \tld\ta, (hl)",
            )
        )

        # Act
        report = vdptiming.check(split, source="replay")

        # Assert
        assert len(report.unguarded) == 2

    def test_unrolled_writes_outside_the_region_still_fail(self):
        # Arrange
        listing = textwrap.dedent(UNROLLED_LOOP)

        # Act
        report = vdptiming.check(listing, source="elsewhere")

        # Assert
        assert [gap.cycles for gap in report.violations] == [16, 16]

    def test_a_listing_without_a_copy_needs_no_guard(self):
        # Arrange
        listing = textwrap.dedent(PACED_LOOP)

        # Act
        report = vdptiming.check(listing, source="paced")

        # Assert
        assert report.unguarded == []

    def test_a_block_that_does_not_reach_the_copy_needs_no_guard(self):
        # Arrange
        detached = textwrap.dedent(GUARDED_COPY.replace("\tnop", "\tret")).replace(
            "\tin\ta, (#0x7E)", "\tnop"
        )

        # Act
        report = vdptiming.check(detached, source="replay")

        # Assert
        assert report.unguarded == []

    def test_a_branch_into_the_copy_needs_the_guard_too(self):
        # Arrange
        branching = textwrap.dedent(GUARDED_COPY.replace("\tnop", "\tjp\tfmvcopy")).replace(
            "\tin\ta, (#0x7E)", "\tld\ta, b"
        )

        # Act
        report = vdptiming.check(branching, source="replay")

        # Assert
        assert len(report.unguarded) == 2


OTHER_PORTS = """
    00000000                          7 _sound::
    00000000 D3 7F            [11]    8 \tout\t(#0x7F), a
    00000002                          9 \t; a comment the assembler kept
    00000002 C9               [10]   10 \tret
"""


class TestWritesTheGateIgnores:
    def test_a_sound_chip_write_is_not_a_vdp_write(self):
        # Arrange
        listing = OTHER_PORTS

        # Act
        parsed = vdptiming.parse(listing)

        # Assert
        assert [instruction.port for instruction in parsed.instructions] == [None, None]
