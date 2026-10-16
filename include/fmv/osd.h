#ifndef FMV_OSD_H
#define FMV_OSD_H

#include "fmv/types.h"

#define FMV_OSD_SPRITES 15u

typedef struct {
    u32 elapsed_fields;
    u32 total_fields;
} fmv_position;

typedef struct {
    fmv_position where;
    u8 paused;
    u8 muted;
} fmv_osd_view;

void fmv_osd_inks(void);
void fmv_osd_open(void);
void fmv_osd_tick(void);
void fmv_osd_state(void);
void fmv_osd_close(void);
void fmv_osd_work(const fmv_osd_view *view);
void fmv_osd_show(const fmv_osd_view *view);

#endif
