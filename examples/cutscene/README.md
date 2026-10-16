# Cutscene example

A minimal game that plays a film and carries on. It exists to prove one
claim: a developer can take the folder the baker emits, include it from a
project they already have, and build a game with it.

It is built the way a developer would build it. [`Makefile`](Makefile)
includes the bundle's own `fmv.mk` fragment and links the player library
next to its own [`main.c`](main.c). Nothing in this directory edits a file
the baker emitted. The bundle's own guide shows the same few lines.

## What it does

1. Clears the screen with `fmv_screen_reset`.
2. Plays the film one chunk per vertical blank until its last frame, and
   stops early on a bad chunk.
3. Silences the PSG with `fmv_psg_silence`.
4. Clears the screen again and waits there.

Step 4 is the part that matters. The game gets the machine back after the
film and keeps running on its own loop.

## Building it

```bash
uv --project tools run python -m smsmedia.cartridge my-film.mp4 \
    --bundle build/bundle

make example
```

`make example` builds inside the pinned toolchain image. The Makefile reads
the bundle from `build/bundle` by default. Pass `FMV_DIR` to point it at
another folder. The game lands in `examples/cutscene/build/cutscene.sms`.

## What it does not cover

The example has no input. It does not skip the film, and it does not draw a
screen of its own afterwards. CI builds it on every pull request and every
push to main, so a bundle that no longer compiles fails there. Nothing runs
the built game.
