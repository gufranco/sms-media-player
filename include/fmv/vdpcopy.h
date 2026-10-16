#ifndef FMV_VDPCOPY_H
#define FMV_VDPCOPY_H

#include "fmv/types.h"

#define FMV_VDP_VRAM_WRITE 0x40u
#define FMV_VDP_CRAM_WRITE 0xC0u

typedef struct {
    u8 low;
    u8 high;
    const u8 *source;
    u8 count;
} fmv_vdp_run;

void fmv_vdp_copy(const fmv_vdp_run *run);

static inline void fmv_vdp_write(u16 address, u8 code, const u8 *source, u8 count)
{
    const fmv_vdp_run run = {
        (u8)(address & 0xFFu), (u8)((address >> 8) | code), source, count,
    };

    fmv_vdp_copy(&run);
}

#endif
