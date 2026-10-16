#include "fmv/seek.h"

#define SEEK_BACK_GRACE_FIELDS 120ul

static u8 seek_current(const fmv_seek_query *query)
{
    u8 index;
    u8 current = 0u;

    for (index = 1u; index < query->count; index++) {
        if (query->keys[index].field <= query->elapsed_fields) {
            current = index;
        }
    }
    return current;
}

u8 fmv_seek_target(const fmv_seek_query *query)
{
    const u8 current = seek_current(query);
    const u32 into = query->elapsed_fields - query->keys[current].field;

    if (query->direction > 0) {
        return (u8)(current + 1u) < query->count ? (u8)(current + 1u) : FMV_SEEK_NONE;
    }
    if (into < SEEK_BACK_GRACE_FIELDS && current > 0u) {
        return (u8)(current - 1u);
    }
    return current;
}
