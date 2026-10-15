from __future__ import annotations

import argparse
import math
from collections.abc import Callable
from typing import Final

AUTO: Final = "auto"


def finite(text: str, *, low: float, high: float, name: str) -> float:
    try:
        value = float(text)
    except ValueError:
        msg = f"{name} must be a number, got {text!r}"
        raise argparse.ArgumentTypeError(msg) from None
    if not math.isfinite(value) or not low <= value <= high:
        msg = f"{name} must lie between {low:g} and {high:g}, got {text}"
        raise argparse.ArgumentTypeError(msg)
    return value


def whole(text: str, *, low: int, high: int, name: str) -> int:
    try:
        value = int(text)
    except ValueError:
        msg = f"{name} must be a whole number, got {text!r}"
        raise argparse.ArgumentTypeError(msg) from None
    if not low <= value <= high:
        msg = f"{name} must lie between {low} and {high}, got {value}"
        raise argparse.ArgumentTypeError(msg)
    return value


def number(*, low: float, high: float, name: str) -> Callable[[str], float]:
    return lambda text: finite(text, low=low, high=high, name=name)


def count(*, low: int, high: int, name: str) -> Callable[[str], int]:
    return lambda text: whole(text, low=low, high=high, name=name)


def number_or_auto(*, low: float, high: float, name: str) -> Callable[[str], str]:
    def check(text: str) -> str:
        if text != AUTO:
            finite(text, low=low, high=high, name=name)
        return text

    return check
