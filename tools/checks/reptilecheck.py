#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check Reptile (fighter id 26, MK's secret) in a duel.

Kano (player 1) against him (player 2, driven by the pad here) on the Pit - which, with
him there, is the Pit's bottom (ecstage rbot: the spikes' floor). His ice blast (down,
forward + LP, move $31) freezes Kano without damage; his slide (back + LK + HK) knocks
Kano down and hurts him; his spear (back, back + LP: Scorpion's, move $34) hits from ~125
px, holds, yanks Kano in to MK's gap and dazes him (~80 frames), then Kano stands again.
The CPU's Reptile throws 4-16 projectiles in 120 s, spear and freeze both (MK's ~4.5 a
minute), and never stalls; round 2 starts (its clock counts down, he comes forward).

    reptilecheck.py [--disc CUE] [--state S]
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT

P1, P2 = 0x2E188, 0x2E330
A6 = 0x30000
FLOOR = 757                   # his fight's floor line (ecstage: rbot; patches.PIT_REPTILE_FLOOR), $1496(a6)
REPTILE_ID, KANO_GRID = 26, 18
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big')
MOVE = lambda r, p: W(r, p + 0xBE) & 0x7FFF


def play(c, steps, port=1, watch=None):
    for held, n in steps:
        c.buttons[port] = set(held)
        for _ in range(n):
            c.run(1)
            if watch:
                watch(c.prg_ram())
    c.buttons[port] = set()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    ap.add_argument('--state', help='duel state (Kano vs Reptile on the Pit) from this disc')
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        state = a.state or os.path.join(tmp, 'duel.state')
        if not a.state:
            subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', a.disc,
                            '--p1', str(KANO_GRID), '--p2', '0', '--p2-id', str(REPTILE_ID), '--stage', '1F',
                            '--out', state], check=True, capture_output=True)
        c = scd.Core(saves=os.path.join(tmp, 'saves'))
        c.load(a.disc)
        c.load_state(state)
        c.run(60)
        r = c.prg_ram()
        ok = r[P2 + 0x4D] == REPTILE_ID and r[P1 + 0x4D] == 13
        bottom = W(r, A6 + 0x1496) == FLOOR and all(abs(W(r, p + 0x52) - FLOOR) <= 8 for p in (P1, P2))
        print(f'fighters {r[P1 + 0x4D]} vs {r[P2 + 0x4D]}; floor {W(r, A6 + 0x1496)}, '
              f'y {W(r, P1 + 0x52)} / {W(r, P2 + 0x52)} -> pit bottom {bottom}')
        # ice blast from where he stands: down, forward (left: he faces Kano) + LP
        hp = W(r, P1 + 0x76)
        st = {'frozen': 0, 'run': 0}
        def frz(r):
            st['run'] = st['run'] + 1 if MOVE(r, P1) == 0x1F else 0
            st['frozen'] = max(st['frozen'], st['run'])
        play(c, [({'down'}, 3), ((), 2), ({'left'}, 3), ({'x'}, 4), ((), 150)], watch=frz)
        r = c.prg_ram()
        frozen = st['frozen'] >= 40 and W(r, P1 + 0x76) == hp
        print(f'ice blast: Kano held dazed {st["frozen"]} frames, health {hp} -> {W(r, P1 + 0x76)} -> frozen {frozen}')
        play(c, [((), 120)])
        # the slide, from close: walk in, then back + LK + HK
        def close(r):
            return abs(W(r, P1 + 0x4E) - W(r, P2 + 0x4E)) < 110
        for _ in range(240):
            if close(c.prg_ram()):
                break
            c.buttons[1] = {'left'}
            c.run(1)
        play(c, [((), 4)])
        hp = W(c.prg_ram(), P1 + 0x76)
        st2 = {'down': False}
        def kd(r):
            st2['down'] |= MOVE(r, P1) == 0x1C
        play(c, [({'right', 'a', 'b'}, 4), ((), 90)], watch=kd)
        r = c.prg_ram()
        slid = st2['down'] and W(r, P1 + 0x76) < hp
        print(f'slide: Kano knocked down {st2["down"]}, health {hp} -> {W(r, P1 + 0x76)} -> {slid}')
        # the spear, from ~125 px
        play(c, [((), 150)])
        for _ in range(300):
            r = c.prg_ram()
            d = W(r, P2 + 0x4E) - W(r, P1 + 0x4E)
            if d < 125:
                break
            c.buttons[1] = {'left'} if d > 125 else {'right'}
            c.run(1)
        play(c, [((), 20)])
        r = c.prg_ram()
        hp, far = W(r, P1 + 0x76), W(r, P2 + 0x4E) - W(r, P1 + 0x4E)
        st3 = {'near': 999, 'daze': 0, 'run': 0, 'stood': False}
        def sp(r):
            st3['near'] = min(st3['near'], abs(W(r, P2 + 0x4E) - W(r, P1 + 0x4E)))
            st3['run'] = st3['run'] + 1 if MOVE(r, P1) == 0x1F else 0
            st3['daze'] = max(st3['daze'], st3['run'])
            st3['stood'] |= st3['daze'] > 0 and MOVE(r, P1) == 0
        play(c, [({'right'}, 3), ((), 2), ({'right'}, 3), ({'x'}, 4), ((), 240)], watch=sp)
        r = c.prg_ram()
        speared = (W(r, P1 + 0x76) < hp and st3['near'] <= 60 and 60 <= st3['daze'] <= 110 and st3['stood'])
        print(f'spear from {far} px: health {hp} -> {W(r, P1 + 0x76)}, pulled to {st3["near"]} px, '
              f'dazed {st3["daze"]} frames, stands again {st3["stood"]} -> {speared}')
        ok = ok and bottom and frozen and slid and speared
        # the CPU's Reptile (mk_fidelity_spec 1: MK's throws ~4.5 projectiles a minute, spear
        # and freeze): 120 s against a standing Kano (which he throws depends on how near he
        # stands: the spear only within its reach)
        cpu = os.path.join(tmp, 'cpu.state')
        subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', a.disc,
                        '--p1', str(KANO_GRID), '--cpu', '--p2', '0', '--p2-id', str(REPTILE_ID), '--stage', '1F',
                        '--out', cpu], check=True, capture_output=True)
        c.load_state(cpu)
        n, prev, same, still, pf = {0x31: 0, 0x34: 0, 0x35: 0}, 0, 0, 0, None
        for t in range(7200):                  # (the round's 99 s clock runs out near the end:
            c.poke_prg(P1 + 0x76, (104).to_bytes(2, 'big'))   #  stills are counted in the first 90 s)
            c.run(1)
            mv = MOVE(c.prg_ram(), P2)
            if mv != prev and mv in n:
                n[mv] += 1
            prev = mv
            fr = c.frame.tobytes()
            same = same + 1 if fr == pf else 0
            pf = fr
            if t < 5400:
                still = max(still, same)
        busy = 4 <= n[0x31] + n[0x34] <= 16 and n[0x31] and n[0x34] and still < 60
        print(f'CPU 120 s: ice {n[0x31]}, spear {n[0x34]}, slide {n[0x35]}, longest still picture {still} -> {bool(busy)}')
        ok = ok and busy
        # round 2 starts (Reptile couldn't walk and the clock stood still: his timed
        # specials, forced in the round's intro, held it there): Kano loses round 1, then in
        # round 2 the clock counts down and Reptile comes toward him
        import mkinputs
        c.load_state(cpu)
        c.poke_prg(P1 + 0x76, (1).to_bytes(2, 'big'))
        L = lambda r, o: int.from_bytes(r[o:o + 4], 'big')
        ko = False
        for _ in range(4000):
            c.run(1)
            r = c.prg_ram()
            ko |= W(r, P1 + 0x76) <= 0
            if ko and W(r, P1 + 0x76) >= 100 and W(r, P2 + 0x76) >= 100:
                break
        x0 = W(r, P2 + 0x4E)
        c.run(900)
        r = c.prg_ram()
        clock = W(r, L(r, A6 + mkinputs.CLOCK_OBJ) + mkinputs.CLOCK_TIME)
        moved = abs(W(r, P2 + 0x4E) - x0)
        r2 = ko and clock < 0x99 and moved > 40
        print(f'round 2: clock {clock:X} (BCD) after 15 s, Reptile moved {moved} px -> {r2}')
        ok = ok and r2
        print('reptile:', 'ok' if ok else 'FAILED')
        sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
