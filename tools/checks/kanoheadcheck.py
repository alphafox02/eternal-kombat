#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check Kano's close punches in a real duel on either player side.

Both punches must show Kano's disc-derived headbutt strike and damage Shadow.

    kanoheadcheck.py [--as-p2] [--state STATE] [--disc CUE]     (after play.py test has made build/states/menu.state)
"""
import argparse
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
from inputs import ROOT
import scd

P1, P2 = 0x2E188, 0x2E330
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big')
X = lambda r, o: int.from_bytes(r[o + 0x4E:o + 0x50], 'big', signed=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--as-p2', action='store_true')
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    ap.add_argument('--state', help='existing duel state for this disc (otherwise create one)')
    a = ap.parse_args()
    with tempfile.TemporaryDirectory(prefix='ek-kano-head-') as tmp:
        state = a.state or os.path.join(tmp, 'duel.state')
        p1, p2 = (0, 18) if a.as_p2 else (18, 0)
        if not a.state:
            subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'),
                            '--disc', a.disc, '--p1', str(p1), '--p2', str(p2), '--out', state], check=True)
        c = scd.Core(saves=os.path.join(tmp, 'saves'))
        c.load(a.disc)
        attacker, victim, port = (P2, P1, 1) if a.as_p2 else (P1, P2, 0)
        for button, move, strike in (('x', 0x20, 0xE71C), ('y', 0x21, 0xE51D)):
            c.load_state(state)
            c.run(40)
            for _ in range(180):
                r = c.prg_ram()
                dx = X(r, victim) - X(r, attacker)
                if abs(dx) < 40:
                    break
                c.buttons[port] = {'right' if dx > 0 else 'left'}
                c.run(1)
            c.buttons[port] = set()
            c.run(20)
            before = W(c.prg_ram(), victim + 0x76)
            seen = False
            for frame in range(100):
                c.buttons[port] = {button} if frame < 4 else set()
                c.run(1)
                r = c.prg_ram()
                seen |= W(r, attacker + 0xBE) & 0x7FFF == move and W(r, attacker + 0x1A) == strike
            after = W(c.prg_ram(), victim + 0x76)
            if not seen or after >= before:
                raise SystemExit(f'{button}: FAILED (headbutt frame {seen}, health {before} -> {after})')
            print(f'{button}: headbutt seen, health {before} -> {after}')
    print('Kano headbutts -> ok')


if __name__ == '__main__':
    main()
