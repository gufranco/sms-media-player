#ifndef FMV_CONSOLE_H
#define FMV_CONSOLE_H

#include "SMSlib.h"
#include "fmv/types.h"

#ifdef TARGET_GG
typedef u16 fmv_colour;
#define FMV_CRAM_ENTRY_BYTES 2u
#define FMV_COLOUR_BLACK     0x0000u
#define FMV_COLOUR_WHITE     0x0FFFu
#define FMV_COLOUR_RED       0x000Fu
#define FMV_COLOUR_ASSERT    0x0F00u
#define FMV_PLAYER_NAME      "SMS/GG Media Player"
#define FMV_KEYS_TEXT        "1 restarts 2 stops Start pauses Up mutes Down diag Left/Right seek"

static inline void fmv_set_bg_colour(u8 entry, fmv_colour colour)
{
    GG_setBGPaletteColor(entry, colour);
}

static inline void fmv_set_sprite_colour(u8 entry, fmv_colour colour)
{
    GG_setSpritePaletteColor(entry, colour);
}
#else
typedef u8 fmv_colour;
#define FMV_CRAM_ENTRY_BYTES 1u
#define FMV_COLOUR_BLACK     0x00u
#define FMV_COLOUR_WHITE     0x3Fu
#define FMV_COLOUR_RED       0x03u
#define FMV_COLOUR_ASSERT    0x30u
#define FMV_PLAYER_NAME      "SMS/GG Media Player"
#define FMV_KEYS_TEXT        "1 restarts 2 stops Pause pauses Up mutes Down diag Left/Right seek"

static inline void fmv_set_bg_colour(u8 entry, fmv_colour colour)
{
    SMS_setBGPaletteColor(entry, colour);
}

static inline void fmv_set_sprite_colour(u8 entry, fmv_colour colour)
{
    SMS_setSpritePaletteColor(entry, colour);
}
#endif

#endif
