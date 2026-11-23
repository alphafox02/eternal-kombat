#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Do the MK fighters' attacks connect like Blade's, and EC fighters' on them as on Blade?

The MK fighters use Blade's moves and hit data. Plays every attack at two ranges
against a standing and a crouching opponent, and prints the damage per pair,
flagging every attack that hits Blade's way but not the MK fighter's.

    hitmatrix.py                    # MK attackers vs EC victims, EC attackers vs MK victims
    hitmatrix.py --quick            # fewer pairs

Fighters by select-grid presses (tools/lib/duelstate.py): 0 Shadow, 1 Larcen,
4 Trident, 6 Xavier, 7 Raiden, 8 Blade, 9 Jetta, 11 Ramses, 14 Blast, 20 Scorpion,
15 Sub-Zero, 16 Sonya, 17 Liu Kang, 18 Kano, 19 Johnny Cage.
"""
import argparse, os, subprocess, sys, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT

P1, P2 = 0x2E188, 0x2E330
NAMES = {0: 'Shadow', 1: 'Larcen', 4: 'Trident', 6: 'Xavier', 7: 'Raiden', 8: 'Blade', 9: 'Jetta',
         11: 'Ramses', 14: 'Blast', 20: 'Scorpion', 15: 'Sub-Zero', 16: 'Sonya', 17: 'Liu Kang', 18: 'Kano', 19: 'Johnny'}
MK = (20, 7, 19, 15, 17, 18, 16)
BLADE = 8
ATTACKS = [('X', [], 'x'), ('Y', [], 'y'), ('A', [], 'a'), ('B', [], 'b'), ('C', [], 'c'),
           ('dX', ['down'], 'x'), ('dY', ['down'], 'y'), ('dA', ['down'], 'a'), ('dB', ['down'], 'b'),
           ('dC', ['down'], 'c')]
RANGES = (45, 70)
w = lambda r, a: int.from_bytes(r[a:a + 2], 'big')
xs = lambda r, o: int.from_bytes(r[o + 0x4E:o + 0x50], 'big', signed=True)


def damage(c, state, hold, btn, gap, crouch_victim):
    c.load_state(state)
    c.run(20)
    for _ in range(300):
        r = c.prg_ram()
        if abs(xs(r, P2) - xs(r, P1)) <= gap:
            break
        c.buttons[0] = {'right' if xs(r, P2) > xs(r, P1) else 'left'}
        c.run(1)
    c.buttons[0] = set(hold)
    c.buttons[1] = {'down'} if crouch_victim else set()
    c.run(10)
    hp0 = w(c.prg_ram(), P2 + 0x76)
    c.buttons[0] = set(hold) | {btn}
    for i in range(70):
        if i == 4:
            c.buttons[0] = set(hold)
        c.run(1)
    c.buttons = [set(), set()]
    return hp0 - w(c.prg_ram(), P2 + 0x76)


def row(c, state):
    out = {}
    for name, hold, btn in ATTACKS:
        for gap in RANGES:
            for cv in (False, True):
                out[(name, gap, cv)] = damage(c, state, hold, btn, gap, cv)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--quick', action='store_true')
    a = ap.parse_args()
    ec = (0, 4) if a.quick else (0, 1, 4, 6, 9, 11)
    tmp = tempfile.mkdtemp()
    c = scd.Core(saves=os.path.join(ROOT, 'build', 'shots', 'probe-saves'))
    c.load(os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    cache = {}

    def state(p1, p2):
        if (p1, p2) not in cache:
            st = os.path.join(tmp, f'{p1}_{p2}.state')
            subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'),
                            '--p1', str(p1), '--p2', str(p2), '--out', st], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            cache[(p1, p2)] = row(c, st)
        return cache[(p1, p2)]

    keys = [(n, g, cv) for n, _, _ in ATTACKS for g in RANGES for cv in (False, True)]
    head = ' '.join(f"{n}{g}{'c' if cv else ''}" for n, g, cv in keys)
    problems = 0
    try:
        print('MK fighters attacking (vs Blade attacking the same victim):')
        for v in ec:
            base = state(BLADE, v)
            for m in MK:
                got = state(m, v)
                miss = [f"{n}@{g}{' crouched' if cv else ''}" for (n, g, cv) in keys if base[(n, g, cv)] > 0 and got[(n, g, cv)] == 0]
                problems += len(miss)
                print(f"  {NAMES[m]:9s} vs {NAMES[v]:8s}: hits {sum(1 for k in keys if got[k] > 0)}/{len(keys)}"
                      f" (Blade {sum(1 for k in keys if base[k] > 0)})" + (f"  MISSES Blade's hits: {miss}" if miss else ''))
        print('EC fighters attacking the MK fighters (vs the same attack on Blade):')
        for e in ec:
            base = state(e, BLADE)
            for m in MK:
                got = state(e, m)
                miss = [f"{n}@{g}{' crouched' if cv else ''}" for (n, g, cv) in keys if base[(n, g, cv)] > 0 and got[(n, g, cv)] == 0]
                problems += len(miss)
                print(f"  {NAMES[e]:8s} vs {NAMES[m]:9s}: hits {sum(1 for k in keys if got[k] > 0)}/{len(keys)}"
                      f" (on Blade {sum(1 for k in keys if base[k] > 0)})" + (f"  MISSES: {miss}" if miss else ''))
    finally:
        shutil.rmtree(tmp)
    print(f'{problems} attacks that hit Blade\'s way but not here')
    raise SystemExit(1 if problems else 0)


if __name__ == '__main__':
    main()
