from __future__ import annotations

import subprocess
from pathlib import Path


def lavfi_clip(path: Path, *, size: str, rate: int = 12) -> Path:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size={size}:rate={rate}:duration=2",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
    )
    return path


def bake_only_argv(clip: Path, folder: Path) -> list[str]:
    return [
        str(clip),
        "--fps",
        "4",
        "--duration",
        "1",
        "--columns",
        "8",
        "--rows",
        "6",
        "--cap",
        "60",
        "--assets",
        str(folder / "assets"),
        "--generated",
        str(folder / "generated"),
        "--report",
        str(folder / "report.json"),
        "--bake-only",
    ]
