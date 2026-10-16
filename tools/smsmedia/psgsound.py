from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import numpy.typing as npt
from fmvcore import ffmpeg

from smsmedia import console

PSG_CLOCK_HZ: Final = console.NTSC_CPU_HZ
TONE_DIVISOR: Final = 32
TONE_CHANNELS: Final = 3
NOISE_CHANNEL: Final = 3
MAX_DIVIDER: Final = 1023
MIN_HZ: Final = PSG_CLOCK_HZ / (TONE_DIVISOR * MAX_DIVIDER)
MAX_HZ: Final = 4000.0
NOISE_LOW_HZ: Final = 4000.0
NOISE_HIGH_HZ: Final = 10000.0
WINDOW: Final = 2048
PEAK_REACH: Final = 3
SEMITONE: Final = 2 ** (1 / 12)
DB_PER_STEP: Final = 2.0
MUTE: Final = 15
QUIETEST_DB: Final = -24.0
LATCH: Final = 0x80
VOLUME: Final = 0x10
LOW_NIBBLE: Final = 0x0F
HIGH_BITS: Final = 0x3F
CHANNEL_SHIFT: Final = 5
NOISE_WHITE_FAST: Final = 0xE4
MAX_FIELD_WRITES: Final = 1 + (TONE_CHANNELS * 3) + 1
DECODE_RATE: Final = 22050

Spectrum = npt.NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class Voice:
    divider: int
    attenuation: int


def has_audio(path: Path) -> bool:
    command = [
        ffmpeg.require_tool("ffprobe"),
        "-v",
        "error",
        "-select_streams",
        "a",
        "-show_entries",
        "stream=index",
        "-of",
        "csv=p=0",
        str(path),
    ]
    done = subprocess.run(command, capture_output=True, text=True, check=True)
    return bool(done.stdout.strip())


def decode(
    path: Path, *, start: float, duration: float | None, rate: int = DECODE_RATE
) -> npt.NDArray[np.float32]:
    window = ["-t", str(duration)] if duration is not None else []
    command = [
        ffmpeg.require_tool("ffmpeg"),
        "-v",
        "error",
        "-ss",
        str(start),
        *window,
        "-i",
        str(path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(rate),
        "-f",
        "f32le",
        "-",
    ]
    done = subprocess.run(command, capture_output=True, check=True)
    return np.frombuffer(done.stdout, dtype=np.float32)


def synthesize(samples: npt.NDArray[np.float32], *, rate: int, fields: int) -> list[bytes]:
    if fields < 1:
        msg = "a film needs at least one field of sound"
        raise ValueError(msg)
    spectra = [_spectrum(samples, rate, field) for field in range(fields)]
    reference = max((float(s.max()) for s in spectra), default=0.0) or 1.0
    frequencies = np.fft.rfftfreq(WINDOW, 1.0 / rate)
    voices = [_voices(s, frequencies, reference) for s in spectra]
    noise = [_noise(s, frequencies, reference) for s in spectra]
    return _changes(voices, noise)


def _spectrum(samples: npt.NDArray[np.float32], rate: int, field: int) -> Spectrum:
    start = round(field * rate / console.NTSC_FIELD_HZ)
    segment = np.zeros(WINDOW, dtype=np.float64)
    piece = samples[start : start + WINDOW]
    segment[: piece.shape[0]] = piece
    return np.abs(np.fft.rfft(segment * np.hanning(WINDOW)))


def _attenuation(magnitude: float, reference: float) -> int:
    if magnitude <= 0.0:
        return MUTE
    level = 20.0 * np.log10(magnitude / reference)
    if level < QUIETEST_DB:
        return MUTE
    return int(min(MUTE, max(0, round(-level / DB_PER_STEP))))


def _voices(spectrum: Spectrum, frequencies: Spectrum, reference: float) -> list[Voice]:
    chosen: list[float] = []
    voices: list[Voice] = []
    for index in _peaks(spectrum, frequencies):
        hz = _refined(spectrum, frequencies, index)
        attenuation = _attenuation(float(spectrum[index]), reference)
        if attenuation == MUTE:
            break
        if any(max(hz, other) / min(hz, other) < SEMITONE for other in chosen):
            continue
        chosen = [*chosen, hz]
        divider = int(min(MAX_DIVIDER, max(1, round(PSG_CLOCK_HZ / (TONE_DIVISOR * hz)))))
        voices = [*voices, Voice(divider, attenuation)]
        if len(voices) == TONE_CHANNELS:
            break
    silent = Voice(MAX_DIVIDER, MUTE)
    return [*voices, *([silent] * (TONE_CHANNELS - len(voices)))]


def _peaks(spectrum: Spectrum, frequencies: Spectrum) -> list[int]:
    band = np.flatnonzero((frequencies >= MIN_HZ) & (frequencies <= MAX_HZ))
    found = [
        int(i)
        for i in band
        if spectrum[i] > 0.0
        and spectrum[i] == spectrum[max(0, i - PEAK_REACH) : i + PEAK_REACH + 1].max()
    ]
    return sorted(found, key=lambda i: -spectrum[i])


def _refined(spectrum: Spectrum, frequencies: Spectrum, index: int) -> float:
    left, centre, right = (float(spectrum[index + step]) for step in (-1, 0, 1))
    bend = left - 2.0 * centre + right
    shift = 0.0 if bend == 0.0 else 0.5 * (left - right) / bend
    return float(frequencies[index] + shift * (frequencies[1] - frequencies[0]))


def _noise(spectrum: Spectrum, frequencies: Spectrum, reference: float) -> int:
    band = (frequencies >= NOISE_LOW_HZ) & (frequencies <= NOISE_HIGH_HZ)
    return _attenuation(float(spectrum[band].max()) if band.any() else 0.0, reference)


def _changes(voices: list[list[Voice]], noise: list[int]) -> list[bytes]:
    previous: list[Voice | None] = [None] * TONE_CHANNELS
    previous_noise: int | None = None
    out: list[bytes] = []
    for field, (current, hiss) in enumerate(zip(voices, noise, strict=True)):
        written = bytearray([NOISE_WHITE_FAST]) if field == 0 else bytearray()
        for channel, voice in enumerate(current):
            written += _voice_bytes(channel, voice, previous[channel])
        if hiss != previous_noise:
            written.append(LATCH | (NOISE_CHANNEL << CHANNEL_SHIFT) | VOLUME | hiss)
        previous = list(current)
        previous_noise = hiss
        out = [*out, bytes(written)]
    return out


def _voice_bytes(channel: int, voice: Voice, before: Voice | None) -> bytes:
    head = LATCH | (channel << CHANNEL_SHIFT)
    written = bytearray()
    retune = voice.attenuation != MUTE and (before is None or voice.divider != before.divider)
    if retune:
        written += bytes([head | (voice.divider & LOW_NIBBLE), (voice.divider >> 4) & HIGH_BITS])
    if before is None or voice.attenuation != before.attenuation:
        written.append(head | VOLUME | voice.attenuation)
    return bytes(written)
