#ifndef FMV_TARGET_H
#define FMV_TARGET_H

#include "SMSlib.h"
#include "fmv/types.h"

typedef u16 fmv_colour;
#define FMV_CRAM_ENTRY_BYTES 2u
#define FMV_COLOUR_BLACK     0x0000u
#define FMV_COLOUR_WHITE     0x0FFFu
#define FMV_COLOUR_RED       0x000Fu
#define FMV_COLOUR_ASSERT    0x0F00u
#define FMV_KEYS_TEXT        "1 restarts 2 stops Start pauses Up mutes Down diag Left/Right seek"

static inline void fmv_set_bg_colour(u8 entry, fmv_colour colour)
{
    GG_setBGPaletteColor(entry, colour);
}

static inline void fmv_set_sprite_colour(u8 entry, fmv_colour colour)
{
    GG_setSpritePaletteColor(entry, colour);
}

#endif
