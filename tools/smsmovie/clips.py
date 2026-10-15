from __future__ import annotations

import hashlib
import json
import os
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from smsmovie import limits

ROOT: Final = Path(__file__).resolve().parents[2]
MANIFEST: Final = ROOT / "tools" / "clips.manifest.json"
DIRECTORY_ENV: Final = "SMSMOVIE_CLIPS_DIR"
REQUIRE_ENV: Final = "SMSMOVIE_CLIPS_REQUIRED"
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


@dataclass(frozen=True, slots=True)
class Verdict:
    ok: bool
    diagnosis: str


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


def digests(payload: bytes) -> dict[str, str]:
    return {
        "sha256": hashlib.sha256(payload).hexdigest(),
        "sha1": hashlib.sha1(payload).hexdigest(),
        "crc32": f"{zlib.crc32(payload) & 0xFFFFFFFF:08X}",
    }


def verify(path: Path, clip: Clip) -> Verdict:
    if not path.is_file():
        return Verdict(False, f"{path} is not here. Fetch it with:\n    {FETCH_COMMAND}")

    if clip.sha256 is None:
        return Verdict(
            False,
            f"the manifest publishes no digest for {clip.key}, so no copy of it can be "
            "recognised; add its sha256 and bytes to the manifest",
        )

    wrong_size = _size_mismatch(path, clip)
    if wrong_size is not None:
        return wrong_size
    return _digest_verdict(path, clip)


def _size_mismatch(path: Path, clip: Clip) -> Verdict | None:
    size = path.stat().st_size
    if clip.bytes is None or size == clip.bytes:
        return None
    return Verdict(
        False,
        f"{path.name} is {size} bytes and {clip.title} is {clip.bytes}. "
        "The size decides before the digest does, so this is a different file "
        "rather than a damaged one. Delete it and fetch again with:\n"
        f"    {FETCH_COMMAND}",
    )


def _digest_verdict(path: Path, clip: Clip) -> Verdict:
    found = digests(path.read_bytes())
    if found["sha256"] == clip.sha256:
        return Verdict(True, f"{path.name} matches {clip.title}")
    shape = "is the right length and" if clip.bytes is not None else "has"
    return Verdict(
        False,
        f"{path.name} {shape} the wrong content, which means "
        "the copy was re-encoded, re-muxed, truncated or corrupted rather than "
        f"being a different film.\n    wanted sha256 {clip.sha256}\n"
        f"    found  sha256 {found['sha256']}\n"
        f"    found  crc32  {found['crc32']}\n"
        f"Search that digest to identify the copy, then fetch again with:\n"
        f"    {FETCH_COMMAND}",
    )


def available() -> list[tuple[Clip, Path]]:
    found: list[tuple[Clip, Path]] = []
    for clip in load():
        path = resolve(clip)
        if path is not None and verify(path, clip).ok:
            found.append((clip, path))
    return found


def required() -> bool:
    return os.environ.get(REQUIRE_ENV, "").strip().lower() in {"1", "true", "yes"}
