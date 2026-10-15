# Design notes

Why each part of the baker, its scripts and its tests is shaped as it is, with the measurements behind each choice. Source files here carry no comments or docstrings, so the reasoning that used to sit above the code lives in this file, one section per module. [AGENTS.md](../AGENTS.md) is the engineering contract and the [README](../README.md) says what the project is and how to use it; this file is the record of why.

## The baker

### [`smsmedia/__init__.py`](smsmedia/__init__.py)

Offline baker that turns a video file into a Sega Master System movie ROM.

### [`smsmedia/bake.py`](smsmedia/bake.py)

Turn decoded frames into the command stream the on-cart player replays.

The pass per frame is: fit both palettes, cut the picture into cells, reduce
the frame's distinct tiles to something the working set can hold, place those
tiles in VRAM without disturbing any slot the displayed picture still points
at, then write the name table entries that changed.

A frame is written into the name table that is not on screen. Its patterns go
to slots the table on screen does not use, its entries go to the other table,
and its last run writes the palettes and flips register 2 to the new table in
one vertical blank. Until that run nothing on screen changes at all, and from
it the whole new frame shows at once.

That replaced an ordering trick. With one table, the palettes, which every
cell shares, could not change without changing cells that were not ready.
Written first they drew the previous picture in the new frame's colours for
the whole transfer, measured on 87% of fields; moved after the patterns they
were still wrong at every cut for the fields the entries took.

A cell the encoder could not place takes the entry it shows now, so after the
flip it still shows the previous frame's tile rather than whatever the other
table last held.

Two sets of slots have to survive a frame, not one. The slots the previous
frame committed are the obvious set. The slots this frame's cells have just
decided to reuse are the other, and leaving them out let allocation evict a
resident a cell was already pointing at, so that cell drew the wrong tile for
exactly one frame and corrected itself on the next. That is a visible flash
rather than a slow drift, and it happened on a third of frames.

A cell whose tile could not be placed keeps the entry it already has, which
leaves it showing the previous frame rather than tearing.

#### `Geometry`

Where the picture sits inside the visible raster.

Bounded by the rows the console draws, not by the rows the name table
holds. Four of its 28 rows are never scanned, and a picture placed into
them is encoded, transferred and then not shown, which no caller wants
and which the old bound permitted.

#### `Encoder`

Encode one frame at a time, carrying the console state between them.

A schedule that picks each frame by the clock needs to know what the last
frame cost before it can choose the next, so the encoder cannot see the
whole film up front. `encode_frames` is a loop over this.

#### `encode_frames`

Encode every frame into per-field chunks.

`upload_ceiling` bounds how many fresh patterns one frame may send. The
player draws one chunk a field and holds the previous picture while a
frame transfers, so a frame that needs many chunks is a visible stall: on
a cut, where the whole working set turns over at once, the worst frame
measured 26 fields against a target of 5. Bounding the uploads turns that
stall into a convergence, since the cells left over keep the previous
frame's pattern for a field and are served on the next. They are drawn
with the new frame's palettes, because CRAM is rewritten every frame, and
the displayed error charges them for it.

### [`smsmedia/capture.py`](smsmedia/capture.py)

Compare what the screen showed, field by field, with the film it came from.

The replay oracle renders the picture after every field, and it matches a
mednafen recording pixel for pixel once the boot fields are skipped, so the
oracle stands for the screen and the recording proves it does. The source is
decoded at the field rate, so every field has a moment to be judged against.

Three numbers come out of that, and they answer different questions. Error
against the source at the same instant is what a viewer sees. Error of each
finished frame against the moment it was taken from is the picture alone.
The share of pixels matching neither neighbouring frame during a transfer is
the glitch at a cut. A fourth, the lag, is measured by matching rather than
taken from the encoder, so it checks the schedule instead of trusting it.

Alignment, the mixed-field share and the lag are measured by
[`fmvcore/capture.py`](../fmv-core-python/fmvcore/capture.py); this module
replays the Master System stream into the fields they are measured on, and
holds the floor of this console's 64 colours.

#### `replay_fields`

Render the screen after each field, up to the last frame shown.

A frame is shown on the field that flips the name table to it, which is
one field after the end marker that closes its transfer. Streams from
before the second table have no flip, and there the end marker is the
moment the frame shows.

### [`smsmedia/cartridge.py`](smsmedia/cartridge.py)

One command: point it at a video file and get the ROM assets.

The picture is 32 by 24 cells, which is 256 by 192: the whole raster, edge to
edge, with nothing framing it. A source of another shape is scaled until it
covers that and then cropped to it, so a 16:9 film loses a quarter of its
width rather than gaining bars.

A smaller picture is still buildable through `--rows`, and it is what the
library half wants: a cutscene inside somebody else's game rarely owns the
whole screen. The rows it leaves over are held black by the player rather
than left to whatever the film last wrote.

The frame rate is measured per film unless `--fps` names one, and each frame
is paced to the slot that rate gives it. A frame that needs more field-sized
chunks than its slot arrives late rather than early, and the bake reports how
late.

#### `shortfall`

Say exactly how much has to come out, and never take it out here.

Shortening a film is the owner's decision. The baker reports the figure
that would fit and stops, which is the same contract the Neo Geo project
holds: no path shortens a movie to make it fit.

### [`smsmedia/clips.py`](smsmedia/clips.py)

The films the gate bakes, and how to know a copy is the right one.

Every encoder parameter in this project was fitted to a single ten second
window of one film. Two defects reached the owner because of it, and neither
was visible on the clip everything was tuned against. The fix is a gate that
bakes several films of genuinely different kinds, which means the project has
to name films it cannot carry.

So it carries their identity instead. The manifest holds a SHA-256 that
decides accept or reject, a byte count that rejects the wrong file for one
stat call, and a CRC-32 and SHA-1 that let a copy be cross-checked against a
public index. Nothing here downloads on its own, nothing points a reader at a
mirror, and the files themselves never enter the repository.

One clip is the exception and is committed, because a gate that needs a
download is a gate that does not run on a clean clone. It is generated from
arithmetic by `tools/scripts/make_fixture.py`, so it is the project's own
work rather than somebody else's film.

The check itself, size first and then SHA-256, is
[`fmvcore/clips.py`](../fmv-core-python/fmvcore/clips.py); this module holds
the Master System's manifest schema, where the films live, and the budgets
each film is held to.

### [`smsmedia/console.py`](smsmedia/console.py)

The console's memory map, and the state the player leaves it in.

Every address here used to be spelled out again in each module that needed
it, which is how the picture ended up framed by garbage. The encoder writes
name table entries for the picture rows and nothing else, so the rows above
and below it keep whatever the player put there at boot. Nobody owned that
value, so nobody noticed when it stopped being safe.

It is safe under exactly two conditions, and both live here because they are
one decision rather than two. The idle cell names pattern zero under the
second palette, whose entry zero is already held at black so the border does
not flash, so an idle cell draws the same black the border does. And pattern
zero is withheld from the working set, so nothing the film uploads can land
in it.

Drop either half and the bands fill with one picture tile stretched across
the width of the screen, three rows deep, top and bottom. That is what
shipped, and a capture of it is what finally named the cause.

There are two name tables. The one on screen is never written while a frame
arrives: patterns and entries go to the other, and the frame's last run
writes the palettes and moves register 2 to point the VDP at it, in one
vertical blank. A cut therefore switches whole on one field instead of
showing the old picture in the new colours while the new one assembles.
Register 2 holds the table address in bits 3 to 1 with bit 0 set, which the
original console needs; SMSlib writes 0xFF for 0x3800, so 0x3000 is 0xFD.
Source: Charles MacDonald's VDP documentation.

The second table costs the pattern slots it sits on, so patterns now end at
0x3000: 384 slots instead of 448.

### [`smsmedia/dials.py`](smsmedia/dials.py)

The three settings measured per bake, settled in the order they depend on.

Frame rate decides how far apart consecutive frames are, and both denoise and
the reuse threshold act on what changes between them, so the rate is settled
first and the other two are measured at it.

#### `resolve_rate`

Take the rate as given, or measure the fastest one the film can hold.

A frame is transferred one chunk a field and the previous picture stays up
until it finishes, so a rate the content cannot sustain does not play fast
and rough: it plays slow and uneven, and the unevenness is what a viewer
notices at a cut. Measured across the regression set at 12 fps, four clips
of six had a median frame costing 15 to 20 fields against a slot of 5, and
not one frame landed on time.

#### `settle_dials`

Settle the rate first, then tune denoise and reuse at that rate.

Denoise and reuse are properties of the frames actually baked, and the
difference between consecutive frames depends on the rate, so tuning them
at a probe rate and baking at another tunes for a film that is not made.
The rate search runs with the given values, or with fixed stand-ins where
those are still to be measured.

### [`smsmedia/fidelity.py`](smsmedia/fidelity.py)

How far what the console shows is from the frame it was asked to show.

#### `displayed_error`

Mean Oklab error against the source, and against the fitted palettes.

The second number is what the working set costs on its own. The first is
dominated by palette quantisation, which no reuse threshold or merge cap
can touch, so searching on it reads mostly noise from the dial being
turned: on one frame the working set replaced a face with a flat wash and
the total moved by 0.006. Charged against the palette fit instead, the
same substitution moves 0.0060 to 0.0033, which is a signal worth
searching.

Charged against every cell of every frame, and a cell the encoder chose
not to redraw is charged against the pattern still on screen rather than
against the source. Excusing those cells makes the number improve
whenever the encoder skips more work, which measures effort rather than
fidelity, and it briefly scored below the palette quantisation floor
here, which is the impossibility that exposed it.

The flips are applied here for the same reason. A first version drew the
pattern in its stored orientation while the console draws it flipped, so
the moment flips were switched on the number reported a fourfold
regression the picture did not have. With flips off the two agreed
exactly, which is what kept the fault hidden.

#### `perceived_cells`

Each cell's colours as an eye sees them at viewing distance.

A 3x3 binomial blur inside the cell, mirrored at its edge. With dithering
on, two tiles that look the same can differ in most pixels, because the
pattern sits in another phase, so a per-pixel distance merges a dither
into whatever is nearest pixel by pixel instead of into the tile that
looks like it. Measured on game footage, merging on this view took
blurred error from 0.0412 to 0.0394 for one bank in 39, and left the
cartoon level.

#### `cell_colours`

Each cell's pixels as Oklab, so the merge clusters on appearance.

A cell's pattern is palette indices, and two cells holding the same
indices under different palettes are still one pattern. The merge has to
decide which cells can share a pattern, and appearance is what that
question is about, so the feature is the colour each pixel resolves to
rather than the index that names it.

### [`smsmedia/frames.py`](smsmedia/frames.py)

Build the filter chain that turns a film into frames at the console's raster
and rate, and hand it to the decode path in
[`fmvcore/ffmpeg.py`](../fmv-core-python/fmvcore/ffmpeg.py), which streams the
frames and refuses a failed or torn decode. This module keeps only what the
Master System decides: the raster in whole tiles, the frame ceiling at the
field rate, and the scale and crop below. The scaler runs
at decode time so nothing downstream ever sees a pixel that is not on the
console's grid.

A source of any shape is scaled until it covers the raster and then cropped
to it, so the picture fills the screen and never carries bars of its own. It
is the deliberate trade: a 16:9 source loses a quarter of its width, and in
exchange every one of the 49,152 pixels the console can draw is film. Bars
baked into the frames would be worse than they look, because the encoder
would spend pattern slots and transfer budget on them all the way to the
screen.

### [`smsmedia/limits.py`](smsmedia/limits.py)

The measured limits every bake is held to.

The per-field budget is measured rather than chosen or derived. A chunk is
one field's work by construction: the player waits for vblank, replays one
chunk, and waits again, so a chunk the field cannot finish makes it miss the
next vblank and costs two fields. A capture compared field by field against
the replay oracle shows that directly: one missed vertical blank and every
later field is offset, so the capture stops repeating the stream.

The player has no sound and never enables the line interrupt, so the whole
field is free for the paced loop. Swept on popeye-for-president from 60 s
for 12 s, with 48 sampled fields compared each time:

    budget                    600    800   1000   1200   1400   1600   1900
    fields per frame at 12   6.90   5.81   5.33   5.11   5.01   5.01   5.01
    capture matches oracle    yes    yes    yes    yes    yes    yes    yes

At 12 fps a frame rarely needs more than its five-field slot, so the same
window was baked again at 30 fps, where every field runs full:

    budget                   1200   1600   1900
    fields per frame         2.76   2.38   2.24
    capture matches oracle    yes    yes    yes

No budget up to 1900 missed a field. The arithmetic ceiling is the whole
field at the paced 30 T-states a byte, 1,991 bytes, and the per-run header,
the dispatch and the main loop all come out of it, so 1900 is close to the
real limit rather than a cliff found below it. The default keeps 5% under
the highest budget the capture held. Overrunning a field is a pacing
fault, not a corruption: every paced write is legal anywhere in the field
and the closing run is guarded by the V counter, so a missed field shows a
frame one field late and draws nothing wrong.

The tile cap no longer decides whether a cell goes stale. A frame merges its
fresh tiles to the slots the displayed frame leaves free, so every cell gets
the nearest tile and none keeps one from an earlier frame. The cap now only
bounds how many fresh tiles a frame may ask for, which is a detail trade.
Swept with the dither at full strength and budget 1800, as blurred Oklab
error against one fixed reference, with stale cells 0 at every value:

    cap                   100     130     160     200     260
    popeye 60 s, 12 s   0.0266  0.0261  0.0259  0.0260  0.0260
    pilotwings 10 s     0.0481  0.0437  0.0415  0.0412  0.0414

Past about 200 the free slots bind before the cap does, so the error stops
falling. 200 is the best figure on the game footage and level on the cartoon.

The dither is full strength: blurred error fell from 0.0647 to 0.0261 on the
cartoon and from 0.0695 to 0.0437 on the game footage between none and 1.0,
and the owner picked 1.0 from the rendered sheets. Above 1.0 the threshold
passes half a step and moves a value already on a level.

### [`smsmedia/output.py`](smsmedia/output.py)

What a bake leaves on disk, and how it avoids leaving the wrong thing.

The build packs whatever film sits in the assets directory. A bake that fails
after an earlier one succeeded would otherwise leave that earlier film in
place, and `make rom` would ship it without a word, so a failure removes it
and a success replaces each file in one rename.

### [`smsmedia/palettes.py`](smsmedia/palettes.py)

Fit the two hardware palettes to one frame, and assign a palette per cell.

CRAM holds two palettes of 16 entries drawn from a 64-colour space, so 32
colours reach the screen at once and a cell picks one palette for all 64 of
its pixels. Uploading the whole of CRAM costs 32 bytes, which against a
per-field budget in the hundreds is cheap enough to refit every frame, but a
refit re-colours every tile already on the console, so `fit_or_keep` keeps the
previous palettes until a fresh fit is clearly better. Cheap uploads are the
one place this hardware is kinder than the Neo Geo, where a full
palette upload costs more than a blanking interval affords and the source
project needs an epoch scheduler to spread it out.

The fit runs in three steps: split the frame's cells into two groups by mean
colour, choose 16 entries for each group from the colours its pixels
actually contain, then let every cell pick whichever of the two palettes
quantises it with less error. Choosing entries from colours that occur
rather than from arbitrary grid points is the same choice the Neo Geo baker
makes, and for the same reason: a palette slot spent on a colour the content
does not contain is a slot wasted.

#### `_fit_tables`

Fit each palette to the cells currently assigned to it.

Entry zero of the second palette is held at black rather than fitted. VDP
register 7 selects the border colour from that palette, and it defaults to
entry zero, so refitting it every frame made the border flash whichever
film colour landed there. The same entry also shows through any cell whose
pattern is entirely index zero under that palette, which put stray
rectangles of the border colour inside the picture.

It costs nothing measurable. Black is almost always in a frame's palette
already, and this palette carries a small minority of the cells, so
reserving the entry moved the error by 0.00% across the frames it was
measured on.

#### `_assign`

Send every cell to whichever palette quantises it with less error.

Splitting cells by mean colour once and fitting each half is a first
guess, not an answer: a cell's mean says little about how well sixteen
particular entries cover its pixels. Alternating assignment and refitting
is Lloyd's algorithm over the two palettes, and it is where most of the
per-cell error can actually be recovered.

### [`smsmedia/pattern.py`](smsmedia/pattern.py)

Pack 8x8 four-bit tiles into the VDP's pattern format, and build name
table entries.

A Mode 4 pattern is 32 bytes: eight rows of four bytes, one byte per
bitplane, so a pixel is four bits spread across the row's four bytes. Bit 7
of each byte is the leftmost pixel. 512 patterns are addressable through the
9-bit index in a name table entry, and 512 times 32 is exactly the 16 KB of
VRAM, which is the constraint the whole project is built around.

A name table entry is `---pcvhnnnnnnnnn`: nine bits of pattern index, then
horizontal flip, vertical flip, palette select and priority. Both flips are
free here, unlike on the Neo Geo where the equivalent lever measured as
worthless, so flip canonicalisation is worth re-measuring rather than
inheriting that verdict.

The bit order within a plane byte is the one place a wrong reading would not
raise. It shows instead as every 8-pixel cell being mirrored left to right,
which is unmistakable on a rendered frame and is checked there.

### [`smsmedia/placement.py`](smsmedia/placement.py)

Decide which VRAM slot every cell of a frame draws from.

A cell either reuses a pattern the console already holds or gets a fresh one.
Fresh patterns may only go to slots no displayed cell still points at, so a
frame merges its fresh tiles down to the slots actually free rather than
dropping the ones that do not fit: a dropped tile leaves its cell showing an
unrelated tile from an earlier frame, while a merged one shows the nearest.
The merge compares tiles as an eye sees them, which keeps a dither from being
merged into the wrong tile.

#### `within_ceiling`

Drop the patterns fewest cells asked for, when a frame wants too many.

Demand is the count of cells a representative serves, so the patterns
that survive are the ones covering most of the screen. A cell whose
pattern was dropped is reported unplaced and keeps what it already
shows, which is the same degradation the working set uses when slots run
out, applied here to bandwidth instead.

#### `reuse_residents`

Point every cell the console can already draw at the slot holding it.

A resident pattern is palette indices, so what it looks like this frame
depends on this frame's palettes. Its appearance is therefore recomputed
against the current CRAM rather than remembered, and a cell is matched
only against residents rendered under the palette that cell chose.

### [`smsmedia/rate.py`](smsmedia/rate.py)

Choose the frame rate a film can actually hold, by measuring it.

A frame is transferred one chunk a field and the previous picture stays up
until it finishes, so a rate the content cannot sustain does not play fast and
rough. It plays slow and uneven, and the unevenness is what a viewer notices
at a cut. The search lives beside the fidelity searches in `tune` and shares
their sampling and scoring, but decides on time rather than on error.

#### `pick_rate`

Take the fastest rate most of the film can actually hold.

Not the rate that scores best, but the fastest one whose typical frame
finishes inside its slot. The median decides rather than a share, because
a long tail is normal on any footage with cuts and a share threshold then
drives every clip to the slowest candidate: at 75% every clip in the
regression set chose 3 fps, including two that pace evenly at 8.

A frame that overruns holds the previous picture, so a nominal rate the
content cannot sustain does not play fast and rough. It plays slow and
uneven, which is worse to watch than a lower steady rate.

It samples less than the fidelity searches do. Pacing is a property of the
typical frame rather than of fine detail, and the search re-decodes once
per candidate, so the sampling is what the bake time is spent on.

Candidates are tried fastest first and the search stops at the first that
holds, because a slower one cannot be preferred once a faster one keeps
time. When nothing holds, the slowest wins: the unevenness only grows with
the rate.

### [`smsmedia/replay.py`](smsmedia/replay.py)

Replay a baked stream into a model of the console, and render what it shows.

This is the measuring instrument the project was missing. Capturing from an
emulator looked like the obvious way to see what a ROM draws, and it is not:
the recording drops frames and its rate does not lock to the emulated field
rate, so aligning a capture against the source drifts by tens of frames and a
best-match search over a wide window then invents matches rather than finding
them. That mistake is documented in the Neo Geo project's own drift tool, and
it reproduced here exactly.

Replaying the cartridge's own bytes has none of that. There is no timing, no
capture, and no alignment to get wrong: chunk N is frame N by construction.
What it cannot check is whether the hardware agrees with this model, which is
what an emulator and a real board are for.

The machine starts in the state the player's screen reset leaves it, not in
a state of all zeros. The difference is the whole of the band defect: the
rows outside the picture are never written by the stream, so what they draw
is decided entirely at boot, and a model that boots differently from the
player is blind to anything that happens there.

#### `framing`

Every visible pixel the picture does not cover, as one flat list.

The stream never addresses these cells, so nothing about them changes as
the film plays and any light here is light the player put there. That
makes the measurement a constant rather than a budget: the answer is
zero, and any other answer is the defect.

### [`smsmedia/schedule.py`](smsmedia/schedule.py)

Choose which frame to show next by the clock, so the picture keeps time.

A frame occupies at least its slot of fields and more when its transfer needs
more. Encoding the decoded frames one after another therefore let every
overrun accumulate: on a twenty second cartoon the last frame landed eight and
a half seconds after its moment in the source, and the on-screen picture
was further from the source than its own frames were.

So the next frame is not the next one decoded. It is the decoded frame whose
moment is nearest the field it will appear on if it fits its slot. A frame that overran is
followed by a later one, the frames in between are never sent, and the film
never runs behind the source by more than the transfer in progress.

The first frame is the exception. Nothing is on screen yet, so it may need
many fields to arrive, and counting those against the film made it start
late, 0.42 s on the cartoon in the regression set. The clock starts when the
first frame is up instead: the fields it took beyond its slot are a lead-in,
reported as `lead`.

#### `due_at`

The decoded frame whose moment is the field a slot starting here ends on.

A frame is padded before its chunks, so it appears on the last field of
its slot. Picking the frame for the slot's first field showed every frame
a slot late, half a second at 3 fps.

### [`smsmedia/scout.py`](smsmedia/scout.py)

Find the passage of a film that encodes best, which is the largest lever.

Every encoder setting measured on this project moves the result by single
digit percentages. The choice of passage moves it far more: the same forty
seconds of one film needs 50 banks from a quiet stretch and 89 from a busy
one, because cost is driven by how much changes between frames rather than by
any parameter. Picking the window was the one decision with no tooling behind
it, so it was being made by hand.

The scan is a profile followed by a slide. Short probes are encoded at a fixed
stride across the film, which costs one decode of a small fraction of it, and
the windows are then ranked by averaging the probes that fall inside each one.
That separation is what keeps it affordable: probing is linear in film length
and the ranking is free, so asking for a different running time re-ranks
without re-probing.

The numbers it reports are estimates from samples, not a bake. A window it
likes still has to be baked, and the baker remains the thing that decides
whether a film fits.

### [`smsmedia/smscolor.py`](smsmedia/smscolor.py)

The Master System colour space, and distance within it.

CRAM is 32 bytes holding two palettes of 16 entries. An entry is one byte
laid out as `--BBGGRR`, two bits per channel, so the console can show 64
distinct colours and 32 of them at once. Read from Charles MacDonald's VDP
documentation; the citation is in the design notes.

A two-bit level maps to 8-bit intensity by scaling across the full range,
which puts the four levels at 0, 85, 170 and 255.

Rounding each channel separately finds the nearest colour in RGB, and that is
not the nearest colour in Oklab. The two disagree on more than half of all
pixels on real footage, and picking the Oklab-nearest cuts Oklab error by
about a third.

The baker rounds per channel anyway, because that measurement is circular:
the metric is Oklab distance and the alternative quantiser minimises Oklab
distance, so it wins on its own definition. Rendered side by side, the
perceptual pick turns a black burrow into saturated navy and dark red, which
is a large visible regression for a large metric improvement. At low
lightness the two chroma axes are ill-conditioned, so dark colours get hues
chosen out of numerical noise.

`nearest_colour` is kept because the effect is worth being able to reproduce,
and it is not the default.

Distance is measured in Oklab rather than in RGB, for the same reason the
Neo Geo baker does it: a metric that agrees with the eye is what lets
palette fitting, tile assignment and the fidelity number all mean the same
thing by "close".

#### `quantise_levels`

Round 8-bit RGB onto the console's two-bit-per-channel grid.

With no dither every pixel takes the level nearest its own value. Four
levels a channel leaves wide steps, and a pale gradient rounds to flat
plateaus that can change hue at the step: a grey-blue sky became blocks of
grey and pink on the cartoon in the regression set.

A dither adds a 4x4 Bayer threshold, scaled by `dither`, before rounding,
so a value between two levels becomes a fixed mix of both in proportion.
The side divides the 8-pixel tile, which keeps the pattern identical
wherever a tile lands and leaves tile reuse intact for flat regions. A
value already on a level is never moved, since the threshold stays inside
half a step. It is judged on blurred error and on a rendered sheet, never
on per-pixel error, which scores any dither as loss by construction.

#### `oklab_palette`

Oklab coordinates of all 64 console colours, indexed by CRAM byte.

The chroma weight scales the two colour axes so error on them is charged
at a fraction of the rate luma error is, which is the lever the Neo Geo
baker uses and the one that survives the port unchanged.

#### `nearest_colour`

Find each pixel's nearest console colour, measured in Oklab.

Searching all 64 rather than rounding per channel, because the console's
colours are a uniform grid in RGB and emphatically not one in Oklab. The
two answers differ on most pixels, and the perceptual one is better by
about a third.

The chroma weight reaches the decision here, which is the only place it
can change anything: with per-channel rounding the choice is made before
any perceptual metric is consulted, so weighting it had no effect at all.

### [`smsmedia/stream.py`](smsmedia/stream.py)

The command stream the on-cart player replays.

A frame is a list of writes, each one a destination and a run of bytes. The
player sets the VDP address once per run and then streams the payload
straight out of ROM, so a run costs one address setup regardless of length.
Consecutive patterns land in consecutive VRAM addresses, so a batch of new
tiles merges into a handful of long runs rather than one run apiece.

The stream is cut into chunks, one per field, and no chunk exceeds the
measured per-field budget. Pattern and name table runs are copied at 30
T-states a byte, which the VDP accepts during the active display too, and they
only touch slots and a name table the screen is not showing, so a chunk may
run on into the picture without anyone seeing it. The closing run is the
exception: it writes the palettes and flips the name table, so it must land in
the vertical blank. `defer_closes` moves it to the start of the next field's
chunk, the player reads the V counter before it and copies its 32 bytes at
the 16 T-states blanking allows, and the first chunk of each frame keeps
room for it.

Runs are dispatched from a one-byte kind through a short chain of
comparisons. There is no general-purpose compressor here on purpose: a
per-frame payload is far too small for a block matcher to amortise a window,
which the prior art on this platform measured directly.

#### `encode_chunks`

Pack a frame's writes into per-field chunks inside the budget.

`reserve` bytes are left free in the first chunk only. That is the chunk
`defer_closes` hands the previous frame's closing run to, and no other
chunk ever receives one.

#### `defer_closes`

Move every frame's closing run to the start of the next field's chunk.

The closing run writes the palettes and flips the name table, and it is
the one run that must land in the vertical blank: the copy into the
palettes runs at 16 T-states a byte and the flip must not split a field.
The player starts each field's chunk at the top of the blank, so a
closing run placed first is always inside it, while one left at the end
of a long chunk would arrive during the picture. The last frame gets a
chunk of its own to carry its closing run.

#### `pace`

Stretch a frame to occupy a fixed number of fields.

The player draws one chunk per field, so without this a cheap frame
appears sooner than an expensive one and the film runs at whatever rate
its content happens to cost. Padding with empty chunks costs one byte
each and makes playback match the rate the film was decoded at.

A frame that already needs more fields than the target is left alone.
Dropping its work to hit a deadline would be the encoder deciding to
show a worse picture than the one it was asked for.

### [`smsmedia/tablewrites.py`](smsmedia/tablewrites.py)

Turn uploads and name table changes into the fewest, longest runs.

Every run costs a header in the stream and an address setup in the player, so
writes to consecutive addresses are folded into one run, and a single unchanged
entry between two changes is rewritten when that joins them.

#### `fill_gaps`

The changed cells, plus single unchanged ones that join two runs.

A run spends four bytes on its header and an entry two, so rewriting one
unchanged entry between two changes makes the frame smaller and spares
the player an address setup. Only cells whose entries sit at consecutive
addresses are joined.

### [`smsmedia/tune.py`](smsmedia/tune.py)

Choose encoder settings by measuring them, rather than by guessing.

Two dials are decided per bake, because where each one belongs is a property
of the footage rather than of the console, and a constant tuned on any one
clip is wrong for the next. Both defects that reached the owner arrived this
way.

Denoising trades detail for pattern slots. Too little and film grain mints a
fresh tile for a region that did not really change; too much and the picture
loses the detail those tiles were being spent on. Three fifteen-second windows
of the same film each preferred a different strength, with an 8% spread
between the best and the worst pick.

The reuse threshold decides how close a resident pattern must be before a cell
draws it instead of minting a new one. Measured across six clips of different
kinds it helps three and hurts two, so it is the same kind of decision. It
became urgent once the picture filled the raster: 768 cells share the same 383
pattern slots that 576 used to, and a threshold loose enough at 576 lets cells
latch onto residents that merely resemble them, which floods the picture.

Selection is on error subject to a byte ceiling, never on error alone. The
cartridge is the binding constraint and the per-field budget is not, so a
setting that scores marginally better while spending far more bytes buys a
fraction of a percent of fidelity and costs the film half its running time. A
candidate over the ceiling cannot win, and when nothing fits the cheapest one
does, which leaves the caller to report an honest shortfall.

Which error, though, is the whole difficulty for reuse. Total displayed error
is dominated by palette quantisation, which no threshold can affect, so it
barely moves while the picture is destroyed: on one frame the working set
replaced a face with a flat wash and the total shifted by 0.006. Charged
against the fitted palettes instead, the same substitution moves 0.0060 to
0.0033. Reuse is picked on the working-set number, because that is the part it
owns, and on its 90th percentile across frames rather than its mean: a cut
changes everything at once, and a threshold that wins on the average can
smear that one frame badly enough to be the thing a viewer remembers.

Both searches treat scores within `SCORE_TIE` of the best as a tie that the
cheapest candidate wins. Two settings a percent or two apart are measuring
noise, while the dearer one mints more tiles than a frame has free slots and
merges them into the wrong ones, which is a visible defect the mean hides.

Denoise is picked on the replayed picture against one reference decoded with
no denoise at all, blurred alike on both sides. Scored against its own
filtered input, a stronger filter always looked easier to encode and won by
construction.

Sampling is by contiguous windows rather than by scattered frames. The
encoder's economy is reuse of what is already resident, so unrelated frames
would show almost none of that reuse and would rank the candidates on a
machine that does not exist.

#### `decide`

Take the best that fits, or the cheapest when nothing does.

Staleness is a tolerance rather than a veto. A cell the encoder could not
place keeps the previous frame, which is the designed graceful
degradation, and a handful of those across a window is invisible. Treating
any at all as disqualifying picked the loosest threshold in the set on one
clip, because it was the only one that reached zero, and its working-set
error was three and a half times the winner's.

#### `pick_reuse`

Score every threshold on one decode and take the best that fits.

Runs after denoise is settled, on frames decoded once at that strength,
because the threshold does not change what comes out of the decoder and
re-decoding per candidate would cost the search five times over.

Staleness is bounded rather than forbidden. A cell the encoder could not
place keeps the previous frame, which is the designed degradation, and a
fraction of a percent of them is invisible while several percent is a
smear on motion. The error number barely registers either, so the share is
carried separately and gates the pool the search chooses from.

### [`smsmedia/vdptiming.py`](smsmedia/vdptiming.py)

Measure the spacing between VDP port writes in the code that shipped.

The rule it enforces is the one hardware constraint no emulator here can see.
Sega's documentation requires 29 T-states between data-port accesses during
the active display and 16 during blanking. Below that the real VDP drops the
write and the picture shreds, while every check in this project reports it as
perfect.

The player copies pattern and name table runs at 30 T-states a byte. Only the
closing run, the palettes and the name table flip, copies with back-to-back
`outi` between the labels `fmvcopy` and `fmvdone`, 16 T-states apart, which
is legal because the code falling into that block reads the V counter and
compares it against both ends of the blanking window first. Inside that block
the floor is 16; everywhere else it stays 29, and an address setup on a path
into the block must follow the guard, with no label in between.

It has cost one shipped defect already. Unrolling a transfer loop that wrote
during the active display took its writes from 26 cycles to 16, measured 1.3%
faster, passed the replay oracle and a cadence measurement, and was destroyed
on a console. The unrolled copy here is the same instructions made legal by
where they run, and `test_replay_on_z80.py` runs the built replay with the V
counter held at chosen lines to prove no byte escapes the window.

The cycle counts are the assembler's, printed in brackets against every
instruction SDCC emits, so this module maintains no table of its own and cannot
disagree with the toolchain about what an instruction costs.

Two paths reach a write. Falling through from the previous one is the obvious
one. The other is the branch at the bottom of a loop, which is where a loop's
interval is actually decided.

Control-port pairs are held to the active-display floor everywhere, guarded
block or not. Sega's documentation gives 29 T-states for VRAM, CRAM and
registers alike, and the project binds the documented figure over any looser
one, so the two bytes of an address setup are spaced like data writes.

#### `check_program`

Measure every interval between VDP writes across the whole program.

A write followed by a return is followed, at runtime, by whatever the
caller does next, and a call reaches the callee's first write. Walking
the listings one at a time stopped at both, so a control write four
T-states before a `ret` was never measured against the caller's next.

#### `unguarded_setups`

Control writes on a path into the blank copy without the V counter guard.

The copy writes a byte every 16 T-states, which is legal only in the
vertical blank, so the block of code that leads into it must read the V
counter and compare it against both ends of the window before it sets
the VDP address. A block leads into the copy when it falls through to
the copy's label or branches to it; a label starts a new block, because
another path could jump there past the guard.

#### `built_listings`

Every listing the last build produced for a source that still exists.

The build directory is not cleaned between builds, so it accumulates
listings for files that have since been deleted. Checking those means
gating on code nobody ships, which is how this check first reported
thirty-one violations in a module that is not in the repository.

#### `stale_listings`

Listings older than the source they were assembled from.

A failed or partial build leaves the previous listing in place, and
measuring it would pass code that is not the code being shipped.

#### `_repeating`

A block-repeat instruction paces itself, and too fast.

`otir` writes a byte every 21 T-states with no branch to slow it, which
is under the threshold and cannot be spaced out. It reads as one
instruction, so nothing that measures the gap between instructions would
ever see it.

#### `_cheapest_paths`

The cheapest path from every write to every write it can reach next.

Branches are followed both ways, so a loop is measured along the path it
actually takes rather than as the sum of every instruction in its range.
A taken branch costs the listing's figure and a fall-through past a
conditional one the smaller not-taken figure, so the cheapest path is
the one charged. Calls into another listing and returns to every call
site are followed too; a call to code outside the listings is charged
its own cycles only, which can only make a path look faster.

### [`smsmedia/workingset.py`](smsmedia/workingset.py)

What lives in VRAM right now, and what it costs to change that.

This module has no counterpart in the Neo Geo baker, and it exists because
of the one difference that reshapes the whole port. That machine holds every
tile the film needs resident in character ROM, so its player writes tile
numbers and never moves a tile. Here, 512 patterns of 32 bytes is exactly
the 16 KB of VRAM, so the dictionary cannot be resident and has to be paged
in while the film plays.

Two rules keep the picture whole while that happens.

A pattern is never written into a slot the displayed name table still points
at. A frame takes several fields to transfer, so a partly-transferred frame
is on screen the whole time, and overwriting a slot under a cell that still
references it corrupts that cell until its entry catches up. Allocation
therefore takes the set of slots the previous frame committed and treats
them as untouchable.

When no slot is free, the pattern is reported unplaced rather than forced
in. The caller leaves those cells showing what they already show, which
degrades a busy frame slightly instead of tearing it. That is the same
choice the Neo Geo baker makes when its dictionary fills.

The low slots are withheld from allocation. Nothing writes name table
entries for the rows above and below the picture, so those cells keep the
pattern the player left there at boot, and the film must not be able to
reach it. One slot out of 384 buys a band that stays black; without it the
first frame that has no uniformly-background cell hands its lexicographically
smallest tile to slot zero and paints it across both bands.

#### `match_residents`

Point each cell at a resident close enough to reuse, or `UNPLACED`.

This is what makes the working set worth having. Without it every frame
re-derives its own representatives, so a region that did not change still
mints a new pattern and pays 32 bytes to upload something the console
already holds. Matching against what is resident turns a still background
into no traffic at all.

Distance is the mean squared Oklab error per pixel, so the threshold
means the same thing whatever the cell size.

#### `merge_to_cap`

Reduce a frame's distinct tiles to at most `cap` representatives.

Exact duplicates collapse first, which on flat content does most of the
work for nothing. Only if that leaves more than the cap does the merge
cluster what remains, and it always returns an existing tile as the
representative rather than a blend, because a blended 4-bit tile is not
one of the tiles anybody asked for.

Distance is measured over `features` when given, and over the raw index
values otherwise. Passing the rendered colour matters: a palette index is
a name, not a quantity, so entry 3 and entry 4 are no more alike than any
other pair and clustering on the numbers merges tiles that look nothing
like each other.

## The scripts

### [`scripts/check_vdp_timing.py`](scripts/check_vdp_timing.py)

Check VDP write spacing in the code the last build actually emitted.

Run after `make rom`, from the repository root:

    uv --project tools run python tools/scripts/check_vdp_timing.py

Exits non-zero on any pair of VDP writes closer together than the active
display allows. A pair of control-port writes is held to the same floor.

### [`scripts/compare_capture.py`](scripts/compare_capture.py)

Compare an emulator capture with the film it was baked from, field by field.

Record the ROM first, windowed and without sound, then run from the repository
root:

    mednafen -video.fs 0 -sound 0 -qtrecord /tmp/run.mov build/sms-media-player.sms
    uv --project tools run python tools/scripts/compare_capture.py \
        --capture /tmp/run.mov --source film.mp4 --start 60 --json /tmp/report.json

It replays the baked stream to know what each field should show, proves the
capture shows exactly that, and then judges the oracle against the source at
the field rate. Exits 1 when the capture does not match the stream, because
every other number would then describe a different ROM.

Pass `--lead` the `lead_fields` from the bake report. Those fields carry the
first frame while it is still arriving, with silence under them, and the film
starts after them.

#### `write_sheet`

Three fields and the source beside the middle one.

The fields are the worst mixed one between its neighbours, or, when no
field is mixed at all, the finished frame furthest from the source
between its neighbours. A sheet of the first frames of a film with
nothing mixed would show only the black the player boots into.

### [`scripts/fetch_clips.py`](scripts/fetch_clips.py)

Fetch the films the multi-clip gate bakes, and verify every one.

Run from the repository root:

    uv --project tools run python tools/scripts/fetch_clips.py

The files land in the directory the manifest names, which is ignored by git
and stays ignored. Nothing here is redistributed: the manifest holds a URL
the publisher operates, and the digests exist so a copy can be recognised
rather than trusted.

The download, its retries and its verification are
[`fmvcore/fetch.py`](../fmv-core-python/fmvcore/fetch.py); this script names
the films and the user agent. A download that does not match its digest is
deleted rather than kept. A
half-right file left on disk is worse than an absent one, because the next
run reports it as present and the gate then measures a film nobody chose.

### [`scripts/make_fixture.py`](scripts/make_fixture.py)

Regenerate the committed synthetic clip the multi-clip gate always runs.

A film cannot be committed, and a gate that needs a download is a gate that
does not run on a clean clone. This builds one small clip from arithmetic, so
the bytes in the repository can be reproduced rather than trusted.

Every term earns its place. The block field gives large areas of one colour
so the encoder can reuse patterns, which is what real footage does. The ramp
varies within every eight by eight cell, so no cell is flat and the working
set has to hold real detail. The sweep and the moving bar change between
frames, so the reuse threshold and the slot allocator both do work rather
than idling on a still.

Run it from the repository root:

    uv --project tools run python tools/scripts/make_fixture.py

## The tests

### [`tests/test_capture.py`](tests/test_capture.py)

Comparing what the screen showed with the film it was made from.

### [`tests/test_check_vdp_timing.py`](tests/test_check_vdp_timing.py)

The build gate that reads write spacing out of the compiled player.

The analysis is tested beside `vdptiming`. What matters here is that the gate
exits non-zero when it finds a violation, because a check that reports a fault
and returns success is worse than no check: it is a check everything passes.

### [`tests/test_clips.py`](tests/test_clips.py)

The clip manifest, and what happens when a file is not what it claims.

Films cannot live in this repository, so the repository carries their
identity instead and the bytes stay on whichever machine fetched them. That
only works if the identity is checked in code rather than printed in a README
nothing reads, and if a mismatch says what the file actually is rather than
just refusing it.

### [`tests/test_compare_capture.py`](tests/test_compare_capture.py)

One command compares an emulator capture with the film it was baked from.

### [`tests/test_console.py`](tests/test_console.py)

The memory map, and the boot state the bands depend on.

These read as trivia until you know what they are guarding. The encoder
never writes the name table rows above and below the picture, so those rows
draw whatever the player left there. The value it leaves has to name a
pattern the film cannot overwrite, under a palette whose entry zero is held
at black. Both halves are asserted here because losing either one refills
the bands with picture.

### [`tests/test_contract.py`](tests/test_contract.py)

The encoder and the player must agree on the numbers they share.

Nothing executes the C player in this suite, so a constant in a C header and
a constant in the encoder can drift apart in silence, each side
self-consistent and both compiling.

The screen reset is where that matters. The encoder never writes the name
table rows framing the picture, so what they draw is decided once, by the
player, at boot. The replay oracle models that boot state, and
if the two disagree the oracle is measuring a console nobody ships.

These read the sources as text and compare them against the encoder. It is a
narrow check and it is the only one that spans the two languages.

### [`tests/test_dials.py`](tests/test_dials.py)

The rate is settled first, and denoise and reuse are measured at it.

### [`tests/test_fetch_clips.py`](tests/test_fetch_clips.py)

Fetching a film is reproducible, and a bad copy is refused loudly.

The script exists so the manifest is not decoration. What matters is that it
verifies what it downloaded rather than trusting the server, and that it says
what a mismatched copy actually is instead of only that it is wrong.

### [`tests/test_framing.py`](tests/test_framing.py)

Nothing may appear above or below the picture, ever, on any frame.

This is the check the project did not have. The bands framing the picture
were measured once at 0.00%, the function that set them up was then changed,
and nobody measured again, so a defect that paints a picture tile across the
full width of the screen three rows deep, top and bottom, shipped and was
found by eye.

The measurement is a constant rather than a budget. The stream never
addresses those cells, so any light there is light the player put there, and
the only correct answer is none.

A check that has only ever seen good input cannot show it would reject bad
input. Every case here is therefore run twice, once against the shipping
configuration and once against the configuration that shipped broken, and
the test fails if the broken one is judged acceptable.

### [`tests/test_make_fixture.py`](tests/test_make_fixture.py)

The committed clip is reproducible, not merely present.

A binary in a repository nobody can regenerate is a binary nobody can
change. These pin the shape of the generator so the file in
`tools/tests/fixtures` stays something the project owns rather than
something it inherited.

### [`tests/test_multiclip.py`](tests/test_multiclip.py)

Bake every clip in the manifest and hold the same guarantees on each.

Every encoder parameter in this project was fitted to a single ten second
window of one film, and two defects reached the owner because of it. Neither
was visible on the clip everything was tuned against, and there was no check
that baked a second one.

This is that check. It runs on whatever the machine holds: the committed
synthetic clip always, and each fetched film when it is present and matches
its digest. It found a real defect on its first run, which is the argument
for it: the tile cap fitted at 576 cells left 1,947 cells showing the
previous frame on the dance clip once the picture filled the raster, and
2,112 at the cap one step higher.

The guarantees are per clip and every one is a constant rather than a budget,
except the displayed error, which is content dependent and carries a per-clip
ceiling in the manifest.

### [`tests/test_output.py`](tests/test_output.py)

A bake leaves either the new film or none, never the previous one.

### [`tests/test_paced_loop_calibration.py`](tests/test_paced_loop_calibration.py)

Calibrate the write-spacing threshold on hand-assembled loops run on a Z80.

These loops are written here, not taken from the ROM, so they prove the
threshold and the measurement rather than the player. The shipped player is
held by `make timing`, which walks its listings, and by
`test_replay_on_z80.py`, which runs its compiled replay.

Consecutive writes to the VDP data port need 29 T states between them, per
Sega's documentation, when they can land during the active display, and this
player's uploads overrun the vertical blank by design, so that condition
always holds. Below
the threshold the real VDP does not accept the write: bytes land in the wrong
place or nowhere, and the picture shreds into scattered tiles.

Nothing else here can catch it. Unrolling the loop to remove the branch took
the interval from 26 cycles to 16, measured 1.3% faster, passed the replay
oracle at 97.8% identical frames, passed a cadence measurement taken from a
recording, and destroyed the picture on a console. Every one of those checks
runs against an emulator, and emulators accept writes at any rate. It took a
video of a television to find it.

Running the instructions on a T-state accurate Z80 and reading the clock
between port writes turns that into something a test can assert.

The unrolled form is kept here on purpose. A check that only ever sees good
input cannot show that it would reject bad input, so the same measurement is
run against the pattern that actually shipped and broken, and the test fails
if that pattern is judged acceptable.

### [`tests/test_replay_on_z80.py`](tests/test_replay_on_z80.py)

Run the player's compiled replay on a Z80 and watch every port it touches.

Pattern and name table runs are copied at 30 T-states a byte, legal at any
time. The closing run copies the palettes with back-to-back `outi`, 16
T-states a byte, which the VDP accepts only in the vertical blank, and flips
the name table, which must not split a field. The listing check shows its
setup follows a V counter read; this runs the ROM's own bytes with the V
counter held at chosen lines and checks what reaches the ports, so a guard
that compares the wrong way round, or jumps to the wrong place, fails here
even though the listing looks right.

### [`tests/test_schedule.py`](tests/test_schedule.py)

The next frame is the one the clock asks for, so the picture keeps pace with the source.

### [`tests/test_vdptiming.py`](tests/test_vdptiming.py)

Reading write spacing out of the assembler's own cycle counts.

The Z80 test beside this one runs a synthetic loop on a real processor, which
proves the threshold is what it claims to be. It does not read the player, so
the player can drift away from it without anything noticing, and this project
has already shipped a transfer loop that was ten cycles too fast.

SDCC's listing prints a T-state count in brackets against every instruction it
emits. That is the assembler's own figure rather than a table this project
would have to maintain, and it makes the spacing between two port writes
arithmetic over the code that actually shipped.
