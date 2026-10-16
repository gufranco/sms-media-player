#include "fmv/mediaplayer.h"

#include "fmv/assert.h"
#include "fmv/seek.h"

#define BANK_WINDOW 0x8000u
#define BANK_SELECT 0xFFFFu
#define BANK_END    0xC000u

volatile u16 movie_cursor;
volatile u8 movie_bank;
volatile u8 movie_kind;
volatile u8 movie_last_bank;
volatile u8 movie_muted;
volatile u8 movie_inks;
volatile u16 movie_defers;
static volatile u16 movie_frames;

void movie_replay(void);

void fmv_movie_start(u8 first_bank, u8 bank_count)
{
    FMV_ASSERT(first_bank != 0u);
    FMV_ASSERT(bank_count != 0u);

    movie_bank = first_bank;
    movie_last_bank = (u8)(first_bank + bank_count - 1u);
    *(volatile u8 *)BANK_SELECT = first_bank;
    movie_cursor = BANK_WINDOW;
    movie_kind = FMV_CHUNK_MORE;
    movie_frames = 0u;
    movie_defers = 0u;
}

void fmv_movie_chunk(void)
{
    FMV_ASSERT(movie_cursor >= BANK_WINDOW);
    FMV_ASSERT(movie_cursor < BANK_END);
    FMV_ASSERT(movie_bank != 0u);

    movie_replay();
    if (movie_kind == FMV_CHUNK_FRAME) {
        movie_frames++;
    }
}

u8 fmv_movie_last_kind(void)
{
    return movie_kind;
}

u16 fmv_movie_frames(void)
{
    return movie_frames;
}

void fmv_movie_set_muted(u8 muted)
{
    movie_muted = muted;
}

u8 fmv_movie_muted(void)
{
    return movie_muted;
}

void fmv_movie_set_inks(u8 inks)
{
    movie_inks = inks;
}

u8 fmv_movie_bank(void)
{
    return movie_bank;
}

u16 fmv_movie_defers(void)
{
    return movie_defers;
}

void fmv_movie_seek(const fmv_key *key)
{
    FMV_ASSERT(key->bank != 0u);
    FMV_ASSERT(key->bank <= movie_last_bank);

    movie_bank = key->bank;
    *(volatile u8 *)BANK_SELECT = key->bank;
    movie_cursor = (u16)(BANK_WINDOW + key->offset);
    movie_kind = FMV_CHUNK_MORE;
    movie_frames = key->frame;
}
