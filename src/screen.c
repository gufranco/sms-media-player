#include "fmv/screen.h"

#include "SMSlib.h"
#include "fmv/console.h"
#include "fmv/psg.h"

void fmv_screen_reset(void)
{
    static_assert(FMV_SCREEN_NAME_TABLE + FMV_SCREEN_NAME_TABLE_BYTES == FMV_SCREEN_SAT,
                  "the name table ends where the sprite table starts");
    static_assert((FMV_SCREEN_IDLE_CELL & 0x01FFu) < FMV_SCREEN_RESERVED,
                  "the idle cell points inside the reserved patterns");
    static_assert(FMV_SCREEN_BACK_TABLE + FMV_SCREEN_NAME_TABLE_BYTES <= FMV_SCREEN_NAME_TABLE,
                  "the back table ends before the front one");

    SMS_displayOff();
    SMS_VRAMmemset(0x0000u, 0x00u, FMV_SCREEN_VRAM_BYTES);
    SMS_VRAMmemsetW(FMV_SCREEN_NAME_TABLE, FMV_SCREEN_IDLE_CELL, FMV_SCREEN_NAME_TABLE_BYTES);
    SMS_VRAMmemsetW(FMV_SCREEN_BACK_TABLE, FMV_SCREEN_IDLE_CELL, FMV_SCREEN_NAME_TABLE_BYTES);
    fmv_screen_table(FMV_SCREEN_FRONT_REGISTER);
    SMS_VRAMmemset(FMV_SCREEN_SAT, FMV_SCREEN_SPRITE_OFF, FMV_SCREEN_SPRITES);
    SMS_initSprites();
    SMS_copySpritestoSAT();
    fmv_set_bg_colour(0u, FMV_COLOUR_BLACK);
    fmv_set_sprite_colour(0u, FMV_COLOUR_BLACK);
    SMS_displayOn();
}

void fmv_screen_fault(void)
{
    fmv_set_sprite_colour(0u, FMV_COLOUR_RED);
}

void fmv_screen_rest(void)
{
    fmv_psg_silence();
    fmv_screen_reset();
}
