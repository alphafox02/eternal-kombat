#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""MK fighters' back + high kick is the roundhouse and back + low kick the sweep (as on MK CD).

MK CD's roundhouse is away + high kick and its sweep away + low kick; here B is the high kick and A
the low kick, and C / down + C gave the two (they still do). patches.controls_code (h) turns a human's
request where only a human's pass (patches.HUMAN_SITE). For each MK fighter, in 2-player duels with Shadow, on both sides
(player 1 faces right, player 2 left):
  - back + B is the roundhouse (EC's move 6) and back + A the sweep ($13), pressed together from
    standing or after walking back; C and down + C still give them;
  - A and B alone, and with toward held, are still the low and high kick (4, 5);
  - back + B held, then back released: one roundhouse, no kick after it;
  - up close, back + A knocks Shadow down as down + C does.
Sub-Zero's slide (back + A + B) still comes out pressed together or A or B up to 2 frames early.
The CPU's fighter never runs that code: a fight against a CPU Sub-Zero plays out frame for frame the
same with the routine in his module turned into a trap (a branch to itself: reached, he'd hang). On a
human's Sub-Zero the trap stops him, and EC's own call put back takes the roundhouse away again.

    backkickcheck.py [--fighters subzero,kano] [--disc CUE]
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT

P = (0x2E188, 0x2E330)                  # the fighters
SLOT = (0x1B000, 0x21800)               # their modules
GRID = {'scorpion': 20, 'raiden': 7, 'johnny': 19, 'subzero': 15, 'liukang': 17, 'kano': 18, 'sonya': 16}
SHADOW = 0
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big', signed=True)
MOVE = lambda r, p: W(r, p + 0xBE) & 0x7FFF
LOW_KICK, HIGH_KICK, ROUNDHOUSE, SWEEP, SLIDE, KNOCKDOWN = 4, 5, 6, 0x13, 0x35, 0x1C
HUMAN_SITE = 0x1784                     # (patches.HUMAN_SITE: the call a human's request passes; EC's: jsr $6ADE)
EC_CALL = bytes.fromhex('4eb900006ade')


def duel(disc, tmp, p1, p2, cpu=False):
    st = os.path.join(tmp, f'{p1}_{p2}{"_cpu" if cpu else ""}.state')
    if not os.path.exists(st):
        subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', disc,
                        '--p1', str(p1), '--p2', str(p2), '--out', st] + (['--cpu'] if cpu else []),
                       check=True, capture_output=True)
    return st


def play(c, port, steps, close=False):
    """Hold each (buttons, frames) on port's pad; -> [(his move, the other's move)] per frame. close: walk up first."""
    me, other = P[port], P[1 - port]
    toward = 'right' if port == 0 else 'left'
    if close:
        for _ in range(400):
            r = c.prg_ram()
            if abs(W(r, other + 0x4E) - W(r, me + 0x4E)) < 60:
                break
            c.buttons[port] = {toward}
            c.run(1)
        c.buttons[port] = set()
        c.run(20)
    out = []
    for held, n in steps:
        c.buttons[port] = set(held.split('+')) - {''}
        for _ in range(n):
            c.run(1)
            r = c.prg_ram()
            out.append((MOVE(r, me), MOVE(r, other)))
    c.buttons[port] = set()
    return out


def attacks(trace, walk):
    """The attack moves in a trace, in order (a held direction shows as its own move id: walk)."""
    out = []
    last = None
    for m, _ in trace:
        if m != last and m not in (0, 0x7FFF, 9, walk):
            out.append(m)
        last = m
    return out


def fighter(c, disc, tmp, who):
    bad = []
    for port in (0, 1):
        st = duel(disc, tmp, GRID[who], SHADOW) if port == 0 else duel(disc, tmp, SHADOW, GRID[who])
        c.load_state(st)
        c.run(30)
        snap = c.snapshot()
        back, fwd = ('left', 'right') if port == 0 else ('right', 'left')
        walk = {'left': 4, 'right': 8}
        cases = [('back + B', [(f'{back}+b', 4), ('', 50)], [ROUNDHOUSE], back),
                 ('back + A', [(f'{back}+a', 4), ('', 50)], [SWEEP], back),
                 ('back, back + B', [(back, 20), (f'{back}+b', 4), (back, 50)], [ROUNDHOUSE], back),
                 ('back, back + A', [(back, 20), (f'{back}+a', 4), (back, 50)], [SWEEP], back),
                 ('C', [('c', 4), ('', 50)], [ROUNDHOUSE], None),
                 ('down + C', [('down', 8), ('down+c', 4), ('down', 10), ('', 40)], [SWEEP], None),
                 ('B', [('b', 4), ('', 50)], [HIGH_KICK], None),
                 ('A', [('a', 4), ('', 50)], [LOW_KICK], None),
                 ('toward + B', [(f'{fwd}+b', 4), ('', 50)], [HIGH_KICK], fwd),
                 ('toward, toward + A', [(fwd, 10), (f'{fwd}+a', 4), ('', 50)], [LOW_KICK], fwd),
                 ('back + B held, back released', [(f'{back}+b', 30), ('b', 40), ('', 20)], [ROUNDHOUSE], back)]
        for name, steps, want, held in cases:
            c.restore(snap)
            tr = play(c, port, steps)
            # (a low kick and walking left are both move 4: told apart by what was held)
            got = attacks(tr, walk.get(held) if LOW_KICK not in want or held != 'left' else None)
            if name.endswith('+ A') and want == [LOW_KICK] and held == 'left':
                got = [m for m in got if m != 8]
            if got != want:
                bad.append(f'player {port + 1} {name}: moves {[hex(m) for m in got]}, expected {[hex(m) for m in want]}')
        downs = []
        for name, steps in (('back + A', [(f'{back}+a', 4), ('', 70)]), ('down + C', [('down', 8), ('down+c', 4), ('', 70)])):
            c.restore(snap)
            tr = play(c, port, steps, close=True)
            downs.append(sum(1 for _, o in tr if o == KNOCKDOWN))
        if not (downs[0] > 20 and abs(downs[0] - downs[1]) <= 8):
            bad.append(f'player {port + 1} up close: Shadow down {downs[0]} frames by back + A, {downs[1]} by down + C')
    return bad


def slide(c, disc, tmp):
    c.load_state(duel(disc, tmp, GRID['subzero'], SHADOW))
    c.run(30)
    snap = c.snapshot()
    bad = []
    for name, steps in (('together', [('left+a+b', 6)]), ('A 1 frame early', [('left+a', 1), ('left+a+b', 6)]),
                        ('A 2 frames early', [('left+a', 2), ('left+a+b', 6)]), ('B 1 frame early', [('left+b', 1), ('left+a+b', 6)]),
                        ('B 2 frames early', [('left+b', 2), ('left+a+b', 6)]),
                        ('walking back, A 2 frames early', [('left', 6), ('left+a', 2), ('left+a+b', 6)])):
        c.restore(snap)
        tr = play(c, 0, steps + [('', 60)])
        if sum(1 for m, _ in tr if m == SLIDE) < 20:
            bad.append(f"Sub-Zero's slide, {name}: moves {[hex(m) for m in attacks(tr, 4)]}")
    return bad


def routine(c, slot):
    """The module offset of the routine the site in the module at slot calls (bsr.w h / nop)."""
    r = c.prg_ram()
    assert r[slot + HUMAN_SITE:slot + HUMAN_SITE + 2] == b'\x61\x00' and r[slot + HUMAN_SITE + 4:slot + HUMAN_SITE + 6] == b'\x4e\x71', 'the site moved'
    return HUMAN_SITE + 2 + W(r, slot + HUMAN_SITE + 2)


def trap(c, slot):
    """The routine in the module at slot becomes a branch to itself."""
    c.poke_prg(slot + routine(c, slot), b'\x60\xfe')


def ec_call(c, slot):
    """EC's own call back at the site in the module at slot."""
    routine(c, slot)
    c.poke_prg(slot + HUMAN_SITE, EC_CALL)


def cpu(c, disc, tmp, frames=2400):
    """A CPU Sub-Zero (player 2) against Shadow walking in and kicking: his fight, with and without the trap."""
    bad = []
    c.load_state(duel(disc, tmp, SHADOW, GRID['subzero'], cpu=True))
    c.run(30)
    snap = c.snapshot()
    traces = []
    for old in (False, True, False):
        c.restore(snap)
        if old:
            trap(c, SLOT[1])
        tr = []
        for t in range(frames):
            c.buttons[0] = {'right'} if t % 90 < 50 else {'b'} if t % 90 < 54 else {'left'} if t % 90 > 75 else set()
            c.run(1)
            r = c.prg_ram()
            tr.append((MOVE(r, P[1]), W(r, P[1] + 0x4E), W(r, P[1] + 0x76), MOVE(r, P[0]), W(r, P[0] + 0x76)))
        traces.append(tr)
    c.buttons[0] = set()
    if traces[0] != traces[2]:
        bad.append('the CPU fight does not repeat from a snapshot (nothing to compare)')
    elif traces[0] != traces[1]:
        at = next(i for i, (x, y) in enumerate(zip(traces[0], traces[1])) if x != y)
        bad.append(f'the CPU fight differs from frame {at} with the trap: he ran the routine')
    walked_back = sum(1 for m, *_ in traces[0] if m in (4, 8))
    kinds = len({m for m, *_ in traces[0]})
    if walked_back < 30 or kinds < 6:
        bad.append(f'the CPU fight showed too little ({walked_back} frames walking, {kinds} moves)')
    c.load_state(duel(disc, tmp, GRID['subzero'], SHADOW))      # the pokes themselves, on a human's
    c.run(30)
    snap = c.snapshot()
    ec_call(c, SLOT[0])
    got = attacks(play(c, 0, [('left', 20), ('left+b', 4), ('left', 50)]), 4)
    if got != [HIGH_KICK]:
        bad.append(f'with EC\'s call a human\'s back + B gave {[hex(m) for m in got]}, expected the high kick')
    c.restore(snap)
    trap(c, SLOT[0])
    play(c, 0, [('b', 4), ('', 20)])
    x = W(c.prg_ram(), P[0] + 0x4E)
    play(c, 0, [('right', 40)])
    if W(c.prg_ram(), P[0] + 0x4E) != x:
        bad.append('the trap did not stop a human\'s Sub-Zero (he walked on after B)')
    return bad, walked_back, kinds


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--fighters', default=','.join(GRID))
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    a = ap.parse_args()
    fails = 0
    with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, 'build')) as tmp:
        c = scd.Core(saves=os.path.join(tmp, 'saves'))
        c.load(a.disc)
        for who in a.fighters.split(','):
            bad = fighter(c, a.disc, tmp, who)
            fails += len(bad)
            print(f'{who:9s} back + B roundhouse, back + A sweep, C, down + C, A, B; both sides -> {"ok" if not bad else "FAIL"}')
            for b in bad:
                print(f'    {b}')
        bad = slide(c, a.disc, tmp)
        fails += len(bad)
        print(f"Sub-Zero's slide, A or B up to 2 frames early -> {'ok' if not bad else 'FAIL'}")
        for b in bad:
            print(f'    {b}')
        bad, walked, kinds = cpu(c, a.disc, tmp)
        fails += len(bad)
        print(f'a CPU Sub-Zero\'s fight ({walked} frames walking, {kinds} moves) the same with the routine a trap -> {"ok" if not bad else "FAIL"}')
        for b in bad:
            print(f'    {b}')
    print('backkickcheck:', 'ok' if not fails else f'{fails} FAIL')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
