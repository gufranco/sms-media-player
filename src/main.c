#include "SMSlib.h"
#include "assets.h"
#include "fmv/mediaplayer.h"
#include "fmv/psg.h"
#include "fmv/screen.h"
#include "fmv/types.h"
#include "movie.h"
#include "version_numbers.h"

#define FMV_RESTART_KEYS PORT_A_KEY_1
#define FMV_EXIT_KEYS    PORT_A_KEY_2
#define FMV_MUTE_KEYS    PORT_A_KEY_UP

typedef enum {
    FMV_OUTCOME_ENDED = 0,
    FMV_OUTCOME_RESTART = 1,
    FMV_OUTCOME_EXIT = 2,
    FMV_OUTCOME_FAULT = 3
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

static void wait_for_resume(void)
{
    fmv_psg_silence();
    SMS_resetPauseRequest();
    while (!SMS_queryPauseRequested()) {
        SMS_waitForVBlank();
    }
    SMS_resetPauseRequest();
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

static fmv_outcome play_once(void)
{
    static_assert(MOVIE_FRAMES > 0u, "a film needs at least one frame");
    static_assert(MOVIE_BANKS > 0u, "a film needs at least one bank");

    fmv_movie_start((u8)MOVIE_FIRST_BANK, (u8)MOVIE_BANKS);

    while (fmv_movie_frames() < MOVIE_FRAMES) {
        u16 pressed;

        SMS_waitForVBlank();
        fmv_movie_chunk();
        if (fmv_movie_last_kind() == FMV_CHUNK_BAD) {
            return FMV_OUTCOME_FAULT;
        }
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
