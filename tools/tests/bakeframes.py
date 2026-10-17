import numpy as np
from fmvcore import colour

from smsggmedia import bake, console, limits, palettes, replay, stream


def gradient_frame(height: int, width: int, shift: int = 0) -> np.ndarray:
    y, x = np.mgrid[0:height, 0:width]
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[..., 0] = ((x + shift) * 3) % 256
    frame[..., 1] = (y * 5) % 256
    frame[..., 2] = ((x + y + shift) * 7) % 256
    return frame


def displays_before_the_palette(
    machine: replay.Machine, chunks: list[bytes], before: np.ndarray
) -> list[bool]:
    untouched = []
    for chunk in chunks:
        if "palette" in write_targets([chunk]):
            break
        machine.apply(chunk)
        untouched.append(np.array_equal(machine.display(), before))
    return untouched


def replayed_working_set(
    encoded_frames: list[list[bytes]], frames: list[np.ndarray], geometry: bake.Geometry
) -> float:
    machine = replay.Machine()
    measured = []
    kept = None
    for index, chunks in enumerate(encoded_frames):
        for chunk in chunks:
            machine.apply(chunk)
        shown = machine.render(
            columns=geometry.columns, rows=geometry.rows, top_row=geometry.top_row
        )
        fitted = palettes.fit_or_keep(
            frames[index],
            kept,
            margin=limits.PALETTE_KEEP_MARGIN,
            ordered_dither=limits.DEFAULT_DITHER,
        )
        kept = fitted.cram
        floor = fitted.render()
        a = colour.srgb_to_oklab(shown.astype(np.float32) / 255.0)
        b = colour.srgb_to_oklab(floor.astype(np.float32) / 255.0)
        measured.append(float(((a - b) ** 2).sum(axis=-1).mean()))
    return float(np.mean(measured))


def write_kinds(chunks: list[bytes]) -> list[int]:
    return [kind for kind, _ in walk(chunks)]


def write_targets(chunks: list[bytes]) -> list[str]:
    names = []
    for kind, address in walk(chunks):
        if kind in stream.CLOSE_KINDS:
            names.append("palette")
        else:
            names.append("names" if address >= console.BACK_TABLE_BASE else "patterns")
    return names


def walk(chunks: list[bytes]) -> list[tuple[int, int]]:
    found = []
    for chunk in chunks:
        pos = 0
        while pos < len(chunk) and chunk[pos] in (stream.VRAM, *stream.CLOSE_KINDS):
            kind = chunk[pos]
            if kind == stream.VRAM:
                found.append((kind, chunk[pos + 1] | (chunk[pos + 2] << 8)))
                pos += 4 + chunk[pos + 3]
            else:
                found.append((kind, chunk[pos + 1]))
                pos += 2 + stream.close_bytes(kind)
    return found
