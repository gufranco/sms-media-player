# AGENTS.md

The engineering contract for this repository, for every person and every agent
working in it.

## Before changing anything

Run `make rom` and confirm it succeeds. A build that was already broken when you
arrived is the first thing to report, not something to work around.

`specs/` holds the plan, the decision record and the sourced hardware
references. It is not committed. Read it before proposing a design change, and
update it in the same turn as any decision that contradicts it.

## Every gate is a command

Nothing here is verified by compiling. Run the gate.

| Claim | Command |
|---|---|
| It builds | `make rom` |
| The C holds | `make analyse` |
| No VDP write pair is under its floor, and every blank copy is guarded | `make timing` and `SMSGGMEDIA_ROM_REQUIRED=1 pytest tools/tests/test_replay_on_z80.py`, after `make rom` |
| The baker holds | `uv --project tools run ruff format --check tools/`, `ruff check tools/`, `mypy tools/smsggmedia tools/scripts` |
| The behaviour holds | `SMSGGMEDIA_CLIPS_REQUIRED=1 uv --project tools run python -m pytest tools/tests --cov=smsggmedia --cov=tools/scripts --cov-config=tools/pyproject.toml --cov-fail-under=95` |
| A commit is clean | [`.githooks/pre-commit`](.githooks/pre-commit), installed once by `make hooks` |
| It runs on a console | the Game Gear, reported by the owner; nothing on this machine settles it |

## What this project is

Full motion video for the Sega Master System, in two halves from one codebase.
An offline baker turns a video file into an SMS ROM, and a library puts a
cutscene inside somebody else's game. It and
[`neogeo-media-player`](https://github.com/gufranco/neogeo-media-player) are
members of one family of tools, never a port of one another; the two machines
differ in the exact dimension the design leans on.

It is a public member of a family with neogeo-media-player, the two kept as
alike as their hardware allows, and held to the requirements in
[FAMILY.md](FAMILY.md) "What every player does". It fills the 1 MB the Sega
mapper decodes, and its sound is tone synthesis on the PSG: the baker writes
the changed tone, noise and attenuation registers once a field, and the replay
sends them to port `$7F` 34 T-states apart before the field's picture. The
player never enables the line interrupt, and it still silences the PSG at boot.
`--silent` leaves sound out. The sound path has played on a Master System and a Game Gear.

Owner's instruction, 2026-10-15: never describe one member as a port, fork,
translation or derivative of another, in a README, a commit, a comment or any
other text, in any language, and never tell which member came first: work
moves between the members in every direction, and more consoles will join.

Owner's instruction, 2026-10-15, replacing the five-second openings of
2026-10-08: the player fills the largest cartridge the standard Sega mapper
addresses, with no added hardware, and the baker sizes picture and sound to the
film's length. A silent build spends the sound's share on a longer or better
picture. Perceived image quality outranks frame rate, by the owner's word on
2026-10-08: when the two compete for bytes or slots, the picture wins, so the
rate search stays at its current candidates rather than rising to buy motion.

The sound is the owner's instruction of 2026-10-15, replacing the removal of
2026-10-08. The line interrupt stays off, and the boot still writes full
attenuation, because a console powers up with its tone channels audible.
Sample playback through the attenuators is the measured alternative in the PSG
sound plan, and it would change the transfer loop's cycle budget.

The Neo Geo holds 1,048,576 tiles resident in character ROM, so its player writes
tile numbers and nothing else. The Master System addresses 512 patterns in 16 KB
of VRAM, which is the whole of VRAM before the name table is placed. The
dictionary cannot be resident, so it is paged in as the film plays, and the
binding constraint moves from character ROM to bytes transferred per field.

## The picture is the whole screen

The film occupies all 256 by 192 pixels of the raster. There are no bars, no
letterbox and no pillarbox, and a source of another shape is scaled until it
covers the raster and then cropped to it. A 16:9 film loses about a quarter
of its width, and that is the trade taken deliberately: every one of the
49,152 pixels the console can draw carries film.

Bars are worse than they look on this machine. They are encoded, they take
pattern slots, and they are transferred every field, so a letterboxed 16:9
source spends a quarter of the working set and a quarter of the per-field
budget delivering black. Cropping spends none of it.

Two things follow for anyone working here.

The tile cap is tied to this. A frame may only mint as many fresh patterns as
there are slots the displayed frame is not still pointing at, and 768 cells
reference far more of the 383 usable slots than 576 did. Any change to the
picture size re-opens that number; the sweep that set the one in
`tools/smsggmedia/limits.py` is recorded under that module in
[tools/DESIGN.md](tools/DESIGN.md).

A smaller picture is still supported through `--rows` and `--columns`, and it
is what the library half needs, since a cutscene inside somebody else's game
rarely owns the whole screen. The picture is centred on both axes, the rows
and columns it leaves over are held black by the player, and a gate holds
them there. See "The bands framing a smaller picture" below.

## How the picture is judged

Owner's instructions of 2026-10-08: perceived image quality comes first, ahead
of frame rate, and dithering is allowed when it raises it. Nothing aimed at a
CRT returns: no composite model and no `--gamut-dither`.

- A dither moves pixels off the source on purpose, so per-pixel error scores
  it as loss by construction. It is judged by Oklab error after the same blur
  on both sides, against one fixed reference, and by a rendered sheet looked
  at beside the source. Both must agree.
- The quantiser adds a tile-aligned 4x4 Bayer threshold before rounding,
  full strength by default through `--dither`. The dial search runs with the
  same strength as the bake.
- Fresh tiles merge only within their palette. A merged cell draws its
  stand-in through its own palette, so a tile taken from a cell of the other
  palette draws in the wrong colours. `placement.merge_by_palette` splits the
  free slots between the palettes by demand, `share_room`, and merges each
  group alone; a pattern both groups keep takes one slot.
- No cell is left badly wrong, meaning more than 0.25 mean Oklab distance from
  the source frame. `placement.guarded_merge` gives such a cell its own tile,
  worst first, within half the group's slots, and `merge_by_palette` moves
  slots to a palette still holding one; a round is kept only when the count
  falls, because forcing tiles squeezes the other cells and once made it 71.
  It is judged against the source, `CellViews.source`, not against the cell's
  own tile: the stand-in's error and the tile's own quantisation add.
- A cell left with a stand-in may switch to a tile already on screen, which
  this frame cannot overwrite, when that tile is closer both pixel for pixel
  and after the blur and stays within 0.25 of the source,
  `placement.better_standins`. Requiring both matters: on
  the blurred view alone it picked tiles that matched in average colour and
  not in texture.
- Palettes carry over between frames. `palettes.fit_or_keep` keeps the
  previous frame's palettes until their error exceeds a fresh fit's by more
  than 30%, `limits.PALETTE_KEEP_MARGIN`. A resident tile is stored as palette indices,
  so a refit re-colours every tile already on the console. The margin was
  swept from 0.02 to 1.5 on the cartoon and the game footage, and 0.3 was best
  on game footage; the README has the numbers.
- A mednafen capture matches the replay oracle pixel for pixel, so it is the
  view to judge by, at integer scale.
- `tools/tests/test_golden.py` pins the stream's size and the replayed
  picture's blurred error for seeded frames, to 0.5%. It is not a byte hash:
  numpy's float results depend on the CPU's vector features, so the same code
  emits different bytes on an M-series Mac, under QEMU and on a GitHub runner,
  while the picture agrees to a few parts in 100,000. A new value is blessed
  only after the change has been measured and looked at.

## Original hardware is the only target

Everything here is built to run on a real Master System, and every change is
made with the care that demands. An emulator that accepts a change is not
evidence the console will: the emulators this project uses do not model VDP
write spacing at all, and every check in this repository runs against one.

- Judge a change against the documented hardware behaviour first and the
  emulator second. Where the two disagree, the hardware wins.
- Where a documented figure and a community measurement disagree, the
  documented figure binds, even when the community one is looser and
  measured. Looser is never a reason.
- A change that touches anything the console can disagree with, the transfer
  loop, port access, the mapper, the interrupt or the header, is unverified
  until it has run on the Game Gear. Say so in the change, and ask for the
  run.

### The binding numbers

| Rule | Value | Source |
|---|---|---|
| Minimum T-states between VDP data-port accesses, active display | 29 | Sega's official documentation, as restated by [Bumbershoot](https://bumbershootsoft.wordpress.com/2025/11/08/the-sega-master-system/) |
| Minimum T-states between VDP data-port accesses, blanking | 16 | same |
| Community measurement, active display, not binding | 26 | sverx, [SMS Power forum thread 16306](https://www.smspower.org/forums/16306-FullscreenVideoPlaybackOnSegaMasterSystem) |
| `outi` | 16 T-states | Z80 instruction timing, as SDCC's listing prints it |
| NTSC V counter | `00-DA`, then `D5-FF` | MacDonald, [msvdp-20021112.txt](https://www.smspower.org/uploads/Development/msvdp-20021112.txt) |
| Z80 clock, NTSC | 3,579,545 Hz, 53.6931 MHz / 15 | [SMS Power, Clock Rate](https://www.smspower.org/Development/ClockRate) |
| NTSC line and field | 228 T-states a line, 262 lines a field | MacDonald, as above |
| NTSC field rate | 59.9227 Hz, derived: the clock over 262 lines of 228 T-states. `console.NTSC_FIELD_HZ` computes it rather than storing it | derived from the three rows above |
| Line interrupt | counter reloaded on lines 193 to 261, so it never fires in the vertical blank | same |
| Safe start window for a blank copy | V counter at or above `C0` and below `E0` | settled on hardware by a sibling project's vertical-blank copy |
| Cartridge ceiling | 64 banks of 16 KB, 1 MB: Sega's mapper revisions decode 3, 5 or 6 bank bits, and 6 is the most any known revision decodes. 4 MB needs a cartridge that decodes all 8 bits, which no Sega mapper does | [SMS Power, Mappers](https://www.smspower.org/Development/Mappers); no Sega datasheet states it |

Pattern and name table runs are copied with `outi`, `nop`, `jp nz`: 30
T-states a byte, legal at any time, and they only touch slots and a name table
the screen is not showing. The one run that must land in the vertical blank
is the closing run, which writes the palettes and flips register 2 to the
other name table. It is moved to the start of the next field's chunk, the
player reads the V counter before it, and its 32 palette bytes go out with
back-to-back `outi`, 16 T-states a byte, the documented blanking floor.

Moving every write into the blank was built and measured first. A field then
holds what fits between lines `C0` and `DF` at 272 T-states of overhead a run,
and the cartoon in the regression set fell from 5.8 frames a second over
twenty seconds to 3.3 over the first twelve, so only the closing run stayed
there.

### VDP write timing is a hardware constraint no emulator enforces

Below the floor the real VDP does not accept a write: bytes land in the wrong
place or not at all, and the picture shreds into scattered tiles. Emulators do
not model this. They accept writes at any rate and show a perfect picture.

This has already cost one shipped defect. Unrolling the upload loop removed
the branch between writes, taking them from 26 cycles to 16, which measured
1.3% faster and rendered correctly under emulation and destroyed the picture
on a console. It was caught by a phone video of a television, because
nothing on this machine can see it.

Rules that follow:

- Back-to-back `outi` is legal only inside the guarded copy in `src/replay.s`,
  between `fmvcopy` and `fmvdone`, and only because the code that falls into
  it reads the V counter and compares it against both ends of the window
  before setting the address. `make timing` holds that block to 16,
  everything else to 29, and fails an address setup on a path into the block
  without the guard.
- `make timing` walks every listing of the build as one program. Branches are
  followed both ways, uppercase conditions included, a call reaches the
  callee and a return reaches every call site, so a write just before a
  `ret` is measured against the caller's next write. Local labels such as
  `00104$` are scoped to their function, because SDCC reuses them.
- SMSlib's own writes are outside the gate. A call into it is charged its
  call cycles only, which can only make a path look faster. The player calls
  it for the screen reset with the display off, the fault colour, the
  vertical blank wait and the pad read.
- The two control-port bytes of an address setup are held to 29 as well,
  inside the guarded block too. Sega's documentation gives the same floor for
  VRAM, CRAM and registers, and the documented figure binds, so every pair in
  `src/replay.s` and `src/vdp.s` is padded with `nop` to 30.
- `tools/tests/test_osd_on_z80.py`, `tools/tests/test_diag_on_z80.py`,
  `tools/tests/test_transport_on_z80.py` and
  `tools/tests/test_seek_on_z80.py` run the built position overlay,
  diagnostics, transport and seek on a Z80 against the VDP model in
  `tools/tests/z80vdp.py` and read back the palette, the glyph pixels and the
  sprite table they wrote.
- `tools/tests/test_replay_on_z80.py` runs the built replay on a Z80 with the
  V counter held at chosen lines. With the guard in place no palette byte and
  no flip reaches the VDP outside the window; with its branches patched out
  all 32 bytes and the flip do, so it is a check that can fail. It also
  measures every control-port pair as executed. It skips when no ROM is
  built, so CI sets `SMSGGMEDIA_ROM_REQUIRED=1` and a missing ROM fails it.
- Every chunk keeps room for a deferred closing run, 34 bytes, so moving one
  into the next field never pushes that field past its budget.
- No measurement available in this repository can validate a change to the
  transfer loop. The replay oracle shares the encoder's model, the cadence
  measurement reads an emulator recording, and both certified the broken
  version as correct. Only the console can.
- A change to that loop is unverified until it has run on hardware, however
  good the local numbers look. Say so rather than reporting it as done.

### The rest of the port contract

Each of these has been settled on hardware by another project, and each applies here.

- **The control port is a two-byte latch.** Both bytes are written before the
  data port is touched, with nothing between them that could also reach the
  control port. The player disables interrupts across the pair for that
  reason; keep the `di` and `ei` around every address setup.
- **Ports `$7E` and `$7F` write the PSG.** Reads there return the V and H
  counters, and the whole `$40` to `$7F` range mirrors on A7, A6 and A0, so a
  stray write meant for a counter makes sound.
- **Eight sprites per scanline, counted whether visible or not.** A slot is
  parked with the terminator Y, `0xD0`, never by moving it off-screen. The
  screen reset writes the terminator into all 64 slots.
- **Work RAM is 8 KB at `$C000`, mirrored at `$E000`.** The mapper registers
  at `$FFFC` to `$FFFF` land in that mirror. Never treat `$E000` and above as
  spare memory.
- **The ROM header stays intact.** The `TMR SEGA` signature and checksum are
  checked by the BIOS on some models, which refuse to boot without them. CI
  verifies both.

## Hard rules

1. **Every build goes through Docker.** No host toolchain is assumed or
   supported. `make rom` builds the image if needed and compiles inside it. A
   change that only builds on one machine is a broken change. SDCC is never
   installed on the host and no host-only build path is added; when Docker is
   unavailable, say so and stop.
2. **The C standard is C23**, via `--std-c23`. SDCC does not implement
   `constexpr`; use `static const` or an `enum`.
3. **NASA Power of 10 applies to all of `src/` and `include/`.** The mapping and
   every recorded exception are below.
4. **`make analyse` must pass** before any commit. It runs cppcheck at exhaustive
   level with `--error-exitcode=1`.
5. **No comments or docstrings in source files.** Names carry the meaning.
   Explanation belongs here, in the README, in the commit message, or, for
   why a baker module is shaped as it is, under that module in
   [tools/DESIGN.md](tools/DESIGN.md).
6. **Emulators never take the screen**: headless when scripted, windowed and minimised when watched, and MAME only as a cross-check. See "Running the ROM" below.
7. **Hardware numbers come from a source.** Every constant tied to the VDP, the
   PSG, the mapper or the raster carries a citation in the design notes. A number
   with no source is not allowed to reach the code. A figure derived by
   arithmetic is labelled as derived and is not treated as measured until
   something has measured it.
8. **Capture and verify rather than ask.** When a defect is visible on screen,
   record the emulator, split the recording into frames and read them. Do not
   describe what to look for and wait for a verdict, and do not ask which of
   two builds looks better when both can be captured and compared. A question
   put to the owner is the last resort after the loop of record, measure, fix
   and re-measure has been run and cannot settle it, and it says what the loop
   showed. Screenshots go to `~/.mednafen/snaps` and the snapshot command is
   bound to F9, which System Events can drive, so a run can be captured without
   anyone watching it. A capture answers what happened, never on its own what
   is better: several metrics here once reported a large improvement on a
   change that was plainly worse.
9. **The original hardware is the target, and every change is made with the
   care that demands.** See "Original hardware is the only target" above. A
   documented hardware figure binds over a looser measured one.


## The Power of 10, as applied here

| Rule | How it is applied |
|---|---|
| 1. No complex flow | No `goto`, no `setjmp`, no recursion. Dispatch is `switch`, never a function-pointer table |
| 2. Fixed loop bounds | Every loop has a compile-time or argument-bounded limit. Recorded exceptions below |
| 3. No heap | No `malloc` anywhere. All state is static or automatic |
| 4. Short functions | Every function fits on one screen |
| 5. Two assertions per function | `FMV_ASSERT` twice minimum in every non-trivial function. Always compiled in: a failure stops the console on a coloured screen, and none sits between two VDP writes. A fact the compiler can see is a `static_assert` instead, since SDCC rejects a runtime check that can never fail as unreachable code |
| 6. Smallest scope | File-static where possible. No cross-module globals |
| 7. Check return values | Every function that can fail returns `bool`, and every caller tests it. A function that cannot fail returns `void`, because a dead failure branch is a cppcheck error here |
| 8. Sparse preprocessor | Include guards, `FMV_ASSERT`, and the SMSlib header macros. No conditional compilation in logic |
| 9. One pointer dereference, no function pointers | Structures are passed by pointer and read one level deep. No function pointers at all |
| 10. All warnings on | `--Werror` on every compile, plus cppcheck in `make analyse` |

### Recorded exceptions to rule 2

- `main()` in `src/main.c` runs `for (;;)`. This is the top-level scheduler of a
  program intended to run until the console is switched off.
- `fmv_assert_fail()` in `src/assert.c` runs `for (;;)`. An assertion failure is
  a deliberate halt, and returning from it would defeat its purpose.
- `wait_for_resume()` and `wait_for_wake()` in `src/main.c` wait, one vertical
  blank per pass, for the viewer to resume from a pause or to play again after
  a stop. A viewer may leave the console paused or stopped indefinitely, and
  no bound would mean anything to them.

No other unbounded loop is permitted. Adding one requires updating this table and
saying why.

### Recorded exceptions to rules 6 and 9

- `movie_cursor`, `movie_bank`, `movie_kind`, `movie_last_bank` and
  `movie_inks` in `src/mediaplayer.c` are globals shared with `src/replay.s`, because the
  replay is assembly and reads and writes them by symbol. Nothing else
  touches them.
- The mapper register at `0xFFFF` is written through a cast `volatile`
  pointer in `fmv_movie_start` and by `ld (0xFFFF), a` in `src/replay.s`.
  That address is the hardware register, so no other form reaches it.

### A corrupt stream stops the player

The replay accepts only the run kinds the baker emits. Any other byte, and a
bank marker past the film's last bank, sets `FMV_CHUNK_BAD` without writing
anything or moving the cursor. `play_once` then returns `FMV_OUTCOME_FAULT`,
and the player resets the screen, turns it red and waits. An exit waits on
black, so a fault on a console reads as a fault rather than as a hang. Without it, a
stale byte from an older stream was decoded as commands and wrote garbage to
VRAM and the mapper. The replay oracle refuses the same streams by name.

### The transfer loop is not unrolled

The per-field transfer loop is the one function whose correctness is measured
in T-states rather than in lines. It is paced at 30 T-states a byte with
`outi; nop; jp nz`, and it stays a loop. Unrolling it is the defect that
shipped once. The only unrolled copy is the 32-byte palette run between
`fmvcopy` and `fmvdone`, legal because it runs inside the guarded vertical
blank.

## Layout

```
Dockerfile          toolchain image: SDCC, devkitSMS built from a pinned commit, SHA-256 checked
Makefile            host target delegates to Docker; in-container target does the real build
include/fmv/        public headers, one per module
src/                implementation, one file per module
tools/smsggmedia/     the baker, one module per stage
tools/scripts/      one-shot helpers: fetch the clips, rebuild the fixture
tools/tests/        the encoder suite, including the multi-clip gate
tools/DESIGN.md     why each baker module, script and test is shaped as it is
tools/clips.manifest.json  identity of the films the gate bakes, never the films
fmv-core-python/    submodule: the family's shared baker code, decode path first
media/clips/        fetched films, ignored, never committed
build/              generated, never committed
specs/              design notes, not committed
```

## Build commands

```
make rom        build the ROM at build/smsggmedia.sms
make analyse    static analysis, must exit 0
make timing     VDP write spacing in the built listings, after make rom
make hooks      install the pre-commit hook: format, lint, types and tests, plus
                rom, analyse, timing and the Z80 replay when the player changes
make shell      interactive shell inside the toolchain image
make clean      remove build output
make distclean  also remove the Docker image
```

The encoder runs on the host, not in the image:

```
uv --project tools run ruff format tools/
uv --project tools run ruff check tools/
uv --project tools run mypy tools/smsggmedia tools/scripts
uv --project tools run python -m pytest tools/tests --cov=smsggmedia --cov=tools/scripts \
    --cov-config=tools/pyproject.toml --cov-fail-under=95

uv --project tools run python tools/scripts/fetch_clips.py     # the regression films
uv --project fmv-core-python run python -m fmvcore.fixture     # the committed clip, in the core
```

## Running the ROM

**Never full screen, headless when scripted.** An emulator never takes the screen. A scripted run is headless and makes no
sound, and a run the owner asked to watch opens windowed and minimised, never
full screen. mednafen opens windowed when told to; pass the flag on every
launch rather than trusting the stored config, which can carry fullscreen over
from an earlier session. MAME starts full screen on macOS and `-video none`
alone still opens a window, so a MAME run carries `SDL_VIDEODRIVER=dummy` with
`-window -video none -sound none`. MAME is never the first witness either: its
BIOS and configuration defaults produce failures and false positives, so the
evidence comes from mednafen or Emulicious, and the [family standard](FAMILY.md)
says the same for every member.

```
mednafen -video.fs 0 -sound 0 build/smsggmedia.sms
```

For an unattended capture, record and pull the frame out afterwards rather than
watching it:

```
mednafen -video.fs 0 -sound 0 -qtrecord /tmp/run.mov build/smsggmedia.sms
ffmpeg -i /tmp/run.mov -vf "select=eq(n\,90)" -vframes 1 /tmp/frame.png
```

MAME's `sms` driver requires a BIOS ROM that is not in this repository, so it is
not the verification path here.

## Verifying on the Game Gear

The owner has a Game Gear with an Everdrive, which runs Master System ROMs.
That is the only real silicon this project can reach, so use it, and be exact
about what it settles.

**It can settle VDP write timing**, which is the one thing no emulator here
can see and the one defect that has already shipped. The Game Gear carries the
same VDP core running at the same clock, so a transfer loop writing faster
than the part accepts shreds the picture there as it does on a Master System.
A run that looks clean on the handheld is the first real evidence this project
has ever had for that constraint.

**It cannot settle colour exactly.** The Game Gear remaps the Master System
palette onto its own, so a colour comparison stays with the emulator.

**It cannot settle the framing, or anything at the edges.** A Game Gear
running a Master System ROM shows the centre 160 by 144 of the 256 by 192
raster, so roughly 38% of the picture is off-screen, including every row the
band guard is about. A defect in those rows is invisible on the handheld by
construction.

Report a Game Gear result as a Game Gear result. It is worth far more than an
emulator for timing and worth nothing for colour or for the edges, and saying
which is which is the difference between evidence and a claim.

## Verification

A change to rendering, banking, the transfer loop or the state machine is not
verified by compiling. Build the ROM and run it. The transfer loop additionally
carries a timing obligation that no emulator reports: writes must be at least 16
cycles apart inside blanking and at least 29 apart during active display, and a
build gate walks the compiled objects to hold that.

A change to what the picture looks like is judged frame by frame against the
source, with one command:

```
mednafen -video.fs 0 -sound 0 -qtrecord /tmp/run.mov build/smsggmedia.sms
uv --project tools run python tools/scripts/compare_capture.py \
    --capture /tmp/run.mov --source <film> --start <seconds> --sheet /tmp/worst.png
```

It first proves the capture repeats the replay oracle pixel for pixel, then
reports what is on screen against the source at the same instant, each frame
against its best-matching moment, the same after an identical blur on both
sides, which is the figure a dither is judged by, the 64-colour floor, the share of pixels
wrong while a frame is still arriving, and how far the picture runs behind its
moment. The sheet shows the worst mid-transfer field. Compare before and after
from the same command, and look at the sheet before quoting a number.

## What CI holds

- The coverage floor is passed on the command line, `--cov-fail-under=95`.
  coverage reads the `pyproject.toml` of the working directory, and the root
  one carries only the release config, so a floor in `tools/pyproject.toml`
  is ignored; that was confirmed by raising it to 99 and watching a run pass.
- The regression films are fetched and verified against the manifest, never
  committed, and cached on the manifest's hash.
- The ROM job bakes a generated clip, so a clean clone reaches a ROM without a
  file the repository cannot carry.
- Actions are pinned to commit SHAs, `uv` to an exact version, and the Docker
  image to a base digest and a dated Debian snapshot with every package
  version named.
- Test data whose value does not matter, file names and opaque payloads,
  comes from the seeded Faker in the core, `fmvcore.testing`. Frame content
  stays on seeded numpy generators.
- Tests that decode through ffmpeg carry the `ffmpeg` marker. Without
  ffmpeg they skip, unless `SMSGGMEDIA_FFMPEG_REQUIRED=1`, which CI and the
  pre-commit hook set, turns the skip into a failure. The listing and Z80
  tests do the same with `SMSGGMEDIA_ROM_REQUIRED=1`.
- Every checkout takes the `fmv-core-python` submodule. A weekly job writes
  how many core commits the pin is behind, and lists them, to its run
  summary; the pin moves after the golden test and the regression set pass
  against the newer core.
- A release publishes a version tag and the release notes, never a ROM.
- A release runs its gates in a read-only job with no stored credential.
  Only the publish job holds a write token, and it installs the `release`
  dependency group alone, so no test dependency ever runs beside that token.

## Things that will bite you

- `ihx2sms` treats each new block appearing at `0x8000` as a new ROM bank, so
  every bank segment needs its own `-Wl-b_BANKn=0x8000` flag.
- Bank object files must be linked in ascending numeric order. An alphabetical
  sort puts `bank10` before `bank2` and silently drops banks from the ROM.
- Do not pass `-m` to `ihx2sms`. Its own documentation says you do not need it,
  and it interferes with bank detection.
- SMSlib and crt0 are rebuilt from source inside the image so their calling
  convention matches the compiler default. Linking the prebuilt `SMSlib.lib`
  produces conflicting-`sdcccall` link errors.
- cppcheck reports a failure branch that can never be taken. A `boot()` that
  cannot fail must return `void`, not `bool`.
- The mapper registers sit inside the RAM mirror at `$FFFC` to `$FFFF`, so they
  are write-only but the last written value reads back out of RAM.
- Banking slot 0 does not remap the first 1 KB, which is held fixed to preserve
  the interrupt vectors.
- After the `fmv-core-python` submodule moves, mypy's incremental cache can
  report a new core module as missing; delete `.mypy_cache` and run it again.
- Running mypy on [`tools/scripts`](tools/scripts) alone poisons `.mypy_cache`:
  the next full run reports `Module "smsggmedia" has no attribute ...` for
  imports that are fine. Always pass both `tools/smsggmedia tools/scripts`, and
  if the error appears, delete `.mypy_cache` rather than chasing it.
- mednafen refuses to start while another instance holds its lockfile, and the
  message names the base directory rather than the lock. Kill the stale process
  before recording. A run killed with SIGTERM leaves the `.mov` unfinalised at
  32 bytes, which reads as a failed emulator rather than a truncated capture.
- CI's commit check wants a lowercase letter or digit right after the colon,
  even for a proper noun, and no local hook checks it; write `game gear`,
  never `Game Gear`, at the start of a subject. A pushed subject that fails
  it stays red, because history is never rewritten.
- `np.argpartition` does not order equal values the same way on x86 and Arm
  NumPy builds, so a tie broken by its order gives one output on this Mac
  and another in CI. Pick a nearest with `np.argmin` and rank with
  `np.argsort(kind="stable")` wherever a tie can change what is baked.

## The bands framing a smaller picture

Fixed. It was never the sprite list, which is what the earlier diagnosis here
said, and the wrong diagnosis is worth keeping because of how it was reached:
by reasoning about which write could reach the sprite attribute table, without
ever rendering the screen and reading the pixels.

The picture used to be 18 rows inside a 24-row raster, so tile rows 0 to 2 and
21 to 23 were never addressed by the stream. They therefore drew whatever the
player left in the name table at boot, which was entry `0x0000`: pattern zero,
first palette. The encoder allocated pattern zero to the film like any other
slot, and the first palette is refitted every frame, so both halves of that
entry were under the film's control. A capture settles it in one line: the
bands repeat with a period of exactly eight rows, are identical top and bottom,
and every lit-pixel count is a multiple of 32. That is one tile drawn across 32
columns, not 64 sprites.

Two changes, and both are needed. `fmv_screen_reset()` fills the whole name
table with `0x0800`, which is pattern zero under the second palette, whose
entry zero is already pinned to black so the border does not flash. And the
working set withholds pattern zero, so nothing the film uploads can land
there. Withholding the slot alone leaves the bands drawing whatever colour the
first palette put at entry zero, which on content with no dark colour is grey
or purple and flickers frame to frame.

Measured on an adversarial clip through the emulator: 88.71% mean band
occupancy before, 0.00% after, across 62 sampled frames, with the picture
still drawing. The guard is `tools/tests/test_framing.py`, and it runs the
same measurement against the configuration that shipped broken so it can be
seen to reject it.

The shipping cartridge now fills the raster and has no bands at all. The guard
still matters, because the library half places a smaller picture.

## What is not done

**The player ran on hardware on 2026-10-17.** The owner ran the current build
on a Master System and on a Game Gear with an Everdrive and reported no defect
so far. That covers every player change listed here before it: the replay's
refusal of run kind `0x03`, the backdrop on an assertion halt, the cursor
assertion below `0xC000`, the sound run written to the PSG 34 T-states apart,
pause on the Pause NMI, the position bar and diagnostics, deferred-field
counting, seek on Left and Right, muting, the overlay drawn during play with its
play, pause and mute glyph, Down for the diagnostics, the resumable stop on
button 2, and the black and white sprite entries the replay writes while the
overlay is up. The report did not itemise each check, so a defect found later
on any of them goes back on this list with what was seen.

Still open: the owner's verdict on the dither default, and a listening verdict
on the PSG sound. The next change to `src/replay.s`, the transfer loop or the
overlay's VDP writes is unverified again until it runs on a console.

Since that run the overlay moved up: text at sprite y 145, the bar at 157 and
the diagnostics rows at 121 and 133, so every overlay sprite sits inside the
Game Gear's visible window, lines 24 to 167 and columns 48 to 207. Before, the
bar drew at y 179, below that window, so a Game Gear in Master System mode
never showed it. Only sprite positions changed; a Game Gear run should confirm
the clock and bar now show on the panel.

The Game Gear build, `--target gg` and `make rom TARGET=gg`, has run only in
mednafen's Game Gear module. It compiles the same player with `TARGET_GG`,
links `SMSlib_GG.lib` and writes header region `0x7C`. Its closing run copies
64 CRAM bytes, two an entry through the Game Gear's latch, with the same 16
T-state `outi` copy inside the same V counter guard; `make timing` walks its
listings in `build/gg`. Start, bit 7 of port `$00`, pauses instead of the
Pause NMI. None of this is verified until it runs on the Game Gear in its own
mode: play with sound, press Start to pause and again to resume, and watch for
shredded tiles and wrong colours.

The Game Gear build also routes the PSG to the left and right headphone
through port `$06`, from a stereo source, and writes `$FF` there whenever it
silences the PSG. The Master System build never writes that port: on a Master
System an even port below `$40` is the memory control register. Stereo is
unverified until it is heard on the Game Gear's headphones.

Start pausing on a Game Gear rests on the SMS Power Start Button page, which
says that in Master System mode the Start button acts identically to the
Pause button, and on the Mark III software reference, which wires Pause to
the Z80 NMI. No Sega document in hand states it for the Game Gear.

The pause overlay lives in VRAM no picture reaches. The back name table spans
0x3000 to 0x36FF for 28 rows, the display shows 24, and nothing writes the
last four rows, so 0x3600 to 0x37FF holds 16 patterns, sprite tiles 176 to
191 with the sprite patterns at 0x2000. The front table's last four rows,
0x3E00 to 0x3EFF, give 8 more, sprite tiles 240 to 247; the diagnostics use
240 to 242, the state glyph 243, and 244 is the blank tile a hidden overlay's
sprites point at, so the diagnostics after them stay in the sprite list. The
screen reset fills those rows with the idle name table cell, which draws as a
one-pixel column, so the overlay clears 244 before it places its sprites. The overlay sets sprite palette
entries 30 and 31 to black and white; the next frame's closing run writes
every palette entry again, so resuming restores the film's colours on the
first frame. A mednafen run of a probe ROM drew it in place, white on a black
shadow.

The owner has a Game Gear with an Everdrive, which runs Master System ROMs, and
that is the hardware path available. What it can and cannot settle is in
"Verifying on the Game Gear" above.

## Three dials are measured per bake

Denoise, the reuse threshold and the frame rate are all chosen by measurement
at bake time, because where each belongs is a property of the footage. Every constant that
stayed fixed here has eventually been wrong for some clip, and both defects
that reached the owner arrived that way.

The reuse search has one subtlety worth keeping. It is scored on the
working-set error, which is what the console shows against what it would show
with a pattern per cell, and not on total displayed error. The total is
dominated by palette quantisation that no threshold can touch: on one frame
the working set replaced a face with a flat wash and the total moved by 0.006,
while the working-set number moved from 0.0060 to 0.0033. A search on the
total reads mostly noise from the dial it is turning. The search takes the
90th percentile of that number across frames rather than its mean, because a
cut changes everything at once and a threshold that wins on the average can
smear that one frame.

Denoise is scored on the replayed picture against one reference decoded with
no denoise, blurred alike on both sides, never on the encoder's error against
its own filtered input. Scored that way a stronger filter always looked easier
to encode and won by construction.

Both searches treat scores within 5% of the best, `tune.SCORE_TIE`, as a tie
the cheapest candidate wins. Carrying palettes over let a finer reuse win by
1 to 2%, and that finer threshold minted more tiles than frames had free
slots: merging doubled and the cuts showed garbage tiles the mean never
registered. A choice made only because every candidate left too many cells
stale is logged as such.

The frame rate is the third, and it is chosen on the median frame rather than
on error at all. A frame that overruns its slot holds the previous picture, so
a rate the content cannot sustain plays slow and uneven rather than fast and
rough. At the nominal 12 fps four clips of six had a typical frame costing 15
to 20 fields against a slot of 5, with no frame landing on time. Choosing the
fastest rate whose median frame fits leaves five clips of six with nothing at
all exceeding twice its slot.

The rate is settled first, and denoise and reuse are then measured at it,
because both act on what changes between consecutive frames and that depends
on how far apart the frames are. Tuning them at a probe rate of 12 and baking
at 3 tuned a film nobody built. The rate search runs with the given values, or
with denoise 2 and the default reuse where those are still to be measured.

The regression set records the dials the search settles on for each clip in
the manifest, and the everyday gate bakes with those, because searching on
every run took seven minutes against twenty seconds. A slow test, run in CI
and at release with `pytest -m slow`, runs the search and fails when the
recorded values bake more than 5% worse than what it found, which is when they
are measured again. It does not require the same values: the search's float
arithmetic differs by CPU, and on a GitHub runner it picked denoise 2 where a
Mac picked 0 for the synthetic clip, with the recorded 0 baking slightly better.

Staleness bounds the pool rather than vetoing candidates. A cell that could
not be placed keeps the previous frame, which is the designed degradation, so
a fraction of a percent is invisible and several percent is a smear. Treating
any staleness as disqualifying picked the loosest threshold in the set on one
clip because it was the only one reaching zero, and its working-set error was
three and a half times the winner's.

## The regression set

Every encoder parameter here was once fitted to a single ten-second window of
one film, and two defects reached the owner because of it. `tools/tests/
test_multiclip.py` now bakes six clips of deliberately different kinds:
synthetic, 3D animation, hand-drawn cartoon, live action, animals and people.
Per clip it holds that nothing is drawn outside the picture, that no cell is
left showing the previous frame, that no pattern lands in a slot the picture
still points at, that the bandwidth stays inside a measured per-clip rate, and
that the displayed error stays inside a measured per-clip ceiling.

It earned its place on its first run. The tile cap of 220, fitted at 576
cells, left 1,947 cells stale on the dance clip and 203 on the city clip once
the picture filled the raster. The sweep that set the replacement is recorded
under `limits.py` in [tools/DESIGN.md](tools/DESIGN.md).

The films themselves are never committed. `tools/clips.manifest.json` carries
their identity, `tools/scripts/fetch_clips.py` downloads and verifies them
against it, and one synthetic clip is committed so the gate runs on a clean
clone with no network. A copy that does not match its digest is refused with a
diagnosis rather than used. Fetch the films before trusting the gate: without
them only the committed synthetic clip runs, and the gate is much weaker.

## Verification discipline

Four failures in this project came from how it was measured rather than from
the code, and each cost more time than the defect it hid.

**Render it and read the pixels before naming a cause.** The bands framing the
picture were attributed to the sprite list for weeks. The reasoning was sound
and the conclusion was wrong, and one capture would have settled it: the bands
repeated with a period of eight rows and every lit-pixel count was a multiple
of 32, which is a background tile across 32 columns and cannot be sprites.

**A passing check expires when you change what it covers.** The sprite fix was
verified at 0.00% and then broken by an edit to the function that invokes it.
Re-run a check after touching anything within its reach; do not carry a result
forward across a change.

**Confirm alignment before trusting a comparison.** A frame comparison against
a misaligned crop returns a plausible number that means nothing. One cadence
figure was inflated because the span counted post-film held frames, and one
error figure was four times too high because the picture crop was eleven rows
out. Derive the offset from the data and check the minimum is sharp.

**Prefer a measure with no confound over one that needs correcting.** Fit a
slope across the middle of a run rather than comparing endpoints. Score a
variant against one fixed reference rather than against its own output, which
is circular and has twice produced a large improvement that looked worse on
screen.

**A metric that vindicates a change you already believe in deserves more
scrutiny, not less.** A perceptual metric once invented to overturn plain
error scored an artefact as the win.
Render the result and look before quoting any number from a new measure.
