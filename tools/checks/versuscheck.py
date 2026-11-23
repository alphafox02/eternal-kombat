#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Reptile's versus portrait (patches.reptile_portrait): Sub-Zero's, his blues turned green.

EC has portraits for ids 2-25 and drew id 26 (his slot) as id 11, Shang Tsung's now. His is
Sub-Zero's picture with his blues turned green, on either side of the screen (palette lines 2
and 3):
  - Sub-Zero vs Reptile: the same shapes (each of Sub-Zero's colours is one of Reptile's), and
    most of Sub-Zero's blue pixels are green in Reptile's;
  - Reptile vs Shang: Reptile's (player 1's side now) is the same picture; Shang's is his own.

    versuscheck.py [--disc CUE]     (run after play.py test has made the disc's build/states/menu.state)
"""
import argparse, os, sys
from collections import defaultdict
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT

PICKS = (0x31428, 0x3142A)              # $1428(a6), $142A(a6): the players' fighters (id - 2)
BOXES = ((48, 80), (200, 80))           # the portraits' top left (72 x 104, the gold frame inside)
FRAME_GOLD = (238, 170, 32)
REPTILE, SUBZERO, SHANG = 26, 20, 11


def versus(disc, p1, p2):
    """The versus screen's two portraits (inside their frames) for fighters p1, p2 (ids), both facing
    as player 1's."""
    c = scd.Core(saves=os.path.join(ROOT, 'build', 'tmp', 'versuscheck-saves'))
    c.load(disc)
    c.load_state(os.path.join(ROOT, 'build', 'states', 'menu.state'))
    c.press(['start']); c.run(240)                     # title -> main menu
    c.press(['down']); c.run(20)                       # Duel
    c.press(['start']); c.run(240)
    c.press(['start'], port=1); c.run(40)              # player 2 joins
    c.press(['start']); c.run(40)                      # both pick (then overwritten: duelstate --p2-id)
    c.press(['start'], port=1); c.run(2)
    prev, same = None, 0
    for _ in range(600):
        for at, fid in zip(PICKS, (p1, p2)):
            if c.prg_ram()[at:at + 2] != (fid - 2).to_bytes(2, 'big'):
                c.poke_prg(at, (fid - 2).to_bytes(2, 'big'))
        c.run(1)
        f = c.frame
        boxes = [f[y + 2:y + 102, x + 2:x + 70].copy() for x, y in BOXES]
        boxes[1] = boxes[1][:, ::-1]                   # (player 2's is drawn mirrored)
        framed = all(tuple(f[y, x + 30]) == FRAME_GOLD for x, y in BOXES)
        same = same + 1 if framed and prev is not None and all(np.array_equal(a, b) for a, b in zip(boxes, prev)) else 0
        prev = boxes
        if same == 30:                                 # half a second still: drawn and faded in
            return boxes
    sys.exit(f'FAIL: no versus screen for {p1} vs {p2}')


def colours(a):
    return a.reshape(-1, 3).astype(int)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    a = ap.parse_args()
    bad = []
    sz, rep = versus(a.disc, SUBZERO, REPTILE)
    s, r = colours(sz), colours(rep)
    to = defaultdict(set)
    for x, y in zip(map(tuple, s), map(tuple, r)):
        to[x].add(y)
    split = {k: v for k, v in to.items() if len(v) > 1}
    if split:
        bad.append(f"Reptile's isn't Sub-Zero's picture: {len(split)} of Sub-Zero's colours are several of his")
    blue = (s[:, 2] > s[:, 0] + 40) & (s[:, 2] > s[:, 1])
    green = (r[:, 1] > r[:, 0]) & (r[:, 1] > r[:, 2])
    share = (blue & green).sum() / max(1, blue.sum())
    if blue.sum() < 300 or share < 0.8:
        bad.append(f"Sub-Zero's blues aren't green in Reptile's: {blue.sum()} blue pixels, {share:.0%} green")
    print(f'Sub-Zero vs Reptile: one colour each ({len(to)} colours), {blue.sum()} blue pixels, {share:.0%} green in his')
    rep1, shang = versus(a.disc, REPTILE, SHANG)
    if not np.array_equal(rep1, rep):
        bad.append(f"Reptile's on player 1's side differs from player 2's: {(rep1 != rep).any(axis=2).sum()} pixels")
    if (shang != rep1).any(axis=2).mean() < 0.5:
        bad.append("Shang's portrait looks like Reptile's")
    print(f"Reptile vs Shang: Reptile's {'the same' if np.array_equal(rep1, rep) else 'different'} as player 1, "
          f"Shang's {(shang != rep1).any(axis=2).mean():.0%} different")
    for b in bad:
        print('FAIL:', b)
    print('versuscheck:', 'FAIL' if bad else 'ok')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
