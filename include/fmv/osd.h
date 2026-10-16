#ifndef FMV_OSD_H
#define FMV_OSD_H

#include "fmv/types.h"

typedef struct {
    u32 elapsed_fields;
    u32 total_fields;
} fmv_position;

void fmv_osd_show(const fmv_position *where);
void fmv_osd_hide(void);

#endif
