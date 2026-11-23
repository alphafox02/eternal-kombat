#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Sonya's specials from the pad, as the player presses them.

(mkinputs.GENERIC_MOVES[17], r_generic's throw rewrite.) Every MK fighter's toward + HP reads as EC's
back + HP (EC's throw), and that made-up back finished her square wave (forward, back + HP) whenever
forward was held: she flew instead of punching. From a 2-player duel, Sonya (player 1) against Shadow:
  - forward held, HP: a high punch (move 2), not the square wave ($35);
  - forward, back, HP and forward, back + HP: the square wave;
  - back, HP and back held + HP: the energy rings ($34);
  - next to Shadow, forward + HP: the throw ($0D).

    sonyainputcheck.py [--disc CUE]     (run after play.py test has made the disc's build/states/menu.state)
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT

P1, P2 = 0x2E188, 0x2E330
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big', signed=True)
PUNCH, SQUARE, RINGS, THROW = 0x02, 0x35, 0x34, 0x0D
CASES = [('forward held, HP', [({'right'}, 20), ({'right', 'y'}, 3), ({'right'}, 20)], PUNCH, False),
         ('forward, back, HP', [({'right'}, 3), (set(), 2), ({'left'}, 3), ({'y'}, 3)], SQUARE, False),
         ('forward, back + HP', [({'right'}, 3), (set(), 2), ({'left', 'y'}, 3)], SQUARE, False),
         ('back, HP', [({'left'}, 3), (set(), 3), ({'y'}, 3)], RINGS, False),
         ('back held + HP', [({'left'}, 20), ({'left', 'y'}, 3)], RINGS, False),
         ('close: forward + HP', [({'right'}, 4), ({'right', 'y'}, 3)], THROW, True)]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    a = ap.parse_args()
    bad = []
    with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, 'build')) as tmp:
        st = os.path.join(tmp, 'duel.state')
        subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', a.disc,
                        '--p1', '16', '--p2', '0', '--out', st], check=True, capture_output=True)
        for name, seq, want, close in CASES:
            c = scd.Core()
            c.load(a.disc)
            c.load_state(st)
            c.run(40)
            for _ in range(400 if close else 0):
                r = c.prg_ram()
                if abs(W(r, P2 + 0x4E) - W(r, P1 + 0x4E)) < 50:
                    break
                c.buttons[0] = {'right'}
                c.run(1)
            moves = []
            for held, n in seq + [(set(), 60)]:
                c.buttons[0] = set(held)
                for _ in range(n):
                    c.run(1)
                    m = W(c.prg_ram(), P1 + 0xBE) & 0x7FFF
                    if not moves or moves[-1] != m:
                        moves.append(m)
            got = [m for m in moves if m in (PUNCH, SQUARE, RINGS, THROW)]
            ok = bool(got) and got[0] == want
            print(f'{name:22s} moves {" ".join(f"{m:X}" for m in moves):24s} want {want:X}: {"ok" if ok else "WRONG"}')
            if not ok:
                bad.append(name)
    print('sonyainputcheck:', 'FAIL ' + ', '.join(bad) if bad else 'ok')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
