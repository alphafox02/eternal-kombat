#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Make build/states/mk_pit_raw.state: Kano vs Kano at the start of a fight on MK's Pit.

From your MK CD (the Pit tools start there: tools/lib/mkstage.py, mkpitbottom.py,
mkpitsound.py).

MK's 2-player stages come in a fixed order: the Courtyard, the Palace Gates,
the Warrior Shrine, then the Pit (battle 4). From build/states/mk_kano_2p.state
(tools/capture/mkduelstate.py kano: battle 1) player 2 crouch-punches player 1 down
(walking in when far) and player 1 presses Start every second (to continue,
with the same pick). A battle starts when MK's fight HUD comes back (in_fight); in the
fourth, the state is saved once the fight has begun.

    mkpitstate.py [--out PATH]        -> build/states/mk_pit_raw.state
"""
import argparse, os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import mkmoves
from vdp import VDPState
from inputs import ROOT

PIT_BATTLE = 4
SETTLE = 300                  # frames after the fighters show up: the round has begun


def in_fight(frame):
    """MK's fight HUD: a green health bar (rows 8-14; either player's: the loser's
    empties; none on the select, versus and loading screens)."""
    f = np.asarray(frame)
    if f.ndim < 3 or f.shape[1] < 320:
        return False
    green = lambda t: int(((t[..., 1] > 110) & (t[..., 0] < 80) & (t[..., 2] < 40)).sum())
    return max(green(f[8:15, 10:150].astype(int)), green(f[8:15, 170:310].astype(int))) > 150


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(ROOT, 'build', 'states', 'mk_pit_raw.state'))
    out = ap.parse_args().out
    s = mkmoves.Session()
    c = s.core
    c.load_state(os.path.join(ROOT, 'build', 'states', 'mk_kano_2p.state'))
    c.run(2)

    def centre(pal):
        xs = [sp['x'] for sp in VDPState(c.snapshot()).sprites() if sp['pal'] == pal and sp['y'] > 40]
        return (min(xs) + max(xs)) // 2 if xs else None
    battle, fight, away, since, a, b = 1, True, 0, 0, None, None
    for k in range(60 * 60 * 15):
        if k % 15 == 0:
            now = in_fight(c.frame)
            if now and not fight and away >= 600:          # a new battle (the HUD back after 10 s+: between
                                                            #  rounds it is gone only briefly)
                battle += 1
                since = k
                if os.environ.get('EK_DEBUG'):
                    print('battle', battle, 'at', k, flush=True)
            away = 0 if now else away + 15
            fight = now
            a, b = centre(0), centre(1)
        if battle == PIT_BATTLE:
            c.buttons = [set(), set()]
            if fight and k >= since + SETTLE:
                c.save_state(out)
                print(f'battle {battle} (the Pit) at frame {k} -> {os.path.relpath(out, ROOT)}')
                return
            c.run(1)
            continue
        # player 2 wins the fights (walking in when far); player 1 presses Start
        # every second throughout (to continue, with the same pick)
        far = a is not None and b is not None and abs(b - a) > 55
        c.buttons[1] = {'left' if b > a else 'right'} if far else \
            ({'down', 'x'} if k % 20 < 6 else ({'down'} if k % 20 < 10 else set()))
        c.buttons[0] = {'start'} if k % 60 < 3 else set()
        c.run(1)
    sys.exit('MK: the Pit not reached in 15 minutes')


if __name__ == '__main__':
    main()
