#include "fmv/pause.h"

#include "SMSlib.h"

bool fmv_pause_requested(u16 pressed)
{
    (void)pressed;
    return SMS_queryPauseRequested();
}

void fmv_pause_clear(void)
{
    SMS_resetPauseRequest();
}
