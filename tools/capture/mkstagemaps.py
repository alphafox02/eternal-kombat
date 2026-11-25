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
ANIM_FRAMES = 1500            # frames of MK's animation recorded (and looped)


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


def record_anim(c, battle, base, tiles, bg, planes):
    """What MK animates on the stage, as it plays it for ANIM_FRAMES (both fighters standing):
    elements - each a cluster of plane cells whose name-table words change (the Gates' torches, the
    Lair's eyes), or the tiles whose pixels change (the Courtyard's monks) - with their distinct
    states and MK's own sequence of them (runs: state, frames), looped by our stage code. Every
    state's art is on the disc: a name-table word names a BACKGD tile (base-relative) or one of the
    BACKGD's sixth block's tiles (extra: VRAM tile -> its index there); a tile's pixels are found in
    the BACKGD file (offset)."""
    import scipy.ndimage as ndi
    off = [int.from_bytes(bg[i:i + 4], 'big') for i in range(0, 24, 4)]
    six = rnc1(bg, off[5]) if bg[off[5]:off[5] + 3] == b'RNC' else b''
    extra_src = tiles_of(six) if six and len(six) % 32 == 0 else np.zeros((0, 8, 8), np.uint8)   # (tiles: the Lair's eyes)
    c.load_state(os.path.join(ROOT, 'build', 'states', f'mk_battle_{battle}.state'))
    c.run(2)
    used = sorted({int(w) & 0x7FF for p in 'AB' for w in np.array(planes[p]).ravel() if w})
    nts, pix = [], []
    for _ in range(ANIM_FRAMES):
        c.buttons = [set(), set()]
        c.run(1)
        v = VDPState(c.snapshot())
        t = {p: name_table(v, p) for p in 'AB'}
        t['B'][:HUD_ROWS] = 0
        nts.append(t)
        pix.append([v.vram[i * 32:i * 32 + 32] for i in used])
    elements, extra = [], {}

    def word_src(w):
        i = w & 0x7FF
        if base <= i < base + len(tiles):
            return w
        k = next((k for k in range(len(extra_src)) if np.array_equal(VDPState(c.snapshot()).tile(i), extra_src[k])), None)
        assert k is not None, f'cell tile {i}: neither the BACKGD\'s tiles nor its sixth block'
        extra[str(i)] = k
        return w

    def runs(seq):
        states, out = [], []
        for s_ in seq:
            if s_ not in states:
                states.append(s_)
            k = states.index(s_)
            if out and out[-1][0] == k:
                out[-1][1] += 1
            else:
                out.append([k, 1])
        return states, out
    for p in 'AB':
        stack = np.array([t[p] for t in nts])
        moving = np.any(stack != stack[0], axis=0)
        lab, nlab = ndi.label(moving, structure=np.ones((3, 3)))
        for k in range(1, nlab + 1):
            cells = [(int(y), int(x)) for y, x in zip(*np.nonzero(lab == k))]
            seq = [tuple(int(stack[f][y, x]) for y, x in cells) for f in range(len(stack))]
            states, rs = runs(seq)
            for st in states:
                for w in st:
                    word_src(w)
            elements.append(dict(plane=p, cells=cells, states=[list(s_) for s_ in states], runs=rs))
    # tiles whose pixels change, as one element (each tile's pixels found in the BACKGD file)
    stack = np.array([[np.frombuffer(b, np.uint8) for b in f] for f in pix])
    moving = [j for j in range(len(used)) if np.any(stack[:, j] != stack[0, j])]
    if moving:
        seq = [tuple(bytes(stack[f, j]) for j in moving) for f in range(len(stack))]
        states, rs = runs(seq)
        found = []
        for st in states:
            offs = []
            for b in st:
                o = bg.find(b)
                assert o >= 0, 'an animated tile\'s pixels aren\'t in the BACKGD file'
                offs.append(o)
            found.append(offs)
        elements.append(dict(tiles=[used[j] - base for j in moving], states=found, runs=rs))
    return dict(frames=ANIM_FRAMES, elements=elements, extra=extra)


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
        anim = record_anim(c, battle, base, tiles, bg, planes)
        cam = mkstagecamera.measure(c, battle)
        animated = sorted({t for e in anim['elements'] if 'tiles' in e for t in e['tiles']})   # (base-relative)
        json.dump(dict(backgd=n, battle=battle, tile_base=base, hud_rows=HUD_ROWS,
                       animated=animated, planes=planes, anim=anim, camera=cam),
                  open(os.path.join(out_dir, f'{key}.json'), 'w'), separators=(',', ':'))
        print(f'{key}: BACKGD{n}.BIN, tile base {base}, {len(anim["elements"])} animated elements, camera {cam["camera"]}, '
              f'cells A {int((np.array(planes["A"]) > 0).sum())} B {int((np.array(planes["B"]) > 0).sum())}', flush=True)


if __name__ == '__main__':
    main()
