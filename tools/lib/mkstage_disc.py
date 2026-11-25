#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""MK's Courtyard, Palace Gates, Warrior Shrine and Throne Room planes, from the MK disc.

Each stage's tiles and two palette lines are its BACKGDn.BIN's (six longs, then RNC blocks:
+0 the tiles; +$C / +$10 palette lines 3 and 2, as mklair_disc.py); where each tile sits on
MK's two planes (and its palette line, flips, priority) is data/mk_stages/<stage>.json, measured
from MK at the fight's start (tools/capture/mkstagemaps.py). Lines 0 and 1 are PAC.PRG's, as for
the Pit.

    mkstage_disc.py --out extracted        (tools/prepare.py runs this)
        -> extracted/mk_stages/<stage>/plane_a.png, plane_b.png, cram.json, prio.json, anim.json
           (and the Lair's anim.json: its planes are mklair_disc.py's)
    mkstage_disc.py --check                (against MK's own planes, from the battle states)

prio.json: each plane's high-priority cells (row-major, 32 x 128 of 0/1): MK's fighters are
high-priority sprites, so these only say which plane is in front.
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
from mklair_disc import tiles_of

ROOT = Path(__file__).resolve().parent.parent.parent
STAGES = ('courtyard', 'gates', 'shrine', 'throne')


def build(key, disc):
    m = json.load(open(ROOT / 'data' / 'mk_stages' / f'{key}.json'))
    bg = (disc / f'BACKGD{m["backgd"]}.BIN').read_bytes()
    pac = (disc / 'PAC.PRG').read_bytes()
    off = [int.from_bytes(bg[i:i + 4], 'big') for i in range(0, 24, 4)]
    tiles = tiles_of(rnc1(bg, off[0]))
    colors = (cram(words(pac[0x1c0d0:0x1c0f0])) + cram(words(pac[0x1c1f0:0x1c210]))
              + cram(words(bg[off[4]:off[4] + 32])) + cram(words(bg[off[3]:off[3] + 32])))
    for i in (0, 16, 32, 48):
        colors[i] = 0
    colors[41] = 33  # palette line 2 entry 9, set by the fight (as the Lair's)
    palette = np.array([((v & 7) * 36, ((v >> 3) & 7) * 36, ((v >> 6) & 7) * 36) for v in colors], np.uint8)
    base = m['tile_base']
    out, prio = {}, {}
    for p in 'AB':
        t = np.array(m['planes'][p], np.int64)
        h, w = t.shape
        img = np.zeros((h * 8, w * 8, 4), np.uint8)
        for cy in range(h):
            for cx in range(w):
                v = int(t[cy, cx])
                if not v:
                    continue
                px = tiles[(v & 0x7FF) - base]
                if v & 0x800:
                    px = px[:, ::-1]
                if v & 0x1000:
                    px = px[::-1]
                cell = img[cy * 8:cy * 8 + 8, cx * 8:cx * 8 + 8]
                cell[:, :, :3] = palette[((v >> 13) & 3) * 16 + px]
                cell[:, :, 3] = (px > 0) * 255
        out[f'plane_{p.lower()}.png'] = png(img)
        prio[p] = ((t >> 15) & 1).astype(int).tolist()
    out['cram.json'] = json.dumps(colors).encode()
    out['prio.json'] = json.dumps(prio, separators=(',', ':')).encode()
    return out


def anim_states(key, disc):
    """MK's animation on the stage (data/mk_stages/<stage>.json 'anim', recorded by
    tools/capture/mkstagemaps.py) with its art from the disc: each element's states as pixels
    (colour indices). A cell element (the Gates' torches, the Lair's eyes): per state, per cell,
    [its name-table word, 64 indices]. A tile element (the Courtyard's monks): per state, per tile,
    64 indices, and every plane cell showing those tiles ([plane, y, x, word])."""
    m = json.load(open(ROOT / 'data' / 'mk_stages' / f'{key}.json'))
    a = m.get('anim') or dict(elements=[], extra={}, frames=0)
    bg = (disc / f'BACKGD{m["backgd"]}.BIN').read_bytes()
    off = [int.from_bytes(bg[i:i + 4], 'big') for i in range(0, 24, 4)]
    tiles = tiles_of(rnc1(bg, off[0]))
    six = rnc1(bg, off[5]) if bg[off[5]:off[5] + 3] == b'RNC' else b''
    extra = tiles_of(six) if six and len(six) % 32 == 0 else None
    base = m['tile_base']

    def tile(i):
        if str(i) in a['extra']:
            return extra[a['extra'][str(i)]]
        return tiles[i - base]
    out = []
    for e in a['elements']:
        if 'cells' in e:
            out.append(dict(kind='cells', plane=e['plane'], cells=e['cells'], runs=e['runs'],
                            states=[[[w, tile(w & 0x7FF).ravel().tolist()] for w in st] for st in e['states']]))
        else:
            want = set(e['tiles'])
            shows = [[p, y, x, int(w)] for p in 'AB' for y, row in enumerate(m['planes'][p]) for x, w in enumerate(row)
                     if w and (w & 0x7FF) - base in want]
            states = []
            for st in e['states']:
                states.append([tiles_of(bg[o:o + 32])[0].ravel().tolist() for o in st])
            out.append(dict(kind='tiles', tiles=e['tiles'], shows=shows, runs=e['runs'], states=states))
    return json.dumps(dict(frames=a['frames'], elements=out), separators=(',', ':')).encode()


def mk_planes(key):
    """MK's own planes (RGBA) and CRAM from the battle state, its HUD rows and other cells cleared."""
    import scd
    from inputs import require
    from vdp import VDPState
    m = json.load(open(ROOT / 'data' / 'mk_stages' / f'{key}.json'))
    c = scd.Core(saves=str(ROOT / 'build' / 'shots' / 'capture-saves'))
    c.load(require('mk_us').cue)
    c.load_state(str(ROOT / 'build' / 'states' / f'mk_battle_{m["battle"]}.state'))
    c.run(2)
    v = VDPState(c.snapshot())
    planes = {}
    for p in 'AB':
        img, used = v.plane(p)
        keep = np.kron(np.array(m['planes'][p]) > 0, np.ones((8, 8), bool))
        planes[p] = np.dstack([img, (used & keep) * 255]).astype(np.uint8)
    return planes, v.cram_raw, set(m['animated']), m


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--disc', type=Path, default=ROOT / 'extracted' / 'mk_us')
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', action='store_true')
    group.add_argument('--out', type=Path, metavar='EXTRACTED')
    a = ap.parse_args()
    bad = 0
    for key in STAGES + ('lair',):
        results = build(key, a.disc) if key != 'lair' else {}       # (the Lair's planes: mklair_disc.py)
        results["anim.json"] = anim_states(key, a.disc)
        if key == 'lair' and not a.out:
            continue
        if a.out:
            d = a.out / 'mk_stages' / key
            d.mkdir(parents=True, exist_ok=True)
            for name, data in results.items():
                (d / name).write_bytes(data)
            print(d)
            continue
        planes, cram_raw, animated, m = mk_planes(key)
        for p in 'AB':
            ours = np.asarray(Image.open(io.BytesIO(results[f'plane_{p.lower()}.png'])))
            theirs = planes[p]
            # cells showing a tile MK animates: any frame (ours is the file's)
            t = np.array(m['planes'][p])
            anim = np.kron(np.isin((t & 0x7FF) - m['tile_base'], list(animated)) & (t > 0), np.ones((8, 8), bool))
            for e in m.get('anim', {}).get('elements', []):          # (cells MK animates by their words)
                if e.get('plane') == p:
                    for y, x in e['cells']:
                        anim[y * 8:y * 8 + 8, x * 8:x * 8 + 8] = True
            seen = (ours[:, :, 3] > 0) | (theirs[:, :, 3] > 0)        # (clear pixels' colours don't count)
            diff = np.any(ours != theirs, axis=2) & seen & ~anim
            # colours by value: MK's CRAM lines 2-3 are the stage's
            print(f'{key} plane {p}: {"identical" if not diff.any() else f"{int(diff.sum())} pixels DIFFERENT"}'
                  f'{f" ({int(anim.sum() // 64)} animated cells skipped)" if anim.any() else ""}')
            bad += bool(diff.any())
        ok = json.loads(results['cram.json'])[32:] == [c if i % 16 else 0 for i, c in enumerate(cram_raw[32:])]
        print(f'{key} palette lines 2-3: {"identical" if ok else "DIFFERENT"}')
        bad += not ok
    if bad:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
