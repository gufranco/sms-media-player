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
LOWEST_HEARD_HZ: Final = 40.0
MAX_HZ: Final = 4000.0
NOISE_LOW_HZ: Final = 4000.0
NOISE_HIGH_HZ: Final = 10000.0
WINDOW: Final = 2048
HANN_GAIN: Final = WINDOW / 4
PEAK_REACH: Final = 3
SEMITONE: Final = 2 ** (1 / 12)
TRACK_REACH: Final = SEMITONE**1.5
HOLD_RATIO: Final = 0.006
LOWEST_HARMONIC: Final = 2
HIGHEST_HARMONIC: Final = 8
HARMONIC_TOLERANCE: Final = 0.03
DB_PER_STEP: Final = 2.0
MUTE: Final = 15
LEVEL_SECONDS: Final = 8.0
LEVEL_FLOOR: Final = 0.05
VOICE_GAIN: Final = 1.2
NOISE_GAIN: Final = 2.0
LATCH: Final = 0x80
VOLUME: Final = 0x10
LOW_NIBBLE: Final = 0x0F
HIGH_BITS: Final = 0x3F
CHANNEL_SHIFT: Final = 5
NOISE_WHITE_FAST: Final = 0xE4
MAX_FIELD_WRITES: Final = 1 + (TONE_CHANNELS * 3) + 1
DECODE_RATE: Final = 22050
REFRESH_FIELDS: Final = 60

Spectrum = npt.NDArray[np.float64]
Tone = tuple[float, float]


@dataclass(frozen=True, slots=True)
class Voice:
    divider: int
    attenuation: int


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
    wave = samples.astype(np.float64)
    spectra = [_spectrum(wave, rate, field) for field in range(fields)]
    frequencies = np.fft.rfftfreq(WINDOW, 1.0 / rate)
    levels = _levels(wave, rate, fields)
    voices = _voices(spectra, frequencies, levels)
    hiss = (frequencies >= NOISE_LOW_HZ) & (frequencies <= NOISE_HIGH_HZ)
    noise = [_noise(s, hiss, level) for s, level in zip(spectra, levels, strict=True)]
    return _changes(voices, noise)


def _spectrum(wave: npt.NDArray[np.float64], rate: int, field: int) -> Spectrum:
    first = round((field + 0.5) * rate / console.NTSC_FIELD_HZ) - WINDOW // 2
    low, high = max(0, first), min(wave.shape[0], first + WINDOW)
    segment = np.zeros(WINDOW, dtype=np.float64)
    if high > low:
        segment[low - first : high - first] = wave[low:high]
    return np.abs(np.fft.rfft(segment * np.hanning(WINDOW))) / HANN_GAIN


def _levels(wave: npt.NDArray[np.float64], rate: int, fields: int) -> list[float]:
    step = rate / console.NTSC_FIELD_HZ
    loudness = [_rms(wave[int(f * step) : int((f + 1) * step)]) for f in range(fields)]
    peak = max(loudness)
    if peak == 0.0:
        return [0.0] * fields
    reach = round(LEVEL_SECONDS * console.NTSC_FIELD_HZ)
    near = [max(loudness[max(0, f - reach) : f + reach + 1]) for f in range(fields)]
    return [loud / max(top, peak * LEVEL_FLOOR) for loud, top in zip(loudness, near, strict=True)]


def _rms(piece: npt.NDArray[np.float64]) -> float:
    return float(np.sqrt(np.mean(piece**2))) if piece.shape[0] else 0.0


def _attenuation(amplitude: float) -> int:
    if amplitude <= 0.0:
        return MUTE
    level = 20.0 * np.log10(min(1.0, amplitude))
    return int(min(MUTE, max(0, round(-level / DB_PER_STEP))))


def _voices(
    spectra: list[Spectrum], frequencies: Spectrum, levels: list[float]
) -> list[list[Voice]]:
    held: list[float | None] = [None] * TONE_CHANNELS
    out: list[list[Voice]] = []
    for spectrum, level in zip(spectra, levels, strict=True):
        tones = _tones(spectrum, frequencies)
        total = sum(magnitude for _, magnitude in tones) or 1.0
        slots = _assign(held, tones)
        row = [_voice(slot, before, level, total) for slot, before in zip(slots, held, strict=True)]
        held = [hz for _, hz in row]
        out = [*out, [voice for voice, _ in row]]
    return out


def _voice(
    tone: Tone | None, before: float | None, level: float, total: float
) -> tuple[Voice, float | None]:
    silent = (Voice(MAX_DIVIDER, MUTE), None)
    if tone is None:
        return silent
    hz, magnitude = tone
    attenuation = _attenuation(level * float(np.sqrt(magnitude / total)) * VOICE_GAIN)
    if attenuation == MUTE:
        return silent
    kept = before if before is not None and abs(hz / before - 1.0) < HOLD_RATIO else hz
    divider = int(min(MAX_DIVIDER, max(1, round(PSG_CLOCK_HZ / (TONE_DIVISOR * kept)))))
    return Voice(divider, attenuation), kept


def _tones(spectrum: Spectrum, frequencies: Spectrum) -> list[Tone]:
    chosen: list[Tone] = []
    for index in _peaks(spectrum, frequencies):
        hz = _refined(spectrum, frequencies, index)
        if any(_interval(hz, other) < SEMITONE or _is_harmonic(hz, other) for other, _ in chosen):
            continue
        chosen = [*chosen, (hz, float(spectrum[index]))]
        if len(chosen) == TONE_CHANNELS:
            break
    return chosen


def _is_harmonic(hz: float, fundamental: float) -> bool:
    ratio = hz / fundamental
    order = round(ratio)
    return (
        LOWEST_HARMONIC <= order <= HIGHEST_HARMONIC
        and abs(ratio - order) < HARMONIC_TOLERANCE * order
    )


def _assign(held: list[float | None], tones: list[Tone]) -> list[Tone | None]:
    slots: list[Tone | None] = [None] * TONE_CHANNELS
    left = list(tones)
    for channel, before in enumerate(held):
        if before is None:
            continue
        near = [tone for tone in left if _interval(tone[0], before) < TRACK_REACH]
        if near:
            match = min(near, key=lambda tone: _interval(tone[0], before))
            slots[channel] = match
            left = [tone for tone in left if tone is not match]
    for channel in range(TONE_CHANNELS):
        if slots[channel] is None and left:
            slots[channel], left = left[0], left[1:]
    return slots


def _interval(one: float, other: float) -> float:
    return max(one, other) / min(one, other)


def _peaks(spectrum: Spectrum, frequencies: Spectrum) -> list[int]:
    band = np.flatnonzero((frequencies >= LOWEST_HEARD_HZ) & (frequencies <= MAX_HZ))
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


def _noise(spectrum: Spectrum, hiss: npt.NDArray[np.bool_], level: float) -> int:
    whole = float(np.sqrt(np.sum(spectrum**2)))
    if whole == 0.0:
        return MUTE
    share = float(np.sqrt(np.sum(spectrum[hiss] ** 2))) / whole
    return _attenuation(level * share * NOISE_GAIN)


def _changes(voices: list[list[Voice]], noise: list[int]) -> list[bytes]:
    previous: list[Voice | None] = [None] * TONE_CHANNELS
    previous_noise: int | None = None
    out: list[bytes] = []
    for field, (current, hiss) in enumerate(zip(voices, noise, strict=True)):
        refresh = field % REFRESH_FIELDS == 0
        if refresh:
            previous = [None] * TONE_CHANNELS
            previous_noise = None
        written = bytearray([NOISE_WHITE_FAST]) if refresh else bytearray()
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
