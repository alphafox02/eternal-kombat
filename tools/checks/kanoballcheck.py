#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Kano's cannonball is MK CD's full circle: toward, down, away, up - Block held or not.

Measured on MK CD (docs/notes/2026-11.md): the four taps in that order do it, with Block held and
without; three of them (toward, down, away - what it was here - or down, away, up), another order, or
the four spread out do nothing. His knife is Block held: away, toward; without Block nothing.
mkinputs.GENERIC_MOVES[13], r_taps' fourth tap. In 2-player duels, Kano against Shadow, on both sides
(player 1 faces right, player 2 left):
  - toward, down, away, up, and the same with Z held: the cannonball (EC's move $35); from a few steps
    away it hits her;
  - toward, down, away; down, away, up; away, down, toward, up; the four taps 40 frames apart: no
    cannonball;
  - Z held: away, toward is the knife ($34); away, toward without Z is not.
The CPU's Kano never runs the recogniser (r_taps; EC's own returns before it for the CPU's fighter): a
fight against him plays out frame for frame the same with the routine in his module turned into a trap
(a branch to itself: reached, the game would hang).

    kanoballcheck.py [--disc CUE]
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT

P = (0x2E188, 0x2E330)                  # the fighters
BLOCK = (0x1B000 + 0x5200, 0x21800 + 0x5200)   # their modules' MK blocks (mkinputs.SLOTS, EXT_OFF)
RAW_TAPS = 8 + 4 * 8                    # a block's own r_taps: a bra.w there (mkinputs.RAW, ENTRIES' first)
KANO, SHADOW = 18, 0
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big', signed=True)
MOVE = lambda r, p: W(r, p + 0xBE) & 0x7FFF
KNIFE, BALL = 0x34, 0x35
# (name, taps - F toward, D down, B away, U up -, frames between taps, Z held, the special wanted or None)
CASES = [('toward, down, away, up', 'FDBU', 2, False, BALL),
         ('toward, down, away, up, no gaps', 'FDBU', 0, False, BALL),
         ('Z held: toward, down, away, up', 'FDBU', 2, True, BALL),
         ('toward, down, away', 'FDB', 2, False, None),
         ('Z held: toward, down, away', 'FDB', 2, True, None),
         ('down, away, up', 'DBU', 2, False, None),
         ('away, down, toward, up', 'BDFU', 2, False, None),
         ('toward, down, away, up 40 frames apart', 'FDBU', 40, False, None),
         ('Z held: away, toward', 'BF', 2, True, KNIFE),
         ('away, toward', 'BF', 2, False, None)]


def duel(disc, tmp, p1, p2, cpu=False):
    st = os.path.join(tmp, f'{p1}_{p2}{"_cpu" if cpu else ""}.state')
    if not os.path.exists(st):
        subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', disc,
                        '--p1', str(p1), '--p2', str(p2), '--stage', '11', '--out', st] + (['--cpu'] if cpu else []),
                       check=True, capture_output=True)
    return st


def play(c, port, taps, gap, z, after=110):
    """A player's taps (4 frames each, gap frames between), Z held through them or not; -> (the specials
    he started, in order; the health the other lost)."""
    way = {'F': 'right', 'B': 'left', 'D': 'down', 'U': 'up'} if port == 0 else {'F': 'left', 'B': 'right', 'D': 'down', 'U': 'up'}
    hold = {'z'} if z else set()
    steps = [(hold, 12)] if z else []
    for t in taps:
        steps += [(hold | {way[t]}, 4), (hold, gap)]
    before = W(c.prg_ram(), P[1 - port] + 0x76)
    got, last = [], None
    for held, n in steps + [(hold, 10), (set(), after)]:
        c.buttons[port] = set(held)
        for _ in range(n):
            c.run(1)
            m = MOVE(c.prg_ram(), P[port])
            if m != last and m in (KNIFE, BALL):
                got.append(m)
            last = m
    c.buttons[port] = set()
    return got, before - W(c.prg_ram(), P[1 - port] + 0x76)


def trap(c, block):
    """r_taps in the MK block at block becomes a branch to itself."""
    r = c.prg_ram()
    assert r[block:block + 4] == b'EKSC' and r[block + RAW_TAPS:block + RAW_TAPS + 2] == b'\x60\x00', 'the block changed'
    c.poke_prg(block + RAW_TAPS + 2 + W(r, block + RAW_TAPS + 2), b'\x60\xfe')


def cpu(c, disc, tmp, frames=2400):
    """A CPU Kano (player 2) against Shadow walking in and kicking: his fight, with and without the trap."""
    bad = []
    c.load_state(duel(disc, tmp, SHADOW, KANO, cpu=True))
    c.run(30)
    snap = c.snapshot()
    traces = []
    for old in (False, True, False):
        c.restore(snap)
        if old:
            trap(c, BLOCK[1])
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
        bad.append(f'the CPU fight differs from frame {at} with the trap: he ran the recogniser')
    kinds = len({m for m, *_ in traces[0]})
    specials = sum(1 for k, (m, *_) in enumerate(traces[0]) if m in (KNIFE, BALL) and traces[0][k - 1][0] != m)
    if kinds < 6:
        bad.append(f'the CPU fight showed too little ({kinds} moves)')
    return bad, kinds, specials


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    a = ap.parse_args()
    bad = []
    with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, 'build')) as tmp:
        c = scd.Core(saves=os.path.join(tmp, 'saves'))
        c.load(a.disc)
        for port in (0, 1):
            c.load_state(duel(a.disc, tmp, KANO, SHADOW) if port == 0 else duel(a.disc, tmp, SHADOW, KANO))
            c.run(80)
            snap = c.snapshot()
            for name, taps, gap, z, want in CASES:
                c.restore(snap)
                got, lost = play(c, port, taps, gap, z)
                ok = got == ([want] if want else [])
                print(f'player {port + 1} {name:40s} specials {" ".join(f"{m:X}" for m in got) or "-":6s}: {"ok" if ok else "WRONG"}')
                if not ok:
                    bad.append(f'player {port + 1} {name}')
            c.restore(snap)
            c.buttons[port] = {'right' if port == 0 else 'left'}
            c.run(30)
            c.buttons[port] = set()
            c.run(20)
            got, lost = play(c, port, 'FDBU', 2, False)
            ok = got == [BALL] and lost > 0
            print(f'player {port + 1} a few steps nearer: the cannonball took {lost} of Shadow\'s health: {"ok" if ok else "WRONG"}')
            if not ok:
                bad.append(f'player {port + 1} the cannonball\'s hit')
        b, kinds, specials = cpu(c, a.disc, tmp)
        print(f'a CPU Kano\'s fight ({kinds} moves, {specials} specials) the same with r_taps a trap -> {"ok" if not b else "FAIL"}')
        for x in b:
            print(f'    {x}')
        bad += b
    print('kanoballcheck:', 'FAIL ' + ', '.join(bad) if bad else 'ok')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
