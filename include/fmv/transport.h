#ifndef FMV_TRANSPORT_H
#define FMV_TRANSPORT_H

#include "fmv/types.h"

#define FMV_TRANSPORT_OVERLAY_FIELDS 180u
#define FMV_TRANSPORT_TICK_FIELDS    60u

#define FMV_ACT_MUTE    0x0001u
#define FMV_ACT_BACK    0x0002u
#define FMV_ACT_AHEAD   0x0004u
#define FMV_ACT_DIAG    0x0008u
#define FMV_ACT_RESTART 0x0010u
#define FMV_ACT_STOP    0x0020u
#define FMV_ACT_SHOW    0x0040u
#define FMV_ACT_REFRESH 0x0080u
#define FMV_ACT_HIDE    0x0100u
#define FMV_ACT_TICK    0x0200u
#define FMV_ACT_RESUME  0x0400u

typedef struct {
    u16 pressed;
    u8 pause;
    u8 overlay_fields;
    u8 tick_fields;
} fmv_transport;

void fmv_transport_begin(fmv_transport *transport);
u16 fmv_transport_playing(fmv_transport *transport);
u16 fmv_transport_paused(fmv_transport *transport);
bool fmv_transport_wakes(const fmv_transport *transport);

#endif
