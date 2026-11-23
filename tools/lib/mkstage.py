#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Dump an MK stage's background layers from a fight state on the MK disc.

VDP planes A and B as PNGs (every cell, transparent where tile colour 0),
plus the 4 palette lines: the reference mkpit_disc.py and mklair_disc.py --check against.

    mkstage.py [--state build/states/mk_pit_raw.state] [--name pit]
        -> extracted/mk_stages/<name>/plane_a.png, plane_b.png, cram.json
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image
import scd
from inputs import ROOT, require
from vdp import VDPState


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--state', default=os.path.join(ROOT, 'build', 'states', 'mk_pit_raw.state'))
    ap.add_argument('--name', default='pit')
    ap.add_argument('--run', type=int, default=2, help='frames to run first')
    a = ap.parse_args()
    c = scd.Core(saves=os.path.join(ROOT, 'build', 'shots', 'capture-saves'))
    c.load(require('mk_us').cue)
    c.load_state(a.state)
    c.run(a.run)
    v = VDPState(c.snapshot())
    out = os.path.join(ROOT, 'extracted', 'mk_stages', a.name)
    os.makedirs(out, exist_ok=True)
    for p in 'AB':
        img, used = v.plane(p)
        rgba = np.dstack([img, (used * 255).astype(np.uint8)])
        Image.fromarray(rgba, 'RGBA').save(os.path.join(out, f'plane_{p.lower()}.png'))
    json.dump(v.cram_raw, open(os.path.join(out, 'cram.json'), 'w'))
    Image.fromarray(c.frame).save(os.path.join(out, 'screen.png'))
    print('plane size', v.plane_size(), '->', os.path.relpath(out, ROOT))


if __name__ == '__main__':
    main()
