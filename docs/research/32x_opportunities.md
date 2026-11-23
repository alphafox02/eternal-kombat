# What the 32X could add (feasibility study, 2026-11-22)

Read-only study: nothing was built or run. Facts carry a file path or URL; anything else is marked
**guess**. Sizes are rough working days for someone who knows this repo.

**Short answer:** little. The 32X has many more colours, but neither disc has art with more colours
to show: MK CD's and EC CD's pictures were all drawn for the Genesis. The 32X
can only undo colour *sharing* forced by EC's screens (as it does for the select portraits), and can
cover something the build can't patch (the title logo). The two things players would notice most, the
title and the missing poses, are better fixed on the plain Sega CD, for everyone.

**Since this study:** item 1 is done (2026-11-23). The logo screen turned out to be a still picture
on plane B, whose tiles are in GAME.DAT, so the title now says ETERNAL KOMBAT on every Sega CD
([mk_fidelity_spec.md](../mk_fidelity_spec.md), section 7); item 4 is moot. The 32X support is now
optional (`tools/build.py --32x`).

## Ranking (value to a player against cost)

| # | Item | Needs 32X? | Value | Size | Verdict |
|---|---|---|---|---|---|
| 1 | Title logo says ETERNAL KOMBAT, drawn by the Genesis VDP over the logo | no | high, every player | 3-6 days (guess) | do first |
| 2 | More MK poses by freeing Sega CD memory (packing, free Word RAM, dead Blade code) | no | high, every player | 1-2 weeks, in steps | do second |
| 3 | Make the existing 32X support trustworthy (hardware test, open items in docs/32x.md) | yes | medium, 32X owners | 1-3 days + a real machine | before any new 32X work |
| 4 | Title logo by the 32X | yes | medium, 32X owners only | 2-4 days | only if item 1 proves impossible |
| 5 | Versus screen (and unlocked Shang/Reptile) portraits in their own colours | yes | low | 2-4 days | optional polish |
| 6 | Stage backgrounds in more colours | yes | none to low: no richer art exists | 2-3 weeks | not worth it |
| 7 | Extra fighter poses or whole fighters drawn by the 32X | yes | high in theory | 4-8 weeks, high risk | not worth it |
| 8 | Blood, fire, lightning, fatality effects by the 32X | yes | very low | 1-2 weeks | not worth it |

## What the 32X is, in this project's terms

- **A second picture.** A 320-wide bitmap with 256 colours from 32,768 (or 32,768 direct, but then
  only 204 lines fit), mixed with the Genesis picture. Two 128 KB frame buffers, one shown, one
  drawn. No sprites, no tiles. (https://raw.githubusercontent.com/viciious/32XDK/master/docs/32x-hardware-manual.md, 1.1, 2.2, 3.3)
- **Layering is coarse.** The whole 32X picture is behind the Genesis picture or in front of it
  (PRI bit), and each 32X pixel can flip to the other side (the "through" bit). Behind, it shows only
  where the Genesis pixel is colour 0. There is no "between plane B and the sprites" or "between the
  two fighters". (same manual, 3.2.3, 3.3 Priority)
- **Scrolling:** a table gives each screen line its start address in the buffer: vertical scroll is
  free, horizontal is 2 pixels at a time per line, plus one whole-screen 1-pixel shift. (3.2.3, 3.3)
- **Width:** the Genesis must be in the same width as the 32X (320). EC's movies run at 256 wide
  (docs/research/cinekill_film_research.md), so the 32X layer must stay off during them.
- **Two SH-2 CPUs (about 23 MHz) with 256 KB of RAM.** From a CD there is no cartridge: the Genesis
  68000 writes a small SH-2 program into the frame buffer, writes `_CD_` to a communication
  register, and the 32X's boot ROM copies and starts it. The repo does this already
  (tools/x32/32x_art_probe.py, `sh2_boot_demo` / `sh2_transfer_demo`).
- **What the repo's 32X code is today:** the SH-2 program is 12 bytes that park both CPUs. All
  drawing is done by the Genesis 68000 writing the frame buffer (`$840000`) and palette (`$A15200`)
  (tools/x32/32x_select_incremental_hook.py, 32x_cursor_roster_hook.py). The data reaches it from
  PRG-RAM at 512 bytes per VBlank, with the sub CPU's bus held while it copies
  (tools/x32/32x_select_incremental_transfer.py). So "the 32X draws" is, so far, "the 68000 draws on
  the 32X's screen". Real SH-2 code would be new ground here.
- **Talking to the SH-2s:** eight shared 16-bit registers, an interrupt the 68000 can raise, and a
  FIFO for bulk data (manual 3.2.1, 3.3). The game logic is on the *sub* CPU, which cannot see the
  32X at all: everything goes sub CPU -> main CPU -> 32X.
- **Precedent:** Doom CD32X Fusion uses CD + 32X but boots from a cartridge and loads extras from the
  CD (https://www.timeextension.com/news/2024/10/doom-cd32x-fusion-is-the-first-non-fmv-game-to-utilize-the-segas-tower-of-power).
  CD-only 32X boots are Sega's `CD_ICD`/`CD_V1A`/`CD_V2A` demos
  (https://www.retroreversing.com/sega-32x-sdk; the page lists them without contents) and the few
  commercial video games. A CD-booted 32X layer over a live game is rare ground, and ours has never
  run on hardware (docs/32x.md, Open 1).

## Is there higher-colour art on the discs? No.

Measured from files already in `extracted/` and `build/runs/` (colour counts with PIL, today):

| Source | Colours |
|---|---|
| MK CD select portraits (extracted/mk_moves*/portrait.png) | 11-14 each |
| MK CD Pit planes (extracted/mk_stages/pit/plane_a.png, plane_b.png) | 17 and 8 |
| MK CD Goro's Lair plane (extracted/mk_stages/lair/plane_a.png) | 14 |
| MK CD Pit, whole screen with fighters (extracted/mk_stages/pit/screen.png) | 45 |
| EC intro movie frame (build/runs/20261122-222701/01_boot/4-title.png, 256x224) | 35 |
| EC logo/menu screen (same run, 5-main-menu.png, 320x224) | 32 |

- MK's fighters are 15 colours each (docs/research/mk_disc_formats.md, fight palettes).
- EC's movies (`ZZ00.BIN`, `ZK.*`, `ZB.*`) and MK's intro (`MORTAL.ANM`, MK's own format,
  docs/notes/2026-11.md line 775) are video made for the Genesis's palette. A frame has about as
  many colours as a game screen. They are not a richer source, and they are grainy.
- The only richer MK art is the arcade game's. It is not on the player's discs, so the
  reproducibility rule excludes it (an early experiment with it was dropped;
  tools/x32/32x_cd_roster_preview.py says "No arcade assets").
- **So where do the select screen's "159 colours" come from?** Seven portraits of 11-14 colours each
  are about 85 colours in all; the rest are in-between shades made when the packer resizes them
  (Lanczos, tools/x32/32x_cd_roster_preview.py). EC's select screen makes all the icons share one
  palette line (docs/notes/2026-11.md line 493). The 32X's gain there is real, but it is "each
  portrait keeps its own colours", not "better art".

That is the pattern for every item below: the 32X helps only where an EC screen forces MK pictures
to share colours.

## Plain Sega CD first

The 32X can never be assumed. These help every player and should come before any 32X-only work.

1. **The title logo with VDP sprites or tiles** (item 1 below).
2. **More poses from the memory there is** (item 2 below).
3. **Backgrounds:** nothing to do. MK's Pit is already MK's art in MK's colours; no source has more.
   If a stage ever did need more colours, the VDP's own tricks (a palette change part-way down the
   screen, shadow/highlight) would be the first tool, not the 32X. **Guess:** EC's stage code would
   fight a mid-screen palette change; not looked at.
4. **Select/versus colours without a 32X:** the Genesis portraits share one line of 14 colours. A
   better shared palette (chosen over all seven portraits at once) or a second line, if the select
   screen has one spare, would improve the plain disc's portraits. **Guess**, not measured: 1-2 days
   to find out.

## 1. Title logo by the Genesis (no 32X) - do first

- **Today:** the logo screen says ETERNAL CHAMPIONS / CHALLENGE FROM THE DARK SIDE. The spec then
  took it for the last frames of the intro movie, which the build can't easily re-encode
  (docs/research/cinekill_film_research.md); it has since been found to be a still picture.
- **New fact:** the logo screen is 320 wide with only 32 colours on it, and has a line of ordinary
  VDP text on it (build/runs/20261122-222701/01_boot/5-main-menu.png). So the VDP is in its normal
  mode there, and 32 colours is two palette lines' worth. **Guess:** one or two lines are spare.
- **Idea:** don't touch the movie. Once the logo screen is up, the main CPU puts an ETERNAL KOMBAT
  logo over it as sprites (or as plane tiles, if the logo turns out to be a still picture in VRAM).
  Opaque logo pixels cover EC's lettering; a dark plate can cover what the new logo doesn't.
- **Art:** from the discs, by script: EC's "ETERNAL" from this very screen, "KOMBAT" from MK CD's
  title lettering (spec section 7 already proposes this).
- **What it takes:** find where MAIN.BIN shows this screen; a spare palette line and about 100-150
  tiles of VRAM; a sprite list (a 200 x 60 logo is about 20-30 sprites, inside the VDP's limits).
- **Risk:** medium. Unknown until measured: whether the water behind the logo is still playing as
  video (then the main CPU is busy feeding it, and its palette may change), and whether any palette
  line is really free.
- **Size:** 3-6 days (guess), most of it finding the screen's code and making the logo art.

## 2. More poses on the plain Sega CD - do second

The limit is Sega CD memory, not the VDP: each fighter's `.PL` must fit its load area (player 2:
PRG-RAM `$51800`-`$7FFFF`, 190,464 bytes; player 1: Word RAM `$81800`, 196,608), and the build caps
it at 188,416 (docs/notes/2026-11.md lines 539, 612-618). MK fighters' files are 155-187 KB. The
notebook already lists unused room:

- Repacking the frame records: about +13 KB per fighter; shared sub-frames (opcodes `$F4`-`$F7`):
  not yet used (docs/notes/2026-11.md, "Still open", lines 634-639).
- Poke-tested free memory: Word RAM `$80000`-`$817FF` (6 KB), `$B9960`-`$BD8FF` (16 KB),
  `$BDAE8`-`$BFACF` (8 KB); art banks work from Word RAM, since bank offsets are 32-bit (same
  place, lines 620-625).
- The 188,416 cap comes from one EC file's size on disc (line 539), not from RAM: about 2 KB (player
  2) to 8 KB (player 1) more is there if the file can grow. **Guess:** needs the file moved on disc.
- Code room is the other limit (Sonya's block has 18 bytes; docs/mk_fidelity_spec.md 0a, 0g). The
  notebook's own next step is to prove which of Blade's special-move code no MK fighter reaches and
  reuse it (docs/notes/2026-11.md, 2026-11-22 evening, "Sonya's room").

At about 1 KB a pose (117 poses in 115 KB, line 631), 30 KB is roughly 30 more poses per fighter:
most of the knockdown, or half the missing throw and cast poses. Size: 1-2 weeks in steps, each one
checkable with the existing suite. Risk: medium (the notebook records hangs from `.PL` overruns).

## 3. Make the existing 32X support trustworthy

Before adding anything: docs/32x.md lists what is unproven: no run on real hardware (SH-2 start,
bus sharing, VBlank timing, scratch RAM), the detection on a Sega CD *without* a 32X on real
hardware, the Tournament, and the moment the Genesis portraits show through during a confirmation.
Shang Tsung and Reptile, once unlocked, have no 32X portrait (the packer lists seven:
tools/x32/32x_cd_roster_preview.py `ROSTER`). **Guess:** 1-3 days of work, plus someone with the
machine. Every new 32X feature multiplies this unproven surface; that is the main cost of items 4-8.

## 4. Title logo by the 32X - only if item 1 fails

- **How:** the same machinery as the select screen: detect the logo screen in the VBlank
  coordinator, copy a packed logo picture and palette to the 32X, show it in front of the Genesis
  picture (PRI/through), hide it when the screen leaves. The 68000 does it all; no SH-2 code. The
  screen is 320 wide, so the widths match.
- **Advantage over item 1:** needs no VDP palette line, tiles or sprites; up to 256 colours of its
  own. But the lettering sources (EC's and MK CD's logos) are Genesis-coloured anyway.
- **Without a 32X:** the screen still says Eternal Champions. That is the reason it ranks below
  item 1: the name of the game should not depend on an add-on.
- **Risk:** medium: fades (the 32X palette doesn't follow EC's fade unless we make it), the demo
  loop back into the 256-wide movie, more unproven hardware behaviour.
- **Reproducible:** yes, like the portraits: art from the discs by script, 68000 code from `Asm`.
- **Size:** 2-4 days.

## 5. Versus screen and other portraits by the 32X

- EC's versus screen draws portraits for ids 2-25 with shared palettes; Reptile's is Sub-Zero's
  tiles recoloured (docs/notes/2026-11.md, 2026-11-22 daytime). The 32X could show each MK
  portrait in its own colours there, as on select, and add Shang's and Reptile's.
- **Without a 32X:** as today. **Size:** 2-4 days, mostly detecting the screen and its fades.
- **Value:** low. The picture is on screen for a couple of seconds, and the gain is the same modest
  one as on select. Worth doing only if the select portraits turn out well liked on real hardware.

## 6. Stage backgrounds in more colours - not worth it

- **It could be made to work.** Put the 32X behind the Genesis picture, leave the back plane empty
  (colour 0), keep fighters, HUD and the front plane on the VDP: the fighters then stand in front
  of a 32X background with no priority problem. A 512 x 224 picture in 256 colours is 115 KB and
  fits one frame buffer; scrolling is then only rewriting the 224-entry line table each frame and
  swapping buffers, cheap enough for the 68000. Parallax bands (the Pit's three cloud bands,
  docs/notes/2026-11.md line 887) work per line, in 2-pixel steps.
- **But there is nothing better to draw.** The Pit's planes have 17 and 8 colours; no file on
  either disc has a richer Pit, or any richer stage (table above). The 32X would show the same
  picture. Smoother skies would mean inventing art, which is neither MK CD's look nor "from the
  player's discs".
- **Costs:** loading 115 KB twice (both buffers) through a path that today moves 512 bytes a frame,
  so a faster transfer and longer stage loads; every fade, flash, tint and stage finisher that
  changes the stage's palette must be mirrored to the 32X palette, or the background pops while the
  rest fades; the stage must still be complete on the VDP for players without a 32X, so two versions
  of each stage to build and check; `allchecks` can't see the 32X (Genesis Plus GX has none).
- **Size:** 2-3 weeks for one stage. **Risk:** high. **Value:** none to low. Skip.

## 7. Fighter poses or whole fighters by the 32X - not worth it

- **Layering fails first.** A 32X fighter can only be in front of the whole Genesis picture or
  behind all of it. In front, he covers the other fighter, projectiles, blood, and any stage
  foreground, whatever the engine intended; behind, the stage hides him. EC decides which fighter
  is in front; the 32X can't follow that.
- **The 32X's RAM can't feed the VDP.** Its 256 KB is reachable from the Genesis only through
  eight small registers, so it can't serve as extra `.PL` memory for ordinary sprites. A pose drawn
  from 32X memory must be drawn on the 32X's own layer.
- **The engine side is large.** The sub CPU would have to send pose, position, flip and palette
  every frame through the main CPU; hide its own sprite on exactly those frames; and keep a full
  second path for no-32X play, in modules with almost no free bytes (item 2). Shadows, EC's tints
  (docs/notes/2026-11.md, "Riptide's bubble"), freezes and fades would all need 32X twins. It needs
  real SH-2 code (drawing a 100 x 130 pose each frame), which the repo has never had: a small SH-2
  assembler in Python beside `mkinputs.Asm` (1-2 days, guess) or a pinned toolchain, which would
  break "a fresh clone builds with Python alone".
- **Without a 32X:** today's reduced poses, so the plain disc gains nothing. A pose switching
  between VDP and 32X mid-move would be hard to make seamless (the 32X layer is one frame late if
  the 68000 relays it: guess).
- **Size:** 4-8 weeks, high risk, for 32X owners only. Item 2 gives much of the gain to everyone.

## 8. Effects (blood, fire, lightning, fatalities, the Pit) by the 32X - not worth it

- The 32X in front, with only effect pixels drawn, would layer acceptably (effects are usually on
  top). But MK CD's effects are small 15-colour sprites; the VDP already shows them as MK does.
- The known gaps are not colour problems. Raiden's fatality uses EC's droplets and an approximate
  tint (README, Known issues) because of sprite art room and palette lines: that is item 2's
  territory, and fixing it there fixes it for everyone.
- The Pit fall and the fatalities are already MK's art and sound. Nothing for the 32X to add.
- **Also nothing:** the 32X's two PWM sound channels (the Sega CD already has CD audio and its PCM
  chip); cleaner Cinekill video (no better source; docs/research/cinekill_film_research.md calls
  it a project).

## Not determined

- **Whether the logo screen is a still or playing video**, and whether a VDP palette line and tiles
  are free there. This decides item 1's size. Needs one emulator session (VRAM, CRAM and sprite
  table on that screen); nothing was run for this study. (Since answered: a still, with four spare
  palette slots.)
- **Whether Eternal Kombat's Pit loses any of MK's colours** to EC's stage palette budget. No note
  says so; if it does, that is a plain-VDP palette question first.
- **The select screen's spare palette lines** (Plain Sega CD first, point 4).
- **Real hardware:** everything about the CD-booted 32X layer. Also how the 68000's exception
  vectors behave once the adapter is on with a CD and no cartridge: the hardware manual describes
  the cartridge case only and never mentions the Sega CD; the build works in PicoDrive and ares
  (docs/32x.md).
- **Sega's CD boot demos' contents** (`CD_ICD` etc.): the index page lists names only. No source or
  write-up of Doom CD32X Fusion's CD side was found.
- **All sizes** are estimates from reading, not from trying.
