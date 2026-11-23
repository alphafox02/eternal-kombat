#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""MK captures whose frames ran off MK's screen, put back whole (data/mk_recipes, data/mk_meta).

The knockdown and sweep captures were taken with the victim flying into the left edge of MK's screen
(and up off its top): a recipe draws each MK frame where MK drew it, clipped by the screen, so the
tumble and the lying poses lost their heads and chests (Sub-Zero's and Johnny Cage's heads were cut
off as they were knocked down: Sub-Zero's frame 135 lost up to 407 of its pixels, 17 px off the left
edge). Each such pose is moved onto the screen
whole - all its parts by the same (dx, dy) - and its anchor (anchors.json: where its feet are,
the point the build places it by) by the same, so it shows where it did, with what was cut.

Only the actions below: a fatality's or the spear's captures keep their framing (the screen edge is
part of those scenes, and their own fixes - mkinputs' spear crop - rely on it).

    mkunclip.py            -> fix data/mk_recipes and data/mk_meta (then mkfromrecipes.py, mkcapmeta.py)
    mkunclip.py --check    -> list poses still cut (exit 1 if any)
"""
import argparse, glob, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import numpy as np
from inputs import ROOT
import mkrecipes

ACTIONS = ('knockdown', 'swept', 'jump_back', 'hit_high', 'hit_low', 'hit_kick')
LOST = 4                      # pixels a pose may lose to the screen's edges (a stray pixel or two)


def extent(part, frames):
    """(x0, y0, x1, y1) of a part's drawn pixels on the screen (x1, y1 exclusive), unclipped."""
    if part[0] == 'line':
        _, y, x0, x1, _ = part
        return x0, y, x1 + 1, y + 1
    if part[0] == 'cut':
        return None
    src, f, mir, x, y = part[:5]
    keep = part[5] if len(part) > 5 else None
    sp = frames[(src, f)]
    fw = max(sx + int(np.nonzero(p.any(0))[0][-1]) + 1 for sx, sy, p in sp if p.any())
    box = None
    for k, (sx, sy, p) in enumerate(sp):
        if keep is not None and not keep >> k & 1:
            continue
        if mir:
            sx, p = fw - sx - p.shape[1], p[:, ::-1]
        X, Y = x + sx, y + sy
        if Y <= mkrecipes.TOP:
            continue
        ys, xs = np.nonzero(p)
        if not len(ys):
            continue
        b = (X + xs.min(), Y + ys.min(), X + xs.max() + 1, Y + ys.max() + 1)
        box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
    return box


def lost(parts, frames):
    """Pixels of a pose's frames that fall outside the screen (not those a later part covers)."""
    n = 0
    for part in parts:
        if part[0] in ('line', 'cut'):
            continue
        src, f, mir, x, y = part[:5]
        keep = part[5] if len(part) > 5 else None
        sp = frames[(src, f)]
        fw = max(sx + int(np.nonzero(p.any(0))[0][-1]) + 1 for sx, sy, p in sp if p.any())
        for k, (sx, sy, p) in enumerate(sp):
            if keep is not None and not keep >> k & 1:
                continue
            if mir:
                sx, p = fw - sx - p.shape[1], p[:, ::-1]
            X, Y = x + sx, y + sy
            if Y <= mkrecipes.TOP:
                continue
            ys, xs = np.nonzero(p)
            ys, xs = ys + Y, xs + X
            n += int((~((ys >= 0) & (ys < mkrecipes.H) & (xs >= 0) & (xs < mkrecipes.W))).sum())
    return n


def shift(part, dx, dy):
    part = list(part)
    if part[0] == 'line':                       # ('line', y, x0, x1, colour)
        part[1] += dy; part[2] += dx; part[3] += dx
    elif part[0] == 'cut':                      # ('cut', y, x0, x1)
        part[1] += dy; part[2] += dx; part[3] += dx
    else:
        part[3] += dx; part[4] += dy
    return part


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    cache, bad = {}, []
    for path in sorted(glob.glob(os.path.join(ROOT, 'data', 'mk_recipes', '*', '*.json'))):
        mk_dir, act = path.split(os.sep)[-2], os.path.basename(path)[:-5]
        if act not in ACTIONS:
            continue
        r = json.load(open(path))
        if 'rgb' in r:
            continue
        key = tuple(r['sources'])
        if key not in cache:
            cache[key] = mkrecipes.frames_of(r['sources'])
        frames = cache[key]
        meta_path = os.path.join(ROOT, 'data', 'mk_meta', mk_dir, act + '.json')
        meta = json.load(open(meta_path)) if os.path.exists(meta_path) else {}
        if 'anchors.json' not in meta:         # (placed without anchors: nothing to move it by)
            continue
        anchors = json.loads(meta['anchors.json']) if isinstance(meta['anchors.json'], str) else meta['anchors.json']
        moved = []
        for i, parts in enumerate(r['poses']):
            if not parts or lost(parts, frames) <= LOST:
                continue
            boxes = [b for b in (extent(p, frames) for p in parts) if b]
            x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
            x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
            if x1 - x0 > mkrecipes.W or y1 - y0 > mkrecipes.H:
                raise SystemExit(f'{mk_dir}/{act} pose {i}: wider than the screen')
            dx = int(-x0 if x0 < 0 else (mkrecipes.W - x1 if x1 > mkrecipes.W else 0))
            dy = int(-y0 if y0 < 0 else (mkrecipes.H - y1 if y1 > mkrecipes.H else 0))
            moved.append((i, dx, dy, lost(parts, frames)))
            if not a.check:
                r['poses'][i] = [shift(p, dx, dy) for p in parts]
                anchors[i] = [anchors[i][0] + dx, anchors[i][1] + dy]
                assert lost(r['poses'][i], frames) <= LOST, (mk_dir, act, i)
        if not moved:
            continue
        print(f'{mk_dir}/{act}: ' + ', '.join(f'pose {i} {n} px cut -> moved {dx:+d},{dy:+d}' for i, dx, dy, n in moved))
        bad.append(f'{mk_dir}/{act}')
        if not a.check:                         # (each file as its own tool writes it: mkrecipes, mkcapmeta)
            assert isinstance(meta['anchors.json'], str)
            meta['anchors.json'] = json.dumps(anchors)
            for p, write in ((path, lambda o: json.dump(r, o, separators=(',', ':'))),
                             (meta_path, lambda o: json.dump(meta, o, indent=0, sort_keys=True))):
                with open(p + '.tmp', 'w') as o:
                    write(o)
                os.replace(p + '.tmp', p)
    if a.check:
        print(f'captures cut by the screen: {len(bad)}' + (f' ({" ".join(bad)})' if bad else ''))
        sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
