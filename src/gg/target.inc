        CLOSE_KIND = 0x07
        CLOSE_BYTES = 64
        INK_ENTRY = 0x3C
        INK_COUNT = 4
        .macro INK_BYTES
        .db 0x00, 0x00, 0xFF, 0x0F
        .endm
