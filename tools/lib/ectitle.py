#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The title screen's logo says ETERNAL KOMBAT: EC's own lettering, rearranged.

EC's title (and main menu) is a still picture on plane B: 40 x 28 cells, tiles from
GAME.DAT ($3B0C-$A2AC = tiles 709-1537, plain 4-bit pixels; a few cells mirrored), palette lines 0-2
from GAME.CO $39A (loaded by the title's setup, GAME.CO $186; the menu after it keeps it, cycling only
line 2's colour 11). The red emblem and yin-yang's triangle are sprites on top.

This rewrites the pixels of the cells that change (76 tiles, none shared or mirrored):
  - CHAMPIONS and its TM are painted out with the water (or glow) beside each letter pixel;
  - KOMBAT is built from EC's own letters - K from "DARK", O and M from CHAMPIONS, T and A from
    ETERNAL, B from CHAMPIONS' P with its bowl repeated below - on ETERNAL's baseline, the K in the
    emblem's glow (where CHAMPIONS' H was);
  - the glow fades on into the K (its cells' palette line 0 stops in steps EC hid behind its C and H),
    with the K's strokes tinted dark red: 4 colours in palette line 2's slots 12-15, which nothing on the
    title or menu draws with.
Everything else (the emblem, CHALLENGE FROM THE DARK SIDE, PRESS START) stays. Same result every build
(a fixed seed).

The plane's map (which tile and palette line each cell uses) is in no file as plain words; it is kept
as numbers in data/ec_title/plane_b.json, measured once from the title screen:

    ectitle.py --measure build/states/menu.state     # (re)writes data/ec_title/plane_b.json
    ectitle.py --preview out.png                     # EC's title and ours side by side (from extracted/)
"""
import argparse, json, os, random, sys
import numpy as np
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
MAP_JSON = os.path.join(ROOT, 'data', 'ec_title', 'plane_b.json')

TILE_RUNS = ((709, 1537, 0x3B0C),)                            # (first, last, GAME.DAT offset)
PALETTE = 0x39A                                                  # GAME.CO: lines 0-3, 16 words each
NEW = {12: (216, 108, 108), 13: (144, 108, 108), 14: (36, 0, 0), 15: (108, 36, 36)}   # line 2's slots
NEW_OLD = bytes.fromhex('02a008ca02ce0ec6')                      # EC's (unused on this screen)
W, H = 320, 224

LETTER = {(0, 0, 0), (36, 36, 72), (36, 0, 0), (72, 36, 72), (72, 72, 108), (108, 72, 108),
          (72, 72, 36), (180, 144, 36), (108, 72, 0)}           # EC's lettering, not water or glow
ERASE = (34, 82, 180, 320)                                       # CHAMPIONS and TM: y0, y1, x0, x1
TM = (36, 57, 294, 320)
GLYPHS = {'K': (214, 228, 86, 114), 'O': (261, 273, 42, 71), 'M': (226, 243, 43, 70),
          'P': (244, 253, 43, 70), 'A': (89, 99, 43, 69), 'T': (39, 51, 42, 69)}   # x0, x1, y0, y1 (inclusive)
WORD, X, BASE = 'KOMBAT', 194, 70
FADE = 24
DARK = ((36, 36, 72), (0, 0, 0), (72, 36, 72))     # a letter's strokes
GLOW_LETTER = (0, 6, 8, 11, 1)       # line 0 colours a letter pixel in the glow may take


def tile_offset(t):
    for first, last, at in TILE_RUNS:
        if first <= t <= last:
            return at + (t - first) * 32
    raise ValueError(f'tile {t} is not one of the title picture\'s')


def rgb(word):
    return ((word >> 1) & 7) * 36, ((word >> 5) & 7) * 36, ((word >> 9) & 7) * 36


def palettes(co):
    return [[rgb(int.from_bytes(co[PALETTE + 32 * l + 2 * i:PALETTE + 32 * l + 2 * i + 2], 'big'))
             for i in range(16)] for l in range(4)]


def load_map():
    return json.load(open(MAP_JSON))['cells']


def picture(dat, cells):
    """Colour indices and palette lines of the whole plane (H x W)."""
    idx = np.zeros((H, W), np.uint8)
    line = np.zeros((H, W), np.uint8)
    for cy in range(H // 8):
        for cx in range(W // 8):
            e = cells[cy][cx]
            o = tile_offset(e & 0x7FF)
            d = np.frombuffer(dat[o:o + 32], np.uint8).reshape(8, 4)
            t = np.empty((8, 8), np.uint8)
            t[:, 0::2], t[:, 1::2] = d >> 4, d & 15
            if e & 0x800:
                t = t[:, ::-1]
            if e & 0x1000:
                t = t[::-1]
            idx[cy * 8:cy * 8 + 8, cx * 8:cx * 8 + 8] = t
            line[cy * 8:cy * 8 + 8, cx * 8:cx * 8 + 8] = (e >> 13) & 3
    return idx, line


def colours(idx, line, pals):
    lut = np.array(pals, np.int32)                    # (4, 16, 3)
    return lut[line, idx]


def nearest(pal, c, allowed=range(16)):
    return min(allowed, key=lambda i: sum((a - b) ** 2 for a, b in zip(pal[i], c)))


def kombat(idx, line, pals):
    """The new picture's colour indices (lines unchanged), from EC's, and the palettes with NEW in
    line 2."""
    pals = [list(p) for p in pals]
    pals[2] = [NEW.get(i, c) for i, c in enumerate(pals[2])]
    col = colours(idx, line, pals)
    is_letter = np.zeros((H, W), bool)
    for c in LETTER:
        is_letter |= np.all(col == c, axis=2)

    # 1. CHAMPIONS and its TM out: each letter pixel from the picture beside it (same palette line)
    y0, y1, x0, x1 = ERASE
    m = np.zeros((H, W), bool)
    m[y0:y1, x0:x1] = is_letter[y0:y1, x0:x1]
    lab, n = ndimage.label(m)
    sizes = ndimage.sum(m, lab, range(1, n + 1))
    big = np.isin(lab, [i + 1 for i, s in enumerate(sizes) if s >= 6])          # (not the water's dark specks)
    tm = np.zeros_like(m)
    tm[TM[0]:TM[1], TM[2]:TM[3]] = m[TM[0]:TM[1], TM[2]:TM[3]]
    m = ndimage.binary_dilation(big | tm, iterations=1)
    m[:y0 - 2] = False
    out = idx.copy()
    rnd = random.Random(1)
    for y, x in zip(*np.nonzero(m)):
        cands, r = [], 1
        while len(cands) < 6 and r < 60:
            for dy in (-1, 0, 1):
                for dx in (-r, r):
                    yy, xx = y + dy, x + dx
                    if 0 <= xx < W and not m[yy, xx] and line[yy, xx] == line[y, x]:
                        cands.append(idx[yy, xx])
            r += 1
        out[y, x] = cands[rnd.randrange(len(cands))]

    # 2. KOMBAT from EC's letters
    def glyph(k):
        gx0, gx1, gy0, gy1 = GLYPHS[k]
        lm = is_letter[gy0:gy1 + 1, gx0:gx1 + 1]
        lab, n = ndimage.label(lm, structure=np.ones((3, 3)))
        sizes = ndimage.sum(lm, lab, range(1, n + 1))
        keep = np.isin(lab, [i + 1 for i, s in enumerate(sizes) if s >= 12])     # (not a neighbour's bits)
        return col[gy0:gy1 + 1, gx0:gx1 + 1].copy(), ndimage.binary_dilation(keep, iterations=1)

    def bee():
        g, gm = glyph('P')
        g[15:27], gm[15:27] = g[2:14], gm[2:14]        # P's bowl again below it
        return g, gm

    placed = np.zeros((H, W), bool)
    x = X
    for k in WORD:
        g, gm = bee() if k == 'B' else glyph(k)
        h, w = gm.shape
        for gy, gx in zip(*np.nonzero(gm)):
            Y, Xp = BASE - h + 1 + gy, x + gx
            c = tuple(int(v) for v in g[gy, gx])
            if line[Y, Xp] == 0:                        # the glow's cells: letter pixels in its reds
                if c in DARK:
                    out[Y, Xp] = nearest(pals[0], (36, 0, 0), GLOW_LETTER)     # (as the fade tints them)
                elif c in LETTER:
                    out[Y, Xp] = nearest(pals[0], c, GLOW_LETTER)
            else:
                out[Y, Xp] = nearest(pals[line[Y, Xp]], c)
            placed[Y, Xp] = c in LETTER
        x += w

    # 3. the glow on into the K
    def put(y, x, c):
        out[y, x] = nearest(pals[line[y, x]], c)
    rnd = random.Random(7)
    for y in range(24, 88):
        zs = [xx for xx in range(150, 240) if line[y, xx] == 0]
        if not zs:
            continue
        b0 = zs[-1] + 1
        for xx in range(b0, b0 + FADE):
            f = 1 - (xx - b0) / FADE
            c = pals[line[y, xx]][out[y, xx]]
            if placed[y, xx]:
                if c in DARK and rnd.random() < f:
                    put(y, xx, (36, 0, 0))
                elif c == (72, 72, 36) and rnd.random() < f:
                    put(y, xx, (108, 36, 36))
            elif rnd.random() < 0.6 * f:
                put(y, xx, (216, 108, 108) if rnd.random() < 0.45 * f + 0.2 else (144, 108, 108))
    return out, pals


def changed_tiles(dat, co, cells):
    """{GAME.DAT offset: (old 32 bytes, new 32 bytes)} and the new line-2 slot words."""
    idx, line = picture(dat, cells)
    out, _ = kombat(idx, line, palettes(co))
    use = {}
    for row in cells:
        for e in row:
            use[e & 0x7FF] = use.get(e & 0x7FF, 0) + 1
    tiles = {}
    for cy in range(H // 8):
        for cx in range(W // 8):
            a, b = idx[cy * 8:cy * 8 + 8, cx * 8:cx * 8 + 8], out[cy * 8:cy * 8 + 8, cx * 8:cx * 8 + 8]
            if (a == b).all():
                continue
            e = cells[cy][cx]
            assert not e & 0x1800 and use[e & 0x7FF] == 1, f'cell {cx},{cy}: tile shared or flipped'
            o = tile_offset(e & 0x7FF)
            tiles[o] = (dat[o:o + 32], bytes((b[:, 0::2] << 4 | b[:, 1::2]).ravel().tolist()))
    words = b''.join(((c[2] // 36) << 9 | (c[1] // 36) << 5 | (c[0] // 36) << 1).to_bytes(2, 'big')
                     for c in NEW.values())
    return tiles, words


def apply(ec):
    dat, co = ec.read_file('GAME.DAT'), ec.read_file('GAME.CO')
    tiles, words = changed_tiles(dat, co, load_map())
    for o, (old, new) in sorted(tiles.items()):
        ec.patch_file('GAME.DAT', o, new, expect=old)
    ec.patch_file('GAME.CO', PALETTE + 64 + 24, words, expect=NEW_OLD)
    return len(tiles)


def render(dat, co, cells, ours=True):
    idx, line = picture(dat, cells)
    pals = palettes(co)
    if ours:
        idx, pals = kombat(idx, line, pals)
    return colours(idx, line, pals).astype(np.uint8)


def measure(state):
    sys.path.insert(0, HERE)
    import vdp
    v = vdp.VDPState(open(state, 'rb').read())
    base, (w, _) = (v.regs[4] & 7) << 13, v.plane_size()
    cells = [[int.from_bytes(v.vram[base + 2 * (cy * w + cx):base + 2 * (cy * w + cx) + 2], 'big')
              for cx in range(W // 8)] for cy in range(H // 8)]
    os.makedirs(os.path.dirname(MAP_JSON), exist_ok=True)
    with open(MAP_JSON, 'w') as f:
        f.write('{"about": "EC title screen, plane B: each cell\'s name-table word (tile | palette line << 13), '
                'measured by tools/lib/ectitle.py --measure",\n "cells": [\n')
        f.write(',\n'.join('  ' + json.dumps(r) for r in cells) + '\n ]}\n')
    print('wrote', MAP_JSON)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--measure', metavar='STATE')
    ap.add_argument('--preview', metavar='PNG')
    ap.add_argument('--src', default=os.path.join(ROOT, 'extracted', 'ec_us'))
    a = ap.parse_args()
    if a.measure:
        measure(a.measure)
    if a.preview:
        from PIL import Image
        dat = open(os.path.join(a.src, 'GAME.DAT'), 'rb').read()
        co = open(os.path.join(a.src, 'GAME.CO'), 'rb').read()
        cells = load_map()
        both = np.concatenate([render(dat, co, cells, False), np.zeros((H, 4, 3), np.uint8),
                               render(dat, co, cells)], axis=1)
        Image.fromarray(both).resize((both.shape[1] * 3, H * 3), Image.NEAREST).save(a.preview)
        print('wrote', a.preview)


if __name__ == '__main__':
    main()
