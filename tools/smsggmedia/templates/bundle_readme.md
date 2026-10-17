# A film for your {console} game

This folder plays one baked film inside your own devkitSMS project. It was written against the film it carries: {seconds} seconds, {frames} frames over {fields} fields, {banks} banks of 16 KB, a picture of {columns} by {rows} cells, {keys} seek points, sound {sound}. Library version {version}.

## What is here

| Path | What it holds |
|---|---|
| `src/` | The replay and the player library, as source |
| `include/fmv/` | The library's headers |
| `movie/movie.h` | The film's figures: banks, frames, fields, seek points |
| `movie/assets/movie.bin` | The baked film, split into banks by `assets2banks` |
| `fmv.mk` | A make fragment that builds the library and the film's banks |
| `target.mk` | The console the film was baked for, which picks the replay's settings and `{library}` |

## Build it

Copy this folder into your project, for example as `fmv/`, and include the fragment from your Makefile inside the devkitSMS toolchain image:

```make
FMV_DIR := fmv
FMV_FIRST_BANK := 2
include $(FMV_DIR)/fmv.mk

game.ihx: main.rel $(FMV_OBJECTS) $(FMV_ASSET_HDR)
	sdcc -mz80 --sdcccall 1 --no-std-crt0 --data-loc 0xC000 $(FMV_BANK_FLAGS) -o $@ \
	    $(CRT0)/crt0_sms.rel main.rel $(FMV_OBJECTS) $(FMV_BANK_RELS) $(SMSLIB)/$(FMV_SMSLIB_LIB)
```

`FMV_FIRST_BANK` is the first 16 KB bank the film may take. Put it after your own code and data.

## Play it

```c
#include "SMSlib.h"
#include "assets.h"
#include "fmv/mediaplayer.h"
#include "fmv/screen.h"
#include "movie.h"

static void play_film(void)
{{
    fmv_screen_rest();
    fmv_movie_start((u8)MOVIE_FIRST_BANK, (u8)MOVIE_BANKS);
    while (fmv_movie_frames() < MOVIE_FRAMES) {{
        SMS_waitForVBlank();
        fmv_movie_chunk();
        if (fmv_movie_last_kind() == FMV_CHUNK_BAD) {{
            break;
        }}
    }}
}}
```

Call `fmv_movie_chunk` once a field, right after the vertical blank begins. `fmv_movie_seek` with an entry of `MOVIE_KEY_TABLE`, after `fmv_screen_rest`, resumes at a seek point. `fmv_screen_rest` silences the PSG and clears the screen; `fmv_screen_reset` clears the screen alone.

## What the film takes over

- All of VRAM: patterns from `0x0000` to `0x2FFF`, name tables at `0x3000` and `0x3800`, the sprite table at `0x3F00`. Reload your own graphics when the film ends.
- The mapper's slot 2 window at `0x8000` while it plays, and banks `FMV_FIRST_BANK` onwards.
- The PSG, when the film has sound. Call `fmv_screen_rest` when the film ends, or `fmv_psg_silence` to keep the screen, so the last note does not sound on.
- Every cycle of each field: run no other VDP writes and no line interrupts while it plays.

Nothing in this folder has run on hardware unless the player's own repository says so.
