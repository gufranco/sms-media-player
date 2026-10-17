from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final

import numpy as np
import numpy.typing as npt

from smsmedia import psgsound

STEREO: Final = 2
CHANNELS: Final = psgsound.TONE_CHANNELS + 1
LEFT_SHIFT: Final = 4
BOTH_SIDES: Final = 0xFF
SIDE_SHARE: Final = 0.8
BIN_REACH: Final = 1
CHANNEL_BITS: Final = 0x03
DATA_SHIFT: Final = 4
NOISE_SOUNDING: Final = 0
PAN_HOLD: Final = 6

Route = tuple[bool, bool]
Tones = tuple[int | None, ...]


@dataclass(frozen=True, slots=True)
class Registers:
    low: tuple[int, ...] = (0,) * psgsound.TONE_CHANNELS
    high: tuple[int, ...] = (0,) * psgsound.TONE_CHANNELS
    muted: tuple[bool, ...] = (True,) * CHANNELS
    latched: int | None = None

    def tones(self) -> Tones:
        voices = tuple(
            None if self.muted[c] else self.low[c] | (self.high[c] << DATA_SHIFT)
            for c in range(psgsound.TONE_CHANNELS)
        )
        return (*voices, None if self.muted[psgsound.NOISE_CHANNEL] else NOISE_SOUNDING)


def pans(stereo: npt.NDArray[np.float32], *, rate: int, writes: list[bytes]) -> list[int | None]:
    if stereo.ndim != STEREO or stereo.shape[1] != STEREO:
        msg = f"stereo samples need a left and a right column, got shape {stereo.shape}"
        raise ValueError(msg)
    left, right = (stereo[:, side].astype(np.float64) for side in range(STEREO))
    frequencies = np.fft.rfftfreq(psgsound.WINDOW, 1.0 / rate)
    hiss = (frequencies >= psgsound.NOISE_LOW_HZ) & (frequencies <= psgsound.NOISE_HIGH_HZ)
    wanted = [
        _wanted(
            (psgsound.field_spectrum(left, rate, f), psgsound.field_spectrum(right, rate, f)),
            tones,
            frequencies=frequencies,
            hiss=hiss,
        )
        for f, tones in enumerate(sounding(writes))
    ]
    return _written(held(wanted))


def held(wanted: list[int]) -> list[int]:
    out: list[int] = []
    current = BOTH_SIDES
    for field in range(len(wanted)):
        recent = wanted[max(0, field - PAN_HOLD + 1) : field + 1]
        steady = len(recent) == PAN_HOLD and len(set(recent)) == 1
        current = recent[0] if steady else current
        out = [*out, current]
    return out


def _written(routing: list[int]) -> list[int | None]:
    return [
        value if field % psgsound.REFRESH_FIELDS == 0 or value != routing[field - 1] else None
        for field, value in enumerate(routing)
    ]


def _wanted(
    spectra: tuple[psgsound.Spectrum, psgsound.Spectrum],
    tones: Tones,
    *,
    frequencies: npt.NDArray[np.float64],
    hiss: npt.NDArray[np.bool_],
) -> int:
    *voices, noise = tones
    masks = [_tone_mask(frequencies, divider) for divider in voices]
    return pack([_route(spectra, mask) for mask in [*masks, None if noise is None else hiss]])


def pack(routes: list[Route]) -> int:
    if len(routes) != CHANNELS:
        msg = f"a pan routes {CHANNELS} channels, got {len(routes)}"
        raise ValueError(msg)
    bits = [
        (int(left) << (channel + LEFT_SHIFT)) | (int(right) << channel)
        for channel, (left, right) in enumerate(routes)
    ]
    return sum(bits)


def sounding(writes: list[bytes]) -> list[Tones]:
    state = Registers()
    out: list[Tones] = []
    for field in writes:
        for byte in field:
            state = apply(state, byte)
        out = [*out, state.tones()]
    return out


def apply(state: Registers, byte: int) -> Registers:
    if not byte & psgsound.LATCH:
        if state.latched is None:
            return state
        high = _with(state.high, state.latched, byte & psgsound.HIGH_BITS)
        return replace(state, high=high)
    channel = (byte >> psgsound.CHANNEL_SHIFT) & CHANNEL_BITS
    if byte & psgsound.VOLUME:
        silent = (byte & psgsound.LOW_NIBBLE) == psgsound.MUTE
        return replace(state, muted=_with(state.muted, channel, silent), latched=None)
    if channel == psgsound.NOISE_CHANNEL:
        return replace(state, latched=None)
    low = _with(state.low, channel, byte & psgsound.LOW_NIBBLE)
    return replace(state, low=low, latched=channel)


def _with[T](values: tuple[T, ...], index: int, value: T) -> tuple[T, ...]:
    return (*values[:index], value, *values[index + 1 :])


def _tone_mask(
    frequencies: npt.NDArray[np.float64], divider: int | None
) -> npt.NDArray[np.bool_] | None:
    if divider is None:
        return None
    hz = psgsound.PSG_CLOCK_HZ / (psgsound.TONE_DIVISOR * max(divider, 1))
    centre = int(np.argmin(np.abs(frequencies - hz)))
    distance = np.abs(np.arange(frequencies.shape[0]) - centre)
    return np.asarray(distance <= BIN_REACH)


def _route(
    spectra: tuple[psgsound.Spectrum, psgsound.Spectrum], mask: npt.NDArray[np.bool_] | None
) -> Route:
    if mask is None:
        return True, True
    left = float(np.sum(spectra[0][mask] ** 2))
    right = float(np.sum(spectra[1][mask] ** 2))
    total = left + right
    if total == 0.0:
        return True, True
    share = left / total
    return share > 1.0 - SIDE_SHARE, share < SIDE_SHARE
