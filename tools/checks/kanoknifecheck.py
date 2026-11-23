#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check Kano's held-Block knife input on either player side.

Uses a fresh duel made from the built disc's menu.state, or --state. Holding
Z alone must not throw; Z held through back, forward must throw and hit.

    kanoknifecheck.py [--as-p2] [--state STATE] [--disc CUE]
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--as-p2', action='store_true')
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    ap.add_argument('--state', help='duel state created for this disc')
    a = ap.parse_args()
    with tempfile.TemporaryDirectory(prefix='ek-kano-knife-') as tmp:
        state = a.state or os.path.join(tmp, 'duel.state')
        p1, p2 = (0, 18) if a.as_p2 else (18, 0)
        if not a.state:
            subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', a.disc,
                            '--p1', str(p1), '--p2', str(p2), '--stage', '11', '--out', state], check=True)
        c = scd.Core(saves=os.path.join(tmp, 'saves'))
        c.load(a.disc)
        c.load_state(state)
        c.run(80)
        actor, victim, port = (P2, P1, 1) if a.as_p2 else (P1, P2, 0)
        before = W(c.prg_ram(), victim + 0x76)
        back, forward = ('right', 'left') if a.as_p2 else ('left', 'right')
        sequence = [(set(), 20), ({'z'}, 12), ({'z', back}, 6), ({'z'}, 3),
                    ({'z', forward}, 6), ({'z'}, 110)]
        seen = early = False
        for step, (held, n) in enumerate(sequence):
            c.buttons[port] = held
            for _ in range(n):
                c.run(1)
                knife = W(c.prg_ram(), actor + 0xBE) & 0x7FFF == 0x34
                seen |= knife
                early |= knife and step < 4
        after = W(c.prg_ram(), victim + 0x76)
        ok = seen and not early and after < before
        print(f'held-Block knife: started {seen}, premature {early}, health {before} -> {after} '
              f'-> {"ok" if ok else "FAILED"}')
        if not ok:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
