#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Johnny Cage's split punch is down + high kick (as on MK CD), and his down + Z blocks.

MK CD's split punch is down + high kick; it was down + Z here (EC's move $10), which left Johnny with no
crouched Block on Z. patches.controls_code (jat) turns a human Johnny's crouched requests, where only a
human's pass (patches.CROUCH_HUMAN). In
2-player duels with Shadow, on both sides (player 1 faces right, player 2 left):
  - down + B is the split punch ($10), from a crouch and pressed together with down; next to Larcen it
    hits him (not Shadow: MK's split punch does nothing to a woman, nor does ours);
  - down + Z is no move; held next to Shadow while she kicks low it blocks (EC's crouch block, $0C; no
    health lost);
  - down + A, down + C, down + X and down + Y are the crouched kick, the sweep and the uppercuts ($11,
    $13, $0E, $0F), and B standing the high kick (5), as before;
  - Sub-Zero's and Kano's down + B is still the crouched kick ($12).
The CPU's Johnny never runs that code: a fight against him plays out frame for frame the same with the
routine in his module turned into a trap (a branch to itself: reached, he'd hang). On a human's Johnny
the trap stops him, and EC's own instruction put back makes down + Z the split punch again.

    splitpunchcheck.py [--disc CUE]
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT

P = (0x2E188, 0x2E330)                  # the fighters
SLOT = (0x1B000, 0x21800)               # their modules
GRID = {'johnny': 19, 'subzero': 15, 'kano': 18}
SHADOW, LARCEN = 0, 1
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big', signed=True)
MOVE = lambda r, p: W(r, p + 0xBE) & 0x7FFF
SPLIT, CROUCH_KICK, CROUCH_HIGH_KICK, SWEEP, UPPERCUTS, HIGH_KICK, CROUCH_BLOCK = 0x10, 0x11, 0x12, 0x13, (0x0E, 0x0F), 5, 0x0C
ATTACKS = set(range(1, 7)) | set(range(0x0E, 0x14)) | set(range(0x20, 0x26))
HUMAN_SITE = 0x19B0                     # (patches.CROUCH_HUMAN: where a human's crouched request becomes its move)
EC_CODE = bytes.fromhex('0641000d')     # (EC's: addi.w #$D,d1)


def duel(disc, tmp, p1, p2, cpu=False):
    st = os.path.join(tmp, f'{p1}_{p2}{"_cpu" if cpu else ""}.state')
    if not os.path.exists(st):
        subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', disc,
                        '--p1', str(p1), '--p2', str(p2), '--out', st] + (['--cpu'] if cpu else []),
                       check=True, capture_output=True)
    return st


def walk_up(c, port):
    me, other = P[port], P[1 - port]
    for _ in range(400):
        r = c.prg_ram()
        if abs(W(r, other + 0x4E) - W(r, me + 0x4E)) < 55:
            break
        c.buttons[port] = {'right' if port == 0 else 'left'}
        c.run(1)
    c.buttons[port] = set()
    c.run(20)


def play(c, port, steps, other=()):
    """Hold each (buttons, frames) on port's pad (the other pad: other, (buttons, frames) too); -> per frame
    (his move, the other's move, his health, the other's health)."""
    me, him = P[port], P[1 - port]
    theirs = [set(b.split('+')) - {''} for b, n in other for _ in range(n)]
    out = []
    for held, n in steps:
        for _ in range(n):
            c.buttons[port] = set(held.split('+')) - {''}
            c.buttons[1 - port] = theirs[len(out)] if len(out) < len(theirs) else set()
            c.run(1)
            r = c.prg_ram()
            out.append((MOVE(r, me), MOVE(r, him), W(r, me + 0x76), W(r, him + 0x76)))
    c.buttons = [set(), set()]
    return out


def attacks(trace):
    """The attack moves in a trace, in order."""
    out, last = [], None
    for m, *_ in trace:
        if m != last and m in ATTACKS:
            out.append(m)
        last = m
    return out


def crouched(c, port, who, cases):
    bad = []
    snap = c.snapshot()
    for name, steps, want in cases:
        c.restore(snap)
        got = attacks(play(c, port, steps))
        if got != want:
            bad.append(f'{who} player {port + 1} {name}: moves {[hex(m) for m in got]}, expected {[hex(m) for m in want]}')
    return bad


def johnny(c, disc, tmp):
    bad = []
    for port in (0, 1):
        c.load_state(duel(disc, tmp, GRID['johnny'], SHADOW) if port == 0 else duel(disc, tmp, SHADOW, GRID['johnny']))
        c.run(30)
        bad += crouched(c, port, 'Johnny', [
            ('down + B', [('down', 12), ('down+b', 4), ('down', 30), ('', 30)], [SPLIT]),
            ('down and B together', [('down+b', 4), ('down', 40), ('', 30)], [SPLIT]),
            ('down + Z', [('down', 12), ('down+z', 20), ('down', 20), ('', 30)], []),
            ('down and Z together', [('down+z', 20), ('down', 20), ('', 30)], []),
            ('down + A', [('down', 12), ('down+a', 4), ('down', 30), ('', 30)], [CROUCH_KICK]),
            ('down + C', [('down', 12), ('down+c', 4), ('down', 30), ('', 30)], [SWEEP]),
            ('down + X', [('down', 12), ('down+x', 4), ('down', 30), ('', 30)], [UPPERCUTS[0]]),
            ('down + Y', [('down', 12), ('down+y', 4), ('down', 30), ('', 30)], [UPPERCUTS[1]]),
            ('B', [('b', 4), ('', 50)], [HIGH_KICK])])
        walk_up(c, port)
        near = c.snapshot()
        c.load_state(duel(disc, tmp, GRID['johnny'], LARCEN) if port == 0 else duel(disc, tmp, LARCEN, GRID['johnny']))
        c.run(30)
        walk_up(c, port)
        tr = play(c, port, [('down', 12), ('down+b', 4), ('down', 40), ('', 20)])
        if SPLIT not in attacks(tr) or tr[-1][3] >= tr[0][3]:
            bad.append(f'Johnny player {port + 1} up close: the split punch took {tr[0][3] - tr[-1][3]} of Larcen\'s health')
        c.restore(near)
        tr = play(c, port, [('down+z', 90), ('', 10)], other=[('', 20), ('down', 10), ('down+a', 4), ('down', 30)])
        if tr[-1][2] != tr[0][2] or not any(m == CROUCH_BLOCK for m, *_ in tr) or SPLIT in attacks(tr):
            bad.append(f'Johnny player {port + 1} down + Z against a low kick: {tr[0][2] - tr[-1][2]} health lost, '
                       f'moves {sorted({hex(m) for m, *_ in tr})}')
        c.restore(near)
        tr = play(c, port, [('down', 90), ('', 10)], other=[('', 20), ('down', 10), ('down+a', 4), ('down', 30)])
        if tr[-1][2] == tr[0][2]:
            bad.append(f'Johnny player {port + 1}: Shadow\'s low kick never hit him crouching (nothing to compare)')
    return bad


def others(c, disc, tmp):
    bad = []
    for who in ('subzero', 'kano'):
        for port in (0, 1):
            c.load_state(duel(disc, tmp, GRID[who], SHADOW) if port == 0 else duel(disc, tmp, SHADOW, GRID[who]))
            c.run(30)
            bad += crouched(c, port, who, [('down + B', [('down', 12), ('down+b', 4), ('down', 30), ('', 30)], [CROUCH_HIGH_KICK]),
                                           ('down + Z', [('down', 12), ('down+z', 20), ('down', 20), ('', 30)], [])])
    return bad


def routine(c, slot):
    """The module offset of the routine the site in the module at slot calls (bsr.w jat)."""
    r = c.prg_ram()
    assert r[slot + HUMAN_SITE:slot + HUMAN_SITE + 2] == b'\x61\x00', 'the site moved'
    return HUMAN_SITE + 2 + W(r, slot + HUMAN_SITE + 2)


def trap(c, slot):
    """The routine in the module at slot becomes a branch to itself."""
    c.poke_prg(slot + routine(c, slot), b'\x60\xfe')


def ec_code(c, slot):
    """EC's own instruction back at the site in the module at slot."""
    routine(c, slot)
    c.poke_prg(slot + HUMAN_SITE, EC_CODE)


def cpu(c, disc, tmp, frames=2400):
    """A CPU Johnny (player 2) against Shadow walking in, kicking and crouching: his fight, with and without."""
    bad = []
    c.load_state(duel(disc, tmp, SHADOW, GRID['johnny'], cpu=True))
    c.run(30)
    snap = c.snapshot()
    traces = []
    for old in (False, True, False):
        c.restore(snap)
        if old:
            trap(c, SLOT[1])
        tr = []
        for t in range(frames):
            c.buttons[0] = ({'right'} if t % 90 < 40 else {'b'} if t % 90 < 44 else {'down'} if t % 90 < 60
                            else {'down', 'a'} if t % 90 < 64 else {'left'} if t % 90 > 78 else set())
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
    low = sum(1 for m, *_ in traces[0] if m == 9 or 0x0C <= m <= 0x13)
    kinds = len({m for m, *_ in traces[0]})
    if low < 20 or kinds < 6:
        bad.append(f'the CPU fight showed too little ({low} frames crouched, {kinds} moves)')
    c.load_state(duel(disc, tmp, GRID['johnny'], SHADOW))       # the pokes themselves, on a human's
    c.run(30)
    snap = c.snapshot()
    ec_code(c, SLOT[0])
    got = attacks(play(c, 0, [('down', 12), ('down+z', 4), ('down', 30), ('', 30)]))
    if got != [SPLIT]:
        bad.append(f'with EC\'s code a human\'s down + Z gave {[hex(m) for m in got]}, expected the split punch')
    c.restore(snap)
    trap(c, SLOT[0])
    play(c, 0, [('down', 12), ('down+a', 4), ('down', 20), ('', 20)])
    x = W(c.prg_ram(), P[0] + 0x4E)
    play(c, 0, [('right', 40)])
    if W(c.prg_ram(), P[0] + 0x4E) != x:
        bad.append('the trap did not stop a human\'s Johnny (he walked on after down + A)')
    return bad, low, kinds


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    a = ap.parse_args()
    fails = 0
    with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, 'build')) as tmp:
        c = scd.Core(saves=os.path.join(tmp, 'saves'))
        c.load(a.disc)
        for label, fn in (("Johnny's down + B split punch, down + Z Block, the rest of his crouch; both sides", johnny),
                          ("Sub-Zero's and Kano's down + B still the crouched kick", others)):
            bad = fn(c, a.disc, tmp)
            fails += len(bad)
            print(f'{label} -> {"ok" if not bad else "FAIL"}')
            for b in bad:
                print(f'    {b}')
        bad, low, kinds = cpu(c, a.disc, tmp)
        fails += len(bad)
        print(f'a CPU Johnny\'s fight ({low} frames crouched, {kinds} moves) the same with the routine a trap -> {"ok" if not bad else "FAIL"}')
        for b in bad:
            print(f'    {b}')
    print('splitpunchcheck:', 'ok' if not fails else f'{fails} FAIL')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
