#include "SMSlib.h"
#include "assets.h"
#include "fmv/mediaplayer.h"
#include "fmv/psg.h"
#include "fmv/screen.h"
#include "movie.h"

SMS_EMBED_SEGA_ROM_HEADER(0, 0);

static void play_film(void)
{
    fmv_screen_reset();
    fmv_movie_start((u8)MOVIE_FIRST_BANK, (u8)MOVIE_BANKS);
    while (fmv_movie_frames() < MOVIE_FRAMES) {
        SMS_waitForVBlank();
        fmv_movie_chunk();
        if (fmv_movie_last_kind() == FMV_CHUNK_BAD) {
            break;
        }
    }
    fmv_psg_silence();
}

void main(void)
{
    play_film();
    fmv_screen_reset();
    for (;;) {
        SMS_waitForVBlank();
    }
}
