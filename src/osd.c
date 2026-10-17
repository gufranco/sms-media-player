#include "fmv/osd.h"

#include "fmv/budget.h"
#include "fmv/console.h"
#include "fmv/glyph.h"
#include "fmv/vdpcopy.h"

#define OSD_FIRST_TILE     176u
#define OSD_TEXT_TILES     6u
#define OSD_ELAPSED_TILES  3u
#define OSD_TILE_FULL      (OSD_FIRST_TILE + OSD_TEXT_TILES)
#define OSD_TILE_EMPTY     (OSD_TILE_FULL + 1u)
#define OSD_TILE_PARTIAL   (OSD_TILE_FULL + 2u)
#define OSD_TILE_STATE     243u
#define OSD_TILE_BLANK     244u
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
#define OSD_STATE_SPRITE   (OSD_TEXT_TILES + OSD_BAR_SPRITES)
#define OSD_SAT_Y          0x3F00u
#define OSD_SAT_XN         0x3F80u
#define OSD_TEXT_Y         145u
#define OSD_BAR_Y          157u
#define OSD_TEXT_X         112u
#define OSD_BAR_X          96u
#define OSD_STATE_X        96u
#define OSD_INK_ENTRY      30u
#define OSD_FIELD_HZ_MILLI 59923ul
#define OSD_INK_LINES      10u
#define OSD_CLOCK_LINES    98u
#define OSD_TEXT_LINES     49u
#define OSD_STRIP_LINES    38u
#define OSD_BAR_LINES      88u
#define OSD_PLACE_LINES    58u
#define OSD_MILLI          1000ul
#define OSD_MAX_MINUTES    99u
#define OSD_SECONDS        60u
#define OSD_MAX_SECONDS    (OSD_MAX_MINUTES * OSD_SECONDS + OSD_SECONDS - 1u)

typedef enum {
    OSD_STEP_INKS = 0,
    OSD_STEP_TOTAL = 1,
    OSD_STEP_TEXT3 = 2,
    OSD_STEP_TEXT4 = 3,
    OSD_STEP_TEXT5 = 4,
    OSD_STEP_BAR_FULL = 5,
    OSD_STEP_BAR_EMPTY = 6,
    OSD_STEP_CLOCK = 7,
    OSD_STEP_TEXT0 = 8,
    OSD_STEP_TEXT1 = 9,
    OSD_STEP_TEXT2 = 10,
    OSD_STEP_BAR = 11,
    OSD_STEP_STATE = 12,
    OSD_STEP_BLANK = 13,
    OSD_STEP_PLACE = 14,
    OSD_STEP_DONE = 15
} osd_step;

static const u8 osd_lines[OSD_STEP_DONE] = {
    OSD_INK_LINES,  OSD_CLOCK_LINES, OSD_TEXT_LINES, OSD_TEXT_LINES, OSD_TEXT_LINES,
    OSD_STRIP_LINES, OSD_STRIP_LINES, OSD_CLOCK_LINES, OSD_TEXT_LINES, OSD_TEXT_LINES,
    OSD_TEXT_LINES, OSD_BAR_LINES,  OSD_TEXT_LINES, OSD_INK_LINES,  OSD_PLACE_LINES,
};

static u8 osd_tile[FMV_GLYPH_TILE_BYTES];
static u8 osd_cells[OSD_CELLS + 1u];
static u8 osd_next;
static u8 osd_fill;
static bool osd_visible;

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
    const u16 clamped = (u16)(seconds > OSD_MAX_SECONDS ? OSD_MAX_SECONDS : seconds);
    const u8 shown = (u8)(clamped / OSD_SECONDS);
    const u8 rest = (u8)(clamped % OSD_SECONDS);

    osd_cells[at] = (u8)(shown / FMV_GLYPH_TENS);
    osd_cells[at + 1u] = (u8)(shown % FMV_GLYPH_TENS);
    osd_cells[at + 2u] = FMV_GLYPH_COLON;
    osd_cells[at + 3u] = (u8)(rest / FMV_GLYPH_TENS);
    osd_cells[at + 4u] = (u8)(rest % FMV_GLYPH_TENS);
}

static void osd_put_total(const fmv_position *where)
{
    osd_cells[5] = FMV_GLYPH_SLASH;
    osd_put_clock(6u, where->total_fields, OSD_FIELD_HZ_MILLI / 2u);
    osd_cells[OSD_CELLS] = FMV_GLYPH_BLANK;
}

static void osd_upload_text(u8 tile)
{
    fmv_glyph_text(osd_tile, osd_cells[tile * 2u], osd_cells[tile * 2u + 1u]);
    fmv_glyph_upload((u8)(OSD_FIRST_TILE + tile), osd_tile);
}

static void osd_upload_bar(u8 number, u8 filled)
{
    osd_compose_bar(filled);
    fmv_glyph_upload(number, osd_tile);
}

static u8 osd_filled(const fmv_position *where)
{
    if (where->total_fields == 0u || where->elapsed_fields >= where->total_fields) {
        return OSD_BAR_PIXELS;
    }
    return (u8)(where->elapsed_fields * OSD_BAR_PIXELS / where->total_fields);
}

static void osd_upload_state(const fmv_osd_view *view)
{
    const u8 state = view->paused != 0u ? FMV_GLYPH_PAUSE : FMV_GLYPH_PLAY;
    const u8 sound = view->muted != 0u ? FMV_GLYPH_MUTE : FMV_GLYPH_BLANK;

    fmv_glyph_text(osd_tile, state, sound);
    fmv_glyph_upload(OSD_TILE_STATE, osd_tile);
}

static void osd_upload_blank(void)
{
    static const u8 clear[FMV_GLYPH_TILE_BYTES] = {0u};

    fmv_glyph_upload(OSD_TILE_BLANK, clear);
}

static u8 osd_bar_tile(u8 bar)
{
    const u8 start = (u8)(bar * OSD_SPRITE_PIXELS);

    if (osd_fill >= start + OSD_SPRITE_PIXELS) {
        return OSD_TILE_FULL;
    }
    if (osd_fill <= start) {
        return OSD_TILE_EMPTY;
    }
    return OSD_TILE_PARTIAL;
}

static u8 osd_sprite_tile(u8 sprite)
{
    if (!osd_visible) {
        return OSD_TILE_BLANK;
    }
    if (sprite < OSD_TEXT_TILES) {
        return (u8)(OSD_FIRST_TILE + sprite);
    }
    if (sprite < OSD_STATE_SPRITE) {
        return osd_bar_tile((u8)(sprite - OSD_TEXT_TILES));
    }
    return OSD_TILE_STATE;
}

static u8 osd_sprite_x(u8 sprite)
{
    if (sprite < OSD_TEXT_TILES) {
        return (u8)(OSD_TEXT_X + sprite * OSD_SPRITE_PIXELS);
    }
    if (sprite < OSD_STATE_SPRITE) {
        return (u8)(OSD_BAR_X + (sprite - OSD_TEXT_TILES) * OSD_SPRITE_PIXELS);
    }
    return OSD_STATE_X;
}

static void osd_place(void)
{
    u8 ys[OSD_SPRITES];
    u8 xn[OSD_SPRITES * 2u];
    u8 sprite;

    for (sprite = 0u; sprite < OSD_SPRITES; sprite++) {
        const bool bar = sprite >= OSD_TEXT_TILES && sprite < OSD_STATE_SPRITE;

        ys[sprite] = bar ? OSD_BAR_Y : OSD_TEXT_Y;
        xn[sprite * 2u] = osd_sprite_x(sprite);
        xn[sprite * 2u + 1u] = osd_sprite_tile(sprite);
    }
    fmv_vdp_write(OSD_SAT_XN, FMV_VDP_VRAM_WRITE, xn, (u8)sizeof xn);
    fmv_vdp_write(OSD_SAT_Y, FMV_VDP_VRAM_WRITE, ys, (u8)sizeof ys);
}

static u8 osd_text_tile(u8 step)
{
    if (step >= OSD_STEP_TEXT0) {
        return (u8)(step - OSD_STEP_TEXT0);
    }
    return (u8)(OSD_ELAPSED_TILES + step - OSD_STEP_TEXT3);
}

static void osd_run(u8 step, const fmv_osd_view *view)
{
    switch (step) {
    case OSD_STEP_INKS:
        fmv_osd_inks();
        break;
    case OSD_STEP_TOTAL:
        osd_put_total(&view->where);
        break;
    case OSD_STEP_BAR_FULL:
        osd_upload_bar(OSD_TILE_FULL, OSD_SPRITE_PIXELS);
        break;
    case OSD_STEP_BAR_EMPTY:
        osd_upload_bar(OSD_TILE_EMPTY, 0u);
        break;
    case OSD_STEP_CLOCK:
        osd_put_clock(0u, view->where.elapsed_fields, 0u);
        break;
    case OSD_STEP_BAR:
        osd_fill = osd_filled(&view->where);
        osd_upload_bar(OSD_TILE_PARTIAL, (u8)(osd_fill % OSD_SPRITE_PIXELS));
        break;
    case OSD_STEP_STATE:
        osd_upload_state(view);
        break;
    case OSD_STEP_BLANK:
        osd_upload_blank();
        break;
    case OSD_STEP_PLACE:
        osd_place();
        break;
    default:
        osd_upload_text(osd_text_tile(step));
        break;
    }
}

static void osd_request(u8 step)
{
    if (step < osd_next) {
        osd_next = step;
    }
}

void fmv_osd_inks(void)
{
    static const fmv_colour inks[2] = {FMV_COLOUR_BLACK, FMV_COLOUR_WHITE};

    fmv_vdp_write(OSD_INK_ENTRY * FMV_CRAM_ENTRY_BYTES, FMV_VDP_CRAM_WRITE, (const u8 *)inks,
                  (u8)sizeof inks);
}

void fmv_osd_open(void)
{
    osd_visible = true;
    osd_next = OSD_STEP_INKS;
}

void fmv_osd_tick(void)
{
    if (osd_visible) {
        osd_request(OSD_STEP_CLOCK);
    }
}

void fmv_osd_state(void)
{
    if (osd_visible) {
        osd_request(OSD_STEP_STATE);
    }
}

void fmv_osd_close(void)
{
    osd_visible = false;
    osd_next = OSD_STEP_BLANK;
}

void fmv_osd_work(const fmv_osd_view *view)
{
    u8 count;

    for (count = 0u; count < OSD_STEP_DONE && osd_next < OSD_STEP_DONE; count++) {
        if (fmv_budget_lines() < osd_lines[osd_next]) {
            return;
        }
        osd_run(osd_next, view);
        osd_next++;
    }
}

void fmv_osd_show(const fmv_osd_view *view)
{
    u8 step;

    static_assert(OSD_STATE_SPRITE + 1u == OSD_SPRITES, "the overlay owns the first sprites");
    static_assert(OSD_TILE_PARTIAL < OSD_FIRST_TILE + 16u, "the bar tiles stay in the hidden rows");
    fmv_osd_open();
    for (step = OSD_STEP_INKS; step < OSD_STEP_DONE; step++) {
        osd_run(step, view);
    }
    osd_next = OSD_STEP_DONE;
}
