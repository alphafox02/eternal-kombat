#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Sonya's square wave at MK's height: over a standing opponent, into a jumping one.

MK CD (Sonya vs a standing Sub-Zero): she rises, flies over his head unhit and
lands behind him; an opponent jumping into her is hit. From a 2-player duel
(Sonya vs Shadow, made here with tools/lib/duelstate.py):
  - Shadow standing: no damage, Sonya at least LIFT px over the floor, back on
    it afterwards;
  - Shadow jumping toward her as she takes off: damaged;
  - Shadow hits her with a light attack or a knockdown: she stays airborne,
    lands, and can walk again.

    squarewavecheck.py [--as-p2] [--state STATE]
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT

P1, P2 = 0x2E188, 0x2E330
LIFT = 100                     # px: her flight is ~119 over the floor (mkinputs.SQ_LIFT)
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big')


def attempt(state, port, jump):
    me, him = (P1, P2) if port == 0 else (P2, P1)
    c = scd.Core()
    c.load(os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    c.load_state(state)
    c.run(20)
    r = c.prg_ram()
    fwd = 'right' if W(r, him + 0x4E) > W(r, me + 0x4E) else 'left'
    back = 'left' if fwd == 'right' else 'right'
    floor = W(r, me + 0x52)
    for held, n in (([fwd], 3), ([], 2), ([back], 3), (['y'], 4)):     # forward, back + Y (MK: F, B + HP)
        c.buttons[port] = set(held)
        c.run(n)
    c.buttons[port] = set()
    hp, top = W(c.prg_ram(), him + 0x76), floor
    for f in range(120):
        c.buttons[1 - port] = {'up', back} if jump and f < 4 else set()   # (toward her)
        c.run(1)
        r = c.prg_ram()
        top = min(top, W(r, me + 0x52))
    r = c.prg_ram()
    return hp - W(r, him + 0x76), floor - top, W(r, me + 0x52) == floor


def interrupted(state, port, attack):
    """A jumping Shadow hits Sonya in flight; track her descent and recovery."""
    me = P2 if port else P1
    c = scd.Core()
    c.load(os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    c.load_state(state)
    c.run(20)
    floor = W(c.prg_ram(), me + 0x52)
    fwd, back = ('left', 'right') if port else ('right', 'left')
    for held, n in (([fwd], 3), ([], 2), ([back], 3), (['y'], 4)):
        c.buttons[port] = set(held)
        c.run(n)
    c.buttons[port] = set()
    hp = W(c.prg_ram(), me + 0x76)
    heights, knocked_down = [], False
    for f in range(110):
        c.buttons[1 - port] = {'up', back} if f < 4 else {attack} if 10 <= f < 15 else set()
        c.run(1)
        r = c.prg_ram()
        if W(r, me + 0x76) < hp:
            heights.append(W(r, me + 0x52))
            knocked_down |= W(r, me + 0xBE) & 0x7FFF == 0x1C
    c.buttons = [set(), set()]
    c.run(10)
    x = W(c.prg_ram(), me + 0x4E)
    c.buttons[port] = {fwd}
    c.run(15)
    walk = abs(W(c.prg_ram(), me + 0x4E) - x)
    jumps = [b - a for a, b in zip(heights, heights[1:])]
    return bool(heights), knocked_down, floor in heights, max(jumps, default=0), walk


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--as-p2', action='store_true', help='Sonya is player 2')
    ap.add_argument('--state', help='a duel state (default: made now)')
    a = ap.parse_args()
    port = int(a.as_p2)
    state = a.state
    if not state:
        state = os.path.join(tempfile.mkdtemp(), 'duel.state')
        p1, p2 = ('0', '16') if a.as_p2 else ('16', '0')
        subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'),
                        '--p1', p1, '--p2', p2, '--stage', '1B', '--out', state], check=True, capture_output=True)
    dmg, lift, landed = attempt(state, port, False)
    print(f'standing: damage {dmg}, lift {lift} px, back on the floor {landed}')
    jdmg, _, jlanded = attempt(state, port, True)
    print(f'jumping:  damage {jdmg}, back on the floor {jlanded}')
    results = [interrupted(state, port, attack) for attack in ('x', 'b')]
    for attack, (hit, knocked_down, hit_landed, jump, walk) in zip(('x', 'b'), results):
        print(f'interrupted ({attack}): hit {hit}, knockdown {knocked_down}, landed {hit_landed}, '
              f'largest drop {jump} px, walk {walk} px')
    ok = (dmg == 0 and lift >= LIFT and landed and jdmg > 0 and jlanded
          and all(hit and knocked_down and hit_landed and jump <= 24 and walk >= 4
                  for hit, knocked_down, hit_landed, jump, walk in results))
    print('square wave ->', 'ok' if ok else 'FAILED')
    if not a.state:
        os.remove(state)
        os.rmdir(os.path.dirname(state))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
