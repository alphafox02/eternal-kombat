# How Eternal Kombat works

A map for someone new to the code. Each part points to where the details live. Findings, with
the evidence for each, are in [notes/2026-11.md](notes/2026-11.md).

## The pipeline

1. **`tools/prepare.py`** reads your discs and writes `extracted/`:
   - EC's and MK's files;
   - every MK pose, drawn from `data/mk_recipes/` (which MK frame goes where);
   - the poses' anchors, timelines and palettes, from `data/mk_meta/`;
   - the fatality and Pit sounds, rendered from MK's samples and CD tracks by `data/mk_sound/`.

   No emulator is needed.
2. **`tools/build.py`** copies your EC disc and applies `tools/lib/patches.py`'s patches in order:
   - files inside the ISO9660 data track are rewritten in place, and sector checksums
     recomputed;
   - MK music is appended to EC's last CD track; one other track is swapped for MK's Pit music, and MK's
     other stage tracks are added as tracks 20-22.

   The same inputs give the same disc, byte for byte.
3. **`tools/checks/allchecks.py`** plays the built disc in Genesis Plus GX (`tools/lib/scd.py`,
   a small libretro front end) and checks fights, finishers, sounds and the Contest. It
   reads the game's memory and screen.

## Eternal Champions' engine

- **The fight runs on the Sega CD's sub CPU,** out of its 512 KB PRG RAM:
  - `SUB.BIN` (resident from `$6000`) holds the engine services, name tables and the sound
    calls;
  - `PLYR.CO` (`$14000`-`$1AE72`) is the code every fighter shares: hits, damage, throws,
    blocking, the attack records;
  - each player's fighter module (`XXX.CO`, its CPU brain `XXX.AI`, its finishers `XXX.OC`)
    loads into one of two slots (`$1B000`, `$21800`).

  The main CPU drives the display; a fighter's art is his `.PL` sprite sheets.
- **Other files:**
  - stages are `.BG`/`.BGI` (their code, including stage finishers);
  - the select, versus and stage tables are in `GAME.CO`;
  - the statistics screen is `STATS.CO`.
- **Sound:**
  - `FIGHT.SND` (hits, swings and falls, shared) loads at sound RAM 0 and must end below
    `$3F00`, where each player's own bank (`XXX.SND`) starts;
  - music is CD audio, started by time or track through the BIOS.

## MK fighters in EC slots

Each MK fighter takes a hidden EC fighter's slot and files. EC's code and data address
fighters by slot:

| MK fighter | host slot (files) | id |
|---|---|---|
| Scorpion | the Senator (SEN) | 22 |
| Raiden | Chin Wo (CHW) | 19 |
| Johnny Cage | an animal (MON) | 18 |
| Sub-Zero | an animal (DOG) | 20 |
| Liu Kang | an animal (CHI) | 12 |
| Kano | an animal (SNA) | 13 |
| Sonya | an animal (OWL) | 17 |
| Shang Tsung (Contest boss) | the Eternal Champion (CHA) | 11 |
| Reptile (hidden) | Eternal's second form (ECX) | 26 |

- **Behaviour:** a host's module is Blade's code (his moves, hit data and throws are the
  closest to MK's), with an **extension block** appended at `EXT_OFF`. The block holds the MK
  behaviour EC lacks: MK's inputs and specials, the walk, jumps, knockdowns, FINISH HIM and the
  fatalities.
- **Where that code comes from:**
  - `tools/lib/mkinputs.py` writes it in 68000 assembly (its own small `Asm`);
  - `tools/lib/patches.py` places it;
  - hooks in `PLYR.CO` jump to it through stubs in the gap after `PLYR.CO` (up to `$1B000`,
    nearly full).
- **Art:**
  - MK's poses replace Blade's frames in the host's `.PL` sheets: `tools/lib/scorpion_full.py`
    picks the poses, `tools/lib/scorpion_map.py` maps EC frames to MK actions;
  - MK's animation for basic attacks comes from `tools/lib/mkscripts.py`.
- **Sound:** MK's voices go in the host's `.SND`, MK's hits, falls, landing and grunt in
  `FIGHT.SND`.
- **Per fighter:** `patches.Spec` lists what differs: name, host, palettes, sounds,
  specials.

## Where to start

| I want to ... | look at |
|---|---|
| build or play | the [README](../README.md) |
| know what a tool does | [tools.md](tools.md) |
| change an MK move or fix a bug | `tools/lib/mkinputs.py`, the matching check in `tools/checks/`, [mk_fidelity_spec.md](mk_fidelity_spec.md) |
| change an MK pose | `tools/lib/scorpion_full.py`, `tools/lib/scorpion_map.py` |
| add a patch | `tools/lib/patches.py` (order matters; `fatality-music` must stay last) |
| understand the recipes and `data/` | [maintaining.md](maintaining.md), in depth [research/reproducibility_2026-11.md](research/reproducibility_2026-11.md) |
| release | the gate in [maintaining.md](maintaining.md) |
