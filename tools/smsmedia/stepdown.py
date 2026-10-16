from __future__ import annotations

import functools
from collections.abc import Callable
from dataclasses import dataclass

from fmvcore import ladder

from smsmedia import rate


@dataclass(frozen=True, slots=True)
class Rung:
    fps: float
    silent: bool


def rungs(settled_fps: float, *, sound: bool) -> list[Rung]:
    slower = [fps for fps in rate.DEFAULT_RATE_CANDIDATES if fps < settled_fps]
    if not slower:
        return [Rung(fps=settled_fps, silent=True)] if sound else []
    voiced = [Rung(fps=fps, silent=not sound) for fps in slower]
    return [*voiced, Rung(fps=slower[-1], silent=True)] if sound else voiced


def search[Result](
    steps: list[Rung],
    attempt: Callable[[Rung], Result],
    fits: Callable[[Result], bool],
) -> tuple[Rung, Result] | None:
    @functools.cache
    def tried(index: int) -> Result:
        return attempt(steps[index])

    found = ladder.first_fit(len(steps), lambda index: fits(tried(index)))
    return None if found is None else (steps[found], tried(found))
