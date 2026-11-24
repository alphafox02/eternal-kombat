#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""MK fighters' specials that name a punch take either punch (as on MK CD), and nothing else changed.

On MK CD the spear, Scorpion's teleport, Raiden's lightning, Johnny's bolt, the ice blast, Liu Kang's
fireball and Sonya's square wave come out with the low punch and with the high punch alike (measured,
docs/notes/2026-11.md); the kick specials take their own kick only. mkinputs.GENERIC_MOVES. For each of
those fighters, in 2-player duels with Shadow, on both sides (player 1 faces right, player 2 left):
  - each punch special with X and with Y (EC's move $34 / $35);
  - his other specials as before (Raiden's torpedo and teleport, Johnny's shadow kick, Sub-Zero's slide,
    Liu Kang's flying kick), and not with the other kick (Johnny's on B, Liu Kang's on A);
  - X and Y alone, with away or toward held, and down + X / Y are still the punches (1, 2) and the
    uppercuts ($0E, $0F).
The CPU's fighter reads none of it: a fight against a CPU Sub-Zero - through FINISH HIM (Shadow on her
last point), where his fatality's button test is - plays out frame for frame the same with his list's
punches put back to the single ones in memory and that test turned into a trap (a branch to itself:
reached, he'd hang).

    eitherpunchcheck.py [--fighters subzero,sonya] [--disc CUE]
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT

P = (0x2E188, 0x2E330)                  # the fighters
SLOT, SLOT_SIZE = (0x1B000, 0x21800), 0x6800   # their modules (mkinputs.SLOTS)
GRID = {'scorpion': 20, 'raiden': 7, 'johnny': 19, 'subzero': 15, 'liukang': 17, 'sonya': 16}
SHADOW = 0
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big', signed=True)
MOVE = lambda r, p: W(r, p + 0xBE) & 0x7FFF
PROJECTILE, DASH, TELEPORT = 0x34, 0x35, 0x31
X, Y = 0x400, 0x200                     # the pad's punches (mkinputs.LP, HP)
# his specials: (name, taps - B away, F toward, D, U -, buttons with the last tap ('P': each punch), EC's move)
SPECIALS = {
    'scorpion': [('spear', 'BB', 'P', PROJECTILE), ('teleport punch', 'DB', 'P', DASH)],
    'raiden': [('lightning', 'DF', 'P', PROJECTILE), ('torpedo', 'BBF', '', DASH), ('teleport', 'DU', '', TELEPORT)],
    'johnny': [('green bolt', 'BF', 'P', PROJECTILE), ('shadow kick', 'BF', 'a', DASH)],
    'subzero': [('ice blast', 'DF', 'P', PROJECTILE), ('slide', 'B', 'a+b', DASH)],
    'liukang': [('fireball', 'FF', 'P', PROJECTILE), ('flying kick', 'FF', 'b', DASH)],
    'sonya': [('square wave', 'FB', 'P', DASH)],
}
WRONG_KICK = {'johnny': ('BF', 'b'), 'liukang': ('FF', 'a')}
SPECIAL_MOVES = (PROJECTILE, DASH, TELEPORT)
PLAIN = [('X', '', 'x', 1), ('Y', '', 'y', 2), ('away held, X', 'b', 'x', 1), ('away held, Y', 'b', 'y', 2),
         ('toward held, X', 'f', 'x', 1), ('toward held, Y', 'f', 'y', 2)]


def duel(disc, tmp, p1, p2, cpu=False):
    st = os.path.join(tmp, f'{p1}_{p2}{"_cpu" if cpu else ""}.state')
    if not os.path.exists(st):
        subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', disc,
                        '--p1', str(p1), '--p2', str(p2), '--out', st] + (['--cpu'] if cpu else []),
                       check=True, capture_output=True)
    return st


def play(c, port, steps):
    """Hold each (buttons, frames) on port's pad; -> his moves, in order, as they change."""
    out = []
    for held, n in steps:
        c.buttons[port] = set(held.split('+')) - {''}
        for _ in range(n):
            c.run(1)
            m = MOVE(c.prg_ram(), P[port])
            if not out or out[-1] != m:
                out.append(m)
    c.buttons[port] = set()
    return out


def special(taps, button, port):
    """A player's presses: each tap 3 frames down and 2 up, the buttons 4 frames with the last tap held."""
    way = {'B': 'left', 'F': 'right', 'D': 'down', 'U': 'up'} if port == 0 else {'B': 'right', 'F': 'left', 'D': 'down', 'U': 'up'}
    steps = []
    for t in taps[:-1]:
        steps += [(way[t], 3), ('', 2)]
    if button:
        steps += [(way[taps[-1]], 2), (f'{way[taps[-1]]}+{button}', 4)]
    else:
        steps += [(way[taps[-1]], 4)]
    return steps + [('', 70)]


def fighter(c, disc, tmp, who):
    bad = []
    for port in (0, 1):
        c.load_state(duel(disc, tmp, GRID[who], SHADOW) if port == 0 else duel(disc, tmp, SHADOW, GRID[who]))
        c.run(30)
        snap = c.snapshot()
        for name, taps, buttons, want in SPECIALS[who]:
            for b in ('x', 'y') if buttons == 'P' else (buttons,):
                c.restore(snap)
                got = [m for m in play(c, port, special(taps, b, port)) if m in SPECIAL_MOVES]
                if got[:1] != [want]:
                    bad.append(f'player {port + 1} {name} with {b.upper() or "no button"}: specials {[hex(m) for m in got]}, expected {want:#x}')
        if who in WRONG_KICK:
            c.restore(snap)
            got = [m for m in play(c, port, special(*WRONG_KICK[who], port)) if m in SPECIAL_MOVES]
            if got:
                bad.append(f'player {port + 1} {WRONG_KICK[who][0]} + {WRONG_KICK[who][1].upper()}: the special {[hex(m) for m in got]}')
        hold = {'b': 'left' if port == 0 else 'right', 'f': 'right' if port == 0 else 'left', '': ''}
        for name, held, b, want in PLAIN:
            c.restore(snap)
            got = play(c, port, [(hold[held], 20), (f'{hold[held]}+{b}', 4), (hold[held], 10), ('', 40)])
            if want not in got or any(m in SPECIAL_MOVES for m in got):
                bad.append(f'player {port + 1} {name}: moves {[hex(m) for m in got]}, expected {want:#x}')
        for b, want in (('x', 0x0E), ('y', 0x0F)):
            c.restore(snap)
            got = play(c, port, [('down', 14), (f'down+{b}', 4), ('down', 20), ('', 40)])
            if want not in got or any(m in SPECIAL_MOVES for m in got):
                bad.append(f'player {port + 1} down + {b.upper()}: moves {[hex(m) for m in got]}, expected {want:#x}')
    return bad


def single_punches(c, block):
    """In the module at block: every list entry's X + Y back to X alone, and his fatality's test of the two
    (move.w d2,d1 / andi.w #X+Y,d1) a branch to itself. -> (entries, tests) changed."""
    r = c.prg_ram()
    blk = r[block:block + SLOT_SIZE]
    entries = tests = 0
    for o in range(0, len(blk) - 8, 2):
        if blk[o:o + 2] == b'\x00\x28' and blk[o + 6:o + 8] == (X | Y).to_bytes(2, 'big') and blk[o + 8] == 0:
            c.poke_prg(block + o + 6, X.to_bytes(2, 'big'))
            entries += 1
        if blk[o:o + 6] == bytes.fromhex('32020241') + (X | Y).to_bytes(2, 'big'):
            c.poke_prg(block + o, b'\x60\xfe')
            tests += 1
    return entries, tests


def cpu(c, disc, tmp, frames=2400):
    """A CPU Sub-Zero (player 2) against Shadow, who walks in and kicks and is on 3 health in the deciding
    round: his fight to FINISH HIM and after, with and without the pokes."""
    bad = []
    c.load_state(duel(disc, tmp, SHADOW, GRID['subzero'], cpu=True))
    c.run(30)
    c.poke_prg(0x31D26, (1).to_bytes(2, 'big'))       # one round each: this one decides it
    c.poke_prg(0x31D28, (1).to_bytes(2, 'big'))
    c.poke_prg(P[0] + 0x76, (3).to_bytes(2, 'big'))
    snap = c.snapshot()
    traces, n = [], (0, 0)
    for old in (False, True, False):
        c.restore(snap)
        if old:
            n = single_punches(c, SLOT[1])
        tr = []
        for t in range(frames):
            c.buttons[0] = {'right'} if t % 90 < 50 else {'b'} if t % 90 < 54 else {'left'} if t % 90 > 75 else set()
            c.run(1)
            r = c.prg_ram()
            tr.append((MOVE(r, P[1]), W(r, P[1] + 0x4E), W(r, P[1] + 0x76), MOVE(r, P[0]), W(r, P[0] + 0x4E), W(r, P[0] + 0x76)))
        traces.append(tr)
    c.buttons[0] = set()
    if n != (1, 2):
        bad.append(f'{n[0]} list entries and {n[1]} fatality tests found in his module, expected 1 and 2')
    if traces[0] != traces[2]:
        bad.append('the CPU fight does not repeat from a snapshot (nothing to compare)')
    elif traces[0] != traces[1]:
        at = next(i for i, (x, y) in enumerate(zip(traces[0], traces[1])) if x != y)
        bad.append(f'the CPU fight differs from frame {at} with the single punches and the trap')
    dazed = sum(1 for *_, hp in traces[0] if hp == 1)
    kinds = len({m for m, *_ in traces[0]})
    if dazed < 30 or traces[0][-1][-1] != 0 or kinds < 5:
        bad.append(f'the CPU fight showed too little ({dazed} frames of FINISH HIM, Shadow on {traces[0][-1][-1]} at the end, {kinds} moves)')
    c.load_state(duel(disc, tmp, GRID['subzero'], SHADOW))      # the poke itself, on a human's
    c.run(30)
    single_punches(c, SLOT[0])
    got = [m for m in play(c, 0, special('DF', 'y', 0)) if m in SPECIAL_MOVES]
    if got:
        bad.append(f'with the single punches a human\'s down, toward + Y still gave {[hex(m) for m in got]}')
    return bad, dazed, kinds


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
            print(f'{who:9s} {", ".join(n for n, *_ in SPECIALS[who])}; X, Y and the uppercuts; both sides -> {"ok" if not bad else "FAIL"}')
            for b in bad:
                print(f'    {b}')
        bad, dazed, kinds = cpu(c, a.disc, tmp)
        fails += len(bad)
        print(f'a CPU Sub-Zero\'s fight ({dazed} frames of FINISH HIM, {kinds} moves) the same with the single punches -> {"ok" if not bad else "FAIL"}')
        for b in bad:
            print(f'    {b}')
    print('eitherpunchcheck:', 'ok' if not fails else f'{fails} FAIL')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
