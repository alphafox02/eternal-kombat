#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""MK's Goro's Lair (the stage of MK's Shang Tsung fight), from the MK disc.

BACKGD6.BIN -> extracted/mk_stages/lair/plane_a.png, plane_b.png, cram.json,
laid out as MK's VDP planes in a fight (the same layout tools/lib/mkstage.py
captures from a state, which --check compares against).

BACKGD6.BIN: six longs, then RNC blocks: +0 the tiles (571), +4 plane A's
map (128 x 32 cells: the walls, the chained skeleton, the floor), +8 plane
B's (128 x 25: the arches behind; MK puts it 3 rows down), +$C / +$10
palette lines 3 and 2 (plane A uses line 3, plane B line 2), +$14 the eyes'
tiles (5 frames: open to shut). MK's code blinks 8 pairs of eyes in the dark
arches (EYES, measured: tools/lib/vdp.py on plane B over 20 s); here they are open.
Lines 0 and 1 are PAC.PRG's, as for the Pit.

    mklair_disc.py --out extracted        (tools/prepare.py runs this)
    mklair_disc.py --check DIR            DIR/mk_stages/lair from tools/lib/mkstage.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # (tools run with python -P)
import argparse
import io
import json
from pathlib import Path
import numpy as np
from PIL import Image
from mkpitbottom import rnc1
from mkpit_disc import words, cram, png

ROOT = Path(__file__).resolve().parent.parent.parent
B_ROW = 3                         # plane B's map starts this many cells down
EYES = [(20, 26), (20, 74), (21, 20), (21, 28), (21, 39), (21, 46), (21, 64), (21, 70)]   # (row, col): a pair at col, col+1


def tiles_of(raw):
    raw = np.frombuffer(raw, np.uint8).reshape(-1, 8, 4)
    t = np.empty((len(raw), 8, 8), np.uint8)
    t[:, :, 0::2], t[:, :, 1::2] = raw >> 4, raw & 15
    return t


def build(bg, pac):
    off = [int.from_bytes(bg[i:i + 4], 'big') for i in range(0, 24, 4)]
    tiles = tiles_of(rnc1(bg, off[0]))
    eyes = tiles_of(rnc1(bg, off[5]))
    a = np.frombuffer(rnc1(bg, off[1]), '>u2').reshape(32, 128)
    b = np.frombuffer(rnc1(bg, off[2]), '>u2').reshape(25, 128)
    colors = (cram(words(pac[0x1c0d0:0x1c0f0])) + cram(words(pac[0x1c1f0:0x1c210]))
              + cram(words(bg[off[4]:off[4] + 32])) + cram(words(bg[off[3]:off[3] + 32])))
    for i in (0, 16, 32, 48): colors[i] = 0
    colors[41] = 33  # palette line 2 entry 9, set by the fight state
    palette = np.array([((v & 7) * 36, ((v >> 3) & 7) * 36, ((v >> 6) & 7) * 36) for v in colors], np.uint8)
    result = [np.zeros((256, 1024, 4), np.uint8), np.zeros((256, 1024, 4), np.uint8)]

    def put(dest, y, x, p, line):
        dst = dest[y * 8:y * 8 + 8, x * 8:x * 8 + 8]
        dst[:, :, :3] = palette[line * 16 + p]
        dst[:, :, 3] = (p > 0).astype(np.uint8) * 255

    def tile(dest, y, x, value, line):
        value = int(value)
        p = tiles[value & 0x7ff]
        if value & 0x800: p = p[:, ::-1]
        if value & 0x1000: p = p[::-1]
        put(dest, y, x, p, line)

    for y, row in enumerate(a):
        for x, v in enumerate(row): tile(result[0], y, x, v, 3)
    for y, row in enumerate(b):
        for x, v in enumerate(row): tile(result[1], y + B_ROW, x, v, 2)
    for y, x in EYES:
        put(result[1], y, x, eyes[0], 2)
        put(result[1], y, x + 1, eyes[0], 2)
    return {'plane_a.png': png(result[0]), 'plane_b.png': png(result[1]),
            'cram.json': json.dumps(colors).encode()}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--disc', type=Path, default=ROOT / 'extracted' / 'mk_us')
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', type=Path, metavar='REFERENCE_EXTRACTED')
    group.add_argument('--out', type=Path, metavar='EXTRACTED')
    a = ap.parse_args()
    results = build((a.disc / 'BACKGD6.BIN').read_bytes(), (a.disc / 'PAC.PRG').read_bytes())
    bad = 0
    for name, data in results.items():
        path = (a.check or a.out) / 'mk_stages' / 'lair' / name
        if a.check:
            ref = path.read_bytes()
            if name.endswith('.png'):
                # plane B: MK's HUD is in its top 5 rows, the rest of its rows
                # past the map hold other VRAM; the eyes blink (any frame)
                e = np.asarray(Image.open(io.BytesIO(ref)).convert('RGBA')).copy()
                g = np.asarray(Image.open(io.BytesIO(data)).convert('RGBA')).copy()
                if name == 'plane_b.png':
                    for y, x in EYES:
                        e[y * 8:y * 8 + 8, x * 8:x * 8 + 16] = g[y * 8:y * 8 + 8, x * 8:x * 8 + 16]
                    e, g = e[40:(25 + B_ROW) * 8], g[40:(25 + B_ROW) * 8]
                equal = e.shape == g.shape and np.array_equal(e, g)
            else:
                ref = json.loads(ref)
                ref[0] = ref[16] = ref[32] = ref[48] = 0          # (backdrops: the state's)
                equal = ref == json.loads(data)
            print(f'{name}: {"identical" if equal else "DIFFERENT"}')
            bad += not equal
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            print(path)
    if bad: raise SystemExit(1)


if __name__ == '__main__': main()
