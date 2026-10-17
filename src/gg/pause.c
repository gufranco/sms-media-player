#include "fmv/pause.h"

#include "SMSlib.h"

bool fmv_pause_requested(u16 pressed)
{
    return (pressed & GG_KEY_START) != 0u;
}

void fmv_pause_clear(void)
{
}
