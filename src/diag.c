#include "fmv/diag.h"

#include "fmv/budget.h"
#include "fmv/glyph.h"
#include "fmv/osd.h"
#include "fmv/vdpcopy.h"

#define DIAG_ROWS          2u
#define DIAG_ROW_TILES     5u
#define DIAG_ROW_CELLS     (DIAG_ROW_TILES * 2u)
#define DIAG_TILES         (DIAG_ROWS * DIAG_ROW_TILES)
#define DIAG_FIRST_SPRITE  FMV_OSD_SPRITES
#define DIAG_SAT_Y         (0x3F00u + DIAG_FIRST_SPRITE)
#define DIAG_SAT_XN        (0x3F80u + DIAG_FIRST_SPRITE * 2u)
#define DIAG_SPRITE_END    0xD0u
#define DIAG_SPRITE_PIXELS 8u
#define DIAG_X             108u
#define DIAG_TOP_Y         143u
#define DIAG_ROW_PITCH     12u
#define DIAG_MAX_FOUR      9999u
#define DIAG_MAX_TWO       99u
#define DIAG_THOUSAND      1000u
#define DIAG_HUNDRED       100u
#define DIAG_STEP_INKS     0u
#define DIAG_STEP_TOP      1u
#define DIAG_STEP_BOTTOM   2u
#define DIAG_STEP_TILE     3u
#define DIAG_STEP_PLACE    (DIAG_STEP_TILE + DIAG_TILES)
#define DIAG_STEP_DONE     (DIAG_STEP_PLACE + 1u)
#define DIAG_INK_LINES     10u
#define DIAG_TOP_LINES     63u
#define DIAG_BOTTOM_LINES  46u
#define DIAG_TILE_LINES    50u
#define DIAG_PLACE_LINES   30u

static const u8 diag_tiles[DIAG_TILES] = {185u, 186u, 187u, 188u, 189u, 190u, 191u, 240u, 241u, 242u};

static u8 diag_tile[FMV_GLYPH_TILE_BYTES];
static u8 diag_cells[DIAG_ROWS * DIAG_ROW_CELLS];
static u8 diag_next = DIAG_STEP_DONE;

static void diag_four(u8 at, u16 value)
{
    const u16 shown = value > DIAG_MAX_FOUR ? DIAG_MAX_FOUR : value;

    diag_cells[at] = (u8)(shown / DIAG_THOUSAND);
    diag_cells[at + 1u] = (u8)(shown / DIAG_HUNDRED % FMV_GLYPH_TENS);
    diag_cells[at + 2u] = (u8)(shown / FMV_GLYPH_TENS % FMV_GLYPH_TENS);
    diag_cells[at + 3u] = (u8)(shown % FMV_GLYPH_TENS);
}

static void diag_fill_top(const fmv_diagnostics *seen)
{
    diag_cells[0] = FMV_GLYPH_F;
    diag_four(1u, seen->frame);
    diag_cells[5] = FMV_GLYPH_SLASH;
    diag_four(6u, seen->total_frames);
}

static void diag_fill_bottom(const fmv_diagnostics *seen)
{
    const u8 bank = seen->bank > DIAG_MAX_TWO ? DIAG_MAX_TWO : seen->bank;

    diag_cells[10] = FMV_GLYPH_B;
    diag_cells[11] = (u8)(bank / FMV_GLYPH_TENS);
    diag_cells[12] = (u8)(bank % FMV_GLYPH_TENS);
    diag_cells[13] = FMV_GLYPH_BLANK;
    diag_cells[14] = FMV_GLYPH_D;
    diag_four(15u, seen->defers);
    diag_cells[19] = FMV_GLYPH_BLANK;
}

static void diag_upload(u8 tile)
{
    fmv_glyph_text(diag_tile, diag_cells[tile * 2u], diag_cells[tile * 2u + 1u]);
    fmv_glyph_upload(diag_tiles[tile], diag_tile);
}

static void diag_place(void)
{
    u8 ys[DIAG_TILES + 1u];
    u8 xn[DIAG_TILES * 2u];
    u8 sprite;
    u8 column = 0u;
    u8 y = DIAG_TOP_Y;

    for (sprite = 0u; sprite < DIAG_TILES; sprite++) {
        ys[sprite] = y;
        xn[sprite * 2u] = (u8)(DIAG_X + column * DIAG_SPRITE_PIXELS);
        xn[sprite * 2u + 1u] = diag_tiles[sprite];
        column++;
        if (column == DIAG_ROW_TILES) {
            column = 0u;
            y = (u8)(y + DIAG_ROW_PITCH);
        }
    }
    ys[DIAG_TILES] = DIAG_SPRITE_END;
    fmv_vdp_write(DIAG_SAT_XN, FMV_VDP_VRAM_WRITE, xn, (u8)sizeof xn);
    fmv_vdp_write(DIAG_SAT_Y, FMV_VDP_VRAM_WRITE, ys, (u8)sizeof ys);
}

static void diag_run(u8 step, const fmv_diagnostics *seen)
{
    switch (step) {
    case DIAG_STEP_INKS:
        fmv_osd_inks();
        break;
    case DIAG_STEP_TOP:
        diag_fill_top(seen);
        break;
    case DIAG_STEP_BOTTOM:
        diag_fill_bottom(seen);
        break;
    case DIAG_STEP_PLACE:
        diag_place();
        break;
    default:
        diag_upload((u8)(step - DIAG_STEP_TILE));
        break;
    }
}

static u8 diag_lines(u8 step)
{
    switch (step) {
    case DIAG_STEP_INKS:
        return DIAG_INK_LINES;
    case DIAG_STEP_TOP:
        return DIAG_TOP_LINES;
    case DIAG_STEP_BOTTOM:
        return DIAG_BOTTOM_LINES;
    case DIAG_STEP_PLACE:
        return DIAG_PLACE_LINES;
    default:
        return DIAG_TILE_LINES;
    }
}

void fmv_diag_open(void)
{
    diag_next = DIAG_STEP_INKS;
}

void fmv_diag_work(const fmv_diagnostics *seen)
{
    u8 count;

    for (count = 0u; count < DIAG_STEP_DONE && diag_next < DIAG_STEP_DONE; count++) {
        if (fmv_budget_lines() < diag_lines(diag_next)) {
            return;
        }
        diag_run(diag_next, seen);
        diag_next++;
    }
}

void fmv_diag_show(const fmv_diagnostics *seen)
{
    u8 step;

    for (step = DIAG_STEP_INKS; step < DIAG_STEP_DONE; step++) {
        diag_run(step, seen);
    }
    diag_next = DIAG_STEP_DONE;
}

void fmv_diag_hide(void)
{
    static const u8 end[1] = {DIAG_SPRITE_END};

    diag_next = DIAG_STEP_DONE;
    fmv_vdp_write(DIAG_SAT_Y, FMV_VDP_VRAM_WRITE, end, (u8)sizeof end);
}
