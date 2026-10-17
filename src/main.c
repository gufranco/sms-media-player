#include "SMSlib.h"
#include "assets.h"
#include "fmv/console.h"
#include "fmv/diag.h"
#include "fmv/mediaplayer.h"
#include "fmv/osd.h"
#include "fmv/pause.h"
#include "fmv/psg.h"
#include "fmv/screen.h"
#include "fmv/transport.h"
#include "fmv/types.h"
#include "movie.h"
#include "version_numbers.h"

typedef enum {
    FMV_OUTCOME_ENDED = 0,
    FMV_OUTCOME_RESTART = 1,
    FMV_OUTCOME_STOP = 2,
    FMV_OUTCOME_FAULT = 3,
    FMV_OUTCOME_PLAYING = 4
} fmv_outcome;

SMS_EMBED_SEGA_ROM_HEADER(0, 0);
SMS_EMBED_SDSC_HEADER(FMV_VERSION_MAJOR, FMV_VERSION_MINOR, 2026, 9, 4,
                      "gufranco",
                      FMV_PLAYER_NAME,
                      FMV_KEYS_TEXT);

static fmv_osd_view view;
static fmv_transport transport;
static bool diag_shown;
static const fmv_key movie_keys[MOVIE_KEYS] = MOVIE_KEY_TABLE;

static void hold_last_frame(void)
{
    u16 field;

    for (field = 0u; field < (u16)MOVIE_HOLD_FIELDS; field++) {
        SMS_waitForVBlank();
    }
}

static void read_input(void)
{
    transport.pressed = (u16)SMS_getKeysPressed();
    transport.pause = (u8)fmv_pause_requested(transport.pressed);
}

static fmv_diagnostics diagnostics(void)
{
    const fmv_diagnostics seen = {
        fmv_movie_frames(), MOVIE_FRAMES, fmv_movie_bank(), fmv_movie_defers(),
    };

    return seen;
}

static void show_inks(void)
{
    fmv_movie_set_inks((u8)(transport.overlay_fields != 0u || diag_shown));
}

static void seek(s8 direction)
{
    const fmv_seek_query query = {movie_keys, (u8)MOVIE_KEYS, view.where.elapsed_fields, direction};
    const u8 target = fmv_seek_target(&query);

    static_assert(MOVIE_KEYS >= 1u && MOVIE_KEYS <= FMV_SEEK_MAX, "seek points fit one byte");
    if (target == FMV_SEEK_NONE) {
        return;
    }
    fmv_psg_silence();
    fmv_screen_reset();
    fmv_movie_seek(&movie_keys[target]);
    view.where.elapsed_fields = movie_keys[target].field;
    fmv_osd_open();
    if (diag_shown) {
        fmv_diag_open();
    }
}

static void show_diagnostics_now(void)
{
    const fmv_diagnostics seen = diagnostics();

    fmv_diag_show(&seen);
}

static void toggle_diagnostics(bool paced)
{
    diag_shown = !diag_shown;
    if (!diag_shown) {
        fmv_diag_hide();
    } else if (paced) {
        fmv_diag_open();
    } else {
        show_diagnostics_now();
    }
}

static void wait_for_resume(void)
{
    u16 actions;

    fmv_psg_silence();
    fmv_pause_clear();
    SMS_waitForVBlank();
    view.paused = 1u;
    fmv_osd_show(&view);
    if (diag_shown) {
        show_diagnostics_now();
    }
    do {
        SMS_waitForVBlank();
        read_input();
        actions = fmv_transport_paused(&transport);
        if ((actions & FMV_ACT_DIAG) != 0u) {
            toggle_diagnostics(false);
        }
    } while ((actions & FMV_ACT_RESUME) == 0u);
    fmv_pause_clear();
    view.paused = 0u;
    fmv_osd_state();
    show_inks();
}

static void wait_for_wake(void)
{
    fmv_pause_clear();
    do {
        SMS_waitForVBlank();
        read_input();
    } while (!fmv_transport_wakes(&transport));
    fmv_pause_clear();
}

static void toggle_sound(void)
{
    const u8 muted = (u8)(fmv_movie_muted() ^ 1u);

    fmv_movie_set_muted(muted);
    view.muted = muted;
    if (muted != 0u) {
        fmv_psg_silence();
    }
}

static void boot(void)
{
    fmv_psg_silence();
    fmv_screen_reset();
}

static void apply_overlay(u16 actions)
{
    if ((actions & FMV_ACT_SHOW) != 0u) {
        fmv_osd_open();
    }
    if ((actions & FMV_ACT_REFRESH) != 0u) {
        fmv_osd_state();
    }
    if ((actions & FMV_ACT_HIDE) != 0u) {
        fmv_osd_close();
    }
    if ((actions & FMV_ACT_TICK) != 0u) {
        fmv_osd_tick();
    }
    if ((actions & FMV_ACT_TICK) != 0u && diag_shown) {
        fmv_diag_open();
    }
    show_inks();
}

static fmv_outcome handle_input(void)
{
    u16 actions;

    read_input();
    if (transport.pause != 0u) {
        wait_for_resume();
        read_input();
    }
    actions = fmv_transport_playing(&transport);
    if ((actions & FMV_ACT_MUTE) != 0u) {
        toggle_sound();
    }
    if ((actions & FMV_ACT_BACK) != 0u) {
        seek(FMV_SEEK_BACK);
    }
    if ((actions & FMV_ACT_AHEAD) != 0u) {
        seek(FMV_SEEK_AHEAD);
    }
    if ((actions & FMV_ACT_DIAG) != 0u) {
        toggle_diagnostics(true);
    }
    apply_overlay(actions);
    if ((actions & FMV_ACT_STOP) != 0u) {
        return FMV_OUTCOME_STOP;
    }
    return (actions & FMV_ACT_RESTART) != 0u ? FMV_OUTCOME_RESTART : FMV_OUTCOME_PLAYING;
}

static void draw_overlays(void)
{
    fmv_osd_work(&view);
    if (diag_shown) {
        const fmv_diagnostics seen = diagnostics();

        fmv_diag_work(&seen);
    }
}

static void begin(void)
{
    fmv_movie_start((u8)MOVIE_FIRST_BANK, (u8)MOVIE_BANKS);
    view.where.elapsed_fields = 0u;
    view.where.total_fields = MOVIE_FIELDS;
    view.paused = 0u;
    view.muted = fmv_movie_muted();
    fmv_transport_begin(&transport);
    fmv_osd_open();
    if (diag_shown) {
        fmv_diag_open();
    }
    show_inks();
}

static fmv_outcome play_once(void)
{
    static_assert(MOVIE_FRAMES > 0u, "a film needs at least one frame");
    static_assert(MOVIE_BANKS > 0u, "a film needs at least one bank");

    begin();
    while (fmv_movie_frames() < MOVIE_FRAMES) {
        fmv_outcome outcome;

        SMS_waitForVBlank();
        fmv_movie_chunk();
        view.where.elapsed_fields++;
        if (fmv_movie_last_kind() == FMV_CHUNK_BAD) {
            return FMV_OUTCOME_FAULT;
        }
        outcome = handle_input();
        if (outcome != FMV_OUTCOME_PLAYING) {
            return outcome;
        }
        draw_overlays();
    }

    return FMV_OUTCOME_ENDED;
}

void main(void)
{
    boot();

    for (;;) {
        const fmv_outcome outcome = play_once();

        if (outcome == FMV_OUTCOME_ENDED) {
            hold_last_frame();
        }
        fmv_screen_reset();
        if (outcome == FMV_OUTCOME_FAULT) {
            fmv_screen_fault();
            for (;;) {
                SMS_waitForVBlank();
            }
        }
        if (outcome == FMV_OUTCOME_STOP) {
            wait_for_wake();
        }
    }
}
