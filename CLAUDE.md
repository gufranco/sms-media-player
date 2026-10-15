# Assistant guide

This file governs assistant behaviour in this repository. The full engineering
contract is in [AGENTS.md](AGENTS.md); read it first. This file adds only what an
assistant specifically needs to know.

## Everything must run on the original hardware

Owner's instruction, and it outranks every other section here: every change is
made with extreme care so that it runs on a real Master System. A clean
emulator run, a green test suite and a good-looking capture are all evidence
about an emulator, and none of them is evidence about the console.

- Before writing anything that reaches a port, the mapper, the interrupt or
  the ROM header, read "Original hardware is the only target" in
  [AGENTS.md](AGENTS.md) and hold its binding numbers.
- When a hardware figure is in doubt, the documented one binds over a looser
  community measurement.
- A change the console could disagree with is reported as unverified until
  the owner has run it on the Game Gear, and the report asks for that run.

## Every gate is a command

Nothing here is verified by compiling. Run the gate.

| Claim | Command |
|---|---|
| It builds | `make rom` |
| The C holds | `make analyse` |
| No VDP write pair is under its floor, and every blank copy is guarded | `make timing` and `SMSMOVIE_ROM_REQUIRED=1 pytest tools/tests/test_replay_on_z80.py`, after `make rom` |
| The baker holds | `uv --project tools run ruff format --check tools/`, `ruff check tools/`, `mypy tools/smsmovie tools/scripts` |
| The behaviour holds | `SMSMOVIE_CLIPS_REQUIRED=1 uv --project tools run python -m pytest tools/tests --cov=smsmovie --cov=tools/scripts --cov-config=tools/pyproject.toml --cov-fail-under=95` |
| A commit is clean | `.githooks/pre-commit`, installed once by `make hooks` |
| It runs on a console | the Game Gear, reported by the owner; nothing on this machine settles it |

## Do not ask what you can capture

When something is wrong on screen, record the emulator, cut the
recording into frames and read them. Screenshots go to `~/.mednafen/snaps` and
the snapshot command is bound to F9, which System Events can drive, so a run can
be captured without anyone watching it.

Handing back a description of what to look for is not a result. Neither is
asking which of two builds is better when both can be built and compared. Run
the loop yourself: capture, measure, change one thing, capture again. Ask only
when that loop has run and genuinely cannot settle the question, and say what
the loop showed when you do.

This is not a licence to trust a measurement. The record here is that several
metrics reported a large improvement on a change that was plainly worse, so a
capture answers what happened and never on its own what is better.

## Before changing anything

Run `make rom` and confirm it succeeds. A build that was already broken when you
arrived is the first thing to report, not something to work around.

## The picture fills the screen

256 by 192, the whole raster, no bars. A source of another shape is scaled
until it covers that and then cropped, so a 16:9 film loses about a quarter of
its width. Do not add letterboxing, do not pad, and do not treat bars as
harmless: they are encoded, they occupy pattern slots and they are transferred
every field.

`--rows` still builds a smaller picture and the library half needs it. The
rows it leaves over are held black by the player, and `tools/tests/
test_framing.py` holds them there.

Changing the picture size re-opens the tile cap, because the cap is bounded by
how many slots the displayed frame is not still using. The sweep that set the
constant in `tools/smsmovie/limits.py` is recorded under that module in
[tools/DESIGN.md](tools/DESIGN.md); re-run the sweep rather than guessing a new
one.

## A public member of a family

Owner's instruction, 2026-10-15: this project and aes-movie-player are public
members of one family, kept as alike as their hardware allows and sharing as
much code as possible.

## Openings are five seconds at most

Owner's figure, 2026-10-08: the openings this converts run five seconds at
most. At the full field budget that is about 33 of the 62 banks, so ROM is not
what limits a bake; the per-field transfer is. Spend the room on detail rather
than on running time.

Perceived image quality outranks frame rate, by the owner's word the same day.
When the two compete for bytes or slots, the picture wins; do not raise the
rate search above its current candidates to buy motion.

## Non-negotiables

- **Docker for every build.** Never suggest installing SDCC on the host, and
  never add a host-only build path. If Docker is unavailable, say so and stop.
- **C23 only**, and `constexpr` is unavailable in SDCC. Reach for `static const`
  or an `enum` instead.
- **NASA Power of 10** governs `src/` and `include/`. The mapping and the
  recorded exceptions are in [AGENTS.md](AGENTS.md). Adding an unbounded loop is
  a change to that table, not a local decision.
- **No comments or docstrings in source.** This is enforced by convention, not
  tooling. Put the explanation in the commit message, in [AGENTS.md](AGENTS.md),
  or, for why a baker module is shaped as it is, under that module in
  [tools/DESIGN.md](tools/DESIGN.md).
- **`make analyse` must pass** before you claim a change is done.
- **Never open an emulator fullscreen.** Always windowed, and minimised when the
  run exists only to produce a capture. See below.

## Emulators run windowed

A fullscreen emulator takes the display away from the user and does not give it
back until the process exits. Pass the flag explicitly every time rather than
trusting the stored config, which can carry fullscreen over from an earlier
session.

```
mednafen -video.fs 0 -sound 0 build/sms-movie-player.sms
```

For an unattended check, record and extract the frame afterwards rather than
sitting in front of it:

```
mednafen -video.fs 0 -sound 0 -qtrecord /tmp/run.mov build/sms-movie-player.sms
ffmpeg -i /tmp/run.mov -vf "select=eq(n\,90)" -vframes 1 /tmp/frame.png
```

## Verification, specifically

A change to rendering, banking, the transfer loop or the state machine is not
verified by compiling. Build the ROM and run it.

The transfer loop carries an obligation on top of that, and no emulator reports
it: consecutive VDP writes must be at least 16 cycles apart inside blanking and
at least 29 apart during active display. Writing faster during display drops
data on real hardware while working in emulation, which is a defect the prior art
on this platform hit and diagnosed. C cannot express instruction spacing, so a
build gate walks the compiled objects instead.

## Hardware numbers carry a source

Every constant tied to the VDP, the PSG, the mapper or the raster is cited in the
design notes. A figure derived by arithmetic is labelled as derived and is not
treated as measured until something has measured it. Do not introduce a hardware
constant from memory.

## Things that will bite you

- cppcheck fails on a failure branch that can never be taken. A function that
  cannot fail returns `void`; giving it a `bool` nobody can make false is an
  error here, not a style preference.
- `ihx2sms` detects a ROM bank per block linked at `0x8000`, so every bank needs
  its own `-Wl-b_BANKn=0x8000` flag, and the objects must be linked in ascending
  numeric order.
- SMSlib and crt0 are rebuilt inside the image so their calling convention
  matches the compiler default. Linking the prebuilt library produces
  conflicting-`sdcccall` errors.
- MAME's `sms` driver needs a BIOS ROM this repository does not ship, so it is
  not the verification path.
- mednafen refuses to start while another instance holds its lockfile, and the
  message names the base directory rather than the lock. Kill the stale process
  before recording. A run killed with SIGTERM leaves the `.mov` unfinalised at
  32 bytes, which reads as a failed emulator rather than a truncated capture.
- Running mypy on [`tools/scripts`](tools/scripts) alone poisons `.mypy_cache`:
  the next full run reports `Module "smsmovie" has no attribute ...` for
  imports that are fine. Always pass both `tools/smsmovie tools/scripts`, and
  if the error appears, delete `.mypy_cache` rather than chasing it.

## Hardware testing runs on a Game Gear

The owner has a Game Gear with an Everdrive, which runs Master System ROMs.
Ask for a run whenever the transfer loop changes, because that is the one
constraint nothing here can check and the one that has already shipped broken.

Be exact about what it proves. Same VDP core at the same clock, so write
timing is genuinely tested. Its palette is remapped onto the Game Gear's own,
so it says nothing exact about colour. And in Master System mode it shows only
the centre 160 by 144 of the 256 by 192 raster, so roughly 38% of the picture
is off-screen, including every row the band guard covers.

Report it as a Game Gear result. Do not let a clean handheld run stand in for
a colour check or an edge-of-screen check.

## Where the design lives

`specs/` holds the plan, the decision record and the sourced hardware
references. It is not committed. Read it before proposing a design change, and
update it in the same turn as any decision that contradicts it.

## There is no sound

Owner's instruction, 2026-10-08: the player converts game openings, and sound
support is removed entirely. The stream carries picture only and the player
never enables the line interrupt. The single PSG write left is full
attenuation at boot, because a console powers up with its tone channels
audible. Do not add a sound path back.

## How the picture is judged

Owner's instruction, 2026-10-08, later the same day as the pixel perfect rule:
dithering is allowed when it raises image quality. Nothing aimed at a CRT comes
back: no composite model, no technique that needs a display to blend colours
the console cannot show on a sharp screen.

A dither moves pixels away from the source on purpose, so a per-pixel error
always scores it as loss. Judge it two ways and require both: an error measured
after the same low-pass blur on both sides, against one fixed reference, and a
rendered sheet looked at beside the source. A dither that wins only on the blurred
metric has not won; the dither and the hue-axis variant removed earlier both
looked better on a metric and worse on screen.

A frame capture from mednafen is the reference view: it matches the replay
oracle pixel for pixel, so what it shows is what the console draws.

## VDP write timing cannot be checked here

Pattern and name table runs go out at 30 T-states a byte, above the 29 the
active display needs. The closing run, palettes plus the name table flip, is
the only one that must land in the vertical blank: it starts each field's
chunk, the replay reads the V counter before it, and only that run copies
with back-to-back `outi` at the 16 T-states blanking allows. The two bytes of
every control-port address setup are padded to 30 T-states, guarded block or
not, because Sega documents the same floor for registers and CRAM. Real
hardware drops or misplaces bytes below the floor and the picture shreds;
emulators accept any rate and look perfect.

An unrolled loop that wrote during the active display has already shipped
once. It measured faster, passed the replay oracle and a cadence measurement,
and was destroyed on a console. `make timing` and
`tools/tests/test_replay_on_z80.py` hold the guard, and neither replaces the
console.

Treat any change to the replay as unverified until it has run on real
hardware, and say so plainly instead of reporting it as done.

## A check expires when you change what it covers

Three defects in this project came from how it was measured, not from the code.

A passing verification is not permanent. The sprite fix measured 0.00% and was
then broken by an edit to the function that invokes it, with no re-run. Re-run
a check after touching anything within its reach.

Confirm alignment before trusting a frame comparison. A misaligned crop returns
a plausible number that means nothing: one error figure was four times too high
because the picture window was eleven rows out, and one cadence figure counted
post-film held frames as elapsed time.

Score a variant against one fixed reference, never against its own output. A
metric invented to vindicate a change you already believe in deserves more
scrutiny, not less, and this has twice produced a large improvement that looked
worse on screen. Render it and look before quoting the number.

Parameters fitted to one clip are not settings, they are a fit. Reuse, denoise
and a since-removed dither strength were all tuned on a single ten-second window, and both
regressions that reached the owner surfaced only when new footage arrived. The
multi-clip gate now bakes six kinds of footage on every run, and it caught a
third one the first time it ran. Fetch the films with
`tools/scripts/fetch_clips.py`; without them only the committed synthetic clip
runs and the gate is much weaker.

Reason about a screen only after rendering it. The bands framing the picture
were blamed on the sprite list for weeks on an argument about which write could
reach the sprite attribute table. One capture disproved it: the bands repeated
every eight rows and every lit-pixel count was a multiple of 32, which is one
background tile across 32 columns and cannot be sprites.
