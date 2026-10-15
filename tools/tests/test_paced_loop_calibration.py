from __future__ import annotations

from itertools import pairwise

from z80 import Cpu, Memory

VDP_DATA_PORT = 0xBE
MINIMUM_INTERVAL = 29
BRANCH_COST = 10
PAD_COST = 4

ORIGIN = 0x8000
SOURCE = 0x9000
RUN_LENGTH = 8

load_source_pointer = (0x21, SOURCE & 0xFF, SOURCE >> 8)
select_vdp_data_port = (0x0E, VDP_DATA_PORT)
load_byte_count = (0x06, RUN_LENGTH)
output_and_advance = (0xED, 0xA3)
pad = (0x00,)
halt = (0x76,)

_preamble = load_source_pointer + select_vdp_data_port + load_byte_count
_first_output = ORIGIN + len(_preamble)
branch_back_while_more = (0xC2, _first_output & 0xFF, _first_output >> 8)

PACED = bytes(_preamble + output_and_advance + pad + branch_back_while_more + halt)
UNPADDED = bytes(_preamble + output_and_advance + branch_back_while_more + halt)
UNROLLED = bytes(_preamble + output_and_advance * RUN_LENGTH + halt)

STEP_LIMIT = 4000
OPEN_BUS = 0xFF


class _Recorder:
    def __init__(self) -> None:
        self.writes: list[tuple[int, int]] = []
        self.clock: Cpu | None = None

    @property
    def stamps(self) -> list[int]:
        return [cycle for cycle, _ in self.writes]

    @property
    def bytes_written(self) -> list[int]:
        return [value for _, value in self.writes]

    def read(self, _address: int) -> int:
        return OPEN_BUS

    def write(self, address: int, value: int) -> None:
        if address & 0xFF == VDP_DATA_PORT and self.clock is not None:
            self.writes.append((self.clock.cycles, value))


def record(program: bytes) -> _Recorder:
    image = bytearray(0x10000)
    image[ORIGIN : ORIGIN + len(program)] = program
    for offset in range(RUN_LENGTH):
        image[SOURCE + offset] = 0xA0 + offset

    recorder = _Recorder()
    cpu = Cpu("z80", Memory(image=bytes(image)), ports=recorder)
    cpu.reset()
    cpu.registers.pc = ORIGIN
    recorder.clock = cpu

    for _ in range(STEP_LIMIT):
        if cpu.halted:
            break
        cpu.step()

    return recorder


def intervals(program: bytes) -> list[int]:
    stamps = record(program).stamps
    return [after - before for before, after in pairwise(stamps)]


class TestUploadLoopPacing:
    def test_the_paced_loop_reaches_the_vdp(self):
        # Arrange
        program = PACED

        # Act
        gaps = intervals(program)

        # Assert
        assert len(gaps) >= RUN_LENGTH - 2

    def test_the_paced_loop_clears_the_vdp_minimum(self):
        # Arrange
        program = PACED

        # Act
        gaps = intervals(program)

        # Assert
        assert min(gaps) >= MINIMUM_INTERVAL

    def test_the_unrolled_loop_is_rejected(self):
        # Arrange
        program = UNROLLED

        # Act
        gaps = intervals(program)

        # Assert
        assert min(gaps) < MINIMUM_INTERVAL

    def test_the_paced_loop_sends_the_source_bytes_in_order(self):
        # Arrange
        expected = [0xA0 + offset for offset in range(RUN_LENGTH)]

        # Act
        recorder = record(PACED)

        # Assert
        assert recorder.bytes_written == expected

    def test_the_branch_and_the_pad_are_what_separate_them(self):
        # Arrange
        unrolled = min(intervals(UNROLLED))

        # Act
        paced = min(intervals(PACED))

        # Assert
        assert paced - unrolled == BRANCH_COST + PAD_COST

    def test_the_loop_without_the_pad_is_below_the_documented_floor(self):
        # Arrange
        program = UNPADDED

        # Act
        gaps = intervals(program)

        # Assert
        assert max(gaps) < MINIMUM_INTERVAL
