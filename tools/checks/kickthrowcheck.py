#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""MK fighters throw with the high kick up close (as on MK CD).

MK CD's throw is the high kick next to the opponent, no direction needed; here B is the high kick, and
toward + Y (EC's throw) still throws. patches.controls_code (h) tests a human's B where only a human's
requests pass (patches.HUMAN_SITE). For each MK fighter, in 2-player duels with Shadow, on both sides (player 1 faces
right, player 2 left), next to her:
  - B alone, toward + B, back + B (MK CD throws with away held too) and toward + Y throw (EC's move $0D;
    Shadow in EC's thrown state, $37) and she lands behind him;
  - B held for two seconds is one throw;
  - C is the close roundhouse ($25), A the close low kick ($23), down + B a crouched kick: no throw;
and away from her B is the high kick (5), as before.
The CPU's fighter never runs that code: fights against a CPU Sub-Zero and a CPU Scorpion play out frame
for frame the same with the routine in his module turned into a trap (a branch to itself: reached, he'd
hang). On a human's Sub-Zero the trap stops him, and EC's own call put back takes the throw away again.

    kickthrowcheck.py [--fighters subzero,kano] [--disc CUE]
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
HIGH_KICK, THROW, THROWN, CLOSE_LOW_KICK, CLOSE_ROUNDHOUSE = 5, 0x0D, 0x37, 0x23, 0x25
CROUCH_KICKS = (0x10, 0x12)             # (down + B: the crouched high kick; Johnny's split punch)
HUMAN_SITE = 0x1784                     # (patches.HUMAN_SITE: the call a human's request passes; EC's: jsr $6ADE)
EC_CALL = bytes.fromhex('4eb900006ade')


def duel(disc, tmp, p1, p2, cpu=False):
    st = os.path.join(tmp, f'{p1}_{p2}{"_cpu" if cpu else ""}.state')
    if not os.path.exists(st):
        subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', disc,
                        '--p1', str(p1), '--p2', str(p2), '--out', st] + (['--cpu'] if cpu else []),
                       check=True, capture_output=True)
    return st


def walk_up(c, port):
    """Walk port's fighter up to the other one (within EC's 'close'), then let him stand."""
    me, other = P[port], P[1 - port]
    for _ in range(400):
        r = c.prg_ram()
        if abs(W(r, other + 0x4E) - W(r, me + 0x4E)) < 50:
            break
        c.buttons[port] = {'right' if port == 0 else 'left'}
        c.run(1)
    c.buttons[port] = set()
    c.run(20)


def play(c, port, steps):
    """Hold each (buttons, frames) on port's pad; -> [(his move, the other's move, his x - the other's)] per frame."""
    me, other = P[port], P[1 - port]
    out = []
    for held, n in steps:
        c.buttons[port] = set(held.split('+')) - {''}
        for _ in range(n):
            c.run(1)
            r = c.prg_ram()
            out.append((MOVE(r, me), MOVE(r, other), W(r, me + 0x4E) - W(r, other + 0x4E)))
    c.buttons[port] = set()
    return out


def throws(trace):
    """How many times he threw in a trace (runs of move $0D), and whether the other was ever thrown."""
    n = sum(1 for k, (m, _, _) in enumerate(trace) if m == THROW and (k == 0 or trace[k - 1][0] != THROW))
    return n, any(o == THROWN for _, o, _ in trace)


def fighter(c, disc, tmp, who):
    bad = []
    for port in (0, 1):
        st = duel(disc, tmp, GRID[who], SHADOW) if port == 0 else duel(disc, tmp, SHADOW, GRID[who])
        c.load_state(st)
        c.run(30)
        far = c.snapshot()
        walk_up(c, port)
        near = c.snapshot()
        back, fwd = ('left', 'right') if port == 0 else ('right', 'left')
        for name, steps in (('B', [('b', 4), ('', 150)]), ('toward + B', [(f'{fwd}+b', 4), ('', 150)]),
                            ('back + B', [(f'{back}+b', 4), ('', 150)]),
                            ('toward + Y', [(f'{fwd}+y', 4), ('', 150)]), ('B held', [('b', 120), ('', 60)])):
            c.restore(near)
            before = W(c.prg_ram(), P[port] + 0x4E) - W(c.prg_ram(), P[1 - port] + 0x4E)
            tr = play(c, port, steps)
            n, thrown = throws(tr)
            if n != 1 or not thrown:
                bad.append(f'player {port + 1} up close {name}: {n} throws, Shadow thrown: {thrown}')
            elif (tr[-1][2] > 0) == (before > 0):
                bad.append(f'player {port + 1} up close {name}: Shadow did not land behind him ({before} -> {tr[-1][2]} px)')
        for name, steps, want in (('C', [('c', 4), ('', 80)], (CLOSE_ROUNDHOUSE,)),
                                  ('A', [('a', 4), ('', 80)], (CLOSE_LOW_KICK,)),
                                  ('down + B', [('down', 10), ('down+b', 4), ('down', 20), ('', 50)], CROUCH_KICKS)):
            c.restore(near)
            tr = play(c, port, steps)
            n, thrown = throws(tr)
            if n or thrown or not any(m in want for m, _, _ in tr):
                bad.append(f'player {port + 1} up close {name}: {n} throws, moves {sorted({hex(m) for m, _, _ in tr})}')
        c.restore(far)
        tr = play(c, port, [('b', 4), ('', 60)])
        if throws(tr)[0] or not any(m == HIGH_KICK for m, _, _ in tr):
            bad.append(f'player {port + 1} away from her B: moves {sorted({hex(m) for m, _, _ in tr})}')
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


def cpu(c, disc, tmp, who, frames=2400):
    """A CPU fighter (player 2) against Shadow walking in and kicking: his fight, with and without the trap."""
    bad = []
    c.load_state(duel(disc, tmp, SHADOW, GRID[who], cpu=True))
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
            tr.append((MOVE(r, P[1]), W(r, P[1] + 0x4E), W(r, P[1] + 0x76), MOVE(r, P[0]), W(r, P[0] + 0x4E), W(r, P[0] + 0x76)))
        traces.append(tr)
    c.buttons[0] = set()
    if traces[0] != traces[2]:
        bad.append('the CPU fight does not repeat from a snapshot (nothing to compare)')
    elif traces[0] != traces[1]:
        at = next(i for i, (x, y) in enumerate(zip(traces[0], traces[1])) if x != y)
        bad.append(f'the CPU fight differs from frame {at} with the trap: he ran the routine')
    near = sum(1 for _, x, _, _, x1, _ in traces[0] if abs(x - x1) < 60)
    kinds = len({m for m, *_ in traces[0]})
    if near < 100 or kinds < 6:
        bad.append(f'the CPU fight showed too little ({near} frames up close, {kinds} moves)')
    return bad, near, kinds


def pokes_work(c, disc, tmp):
    """The pokes themselves, on a human's Sub-Zero: with EC's call B up close is a kick again; the trap stops him."""
    bad = []
    c.load_state(duel(disc, tmp, GRID['subzero'], SHADOW))
    c.run(30)
    walk_up(c, 0)
    snap = c.snapshot()
    ec_call(c, SLOT[0])
    if throws(play(c, 0, [('b', 4), ('', 100)]))[0]:
        bad.append('with EC\'s call a human\'s B up close still threw')
    c.restore(snap)
    trap(c, SLOT[0])
    tr = play(c, 0, [('b', 4), ('', 20), ('left', 40)])
    if tr[-1][2] != tr[30][2] or throws(tr)[0]:
        bad.append('the trap did not stop a human\'s Sub-Zero (he walked on after B)')
    return bad


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
            print(f'{who:9s} up close B (alone, toward, back) and toward + Y throw; C, A, down + B don\'t; both sides -> {"ok" if not bad else "FAIL"}')
            for b in bad:
                print(f'    {b}')
        for who in ('subzero', 'scorpion'):
            bad, near, kinds = cpu(c, a.disc, tmp, who)
            fails += len(bad)
            print(f'a CPU {who}\'s fight ({near} frames up close, {kinds} moves) the same with the routine a trap -> {"ok" if not bad else "FAIL"}')
            for b in bad:
                print(f'    {b}')
        bad = pokes_work(c, a.disc, tmp)
        fails += len(bad)
        print(f'on a human\'s: EC\'s call takes the throw away, the trap stops him -> {"ok" if not bad else "FAIL"}')
        for b in bad:
            print(f'    {b}')
    print('kickthrowcheck:', 'ok' if not fails else f'{fails} FAIL')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
