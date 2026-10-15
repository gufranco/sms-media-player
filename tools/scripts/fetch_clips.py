from __future__ import annotations

import argparse
import http.client
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from smsmovie import clips

USER_AGENT: Final = "sms-movie-player-clips/1.0 (+https://github.com/gufranco/sms-movie-player)"
CHUNK: Final = 1 << 20
TIMEOUT: Final = 300
MAX_BLOCKS: Final = 1 << 12
PARTIAL_SUFFIX: Final = ".part"
ATTEMPTS: Final = 3
BACKOFF_SECONDS: Final = 5.0
TRANSIENT: Final = (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException)


@dataclass(frozen=True, slots=True)
class Outcome:
    key: str
    action: str
    ok: bool
    diagnosis: str


class TooLargeError(RuntimeError):
    pass


def download(url: str, target: Path, limit: int | None) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    target.parent.mkdir(parents=True, exist_ok=True)
    ceiling = limit if limit is not None else 0
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response, target.open("wb") as sink:
        written = 0
        for _ in range(MAX_BLOCKS):
            block = response.read(CHUNK)
            if not block:
                return
            written += len(block)
            if ceiling and written > ceiling:
                msg = f"{url} sent more than the {ceiling} bytes the manifest names"
                raise TooLargeError(msg)
            sink.write(block)
    msg = f"{url} sent more than {MAX_BLOCKS} blocks without ending"
    raise TooLargeError(msg)


def fetch(
    url: str,
    target: Path,
    limit: int | None,
    *,
    download: Callable[[str, Path, int | None], None] = download,
    wait: Callable[[float], None] = time.sleep,
) -> None:
    for attempt in range(1, ATTEMPTS + 1):
        try:
            download(url, target, limit)
        except TRANSIENT as error:
            if attempt == ATTEMPTS:
                raise
            print(f"{url}: {error!r}; retrying, attempt {attempt + 1} of {ATTEMPTS}")
            wait(BACKOFF_SECONDS * attempt)
        else:
            return


def acquire(
    clip: clips.Clip,
    *,
    download: Callable[[str, Path, int | None], None] = download,
    wait: Callable[[float], None] = time.sleep,
) -> Outcome:
    target = clips.path_of(clip)
    held = _already_held(clip, target)
    if held is not None:
        return held
    if not clip.url:
        return Outcome(clip.key, "unreachable", False, f"{clip.key} has no url in the manifest")

    partial = target.with_name(target.name + PARTIAL_SUFFIX)
    try:
        fetch(clip.url, partial, clip.bytes, download=download, wait=wait)
    except (*TRANSIENT, TooLargeError) as error:
        partial.unlink(missing_ok=True)
        return Outcome(clip.key, "failed", False, f"{clip.url}: {error}")
    verdict = clips.verify(partial, clip)
    if not verdict.ok:
        partial.unlink(missing_ok=True)
        return Outcome(clip.key, "rejected", False, verdict.diagnosis)
    partial.replace(target)
    return Outcome(clip.key, "fetched", True, verdict.diagnosis)


def _already_held(clip: clips.Clip, target: Path) -> Outcome | None:
    if clip.committed:
        verdict = clips.verify(target, clip)
        return Outcome(clip.key, "committed", verdict.ok, verdict.diagnosis)
    if target.is_file():
        verdict = clips.verify(target, clip)
        if verdict.ok:
            return Outcome(clip.key, "present", True, verdict.diagnosis)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fetch_clips")
    parser.add_argument("keys", nargs="*", help="fetch only these clips")
    args = parser.parse_args(argv)

    manifest = clips.load()
    unknown = sorted(set(args.keys) - {clip.key for clip in manifest})
    if unknown:
        known = ", ".join(clip.key for clip in manifest)
        print(f"not in the manifest: {', '.join(unknown)}; it holds {known}", file=sys.stderr)
        return 2
    wanted = [clip for clip in manifest if not args.keys or clip.key in args.keys]

    outcomes = [acquire(clip) for clip in wanted]
    for outcome in outcomes:
        print(f"[{outcome.action:>10}] {outcome.key}: {outcome.diagnosis}")
    failures = sum(1 for outcome in outcomes if not outcome.ok)
    print(f"\n{len(wanted) - failures} of {len(wanted)} clips are ready in {clips.directory()}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
