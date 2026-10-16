#include "SMSlib.h"
#include "assets.h"
#include "fmv/diag.h"
#include "fmv/mediaplayer.h"
#include "fmv/osd.h"
#include "fmv/psg.h"
#include "fmv/screen.h"
#include "fmv/types.h"
#include "movie.h"
#include "version_numbers.h"

#define FMV_RESTART_KEYS PORT_A_KEY_1
#define FMV_EXIT_KEYS    PORT_A_KEY_2
#define FMV_MUTE_KEYS    PORT_A_KEY_UP
#define FMV_DIAG_KEYS    PORT_A_KEY_1

typedef enum {
    FMV_OUTCOME_ENDED = 0,
    FMV_OUTCOME_RESTART = 1,
    FMV_OUTCOME_EXIT = 2,
    FMV_OUTCOME_FAULT = 3,
    FMV_OUTCOME_PLAYING = 4
} fmv_outcome;

SMS_EMBED_SEGA_ROM_HEADER(0, 0);
SMS_EMBED_SDSC_HEADER(FMV_VERSION_MAJOR, FMV_VERSION_MINOR, 2026, 9, 4,
                      "gufranco",
                      "SMS Media Player",
                      "Button 1 restarts, 2 exits, Pause pauses, Up mutes");

static void hold_last_frame(void)
{
    u16 field;

    for (field = 0u; field < (u16)MOVIE_HOLD_FIELDS; field++) {
        SMS_waitForVBlank();
    }
}

static fmv_position position;

static bool toggle_diagnostics(bool shown)
{
    fmv_diagnostics seen;

    if ((SMS_getKeysPressed() & FMV_DIAG_KEYS) == 0u) {
        return shown;
    }
    if (shown) {
        fmv_diag_hide();
        return false;
    }
    seen.frame = fmv_movie_frames();
    seen.total_frames = MOVIE_FRAMES;
    seen.bank = fmv_movie_bank();
    seen.defers = fmv_movie_defers();
    fmv_diag_show(&seen);
    return true;
}

static void wait_for_resume(void)
{
    bool shown = false;

    fmv_psg_silence();
    SMS_resetPauseRequest();
    SMS_waitForVBlank();
    fmv_osd_show(&position);
    while (!SMS_queryPauseRequested()) {
        SMS_waitForVBlank();
        shown = toggle_diagnostics(shown);
    }
    SMS_resetPauseRequest();
    fmv_osd_hide();
}

static void toggle_sound(void)
{
    const u8 muted = (u8)(fmv_movie_muted() ^ 1u);

    fmv_movie_set_muted(muted);
    if (muted != 0u) {
        fmv_psg_silence();
    }
}

static void boot(void)
{
    fmv_psg_silence();
    fmv_screen_reset();
}

static fmv_outcome handle_input(void)
{
    u16 pressed;

    if (SMS_queryPauseRequested()) {
        wait_for_resume();
    }
    pressed = (u16)SMS_getKeysPressed();
    if ((pressed & FMV_MUTE_KEYS) != 0u) {
        toggle_sound();
    }
    if ((pressed & FMV_EXIT_KEYS) != 0u) {
        return FMV_OUTCOME_EXIT;
    }
    if ((pressed & FMV_RESTART_KEYS) != 0u) {
        return FMV_OUTCOME_RESTART;
    }
    return FMV_OUTCOME_PLAYING;
}

static fmv_outcome play_once(void)
{
    static_assert(MOVIE_FRAMES > 0u, "a film needs at least one frame");
    static_assert(MOVIE_BANKS > 0u, "a film needs at least one bank");

    fmv_movie_start((u8)MOVIE_FIRST_BANK, (u8)MOVIE_BANKS);
    position.elapsed_fields = 0u;
    position.total_fields = MOVIE_FIELDS;

    while (fmv_movie_frames() < MOVIE_FRAMES) {
        fmv_outcome outcome;

        SMS_waitForVBlank();
        fmv_movie_chunk();
        position.elapsed_fields++;
        if (fmv_movie_last_kind() == FMV_CHUNK_BAD) {
            return FMV_OUTCOME_FAULT;
        }
        outcome = handle_input();
        if (outcome != FMV_OUTCOME_PLAYING) {
            return outcome;
        }
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
        }

        if (outcome == FMV_OUTCOME_EXIT || outcome == FMV_OUTCOME_FAULT) {
            for (;;) {
                SMS_waitForVBlank();
            }
        }
    }
}
