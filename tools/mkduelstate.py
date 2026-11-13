#!/usr/bin/env python3
"""Make an MK 2-player fight state for capturing a fighter's moves
(tools/mkmoves.py --fighter=...): from states/mk_select.state, player 1 picks
the fighter, player 2 joins and picks an opponent, and the state is saved once
player 1 responds to the pad (his sprite moves when Right is held).

MK's select screen: top row Johnny Cage, Kano, (dragon), Sub-Zero, Sonya;
bottom row Raiden, Liu Kang, Scorpion. Player 1's cursor starts on Kano,
player 2's on Sub-Zero.

    mkduelstate.py johnny|johnny_sonya|subzero|raiden|scorpion|liukang|sonya|kano
"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mkmoves
from inputs import ROOT

# fighter: (player 1's presses from Kano, player 2's from Sub-Zero, state file)
PICKS = {
    'johnny':   (['left'], [], 'mk_johnny_2p.state'),
    'johnny_sonya': (['left'], ['right'], 'mk_johnny_sonya_2p.state'),   # vs Sonya (MK's one woman)
    'kano':     ([], [], 'mk_kano_2p.state'),
    'subzero':  (['right'], ['down'], 'mk_subzero_2p.state'),     # vs Scorpion
    'sonya':    (['right', 'right'], [], 'mk_sonya_2p.state'),
    'raiden':   (['down'], [], 'mk_raiden_2p.state'),
    'liukang':  (['down', 'right'], [], 'mk_liukang_2p.state'),
    'scorpion': (['down', 'right', 'right'], [], 'mk_2p.state'),
}


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else 'johnny'
    p1, p2, out = PICKS[name]
    s = mkmoves.Session()
    c = s.core
    c.load_state(os.path.join(ROOT, 'states', 'mk_select.state'))
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
    tmp = os.path.join(ROOT, 'states', out + '.tmp')

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
            c.save_state(os.path.join(ROOT, 'states', out))
            os.remove(tmp)
            print(f'{name}: fight live after {t} frames; saved states/{out}')
            return
    os.remove(tmp)
    raise SystemExit('player 1 never moved')


if __name__ == '__main__':
    main()
