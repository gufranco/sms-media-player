from __future__ import annotations

import pytest
from z80 import Cpu, Memory

from smsggmedia import console, stream

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

ACTIVE_FLOOR = 29

BLANK_FLOOR = 16

GUARD = bytes([0xDB, V_COUNTER, 0xFE, 0xC0, 0x38])

GUARD_BRANCHES = (4, 8)

NOP = 0x00


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


OVERLAY_INKS = [0x00, 0x3F]

INK_ADDRESS = [0x1E, 0xC0]

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


def sounded_film() -> bytes:
    return stream.psg_run(SOUND_WRITES) + film()
