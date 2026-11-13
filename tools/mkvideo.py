#!/usr/bin/env python3
"""Record MK CD itself (with sound) as a reference clip for a move, to set
beside Eternal Kombat's version. From states/mk_2p.state (Scorpion vs
Sub-Zero; tools/mkduelstate.py).

    mkvideo.py teleport [--out shots/mk_scorpion_teleport.mp4]

teleport: Scorpion's teleport punch (down, back + HP) three times - with
Sub-Zero mid-screen (he misses), with Sub-Zero by the far edge (it hits), and
from the other side.
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import mkmoves
from scd import Core
from inputs import ROOT, require
from finishvideo import Rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('move', choices=('teleport',))
    ap.add_argument('--out')
    a = ap.parse_args()
    out = a.out or os.path.join(ROOT, 'shots', f'mk_scorpion_{a.move}.mp4')
    c = Core(audio=True, saves=os.path.join(ROOT, 'shots', 'capture-saves'))
    c.load(require('mk_us').cue)
    c.load_state(os.path.join(ROOT, 'states', 'mk_2p.state'))
    c.run(5)
    c.audio.clear()
    s = mkmoves.Session.__new__(mkmoves.Session)      # its sprite helpers on this core
    s.core = c
    r = Rec(c, out)

    def centre(pal):
        f = s.frame(s.vdp()) if pal == 0 else None
        if pal == 0:
            xs = np.nonzero(f.any(0))[0]
            return xs.mean() if len(xs) else None
        from vdp import VDPState
        xs = [sp['x'] for sp in VDPState(c.snapshot()).sprites() if sp['pal'] == 1 and sp['y'] > 40]
        return (min(xs) + max(xs)) / 2 if xs else None

    def p2(held, n):
        c.buttons[1] = set(held)
        r.run(n)
        c.buttons[1] = set()

    def teleport(back):
        for held, n in ((['down'], 3), ([], 2), ([back], 3), (['x'], 4)):
            r.run(n, held)
        r.run(110)

    r.run(40)
    teleport('left')                                   # Sub-Zero mid-screen: a miss
    p2(['left'], 1)
    r.run(40)
    # Scorpion now stands on the right: Sub-Zero walks to the left edge, Scorpion teleports (back = right)
    p2(['left'], 120)
    r.run(30)
    teleport('right')                                  # he comes in at the left edge: it hits
    r.run(60)
    teleport('left' if (centre(0) or 0) < 160 else 'right')
    r.run(40)
    r.close()
    print(f'{r.frames / c.fps:.1f}s -> {os.path.relpath(out, ROOT)}')


if __name__ == '__main__':
    main()
