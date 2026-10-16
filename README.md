English | [日本語](README.ja.md) | [简体中文](README.zh-Hans.md) | [繁體中文（香港）](README.zh-HK.md)

<div align="center">

# SMS Media Player

<strong>Full-screen video on a stock Sega Master System,<br>
its tiles paged through VRAM while the film plays.</strong>

<br>

[![CI](https://img.shields.io/github/actions/workflow/status/gufranco/sms-media-player/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/gufranco/sms-media-player/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-0.1.0-blue?style=flat-square)](RELEASES.md)
[![Licence](https://img.shields.io/badge/licence-MIT-blue?style=flat-square)](LICENSE)
[![Target](https://img.shields.io/badge/target-Sega%20Master%20System-red?style=flat-square)](#hardware-ceilings)
[![Hardware](https://img.shields.io/badge/hardware-console%20run%20pending-yellow?style=flat-square)](#verification)

</div>

<p align="center">
  <a href="#quick-start"><strong>Quick start</strong></a> &nbsp;|&nbsp;
  <a href="#how-it-works"><strong>How it works</strong></a> &nbsp;|&nbsp;
  <a href="#quality"><strong>Quality</strong></a> &nbsp;|&nbsp;
  <a href="#verification"><strong>Verification</strong></a> &nbsp;|&nbsp;
  <a href="#the-family"><strong>The family</strong></a>
</p>

<div align="center">

<img src="readme/demo.gif" alt="Six seconds of the Sintel trailer playing from the built Master System cartridge, captured from mednafen" width="640">

<sub>Six seconds of the Sintel trailer, captured from mednafen running the built cartridge at the console's own 256x192. The same film opens the Neo Geo player's README. Sintel is by the Blender Foundation, CC BY 3.0.</sub>

</div>

```bash
uv --project tools run python -m smsmedia.cartridge ~/Movies/my-film.mkv --duration 5
# build/smsmedia.sms
```

---

## What it is

A baker that turns any video file into a Master System cartridge, and a Z80
player that shows it full screen on a stock console. The baker runs on the
host; the player and every ROM build run in a pinned Docker image.

The whole path runs: preprocessing, the encoder, bank packing, the Z80 player
and the controls.

| Piece | State |
|---|---|
| Encoder and working-set policy | Working, with a replay oracle that agrees with it to five decimals |
| Picture | 256x192, the whole raster. A source of another shape is cropped to fill it |
| Z80 replay loop | Working. Pattern and name runs at 30 cycles a byte against Sega's documented floor of 29; the palette and name table flip at 16 inside a V counter guard in the vertical blank. Held by a build gate and by running the built replay on a Z80 |
| Sound | Tone synthesis on the PSG, written once a field before the picture. `--silent` leaves it out. Not yet run on a console |
| Subtitles | A SubRip `.srt` named with `--subtitles`, or one beside the source under the same name, is burned into the bottom of the picture in the family's 8x8 font, white on a black edge, at most two lines of 32 columns |
| Controls | Plays on a loop. A position bar with a play, pause and mute glyph and the elapsed and total time shows for about three seconds at the start and after any press of Up, Down, Left, Right or button 1, then gets out of the picture's way; while paused it stays up. Button 1 restarts. Button 2 stops on a black screen, and button 1, button 2 or Pause then plays from the beginning. Pause, or Start on a Game Gear, pauses and resumes. Down shows and hides the diagnostics at any time, and button 1 does too while paused: frame over total frames, the cartridge bank, and how many fields were deferred because the vertical blank was missed. Up turns sound off and on; sound returns within a second. Left and Right jump to the seek points the baker places every 10 seconds, `--seek-every` to change; a jump shows about a quarter of a second of black while the point's picture loads. A corrupt stream stops on a red one |
| Field rate | Paced for NTSC, 59.92 fields a second, which the Game Gear also runs at. The player draws one chunk a field, so a 50 Hz PAL console plays the same stream at about five sixths of its intended speed. Nothing here has been checked on a PAL console |
| Regression set | Six clips of different kinds baked on every test run |
| Hardware run | Not done. Every figure here comes from an emulator or a listing |

## What every player does

Both players are built to the same feature list, set in [FAMILY.md](FAMILY.md),
and this table is the same in both READMEs. "Planned" is work not done yet. A
feature a console cannot carry would say "Not possible" with the hardware reason;
none does today.

| Feature | Neo Geo | Master System |
|---|---|---|
| One command from a video file to a cartridge | Yes | Yes |
| The picture fills the screen, scaled to cover and cropped | Yes. `--fit letterbox` still exists and is due to go | Yes |
| Black bars baked into a source are found and cropped | Yes | Yes |
| Picture and sound step down from the best until the film fits | Yes. `--quality search` bakes down a 35-rung ladder, and sound takes the highest rate that still fits | Yes. A bake that overruns the cartridge steps the frame rate down through the same search, and sound goes last |
| The largest standard cartridge, no added hardware | Yes, 128 MiB of character ROM | Yes, 1 MB, the most any Sega mapper revision decodes |
| Ordered dithering | Yes, `--dither` | Yes, on by default |
| Palettes refit as the film changes | Yes, per scene | Yes, per frame, kept while they still fit |
| Sound with no added hardware | Yes, ADPCM-B on the YM2610 | Yes, tone synthesis on the PSG |
| A silent build that gives sound's room to the picture | Partly. A library bundle can leave sound out; sound has its own ROM, so leaving it out frees no picture room | Yes, `--silent` |
| Subtitles from a SubRip file | Yes | Yes, burned into the picture, so they cannot be switched off |
| Play and pause | Yes | Yes. Pause on the console, Start on a Game Gear |
| Fast forward and rewind | Yes, forward at 2x, 5x and 10x | Not possible: the replay already spends about 90% of every field moving one frame, so it cannot move two; Left and Right jump between seek points instead |
| Seek | Yes, 10 seconds back or forward | Yes, Left and Right jump between points 10 seconds apart |
| A position bar with elapsed and total time | Yes | Yes, while paused |
| Restart and stop | Yes | Yes |
| Sound on and off | Yes | Yes, Up |
| The film loops at the end | Yes | Yes |
| A diagnostics overlay | Yes | Yes, button 1 while paused |
| A fault screen for a corrupt stream | Yes | Yes |
| A film inside your own game | Yes, `--bundle` emits a drop-in library | Yes, `--bundle` emits a drop-in library and `examples/cutscene` builds a game from it |
| A preview of what the console will draw | Yes, a video | Yes, a video, or four frames beside their source |
| A write-timing gate on every build | Yes | Yes |
| A regression set of films baked on every test run | Yes, six films | Yes, six films |
| Run on the original hardware | Yes, AES and MVS | Not yet. A Game Gear run is pending |

## How it works

### The constraint that shapes everything

This player and the Neo Geo's [`neogeo-media-player`](https://github.com/gufranco/neogeo-media-player) are members of one
family, and the two machines differ in the one dimension the design leans on.

The Neo Geo holds **1,048,576 tiles resident in character ROM**, so its player
writes tile numbers into sprite control blocks and does nothing else at runtime.
A tile number is the decoded form, so there is no decompression step.

The Master System addresses **512 patterns in 16 KB of VRAM**, and 512 patterns
at 32 bytes each is exactly all of VRAM before the name table is placed. The
dictionary cannot be resident. It has to be paged in from ROM while the film
plays.

Three consequences follow, and they are the whole design.

| | Neo Geo | Master System |
|---|---|---|
| Binding constraint | Character ROM | Cartridge bytes |
| Per-frame work | Write tile numbers | Upload patterns, then write name table entries |
| New component | none | A working-set policy deciding what to evict |

The picture switches whole. There are two name tables: a frame's patterns go
into slots the table on screen does not use, its entries go into the other
table, and its last run writes the palettes and flips register 2 to that
table at the top of one vertical blank. Nothing on screen changes while a
frame arrives, and a cut shows no mixture of the old and new picture. The
second table costs 64 of the pattern slots, leaving 383 for the film. A cell
never keeps a tile from an earlier frame: a frame merges its fresh tiles down
to the slots the displayed frame leaves free, so a busy frame loses detail
rather than showing stale patches.

### The picture is the whole screen

All 256 by 192 pixels, with nothing framing it. A source of another shape is
scaled until it covers the raster and then cropped to it, so a 16:9 film loses
about a quarter of its width and every pixel the console draws carries film.

Bars are not free here. They would be encoded, take pattern slots, and be
transferred every field, so letterboxing a 16:9 source spends a quarter of the
working set and a quarter of the per-field budget delivering black.

`--rows` and `--columns` still build a smaller picture, which is what the
library half needs. The picture is centred, and the rows and columns it leaves
over are held black by the player.

### Sound

Sound comes from the PSG by tone synthesis. The baker reads the soundtrack
once a field and picks its three strongest notes, leaving out the harmonics
of a note already chosen. Each held note stays on its own channel, and the
volume follows the scene's loudness over the surrounding 8 seconds, so quiet
passages stay audible. High-frequency noise rides on the noise channel. Only
registers that changed are written: 3 to 6 bytes a field on the regression
films, under 0.4 KB of ROM a second. The player writes them to the PSG before
the field's picture, 34 T-states apart, and the transfer loop is untouched.
Speech and dense mixes come out as tones; music with a clear melody survives
best. `--silent` leaves sound out and gives its 16 bytes a field back to the
picture. The player never enables the line interrupt, so the whole field,
active display included, stays free for the transfer loop. None of this has
run on a console yet.

It still writes the PSG once, at boot: full attenuation on all four channels.
A console powers up with its tone channels audible, so leaving the chip alone
would hum through the whole film.

### Prior art

Four video efforts exist for this console. Three encode a 1-bit silhouette
animation, where large flat regions and a two-colour palette make tile
deduplication far more effective than colour film will ever allow, so their
numbers are not a target.

The one colour player, [gligli's Bad Apple
3D](https://www.smspower.org/Homebrew/BadApple3DFullLength-SMS), is the honest
benchmark: 256x192 at 12.5 fps, 2,724 frames, three minutes and thirty-eight
seconds filling a 4 MB ROM, with 10.3 kHz sampled audio underneath. It draws
28 distinct colours, which is inside the 32 the hardware shows at once, so it
sets no precedent for exceeding them.

Its encoder source has not been located. GliGli's [tiler](https://github.com/gligli/tiler)
repository is a later and different project, a general video codec named
TileMotion whose palettes are RGBA8888 and whose reference decoder is HTML5
Canvas, with no Z80 or Master System target in it. An earlier revision of this
file cited it as the Bad Apple encoder, which was wrong.

One technique from that work carries into this design. Writing VRAM during
active display as well as blanking roughly doubles the budget, with the encoder
computing the switch point offline so the player never branches on the raster.

## Hardware ceilings

Every figure here carries its source in [AGENTS.md](AGENTS.md).

| Resource | Ceiling | Consequence |
|---|---|---|
| VRAM | 16 KB, 512 patterns of 32 bytes | The dictionary cannot be resident. Patterns are paged in while the film plays, and the second name table leaves 383 slots for the film |
| VDP data port, active display | 29 T-states between writes | Pattern and name runs go out at 30 T-states a byte |
| VDP data port, blanking | 16 T-states between writes | Only the guarded closing run, palettes and the name table flip, uses it |
| Colours | 64, in two palettes of 16 | A cell of 8x8 pixels draws from one palette, so a cell has 16 colours |
| Field rate, NTSC | 59.9227 Hz, 228 T-states a line, 262 lines | One chunk of the stream a field |
| Cartridge | 64 banks of 16 KB through the Sega mapper, two of them code | The baker's ceiling today is 62 banks of film |
| Work RAM | 8 KB at `$C000`, mirrored at `$E000` | The mapper registers live in the mirror |

## Quick start

### Prerequisites

| Tool | Version | Install |
|:-----|:--------|:--------|
| Docker | any recent | [docs.docker.com](https://docs.docker.com/get-docker/) |
| uv | latest | [docs.astral.sh/uv](https://docs.astral.sh/uv/) |
| Python | 3.14, fetched by uv from [`.python-version`](.python-version) | |
| ffmpeg and ffprobe | any recent | [ffmpeg.org](https://ffmpeg.org) |
| mednafen | any recent | Only to run the cartridge on this machine |

### Get the code

The baker shares its decode, colour, film and capture code with the Neo Geo
player through the [fmv-core-python](https://github.com/gufranco/fmv-core-python)
submodule, so clone with submodules. A source archive from the download button
cannot carry a submodule and does not run.

```bash
git clone --recurse-submodules https://github.com/gufranco/sms-media-player.git
git submodule update --init   # in a clone made without the flag
```

### Make a cartridge

Bake a film from any video file and build the ROM in one command.
`--bake-only` stops after the bake, before the ROM build:

```bash
uv --project tools run python -m smsmedia.cartridge input.mp4 --start 300 --duration 5 \
    --preview build/preview.png
make timing     # VDP write spacing, read out of the assembler's own listing
```

`--bundle DIR` writes a drop-in folder for your own devkitSMS game: the player library as source, the film, an `fmv.mk` fragment and a guide written against the film you baked. [`examples/cutscene/`](examples/cutscene) is a game built from one, with `make example`.

`--preview` writes four frames from across the film as the console will draw
them, each beside its source, so a bake can be judged without an emulator.
Given a `.mp4`, it writes a video of every field the console draws instead.
The report in `build/report.json` names `cells_merged`, the cells that showed
a merged tile instead of their own, and `most_merged_frames`, the frames that
lost the most, so a poor result can be traced to the frames that caused it.
`frames_unshown_at_end` counts the decoded frames at the end of the film that
the clock passed before a slot was free for them.

### Running it

On hardware, copy `build/smsmedia.sms` to a flash cartridge. Under an
emulator, run it windowed, never fullscreen:

```bash
mednafen -video.fs 0 -sound 0 build/smsmedia.sms
```

### Toolchain

Every ROM build goes through Docker, and there is no host toolchain path. The
[`Dockerfile`](Dockerfile) pins SDCC by package version, devkitSMS by commit
and archive SHA-256, and the base image by digest. The build runs as the
calling user.

```bash
make rom        # build/smsmedia.sms
make analyse    # cppcheck at exhaustive level, must exit 0
make shell      # a shell inside the toolchain image
make clean
```

## Quality

**The per-field transfer is the binding constraint, not ROM.** Five seconds
at the full field budget fills about a third of the 62 banks, so cartridge
space is not what limits a short bake. What limits it is how many bytes
reach the VDP each field, and a frame that needs more fields than its slot
arrives late. A change is worth having when it raises perceived quality inside
that transfer.

Three bounds locate where the remaining loss lives, measured on ten seconds of
cartoon source:

| Bound | Error | What it allows |
|---|---|---|
| Colour floor | 0.00238 | Every pixel its nearest of the 64 console colours |
| Palette floor | 0.00442 | The two fitted 16-entry palettes, every cell its own pattern |
| Achieved | 0.00565 | The working set, as shipped |

The gap between the first two is +86%, and it is worth naming precisely,
because the obvious reading is wrong. It is not the cost of having only two
palettes per frame. It is the cost of a cell having only 16 colours for its
64 pixels.

That distinction decides what is worth trying. Four separate measurements now
agree on it: giving each band of tile rows its own two palettes buys 0.07%,
forcing a grey-against-saturated split buys nothing, seeding the fitter from
eight partitions buys nothing, and 96% of cells already choose one palette
because 16 colours cover this material. Nothing that reallocates palettes can
help, because no palette arrangement gives a single cell a 17th colour.

### The metric lies about dark colours

Oklab compresses lightness near black, so for a very dark pixel the distance
is dominated by the two chroma axes. A faintly tinted dark entry then scores
nearer to a near-black pixel than a neutral one does, and a change that chases
that score turns a black region into saturated navy and dark red bands.

Three separate changes have been rejected for exactly this, each after a
metric declared a large win: a perceptual quantiser at 36%, direct palette
quantisation at 58%, and error diffusion at 110x on a blurred metric. Any
change that picks colours by minimising a distance is scoring itself with its
own objective, so render it and look at the dark areas before believing the
number.

Routing through the 64-colour lattice guards the first two and does not guard
the third, because diffused error pushes a dark neutral off-neutral before it
ever reaches the lattice.

### Banding is cheap to the metric and expensive to look at

Every pixel in a band sits close to the colour it was assigned, so banding
costs almost nothing in squared error while being the most visible defect on
screen. That asymmetry explains the results above: error diffusion removes
banding and looks worse per pixel, and a palette dedicated to the gradient
scores identically to one that is not.

It also bounds what is available. The palette is not starved, so reallocating
entries cannot help. Measured on a rotating planet, which is the worst case
this footage offers, the split is unambiguous: the 64-colour gamut accounts
for the whole of that region's error, the 16-entries-per-cell selection costs
zero, and the working set adds zero. More colours are what would fix it, and
the hardware does not have them.

So the quantiser dithers. A 4x4 Bayer threshold is added before rounding to
the 64-colour grid, at full strength by default, through `--dither`. The side
divides the 8-pixel tile, so flat regions still reuse tiles. A per-pixel
metric scores any dither as loss, so it is judged by error measured after the
same blur on both sides, and by eye on a rendered sheet:

| `--dither` | 0 | 0.5 | 0.75 | 1.0 |
|---|---|---|---|---|
| Cartoon, blurred error | 0.0647 | 0.0439 | 0.0325 | 0.0261 |
| Game footage, blurred error | 0.0695 | 0.0537 | 0.0460 | 0.0437 |

Undithered, a pale sky rounds to flat blocks of grey and pink; dithered, the
city behind it comes back. It costs bytes: 36 banks against 29 for the same
twelve seconds of cartoon, which a five-second opening does not notice.

### The reuse threshold is measured, not set

It decides how close a resident pattern must be before a cell draws it instead
of minting a new one, and it trades error against cartridge bytes and therefore
against running time. It was a constant fitted to one clip until the regression
set showed it helps three clips and hurts two, so it is now chosen per bake the
way denoise already was.

Two things make that search work. It is scored on the error the threshold
actually owns, which is what the console shows against what it would show with
a pattern per cell, because total displayed error is dominated by palette
quantisation and barely moves while the picture is destroyed. And a candidate
that leaves more than 0.5% of cells showing the previous frame is dropped from
the pool, because that smear is invisible to the error number and obvious on
motion.

Two rules keep the searches honest. Denoise is scored on the replayed picture
against one reference decoded with no denoise, blurred alike on both sides;
scored against its own filtered input, the strongest filter always won. And
scores within 5% of the best are a tie that the cheapest candidate wins,
because a percent or two is noise while the dearer setting mints more tiles
than a frame has free slots.

`--reuse <value>` still forces one. The historical curve, measured on a single
twenty-second window at 32x18:

| reuse | Error | Bytes per frame | Seconds in 62 banks |
|---|---|---|---|
| 0.016 | 0.00863 | 1,254 | 67.5 |
| 0.012 | 0.00789 | 1,660 | 51.0 |
| 0.008 | 0.00706 | 2,279 | 37.2 |
| 0.006 | 0.00653 | 2,664 | 31.8 |
| 0.004 | 0.00614 | 3,041 | 27.8 |
| 0.001 | 0.00564 | 4,005 | 21.1 |

Measured on one twenty-second window. The shape of the curve holds, and the
absolute figures do not: a busier passage of the same film costs nearly twice
as much per frame, so read the last column as a ratio between rows rather than
as a running time to plan around.

Nothing here shortens a film to make it fit. The baker reports the running time
that would fit and stops.

### Measured and rejected

Each of these was implemented and measured before being turned off. Code with
no remaining caller has since been deleted; the measurement is the record.

- **Palette bands via line interrupt**: 0.07%. Re-measured by refitting both palettes inside every band of tile rows: going from one band to eighteen, which is 32 colour slots to 576, moved error from 0.00688 to 0.00687. Extra palettes give a cell no extra colours, and the cell is where the limit lives
- **Perceptual nearest-colour quantiser**: Metric 36% better, picture clearly worse. Judging an Oklab choice with an Oklab metric is circular
- **Tile mirroring**: 0.3% worse. Only 0.5% of cells are exact mirrors
- **Ordered dithering between palette entries**: Moves 0.09% of pixels and neither metric budges. It selects between a pixel's two nearest entries, and inside a colour band every pixel sits almost exactly on one entry, so it can only fire at band edges and cannot break a band up. Perturbing before quantising instead is what ships, under `--dither`
- **Attenuating the dither by lightness**: Shipped once and wrong. The argument was that one level is 85 of 255 and so shouts against black, and a crosshatch did appear over the starfield. That crosshatch was the background nebula: the source has 62.3% of its dark region non-black at mean 2.70, the attenuated build rendered 0.5% at mean 0.15, and removing the attenuation restored it to 6.2% at 1.75. The premise was false, since an ordered threshold cannot lift a true zero, so nothing it draws in a dark region is invented. Cost of the mistake: 9.6% error, six bytes a frame and a bank, all in the wrong direction
- **Perceptual nearest-colour above a lightness gate**: Metric says 5.1% better overall and 28% on lit pixels; rendered, it speckles the planet magenta. The gate was meant to keep the dark-hue failure that sank the ungated version, and it does, but the same chroma noise reappears at middling lightness. An Oklab metric judging an Oklab choice stays circular wherever the gate is put
- **Quantising straight to the palette, skipping the 64-colour lattice**: Metric 58% better, picture clearly worse. Oklab compresses lightness near black, so for dark pixels the distance is dominated by the chroma axes and a faintly blue entry scores nearer to a near-black pixel than a neutral one. The whole dark surround turned to navy and dark red bands. The lattice hop that looks redundant is what keeps near-blacks neutral
- **Floyd-Steinberg error diffusion**: Breaks the banding, and cannot be afforded. Distinct tiles per frame go from 204 to 434, which is 13,888 bytes of pattern data against a 7,160-byte transfer budget, so it overruns bandwidth by 1.9x before ROM is considered, and it exceeds the 220 merge cap so the encoder would cluster the dither away again. It also speckles the dark surround with red and blue, the near-black problem a third time, which routing through the lattice does not prevent because the diffused error pushes dark neutrals off-neutral before quantisation
- **Per-frame palette reallocation**: No gain. 96% of cells choose palette 0 and 14 of 16 entries duplicate the other palette, which looks like waste and is not: this footage needs about 16 distinct colours, so one palette covers it and the second is genuinely spare. Forcing a grey-against-saturated split, so one palette spends all 16 entries on the gradient, left error unchanged at 0.00383 and raised tiles per frame from 130 to 185
- **Dropping to 8 fps to buy per-frame bytes**: Backwards. 4,301 bytes per frame against 2,205 at 12 fps, because fewer frames means more change between them and less to reuse. 78 banks against 50
- **A picture wider than 448 cells**: Better on the metric, worse on screen, and the metric is the one at fault. VRAM holds 448 patterns, so a 32x18 picture asks 576 cells to share them and shapes borrow tiles from elsewhere in the frame. A 28x16 picture matches cells to slots exactly and measures 0.00478 against 0.00547, with 713 bytes a frame against 826. It also has 22% fewer pixels. Error is charged per pixel against each geometry's own downscale, so a smaller picture is rewarded for having less to get wrong, and composited onto a real 256x192 screen at the same scale the larger one plainly shows more of the planet's surface. Kept at 576 cells, and since superseded: the picture now fills the raster at 768 cells, which settles the same argument from the other direction
- **A finer reuse threshold as a cure for blockiness**: Buys error and nothing visible. Detail retention is 84.5% at reuse 0.012 and 84.5% at 0.001, while the cartridge goes from 13 banks to 51. The coarseness is set by the cell grid, which is 8x8 pixels holding 16 colours, and no threshold reaches it
- **A sharper scaler, or less denoise, ahead of the quantiser**: Measured at 32x18 before dithering, and since overtaken by the per-bake denoise search. No effect at the time. Scored against one fixed lanczos reference rather than each variant's own downscale, area, lanczos, bicubic, spline and bilinear span 0.00502 to 0.00507, and denoise from 0 to 4 spans 0.00501 to 0.00503. The quantiser dominates so completely that the input filter is irrelevant
- **Merge cap above 220**: Bit-identical output at 576 cells, where the cap never binds. It binds hard at 768: 200 leaves 675 cells showing the previous frame across the regression set and 224 leaves 2,401, so the cap became 160, and 130 once the second name table took 64 slots. Those stale cells came from dropping tiles that found no free slot; once a frame merged to the free slots instead, the cap stopped causing stale cells and went to 200, where the free slots bind first. A finding that holds at one picture size is not a finding about the encoder
- **Unsharp mask**: Dominated. Sharpen at 0.8 costs 2,692 bytes for 0.00678, while reuse 0.006 costs 2,664 for 0.00653
- **Palette entries from the whole 64-colour lattice**: Identical entries on all 180 fits. The frame is already quantised onto that lattice, so the medoid and the projected centroid converge
- **Chroma weight from 1.0 to 0.25**: Exactly flat
- **Dithering in linear light**: Each blurred metric favours the dither done in its own space: 0.0260 against 0.0408 blurred in Oklab, 0.0370 against 0.0302 blurred in linear light, on the cartoon. Rendered, it turns the cartoon's trees orange-red and patches the sky; on game footage it is mixed. Kept off
- **An 8x8 Bayer matrix, or an 8x8 blue-noise mask**: Level on the cartoon and worse on game footage, 0.0424 and 0.0431 against 0.0412
- **An exact palette fit, packing each cell's colours into the two palettes**: Applied on 42 of 143 cartoon frames and 1 of 99 game frames, and worse on the cartoon, 0.0265 against 0.0258 with 43 banks against 37
- **Guarding the kept palettes so no cell gets worse than under a fresh fit**: Kept fewer frames and lost most of the gain: game footage 0.0376 against 0.0365 unguarded, with more badly-off cells, 129 against 122
- **Reusing residents on a blurred view**: 9 to 12% better on game footage at equal banks, but on the cartoon the reuse search traded it for nine fewer banks and worse error. Mixed, kept off
- **pngquant choosing the two palettes**: Worse than the fitted palettes on all 59 frames of both openings, blurred error 0.0287 against 0.0154 on the cartoon and 0.0266 against 0.0201 on game footage. It optimises one free palette per image, then has to be snapped to the 64 colours
- **ImageMagick Floyd-Steinberg onto the 64 colours**: Wins on a still frame of game footage, 0.0151 against 0.0169, and loses in a bake: 0.0337 against 0.0262 on the cartoon, 0.0353 against 0.0258 on game footage, and 19 banks against 12. The pattern moves every frame, so tiles stop repeating and merging rises
- **Seeding and choosing merged tiles by how many cells use them**: Mixed. Fewer merged cells on game footage, but worse on the cartoon, 16 badly-off cells against 8, and no better at the fade the change was aimed at

### Kept

- **Whole-frame writing, measured at the old 26-cycle loop**: 9.10 to 20.35 fps, the largest single win
- **Resident reuse**: 4.07 to 15.77 fps at lower error
- **Cartoon rather than live-action source**: 44% lower error
- **Measured denoise per bake**: Up to 8%, and no constant beats it
- **Keeping the previous frame's palettes**: A fresh fit replaces them only when the kept palettes' error exceeds the fresh fit's by more than 30%. Game footage: blurred error 0.0397 to 0.0347, badly-off cells 418 to 100, 40 banks to 24. Cartoon: 0.0258 to 0.0249, 37 banks to 26. A refit re-coloured every resident tile, so still regions shifted and fewer residents were worth reusing
- **Merging tiles only within each palette**: A merged cell draws its stand-in tile through its own palette, and the merge used to hand it a tile taken from a cell of the other palette, whose indices then drew in the wrong colours: these were the stray tiles at busy moments. Badly wrong cells fell from 707 to 1 on the crowd footage, 340 to 5 on game footage and 8 to 0 on the cartoon
- **No cell left badly wrong**: A cell is badly wrong when its mean Oklab distance to the source exceeds 0.25. After merging, any cell whose stand-in would cross that gets its own tile, the worst first, and a palette still left with such cells borrows slots from the other; each step is kept only when it lowers the count. Across twelve five-second windows of every film here, game, cartoon, crowd, city, bird and 3D, the count is zero. Measured against the source rather than against the cell's own tile, because the two errors add
- **A merged cell taking a tile already on screen when it is closer**: Tiles the frame on screen still uses cannot be overwritten this frame, so they cost nothing to point at. A merged cell switches to one when it is closer both pixel for pixel and after the same blur; on game footage the worst tenth of frames went from 0.0294 to 0.0284 and the stream from 19 banks to 17, on the crowd footage the worst frame from 0.0540 to 0.0494 and 27 banks to 21. Allowing the switch on the blurred view alone took more badly-off cells, 363 against 22, and put a band of wrong tiles across one game frame
- **Picking reuse on the 90th percentile of per-frame error**: The mean let a threshold win that smeared the one frame at a cut; the cartoon's worst frame went from 0.0412 back to 0.0297
- **Scoring denoise on the replayed picture against an undenoised reference, and breaking near-ties toward the cheaper setting**: Palette carry-over had let both searches drift to settings that won by 1 to 2% and merged twice as many cells. On the cartoon the worst frame went from 0.0420 back to 0.0303 and badly-off cells from 142 to 8; on game footage the corrupted HUD at the end of the fade is gone
- **Merging tiles on a blurred view of each cell**: 0.0412 to 0.0394 blurred error on game footage for one bank in 39, cartoon level. With dithering two tiles that look alike can differ in most pixels, so a per-pixel distance merged a dither into the wrong tile

Denoise is measured rather than fixed because the right strength is a property
of the footage. Three fifteen-second windows of one film preferred three
different strengths, with an 8% spread between the best and worst pick.

### What a cartridge costs

Measured across the regression set at 12 fps, 256 by 192, dither at full
strength, two-second windows, so a bank either way moves the figure by half:

| Clip | Kind | Banks per second | 62 banks hold |
|---|---|---|---|
| Synthetic block field | synthetic | 6.0 | 10s |
| Sintel trailer | 3D animation | 4.0 | 15s |
| Popeye for President | hand-drawn cartoon | 3.0 | 20s |
| Vespero en Hong Kong | live action | 6.0 | 10s |
| Cute Colorful Bird | animals | 5.0 | 12s |
| Bhagoria dance | people | 6.0 | 10s |

Every one holds a five-second opening with room to spare.

Cost varies with the footage far more than with any setting, so compare two
cartridges only when they came from the same source window. Nothing here
shortens a film to make it fit: the baker reports the running time that would
fit and stops.

## Verification

Nothing here has run on a console yet. Every figure comes from an emulator, a
listing or the replay oracle, and the owner's Game Gear is the hardware check.

| Check | What it settles |
|---|---|
| Replay oracle | The baker's model of the stream replays to the picture the encoder meant, to five decimals |
| mednafen capture | A frame captured from mednafen matches the replay oracle pixel for pixel, so the oracle stands for the screen |
| `make timing` | Every VDP write pair in the compiled player clears 29 T-states, or 16 inside the guarded vertical-blank copy, walking every listing as one program |
| `test_seek_on_z80.py` | The built player picks the right seek point for Left and Right, and a jump puts the replay at that point's bank and offset |
| `test_diag_on_z80.py` | The built diagnostics run on a Z80 against a VDP model, and write the frame, bank and deferred-field rows after the position overlay's sprites |
| `test_osd_on_z80.py` | The built position overlay runs on a Z80 against a VDP model, writes the elapsed and total time, the bar, the state glyph and its palette where the sprites read them, and spreads its work over fields without passing the frame interrupt |
| `test_transport_on_z80.py` | The built transport decides on a Z80 which press does what, how long the overlay stays up, and what wakes a stopped player |
| `test_replay_on_z80.py` | The built replay runs on a Z80 with the V counter held at chosen lines, and no palette byte or flip reaches the VDP outside the window |
| Regression set | Six films of different kinds bake on every test run, each held to a measured error and bank budget |
| Game Gear with an Everdrive | Write timing on the same VDP core at the same clock. It remaps colour and shows only the centre 160x144, so it settles neither colour nor the screen edges |

No emulator enforces the VDP write spacing, so a change to the transfer loop is
unverified until it has run on hardware, however good the local numbers look.

## Repository layout

| Path | Contents |
|---|---|
| [`src/`](src) and [`include/fmv/`](include/fmv) | The Z80 player in C and assembly, one module per file |
| [`examples/cutscene/`](examples/cutscene) | A game that plays a film and carries on, built from an emitted bundle |
| [`tools/smsmedia/`](tools/smsmedia) | The baker, one module per stage |
| [`tools/scripts/`](tools/scripts) | Fetch the regression films, rebuild the fixture, check write timing, compare a capture |
| [`tools/tests/`](tools/tests) | The encoder suite, including the multi-clip gate and the Z80 replay |
| [`fmv-core-python/`](https://github.com/gufranco/fmv-core-python) | Submodule: the family's shared baker and measurement code |
| [`readme/`](readme) | The demo GIF |
| `media/clips/` | Fetched films, ignored, never committed |
| `build/` | Generated, never committed |

## Development

Install the pre-commit hook once. On every commit it runs the formatter,
linter, type checker and the test suite with its coverage floor, and when a
staged path can change the player it also builds the ROM and runs the static
analysis, the timing gate and the Z80 replay:

```bash
make hooks
```

```bash
# Format
uv --project tools run ruff format tools/

# Lint gate
uv --project tools run ruff check tools/

# Type gate
uv --project tools run mypy tools/smsmedia tools/scripts

# Tests, with the 95% coverage floor
uv --project tools run python -m pytest tools/tests --cov=smsmedia --cov=tools/scripts --cov-config=tools/pyproject.toml --cov-fail-under=95

# Fetch and verify the regression films
uv --project tools run python tools/scripts/fetch_clips.py

# The player gates, in the pinned image
make rom
make analyse
make timing
```

The regression set bakes six clips of deliberately different kinds. They are
not in the repository and are not ours to redistribute, so the manifest holds
their identity and the script above fetches and verifies them. Without them
only the committed synthetic clip runs, and the gate is much weaker. Every
credit and licence is in [`tools/clips.manifest.json`](tools/clips.manifest.json).

### Documentation

| File | Contents |
|---|---|
| [`AGENTS.md`](AGENTS.md) | The engineering contract: hard rules, the Power of 10 mapping, layout, and what will bite you |
| [`FAMILY.md`](FAMILY.md) | The standard shared with neogeo-media-player and fmv-core-python, identical in each |
| [`tools/DESIGN.md`](tools/DESIGN.md) | Why each baker module, script and test is shaped as it is, with the measurements behind it |
| [`CHANGELOG.md`](CHANGELOG.md) | What was tried, measured and rejected, and what each failure cost |
| [`RELEASES.md`](RELEASES.md) | Version history, generated from commit subjects |
| [`Dockerfile`](Dockerfile) | The toolchain image, with devkitSMS pinned by commit and archive SHA-256 |
| [`tools/clips.manifest.json`](tools/clips.manifest.json) | The regression films: identity, credit and licence, never the films |

## FAQ

<details>
<summary><strong>Why are the tiles paged instead of stored in ROM?</strong></summary>
<br>

The Master System draws only from VRAM, and VRAM holds 512 patterns. A film
needs thousands, so they live in the cartridge and the player copies each
frame's new ones into slots the screen is not showing.

</details>

<details>
<summary><strong>Does it run on a Game Gear?</strong></summary>
<br>

A Game Gear with an Everdrive runs Master System ROMs, and that is how write
timing gets checked here. In Master System mode it shows only the centre 160 by
144 of the picture and remaps the palette, so the full picture is a Master
System's to show.

</details>

<details>
<summary><strong>Does it play on a PAL console?</strong></summary>
<br>

It is paced for NTSC, 59.92 fields a second. The player draws one chunk a
field, so a 50 Hz console plays the same stream at about five sixths of its
intended speed. Nothing here has been checked on a PAL console.

</details>

<details>
<summary><strong>Why is it silent?</strong></summary>
<br>

The transfer loop owns every cycle of the field today, and the PSG has no
sample channel, so sound costs Z80 time the picture now uses. Sound is a
requirement the family sets, and it is planned.

</details>

## The family

This player is one of a family that plays full-motion video on consoles that
were never meant to show it. The members share one standard,
[FAMILY.md](FAMILY.md), and every piece of baker code the hardware does not
force lives once in the core.

| Member | What it is |
|:--|:--|
| [neogeo-media-player](https://github.com/gufranco/neogeo-media-player) | A full-screen film with sound on a Neo Geo AES or MVS, and a library that plays one inside another game |
| [sms-media-player](https://github.com/gufranco/sms-media-player) | This repository |
| [fmv-core-python](https://github.com/gufranco/fmv-core-python) | The baker and measurement code the players share |

## Licence and credits

[MIT](LICENSE).

Built with [SDCC](https://sdcc.sourceforge.net/) and
[devkitSMS](https://github.com/sverx/devkitSMS). The demo film is the
[Sintel](https://durian.blender.org/) trailer by the Blender Foundation, CC BY
3.0. The regression films and their licences are listed in
[`tools/clips.manifest.json`](tools/clips.manifest.json).
