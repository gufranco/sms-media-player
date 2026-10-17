from __future__ import annotations

import os
import re
from itertools import pairwise
from pathlib import Path

import pytest
from z80 import Cpu, Memory
from z80vdp import call

from smsmedia import console, stream

ROOT = Path(__file__).resolve().parents[2]
ROM = ROOT / "build" / "smsmedia.sms"
SYMBOLS = ROOT / "build" / "smsmedia.noi"
WINDOW = 0x8000
RETURN = 0xFFF0
STACK = 0xDFF0
HALT = 0x76
STEP_LIMIT = 200_000
V_COUNTER = 0x7E
DATA_PORT = 0xBE
CONTROL_PORT = 0xBF
SOUND_PORT = 0x7F
PAN_PORT = 0x06
SOUND_FLOOR = 32
SOUND_WRITES = bytes([0x9F, 0xBF, 0xDF, 0x80, 0x04])
INSIDE = 0xC8
ACTIVE = 0x40
LATE = 0xE4
PAYLOAD = bytes(range(1, 41))
PALETTE = bytes(range(32))
BAD = 0x80
RETIRED_KINDS = (0x03, 0x04)
FIRST_BANK = 2
ROM_REQUIRED_ENV = "SMSMEDIA_ROM_REQUIRED"
ACTIVE_FLOOR = 29
BLANK_FLOOR = 16
GUARD = bytes([0xDB, V_COUNTER, 0xFE, 0xC0, 0x38])
GUARD_BRANCHES = (4, 8)
NOP = 0x00


def symbols() -> dict[str, int]:
    found = {}
    for line in SYMBOLS.read_text().splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0] == "DEF":
            found[parts[1]] = int(parts[2], 16)
    return found


@pytest.fixture(scope="module")
def built():
    if not ROM.is_file() or not SYMBOLS.is_file():
        if os.environ.get(ROM_REQUIRED_ENV) == "1":
            pytest.fail(f"{ROM.name} or its symbols are missing and {ROM_REQUIRED_ENV}=1")
        pytest.skip("run `make rom` first; this executes the ROM's own replay")
    return ROM.read_bytes(), symbols()


def without_guard(rom: bytes) -> bytes:
    start = rom.find(GUARD)
    if start < 0:
        pytest.fail("the V counter guard was not found in the ROM")
    patched = bytearray(rom)
    for offset in GUARD_BRANCHES:
        patched[start + offset] = NOP
        patched[start + offset + 1] = NOP
    return bytes(patched)


def control_stamps(ports: Ports) -> list[int]:
    return [cycle for cycle, port, _ in ports.writes if port == CONTROL_PORT]


class Ports:
    def __init__(self, lines: list[int]) -> None:
        self.lines = lines
        self.reads = 0
        self.writes: list[tuple[int, int, int]] = []
        self.clock: Cpu | None = None

    def read(self, address: int) -> int:
        if address & 0xFF == V_COUNTER:
            line = self.lines[min(self.reads, len(self.lines) - 1)]
            self.reads += 1
            return line
        return 0xFF

    def write(self, address: int, value: int) -> None:
        if self.clock is not None and address & 0xFF in (
            DATA_PORT,
            CONTROL_PORT,
            SOUND_PORT,
            PAN_PORT,
        ):
            self.writes.append((self.clock.cycles, address & 0xFF, value))

    def sound(self) -> list[tuple[int, int]]:
        return [(cycle, value) for cycle, port, value in self.writes if port == SOUND_PORT]

    def data(self) -> list[int]:
        return [value for _, port, value in self.writes if port == DATA_PORT]

    def pans(self) -> list[int]:
        return [value for _, port, value in self.writes if port == PAN_PORT]


def film() -> bytes:
    vram = bytes([stream.VRAM, 0x00, 0x10, len(PAYLOAD)]) + PAYLOAD
    close = bytes([stream.CLOSE, console.TABLE_REGISTER[console.BACK_TABLE_BASE]]) + PALETTE
    return vram + close + bytes([stream.END_FRAME])


def replay(
    built,
    lines: list[int],
    *,
    data: bytes | None = None,
    banks: int = 1,
    muted: bool = False,
    inks: bool = False,
) -> tuple[Ports, Memory, dict[str, int]]:
    rom, names = built
    chunk = film() if data is None else data
    image = bytearray(0x10000)
    image[:WINDOW] = rom[:WINDOW]
    image[WINDOW : WINDOW + len(chunk)] = chunk
    image[names["_movie_bank"]] = FIRST_BANK
    image[names["_movie_last_bank"]] = FIRST_BANK + banks - 1
    image[names["_movie_muted"]] = int(muted)
    image[names["_movie_inks"]] = int(inks)
    image[RETURN] = HALT
    cursor = names["_movie_cursor"]
    image[cursor] = WINDOW & 0xFF
    image[cursor + 1] = WINDOW >> 8
    image[STACK] = RETURN & 0xFF
    image[STACK + 1] = RETURN >> 8
    memory = Memory(image=bytes(image))
    ports = Ports(lines)
    cpu = Cpu("z80", memory, ports=ports)
    cpu.reset()
    cpu.registers.pc = names["_movie_replay"]
    cpu.registers.sp = STACK
    ports.clock = cpu
    for _ in range(STEP_LIMIT):
        if cpu.halted:
            break
        cpu.step()
    if not cpu.halted:
        pytest.fail(f"the replay did not return within {STEP_LIMIT} steps")
    return ports, memory, names


def word_at(memory: Memory, address: int) -> int:
    return memory.read8(address) | (memory.read8(address + 1) << 8)


def cursor_of(memory: Memory, names: dict[str, int]) -> int:
    address = names["_movie_cursor"]
    return memory.read8(address) | (memory.read8(address + 1) << 8)


class TestInsideTheWindow:
    def test_the_payload_reaches_the_data_port_in_order(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        ports, _, _ = replay(built, lines)

        # Assert
        assert ports.data()[: len(PAYLOAD)] == list(PAYLOAD)

    def test_the_palette_follows_the_payload(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        ports, _, _ = replay(built, lines)

        # Assert
        assert ports.data()[len(PAYLOAD) :] == list(PALETTE)

    def test_the_closing_run_selects_the_other_table(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        ports, _, _ = replay(built, lines)

        # Assert
        control = [value for _, port, value in ports.writes if port == CONTROL_PORT]
        assert [console.TABLE_REGISTER[console.BACK_TABLE_BASE], 0x82] == control[2:4]

    def test_payload_bytes_keep_the_active_display_floor(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        ports, _, _ = replay(built, lines)

        # Assert
        stamps = [cycle for cycle, port, _ in ports.writes if port == DATA_PORT]
        assert (
            min(after - before for before, after in pairwise(stamps[: len(PAYLOAD)]))
            >= ACTIVE_FLOOR
        )

    def test_palette_bytes_keep_the_blanking_floor(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        ports, _, _ = replay(built, lines)

        # Assert
        stamps = [cycle for cycle, port, _ in ports.writes if port == DATA_PORT]
        assert (
            min(after - before for before, after in pairwise(stamps[len(PAYLOAD) :])) >= BLANK_FLOOR
        )

    def test_the_frame_completes(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        _, memory, names = replay(built, lines)

        # Assert
        assert memory.read8(names["_movie_kind"]) == stream.END_FRAME


class TestControlPortSpacing:
    def test_every_control_write_keeps_the_active_display_floor(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        ports, _, _ = replay(built, lines)

        # Assert
        stamps = control_stamps(ports)
        assert min(after - before for before, after in pairwise(stamps)) >= ACTIVE_FLOOR


class TestTheGuardIsWhatHoldsTheWindow:
    def test_without_the_guard_the_palette_lands_in_the_active_display(self, built):
        # Arrange
        rom, names = built
        unguarded = (without_guard(rom), names)

        # Act
        ports, _, _ = replay(unguarded, [ACTIVE])

        # Assert
        assert ports.data() == list(PAYLOAD) + list(PALETTE)


class TestOutsideTheWindow:
    @pytest.mark.parametrize("line", [ACTIVE, 0x00, 0xBF, 0xE0, LATE, 0xFF])
    def test_the_palette_and_the_flip_wait_for_the_blank(self, built, line):
        # Arrange
        lines = [line]

        # Act
        ports, _, _ = replay(built, lines)

        # Assert
        control = [value for _, port, value in ports.writes if port == CONTROL_PORT]
        assert ports.data() == list(PAYLOAD)
        assert 0x82 not in control

    def test_the_closing_run_is_left_for_the_next_field(self, built):
        # Arrange
        lines = [ACTIVE]

        # Act
        _, memory, names = replay(built, lines)

        # Assert
        assert cursor_of(memory, names) == WINDOW + 4 + len(PAYLOAD)

    def test_a_deferred_field_completes_no_frame(self, built):
        # Arrange
        lines = [ACTIVE]

        # Act
        _, memory, names = replay(built, lines)

        # Assert
        assert memory.read8(names["_movie_kind"]) == stream.END_CHUNK

    def test_a_deferred_field_is_counted(self, built):
        # Arrange
        lines = [ACTIVE]

        # Act
        _, memory, names = replay(built, lines)

        # Assert
        assert word_at(memory, names["_movie_defers"]) == 1

    def test_a_field_inside_the_window_is_not_counted(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        _, memory, names = replay(built, lines)

        # Assert
        assert word_at(memory, names["_movie_defers"]) == 0


class TestACorruptStream:
    @pytest.mark.parametrize("kind", RETIRED_KINDS)
    def test_an_unknown_run_kind_stops_the_replay(self, built, kind):
        # Arrange
        data = bytes([kind, 2, 0, 0x10, 1])

        # Act
        _, memory, names = replay(built, [INSIDE], data=data)

        # Assert
        assert memory.read8(names["_movie_kind"]) == BAD

    @pytest.mark.parametrize("kind", RETIRED_KINDS)
    def test_an_unknown_run_kind_writes_nothing(self, built, kind):
        # Arrange
        data = bytes([kind, 2, 0, 0x10, 1])

        # Act
        ports, _, _ = replay(built, [INSIDE], data=data)

        # Assert
        assert ports.writes == []

    @pytest.mark.parametrize("kind", RETIRED_KINDS)
    def test_an_unknown_run_kind_leaves_the_cursor_on_it(self, built, kind):
        # Arrange
        data = bytes([kind])

        # Act
        _, memory, names = replay(built, [INSIDE], data=data)

        # Assert
        assert cursor_of(memory, names) == WINDOW

    def test_a_bank_marker_past_the_last_bank_stops_the_replay(self, built):
        # Arrange
        data = bytes([stream.NEXT_BANK])

        # Act
        _, memory, names = replay(built, [INSIDE], data=data)

        # Assert
        assert (memory.read8(names["_movie_kind"]), memory.read8(names["_movie_bank"])) == (
            BAD,
            FIRST_BANK,
        )

    def test_a_bank_marker_inside_the_film_moves_on(self, built):
        # Arrange
        data = bytes([stream.NEXT_BANK])

        # Act
        _, memory, names = replay(built, [INSIDE], data=data, banks=2)

        # Assert
        assert memory.read8(names["_movie_bank"]) == FIRST_BANK + 1


OVERLAY_INKS = [0x00, 0x3F]
INK_ADDRESS = [0x1E, 0xC0]


class TestTheOverlayInks:
    def test_with_the_overlay_up_black_and_white_follow_the_palette(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        ports, _, _ = replay(built, lines, inks=True)

        # Assert
        assert ports.data() == list(PAYLOAD) + list(PALETTE) + OVERLAY_INKS

    def test_they_land_on_the_last_two_sprite_palette_entries(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        ports, _, _ = replay(built, lines, inks=True)

        # Assert
        control = [value for _, port, value in ports.writes if port == CONTROL_PORT]
        assert control[-2:] == INK_ADDRESS

    def test_without_the_overlay_nothing_follows_the_palette(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        ports, _, _ = replay(built, lines, inks=False)

        # Assert
        assert ports.data() == list(PAYLOAD) + list(PALETTE)

    def test_a_deferred_field_writes_no_inks(self, built):
        # Arrange
        lines = [ACTIVE]

        # Act
        ports, _, _ = replay(built, lines, inks=True)

        # Assert
        assert ports.data() == list(PAYLOAD)

    def test_every_write_after_the_palette_keeps_the_active_display_floor(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        ports, _, _ = replay(built, lines, inks=True)

        # Assert
        stamps = [cycle for cycle, port, _ in ports.writes if port in (DATA_PORT, CONTROL_PORT)]
        after = stamps[len(stamps) - len(OVERLAY_INKS) - len(INK_ADDRESS) - 1 :]
        assert min(later - earlier for earlier, later in pairwise(after)) >= ACTIVE_FLOOR

    def test_the_frame_still_completes(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        _, memory, names = replay(built, lines, inks=True)

        # Assert
        assert memory.read8(names["_movie_kind"]) == stream.END_FRAME


PSG_ATTENUATE_ALL = [0x9F, 0xBF, 0xDF, 0xFF]


class Speaker:
    def __init__(self) -> None:
        self.writes: list[tuple[int, int]] = []

    def read(self, _address: int) -> int:
        return 0xFF

    def write(self, address: int, value: int) -> None:
        self.writes.append((address & 0xFF, value))


def silence(built) -> Speaker:
    rom, names = built
    image = bytearray(0x10000)
    image[:WINDOW] = rom[:WINDOW]
    image[RETURN] = HALT
    image[STACK] = RETURN & 0xFF
    image[STACK + 1] = RETURN >> 8
    speaker = Speaker()
    cpu = Cpu("z80", Memory(image=bytes(image)), ports=speaker)
    cpu.reset()
    cpu.registers.pc = names["_fmv_psg_silence"]
    cpu.registers.sp = STACK
    for _ in range(STEP_LIMIT):
        if cpu.halted:
            break
        cpu.step()
    return speaker


class TestTheSoundChipIsSilenced:
    def test_every_channel_is_attenuated_fully_on_the_psg_port(self, built):
        # Arrange
        expected = [(SOUND_PORT, value) for value in PSG_ATTENUATE_ALL]

        # Act
        speaker = silence(built)

        # Assert
        assert speaker.writes == expected


ASSERT_STEPS = 5_000
ASSERT_LINE = 42
ASSERT_COLOUR = 0x32
BACKDROP_ENTRY = 0x10
CRAM_COMMAND = 0xC0
BANK_END = 0xC000


def run_until_halted(built, entry: str, *, pokes: dict[str, int], hl: int = 0) -> Speaker:
    rom, names = built
    image = bytearray(0x10000)
    image[:WINDOW] = rom[:WINDOW]
    for name, value in pokes.items():
        image[names[name]] = value & 0xFF
        image[names[name] + 1] = value >> 8
    speaker = Speaker()
    cpu = Cpu("z80", Memory(image=bytes(image)), ports=speaker)
    cpu.reset()
    cpu.registers.pc = names[entry]
    cpu.registers.sp = STACK
    cpu.registers.hl = hl
    for _ in range(ASSERT_STEPS):
        cpu.step()
    return speaker


def palette_writes(speaker: Speaker) -> list[tuple[int, int]]:
    found: list[tuple[int, int]] = []
    control: list[int] = []
    for port, value in speaker.writes:
        if port == CONTROL_PORT:
            control = [*control, value]
            continue
        if port == DATA_PORT and len(control) >= 2 and control[-1] == CRAM_COMMAND:
            found = [*found, (control[-2], value)]
    return found


class TestAnAssertionHalt:
    def test_the_halt_colour_lands_on_the_backdrop_entry(self, built):
        # Arrange
        expected = (BACKDROP_ENTRY, ASSERT_COLOUR)

        # Act
        speaker = run_until_halted(built, "_fmv_assert_fail", pokes={}, hl=ASSERT_LINE)

        # Assert
        assert palette_writes(speaker)[0] == expected

    def test_a_cursor_past_the_bank_window_halts_before_the_replay(self, built):
        # Arrange
        pokes = {"_movie_cursor": BANK_END, "_movie_bank": FIRST_BANK}

        # Act
        speaker = run_until_halted(built, "_fmv_movie_chunk", pokes=pokes)

        # Assert
        assert [entry for entry, _ in palette_writes(speaker)][:1] == [BACKDROP_ENTRY]


VERSION_HEADER = ROOT / "include" / "fmv" / "version.h"
SDSC_SIGNATURE = 0x7FE0


def bcd(value: int) -> int:
    return (value // 10) * 16 + value % 10


class TestTheRomHeader:
    def test_the_sdsc_version_is_the_one_the_release_stamps(self, built):
        # Arrange
        rom, _ = built
        declared = re.search(r'#define FMV_VERSION "(\d+)\.(\d+)\.\d+"', VERSION_HEADER.read_text())

        # Act
        stamped = rom[SDSC_SIGNATURE : SDSC_SIGNATURE + 6]

        # Assert
        assert declared is not None
        assert stamped == b"SDSC" + bytes([bcd(int(declared[1])), bcd(int(declared[2]))])


def sounded_film() -> bytes:
    return stream.psg_run(SOUND_WRITES) + film()


class TestASoundRun:
    def test_the_writes_reach_the_sound_port_in_order(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        ports, _, _ = replay(built, lines, data=sounded_film())

        # Assert
        assert [value for _, value in ports.sound()] == list(SOUND_WRITES)

    def test_consecutive_sound_writes_keep_the_floor(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        ports, _, _ = replay(built, lines, data=sounded_film())

        # Assert
        stamps = [cycle for cycle, _ in ports.sound()]
        assert min(later - earlier for earlier, later in pairwise(stamps)) >= SOUND_FLOOR

    def test_the_picture_after_the_sound_still_arrives(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        ports, _, _ = replay(built, lines, data=sounded_film())

        # Assert
        assert ports.data()[: len(PAYLOAD)] == list(PAYLOAD)


class TestAMutedSoundRun:
    def test_nothing_reaches_the_sound_port(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        ports, _, _ = replay(built, lines, data=sounded_film(), muted=True)

        # Assert
        assert ports.sound() == []

    def test_the_picture_after_the_skipped_run_still_arrives(self, built):
        # Arrange
        lines = [INSIDE]

        # Act
        ports, _, _ = replay(built, lines, data=sounded_film(), muted=True)

        # Assert
        assert ports.data() == list(PAYLOAD) + list(PALETTE)


class TestAPanRunOnTheMasterSystem:
    def test_it_is_refused_as_a_kind_the_player_does_not_know(self, built):
        # Arrange
        lines = [INSIDE]
        data = bytes([stream.PAN, 0xEF, stream.END_FRAME])

        # Act
        ports, memory, names = replay(built, lines, data=data)

        # Assert
        assert (memory.read8(names["_movie_kind"]), ports.pans()) == (BAD, [])

    def test_silencing_the_psg_never_writes_the_memory_control_mirror(self, built):
        # Arrange
        routine = "_fmv_psg_silence"

        # Act
        vdp, _, _ = call(built, routine)

        # Assert
        assert vdp.pans == []
