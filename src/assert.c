#include "fmv/assert.h"

#include "SMSlib.h"

void fmv_assert_fail(u16 line)
{
    u8 colour = (u8)((line & 0x03u) | 0x30u);

    SMS_displayOff();
    for (;;) {
        SMS_setSpritePaletteColor(0u, colour);
        SMS_waitForVBlank();
    }
}
