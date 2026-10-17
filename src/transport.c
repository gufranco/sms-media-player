#include "fmv/transport.h"

#include "SMSlib.h"
#include "fmv/assert.h"

#define TRANSPORT_MUTE_KEYS    PORT_A_KEY_UP
#define TRANSPORT_DIAG_KEYS    PORT_A_KEY_DOWN
#define TRANSPORT_BACK_KEYS    PORT_A_KEY_LEFT
#define TRANSPORT_AHEAD_KEYS   PORT_A_KEY_RIGHT
#define TRANSPORT_RESTART_KEYS PORT_A_KEY_1
#define TRANSPORT_STOP_KEYS    PORT_A_KEY_2
#define TRANSPORT_PAUSED_DIAG  (PORT_A_KEY_1 | PORT_A_KEY_DOWN)
#define TRANSPORT_WAKE_KEYS    (PORT_A_KEY_1 | PORT_A_KEY_2)
#define TRANSPORT_SHOW_KEYS    (PORT_A_KEY_UP | PORT_A_KEY_DOWN | PORT_A_KEY_LEFT \
                                | PORT_A_KEY_RIGHT | PORT_A_KEY_1)

static u16 transport_keys(u16 pressed)
{
    u16 actions = 0u;

    if ((pressed & TRANSPORT_MUTE_KEYS) != 0u) {
        actions |= FMV_ACT_MUTE;
    }
    if ((pressed & TRANSPORT_DIAG_KEYS) != 0u) {
        actions |= FMV_ACT_DIAG;
    }
    if ((pressed & TRANSPORT_BACK_KEYS) != 0u) {
        actions |= FMV_ACT_BACK;
    }
    if ((pressed & TRANSPORT_AHEAD_KEYS) != 0u) {
        actions |= FMV_ACT_AHEAD;
    }
    if ((pressed & TRANSPORT_RESTART_KEYS) != 0u) {
        actions |= FMV_ACT_RESTART;
    }
    if ((pressed & TRANSPORT_STOP_KEYS) != 0u) {
        actions |= FMV_ACT_STOP;
    }
    return actions;
}

static u16 transport_show(fmv_transport *transport)
{
    const u16 shown = transport->overlay_fields == 0u ? FMV_ACT_SHOW : FMV_ACT_REFRESH;

    transport->overlay_fields = FMV_TRANSPORT_OVERLAY_FIELDS;
    return shown;
}

static u16 transport_overlay(fmv_transport *transport)
{
    if ((transport->pressed & TRANSPORT_SHOW_KEYS) != 0u) {
        return transport_show(transport);
    }
    if (transport->overlay_fields == 0u) {
        return 0u;
    }
    transport->overlay_fields--;
    return transport->overlay_fields == 0u ? FMV_ACT_HIDE : 0u;
}

static u16 transport_tick(fmv_transport *transport)
{
    transport->tick_fields++;
    if (transport->tick_fields < FMV_TRANSPORT_TICK_FIELDS) {
        return 0u;
    }
    transport->tick_fields = 0u;
    return FMV_ACT_TICK;
}

void fmv_transport_begin(fmv_transport *transport)
{
    transport->overlay_fields = FMV_TRANSPORT_OVERLAY_FIELDS;
    transport->tick_fields = 0u;
}

u16 fmv_transport_playing(fmv_transport *transport)
{
    FMV_ASSERT(transport->overlay_fields <= FMV_TRANSPORT_OVERLAY_FIELDS);
    FMV_ASSERT(transport->tick_fields < FMV_TRANSPORT_TICK_FIELDS);

    const u16 keys = transport_keys(transport->pressed);
    const u16 overlay = transport_overlay(transport);

    return (u16)(keys | overlay | transport_tick(transport));
}

u16 fmv_transport_paused(fmv_transport *transport)
{
    FMV_ASSERT(transport->overlay_fields <= FMV_TRANSPORT_OVERLAY_FIELDS);
    FMV_ASSERT(transport->pause <= 1u);

    if (transport->pause != 0u) {
        transport->overlay_fields = FMV_TRANSPORT_OVERLAY_FIELDS;
        return FMV_ACT_RESUME;
    }
    return (transport->pressed & TRANSPORT_PAUSED_DIAG) != 0u ? FMV_ACT_DIAG : 0u;
}

bool fmv_transport_wakes(const fmv_transport *transport)
{
    return transport->pause != 0u || (transport->pressed & TRANSPORT_WAKE_KEYS) != 0u;
}
