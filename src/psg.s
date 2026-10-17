        .module psg

        .globl _fmv_psg_silence

        PSG_PORT = 0x7F
        .include "target.inc"

        .area _CODE

_fmv_psg_silence::
        ld  a, #0x9F
        out (#PSG_PORT), a
        ld  a, #0xBF
        out (#PSG_PORT), a
        ld  a, #0xDF
        out (#PSG_PORT), a
        ld  a, #0xFF
        out (#PSG_PORT), a
        PAN_RESET
        ret
