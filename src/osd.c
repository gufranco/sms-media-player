#include "fmv/osd.h"

#include "fmv/glyph.h"
#include "fmv/vdpcopy.h"

#define OSD_FIRST_TILE     176u
#define OSD_TEXT_TILES     6u
#define OSD_TILE_FULL      (OSD_FIRST_TILE + OSD_TEXT_TILES)
#define OSD_TILE_EMPTY     (OSD_TILE_FULL + 1u)
#define OSD_TILE_PARTIAL   (OSD_TILE_FULL + 2u)
#define OSD_TILE_ROWS      8u
#define OSD_SPRITE_PIXELS  8u
#define OSD_CELLS          11u
#define OSD_BAR_SPRITES    8u
#define OSD_BAR_PIXELS     64u
#define OSD_BAR_TOP        2u
#define OSD_BAR_BOTTOM     5u
#define OSD_TRACK_TOP      3u
#define OSD_TRACK_BOTTOM   4u
#define OSD_SPRITES        FMV_OSD_SPRITES
#define OSD_SAT_Y          0x3F00u
#define OSD_SAT_XN         0x3F80u
#define OSD_SPRITE_END     0xD0u
#define OSD_TEXT_Y         167u
#define OSD_BAR_Y          179u
#define OSD_TEXT_X         104u
#define OSD_BAR_X          96u
#define OSD_INK_ENTRY      30u
#define OSD_INK_BLACK      0x00u
#define OSD_INK_WHITE      0x3Fu
#define OSD_FIELD_HZ_MILLI 59923ul
#define OSD_MILLI          1000ul
#define OSD_MAX_MINUTES    99ul
#define OSD_SECONDS        60ul

static u8 osd_tile[FMV_GLYPH_TILE_BYTES];
static u8 osd_cells[OSD_CELLS + 1u];

static void osd_compose_bar(u8 filled)
{
    const u8 ink = (u8)(0xFFu << (OSD_SPRITE_PIXELS - filled));
    u8 row;

    for (row = 0u; row < OSD_TILE_ROWS; row++) {
        const bool band = row >= OSD_BAR_TOP && row <= OSD_BAR_BOTTOM;
        const bool track = row >= OSD_TRACK_TOP && row <= OSD_TRACK_BOTTOM;
        const u8 lit = band ? ink : 0u;

        fmv_glyph_row(osd_tile, row, lit, (u8)((track ? 0xFFu : 0u) & (u8)~lit));
    }
}

static void osd_put_clock(u8 at, u32 fields, u32 bias)
{
    const u32 seconds = (fields * OSD_MILLI + bias) / OSD_FIELD_HZ_MILLI;
    const u32 minutes = seconds / OSD_SECONDS;
    const u8 shown = (u8)(minutes > OSD_MAX_MINUTES ? OSD_MAX_MINUTES : minutes);
    const u8 rest = (u8)(minutes > OSD_MAX_MINUTES ? OSD_SECONDS - 1u : seconds % OSD_SECONDS);

    osd_cells[at] = (u8)(shown / FMV_GLYPH_TENS);
    osd_cells[at + 1u] = (u8)(shown % FMV_GLYPH_TENS);
    osd_cells[at + 2u] = FMV_GLYPH_COLON;
    osd_cells[at + 3u] = (u8)(rest / FMV_GLYPH_TENS);
    osd_cells[at + 4u] = (u8)(rest % FMV_GLYPH_TENS);
}

static void osd_upload_text(const fmv_position *where)
{
    u8 tile;

    osd_put_clock(0u, where->elapsed_fields, 0u);
    osd_cells[5] = FMV_GLYPH_SLASH;
    osd_put_clock(6u, where->total_fields, OSD_FIELD_HZ_MILLI / 2u);
    osd_cells[OSD_CELLS] = FMV_GLYPH_BLANK;
    for (tile = 0u; tile < OSD_TEXT_TILES; tile++) {
        fmv_glyph_text(osd_tile, osd_cells[tile * 2u], osd_cells[tile * 2u + 1u]);
        fmv_glyph_upload((u8)(OSD_FIRST_TILE + tile), osd_tile);
    }
}

static u8 osd_filled(const fmv_position *where)
{
    if (where->total_fields == 0u || where->elapsed_fields >= where->total_fields) {
        return OSD_BAR_PIXELS;
    }
    return (u8)(where->elapsed_fields * OSD_BAR_PIXELS / where->total_fields);
}

static void osd_upload_bar(u8 filled)
{
    static const u8 tiles[3] = {OSD_TILE_FULL, OSD_TILE_EMPTY, OSD_TILE_PARTIAL};
    const u8 widths[3] = {OSD_SPRITE_PIXELS, 0u, (u8)(filled % OSD_SPRITE_PIXELS)};
    u8 index;

    for (index = 0u; index < 3u; index++) {
        osd_compose_bar(widths[index]);
        fmv_glyph_upload(tiles[index], osd_tile);
    }
}

static u8 osd_bar_tile(u8 sprite, u8 filled)
{
    const u8 start = (u8)(sprite * OSD_SPRITE_PIXELS);

    if (filled >= start + OSD_SPRITE_PIXELS) {
        return OSD_TILE_FULL;
    }
    if (filled <= start) {
        return OSD_TILE_EMPTY;
    }
    return OSD_TILE_PARTIAL;
}

static void osd_place(u8 filled)
{
    u8 ys[OSD_SPRITES + 1u];
    u8 xn[OSD_SPRITES * 2u];
    u8 sprite;

    for (sprite = 0u; sprite < OSD_SPRITES; sprite++) {
        const bool text = sprite < OSD_TEXT_TILES;
        const u8 bar = (u8)(sprite - OSD_TEXT_TILES);

        ys[sprite] = text ? OSD_TEXT_Y : OSD_BAR_Y;
        xn[sprite * 2u] = (u8)(text ? OSD_TEXT_X + sprite * OSD_SPRITE_PIXELS : OSD_BAR_X + bar * OSD_SPRITE_PIXELS);
        xn[sprite * 2u + 1u] = text ? (u8)(OSD_FIRST_TILE + sprite) : osd_bar_tile(bar, filled);
    }
    ys[OSD_SPRITES] = OSD_SPRITE_END;
    fmv_vdp_write(OSD_SAT_XN, FMV_VDP_VRAM_WRITE, xn, (u8)sizeof xn);
    fmv_vdp_write(OSD_SAT_Y, FMV_VDP_VRAM_WRITE, ys, (u8)sizeof ys);
}

void fmv_osd_show(const fmv_position *where)
{
    static_assert(OSD_TEXT_TILES + OSD_BAR_SPRITES == OSD_SPRITES, "the overlay owns the first sprites");
    static const u8 inks[2] = {OSD_INK_BLACK, OSD_INK_WHITE};
    const u8 filled = osd_filled(where);

    fmv_vdp_write(OSD_INK_ENTRY, FMV_VDP_CRAM_WRITE, inks, (u8)sizeof inks);
    osd_upload_text(where);
    osd_upload_bar(filled);
    osd_place(filled);
}

void fmv_osd_hide(void)
{
    static const u8 end[1] = {OSD_SPRITE_END};

    fmv_vdp_write(OSD_SAT_Y, FMV_VDP_VRAM_WRITE, end, (u8)sizeof end);
}
