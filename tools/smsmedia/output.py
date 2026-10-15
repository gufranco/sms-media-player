from __future__ import annotations

import math
from pathlib import Path
from typing import Final

FILM: Final = "movie.bin"
HEADER: Final = "movie.h"
STAGED: Final = ".tmp"
FIRST_BANK_SYMBOL: Final = "movie_bin_PART0_bank"
MAX_HOLD_FIELDS: Final = 0xFFFF


def write_header(
    path: Path,
    *,
    banks: int,
    frame_count: int,
    hold_fields: int,
    first_bank_symbol: str,
) -> None:
    if not 1 <= hold_fields <= MAX_HOLD_FIELDS:
        msg = f"the player counts the hold in 16 bits, so {hold_fields} fields cannot be held"
        raise ValueError(msg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#ifndef FMV_MOVIE_H\n"
        "#define FMV_MOVIE_H\n"
        "\n"
        f"#define MOVIE_BANKS {banks}u\n"
        f"#define MOVIE_FRAMES {frame_count}u\n"
        f"#define MOVIE_HOLD_FIELDS {hold_fields}u\n"
        f"#define MOVIE_FIRST_BANK {first_bank_symbol}\n"
        "\n"
        "#endif\n"
    )


def nearest_rank(values: list[int], share: float) -> int:
    if not values:
        msg = "a percentile needs at least one value"
        raise ValueError(msg)
    ordered = sorted(values)
    return ordered[max(0, math.ceil(share * len(ordered)) - 1)]


def clear(*, assets: Path, generated: Path) -> None:
    for path in (
        assets / FILM,
        assets / (FILM + STAGED),
        generated / HEADER,
        generated / (HEADER + STAGED),
    ):
        path.unlink(missing_ok=True)


def publish(
    *,
    assets: Path,
    generated: Path,
    blob: bytes,
    banks: int,
    frame_count: int,
    hold_fields: int,
) -> None:
    assets.mkdir(parents=True, exist_ok=True)
    film = assets / (FILM + STAGED)
    film.write_bytes(blob)
    header = generated / (HEADER + STAGED)
    write_header(
        header,
        banks=banks,
        frame_count=frame_count,
        hold_fields=hold_fields,
        first_bank_symbol=FIRST_BANK_SYMBOL,
    )
    (assets / FILM).unlink(missing_ok=True)
    header.replace(generated / HEADER)
    film.replace(assets / FILM)
