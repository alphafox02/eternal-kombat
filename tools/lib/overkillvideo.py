#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Record EC's Chicago Theater stage Overkill (the drive-by) on Scorpion.

From build/states/duel_shadow.state, Scorpion vs Shadow on the Chicago Theater
(stage mode $1B: tools/lib/duelstate.py --p2 0 --stage 1B): the deciding round,
Scorpion low on health in the Overkill window (x 560-590: the stage's .OC
checks $223-$279 in its handler), Shadow on his right; she punches.

    overkillvideo.py [--out build/shots/scorpion_overkill.mp4]
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scd import Core
from inputs import ROOT
from finishvideo import Rec

P1, P2 = 0x2E188, 0x2E330
SPOT = 575


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(ROOT, 'build', 'shots', 'scorpion_overkill.mp4'))
    a = ap.parse_args()
    c = Core(audio=True, saves=os.path.join(ROOT, 'build', 'shots', 'record-saves'))
    c.load(os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    c.load_state(os.path.join(ROOT, 'build', 'states', 'duel_shadow.state'))
    c.run(30)
    c.poke_prg(0x31D26, (1).to_bytes(2, 'big'))       # one round each: this one decides it
    c.poke_prg(0x31D28, (1).to_bytes(2, 'big'))
    for o, v in ((P1, SPOT), (P2, SPOT + 50)):
        for f in (0x4E, 0xB2):
            c.poke_prg(o + f, v.to_bytes(2, 'big'))
    c.run(40)
    c.poke_prg(P1 + 0x76, (6).to_bytes(2, 'big'))     # nearly beaten
    c.poke_prg(P1 + 0x190, (40).to_bytes(2, 'big'))   # (the Overkill also wants 10+ damage taken)
    c.audio.clear()
    r = Rec(c, a.out)
    r.run(60)
    c.buttons[1] = {'y'}
    r.run(4)
    c.buttons[1] = set()
    for _ in range(1800):                             # the drive-by plays; the round ends after it
        r.run(1)
        if r.ram()[0x30AB7] & 3 == 3:
            break
    r.run(240)
    r.close()
    print(f'{r.frames / c.fps:.1f}s -> {os.path.relpath(a.out, ROOT)}')


if __name__ == '__main__':
    main()
