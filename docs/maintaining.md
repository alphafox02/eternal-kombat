# Maintaining Eternal Kombat

How this repository stays something anyone can rebuild from their own discs. (History: the reproducible-captures
work is in [research/reproducibility_2026-11.md](research/reproducibility_2026-11.md); the 2026-11-22 restructure
in [notes/2026-11.md](notes/2026-11.md).)

## Layout

| | in git | what it is |
|---|---|---|
| `tools/` | yes | the commands you run: `checkinputs.py`, `prepare.py`, `build.py`, `play.py` |
| `tools/lib/` | yes | the library: the patches, the disc and emulator code, the MK extractors |
| `tools/checks/` | yes | the test suite (`allchecks.py` runs it all) and `play.py test`'s scenarios |
| `tools/capture/` | yes | how the MK data was measured (kept to re-measure, not run by the build) |
| `tools/dev/` | yes | developer tools: `verify_fresh.py`, `clean.py`, disassemblers, audits |
| `tools/x32/` | yes | the 32X support's steps (run by `build.py --32x`) |
| `data/` | yes | the numbers that rebuild MK's art and sounds from your MK disc (no art, no sound) |
| `docs/` | yes | the guides; `docs/research/` finished investigations; `docs/notes/` the lab notebook |
| `roms/`, `bios/` | never | your own discs and the Sega CD BIOS |
| `extracted/` | never | made by `prepare.py` from your discs |
| `build/` | never | the disc, and the emulator's output: `build/states/`, `shots/`, `runs/`, `saves/` |

Every tool has one line in [tools.md](tools.md) (`tools/checks/toolsdoccheck.py` keeps it so).

## Rules

1. **One repository**, branch `main`; work on short branches merged into `main`.
2. **Two discs in, the game out.** `prepare.py` then `build.py` need only the EC CD and MK CD images
   (and the Sega CD BIOS for the emulator checks). Nothing else on a machine may matter.
3. **The gate**, before anything reaches `main`:
   ```
   python3 tools/checks/allchecks.py       # the whole suite passes
   python3 tools/build.py --32x --out "build/Eternal Kombat 32X"
   python3 tools/checks/x32check.py --disc "build/Eternal Kombat 32X/Eternal Kombat.cue"   # the 32X build still works
   python3 tools/dev/verify_fresh.py       # a fresh clone, prepared and built from nothing, gives this exact disc
   ```
   `main` moves only after all of them pass ([release.md](release.md) adds the rest for a release).
4. **No game data in git:** discs, BIOS, extracted art and sound, save states, screenshots stay
   ignored (`.gitignore`). `data/` holds numbers only: recipes (which MK frame, where), timings,
   palette references; the pictures and sounds always come from the player's own disc.
5. **One home per tool**, one line in `docs/tools.md`; a tool nothing runs and no doc needs is
   deleted (git keeps it).
6. **MIT** (`LICENSE`); every Python file starts with its SPDX tag (`tools/checks/licensecheck.py`).
7. **No attribution trailers** (co-author lines and the like) in commits or files.

## How MK's data is reproducible

MK draws a fighter's frame by number, so every pose the build uses is a **recipe**
(`data/mk_recipes/`): which MK frame, mirrored or not, cut and placed where. `prepare.py` draws the
recipes from the player's MK disc (`tools/lib/mkfromrecipes.py`), with the anchors, timelines and
palette references in `data/mk_meta/`, and renders MK's sounds from `data/mk_sound/`. Two fresh
setups build the same disc byte for byte; `verify_fresh.py` proves it on every change.

## Memory limits the build asserts

A pose stays within 112 tiles (`scorpion_full.TILE_CAP`); a fighter's `.PL` and its tail within
`scorpion_full.MAX_PL`; each MK fighter's code block within its module slot (5600 bytes). A change
that doesn't fit is reworked, not forced.
