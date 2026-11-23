#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Capture Scorpion's MK dazed pose (FINISH HIM, as the loser) from the MK disc.

In build/states/mk_2p.state player 2 (Sub-Zero) uppercuts an idle Scorpion until
he wins twice; then Scorpion (player 1, palette line 0) wobbles. Writes
extracted/mk_moves/dizzy_raw/ (everything) and from it dizzy/ (the sway) and
lying/ (flat on his back), as tools/lib/mkmoves.py does.

    mkdizzy.py
"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import mkmoves
from vdp import VDPState
from inputs import ROOT

QUIET = 1502          # the round-winning blow has landed (FINISH HIM shows ~1506): Sub-Zero stops


def main():
    s = mkmoves.Session()
    c = s.core
    c.load_state(os.path.join(ROOT, 'build', 'states', 'mk_2p.state'))
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
    mkmoves.save('dizzy_raw', poses, order, cram)   # poses 0-4: hit while standing; 5-11: the FINISH HIM sway; 16: lying flat
    print(len(poses), 'poses over', len(order), 'frames')
    split(poses, cram)


SWAY, LYING = range(5, 12), 16       # in the capture (deterministic: the same every run)


def split(poses, cram):
    """dizzy/: the sway, all on its first pose's feet (he sways in place); lying/:
    flat on his back, anchored under the middle of his body."""
    import json
    sway = [poses[k] for k in SWAY]
    mkmoves.save('dizzy', sway, list(range(len(sway))), cram)
    a0 = mkmoves.anchor(sway[0])
    json.dump([a0] * len(sway), open(os.path.join(mkmoves.OUT, 'dizzy', 'anchors.json'), 'w'))
    p = poses[LYING]
    ys, xs = np.nonzero(p)
    mkmoves.save('lying', [p], [0], cram)
    json.dump([[int(xs.min() + xs.max()) // 2, int(ys.max()) + 1]], open(os.path.join(mkmoves.OUT, 'lying', 'anchors.json'), 'w'))


if __name__ == '__main__':
    main()
