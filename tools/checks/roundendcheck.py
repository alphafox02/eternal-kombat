#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Does every knockout lead to the next round?

Player 1 walks up to player 2 (both human-controlled, so player 2 stands), player 2's health is set
to 1 and player 1 jabs - at N different moments (each one a frame-count apart, so EC's random
choices - the winner's victory dance, the knockdown - differ). After FRAMES frames player 2's health
must be full again (round 2 started).

    roundendcheck.py [--p1 18] [--p2 18] [--tries 8] [--frames 1400]
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT

P1, P2 = 0x2E188, 0x2E330
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big', signed=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--p1', type=int, default=18, help='right presses on the select grid (18 Kano)')
    ap.add_argument('--p2', type=int, default=18)
    ap.add_argument('--tries', type=int, default=8)
    ap.add_argument('--frames', type=int, default=1400)
    ap.add_argument('--stage', default='11', help='stage mode (hex): 1F the Pit')
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        st = os.path.join(tmp, 'duel.state')
        subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--p1', str(a.p1),
                        '--p2', str(a.p2), '--stage', a.stage, '--out', st], check=True, capture_output=True)
        c = scd.Core(saves=os.path.join(tmp, 'saves'))
        c.load(os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
        c.load_state(st)
        c.run(30)
        c.buttons[0] = {'right'}
        for _ in range(300):
            c.run(1)
            r = c.prg_ram()
            if abs(W(r, P2 + 0x4E) - W(r, P1 + 0x4E)) < 75:
                break
        c.buttons[0] = set()
        snap = c.snapshot()
        bad = 0
        for k in range(a.tries):
            c.restore(snap)
            c.run(3 * k + 1)
            c.poke_prg(P2 + 0x76, (1).to_bytes(2, 'big'))
            for t in range(a.frames):
                c.buttons[0] = {'y'} if t < 4 else set()
                c.run(1)
            r = c.prg_ram()
            ok = W(r, P2 + 0x76) > 0
            bad += not ok
            print(f'  try {k}: {"next round" if ok else "STUCK (no round 2)"}')
        print(f'round ends (P1 grid {a.p1} KOs P2 grid {a.p2}): {a.tries - bad} of {a.tries} reach round 2 -> '
              f'{"ok" if not bad else "FAIL"}')
        sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
