#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Rebuild MK captures from their recipes (docs/research/reproducibility_2026-11.md).

data/mk_recipes/MK_DIR/ACTION.json (made by tools/lib/mkrecipes.py --out) names,
for every pose the build reads, the MK frames drawn into it; the frames come
from your MK disc (tools/lib/mkframes.py, through the fight states prepare.py
makes). A pose the build doesn't read is left blank: it only keeps its place.

    mkfromrecipes.py [MK_DIR[/ACTION] ...]            -> extracted/MK_DIR/ACTION/indexed.npy
    mkfromrecipes.py --check [MK_DIR[/ACTION] ...]    -> compare with what's there, write nothing
"""
import argparse, glob, json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inputs import ROOT
import mkrecipes

DATA = os.path.join(ROOT, 'data', 'mk_recipes')


def part(t):
    """A recipe part from JSON (lists) to mkrecipes.draw's tuple; a piece's
    frame is its hash name, a frame's its number."""
    return tuple(t)


def rebuild(path, frames_cache):
    """(poses, the poses drawn): indexed, or RGB for an RGB capture (drawn in
    canonical indices, coloured with each pose's palette)."""
    r = json.load(open(path))
    crams = None
    if 'rgb' in r:
        import mkcapmeta
        crams = [mkcapmeta.palette(src) for src in r['rgb']]
    out = np.zeros((len(r['poses']), mkrecipes.H, mkrecipes.W) + ((3,) if crams else ()), np.uint8)
    for i, parts in enumerate(r['poses']):
        if parts is None:
            continue
        remap = mkrecipes.canon(crams[r['palette_of'][i]]) if crams else None
        key = (tuple(r['sources']), None if remap is None else remap.tobytes())
        if key not in frames_cache:
            frames_cache[key] = mkrecipes.frames_of(r['sources'], remap)
        q = mkrecipes.draw([part(t) for t in parts], frames_cache[key])
        out[i] = mkrecipes.colours(crams[r['palette_of'][i]])[q] * (q > 0)[..., None] if crams else q
    return out, [i for i, p in enumerate(r['poses']) if p is not None]


def target(name, r):
    return os.path.join(ROOT, 'extracted', name, 'rgb.npy' if 'rgb' in r else 'indexed.npy')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('which', nargs='*')
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    todo = sorted(glob.glob(os.path.join(DATA, '*', '*.json')))
    if a.which:
        todo = [p for p in todo if any(os.path.relpath(p, DATA)[:-5] == w or
                                       os.path.relpath(p, DATA).split('/')[0] == w for w in a.which)]
    cache, bad = {}, []
    for p in todo:
        name = os.path.relpath(p, DATA)[:-5]
        poses, made = rebuild(p, cache)
        dst = target(name, json.load(open(p)))
        if a.check:
            have = np.load(dst)
            wrong = [i for i in made if not (have[i] == poses[i]).all()]
            ok = len(have) == len(poses) and not wrong
            print(f'{name:40s} {len(made) - len(wrong):4d}/{len(made):4d} exact' + ('' if ok else f'  WRONG {wrong[:10]}'))
            if not ok:
                bad.append(name)
        else:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            np.save(dst, poses)
            print(f'{name:40s} {len(made):4d} poses drawn')
    if bad:
        sys.exit(f'not exact: {" ".join(bad)}')


if __name__ == '__main__':
    main()
