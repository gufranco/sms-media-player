from __future__ import annotations

import numpy as np
import numpy.typing as npt
from fmvcore import colour

from smsmovie import palettes, pattern, smscolor, workingset


def displayed_error(
    frame: npt.NDArray[np.uint8],
    fitted: palettes.FramePalettes,
    *,
    shown_slot: npt.NDArray[np.int32],
    cache: workingset.WorkingSet,
    chroma_weight: float,
    flips: tuple[npt.NDArray[np.bool_], npt.NDArray[np.bool_]],
    floor: npt.NDArray[np.float32],
) -> tuple[float, float]:
    lab = smscolor.oklab_palette(chroma_weight)
    slots, data = cache.residents()
    if slots.size == 0:
        msg = "no pattern is resident, so nothing on screen can be scored"
        raise ValueError(msg)

    flat_source = source_cells(frame, chroma_weight)
    shown = _shown_cells(
        fitted, lab=lab, slots=slots, data=data, shown_slot=shown_slot, flips=flips
    )
    difference = flat_source - shown
    against_floor = floor.reshape(shown.shape) - shown
    return (
        float((difference * difference).sum(axis=-1).mean()),
        float((against_floor * against_floor).sum(axis=-1).mean()),
    )


def source_cells(frame: npt.NDArray[np.uint8], chroma_weight: float) -> npt.NDArray[np.float32]:
    source = colour.srgb_to_oklab(frame.astype(np.float32) / 255.0)
    source[..., 1] *= chroma_weight
    source[..., 2] *= chroma_weight
    source_cells = pattern.tile_frame(
        np.arange(frame.shape[0] * frame.shape[1], dtype=np.int32).reshape(frame.shape[:2])
    )
    return source.reshape(-1, 3)[source_cells]


def _shown_cells(
    fitted: palettes.FramePalettes,
    *,
    lab: npt.NDArray[np.float32],
    slots: npt.NDArray[np.int32],
    data: npt.NDArray[np.uint8],
    shown_slot: npt.NDArray[np.int32],
    flips: tuple[npt.NDArray[np.bool_], npt.NDArray[np.bool_]],
) -> npt.NDArray[np.float32]:
    table = fitted.cram.reshape(smscolor.PALETTE_COUNT, smscolor.PALETTE_ENTRIES)
    lookup = np.full(int(max(slots.max(), shown_slot.max())) + 1, -1, dtype=np.intp)
    lookup[slots] = np.arange(slots.shape[0])
    indices = pattern.unpack_patterns(data)
    hflip, vflip = flips
    shown = np.zeros((shown_slot.shape[0], pattern.TILE_PX, pattern.TILE_PX, 3), dtype=np.float32)
    for cell in range(shown_slot.shape[0]):
        slot = int(shown_slot[cell])
        if slot < 0:
            shown[cell] = lab[0]
            continue
        if lookup[slot] < 0:
            msg = f"cell {cell} shows slot {slot}, which holds no resident pattern"
            raise ValueError(msg)
        cell_tile = indices[lookup[slot]]
        if hflip[cell]:
            cell_tile = cell_tile[:, ::-1]
        if vflip[cell]:
            cell_tile = cell_tile[::-1, :]
        shown[cell] = lab[table[int(fitted.choice[cell])][cell_tile].astype(np.intp)]
    return shown


_PERCEIVED_KERNEL = np.array([0.25, 0.5, 0.25], dtype=np.float32)
_CHANNELS = smscolor.RGB_CHANNELS


def perceived_cells(features: npt.NDArray[np.float32]) -> npt.NDArray[np.float32]:
    width = pattern.TILE_PX * pattern.TILE_PX * _CHANNELS
    if features.ndim != pattern.BATCH_RANK or features.shape[1] != width:
        msg = f"features must be whole cells of {width} values, got shape {features.shape}"
        raise ValueError(msg)
    side = pattern.TILE_PX
    grid = features.reshape(-1, side, side, _CHANNELS)
    padded = np.pad(grid, ((0, 0), (1, 1), (0, 0), (0, 0)), mode="reflect")
    rows = sum(_PERCEIVED_KERNEL[i] * padded[:, i : i + side] for i in range(3))
    padded = np.pad(rows, ((0, 0), (0, 0), (1, 1), (0, 0)), mode="reflect")
    both = sum(_PERCEIVED_KERNEL[i] * padded[:, :, i : i + side] for i in range(3))
    return np.asarray(both, dtype=np.float32).reshape(features.shape)


def cell_colours(
    indices: npt.NDArray[np.uint8],
    fitted: palettes.FramePalettes,
    chroma_weight: float,
) -> npt.NDArray[np.float32]:
    lab = smscolor.oklab_palette(chroma_weight)
    table = fitted.cram.reshape(smscolor.PALETTE_COUNT, smscolor.PALETTE_ENTRIES)
    entries = table[fitted.choice]
    colours = np.take_along_axis(
        entries.reshape(-1, 1, 1, smscolor.PALETTE_ENTRIES),
        indices[..., None].astype(np.intp),
        axis=3,
    )[..., 0]
    return lab[colours.astype(np.intp)]
