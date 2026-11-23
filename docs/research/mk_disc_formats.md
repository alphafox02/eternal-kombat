# MK CD's data, read straight from the disc

`prepare.py` builds everything Eternal Kombat takes from Mortal Kombat CD by decoding MK's own files
(`extracted/mk_us/`, copied from your disc): no emulator, no BIOS. This is how each format was worked
out. The sounds have their own note: [mk_sound_research.md](mk_sound_research.md).

## Fighter art: OBJ and SCH (`tools/lib/mksch.py`)

Frame IDs in MK's animation lists map to OBJ frame indices by subtracting `$10`.

- Scorpion's `.SCH` is 194,944 bytes, exactly 3,046 blocks of 64 bytes.
- In `SCORPION.OBJ`, the first three longwords are offsets `$1E`, `$29D2`, `$2B64`; the word at `$0C`
  is 201. The word table at `$29D2` begins `$0006, $0012, $0054, ...`. Adding `$1E` to `$12` reaches
  `$30`, a descriptor whose dimensions are 4 by 7 and whose 28 following words are a grid of cell IDs
  1-23 with five zero entries. Forcing frame 1 in MK produces 23 16x16 sprites on a matching 4x7 grid.
- The first SCH block is empty; each subsequent 64-byte block is a 16x16 cell. Its byte indices select
  two bytes from the two 256-byte lookup tables for that group of 32 cells. The dictionary base is the
  longword at OBJ `$1A`; bank N starts at base + N x 512. Four indices produce four bytes of one row,
  then four bytes of the next, in Genesis tile order.
- `MAIN.PRG` offsets `$456` and `$4C8` hold a graphics expansion using two 256-byte lookup tables and
  an indexed stream (four indices, two longwords, one through each table, to the VDP). `RJC.PRG`
  runtime `$3753C` is an RNC method-1 unpacker (the `RNC\x01` signature), not the SCH codec.

Validated against the emulator: frames `$12`, `$13`, `$17`, `$20` and `$40` of all seven playable
fighters have the same 16x16 cells (Raiden's emulator images also hold four effect sprites); every
frame descriptor of the seven, Goro, EMP and BONES decodes. `FighterArt.frame(index)` gives the grid
as palette indices, without origins, clipping, flips or effects: the poses themselves are drawn from
recipes (`data/mk_recipes/`: which frame, mirrored or not, where), which add those
([reproducibility_2026-11.md](reproducibility_2026-11.md)).

```
python3 -P tools/lib/mksch.py extracted/mk_us/SCORPION.OBJ 5 --palette extracted/mk_moves/idle/cram.json --out build/tmp/scorpion.png
```

## Palettes, portraits, the Pit, Sub-Zero's spine

- **Fight palettes** (`mkpalettes.py`): `PAC.PRG` `$1C030`-`$1C10F`, seven 32-byte palettes, 16
  big-endian Genesis `$0BGR` words each; entry 0 is `$0E0E` as a placeholder (0 in CRAM).
- **Select portraits** (`mkportraits_disc.py`): `RJC.PRG` `$2474E`, an RNC method-1 block of 4bpp
  tiles; the select screen's palette words at `$7842`. The tool maps tiles onto seven 42x50 crops
  with the emulator's colour conversion (numbers only: tile indices and crop offsets).
- **The Pit** (`mkpit_disc.py`, `mkpitbottom.py`): `BACKGD4.BIN` has six sections - 0 compressed
  tiles, 1 and 2 compressed foreground and background maps, 5 two palettes. The fight planes, the
  moon and the pit's bottom (its second map copy in PAC) are rebuilt from them.
- **Sub-Zero's spine** (`mkspine_disc.py`): `PAC.PRG` `$1FBE2`-`$1FE61`, six 4bpp sprite blocks, four
  with horizontal mirrors: the ten pieces of his fatality, in order.

Each decoder has `--check DIR`: it regenerates its output and compares it byte for byte with a
reference `extracted/` (it never writes there). When these decoders replaced the emulator captures,
a build from them matched the capture-based build in all 20 files.
