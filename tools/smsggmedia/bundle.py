from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from fmvcore import bundle

from smsggmedia import target as targets

ROOT: Final = Path(__file__).resolve().parents[2]
TEMPLATES: Final = Path(__file__).resolve().parent / "templates"
LIBRARY_SOURCES: Final = (
    "replay.s",
    "psg.s",
    "vdp.s",
    "mediaplayer.c",
    "screen.c",
    "assert.c",
    "seek.c",
)
LIBRARY_HEADERS: Final = (
    "types.h",
    "mediaplayer.h",
    "seek.h",
    "psg.h",
    "screen.h",
    "assert.h",
    "console.h",
)
MAKEFILE: Final = "fmv.mk"
TARGET_INCLUDE: Final = "target.inc"
TARGET_MAKEFILE: Final = "target.mk"
LIBRARIES: Final = {
    targets.MASTER_SYSTEM.name: "SMSlib.lib",
    targets.GAME_GEAR.name: "SMSlib_GG.lib",
}
GUIDE: Final = "README.md"
GUIDE_TEMPLATE: Final = "bundle_readme.md"
FILM: Final = "movie.bin"
HEADER: Final = "movie.h"
VERSION_HEADER: Final = ROOT / "include" / "fmv" / "version.h"
VERSION_LINE: Final = re.compile(r'#define FMV_VERSION "([^"]+)"')


@dataclass(frozen=True, slots=True)
class Figures:
    seconds: float
    frames: int
    fields: int
    banks: int
    columns: int
    rows: int
    keys: int
    sound: bool


def write(
    *,
    target: Path,
    assets: Path,
    generated: Path,
    figures: Figures,
    system: targets.Target = targets.DEFAULT,
) -> Path:
    bundle.copy_files(LIBRARY_SOURCES, ROOT / "src", target / "src", required=True)
    bundle.copy_files((TARGET_INCLUDE,), ROOT / "src" / system.name, target / "src", required=True)
    bundle.copy_files(
        LIBRARY_HEADERS, ROOT / "include" / "fmv", target / "include" / "fmv", required=True
    )
    bundle.copy_files((HEADER,), generated, target / "movie", required=True)
    bundle.copy_files((FILM,), assets, target / "movie" / "assets", required=True)
    bundle.copy_files((MAKEFILE,), TEMPLATES, target, required=True)
    (target / TARGET_MAKEFILE).write_text(f"FMV_TARGET := {system.name}\n", encoding="utf-8")
    guide = target / GUIDE
    fields = _fields(figures, system)
    guide.write_text(bundle.render(TEMPLATES / GUIDE_TEMPLATE, fields), encoding="utf-8")
    return guide


def _fields(figures: Figures, system: targets.Target) -> dict[str, object]:
    return {
        "console": system.console,
        "library": LIBRARIES[system.name],
        "seconds": f"{figures.seconds:.1f}",
        "frames": figures.frames,
        "fields": figures.fields,
        "banks": figures.banks,
        "columns": figures.columns,
        "rows": figures.rows,
        "keys": figures.keys,
        "sound": "on" if figures.sound else "off",
        "version": version(),
    }


def version(header: Path = VERSION_HEADER) -> str:
    found = VERSION_LINE.search(header.read_text(encoding="utf-8"))
    if found is None:
        msg = f"{header} does not define FMV_VERSION"
        raise ValueError(msg)
    return found.group(1)
