#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Does a fight run without freezing? Two kinds:

    fightcheck.py cpu GRID [--secs 60]
        1 player vs the CPU playing GRID (select-grid presses): from the main menu,
        Enter Duel, player 1 takes Shadow, the CPU the fighter. The CPU's own choice of
        moves (specials included) runs for --secs; player 1 idles.
    fightcheck.py duel P1 P2 [--secs 20]
        a 2-player duel (tools/lib/duelstate.py), player 1 walking in, punching, his
        specials' taps; player 2 jabbing now and then (a mirror match: P1 == P2).

A freeze = the same picture for 2 s while the fight is on (both alive). Exits 1 on
a freeze. Prints the longest still picture and both fighters' health.
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT

P1, P2 = 0x2E188, 0x2E330
W = lambda r, a: int.from_bytes(r[a:a + 2], 'big')
X = lambda r, o: int.from_bytes(r[o + 0x4E:o + 0x50], 'big', signed=True)
CUE = os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue')
FREEZE = 120


def watch(c, frames, pad=lambda f: None):
    prev, same, worst = None, 0, 0
    for f in range(frames):
        pad(f)
        c.run(1)
        r = c.prg_ram()
        fr = c.frame.tobytes()
        live = W(r, P1 + 0x76) > 0 and W(r, P2 + 0x76) > 0
        same = same + 1 if fr == prev and live else 0
        prev = fr
        worst = max(worst, same)
    return worst


def cpu(grid, secs):
    c = scd.Core(saves=os.path.join(ROOT, 'build', 'shots', 'duel-saves'))
    c.load(CUE)
    c.load_state(os.path.join(ROOT, 'build', 'states', 'menu.state'))
    c.press(['start']); c.run(240); c.press(['down']); c.run(20); c.press(['start']); c.run(240)
    c.press(['start']); c.run(60)                       # player 1: Shadow (the cursor's start)
    for _ in range(grid):
        c.press(['right']); c.run(20)
    c.press(['start']); c.run(120)                      # the CPU's fighter
    for _ in range(4):                                  # versus screen, stage card, intro
        c.press(['start']); c.run(60)
    worst = watch(c, 60 * secs)
    r = c.prg_ram()
    return worst, r[P2 + 0x4D], W(r, P1 + 0x76), W(r, P2 + 0x76)


SEQ = [(['right'], 30), (['x'], 4), ([], 20), (['right'], 3), ([], 2), (['right'], 3), (['y'], 4), ([], 60),
       (['left'], 3), ([], 2), (['right'], 3), (['x'], 4), ([], 60), (['down'], 3), ([], 2), (['right'], 3),
       (['x'], 4), ([], 60), (['z'], 3), (['z', 'left'], 3), (['z'], 2), (['z', 'right'], 3), ([], 60),
       (['down'], 8), (['down', 'y'], 4), ([], 60)]


def duel(p1, p2, secs):
    st = os.path.join(tempfile.mkdtemp(), 'duel.state')
    subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'),
                    '--p1', str(p1), '--p2', str(p2), '--out', st], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    c = scd.Core(saves=os.path.join(ROOT, 'build', 'shots', 'record-saves'))
    c.load(CUE)
    c.load_state(st)
    c.run(20)
    plan = []
    while sum(n for _, n in plan) < 60 * secs:
        plan += SEQ
    flat = [h for held, n in plan for h in [held] * n]

    def pad(f):
        c.buttons[0] = set(flat[f]) if f < len(flat) else set()
        c.buttons[1] = {'x'} if f % 30 == 0 else set()
    worst = watch(c, 60 * secs, pad)
    r = c.prg_ram()
    return worst, r[P2 + 0x4D], W(r, P1 + 0x76), W(r, P2 + 0x76)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('kind', choices=('cpu', 'duel'))
    ap.add_argument('grid', type=int, nargs='+')
    ap.add_argument('--secs', type=int)
    a = ap.parse_args()
    if a.kind == 'cpu':
        worst, pid, h1, h2 = cpu(a.grid[0], a.secs or 60)
    else:
        p1, p2 = (a.grid + a.grid)[:2]
        worst, pid, h1, h2 = duel(p1, p2, a.secs or 20)
    ok = worst < FREEZE
    print(f'{a.kind} {" ".join(map(str, a.grid))}: player 2 id {pid}, health {h1} / {h2}, '
          f'longest still picture {worst} frames -> {"ok" if ok else "FROZE"}')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
