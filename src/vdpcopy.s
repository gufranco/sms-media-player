        .module vdpcopy

        .globl _fmv_vdp_copy

        .area _CODE

_fmv_vdp_copy::
        di
        ld  a, (hl)
        inc hl
        out (#0xBF), a
        ld  a, (hl)
        inc hl
        nop
        nop
        out (#0xBF), a
        ei
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        inc hl
        ld  b, (hl)
        ex  de, hl
        ld  c, #0xBE
fmvvdpcopy:
        outi
        nop
        jp  nz, fmvvdpcopy
        ret
