        .module vdp

        .globl _fmv_screen_table

        .area _CODE

_fmv_screen_table::
        di
        out (#0xBF), a
        ld  a, #0x82
        nop
        nop
        nop
        out (#0xBF), a
        ei
        ret
