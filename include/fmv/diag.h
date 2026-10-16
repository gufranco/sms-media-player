#ifndef FMV_DIAG_H
#define FMV_DIAG_H

#include "fmv/types.h"

typedef struct {
    u16 frame;
    u16 total_frames;
    u8 bank;
    u16 defers;
} fmv_diagnostics;

void fmv_diag_open(void);
void fmv_diag_work(const fmv_diagnostics *seen);
void fmv_diag_show(const fmv_diagnostics *seen);
void fmv_diag_hide(void);

#endif
