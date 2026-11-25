#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""MK CD's stages as numbers: where each stage tile sits on the planes, and how they scroll.

MK CD builds a stage's planes from its BACKGDn.BIN (tiles, maps, two palette lines) in ways
its maps alone don't say (the floors are laid in code, maps go in at offsets). The planes'
name tables at a fight's start - 128 x 32 words each: tile, palette line, flips, priority -
are measured once from the battle states (tools/capture/mkstagestates.py) and kept here as
numbers, with the tile number BACKGDn's first tile has in VRAM (found by matching pixels) and
MK's camera (tools/capture/mkstagecamera.py). The art itself (tiles, colours) is read from
the player's MK disc by tools/lib/mkstage_disc.py.

MK's HUD (plane B's top 3 rows) and cells that aren't the stage's tiles are 0.

    mkstagemaps.py [--stages courtyard,gates,shrine,throne]   -> data/mk_stages/<stage>.json
"""
import argparse, json, os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scd
from inputs import ROOT, require
from vdp import VDPState
from mkpitbottom import rnc1
from mklair_disc import tiles_of
import mkstagecamera

# key: (MK's 2-player battle it is first fought in, its BACKGD file)
STAGES = {'courtyard': (1, 1), 'gates': (2, 2), 'shrine': (3, 3), 'throne': (5, 5), 'lair': (6, 6)}
HUD_ROWS = 3
ANIM_WATCH = 120              # frames watched for tiles MK animates


def name_table(v, plane):
    w, h = v.plane_size()
    base = ((v.regs[2] & 0x38) << 10) if plane == 'A' else ((v.regs[4] & 7) << 13)
    return np.frombuffer(v.vram[base:base + w * h * 2], '>u2').reshape(h, w).astype(int)


def tile_base(v, tiles, tables):
    """The VRAM tile number of BACKGD's tile 0: the one that makes the most used cells' pixels match."""
    used = sorted({int(i) for t in tables for i in (t & 0x7FF).ravel() if i})
    best = (-1, None)
    for base in range(0, 2048 - len(tiles) + 1):
        ok = sum(1 for i in used[::7] if base <= i < base + len(tiles) and np.array_equal(v.tile(i), tiles[i - base]))
        if ok > best[0]:
            best = (ok, base)
    return best[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stages', default=','.join(STAGES))
    a = ap.parse_args()
    c = scd.Core(saves=os.path.join(ROOT, 'build', 'shots', 'capture-saves'))
    c.load(require('mk_us').cue)
    disc = os.path.join(ROOT, 'extracted', 'mk_us')                # (tools/prepare.py: the MK disc's files)
    out_dir = os.path.join(ROOT, 'data', 'mk_stages')
    os.makedirs(out_dir, exist_ok=True)
    for key in a.stages.split(','):
        battle, n = STAGES[key]
        bg = open(os.path.join(disc, f'BACKGD{n}.BIN'), 'rb').read()
        tiles = tiles_of(rnc1(bg, int.from_bytes(bg[0:4], 'big')))
        c.load_state(os.path.join(ROOT, 'build', 'states', f'mk_battle_{battle}.state'))
        c.run(2)
        v = VDPState(c.snapshot())
        tables = {p: name_table(v, p) for p in 'AB'}
        base = tile_base(v, tiles, tables.values())
        # tiles MK rewrites as it runs (the Courtyard's monks sway: 12 tiles, every 8 frames)
        seen = {i: v.tile(i).tobytes() for i in range(base, base + len(tiles))}
        animated = set()
        for _ in range(ANIM_WATCH):
            c.run(1)
            w = VDPState(c.snapshot())
            animated |= {i for i in seen if w.tile(i).tobytes() != seen[i]}
        planes = {}
        for p, t in tables.items():
            t = t.copy()
            idx = t & 0x7FF
            t[(idx < base) | (idx >= base + len(tiles))] = 0       # not the stage's (the HUD's font, ...)
            t[idx == 0] = 0
            if p == 'B':
                t[:HUD_ROWS] = 0
            # check: every kept cell's VRAM tile is BACKGD's
            for i in sorted({int(x) for x in (t & 0x7FF).ravel() if x} - animated):
                assert np.array_equal(v.tile(i), tiles[i - base]), (key, p, i)
            planes[p] = t.tolist()
        cam = mkstagecamera.measure(c, battle)
        json.dump(dict(backgd=n, battle=battle, tile_base=base, hud_rows=HUD_ROWS,
                       animated=sorted(i - base for i in animated), planes=planes, camera=cam),
                  open(os.path.join(out_dir, f'{key}.json'), 'w'), separators=(',', ':'))
        print(f'{key}: BACKGD{n}.BIN, tile base {base}, {len(animated)} animated tiles, camera {cam["camera"]}, '
              f'cells A {int((np.array(planes["A"]) > 0).sum())} B {int((np.array(planes["B"]) > 0).sum())}', flush=True)


if __name__ == '__main__':
    main()
