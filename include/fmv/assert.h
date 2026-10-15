#ifndef FMV_ASSERT_H
#define FMV_ASSERT_H

#include "fmv/types.h"

void fmv_assert_fail(u16 line);

#define FMV_ASSERT(cond) \
    do { if (!(cond)) { fmv_assert_fail((u16)__LINE__); } } while (0)

#endif
