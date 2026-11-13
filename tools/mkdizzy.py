#!/usr/bin/env python3
"""Capture Scorpion's MK dazed pose (FINISH HIM, as the loser) from the MK disc:
in states/mk_2p.state player 2 (Sub-Zero) uppercuts an idle Scorpion until
he wins twice; then Scorpion (player 1, palette line 0) wobbles. Writes
extracted/mk_moves/dizzy/ like tools/mkmoves.py does.

    mkdizzy.py
"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mkmoves
from vdp import VDPState
from inputs import ROOT

QUIET = 1502          # the round-winning blow has landed (FINISH HIM shows ~1506): Sub-Zero stops


def main():
    s = mkmoves.Session()
    c = s.core
    c.load_state(os.path.join(ROOT, 'states', 'mk_2p.state'))
    v = lambda: VDPState(c.snapshot())

    def centre(pal):
        xs = [sp['x'] for sp in v().sprites() if sp['pal'] == pal and sp['y'] > 40]
        return (min(xs) + max(xs)) // 2 if xs else None
    poses, index, order = [], {}, []
    import hashlib
    for k in range(2400):                                    # Sub-Zero wins two rounds
        a, b = centre(0), centre(1)
        if k >= QUIET:                                       # FINISH HIM: Sub-Zero waits, Scorpion wobbles
            c.buttons[1] = set()
        elif a is not None and b is not None and abs(b - a) > 55:
            c.buttons[1] = {'left' if b > a else 'right'}
        else:
            c.buttons[1] = {'down', 'x'} if k % 20 < 6 else ({'down'} if k % 20 < 10 else set())
        c.buttons[0] = set()
        c.run(1)
        if k > 1300:                                         # FINISH HIM comes in the second round
            f = s.frame(s.vdp())
            if f.any():
                ys, xs = np.nonzero(f)
                h = hashlib.md5(f[ys.min():ys.max() + 1, xs.min():xs.max() + 1].tobytes()).hexdigest()
                if h not in index:
                    index[h] = len(poses)
                    poses.append(f)
                order.append(index[h])
    vv = s.vdp()
    cram = vv.cram_raw[0:16]
    mkmoves.save('dizzy_raw', poses, order, cram)   # poses 0-4: hit while standing; 5-11: the FINISH HIM sway (-> dizzy/); 16: lying flat (-> lying/)
    print(len(poses), 'poses over', len(order), 'frames')


if __name__ == '__main__':
    main()
