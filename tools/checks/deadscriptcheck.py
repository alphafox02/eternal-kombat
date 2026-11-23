#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The bodies of Blade's move scripts that an MK fighter's block replaces are never played.

The build keeps code there (mkinputs.GEN_DEAD: room_put's fourth room). PLYR $1A278 builds the move
table from the chain of Blade's scripts at fight start, reading only each one's slot and step count; the
block puts its own scripts in those slots every frame. If a fighter ever ran one of those Blade scripts,
he'd play the code there as animation steps.

2-player duels of MK fighters against each other (each MK fighter but Scorpion - whose module keeps
Blade's own - on both sides), FRAMES frames of random pad input each: a fighter's running script ($AE)
is never inside one of those bodies.

    deadscriptcheck.py [--frames N] [--disc CUE]     (after play.py test has made build/states/menu.state)
"""
import argparse, os, random, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd, mkinputs, mkscripts
from inputs import ROOT

P = ((0x2E188, 0x1B000), (0x2E330, 0x21800))        # (fighter object, his module's load address)
L = lambda r, o: int.from_bytes(r[o:o + 4], 'big')
GRID = {'mk_moves_raiden': 7, 'mk_moves_subzero': 15, 'mk_moves_sonya': 16, 'mk_moves_liukang': 17,
        'mk_moves_kano': 18, 'mk_moves_johnny': 19}
PAIRS = [(16, 18), (18, 16), (15, 19), (19, 15), (17, 7), (7, 17)]
BUTTONS = ['up', 'down', 'left', 'right', 'a', 'b', 'c', 'x', 'y', 'z']


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--frames', type=int, default=3000)
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    a = ap.parse_args()
    bla = open(os.path.join(ROOT, 'extracted', 'ec_us', 'BLA.CO'), 'rb').read()
    dead = {}
    for d, g in GRID.items():
        slots = {int.from_bytes(sc[0:2], 'big') for sc in mkscripts.build(bla, d)[0].values()}
        dead[g] = mkinputs.dead_bodies(bla, slots)
    bad = []
    with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, 'build')) as tmp:
        for p1, p2 in PAIRS:
            st = os.path.join(tmp, f'{p1}_{p2}.state')
            subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', a.disc,
                            '--p1', str(p1), '--p2', str(p2), '--out', st], check=True, capture_output=True)
            c = scd.Core()
            c.load(a.disc)
            c.load_state(st)
            rnd = random.Random(p1 * 100 + p2)
            inside, seen = [], 0
            for f in range(a.frames):
                if f % 6 == 0:
                    for port in (0, 1):
                        c.buttons[port] = set(rnd.sample(BUTTONS, rnd.choice((0, 1, 1, 2, 2, 3))))
                c.run(1)
                r = c.prg_ram()
                for side, ((obj, base), grid) in enumerate(zip(P, (p1, p2))):
                    v = L(r, obj + 0xAE) - base
                    if 0x3FA0 <= v < 0x51A4:
                        seen += 1
                    if any(s - 4 <= v < e for s, e in dead[grid]):
                        inside.append((f, side + 1, hex(v)))
            print(f'grid {p1} vs {p2}: a Blade script running on {seen} fighter-frames; '
                  f'in a replaced one\'s body: {len(inside)}' + (f' (first {inside[0]})' if inside else ''))
            if inside or not seen:
                bad.append(f'{p1} vs {p2}')
    print('deadscriptcheck:', 'FAIL ' + ', '.join(bad) if bad else 'ok')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
