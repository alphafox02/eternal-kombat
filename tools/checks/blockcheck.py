#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Does Z block for an MK fighter, as MK's Block?

It didn't: the pad's 'away' was added after EC read it (traced; mkinputs.emit_zblock). Player 1 (an MK
fighter, human) stands next to Shadow (player 2) and holds Z while she punches (Y), kicks (B); and
down + Z while she kicks low (down + A). Each must cost him no health (a block: EC's state 7 standing,
$0C crouching). Control: down alone against the low kick is hit.

    blockcheck.py [--fighters sonya,kano,scorpion]
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT

P1, P2 = 0x2E188, 0x2E330
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big', signed=True)
GRID = {'scorpion': 20, 'raiden': 7, 'subzero': 15, 'sonya': 16, 'liukang': 17, 'kano': 18, 'johnny': 19}
CASES = (('Z vs a punch', {'z'}, {'y'}, False, True), ('Z vs a kick', {'z'}, {'b'}, False, True),
         ('down+Z vs a low kick', {'down', 'z'}, {'a'}, True, True), ('down vs a low kick', {'down'}, {'a'}, True, False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fighters', default='sonya,kano,scorpion')
    a = ap.parse_args()
    cue = os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue')
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        for who in a.fighters.split(','):
            st = os.path.join(tmp, f'{who}.state')
            subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--p1', str(GRID[who]),
                            '--p2', '0', '--stage', '11', '--out', st], check=True, capture_output=True)
            c = scd.Core(saves=os.path.join(tmp, 'saves'))
            c.load(cue)
            c.load_state(st)
            c.run(30)
            c.buttons[1] = {'left'}                       # she walks up to him
            for _ in range(300):
                c.run(1)
                r = c.prg_ram()
                if abs(W(r, P2 + 0x4E) - W(r, P1 + 0x4E)) < 55:
                    break
            c.buttons[1] = set()
            c.run(20)
            snap = c.snapshot()
            for name, hold, att, low, want_block in CASES:
                c.restore(snap)
                h0 = W(c.prg_ram(), P1 + 0x76)
                blocked = False
                at = 15 if low else 5            # (low: once he is down - Kano, Scorpion take 7 frames)
                for t in range(60):
                    c.buttons[0] = hold
                    c.buttons[1] = (att | ({'down'} if low else set())) if at <= t < at + 4 else ({'down'} if low else set())
                    c.run(1)
                    blocked |= W(c.prg_ram(), P1 + 0xBE) & 0x7FFF in (0x07, 0x0C)
                lost = h0 - W(c.prg_ram(), P1 + 0x76)
                ok = (lost == 0 and blocked) if want_block else lost > 0
                bad += not ok
                print(f'  {who:9s} {name:22s} -{lost} hp, block state {"yes" if blocked else "no"} -> {"ok" if ok else "FAIL"}')
    print(f'block: {"ok" if not bad else f"{bad} FAIL"}')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
