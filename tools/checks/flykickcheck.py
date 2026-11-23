#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Liu Kang's flying kick (forward, forward + HK) gets going as MK's.

MK CD (live, tools/lib/mkmoves.py's script) leaves the floor 4-5 frames after HK and holds the kick
~9-10 frames after it, travelling all the way (mkinputs.flykick_plan). Ours stood 12 frames in place
first (slow to get going). From a 2-player duel, Liu Kang (player 1) against Shadow: after HK he
  - travels (x up 4+ px past where he stood) by HK + MOVING frames;
  - shows the kick (his dash's strike frame, xx:62) by HK + KICK frames;
  - flies on (x up 60+ px) and lands.

    flykickcheck.py [--disc CUE]     (run after play.py test has made the disc's build/states/menu.state)
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT

P1 = 0x2E188
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big', signed=True)
LIU_KANG, SHADOW = 17, 0
DASH = 0x35                                  # his flying kick's move (Blade's dash)
MOVING, KICK = 6, 10                         # frames after HK (MK: 4-5 off the floor, the kick at ~9-10)
INPUT = [({'right'}, 4), (set(), 3), ({'right'}, 4), ({'b'}, 4), (set(), 70)]   # HK (EC's B) at frame 12


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    a = ap.parse_args()
    with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, 'build')) as tmp:
        st = os.path.join(tmp, 'duel.state')
        subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', a.disc,
                        '--p1', str(LIU_KANG), '--p2', str(SHADOW), '--out', st], check=True, capture_output=True)
        c = scd.Core()
        c.load(a.disc)
        c.load_state(st)
    c.run(30)
    log, f, hk = [], 0, None
    for held, n in INPUT:
        for _ in range(n):
            c.buttons[0] = set(held)
            c.run(1)
            f += 1
            if hk is None and 'b' in held:
                hk = f
            r = c.prg_ram()
            log.append((f, W(r, P1 + 0xBE) & 0x7FFF, int.from_bytes(r[P1 + 0x1A:P1 + 0x1C], 'big'), W(r, P1 + 0x4E)))
    c.buttons[0] = set()
    dash = [(f, fr, x) for f, mv, fr, x in log if mv == DASH]
    bad = []
    if not dash:
        bad.append('no flying kick (move $35)')
    else:
        x0 = next(x for f, mv, fr, x in log if f == dash[0][0] - 1)
        moving = next((f for f, fr, x in dash if x - x0 >= 4), None)
        kick = next((f for f, fr, x in dash if fr & 0xFF == 0x62), None)
        far = max(x for f, fr, x in dash) - x0
        print(f'HK at frame {hk}; the kick move from {dash[0][0]}, travelling from {moving}, '
              f'the kick shown from {kick}; {far} px')
        if moving is None or moving - hk > MOVING:
            bad.append(f'travelling {None if moving is None else moving - hk} frames after HK (MK: 4-5; at most {MOVING})')
        if kick is None or kick - hk > KICK:
            bad.append(f'the kick {None if kick is None else kick - hk} frames after HK (MK: ~9-10; at most {KICK})')
        if far < 60:
            bad.append(f'flew only {far} px')
    print('flykickcheck:', 'FAIL ' + '; '.join(bad) if bad else 'ok')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
