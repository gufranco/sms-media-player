        .module replay

        .globl _movie_replay
        .globl _movie_cursor
        .globl _movie_bank
        .globl _movie_kind
        .globl _movie_last_bank
        .globl _movie_muted

        CHUNK_BAD = 0x80

        .area _CODE

_movie_replay::
        ld  hl, (_movie_cursor)

mvloop:
        ld  a, (hl)
        cp  a, #0x02
        jr  z, mvvram
        cp  a, #0x05
        jr  z, mvclose
        cp  a, #0xFF
        jp  z, mvbank
        cp  a, #0x06
        jr  z, mvpsg
        cp  a, #0x02
        jr  nc, mvbad

        inc hl
        ld  (_movie_cursor), hl
        ld  (_movie_kind), a
        ret

mvdefer:
        ld  (_movie_cursor), hl
        xor a, a
        ld  (_movie_kind), a
        ret

mvbad:
        ld  (_movie_cursor), hl
        ld  a, #CHUNK_BAD
        ld  (_movie_kind), a
        ret

mvvram:
        inc hl
        di
        ld  a, (hl)
        inc hl
        out (#0xBF), a
        ld  a, (hl)
        inc hl
        or  a, #0x40
        out (#0xBF), a
        ei
        ld  b, (hl)
        inc hl
        jr  mvpace

mvpace:
        ld  c, #0xBE
mvpaced:
        outi
        nop
        jp  nz, mvpaced
        jp  mvloop

mvpsg:
        inc hl
        ld  b, (hl)
        inc hl
        ld  a, (_movie_muted)
        or  a, a
        jr  nz, mvpsgskip
        ld  c, #0x7F
mvpsgpaced:
        outi
        nop
        nop
        jp  nz, mvpsgpaced
        jp  mvloop

mvpsgskip:
        ld  e, b
        ld  d, #0x00
        add hl, de
        jp  mvloop

mvclose:
        in  a, (#0x7E)
        cp  a, #0xC0
        jr  c, mvdefer
        cp  a, #0xE0
        jr  nc, mvdefer
        inc hl
        di
        ld  a, (hl)
        inc hl
        out (#0xBF), a
        ld  a, #0x82
        nop
        nop
        nop
        out (#0xBF), a
        ld  a, #0x00
        nop
        nop
        nop
        out (#0xBF), a
        ld  a, #0xC0
        nop
        nop
        nop
        out (#0xBF), a
        ei
        ld  c, #0xBE
fmvcopy:
        .rept 32
        outi
        .endm
fmvdone:
        jp  mvloop

mvbank:
        ld  a, (_movie_last_bank)
        ld  b, a
        ld  a, (_movie_bank)
        cp  a, b
        jp  nc, mvbad
        inc a
        ld  (_movie_bank), a
        ld  (0xFFFF), a
        ld  hl, #0x8000
        jp  mvloop
