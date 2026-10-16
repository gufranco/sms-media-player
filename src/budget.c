#include "fmv/budget.h"

#include "SMSlib.h"

u8 fmv_budget_lines(void)
{
    const u8 line = SMS_getVCount();

    if (line >= FMV_BUDGET_DISPLAY_LINES) {
        return FMV_BUDGET_DISPLAY_LINES;
    }
    return (u8)(FMV_BUDGET_DISPLAY_LINES - line);
}
