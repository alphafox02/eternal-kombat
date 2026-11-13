# Eternal Kombat

A Sega CD crossover: Mortal Kombat's fighters and stages brought into the
engine of *Eternal Champions: Challenge from the Dark Side*, with their own
moves, and MK stages rebuilt so they get EC-style stage finishers.

**Status:** four MK fighters in their own slots, alongside every EC fighter:
**Scorpion, Raiden, Johnny Cage, Sub-Zero.**

- **All four** have MK's art and palettes, MK's attack animations at MK's timing (standing, close and crouch attacks), names, portraits and select-screen icons.
- **Scorpion** is the complete one:
  - spear with "GET OVER HERE!";
  - MK's teleport punch;
  - FINISH HIM / FINISH HER with MK's music;
  - his fatality;
  - MK's walk, dazed sway, upright jump attacks and sweep;
  - blood;
  - EC's Chicago Overkill working on him.
- **The other three** still use Blade's moves for their specials (lightning, green bolt, ice blast; the torpedo and shadow kick from Blade's dash). Johnny has MK's split punch.

Work in progress and findings: [docs/re_notes.md](docs/re_notes.md).

## Why EC hosts

EC CD's engine is modular. Every fighter, stage and stage finisher is a
separate 68000 code module on the disc (`BLA.CO`, `BLA.OC`, `BLAD.AI`, ...)
that calls into a fixed table of engine services in `SUB.BIN`. Adding a
fighter means adding modules, not rewriting the game. MK's fighters are pure
data driven by code shared across the whole game, so the reverse direction
is much harder. Details: [docs/re_notes.md](docs/re_notes.md).

## This repository contains no game data

You supply your own rips. Put them anywhere under `roms/`, in any layout
(one bin per track or a single bin, any file names):

```
roms/   Eternal Champions: Challenge from the Dark Side (USA)   required: the engine
        Mortal Kombat (USA) (Sega CD)                            required: the content
        Mortal Kombat Kanzenban (Japan)                          optional
bios/   bios_CD_U.bin  (Sega CD Model 1 v1.10)                   only to run the emulator
```

Discs are recognised by the SHA-1 of their data track, so file names don't
matter:

```
python3 tools/checkinputs.py
```

## Building

```
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python3 tools/checkinputs.py
python3 tools/build.py            # -> build/Eternal Kombat/Eternal Kombat.cue
```

The build copies your EC disc and applies `tools/patches.py` in order,
patching files inside the ISO9660 data track in place and recomputing each
touched sector's EDC/ECC. Audio tracks are hard-linked. The same inputs give
a byte-identical disc. `--list` shows the patches, `--skip NAME` leaves one out.

## Playing and testing

`pip install -r requirements-dev.txt` adds the emulator core and disassembler.

```
python3 tools/play.py window --state fight     # play, with sound
python3 tools/play.py test                     # build + run tests/scenarios/*.txt
python3 tools/play.py run "load fight; mash 600; shot x"
```

`test` runs every scenario headless at about 25x real time and writes
`runs/<time>/report.md` with a contact sheet per scenario, so it can run
unattended. Savestates in `states/` are shared between the window (F2 / F4)
and scenarios (`save` / `load`).

Save states only once the game is idle. A state saved while the game is
still reading the CD restores into a hung drive.

## Tools

| | |
|---|---|
| `checkinputs.py` | finds and verifies your discs and BIOS |
| `build.py`, `patches.py` | builds the disc |
| `disc.py` | cue/bin, raw sectors, EDC/ECC, ISO9660 read and in-place patching |
| `extract.py` | unpacks every disc's files to `extracted/` for study |
| `ecdis.py` | disassembler for EC modules; labels engine calls and follows spawned tasks |
| `scd.py` | minimal libretro front-end for Genesis Plus GX |
| `play.py` | window, scenarios, unattended test runs |
