#ifndef FMV_SCREEN_H
#define FMV_SCREEN_H

#include "fmv/types.h"

#define FMV_SCREEN_VRAM_BYTES       0x4000u
#define FMV_SCREEN_NAME_TABLE       0x3800u
#define FMV_SCREEN_BACK_TABLE       0x3000u
#define FMV_SCREEN_FRONT_REGISTER   0xFFu
#define FMV_SCREEN_NAME_TABLE_BYTES 0x0700u
#define FMV_SCREEN_IDLE_CELL        0x0800u
#define FMV_SCREEN_SAT              0x3F00u
#define FMV_SCREEN_SPRITES          64u
#define FMV_SCREEN_SPRITE_OFF       0xD0u
#define FMV_SCREEN_RESERVED         1u

void fmv_screen_reset(void);
void fmv_screen_table(u8 value);
void fmv_screen_fault(void);
void fmv_screen_rest(void);

#endif
