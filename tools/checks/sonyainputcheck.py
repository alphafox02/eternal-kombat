#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Sonya's specials from the pad, as the player presses them.

(mkinputs.GENERIC_MOVES[17], r_taps, r_generic's throw rewrite.) Every MK fighter's toward + HP reads as
EC's back + HP (EC's throw), and that made-up back finished her square wave (forward, back + a punch)
whenever forward was held: she flew instead of punching. Her energy rings are MK CD's high punch, back,
a punch (measured: HP, back, HP and HP, back, LP throw them; LP first, back + a punch alone, or the three
spread out, only punch). From 2-player duels, Sonya against Shadow, on both sides (player 1 faces right,
player 2 left):
  - forward held, HP: a high punch (move 2), not the square wave ($35);
  - forward, back, HP and forward, back + HP: the square wave;
  - HP, back, HP; HP, back, LP; HP, back + HP: the energy rings ($34), after her high punch;
  - back, HP; back held + HP; LP, back, LP; LP, back, HP; HP, back, HP half a second apart: punches,
    no rings;
  - next to Shadow, forward + HP: the throw ($0D).
The CPU's Sonya never runs the recogniser (r_taps; EC's own returns before it for the CPU's fighter): a
fight against her plays out frame for frame the same with the routine in her module turned into a trap
(a branch to itself: reached, the game would hang) - and on a human's Sonya the trap stops her.

    sonyainputcheck.py [--disc CUE]     (run after play.py test has made the disc's build/states/menu.state)
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT

P = (0x2E188, 0x2E330)                  # the fighters
BLOCK = (0x1B000 + 0x5200, 0x21800 + 0x5200)   # their modules' MK blocks (mkinputs.SLOTS, EXT_OFF)
RAW_TAPS = 8 + 4 * 8                    # a block's own r_taps: a bra.w there (mkinputs.RAW, ENTRIES' first)
SONYA, SHADOW = 16, 0
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big', signed=True)
MOVE = lambda r, p: W(r, p + 0xBE) & 0x7FFF
LOW_PUNCH, PUNCH, SQUARE, RINGS, THROW = 0x01, 0x02, 0x35, 0x34, 0x0D
# (name, [(held - 'f' toward, 'b' away, buttons -, frames)], the moves wanted in order, up close)
CASES = [('forward held, HP', [('f', 20), ('f+y', 3), ('f', 20)], [PUNCH], False),
         ('forward, back, HP', [('f', 3), ('', 2), ('b', 3), ('y', 3)], [SQUARE], False),
         ('forward, back + HP', [('f', 3), ('', 2), ('b+y', 3)], [SQUARE], False),
         ('HP, back, HP', [('y', 4), ('', 2), ('b', 4), ('', 2), ('y', 4)], [PUNCH, RINGS], False),
         ('HP, back, LP', [('y', 4), ('', 2), ('b', 4), ('', 2), ('x', 4)], [PUNCH, RINGS], False),
         ('HP, back + HP', [('y', 4), ('', 2), ('b', 2), ('b+y', 4)], [PUNCH, RINGS], False),
         ('back, HP', [('b', 3), ('', 3), ('y', 3)], [PUNCH], False),
         ('back held + HP', [('b', 20), ('b+y', 3)], [PUNCH], False),
         ('LP, back, LP', [('x', 4), ('', 2), ('b', 4), ('', 2), ('x', 4)], [LOW_PUNCH], False),
         ('LP, back, HP', [('x', 4), ('', 2), ('b', 4), ('', 2), ('y', 4)], [LOW_PUNCH], False),
         ('HP, back, HP spread out', [('y', 4), ('', 30), ('b', 4), ('', 30), ('y', 4)], [PUNCH, PUNCH], False),
         ('close: forward + HP', [('f', 4), ('f+y', 3)], [THROW], True)]


def duel(disc, tmp, p1, p2, cpu=False):
    st = os.path.join(tmp, f'{p1}_{p2}{"_cpu" if cpu else ""}.state')
    if not os.path.exists(st):
        subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', disc,
                        '--p1', str(p1), '--p2', str(p2), '--out', st] + (['--cpu'] if cpu else []),
                       check=True, capture_output=True)
    return st


def pad(held, port):
    way = {'f': 'right', 'b': 'left'} if port == 0 else {'f': 'left', 'b': 'right'}
    return {way.get(b, b) for b in held.split('+') if b}


def trap(c, block):
    """r_taps in the MK block at block becomes a branch to itself."""
    r = c.prg_ram()
    assert r[block:block + 4] == b'EKSC' and r[block + RAW_TAPS:block + RAW_TAPS + 2] == b'\x60\x00', 'the block changed'
    c.poke_prg(block + RAW_TAPS + 2 + W(r, block + RAW_TAPS + 2), b'\x60\xfe')


def cpu(c, disc, tmp, frames=2400):
    """A CPU Sonya (player 2) against Shadow walking in and kicking: her fight, with and without the trap."""
    bad = []
    c.load_state(duel(disc, tmp, SHADOW, SONYA, cpu=True))
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
        bad.append(f'the CPU fight differs from frame {at} with the trap: she ran the recogniser')
    kinds = len({m for m, *_ in traces[0]})
    specials = sum(1 for k, (m, *_) in enumerate(traces[0]) if m in (SQUARE, RINGS) and traces[0][k - 1][0] != m)
    if kinds < 6:
        bad.append(f'the CPU fight showed too little ({kinds} moves)')
    c.load_state(duel(disc, tmp, SONYA, SHADOW))                # the trap itself, on a human's
    c.run(40)
    trap(c, BLOCK[0])
    c.buttons[0] = {'right'}
    c.run(10)
    x = W(c.prg_ram(), P[0] + 0x4E)
    c.run(40)
    c.buttons[0] = set()
    if W(c.prg_ram(), P[0] + 0x4E) != x:
        bad.append('the trap did not stop a human\'s Sonya (she walked on)')
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
            st = duel(a.disc, tmp, SONYA, SHADOW) if port == 0 else duel(a.disc, tmp, SHADOW, SONYA)
            me, other = P[port], P[1 - port]
            for name, seq, want, close in CASES:
                c.load_state(st)
                c.run(40)
                for _ in range(400 if close else 0):
                    r = c.prg_ram()
                    if abs(W(r, other + 0x4E) - W(r, me + 0x4E)) < 50:
                        break
                    c.buttons[port] = pad('f', port)
                    c.run(1)
                moves = []
                for held, n in seq + [('', 70)]:
                    c.buttons[port] = pad(held, port)
                    for _ in range(n):
                        c.run(1)
                        m = MOVE(c.prg_ram(), me)
                        if not moves or moves[-1] != m:
                            moves.append(m)
                c.buttons[port] = set()
                got = [m for m in moves if m in (LOW_PUNCH, PUNCH, SQUARE, RINGS, THROW)]
                ok = got == want
                print(f'player {port + 1} {name:24s} moves {" ".join(f"{m:X}" for m in moves):28s} want {" ".join(f"{m:X}" for m in want)}: {"ok" if ok else "WRONG"}')
                if not ok:
                    bad.append(f'player {port + 1} {name}')
        b, kinds, specials = cpu(c, a.disc, tmp)
        print(f'a CPU Sonya\'s fight ({kinds} moves, {specials} specials) the same with r_taps a trap -> {"ok" if not b else "FAIL"}')
        for x in b:
            print(f'    {x}')
        bad += b
    print('sonyainputcheck:', 'FAIL ' + ', '.join(bad) if bad else 'ok')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
