#!/usr/bin/env python3
"""Make states/duel.state: a real 2-player Duel (both fighters human-controlled,
so player 2 stands still with no input), saved the moment player 1 actually
responds (holding forward moves him). Used by ecprobe.py and the move tests.

Player 2 has to press start on the select screen *before* player 1 picks;
otherwise "Choose your opponent" makes player 2 a CPU fighter.

    duelstate.py [--disc build/.../Eternal Kombat.cue]
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scd
from inputs import ROOT

P1 = 0x2E188


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'states', 'duel.state'))
    ap.add_argument("--p2", type=int, default=14,
                    help="player 2's fighter: right presses (0 Shadow, 1 Larcen, 7 Raiden, 8 Blade, 14 Scorpion, 15 Sub-Zero, 16 Johnny Cage)")
    ap.add_argument('--p1', type=int, default=14,
                    help="player 1's fighter: right presses on the select grid (14: Scorpion, 7: Raiden, 8: Blade)")
    ap.add_argument('--stage', type=lambda v: int(v, 16),
                    help="stage mode to fight on (hex, $11-$22; 13 = Blast's stage, now the Pit): "
                         "written over GAME.CO's stage-by-fighter table ($C28) in RAM once both picked")
    a = ap.parse_args()
    c = scd.Core(saves=os.path.join(ROOT, 'shots', 'duel-saves'))
    c.load(a.disc)
    c.load_state(os.path.join(ROOT, 'states', 'menu.state'))
    c.press(['start']); c.run(240)                     # title -> main menu
    c.press(['down']); c.run(20)                       # Enter Duel
    c.press(['start']); c.run(240)
    c.press(['start'], port=1); c.run(40)              # player 2 joins first (cursor on slot 0)
    for _ in range(a.p1):                              # player 1
        c.press(['right']); c.run(20)
    c.press(['start']); c.run(40)
    for _ in range(a.p2):                              # player 2 picks with their own pad
        c.press(['right'], port=1); c.run(20)
    c.press(['start'], port=1)
    if a.stage:
        c.run(2)
        c.poke_prg(0x14C28, bytes([0, a.stage]) * 25)
    c.run(300)
    c.press(['start']); c.run(400)
    c.press(['start'])
    tmp = a.out + '.tmp'
    W = lambda r: int.from_bytes(r[P1 + 0x4E:P1 + 0x50], 'big', signed=True)
    for t in range(0, 3000, 10):
        c.run(10)
        c.save_state(tmp)
        c.run(12)                                      # what happens on its own (intro walk-in)
        x_idle = W(c.prg_ram())
        c.load_state(tmp)
        c.buttons[0] = {'right'}
        c.run(12)
        c.buttons[0] = set()
        x_walk = W(c.prg_ram())
        c.load_state(tmp)
        if x_walk - x_idle >= 4:                       # the input itself moved him
            c.save_state(a.out)
            os.remove(tmp)
            print(f'duel live after {t} frames; saved {os.path.relpath(a.out, ROOT)}')
            return
    os.remove(tmp)
    raise SystemExit('player 1 never responded')


if __name__ == '__main__':
    main()
