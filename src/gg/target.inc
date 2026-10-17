        CLOSE_KIND = 0x07
        CLOSE_BYTES = 64
        INK_ENTRY = 0x3C
        INK_COUNT = 4
        .macro INK_BYTES
        .db 0x00, 0x00, 0xFF, 0x0F
        .endm
        PAN_KIND = 0x08
        PAN_PORT = 0x06
        PAN_CENTRE = 0xFF
        .macro PAN_DISPATCH
        cp  a, #PAN_KIND
        jr  z, mvpan
        .endm
        .macro PAN_RUN
mvpan:
        inc hl
        ld  a, (hl)
        inc hl
        out (#PAN_PORT), a
        jp  mvloop
        .endm
        .macro PAN_RESET
        ld  a, #PAN_CENTRE
        out (#PAN_PORT), a
        .endm
