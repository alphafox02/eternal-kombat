#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""An MK fighter's sweep (crouch, then down + C) drops an EC fighter where he stands.

MK's sweep takes the feet out and he falls where he stands (mkinputs.r_swept_by); EC's sweep launches
him ~140 px back (Sonya's flung EC fighters). From a 2-player duel, the MK fighter (player 1) walks up
to Larcen and sweeps: Larcen's knockdown ($1C) carries him at most MAX_SLIDE px (MK's drop: ~9 px; EC's
launch ~135). EC takes the launch from the victim's own knockdown header (PLYR $18984: $C6/$CA), so it
is code (mkinputs.r_swept_by); Sonya's is a subroutine in a dead script body of her module (her block
had 4 bytes left: mkinputs.GEN_DEAD).

    sweepcheck.py [WHO_PRESSES ...] [--disc CUE]     (default: every MK fighter with a sweep)
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT

P1, P2 = 0x2E188, 0x2E330
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big', signed=True)
LARCEN = 1
KNOCKDOWN = 0x1C
MAX_SLIDE = 40
FIGHTERS = {20: 'Scorpion', 15: 'Sub-Zero', 7: 'Raiden', 16: 'Sonya', 17: 'Liu Kang', 18: 'Kano', 19: 'Johnny Cage'}
CHECKED = (20, 15, 7, 16, 17, 18, 19)


def slide(disc, who, tmp):
    st = os.path.join(tmp, f'sweep_{who}.state')
    subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', disc,
                    '--p1', str(who), '--p2', str(LARCEN), '--out', st], check=True, capture_output=True)
    c = scd.Core()
    c.load(disc)
    c.load_state(st)
    c.run(40)
    for _ in range(400):                                 # up close
        r = c.prg_ram()
        if abs(W(r, P2 + 0x4E) - W(r, P1 + 0x4E)) < 60:
            break
        c.buttons[0] = {'right'}
        c.run(1)
    for held, n in (({'down'}, 8), ({'down', 'c'}, 4), ({'down'}, 10)):
        c.buttons[0] = held
        c.run(n)
    c.buttons[0] = set()
    x0 = None
    far = 0
    for _ in range(150):
        c.run(1)
        r = c.prg_ram()
        if W(r, P2 + 0xBE) & 0x7FFF == KNOCKDOWN:
            x = W(r, P2 + 0x4E)
            x0 = x if x0 is None else x0
            far = max(far, abs(x - x0))
    return x0, far


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('who', nargs='*', type=int, default=list(CHECKED))
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    a = ap.parse_args()
    bad = []
    with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, 'build')) as tmp:
        for who in a.who:
            x0, far = slide(a.disc, who, tmp)
            ok = x0 is not None and far <= MAX_SLIDE
            print(f'{FIGHTERS.get(who, who):12s} ' + ('Larcen never knocked down' if x0 is None else
                  f'Larcen slid {far:3d} px in his knockdown') + ('' if ok else '  WRONG'))
            if not ok:
                bad.append(FIGHTERS.get(who, str(who)))
    print('sweepcheck:', 'FAIL ' + ', '.join(bad) if bad else 'ok')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
