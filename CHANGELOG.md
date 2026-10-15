# Development log

What this project tried, what it measured, and what it rejected. The
[README](README.md) says what the cartridge is and how to build one, and
[RELEASES.md](RELEASES.md) is the version history. This file is the record of
how the design got here, kept because the failures are the expensive part:
every entry below was paid for once and does not need paying for again.

The measured levers that are still live, with their numbers, are in the
README under "Quality". This file carries the ones that cost time.

## Contents

- [Paths the timing gate never walked](#paths-the-timing-gate-never-walked)
- [No cell left badly wrong](#no-cell-left-badly-wrong)
- [Stray tiles drawn in the other palette's colours](#stray-tiles-drawn-in-the-other-palettes-colours)
- [The searches were chasing noise](#the-searches-were-chasing-noise)
- [Palettes that stay put](#palettes-that-stay-put)
- [Silent openings, a dithered picture](#silent-openings-a-dithered-picture)
- [A cut now switches whole](#a-cut-now-switches-whole)
- [What the screen showed, frame by frame](#what-the-screen-showed-frame-by-frame)
- [The dials were tuned for a film nobody built](#the-dials-were-tuned-for-a-film-nobody-built)
- [The write floor moved to the documented figure](#the-write-floor-moved-to-the-documented-figure)
- [A defect blamed on sprites for weeks](#a-defect-blamed-on-sprites-for-weeks)
- [The picture now fills the screen](#the-picture-now-fills-the-screen)
- [A cap fitted at one picture size](#a-cap-fitted-at-one-picture-size)
- [A gate the repository said it had](#a-gate-the-repository-said-it-had)
- [Four attempts to buy colour from the CRT blend](#four-attempts-to-buy-colour-from-the-crt-blend)
- [Four parameters checked against the conditions that changed](#four-parameters-checked-against-the-conditions-that-changed)
- [The film was promising a frame rate it could not hold](#the-film-was-promising-a-frame-rate-it-could-not-hold)
- [An unrolled loop that every check approved](#an-unrolled-loop-that-every-check-approved)

## Paths the timing gate never walked

`make timing` passed every build while three kinds of path went unmeasured. It
read each listing on its own, so a write just before a `ret` was never set
against the caller's next write; `vdp.s` writes the control port four
T-states before its `ret`. Its branch pattern accepted lowercase conditions
only, and SDCC's C listings write `jr NZ`, so no conditional branch in any C
file was followed. And it resolved local labels by bare name, while SDCC
reuses `00104$` in every function, so a branch could land in another
function. Loops were also costed as every instruction in their address range
rather than along the path taken.

The gate now walks the whole build as one program by cheapest path: branches
both ways, calls into the callee, returns to every call site, tail jumps
followed, local labels scoped to their function. The shipped build measures
clean, and the `vdp.s` write before its `ret` is 715 T-states from the next
one. A test for each blind spot fails against the old gate.

Two player paths the same review found are hardware changes and wait for the
Game Gear. The replay still accepted kind `0x03`, a palette copy outside the V
counter guard that the baker stopped emitting when the palettes moved into the
closing run; it is now a corrupt stream like any other unknown kind. And an assertion halt painted background
palette entry 0 with the display off, where only the backdrop shows, which
SMSlib selects from the sprite palette, so a halt read as black, the same as
an exit. It now paints the backdrop entry, and a Z80 test runs the compiled
halt to check it.

## No cell left badly wrong

The owner asked for no badly wrong cell at all, a cell being badly wrong when its
mean Oklab distance to the source exceeds 0.25. Every one left was a placement
choice: the input and the palettes were fine, and the replay drew exactly what
the encoder placed. The encoder judged stand-ins against each cell's own tile,
and that error adds to the tile's own quantisation, so cells at 0.15 by its
measure landed at 0.27 on screen.

The merge now judges against the source frame. A cell whose stand-in would
cross the line gets its own tile, worst first, and a palette still holding such
cells borrows slots from the other palette. Forcing tiles squeezes every other
cell in the group, and a first version that always took the trade made game
footage worse, 71 cells against 1, so each round is kept only when the count
falls. Free slots, not the merge cap, were the limit throughout: a median of 86
to 112 a frame. Across twelve five-second windows of every film here the count
is zero.

## Stray tiles drawn in the other palette's colours

At moments of heavy change the owner saw tiles that looked plainly wrong. They
were not a hardware limit. When a frame needs more fresh tiles than it has
free slots, the surplus cells borrow the nearest kept tile, and a cell draws
that tile through its own palette. The merge compared cells by how they look
but kept tiles as palette indices, and it would hand a cell a tile taken from a
cell of the other palette, whose indices drew in unrelated colours. Every
badly wrong merged cell measured came from that: 707 of 707 on a crowd scene,
339 of 340 on game footage, 8 of 8 on the cartoon.

The merge now runs within each palette, with the free slots shared between
them by demand. Badly wrong cells fell to 1, 5 and 0. The crowd scene is still
coarse, because 768 changing cells cannot fit 383 tiles, but it is coarse
rather than speckled.

The fix let the reuse search prefer a finer threshold on the cartoon that won
on the mean and smeared the frame at its cut, so reuse is now chosen on the
90th percentile of per-frame error. That keeps the cartoon at its clean
setting and leaves the other clips where they were.

Merged cells also gained a second source. The tiles the frame on screen still
uses are safe this frame, so a merged cell can point at one of them when it is
closer than its stand-in. Requiring it to be closer pixel for pixel as well as
after the blur kept the switch from trading a wrong colour for a wrong texture;
on the blurred view alone, badly-off cells on the crowd footage rose from 22 to
363. With both conditions, game footage dropped from 19 banks to 17 and the
crowd footage from 27 to 21, with a better worst frame on each.

## The searches were chasing noise

Palette carry-over made the openings look worse, and a frame-by-frame
comparison against one undenoised reference showed why. Carry-over was not the
cause. It made bytes cheaper, so the reuse search, which picks on a mean, moved
to a finer threshold that won by 1 to 2%. That threshold minted more tiles than
a frame had free slots, merging went from 3,665 cells to 8,590 on the cartoon,
and the cuts filled with garbage tiles. The mean improved while the worst frame
went from 0.0301 to 0.0420.

The denoise search had an older fault underneath. It scored each strength by
the encoder's error against the frames that strength produced, so a heavier
filter handed the encoder an easier picture and won by construction; on game
footage it moved from 4 to 8, which is worse with or without carry-over. It now
scores the replayed picture against a reference decoded with no denoise, with
the same blur on both sides. Both searches treat anything within 5% of the best
as a tie and take the cheaper setting. The cartoon's worst frame is back to
0.0303 with 8 badly-off cells; game footage beats where it started on every
measure, though a few dark tiles remain at the end of its fade.

Two tools were tried on the colour conversion and rejected. pngquant's palettes
lost on every frame. ImageMagick's Floyd-Steinberg won on a still frame and lost
in a bake, because a pattern that moves every frame stops tiles repeating.
Colour conversion was already at that ceiling; the loss lives in the tile
budget.

The same pass held the control port to the documented floor. Two address
setups wrote their bytes 15 and 18 T-states apart, under the 29 Sega gives for
registers and CRAM as well as data. Both are padded to 30, `make timing` now
fails such a pair, and the Z80 replay test measures every pair as executed. A
corrupt stream now ends on a red screen, assertions run in every build, and the
toolchain image installs from a dated Debian snapshot with every package
pinned. None of the player changes counts until it has run on the Game Gear.

## Palettes that stay put

Both palettes used to be refitted from scratch for every frame. A tile already
on the console is stored as palette indices, so each refit re-coloured every
resident tile: still regions shifted colour, and fewer residents matched well
enough to reuse. Now a frame keeps the previous palettes unless a fresh fit is
more than 30% better.

On game footage that took blurred error from 0.0397 to 0.0347, badly-off cells
from 418 to 100 and the cartridge from 40 banks to 24; the yellow checkerboard
and the landscape that the old fit washed into grey came back. The cartoon
improved by a smaller step and needed 26 banks instead of 37.

The idea came from reading NesTiler, which shares one palette set across every
image it converts. Two other ideas from it were measured and dropped: an exact
palette fit that packs each cell's colours, which rarely applied and was worse
on the cartoon, and a guard against any cell getting worse, which kept the
palettes less often and lost most of the gain.

The bake can now write a preview of what the console will draw, its report
names the frames that lost the most detail to merged tiles, and a test pins the
exact stream the encoder produces for seeded frames.

## Silent openings, a dithered picture

The player now converts game openings of five seconds at most, as an internal
tool, and carries no sound. The sampled PSG path, its line interrupt, the
`AUDIO` run and `--audio` are gone; one write at boot attenuates all four
channels, because a console powers up with its tone channels audible.

With no interrupt the whole field is free for the paced loop. A capture
compared with the replay oracle held every sampled field at every budget from
600 to 1900 bytes, at 12 fps and again at 30 fps where every field runs full.
The default went from 500 to 1800, 5% under the highest budget that held.
An overrun only delays a frame by a field: paced writes are legal anywhere in
the field and the flip is guarded.

The owner then put perceived quality ahead of frame rate and allowed
dithering. A tile-aligned 4x4 Bayer threshold before the 64-colour rounding
took blurred error from 0.0647 to 0.0261 on the cartoon and from 0.0695 to
0.0437 on game footage, and the owner picked full strength by eye.

Dithering exposed a defect that had been there all along. A frame's fresh
tiles beyond the free slots were dropped, and their cells kept a tile from an
earlier frame: 3,864 such cells on twelve seconds of dithered cartoon. A frame
now merges its fresh tiles to the slots actually free, so every cell gets the
nearest tile, and stale cells are 0 on every clip. With that the merge cap
stopped causing stale cells and went from 130 to 200, past which the free
slots bind first.

Four more techniques were then measured on both clips, each judged by
blurred error and by a rendered sheet. Merging tiles on a blurred view of each
cell won: with dithering, two tiles that look alike differ in most pixels, so a
per-pixel distance merged a dither into the wrong tile. It took blurred error on
game footage from 0.0412 to 0.0394 and cleaned visible stray blocks. Dithering
in linear light, larger 8x8 and blue-noise masks, and reuse on the blurred view
did not earn a place; the README has the numbers.

An audit of the work then found a dial search and a bake that disagreed:
the window scout encoded without the dither the bake applies, because every
library default for the strength was zero while the command defaulted to full.
There is now one default. The same audit made the player stop on a run kind it
does not know, or a bank past the film's end, instead of decoding what follows
as commands, and made the oracle refuse such a stream. The encoder was split so
placement and run building are their own modules; its output is byte-identical
across eight reference encodes.

Tried and dropped: nearest-neighbour scaling for a pixel-doubled SNES capture,
0.0954 against 0.0934 for area, which already lands one source pixel per
console pixel; and frame rates above 12 fps, which the owner declined in
favour of picture quality.

## A cut now switches whole

At a hard cut the screen used to show part of the old picture in the new
frame's colours for the few fields the name table took to arrive, 2.3% of
pixels on average across a film and most of the screen on the worst field.
The palettes are shared by every cell, so no ordering of the writes could
avoid it with one name table.

There are now two. A frame's patterns go into slots the table on screen does
not use, its entries go into the other table, and its last run, `CLOSE`,
writes the palettes and flips register 2 to that table. `CLOSE` is moved to
the start of the next field's chunk, so it always runs at the top of a
vertical blank, and the player reads the V counter before it and copies its
32 palette bytes with back-to-back `outi`, the 16 T-states blanking allows.
Nothing on screen changes while a frame arrives. The six-clip gate now fails
any field before a `CLOSE` that changes a pixel, and a test runs the built
replay on a Z80 with the V counter held outside the window and fails if the
palette or the flip gets through; with the guard patched out, all 32 bytes
and the flip do.

It costs 64 pattern slots, leaving 383, and about 170 more name table bytes a
frame, because the back table is two frames old. The merge cap was swept
again for the smaller pool: stale cells summed over the six clips are 0 at
90, 110 and 130, 42 at 150 and 182 at 160, so the cap is now 130.

**Copying everything in the vertical blank was built, measured and backed
out.** No interrupt fires in the blank, so the plan was to copy every run
there at 16 T-states a byte. A run costs 272 T-states before its first byte,
measured on the player's own code on a Z80, and runs may only start until the
V counter reaches `E0`, so a field holds about 460 bytes at best, and the
cartoon fell from 5.8 frames a second over twenty seconds to 3.3 over the
first twelve. Pattern and name table runs went back to 30 T-states a byte,
which is legal in the active display and invisible there because they touch
only what the screen is not showing. Only `CLOSE` stays in the blank.

Measured with `compare_capture.py` on popeye from 60 s for 20 s with the
default settings, each build captured in mednafen and matched to its own
stream on every sampled field. Before is the single-table pixel-perfect build:

    measure                         before   after
    on screen against source now    0.0959   0.0905
    each frame at its best moment   0.0774   0.0784
    pixels mixed mid-transfer       2.3%     0.0%
    frames a second                 5.82     6.29
    lag, median                     0.00 s   0.02 s
    banks for 20 s                  27       30

Each frame is a little further from the source, because 64 fewer slots force
more merging. What the eye sees at each instant is closer, because nothing is
ever mixed and the film holds more frames a second. Counting a frame as shown
on the field that flips to it, not on its end marker one field earlier, was
itself a fix to the tool: the first comparison of this build scored every
frame against the picture before it.

**The budget rose to 500.** With `CLOSE` at the top of the field and the
sound block skipped in one step rather than byte by byte, a capture repeated
the oracle field for field at 400, 450 and 500 bytes and fell behind at 550.

**The first frame is on time.** It may take many fields to arrive with
nothing yet on screen, and counting those against the film made it start
0.42 s late. Those fields are now a lead-in with silence under it.

**Sharpening the picture further found nothing.** Against one fixed
reference across all six clips, the area scaler and a chroma weight of 1.0
were already best. A weight of 1.5 had looked better on the cartoon alone, a
one-clip fit: across the set it was 0.3% worse and cost 10.7% more bytes.

## What the screen showed, frame by frame

A mednafen recording of popeye from 60 s, compared field by field with the
source, matched the replay oracle exactly on every sampled field. So the
oracle is the screen, and three things it showed were wrong.

**The picture fell behind the sound.** A frame that needs more fields than
its slot holds the screen longer, and nothing ever caught up. Sound plays in
real time, so by the end of twenty seconds the picture was 8.5 s behind, and
what was on screen at any instant was twice as far from the source as the
frames themselves. Frames are now chosen by the clock: the next one is the
source frame for the field it will appear on, so an overrun skips ahead
instead of accumulating. In the spike the last frame's lag fell from 13.95 s to
0.57 s and the on-screen error by 36%. The bake now reports lag, and the
regression set fails a clip whose picture runs more than one transfer behind.

**The previous picture was drawn in the new frame's colours.** The palettes
were written first, before any pattern, so for the whole transfer, 8.5 fields
on average, the old picture showed in the wrong colours. That was the glitch
at a cut. The palettes now follow the patterns and precede the names. Mixed
pixels during a transfer fell from 18.2% to 3.9%, and a test fails if a field
carrying only patterns changes anything on screen. Writing them last instead
measured 3.3% but rendered worse: the cells already switched drew new tiles
in old colours.

**The CRT processing is gone.** By the owner's decision the picture is now
judged pixel for pixel. The chroma-axis dither, its `--gamut-dither` flag and
the composite model were removed. Re-measured without it, popeye holds 12 fps
instead of 6, at 1.5 banks a second instead of 2.0, with lower error.

**The last frame of the film was never shown.** The player stopped as soon as
the final frame finished arriving and reset the screen on the next field, so
that frame was on screen for less than one field. The capture comparison found
it as the only field that did not match. The baker now writes
`MOVIE_HOLD_FIELDS`, one slot, into the generated header, and the player holds
the last frame that long before it resets.

The comparison is now a tool, `tools/scripts/compare_capture.py`, so the next
change is judged on the same evidence.

Measured by that tool on popeye from 60 s for 20 s, each build captured in
mednafen and matched to its own stream on every sampled field. Before is the
dithered, sequential build; after is this one with the default settings:

    measure                         before   after
    on screen against source now    0.2148   0.0959
    each frame at its best moment   0.0977   0.0774
    64-colour floor                 0.0688   0.0689
    pixels mixed mid-transfer       17.5%    2.3%
    lag, median                     3.96 s   0.00 s
    lag, last frame                 8.49 s   0.23 s
    banks for 20 s                  37       27

The error above the 64-colour floor, which is all any of this can move, fell
from 0.029 to 0.009. The film now shows 117 frames instead of 200, each at its
moment instead of drifting behind the sound.

## The dials were tuned for a film nobody built

Denoise and the reuse threshold were measured at a probe rate of 12 fps, and
the rate search then picked 3 or 6 for every clip in the set, so both were
tuned on frames four times closer together than the ones baked. The rate is
now settled first and the other two are measured at it. Recorded per clip,
the search lands on 3 fps for four clips and 6 for two, with denoise from 0
to 8 and reuse from 0.001 to 0.008, which is the spread that made all three
worth measuring.

The regression set was baking with none of that: a fixed 8 fps, a fixed
denoise and the default reuse, no sound, and none of the per-bake search the
cartridge ships. It now bakes through the cartridge's own path with the dials
the search settles on, and a slow test runs the search in CI to catch the day
it stops landing on them. Two error ceilings rose a little, hong-kong from
0.0258 to 0.0264 and bhagoria from 0.0301 to 0.0323, because 3 fps leaves
more change per frame than 8 did; the other four tightened.

The same pass removed several ways a bad bake could get through:

- `--fps 0` divided by zero, `--fps -5` paced every frame to one field, and
  `--reuse nan` baked a ROM. Every value is now checked where it enters, with
  the range it had to lie in.
- `--upload-ceiling 0` scored NaN, and a NaN in the selection made the first
  candidate win silently. A ceiling under one is refused.
- `--gamut-dither` never reached the denoise search, and the upload ceiling
  reached no search, so both were tuned against an encoder other than the one
  that baked.
- A bake that did not fit left the previous film in `assets/`, where
  `make rom` would have packed it. A failed bake now removes it, and a good one
  replaces each file in one rename.
- The multi-clip gate baked every clip up front, so one missing film skipped
  the whole set, the committed clip included.
- The clip fetcher accepted any committed file without checking it, accepted a
  clip with no digest, wrote downloads in place with no size limit, crashed on
  a network error, and ignored a misspelt clip name.
- The frame decoder ignored ffmpeg's exit code, so a source that failed part
  way through baked whatever had arrived before the failure. It also never
  closed ffmpeg's error stream, which Python 3.14 reports as a warning. Both
  are fixed, and warnings now fail the test suite.

The toolchain moved to Python 3.14, pinned in `.python-version`, with every
dependency pinned to an exact version and the Z80 emulator the tests run on
pinned to a commit.

## The write floor moved to the documented figure

The transfer loop wrote one byte every 26 T-states during the active display,
on the strength of timing experiments published on the SMS Power forum. Sega's
own documentation gives 29 for the active display and 16 for blanking, and the
sibling project that has already run on a console holds 29. Where a documented
hardware figure and a looser measured one disagree, the documented one now
binds.

A Z80 cannot reach 29 exactly. It has no three-cycle instruction, and `outi`
plus `jr nz` is 28, so the loop became `outi`, `nop`, `jp nz` at 30. The timing
gate fails anything under 29, and a listing of the old loop is kept in its
tests as a case that must fail.

The four cycles a byte cost field capacity, so the budget was measured again
rather than scaled. Audio stretch on sintel-trailer at 12 fps with dither on:

    budget   400    450    500    550
    stretch  1.02   1.02   1.035  1.105

1.02 is the floor of the instrument. The default budget moved from 500 to 450.

The same pass closed four ways the timing gate could pass code it had not
checked. A run that measured no data-port interval at all exited clean, and
now fails. A listing older than its source was measured as if current. A
conditional branch was charged its taken cost on the path that falls past it,
which made a too-fast pair look slower than it is, and a forward branch that
was taken reached writes the walk never followed. A port number loaded into C
survived into the next function. Each has a test that fails without the fix.

This change touches the transfer loop, so it is unverified until it has run on
the Game Gear.

## A defect blamed on sprites for weeks

Content appeared in the rows above and below the picture. The diagnosis on
record was the sprite attribute table: zeroed VRAM sets every sprite's Y to 0,
which the VDP draws at the top of the screen rather than treating as unused,
and the reasoning went that the list was not being terminated after the film
started looping.

It was wrong, and the argument that produced it never looked at a pixel. One
capture settles it. The bands repeat with a period of exactly eight rows, are
identical top and bottom, and every lit-pixel count in every row is a multiple
of 32. That is one background tile drawn across 32 columns and three rows, and
sprites cannot produce it.

What it actually was: the picture occupied 18 of the 24 visible rows, so the
name table cells outside it were never addressed by the stream and kept the
value the player left at boot, which was `0x0000`. That names pattern zero
under the first palette, and both halves were under the film's control. The
encoder allocated pattern zero like any other slot, so on any frame with no
uniformly flat cell it held picture data. The first palette is refitted every
frame, so even with the slot withheld, entry zero measured grey and purple on
content with no dark colour.

Both halves had to change. The player now fills the name table with `0x0800`,
which is pattern zero under the second palette, whose entry zero is already
held at black so the border does not flash. And the working set withholds
pattern zero, at a cost of one slot in 448.

Measured on an adversarial clip through the emulator: 88.71% mean band
occupancy before, 0.00% after, across 62 sampled frames, with the picture
still drawing. `tools/tests/test_framing.py` runs the same measurement against
the configuration that shipped broken, so it can be seen to reject it.

Two things kept this hidden for so long. `np.unique` sorts the all-zero
pattern first, so most footage most of the time hands pattern zero a blank
tile by accident. And the replay oracle booted VRAM to zeros rather than to
the state the player leaves, so the one instrument that could have caught it
was modelling a console nobody ships. It now boots from the same constants the
player compiles against, and a contract test compares the two.

## The picture now fills the screen

256 by 192, the whole raster. A source of another shape is scaled until it
covers that and then cropped, so a 16:9 film loses about a quarter of its
width. Previously it was letterboxed into 18 rows.

Bars are not free on this machine. They are encoded, they take pattern slots,
and they are transferred every field, so the old geometry spent a quarter of
the working set and a quarter of the per-field budget delivering black.

The cost is real and worth stating: 768 cells against 576 is a third more
work, and the bank rate rises accordingly. Measured across the regression set
at 8 fps, the six clips run between 1.5 and 3.5 banks per second, so 62 banks
hold between 18 and 41 seconds depending on the footage.

## A cap fitted at one picture size

The merge cap of 220 came from a sweep at 576 cells, where the README records
it as never binding. At 768 cells it binds hard, and the first run of the new
multi-clip gate found it: 1,947 cells left showing the previous frame on the
dance clip and 203 on the city clip.

The mechanism is slot pressure. A frame may only mint as many fresh patterns
as there are slots the displayed frame is not still pointing at, and 768 cells
reference far more of the 447 usable slots than 576 did.

The sweep at 8 fps puts the cliff between 170 and 200: 170 leaves nothing
stale, 200 leaves 675 cells stale across two clips, and 224 leaves 2,401. The
cap is now 160, which clears every clip at both 8 and 12 fps and costs 0.0007
of mean displayed error against 220.

Raising the reuse threshold to 0.020 also clears the staleness and cuts
uploads four-fold, and it was rejected: it costs 0.006 to 0.007 of error on
four of the six clips, where the cap change costs almost nothing.

## A gate the repository said it had

`AGENTS.md` stated that a build gate walked the compiled objects to hold the
VDP write spacing. No such gate existed. What existed was a synthetic loop
executed on a real Z80, which proves the threshold is what it claims to be and
reads nothing the player emits, so the player could drift away from it in
silence.

The gate now reads SDCC's own listing, where every instruction carries a
T-state count in brackets, and measures the spacing between VDP writes across
both paths that reach one: falling through from the previous write, and the
branch at the bottom of a loop, which is where the interval is actually
decided. It rejects the unrolled form and the `otir` form, and it passes the
shipped player at exactly 26.

It also reports one thing rather than failing it. The CRAM address setup
writes its two control-port bytes 18 T-states apart, against 31 on the VRAM
path, because the second byte is a constant and needs no load. Whether two
bytes of one latched address operation must be spaced like two data writes is
not a figure this project has a source for, and inventing one would be worse
than saying so. It is printed on every run and is a question for the console.

## Four attempts to buy colour from the CRT blend

The picture had improved and the question was whether the composite blend
could be pushed further: if the display averages colour over several pixels,
the encoder ought to be able to make a run of pixels average to a colour the
palette does not contain.

The idea is sound and the headroom is real. Splitting the perceived error
into its parts puts colour at 42 to 73% of it across the regression set,
averaging 58%, so there is something there to win. Four attempts, one kept.

**The dither offset moved from brightness to colour. Kept, and the largest
single quality win measured here.** Recorded in its own entry above.

**Colour-only error diffusion at palette assignment, confined to a cell.**
Charging the residual forward along the row, reset at every cell boundary so
tile reuse survives. Improved plain error on all four clips tried, moved the
perceived number in both directions depending on the clip, and raised the
distinct tile count by 8 to 12%, which is bandwidth and therefore running
time. Not compelling enough to ship.

**A palette widened in colour, so blending could pull it back.** If adjacent
pixels average, entries further out should let the average reach further in.
Measured a clean loss on both metrics at every factor tried, monotonically
worse as the factor rose.

**Brightness charged per pixel, colour charged on the four-pixel average.**
This is the direct expression of the idea and it optimises the display model
exactly. It scored 4 to 24% better through that model, and it lost on plain
per-pixel error on all four clips. Rendered through the model itself, the
figures broke into vertical streaks and the picture was visibly noisier. It
was rejected on the render, which makes four separate changes now rejected
after a metric declared a large win.

**The dither amplitude was swept and the shipped value is already the peak.**
Perceived error runs 0.01142, 0.01096, 0.01002, 0.01048 at amplitudes 0.6,
0.8, 1.0 and 1.2, so 1.0 is bracketed on both sides. Plain error prefers less
dither monotonically, which is what it always does and why it cannot settle
this on its own.

A second round went further and found the reason all of it fails.

**The headroom is not in doubt.** Enumerating all 16^4 assignments of a
cell's palette to a four-pixel group, against the objective the display
implies, puts the exact optimum 68 to 74% below what the encoder achieves on
every clip tried. There is a great deal left on the table.

**Brightness and colour are not separable on this gamut.** The obvious way to
spend that headroom is to swap entries for brightness-equivalent ones and let
only the colour move. Constraining brightness to within a tolerance of its
best cuts brightness error tenfold, and makes perceived error worse on every
clip. With four levels a channel there are too few lattice points at any
given brightness, so reaching a colour requires moving brightness, and the
dither's brightness excursion is not a flaw to be removed but the mechanism
by which it reaches colours at all.

**A box mean is the wrong objective, and this is what streaks the picture.**
Charging colour on the mean of a four-pixel group treats high-frequency
excursion as free, because whatever a pixel overshoots its neighbour can
cancel. The display does not agree: its colour filter is a gentle low-pass,
not a perfect box, so the residual survives and appears as vertical streaking
across flat areas. Coordinate descent on that objective scored 22 to 27%
better on three clips, worse on a fourth, and rendered through the model
itself with the figures broken into light bands. Rejected on the render,
which makes five changes now rejected after a metric declared a large win.

The next attempt was the optimiser against the true convolution rather than a
block mean, with the cost charged through the same sliding filter the display
applies, so a lone excursion lands in four output positions and cannot be
undone by one neighbour. Objective and evaluator were then the same function,
which makes the result decisive either way.

It scored better on three clips of four and rendered, through that same
function, with the coats still broken into vertical bands. That closes the
line rather than extending it: when the objective is exactly the evaluator
and the render still disagrees, the model is what is wrong. It rewards
alternation that a viewer reads as texture, because a four-tap average says
the colour is right on average while the eye sees the alternation. It is the
mirror of per-pixel error, which cannot see dithering's benefit; this one
cannot see its cost.

Six changes have now been rejected on the render after a metric declared a
large win. Model-guided optimisation of the palette assignment is closed
until there is ground truth from the target display to calibrate against.

What the round leaves behind is the model itself, in
`smscolor.composite_perceived`, with its own failure written into its
docstring. The pixel clock is 53.6931 MHz over ten and NTSC carries luma to
4.2 MHz and chroma to 1.3 MHz, so brightness lands per pixel and colour is
averaged over about four. The rule that comes with it: a change that improves
plain error as well needs no model, and a change that only improves the model
needs a console.

## Four parameters checked against the conditions that changed

Every parameter in this encoder has at some point been fitted under conditions
that later moved, and each time the result was a defect nobody could see. This
round re-checked the survivors rather than waiting for the next one.

**Tile flips, re-measured at the full raster.** They were rejected at 576
cells on a 0.3% loss, and the obvious thought is that 768 cells sharing the
same 447 slots should want the capacity. They do not: flat to slightly worse
on five clips of six, worse on the dark city clip on both metrics, and more
uploads on most. The original verdict survives the change of geometry.

**The denoise search is not boundary-limited.** It picked its maximum
candidate on one clip, which is the classic sign of a range too narrow.
Extending it from four candidates to seven, out to 24, moved one clip by 0.4%
and left the rest identical, and the clip that had chosen the boundary chose
the same value again with room above it. The range is adequate.

**The tile cap of 160 is still right.** It was swept when the per-field budget
was 1,450 and that budget is now 500, so the slot pressure it was fitted
against no longer exists. Re-swept at the current budget it is the best of
120, 160, 220, 300 and 400 on both metrics with no stale cells, and it is
bracketed: 120 is worse and 220 begins leaving cells behind.

**A dither axis chosen per frame from the content loses.** The axis is fixed,
and footage varies, so aligning it with each frame's own colour spread ought
to put the freedom where the content needs it. It improves per-pixel error on
four clips and loses on the composite model on five. Aligning the dither with
the direction the content already varies in adds its excursion parallel to
real signal instead of across it.

## The film was promising a frame rate it could not hold

Reported as a stall on scenes that change drastically, where the whole screen
has to be redrawn. It is that, and it is also more general than that.

A frame is transferred one chunk a field and the previous picture stays on
screen until it finishes, so a frame needing more fields than its slot is a
stall by construction. Measured across the regression set at the nominal 12
fps, with a slot of 5 fields:

    clip                median  p90  max   over 2x  on time
    synthetic               15   21   26       92%       0%
    sintel-trailer           6   19   26       20%      37%
    popeye                   6   20   26       17%      50%
    hong-kong-evening       18   20   26      100%       0%
    colourful-bird          14   20   26       70%       0%
    bhagoria-dance          19   21   26      100%       0%

On four clips of six the typical frame costs 15 to 20 fields against a slot of
5, and not one frame lands on time. The film is running at three or four
frames a second while the encoder reports twelve. A cut is where a viewer
notices it, but the unevenness is everywhere on that footage.

Pacing cannot fix it. `pace` pads a cheap frame up to the slot and never
shortens an expensive one, deliberately, because dropping work to hit a
deadline would be the encoder choosing to show a worse picture than it was
asked for. That choice is right and it leaves the rate itself as the only
lever.

**Bounding the work per frame was tried first and rejected.** An upload
ceiling drops the patterns fewest cells asked for, so a cut converges over
two frames instead of freezing. It works: the worst frame falls from 26 fields
to 15. But the share of frames over twice their slot barely moves, 66% to 68%,
because the problem is not a tail. The trade is poor across the set: worst
frame 26 to 22 costs 8% error, 26 to 16 costs 29%, and staleness climbs to
6,654 cells. The mechanism is kept behind `--upload-ceiling` for footage that
is one hard cut in an otherwise easy film, and it is not on by default.
A stale cell is also not quite the previous frame: it keeps its pattern, but
the palettes are rewritten every frame, so it is drawn in the new frame's
colours. The error figure charges that, and it is one more reason the ceiling
stays off.

**The rate is now measured, like denoise and reuse before it.** `--fps auto`
takes the fastest candidate whose median frame finishes inside its slot.
Five clips of six then have no frame at all exceeding twice its slot, against
66 to 100% before, and popeye holds 10 fps where the others fall to 3.

The median decides rather than a share of frames. A share threshold of 75%
drove every clip in the set to the slowest candidate, including the two that
pace evenly at 8 fps, because a long tail is normal on any footage with cuts.

The honest rates are lower than the nominal 12 and that is the point: the film
was already running at three or four frames a second, unevenly, while claiming
twelve. It now runs at three or four steadily.

The search costs bake time and that cost is real. Three searches now run in
series and the rate search re-decodes once per candidate, so it samples less
than the fidelity searches, two windows against three, and tries candidates
fastest first so it stops at the first that holds. A bake of a twenty-second
clip still takes minutes. `--fps <value>` skips the search entirely and is the
right flag when the rate is already known for that footage.

## An unrolled loop that every check approved

Kept from the earlier record because it is the reason the gate above exists.

Unrolling the transfer loop removed the branch between writes and took them
from 26 T-states to 16. It measured 1.3% faster, agreed with the replay oracle
on 97.8% of frames, passed a cadence measurement taken from a recording, and
destroyed the picture on a console. It was caught by a phone video of a
television.

Every check in this repository runs against an emulator, and emulators accept
VDP writes at any rate. Treat any change to that loop as unverified until it
has run on hardware, and say so rather than reporting it as done.
