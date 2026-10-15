from __future__ import annotations

import numpy as np
import pytest

from smsmedia import console, pattern


class TestMemoryMap:
    def test_the_name_table_ends_where_the_sprite_table_starts(self):
        # Arrange
        expected = console.SAT_BASE

        # Act
        end = console.NAME_TABLE_BASE + console.NAME_TABLE_BYTES

        # Assert
        assert end == expected

    def test_the_sprite_table_ends_at_the_top_of_vram(self):
        # Arrange
        expected = console.VRAM_BYTES

        # Act
        end = console.SAT_BASE + 4 * console.SPRITE_SLOTS

        # Assert
        assert end == expected

    def test_the_pattern_slots_fill_vram_up_to_the_name_table(self):
        # Arrange
        expected = console.BACK_TABLE_BASE

        # Act
        end = console.PATTERN_SLOTS * console.PATTERN_BYTES

        # Assert
        assert end == expected

    def test_the_visible_rows_are_fewer_than_the_name_table_holds(self):
        # Arrange
        held = console.NAME_TABLE_ROWS

        # Act
        visible = console.VISIBLE_ROWS

        # Assert
        assert visible < held

    def test_the_pattern_format_agrees_with_the_packer(self):
        # Arrange
        expected = pattern.PATTERN_BYTES

        # Act
        size = console.PATTERN_BYTES

        # Assert
        assert size == expected

    def test_the_idle_cell_selects_the_palette_the_border_uses(self):
        # Arrange
        expected = pattern.PALETTE_BIT

        # Act
        cell = console.IDLE_CELL

        # Assert
        assert cell == expected

    def test_the_idle_cell_names_a_withheld_pattern(self):
        # Arrange
        withheld = console.RESERVED_PATTERNS

        # Act
        named = console.IDLE_CELL & 0x01FF

        # Assert
        assert named < withheld

    def test_at_least_one_pattern_is_withheld(self):
        # Arrange
        minimum = 1

        # Act
        withheld = console.RESERVED_PATTERNS

        # Assert
        assert withheld >= minimum


class TestBootState:
    def test_vram_is_the_size_the_hardware_has(self):
        # Arrange
        expected = (console.VRAM_BYTES,)

        # Act
        vram = console.boot_vram()

        # Assert
        assert vram.shape == expected

    def test_every_pattern_slot_starts_blank(self):
        # Arrange
        patterns_end = console.BACK_TABLE_BASE

        # Act
        vram = console.boot_vram()

        # Assert
        assert int(np.count_nonzero(vram[:patterns_end])) == 0

    def test_every_name_table_cell_starts_idle(self):
        # Arrange
        start, end = console.NAME_TABLE_BASE, console.SAT_BASE

        # Act
        vram = console.boot_vram()

        # Assert
        table = vram[start:end]
        entries = table[0::2].astype(np.uint16) | (table[1::2].astype(np.uint16) << 8)
        assert bool(np.all(entries == console.IDLE_CELL)) is True

    def test_the_sprite_list_starts_terminated(self):
        # Arrange
        first_y = console.SAT_BASE

        # Act
        vram = console.boot_vram()

        # Assert
        assert vram[first_y] == console.SPRITE_OFF

    def test_no_sprite_slot_is_left_on_screen(self):
        # Arrange
        start, end = console.SAT_BASE, console.SAT_BASE + console.SPRITE_SLOTS

        # Act
        vram = console.boot_vram()

        # Assert
        assert bool(np.all(vram[start:end] == console.SPRITE_OFF)) is True

    def test_cram_starts_black(self):
        # Arrange
        black = 0

        # Act
        cram = console.boot_cram()

        # Assert
        assert int(np.count_nonzero(cram != black)) == 0

    def test_cram_is_the_size_the_hardware_has(self):
        # Arrange
        expected = (console.CRAM_BYTES,)

        # Act
        cram = console.boot_cram()

        # Assert
        assert cram.shape == expected

    def test_the_boot_state_is_a_fresh_array_each_time(self):
        # Arrange
        first = console.boot_vram()
        first[0] = 0xFF

        # Act
        second = console.boot_vram()

        # Assert
        assert second[0] == 0

    def test_the_idle_cell_renders_black_under_a_pinned_palette(self):
        # Arrange
        blank_end = console.PATTERN_BYTES

        # Act
        vram, cram = console.boot_vram(), console.boot_cram()

        # Assert
        assert int(np.count_nonzero(vram[:blank_end])) == 0
        assert int(cram[16]) == 0


class TestConstantsAreNotAccidental:
    @pytest.mark.parametrize(
        ("name", "value"),
        [
            ("VRAM_BYTES", 0x4000),
            ("CRAM_BYTES", 32),
            ("NAME_TABLE_BASE", 0x3800),
            ("SAT_BASE", 0x3F00),
            ("SPRITE_OFF", 0xD0),
            ("IDLE_CELL", 0x0800),
            ("BACK_TABLE_BASE", 0x3000),
            ("PATTERN_SLOTS", 384),
            ("NTSC_CPU_HZ", 3_579_545),
            ("NTSC_LINES", 262),
            ("CYCLES_PER_LINE", 228),
        ],
    )
    def test_the_documented_value_is_the_one_in_use(self, name, value):
        # Arrange
        expected = value

        # Act
        in_use = getattr(console, name)

        # Assert
        assert in_use == expected

    def test_the_field_rate_is_the_cpu_clock_over_a_whole_field(self):
        # Arrange
        worked_example = 59.92274

        # Act
        rate = console.NTSC_FIELD_HZ

        # Assert
        assert rate == pytest.approx(worked_example, abs=1e-5)


class TestTwoTables:
    def test_both_tables_start_idle(self):
        # Arrange
        start = console.BACK_TABLE_BASE
        end = console.BACK_TABLE_BASE + console.NAME_TABLE_BYTES
        expected = [console.IDLE_CELL] * (console.NAME_TABLE_BYTES // 2)

        # Act
        vram = console.boot_vram()

        # Assert
        assert vram[start:end].view("<u2").tolist() == expected

    def test_the_tables_do_not_overlap_the_patterns(self):
        # Arrange
        patterns_end = console.PATTERN_SLOTS * console.PATTERN_BYTES

        # Act
        lowest = min(console.NAME_TABLES)

        # Assert
        assert lowest >= patterns_end

    def test_each_register_value_names_its_table(self):
        # Arrange
        registers = [console.TABLE_REGISTER[base] for base in console.NAME_TABLES]

        # Act
        named = [console.table_at(register) for register in registers]

        # Assert
        assert named == list(console.NAME_TABLES)

    def test_an_unknown_register_value_is_refused(self):
        # Arrange
        register = 0x00

        # Act
        with pytest.raises(ValueError) as refused:
            console.table_at(register)

        # Assert
        assert str(refused.value) == "register 2 value 0x00 selects no table this player uses"
