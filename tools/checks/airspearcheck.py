#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Scorpion's spear on a jumping fighter must not hang the game.

Kano (an MK fighter), then Riptide (EC's), jumps in at 10 timings while Scorpion (player 1) throws;
whenever the spear meets him in the air, EC's knockdown takes him (mkinputs: r_hit's +96, r_drag
skips him; the rope's pin skips him, sr_h3). It hung twice: the pull dazed him mid-fall, EC's landing
code looped in his task and its thud ($3EE) flooded the sound queue (sub CPU $472C0) until the
picture stopped; and the pin held Riptide in her airborne reel for good, Scorpion on his pull, the
picture moving (blood) but neither able to move. Each run: the queue may not grow by more than QUEUE
bytes, nor the picture stand still for more than STILL frames, and by FREE frames both are out of the
throw and the hit.

    airspearcheck.py [--disc CUE]
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT

P1, P2 = 0x2E188, 0x2E330
QUEUE_END = 0x472C0           # the sound queue's write pointer (SUB $47F7E's command queue)
QUEUE, STILL = 200, 150
FREE = 500                    # frames from the press: both fighters out of the throw and the hit
JUMPERS = (('Kano', '18'), ('Riptide', '10'))   # (select-grid presses)
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big', signed=True)
L = lambda r, o: int.from_bytes(r[o:o + 4], 'big')
SPEAR = (({'left'}, 3), (set(), 2), ({'left'}, 3), ({'x'}, 4))   # back, back + LP


def jumps(disc, tmp, who, grid):
    bad = 0
    st = os.path.join(tmp, who + '.state')
    subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', disc,
                    '--p1', '20', '--p2', grid, '--out', st], check=True, capture_output=True)
    c = scd.Core(saves=os.path.join(tmp, 'saves-' + who))
    c.load(disc)
    c.load_state(st)
    c.run(30)
    for _ in range(300):
        if abs(W(c.prg_ram(), P2 + 0x4E) - W(c.prg_ram(), P1 + 0x4E)) < 120:
            break
        c.buttons[0] = {'right'}
        c.run(1)
    c.buttons[0] = set()
    c.run(10)
    snap = c.snapshot()
    for off in range(0, 30, 3):
        c.restore(snap)
        q0, grew, pf, same, worst, air = L(c.prg_ram(), QUEUE_END), 0, None, 0, 0, False
        for t in range(FREE):
            acc, held = 0, set()
            for h, n in SPEAR:
                if acc <= t < acc + n:
                    held = h
                acc += n
            c.buttons[0] = held
            c.buttons[1] = {'up', 'left'} if off <= t < off + 4 else set()
            c.run(1)
            r = c.prg_ram()
            grew = max(grew, L(r, QUEUE_END) - q0)
            air |= 0x1A <= W(r, P2 + 0xBE) & 0x7FFF <= 0x1D and W(r, P2 + 0x52) < W(r, 0x31496) - 4
            fr = c.frame.tobytes()
            same = same + 1 if fr == pf else 0
            pf, worst = fr, max(worst, same)
        st1, st2 = W(r, P1 + 0xBE) & 0x7FFF, W(r, P2 + 0xBE) & 0x7FFF
        free = st1 != 0x34 and not (st2 == 0x0E or 0x1A <= st2 <= 0x1D)
        ok = grew <= QUEUE and worst <= STILL and free
        bad += not ok
        print(f'  {who} jumps at {off:2d}: hit in the air {air}, sound queue +{grew}, longest still picture {worst},'
              f' {"both free" if free else f"stuck (Scorpion ${st1:02X}, {who} ${st2:02X})"}'
              f' -> {"ok" if ok else "HUNG"}')
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    a = ap.parse_args()
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        for who, grid in JUMPERS:
            bad += jumps(a.disc, tmp, who, grid)
    print(f'spear on a jumper: {"ok" if not bad else f"{bad} HUNG"}')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
