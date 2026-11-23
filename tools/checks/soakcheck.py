#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""A long fight that must never freeze.

Kano (player 1) jumps in at the CPU's Reptile on the Pit every PERIOD frames, both healths kept
full, for FRAMES frames; the picture may not stand still for more than STILL frames (the hang
this guards: Reptile's spear on a knocked-down Kano - EC's landing code looped, its thud flooding
the sound queue; frame 1438 at period 70).
Health is kept full only while the round's clock runs (poking memory through a round's end
is not the game's own play).

    soakcheck.py [--period 70] [--frames 5400] [--disc CUE]
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT

P1, P2 = 0x2E188, 0x2E330
STILL = 150
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big')
L = lambda r, o: int.from_bytes(r[o:o + 4], 'big')


def main():
    import mkinputs
    ap = argparse.ArgumentParser()
    ap.add_argument('--period', type=int, default=70)
    ap.add_argument('--frames', type=int, default=5400)   # (within round 1: its clock is 99 s)
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        state = os.path.join(tmp, 'cpu.state')
        subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', a.disc,
                        '--p1', '18', '--cpu', '--p2', '0', '--p2-id', '26', '--stage', '1F', '--out', state],
                       check=True, capture_output=True)
        c = scd.Core(saves=os.path.join(tmp, 'saves'))
        c.load(a.disc)
        c.load_state(state)
        pf, same, worst = None, 0, 0
        for t in range(a.frames):
            r = c.prg_ram()
            obj = L(r, 0x30000 + mkinputs.CLOCK_OBJ)
            if 0 < obj < 0x80000 and W(r, obj + mkinputs.CLOCK_TIME) > 3:
                c.poke_prg(P1 + 0x76, (104).to_bytes(2, 'big'))
                c.poke_prg(P2 + 0x76, (104).to_bytes(2, 'big'))
            c.buttons[0] = {'up', 'right'} if t % a.period < 4 else set()
            c.run(1)
            fr = c.frame.tobytes()
            same = same + 1 if fr == pf else 0
            pf, worst = fr, max(worst, same)
            if same > STILL:
                break
        ok = same <= STILL
        print(f'soak (Kano jumping in every {a.period} vs the CPU Reptile): {t + 1} frames, '
              f'longest still picture {worst} -> {"ok" if ok else "FROZE"}')
        sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
