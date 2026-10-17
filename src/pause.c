#include "fmv/pause.h"

#include "SMSlib.h"

#ifdef TARGET_GG
bool fmv_pause_requested(u16 pressed)
{
    return (pressed & GG_KEY_START) != 0u;
}

void fmv_pause_clear(void)
{
}
#else
bool fmv_pause_requested(u16 pressed)
{
    (void)pressed;
    return SMS_queryPauseRequested();
}

void fmv_pause_clear(void)
{
    SMS_resetPauseRequest();
}
#endif
