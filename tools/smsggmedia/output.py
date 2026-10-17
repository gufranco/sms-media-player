from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Final

FILM: Final = "movie.bin"
HEADER: Final = "movie.h"
STAGED: Final = ".tmp"
FIRST_BANK_SYMBOL: Final = "movie_bin_PART0_bank"
MAX_HOLD_FIELDS: Final = 0xFFFF
MAX_FRAME_INDEX: Final = 0xFFFF
MAX_KEYS: Final = 254


@dataclass(frozen=True, slots=True)
class Key:
    bank: int
    offset: int
    frame: int
    field: int


def write_header(
    path: Path,
    *,
    banks: int,
    frame_count: int,
    field_count: int,
    hold_fields: int,
    first_bank_symbol: str,
    keys: tuple[Key, ...] = (Key(bank=0, offset=0, frame=0, field=0),),
) -> None:
    check_header(
        frame_count=frame_count, field_count=field_count, hold_fields=hold_fields, keys=keys
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#ifndef FMV_MOVIE_H\n"
        "#define FMV_MOVIE_H\n"
        "\n"
        f"#define MOVIE_BANKS {banks}u\n"
        f"#define MOVIE_FRAMES {frame_count}u\n"
        f"#define MOVIE_FIELDS {field_count}ul\n"
        f"#define MOVIE_HOLD_FIELDS {hold_fields}u\n"
        f"#define MOVIE_FIRST_BANK {first_bank_symbol}\n"
        f"#define MOVIE_KEYS {len(keys)}u\n"
        f"#define MOVIE_KEY_TABLE {_key_table(keys, first_bank_symbol)}\n"
        "\n"
        "#endif\n"
    )


def check_header(
    *, frame_count: int, field_count: int, hold_fields: int, keys: tuple[Key, ...]
) -> None:
    _check_keys(keys)
    if not 1 <= frame_count <= MAX_FRAME_INDEX:
        msg = f"the player counts frames in 16 bits, so a film of {frame_count} cannot play"
        raise ValueError(msg)
    if field_count < 1:
        msg = "a film needs at least one field"
        raise ValueError(msg)
    if not 1 <= hold_fields <= MAX_HOLD_FIELDS:
        msg = f"the player counts the hold in 16 bits, so {hold_fields} fields cannot be held"
        raise ValueError(msg)


def _check_keys(keys: tuple[Key, ...]) -> None:
    if not keys:
        msg = "a film needs at least one seek point, its first frame"
        raise ValueError(msg)
    if len(keys) > MAX_KEYS:
        msg = f"the player indexes seek points in one byte, so {len(keys)} is more than {MAX_KEYS}"
        raise ValueError(msg)
    if any(key.frame > MAX_FRAME_INDEX for key in keys):
        msg = f"the player counts frames in 16 bits, so no seek point can pass {MAX_FRAME_INDEX}"
        raise ValueError(msg)


def _key_table(keys: tuple[Key, ...], first_bank_symbol: str) -> str:
    rows = ", ".join(
        f"{{{first_bank_symbol} + {key.bank}u, 0x{key.offset:04X}u, {key.frame}u, {key.field}ul}}"
        for key in keys
    )
    return f"{{{rows}}}"


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
    field_count: int,
    hold_fields: int,
    keys: tuple[Key, ...] = (Key(bank=0, offset=0, frame=0, field=0),),
) -> None:
    clear(assets=assets, generated=generated)
    check_header(
        frame_count=frame_count, field_count=field_count, hold_fields=hold_fields, keys=keys
    )
    assets.mkdir(parents=True, exist_ok=True)
    film = assets / (FILM + STAGED)
    film.write_bytes(blob)
    header = generated / (HEADER + STAGED)
    write_header(
        header,
        banks=banks,
        frame_count=frame_count,
        field_count=field_count,
        hold_fields=hold_fields,
        first_bank_symbol=FIRST_BANK_SYMBOL,
        keys=keys,
    )
    header.replace(generated / HEADER)
    film.replace(assets / FILM)
