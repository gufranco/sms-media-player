#include "fmv/assert.h"

#include "SMSlib.h"
#include "fmv/console.h"

void fmv_assert_fail(u16 line)
{
    const fmv_colour colour = (fmv_colour)((line & 0x03u) | FMV_COLOUR_ASSERT);

    SMS_displayOff();
    for (;;) {
        fmv_set_sprite_colour(0u, colour);
        SMS_waitForVBlank();
    }
}
