# Reproducible captures, then better ones

The plan and record (2026-11-14 to 21) of the work that made every MK capture rebuildable from the
player's own MK disc, then the fresh-clone check after each change. The commit ids name the private
development history, which the public repository doesn't carry.

**Goal:** anyone with their own discs runs `prepare.py` then `build.py` and gets
exactly the game we have, every pose, fatality and move. Then improve the
art on purpose, one reviewed change at a time.

**Why:** the build reads MK's fighters as captures in `extracted/`, made by
playing MK in the emulator over a week with changing tools and two hand-made
start states. A fresh run re-captures only 83% of the poses identically
(2026-11-14), and hand-tuned choices (fatality poses, pins, the dazed sway)
refer to poses by their place in those captures.

## The method

MK draws a fighter's frame by number: each fighter's `.OBJ` holds his
animation lists (frame numbers; Scorpion's idle at OBJ+$F000 is $12-$17), and
writing a frame number into the list he's playing makes MK draw exactly that
frame, on any machine, whatever the timing (tools to come: `mkframes.py`).

Every captured pose is then rebuilt from a **recipe**: one or more parts, each
"frame N of fighter F (or MK's shared effects), mirrored or not, cut to this
window, placed here". A recipe is only numbers, so it can be committed
(`data/` manifest); the pictures always come from the user's own disc.

Recipe parts (tools/lib/mkrecipes.py): a frame (number, mirrored, x, y), drawn by
the capture's own rules (its MK sprites; a sprite only below line 40; the
screen's edges); optionally only some of its sprites (a capture taken while MK
rewrote its sprite list); a one-pixel line of one colour (the spear's rope);
player 2's frames for victim captures (PRG RAM $7D808, palette line 1).

Status (2026-11-14, evening). Tools: `mkframes.py` (frame libraries per
source, cached in extracted/mk_frames/), `mkrecipes.py MK_DIR --out [--skip-done]`
(recipe files data/mk_recipes/, only the poses the build reads:
extracted/build_reads.json from `buildreads.py`, which also lists every file
the build reads in extracted/build_files.txt), `mkfromrecipes.py [--check]`
(captures drawn back), `mkcapmeta.py [--out|--check]` (anchors, orders,
timelines as numbers, palettes by fight state:line, data/mk_meta/: 235
captures, round trip exact).

Sources: 'STATE:PLAYER' (a fight state's player, frames $01-$FF by number;
0 is a command in MK's lists), 'REPLAY+AT:SLOT:PAL' (an object in a replayed
fatality: BONES.OBJ's fire 'scfatal+210:2:0', burning 'sonyafatal+290:1:1'),
and replay pieces ('szfatal': sprites that are no fighter's frame, Sub-Zero's
spine, named by pixel hash). Effects (drawn over, some sprites at a time):
Raiden's electricity and bolts $C7-$D8, the loser's head $D1-$D8, Kano's heart
$D1-$DA, Scorpion's fire. Rope lines only for Scorpion's spear.

Exact: Kano all 536 read poses (rebuilt and checked with mkfromrecipes);
the other fighters' runs were cut by a power loss part way (their finished
captures are in data/mk_recipes/). Known gaps: Sonya's fatality_burn (9),
Johnny's fatality_mk_victim (4), Sub-Zero's fatality_victim (RGB; recipes
match in "canonical" indices, black = empty: just fixed, rerun), Scorpion's
dizzy/lying/teleport_mk (hand-cleaned, no tool: recipes), fatality_skeleton
(derived from his RGB victim by nearest colour: next).

Fresh prepare (scratch clone, 2026-11-14): of the 848 files the build reads,
404 identical (disc extracts, portraits, the Pit's art), the Pit's plane_b
differs only in the HUD rows the build blanks; the captures and their number
files differ (recipes and mk_meta replace them); the 9 recorded sounds differ
(recording from the ORIGINAL state is byte-identical, so it's the fresh
states): to the ear Scorpion's (man), Johnny's, Kano's, Liu Kang's are the
same (spectrogram corr ~1.0), Sub-Zero's 0.99, Scorpion's (woman), Sonya's,
Raiden's, the Pit fall 0.89-0.97: to look into (an event a few frames apart
or a different scream?). Byte-identical sounds weren't possible from fresh
states at this point (solved on 2026-11-15 by rendering them: below).

**Proven (2026-11-14):** a scratch clone with every capture deleted, rebuilt
from data/ alone (`mkfromrecipes.py`, `mkcapmeta.py`, `mkburn.py`,
`mkfatality.py skeleton`; unread poses blank) builds a disc identical to the
working copy's in all 20 files (19 tracks and the cue). Recipes: 233 captures,
3638 poses (data/mk_recipes), number files and palettes for 236 (data/mk_meta).

**Fresh machine (2026-11-14, evening):** a new clone with only the discs and BIOS,
`prepare.py` then `build.py`: the data track is byte-identical (SHA-1 7cf7c190...),
tracks 1-18 and the cue too; only track 19 differs - the fatality music mixed with
the recorded fatality sounds, which fresh fight states can't record byte for
byte. MK's art now comes from tools/lib/mksch.py (no emulator for frames).

**Reproducible (2026-11-15):** two independent fresh clones (prepare + build from
nothing) build identical discs, all 20 files; the working copy's disc now matches
them too (its 9 recorded sounds replaced by the fresh recordings: the same events
within a frame; the originals kept outside the repository).
Disc: data track SHA-1 088d607c..., all files' sha1s hashed: 94477e7a....

**Merged (2026-11-15):** the disc-only extraction (palettes, portraits, the Pit,
the spine read from the MK disc). A fresh clone of the merge (only the discs and
BIOS) prepares and builds a disc identical to the working copy's in all 20 files
(data track SHA-1 0c7d94c5...); allchecks 52 of 52.

**No emulator (2026-11-15):** the nine sounds are rendered from the disc
(tools/lib/mksound_render.py, data/mk_sound; all byte-identical). A fresh clone with only
the discs - no BIOS, no emulator installed - prepares and builds a disc identical to
the working copy's in all 20 files (data track SHA-1 793615f7...). allchecks 52 of 52.

**Where it stood on 2026-11-15** (each since picked up: see the entries below):
1. Sonya's kiss as player 2 (the notebook): the kiss object crashed the sub CPU.
2. The one-frame flash before Scorpion's flames (the notebook).
3. Phase 3: the daze before/after, the teleport made whole, the rest.

## Phases

1. **Exact copy (the safety net).** For all seven fighters and the Pit:
   recipes for every pose the build reads; `prepare.py` rebuilds the captures
   from them. Done when a fresh clone (new venv, only the discs and BIOS)
   builds a disc whose every track matches the current one byte for byte.
2. **Merge.** Only after 1: the branch `reproducible-captures` goes into `main`,
   README updated, tested by following it on a clean copy.
3. **Better, one change at a time.** Candidates: clipped poses made whole
   (walk back, jumps; Scorpion's teleport punch: he comes in cut by the screen
   edge); every fighter's real MK dazed sway (only Scorpion
   has it); each move's frames from MK's own animation list, in MK's order;
   "Eternal Kombat" where the game says Eternal Champions (its text first; the
   title logo since done, 2026-11-23); the "Toasty!" easter
   egg when the player also has UMK3 (Genesis) - tools/capture/umk3toasty.py captures it
   into extracted/umk3_toasty/, the build doesn't use it yet; an optional
   input in the README; the silhouette crossing the Pit's moon (MK1's hint for
   Reptile), if MK CD has it (check on the disc). Each
   change: its own commit, a before/after reel, allchecks, and a look in play.

## Guard rails

- The original captures and states, and the repository, were backed up
  outside the repository before the work began.
- Work happens on `reproducible-captures` and in a scratch clone; the working
  copy's `extracted/` and `build/states/` are never overwritten by new tools until
  phase 1's byte-identical check passes.
- Phase 1 changes no game output: anything that would is phase 3.
- Every recipe is checked pixel for pixel against the original pose when it's
  made; a pose with no exact recipe stops the run (no silent fallbacks).
- No game data in git: recipes are numbers; pictures, palettes and sounds
  always come from the user's discs.
- No attribution lines in commits or files.
- Phase 3 changes must fit the game's memory: a pose stays within 112 tiles
  (scorpion_full.TILE_CAP: bigger ones draw scrambled), a fighter's .PL plus its
  tail within scorpion_full.MAX_PL (Raiden's is already near it), an effect
  sheet within its tile source. The build asserts these; frame checks (since
  retired) checked the frames; a change that doesn't fit is reworked, not forced.

**Sonya / mirror fixes (2026-11-15):** a fresh clone of main c257d06 (only the discs,
no BIOS, no emulator) prepares and builds a disc identical to the working copy's in
all 20 files (data track SHA-1 c1c3af19...). allchecks 59 of 59 (now with each
fighter's player-2 mirror-match fatality).

**Kano headbutt / knife (2026-11-15):** a fresh clone of main f5897fe (only the discs,
no BIOS, no emulator; the headbutt rebuilt from its new recipes) builds a disc
identical to the working copy's in all 20 files (data track SHA-1 840b27ce...).
allchecks 61 of 61.

**Vendettas on MK fighters, teleports, Kano's held-Block knife (2026-11-16):** a fresh
clone of a689b02 (only the discs, no BIOS, no emulator) builds a disc identical to the
working copy's in all 20 files (data track SHA-1 5882a317...). allchecks 73 of 73.

**Burn flash, square wave (2026-11-16):** a fresh clone of 9a3adf2 (only the discs)
builds a disc identical to the working copy's in all 20 files (data track SHA-1
d2a4ee33...). allchecks 73 of 73.

**Square wave at MK's height (2026-11-16):** a fresh clone of 2481248 (only the discs)
builds a disc identical to the working copy's in all 20 files (data track SHA-1
efd4e5da...). allchecks 73 of 73, squarewavecheck both sides.

**Sonya's leg grab (2026-11-16):** a fresh clone of 8529519 (only the discs) builds a
disc identical to the working copy's in all 20 files (data track SHA-1 6122e612...).
allchecks 77 of 77.

**Every fighter's daze sway, Raiden's daze (2026-11-16):** a fresh clone of 755af2e (only
the discs) builds a disc identical to the working copy's in all 20 files (data track
SHA-1 dfb88b6b...). allchecks 91 of 91 (dazecheck: all seven, both sides).

**Square-wave knockdown, shadow-kick trail, Raiden's flashes, lying poses (2026-11-16):** a
fresh clone of bc2a0c7 (only the discs) builds a disc identical to the working copy's in all
20 files (data track SHA-1 ebc10511...). allchecks 95 of 95.

**Teleport double, FINISH HER for Riptide, mirror teleport (2026-11-16, evening):** a fresh
clone of e16fd4a (only the discs) builds a disc identical to the working copy's in all 20
files (data track SHA-1 e55b76d0...). allchecks 96 of 97: Scorpion's Contest ending, a
latent boss-fight stall (docs/notes/2026-11.md), also reproduced on e71680a with a padded .PL.

**Scorpion in the Senator's slot, Blast back (2026-11-16, night):** a fresh clone of 0f16963
(only the discs) builds a disc identical to the working copy's in all 20 files (data
track SHA-1 2e8491fd...). allchecks 97 of 97.

**Liu Kang on Blast, the spear's knockout (2026-11-16, late):** a fresh clone of 4582529
(only the discs) builds a disc identical to the working copy's in all 20 files (data
track SHA-1 fa5e6ce1...). allchecks 111 of 111 (every MK fatality on Blast and Thanatos).

**Shang Tsung for the Eternal Champion (2026-11-17):** a fresh clone of 962aab1 (only the
discs) builds a disc identical to the working copy's in all 20 files (data track SHA-1
bbc3e8af...). allchecks 111 of 111 (every fighter's Contest through both Shang forms).

**The Eternal Champion back (2026-11-17):** a fresh clone of 801e75f (only the discs) builds
a disc identical to the working copy's in all 20 files (data track SHA-1 269edd68...).
allchecks 111 of 111.

**Shang Tsung as his own fighter (2026-11-17):** a fresh clone of edacd36 (only the discs, a
new venv, no BIOS) prepares and builds a disc identical to the working copy's in all 20 files
(data track SHA-1 7c1f3046...). prepare.py gained his moves (tools/lib/mkshangmoves.py): without
them a fresh clone had no extracted/mk_moves_shang. allchecks 112 of 112 (tools/checks/shangcheck.py
added; every fighter's Contest through Shang to the Dark Champion and the ending).

**Shang's morph (2026-11-18):** a fresh clone of 3836018 (only the discs, a new venv, no BIOS)
prepares and builds a disc identical to the working copy's in all 20 files (data track SHA-1
af4b3d59...). allchecks 112 of 112 (tools/checks/shangcheck.py: the morph and its colours frame by
frame; every fighter's Contest through Shang to the Dark Champion and the ending).

**MK throws and sweeps (2026-11-19):** a fresh clone of 7c2dfc9 (only the discs, a new venv,
no BIOS) prepares and builds a disc identical to the working copy's in all 20 files (data track
SHA-1 e18faea8...). allchecks 112 of 112 (throws as MK's, sweeps drop in place, no fatality
input while being thrown).

**Dark Champion hang fixed (2026-11-19):** a fresh clone of 9455b6c (only the discs, a new
venv, no BIOS) prepares and builds a disc identical to the working copy's in all 20 files (data
track SHA-1 0e8d99a8...). allchecks 112 of 112 (shadowkickcheck now also checks the palette
pool and the sprite list).

**Reptile (2026-11-19):** a fresh clone of 6789734 (only the discs, a new venv, no BIOS)
prepares and builds a disc identical to the working copy's in all 20 files (data track SHA-1
444b14d9...). allchecks 112 of 112 (a clean run; the earlier run's one failure, Kano's Pit
fall, was /tmp filling up during a parallel fresh-clone build, and passed alone).

**Reptile's spear, MK's roll, attack timing (2026-11-19, branch reptile-spear):** the first
fresh clone failed: the roll (mkinputs.jump_plan) reads the jump captures' order.txt, which
data/mk_meta didn't carry (the build had never read it). buildreads.py + mkcapmeta.py --out
added it (jump_fwd/jump_back of Johnny, Kano, Liu Kang, Sub-Zero; mkcapmeta --check: all the
same). Then a fresh clone of d9ba199 (only the discs, a new venv, no BIOS) prepares and builds a
disc identical to the working copy's in all 20 files (data track SHA-1 96e00ed3...). allchecks
113 of 113 (c56c4f5; d9ba199 adds data only).

**Rolls for six fighters (2026-11-19, later):** after Scorpion's jump timelines went into
data/mk_meta, a fresh clone of c43aa5b (only the discs, a new venv, no BIOS) prepares and builds
a disc identical to the working copy's in all 20 files (data track SHA-1 d84ab3cf...).
allchecks 113 of 113 (7de998c; since then notes only).

**Block, crouch attacks, MK's jumps for all (2026-11-20):** a fresh clone of 2e51c74 (only the
discs, a new venv) prepares and builds a disc identical to the working copy's in all 20 files
(data track SHA-1 e7a2b31f...). allchecks 114 of 114.

**Round end, roundhouse, knockdowns (2026-11-20):** a fresh clone of 33c9a75 (only the discs, a new
venv) prepares and builds a disc identical to the working copy's in all 20 files (data track SHA-1
a9b9e87a...). allchecks 116 of 116.

**Frame slots, kick reaction (2026-11-20):** the first fresh clone of 68b23eb differed: the kick
plan read hit_kick captures that had no recipes (the clone's plan fell back). mkrecipes for hit_kick
(all exact; Shang keeps hit_high: no recipe source), then a fresh clone of b38344f (only the discs, a
new venv) builds a disc identical to the working copy's in all 20 files (data track SHA-1
db3d6a5f...). allchecks 116 of 116.

**Raiden's knockdown and roll, sheet $45 stripped (2026-11-20):** a fresh clone of 1620f27 (only the
discs, a new venv) builds a disc identical to the working copy's in all 20 files. allchecks 116 of 116.

**Contest freeze, jump attacks, Scorpion's kick (2026-11-20):** a fresh clone of a8e7568 (only the
discs, a new venv) builds a disc identical to the working copy's in all 20 files. allchecks 116 of 116.

**Whole MK captures, spear miss/block, MK hit sounds (2026-11-21, branch reptile-spear):** a fresh
clone of 9e079c0 (only the discs, a new venv) builds a disc identical to the working copy's in all
20 files (data track SHA-1 c6280898...). allchecks 116 of 116 (resumed once: tools/checks/allchecks.py now
writes each result to build/allchecks.progress and --resume skips what passed on the same build).
Merged into main (fast-forward to 9e079c0).

**Spear sounds, sound banks, Ramses' draped frames (2026-11-21):** a fresh clone of c16ffa2 (only the
discs, a new venv) builds a disc identical to the working copy's in all 20 files (data track SHA-1
c8d00a1c...).
allchecks 117 of 117 on c16ffa2's build (a full run: 13 min). Merged into main.

**MK punch reaction to EC punches, first hit frame, Reptile's spear miss (2026-11-21):** a fresh clone
of 1bd3002 (only the discs, a new venv) builds a disc identical to the working copy's in all 20 files
(data track SHA-1 89b70d35...). allchecks 117 of 117 (13 min). Merged into main.

**Jump attack landing (2026-11-21):** a fresh clone of 9f7ac6e (only the discs, a new venv) builds a disc
identical to the working copy's in all 20 files (data track SHA-1 fec5e0d9...). allchecks 117 of 117.
Merged into main.

**Z blocks, FINISH HIM round end (2026-11-21):** a fresh clone of cf0d439 (only the discs, a new venv)
builds a disc identical to the working copy's in all 20 files (data track SHA-1 fbf0c268...).
allchecks 118 of 118 (blockcheck new). Merged into main.

**MK's Block pose at once, Scorpion's fatality with Z (2026-11-21):** a fresh clone of 8d4a1fe (only the
discs, a new venv) builds a disc identical to the working copy's in all 20 files (data track SHA-1
27cb26f0...). allchecks 118 of 118. Merged into main.

**Reptile's spear sounds, MK's walk pace, FALL2, two hangs fixed (2026-11-21):** a fresh clone of 7551629
(only the discs, a new venv) builds a disc identical to the working copy's in all 20 files (data track
SHA-1 4c8d30bd...). allchecks 120 of 120 (spearsoundcheck and airspearcheck new). Merged into main.
