from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from fmvcore import clips as core

from smsggmedia import limits

ROOT: Final = Path(__file__).resolve().parents[2]
MANIFEST: Final = ROOT / "tools" / "clips.manifest.json"
DIRECTORY_ENV: Final = "SMSGGMEDIA_CLIPS_DIR"
REQUIRE_ENV: Final = "SMSGGMEDIA_CLIPS_REQUIRED"
BANK_CEILING: Final = limits.DEFAULT_MAX_BANKS
OPENING_SECONDS: Final = 5.0
FETCH_COMMAND: Final = "uv --project tools run python tools/scripts/fetch_clips.py"


@dataclass(frozen=True, slots=True)
class Clip:
    key: str
    content: str
    title: str
    credit: str
    license: str
    license_url: str
    source: str
    url: str | None
    file: str
    committed: bool
    start: float
    duration: float
    fps: float
    denoise: float
    reuse: float
    max_error: float
    max_banks_per_second: float
    bytes: int | None = None
    sha256: str | None = None
    sha1: str | None = None
    crc32: str | None = None
    provenance: str | None = None


def load(manifest: Path = MANIFEST) -> list[Clip]:
    document = json.loads(manifest.read_text())
    return [Clip(**entry) for entry in document["clips"]]


def by_key(key: str, manifest: Path = MANIFEST) -> Clip:
    for clip in load(manifest):
        if clip.key == key:
            return clip
    known = ", ".join(clip.key for clip in load(manifest))
    msg = f"{key} is not in the manifest; it holds {known}"
    raise KeyError(msg)


def directory() -> Path:
    override = os.environ.get(DIRECTORY_ENV)
    if override:
        return Path(override)
    document = json.loads(MANIFEST.read_text())
    return ROOT / str(document["directory"])


def path_of(clip: Clip) -> Path:
    if clip.committed:
        return ROOT / clip.file
    return directory() / clip.file


def resolve(clip: Clip) -> Path | None:
    candidate = path_of(clip)
    return candidate if candidate.is_file() else None


def verify(path: Path, clip: Clip) -> core.Verdict:
    return core.verify(path, clip, fetch_command=FETCH_COMMAND)


def available() -> list[tuple[Clip, Path]]:
    found: list[tuple[Clip, Path]] = []
    for clip in load():
        path = resolve(clip)
        if path is not None and verify(path, clip).ok:
            found.append((clip, path))
    return found


def required() -> bool:
    return core.required(REQUIRE_ENV)
