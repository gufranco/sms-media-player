#ifndef FMV_SEEK_H
#define FMV_SEEK_H

#include "fmv/types.h"

typedef struct {
    u8 bank;
    u16 offset;
    u16 frame;
    u32 field;
} fmv_key;

#define FMV_SEEK_NONE   0xFFu
#define FMV_SEEK_MAX    254u
#define FMV_SEEK_BACK   (-1)
#define FMV_SEEK_AHEAD  1

typedef struct {
    const fmv_key *keys;
    u8 count;
    u32 elapsed_fields;
    s8 direction;
} fmv_seek_query;

u8 fmv_seek_target(const fmv_seek_query *query);

#endif
