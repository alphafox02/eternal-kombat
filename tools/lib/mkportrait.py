#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Capture an MK fighter's portrait from MK's character-select screen.

From build/states/mk_select.state into extracted/<his MK dir>/portrait.png (RGB,
native pixels; Scorpion's in mk_moves/ by default). patches.scorpion_portrait
fits it into EC's versus-screen frame.

    mkportrait.py [--fighter raiden] [--box x0,y0,x1,y1]
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scd
from inputs import ROOT, require
from PIL import Image

BOX = (195, 113, 237, 163)    # inside Scorpion's frame on MK's select screen (320x224)
# the frames sit 57 px apart: bottom row Raiden, Liu Kang, Scorpion; top row
# Johnny Cage, Kano, (dragon), Sub-Zero, Sonya
BOXES = {'scorpion': (BOX, 'mk_moves'), 'raiden': ((81, 113, 123, 163), 'mk_moves_raiden'),
         'subzero': ((195, 49, 237, 99), 'mk_moves_subzero'), 'johnny': ((24, 49, 66, 99), 'mk_moves_johnny'),
         'liukang': ((138, 113, 180, 163), 'mk_moves_liukang'), 'kano': ((81, 49, 123, 99), 'mk_moves_kano'),
         'sonya': ((252, 49, 294, 99), 'mk_moves_sonya')}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fighter', default='scorpion', choices=sorted(BOXES))
    ap.add_argument('--box', help='x0,y0,x1,y1 (default: the fighter\'s)')
    a = ap.parse_args()
    box, folder = BOXES[a.fighter]
    if a.box:
        box = tuple(int(v) for v in a.box.split(','))
    c = scd.Core(saves=os.path.join(ROOT, 'build', 'shots', 'capture-saves'))
    c.load(require('mk_us').cue)
    c.load_state(os.path.join(ROOT, 'build', 'states', 'mk_select.state'))
    c.run(30)
    if a.fighter == 'kano':                      # player 1's cursor starts on him: move it off
        c.press(['right'])
        c.run(30)
    os.makedirs(os.path.join(ROOT, 'extracted', folder), exist_ok=True)
    out = os.path.join(ROOT, 'extracted', folder, 'portrait.png')
    Image.fromarray(c.frame).crop(box).save(out)
    print('->', os.path.relpath(out, ROOT), box)


if __name__ == '__main__':
    main()
