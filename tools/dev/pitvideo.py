#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Record the Pit finisher (with sound).

On the Pit (tools/lib/duelstate.py --p1 20 --p2 0 --stage 1F --out
build/states/duel_pit.state), the deciding round, Scorpion jabs Shadow to FINISH
HIM, waits, then uppercuts her (down + Y): she flies up and falls past the bridge
into the pit (ecstage.PIT_FALL).

    pitvideo.py [--out build/shots/scorpion_pit_fatality.mp4]
"""
import argparse, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
from scd import Core
from inputs import ROOT
from finishvideo import Rec, w, x, P1, P2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(ROOT, 'build', 'shots', 'scorpion_pit_fatality.mp4'))
    ap.add_argument('--state', default=os.path.join(ROOT, 'build', 'states', 'duel_pit.state'))
    a = ap.parse_args()
    c = Core(audio=True, saves=os.path.join(ROOT, 'build', 'shots', 'record-saves'))
    c.load(os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    c.load_state(a.state)
    c.run(30)
    c.poke_prg(0x31D26, (1).to_bytes(2, 'big'))       # one round each: this one decides it
    c.poke_prg(0x31D28, (1).to_bytes(2, 'big'))
    c.poke_prg(P2 + 0x76, (12).to_bytes(2, 'big'))
    c.audio.clear()
    r = Rec(c, a.out)
    r.run(40)
    for _ in range(300):
        m = r.ram()
        if x(m, P2) - x(m, P1) <= 50:
            break
        r.run(1, ['right'])
    for _ in range(20):                               # jabs until FINISH HIM
        for _ in range(100):                          # each pushes her back: step in
            m = r.ram()
            if x(m, P2) - x(m, P1) <= 56:
                break
            r.run(1, ['right'])
        r.run(4, ['x'])
        for _ in range(90):                           # (the daze can start ~45 frames after the jab)
            r.run(1)
            if w(r.ram(), P2 + 0xBE) == 0x1F:
                break
        if w(r.ram(), P2 + 0xBE) == 0x1F:
            break
    assert w(r.ram(), P2 + 0xBE) == 0x1F, 'no FINISH HIM'
    r.run(50)
    for _ in range(200):                              # step in: the jabs pushed her back
        m = r.ram()
        if x(m, P2) - x(m, P1) <= 56:
            break
        r.run(1, ['right'])
    r.run(6)
    # EC crouches on a fresh press of down from idle (one held through his
    # last jab does nothing): wait until he's idle, then press it, again if
    # need be, until he's really crouching - then the uppercut
    for _ in range(20):
        for _ in range(60):
            if w(r.ram(), P1 + 0xBE) == 0:
                break
            r.run(1)
        r.run(2)
        for _ in range(10):
            r.run(1, ['down'])
            if w(r.ram(), P1 + 0xBE) & 0x7FFF == 9:   # crouching
                break
        if w(r.ram(), P1 + 0xBE) & 0x7FFF == 9:
            break
    assert w(r.ram(), P1 + 0xBE) & 0x7FFF == 9, 'he never crouched'
    r.run(6, ['down'])
    print('winner health at the uppercut:', w(r.ram(), P1 + 0x76))
    for held, n in ((['down', 'y'], 4), (['down'], 6)):
        r.run(n, held)
    fell = False
    for _ in range(900):
        r.run(1)
        m = r.ram()
        fell = fell or int.from_bytes(m[P2 + 0x52:P2 + 0x54], 'big', signed=True) > 240
        if m[0x30AB7] & 3 == 3:
            break
    assert fell, 'she did not fall into the pit'
    r.run(420)                                       # the announcer (an MK winner)
    r.close()
    print(f'{r.frames / c.fps:.1f}s -> {os.path.relpath(a.out, ROOT)}')


if __name__ == '__main__':
    main()
