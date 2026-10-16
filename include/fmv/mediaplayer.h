#ifndef FMV_MEDIAPLAYER_H
#define FMV_MEDIAPLAYER_H

#include "fmv/types.h"

#define FMV_CHUNK_MORE  0x00u
#define FMV_CHUNK_FRAME 0x01u
#define FMV_CHUNK_BAD   0x80u

void fmv_movie_start(u8 first_bank, u8 bank_count);
void fmv_movie_chunk(void);
u8 fmv_movie_last_kind(void);
u16 fmv_movie_frames(void);
void fmv_movie_set_muted(u8 muted);
u8 fmv_movie_muted(void);

#endif
