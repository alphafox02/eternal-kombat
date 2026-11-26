# Eternal Kombat

**Mortal Kombat's fighters inside Eternal Champions, on one Sega CD disc that you build from your own
two games.** The result is an ordinary Sega CD disc image (BIN/CUE) for an emulator or a burned
CD-R; an optional build also uses a 32X when one is attached (below).

https://github.com/user-attachments/assets/f60cf228-e38a-479d-89c5-50f12dce9120

*The built disc, recorded in an emulator, cut to MK CD's Mortal Monday music
(`tools/dev/trailer.py` makes it from your own build).*

## The two games

- ***Mortal Kombat*** (Midway's 1992 arcade game; its 1993 Sega CD version is the one used here):
  digitised actors, special moves done with joystick motions, and the fatality - FINISH HIM - at the
  end of a fight.
- ***Eternal Champions*** (EC; Sega's own fighting game, 1993 on the Genesis; the 1995 Sega CD version,
  *Challenge from the Dark Side*, is the one used here): hand-drawn fighters from across history,
  each with a home stage, and known for its many finishers - *Overkills* (a stage kills
  the loser), *Vendettas* (each fighter's own finisher), *Sudden Deaths* and *Cinekills* (short
  movies).

Eternal Kombat takes the Eternal Champions CD as the game and puts MK's fighters into it, drawn,
moving, timed and sounding as they do on MK CD. Both casts share one select screen: MK fighters
against Eternal Champions, Eternal Champions' finishers on MK fighters, MK fatalities on everyone.

## What you get

Nine MK fighters. Seven are on the select screen from the start: **Scorpion, Raiden, Johnny Cage,
Sub-Zero, Liu Kang, Kano and Sonya**, in the slots Eternal Champions keeps for its hidden extras.
**Shang Tsung** and **Reptile** are hidden at first, as in MK.

- MK's art, colours, attacks, walk, jumps, throws and specials (spear, teleport, lightning,
  torpedo, green bolt, shadow kick, ice blast and freeze, slide, fireball, flying kick, knife,
  cannonball, square wave, energy rings, leg grab), done with MK's inputs.
- FINISH HIM / FINISH HER with MK's music, announcer and dazed sway, and every MK fighter's
  fatality, on Eternal Champions' fighters and MK's alike.
- Eternal Champions' Vendettas and stage Overkills work on MK fighters too (their death art redrawn
  from MK's), on Eternal Champions' stages.
- MK CD's six stages, each with its MK music: the Courtyard (its monks swaying), the Palace Gates
  (its torches burning), the Warrior Shrine, the Pit (with the fall to the spikes), the Throne Room
  and Goro's Lair (the eyes blinking in the dark). On all six MK's announcer says FIGHT!; on five
  of them MK's FIGHT! and FINISH HIM / FINISH HER zoom in as in MK. A fight with an MK fighter
  in it is on one of them at random, never the same one twice running; two Eternal Champions
  fighters fight on Eternal Champions' stages as before. In a Duel, BACKGROUND SETTING can still
  name an Eternal Champions stage for anyone (PLAYER 2: player 2's home).
- The one-player mode (the Contest) for every MK fighter, through Eternal Champions' bosses to his
  MK ending, with **Shang Tsung** (MK's boss, taking his opponent's form) on the way and **Reptile**
  hidden as in MK; both become selectable once you've won it.
- The title says ETERNAL KOMBAT, and the menus play Eternal Champions' theme, then MK CD's
  Mortal Monday music.
- **Optional, with a 32X** (`tools/build.py --32x`): the select screen shows MK CD's own portraits,
  drawn by the 32X; without one that disc plays the same. Experimental, tested in emulators only
  ([docs/32x.md](docs/32x.md)), so the standard build leaves it out.

## Quick start

You need Linux with Python 3.11+, and your own rips of the *Eternal Champions: Challenge from the
Dark Side* (USA) and *Mortal Kombat* (USA) Sega CD discs as BIN/CUE (see
[below](#this-repository-contains-no-game-data)). Copy each disc's folder (its .cue and .bin files)
into `roms/`, then:

```
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python3 tools/checkinputs.py     # finds and checks your discs under roms/
python3 tools/prepare.py         # MK's fighters, from your MK disc
python3 tools/build.py           # -> build/Eternal Kombat/Eternal Kombat.cue
```

Play the cue in any Sega CD emulator (Genesis Plus GX, PicoDrive, ares), with
`tools/play.py window` (below), or burn it to a CD-R ([on a real Sega CD](#on-a-real-sega-cd)). For the 32X portraits, `tools/build.py --32x` and an emulator with
Sega CD + 32X (PicoDrive, ares).

## Controls

Both casts use the same pad; the buttons mean MK's moves for MK fighters and Eternal Champions'
for its own. With a six-button pad and Controller Setup as it starts:

| Button | MK fighters | Eternal Champions fighters |
|---|---|---|
| X | low punch | punch (Straight) |
| Y | high punch | punch (Lunge) |
| Z | **block** | punch (Swing) |
| A | low kick | kick (Snap) |
| B | high kick | kick (Thrust) |
| C | roundhouse | kick (Wheel) |
| hold back | walks back, and blocks an attack | walks back, and blocks an attack |

For MK fighters:
- **Blocking:** hold Z as in MK, or hold back as in Eternal Champions; down + Z blocks low.
- **Back + B** is the roundhouse and **back + A** the sweep, as MK's away + high kick and away + low
  kick; C and down + C give them too.
- **Down + X or Y** is the uppercut; **down + A or B** the low kick (Johnny Cage's down + B is his
  split punch).
- **Up close, B** throws, as MK CD's high kick; toward + Y throws too. X or Y is MK's close punch
  (Kano's headbutt) and A the knee (Raiden keeps his usual low kick there).
- **Special moves and fatalities** take MK CD's own motions with these buttons (Z where MK says
  Block). Where MK names a punch either punch does it, as on MK CD.

| Fighter | Special moves | Fatality (at FINISH HIM) |
|---|---|---|
| Scorpion | spear: back, back + punch; teleport punch: down, back + punch | hold Z: up, up |
| Raiden | lightning: down, toward + punch; torpedo: back, back, toward; teleport: down, up | toward, back, back, back + punch |
| Johnny Cage | green bolt: back, toward + punch; shadow kick: back, toward + A; split punch: down + B | toward, toward, toward + punch |
| Sub-Zero | ice blast: down, toward + punch; slide: back + A + B | toward, down, toward + punch |
| Liu Kang | fireball: toward, toward + punch; flying kick: toward, toward + B | down, back, up, toward, down |
| Kano | knife: hold Z: back, toward; cannonball: toward, down, back, up | back, back + punch |
| Sonya | rings: Y, back, punch; square wave: toward, back + punch; leg grab: up close, down + X + A | toward, toward, back, back + Z |

(punch: X or Y)

**Three-button pad:** A, B and C are the kicks (low kick, high kick, roundhouse for MK fighters),
and Start + A, B or C the punches and Z: Start + A low punch, Start + B high punch, Start + C block.
Holding back blocks too. Everything works on three buttons, but a six-button pad is recommended
for MK fighters, with block and both punches on their own buttons.

## Where things are

| | |
|---|---|
| `tools/` | the commands: `checkinputs.py`, `prepare.py`, `build.py`, `play.py` |
| `tools/lib/` | the library they use: the patches, the disc and emulator code, the MK extractors |
| `tools/checks/` | the test suite (`allchecks.py`) and `play.py test`'s scenarios |
| `tools/capture/`, `tools/dev/`, `tools/x32/` | how the MK data was measured; developer tools; the 32X support's steps |
| `data/` | the committed numbers that rebuild MK's art and sounds from your disc (no art, no sound) |
| `docs/` | [tools.md](docs/tools.md) (every tool, one line each), [architecture.md](docs/architecture.md), [mk_fidelity_spec.md](docs/mk_fidelity_spec.md) (what "as MK CD" means and what's open), [maintaining.md](docs/maintaining.md) (the rules and the gate), [32x.md](docs/32x.md), [release.md](docs/release.md); `research/` finished investigations, `notes/` the lab notebook |
| `roms/`, `bios/` | yours: the discs and BIOS (never committed) |
| `extracted/`, `build/` | generated: what `prepare.py` makes from your discs; the disc and the emulator's output (never committed) |

## Why Eternal Champions is the host

Eternal Champions CD's engine is modular. Every fighter, stage and stage finisher is a
separate 68000 code module on the disc (`BLA.CO`, `BLA.OC`, `BLAD.AI`, ...)
that calls into a fixed table of engine services in `SUB.BIN`. Adding a
fighter means adding modules, not rewriting the game. MK's fighters are pure
data driven by code shared across the whole game, so the reverse direction
is much harder. Each MK fighter starts as a copy of one Eternal Champions fighter's module (Blade's),
with MK's art, animations and sounds in it and MK's own moves added as new code. Details:
[docs/architecture.md](docs/architecture.md), [docs/notes/2026-11.md](docs/notes/2026-11.md).

## This repository contains no game data

You supply your own rips. Put them anywhere under `roms/`, in any layout
(one bin per track or a single bin, any file names):

```
roms/   Eternal Champions: Challenge from the Dark Side (USA)   required: the engine
        Mortal Kombat (USA) (Sega CD)                            required: the content
        Mortal Kombat Kanzenban (Japan)                          optional
bios/   bios_CD_U.bin  (Sega CD Model 1 v1.10)                   for the emulator (captures, tests)
```

Discs are recognised by the SHA-1 of their data track, so file names don't
matter. The format is BIN/CUE with raw 2352-byte sectors, as Redump dumps are:

| Disc | Data track (Track 01) SHA-1 |
|---|---|
| Eternal Champions: Challenge from the Dark Side (USA) | `261809c666e5d91626a222f252caa383c50cecb9` |
| Mortal Kombat (USA) | `79e0dd945681f8ed25fa6857dcac6a3fc8bb3d5f` |

Other rips (ISO + MP3/OGG/WAV, CHD) need converting to BIN/CUE first (a CHD with
`chdman extractcd`), and archives (.7z, .zip, .rar) extracting; `tools/checkinputs.py` says
whether what it found is the right dump. Nothing made from them (`extracted/`, `build/`) is ever committed: `.gitignore`
keeps it out.

## Setting up (Linux)

System packages: Python 3.11+ with venv (the tools run with `python -P`), and for
the optional extras `ffmpeg` (videos) and Tk (`python3-tk`, the play window).

```
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt          # what the build needs
pip install -r requirements-dev.txt      # + the emulator (playing, tests, research)
python3 tools/checkinputs.py             # finds and verifies your discs and BIOS
```

### The MK fighters' data

The build reads MK's fighters (poses, portraits, fatalities, sounds) and MK's stages
from `extracted/`, made from your MK disc by

```
python3 tools/prepare.py                 # reads only your discs: no emulator, no BIOS
```

- **Poses:** MK's fighter art is decoded straight from its files on your disc
  (`tools/lib/mksch.py`), and every pose is drawn from a recipe in `data/mk_recipes/`
  (which MK frame, mirrored or not, where: numbers only, no art). Their anchors,
  timings and palette references are in `data/mk_meta/`. These rebuild the poses
  pixel for pixel.
- **Portraits and the stages:** decoded from MK's files on your disc. Where MK puts each
  stage tile on its screen, and how its camera scrolls each band, is in `data/mk_stages/`
  (measured once from MK: numbers only, no art).
- **Sounds:** the fatality sounds and the Pit fall's are rendered from MK's
  samples and CD tracks on your disc as MK plays them (`data/mk_sound/`:
  measured once on the pinned emulator core; byte for byte the recordings that
  were made by playing MK: `tools/lib/mksound_render.py --check`).

Two fresh setups build the same disc, byte for byte (all 22 tracks and the cue).

A step whose output is there (and whose inputs haven't changed) is skipped, so an
interrupted run picks up where it stopped; `--list` shows the steps.

## Building

```
python3 tools/build.py            # -> build/Eternal Kombat/Eternal Kombat.cue
python3 tools/build.py --32x      # the same with the (experimental) 32X support
```

The build copies your EC disc and applies `tools/lib/patches.py` in order,
patching files inside the ISO9660 data track in place and recomputing each
touched sector's EDC/ECC. Audio tracks are hard-linked. The same inputs give
a byte-identical disc. `--list` shows the patches, `--skip NAME` leaves one out.

## Playing and testing

```
python3 tools/play.py window                   # play the built disc, with sound (needs requirements-dev.txt and the BIOS)
python3 tools/play.py test --no-build          # the scenarios in tools/checks/scenarios/
python3 tools/checks/allchecks.py              # every check, every MK fighter
```

In the window: arrows, Enter = Start, `a` `s` `d` = X Y Z, `z` `x` `c` = A B C; F2 / F4 save and
load a state, F12 a screenshot.

`play.py test` runs every scenario headless at about 25x real time and writes
`build/runs/<time>/report.md` with a contact sheet per scenario. Run it after every
build: it re-saves `build/states/menu.state`, which other tools start from (a state
saved before a build that moved files is refused).

`allchecks.py` runs the test suite, then for each MK fighter: his fatality as
player 1 and player 2, a mirror match, a fight against the CPU, the Pit's fall,
ten matches of the one-player Contest and its ending.

Save states only once the game is idle. A state saved while the game is
still reading the CD restores into a hung drive.

### On a real Sega CD

The built disc is a standard multi-track BIN/CUE: burn `Eternal Kombat.cue` to a CD-R in
disc-at-once mode (most CD-burning software reads the cue directly), or load the folder on an optical
drive emulator. So far it has been played in emulators only (Genesis Plus GX; PicoDrive and ares for
the 32X build): reports from real hardware are welcome.

## Known issues

- **Scorpion's and Reptile's spear:** an MK fighter on the rope leans back as in MK, but an EC
  fighter shows a standing recoil of his own (MK has no art of them). The victim bleeds less, and is not
  shaken on the rope as MK shakes him. The flying rope reaches back to his hand, where MK's runs on
  behind him to the screen's edge. And Scorpion's spear shows 8 of MK's 35 poses (his art memory is full).
- **Fewer of MK's poses:** a knockdown shows about 5 of MK's (Scorpion 4; Kano lies flat without MK's
  getting up), throws and projectile casts 6-11 of MK's ~25: the fighters' art memory is full.
- **Blast's Vendetta** can't be done on an MK fighter yet: switched off. Where the tests land it (on
  Kano and Liu Kang) it now plays as on an EC fighter; it isn't tested on every MK fighter.
- **Sonya's interrupted square wave** tumbles on an airborne hit, as in MK, but with Eternal
  Champions' knockdown poses and trajectory.
- **Raiden's fatality** uses an approximate blue tint and Eternal Champions' blood droplets rather
  than MK's exact explosion spray; his art shares six near-identical poses to fit player 2's memory.
- **A menu screen left alone** (Controller Setup, Access Info: the ones that don't hand over to the
  intro video after 5 minutes) for about 6 minutes plays on from the menu music into MK's fight cues
  (FINISH HIM's music, the announcer). The title and main menu don't.
- **Tested in emulators only** (Genesis Plus GX; PicoDrive and ares for the 32X build), not yet on a
  real Sega CD or 32X.

## Tools

The ones you run are in `tools/` (`checkinputs.py`, `prepare.py`, `build.py`, `play.py`) and
`tools/checks/allchecks.py`; [docs/tools.md](docs/tools.md) says what every tool is for.

## Contributing

Fixes and reports are welcome. A change goes into `main` only when every check passes and a fresh
clone still builds the identical disc: [docs/maintaining.md](docs/maintaining.md) has the rules and
the commands.

## Licence

MIT ([LICENSE](LICENSE)): the tools and data in this repository. The games they read are not included
and stay their owners'. A fan project, not affiliated with or endorsed by the owners of *Mortal Kombat*
or *Eternal Champions*; their names and trademarks belong to them.
