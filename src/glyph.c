#include "fmv/glyph.h"

#include "fmv/assert.h"
#include "fmv/vdpcopy.h"

#define GLYPH_SPRITE_PATTERNS 0x2000u
#define GLYPH_TILE_ROWS       8u
#define GLYPH_PLANES          4u
#define GLYPH_ROWS            5u
#define GLYPH_TOP             1u
#define GLYPH_COUNT           19u
#define GLYPH_LEFT_SHIFT      5u
#define GLYPH_RIGHT_SHIFT     1u
#define GLYPH_BACK_FIRST      176u
#define GLYPH_BACK_LAST       191u
#define GLYPH_FRONT_FIRST     240u
#define GLYPH_FRONT_LAST      247u

static const u8 glyph_font[GLYPH_COUNT][GLYPH_ROWS] = {
    {7u, 5u, 5u, 5u, 7u}, {2u, 6u, 2u, 2u, 7u}, {7u, 1u, 7u, 4u, 7u}, {7u, 1u, 3u, 1u, 7u},
    {5u, 5u, 7u, 1u, 1u}, {7u, 4u, 7u, 1u, 7u}, {7u, 4u, 7u, 5u, 7u}, {7u, 1u, 1u, 2u, 2u},
    {7u, 5u, 7u, 5u, 7u}, {7u, 5u, 7u, 1u, 7u}, {0u, 2u, 0u, 2u, 0u}, {1u, 1u, 2u, 4u, 4u},
    {0u, 0u, 0u, 0u, 0u}, {6u, 5u, 6u, 5u, 6u}, {6u, 5u, 5u, 5u, 6u}, {7u, 4u, 6u, 4u, 4u},
    {4u, 6u, 7u, 6u, 4u}, {5u, 5u, 5u, 5u, 5u}, {0u, 5u, 2u, 5u, 0u},
};

static u8 glyph_pixels(u8 glyph, u8 row)
{
    FMV_ASSERT(glyph < GLYPH_COUNT);
    FMV_ASSERT(row < GLYPH_TILE_ROWS);

    if (row < GLYPH_TOP || row >= GLYPH_TOP + GLYPH_ROWS) {
        return 0u;
    }
    return glyph_font[glyph][row - GLYPH_TOP];
}

void fmv_glyph_row(u8 *tile, u8 row, u8 ink, u8 shade)
{
    u8 *const planes = &tile[(u8)(row * GLYPH_PLANES)];
    const u8 lit = (u8)(ink | shade);

    FMV_ASSERT(tile != 0);
    FMV_ASSERT(row < GLYPH_TILE_ROWS);
    planes[0] = ink;
    planes[1] = lit;
    planes[2] = lit;
    planes[3] = lit;
}

void fmv_glyph_text(u8 *tile, u8 left, u8 right)
{
    u8 row;
    u8 above = 0u;

    FMV_ASSERT(left < GLYPH_COUNT);
    FMV_ASSERT(right < GLYPH_COUNT);
    for (row = 0u; row < GLYPH_TILE_ROWS; row++) {
        const u8 ink = (u8)((glyph_pixels(left, row) << GLYPH_LEFT_SHIFT)
                            | (glyph_pixels(right, row) << GLYPH_RIGHT_SHIFT));
        const u8 shade = (u8)(((u8)(ink >> 1) | above | (u8)(above >> 1)) & (u8)~ink);

        fmv_glyph_row(tile, row, ink, shade);
        above = ink;
    }
}

void fmv_glyph_upload(u8 number, const u8 *tile)
{
    FMV_ASSERT(tile != 0);
    FMV_ASSERT((number >= GLYPH_BACK_FIRST && number <= GLYPH_BACK_LAST)
               || (number >= GLYPH_FRONT_FIRST && number <= GLYPH_FRONT_LAST));

    fmv_vdp_write((u16)(GLYPH_SPRITE_PATTERNS + (u16)number * FMV_GLYPH_TILE_BYTES),
                  FMV_VDP_VRAM_WRITE, tile, FMV_GLYPH_TILE_BYTES);
}
