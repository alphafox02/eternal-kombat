#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Make an MK 2-player fight state to capture a fighter's moves from.

For tools/lib/mkmoves.py --fighter=...: from build/states/mk_select.state, player 1 picks
the fighter, player 2 joins and picks an opponent, and the state is saved once
player 1 responds to the pad (his sprite moves when Right is held).

MK's select screen: top row Johnny Cage, Kano, (dragon), Sub-Zero, Sonya;
bottom row Raiden, Liu Kang, Scorpion. Player 1's cursor starts on Kano,
player 2's on Sub-Zero.

    mkduelstate.py johnny|johnny_sonya|subzero|subzero_sonya|subzero_raiden|subzero_johnny|subzero_subzero|raiden|scorpion|liukang|sonya|kano
                   [--states DIR]   (where mk_select.state is and the fight state goes; default build/states/)
"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import mkmoves
from inputs import ROOT

# fighter: (player 1's presses from Kano, player 2's from Sub-Zero, state file)
PICKS = {
    'johnny':   (['left'], [], 'mk_johnny_2p.state'),
    'johnny_sonya': (['left'], ['right'], 'mk_johnny_sonya_2p.state'),   # vs Sonya (MK's one woman)
    'kano':     ([], [], 'mk_kano_2p.state'),
    'subzero':  (['right'], ['down'], 'mk_subzero_2p.state'),     # vs Scorpion
    'subzero_sonya': (['right'], ['right'], 'mk_subzero_sonya_2p.state'),   # vs Sonya (his fatality on a woman)
    # vs each MK fighter of ours: tools/capture/mkvictim.py captures the spine rip's victim
    'subzero_raiden': (['right'], ['down', 'left', 'left'], 'mk_subzero_raiden_2p.state'),
    'subzero_johnny': (['right'], ['left', 'left'], 'mk_subzero_johnny_2p.state'),
    'subzero_subzero': (['right'], [], 'mk_subzero_subzero_2p.state'),
    'subzero_liukang': (['right'], ['down', 'left'], 'mk_subzero_liukang_2p.state'),
    'subzero_kano': (['right'], ['left'], 'mk_subzero_kano_2p.state'),
    'scorpion_sonya': (['down', 'right', 'right'], ['right'], 'mk_scorpion_sonya_2p.state'),   # (his fatality on a woman)
    'sonya':    (['right', 'right'], [], 'mk_sonya_2p.state'),
    'raiden':   (['down'], [], 'mk_raiden_2p.state'),
    'liukang':  (['down', 'right'], [], 'mk_liukang_2p.state'),
    'scorpion': (['down', 'right', 'right'], [], 'mk_2p.state'),
}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('name', nargs='?', default='johnny', choices=sorted(PICKS))
    ap.add_argument('--states', default=os.path.join(ROOT, 'build', 'states'))
    a = ap.parse_args()
    name, sdir = a.name, a.states
    p1, p2, out = PICKS[name]
    s = mkmoves.Session()
    c = s.core
    c.load_state(os.path.join(sdir, 'mk_select.state'))
    c.run(10)
    c.press(['start'], port=1)
    c.run(30)
    for d in p1:
        c.press([d])
        c.run(20)
    for d in p2:
        c.press([d], port=1)
        c.run(20)
    c.press(['start'])
    c.run(20)
    c.press(['start'], port=1)
    c.run(20)
    tmp = os.path.join(sdir, out + '.tmp')

    def p1_x():
        f = s.frame(s.vdp())
        xs = np.nonzero(f.any(0))[0]
        return xs.mean() if len(xs) else None
    for t in range(0, 3000, 20):
        c.run(20)
        c.save_state(tmp)
        x0 = p1_x()
        c.buttons[0] = {'right'}
        c.run(16)
        c.buttons[0] = set()
        x1 = p1_x()
        c.load_state(tmp)
        if x0 is not None and x1 is not None and x1 - x0 >= 6:
            c.save_state(os.path.join(sdir, out))
            os.remove(tmp)
            print(f'{name}: fight live after {t} frames; saved {os.path.join(sdir, out)}')
            return
    os.remove(tmp)
    raise SystemExit('player 1 never moved')


if __name__ == '__main__':
    main()
