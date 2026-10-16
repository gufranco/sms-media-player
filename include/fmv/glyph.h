#ifndef FMV_GLYPH_H
#define FMV_GLYPH_H

#include "fmv/types.h"

#define FMV_GLYPH_TILE_BYTES 32u
#define FMV_GLYPH_COLON      10u
#define FMV_GLYPH_SLASH      11u
#define FMV_GLYPH_BLANK      12u
#define FMV_GLYPH_B          13u
#define FMV_GLYPH_D          14u
#define FMV_GLYPH_F          15u
#define FMV_GLYPH_TENS       10u

void fmv_glyph_row(u8 *tile, u8 row, u8 ink, u8 shade);
void fmv_glyph_text(u8 *tile, u8 left, u8 right);
void fmv_glyph_upload(u8 number, const u8 *tile);

#endif
