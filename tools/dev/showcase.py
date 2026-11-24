#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Record a shareable clip of an MK fighter's moves against Shadow (with sound).

From his duel state (build/states/duel_shadow.state for Scorpion, duel_FIGHTER.state
for the others; tools/lib/duelstate.py --p2 0 --out ...), or --state. Shadow stands
still (no input, so she never blocks). Scorpion, with EC's buttons (X/Y/Z punches,
A/B/C kicks): walk in and out (MK's walk, both ways), his normals, the throw,
straight-up jump + low kick (A), straight-up jump + high kick (C), the flying jump
kick (forward jump + C, knocks down), the sweep (down + C), the teleport punch
(down, back + Y) twice: with her away from the far edge (he comes in at the edge and
misses) and near it (hit). The others: the walk, their normals, their MK specials and
the throw. Every fighter ends with Shadow punching him (his MK hit reaction); Sub-Zero
and Johnny Cage then do their fatality.

    showcase.py [--fighter scorpion|raiden|johnny|subzero|liukang|kano|sonya] [--out build/shots/FIGHTER_moves.mp4] [--state FILE]
"""
import argparse, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
from scd import Core
from inputs import ROOT
from finishvideo import Rec, w, x, P1, P2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fighter', default='scorpion', choices=('scorpion', 'raiden', 'johnny', 'subzero', 'liukang', 'kano', 'sonya'))
    ap.add_argument('--out')
    ap.add_argument('--state', help='duel state to start from (default: the fighter\'s)')
    a = ap.parse_args()
    a.out = a.out or os.path.join(ROOT, 'build', 'shots', f'{a.fighter}_moves.mp4')
    c = Core(audio=True, saves=os.path.join(ROOT, 'build', 'shots', 'record-saves'))
    c.load(os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    c.load_state(a.state or os.path.join(ROOT, 'build', 'states', 'duel_shadow.state' if a.fighter == 'scorpion'
                                         else f'duel_{a.fighter}.state'))
    c.run(20)
    c.audio.clear()
    r = Rec(c, a.out)
    marks = []

    def gap():
        m = r.ram()
        return x(m, P2) - x(m, P1)

    def settle(limit=150):
        """Until both stand (and Shadow is back up)."""
        for _ in range(limit):
            m = r.ram()
            if w(m, P1 + 0xBE) & 0x7FFF == 0 and w(m, P2 + 0xBE) & 0x7FFF == 0:
                break
            r.run(1)
        r.run(20)

    def to(dist, limit=300):
        for _ in range(limit):
            g = abs(gap())
            if abs(g - dist) <= 6:
                break
            toward = 'right' if gap() > 0 else 'left'
            away = 'left' if toward == 'right' else 'right'
            r.run(1, [toward] if g > dist else [away])
        r.run(10)

    def move(name, steps, after=90):
        """steps' 'back'/'fwd' are relative to where Shadow is."""
        marks.append((name, r.frames))
        fwd = 'right' if gap() > 0 else 'left'
        rel = {'fwd': fwd, 'back': 'left' if fwd == 'right' else 'right'}
        for held, n in steps:
            r.run(n, [rel.get(b, b) for b in held])
        r.run(after)
        settle()

    r.run(30)
    marks.append(('walk', r.frames))
    r.run(80, ['right'])                                   # walk in
    r.run(60, ['left'])                                    # and back
    r.run(20)
    if a.fighter != 'scorpion':
        # the other MK fighters: their normals, then their specials
        to(60)
        move('punches', [(['x'], 4), ([], 14), (['y'], 4), ([], 20)])
        to(60)
        move('kicks', [(['a'], 4), ([], 14), (['c'], 4), ([], 20)])
        to(55)
        move('uppercut', [(['down'], 8), (['down', 'y'], 4), (['down'], 6)], after=100)
        to(55)
        move('sweep', [(['down'], 6), (['down', 'c'], 4), (['down'], 8)], after=100)
        to(70)
        move('jump kick', [(['up'], 4), ([], 12), (['c'], 4)])
        if a.fighter == 'johnny':
            to(60)
            move('split punch (down + B)', [(['down'], 6), (['down', 'b'], 4), (['down'], 30)], after=60)
        # MK1's special inputs (mkinputs.GENERIC_MOVES); EC: X = MK low punch, A = low kick
        specials = {
            'raiden': [('lightning (down, forward + X)', [(['down'], 3), ([], 2), (['fwd'], 3), (['x'], 4)], 100),
                       ('torpedo (back, back, forward)', [(['back'], 3), ([], 2), (['back'], 3), ([], 2), (['fwd'], 3)], 200),
                       ('teleport (down, up)', [(['down'], 3), ([], 2), (['up'], 3)], 150)],
            'johnny': [('green bolt (back, forward + X)', [(['back'], 3), ([], 2), (['fwd'], 3), (['x'], 4)], 100),
                       ('shadow kick (back, forward + A)', [(['back'], 3), ([], 2), (['fwd'], 3), (['a'], 4)], 200)],
            'subzero': [('ice blast (down, forward + X): she freezes', [(['down'], 3), ([], 2), (['fwd'], 3), (['x'], 4)], 100),
                        ('slide (back + A + B)', [(['back'], 4), (['back', 'a', 'b'], 4)], 150)],
            'liukang': [('fireball (forward, forward + Y)', [(['fwd'], 3), ([], 2), (['fwd'], 3), (['y'], 4)], 100),
                        ('flying kick (forward, forward + B)', [(['fwd'], 3), ([], 2), (['fwd'], 3), (['b'], 4)], 200)],
            'kano': [('knife (hold Z, back, forward)', [(['z'], 12), (['z', 'back'], 6), (['z'], 3),
                                                       (['z', 'fwd'], 6)], 100),
                     ('cannonball (forward, down, back, up)', [(['fwd'], 3), ([], 2), (['down'], 3), ([], 2), (['back'], 3),
                                                               ([], 2), (['up'], 3)], 200)],
            'sonya': [('energy rings (Y, back, Y)', [(['y'], 4), ([], 2), (['back'], 4), ([], 2), (['y'], 4)], 100),
                      ('square-wave flight (forward, back + Y)', [(['fwd'], 3), ([], 2), (['back'], 3), (['y'], 4)], 200),
                      ('leg grab (close: down + X + A + Z)', [(['down', 'x', 'a', 'z'], 6)], 45)],
        }[a.fighter]
        for name, steps, dist in specials:
            to(dist)
            move(name, steps, after=240 if 'freezes' in name else 120)
        to(30)
        move('throw (close, B)', [(['b'], 4)], after=120)
    else:
        for name, b in (('low punch (X)', 'x'), ('high punch (Y)', 'y'), ('low kick (A)', 'a'),
                        ('high kick (B)', 'b'), ('roundhouse (C)', 'c')):
            to(70 if b == 'b' else 55)       # (B nearer than that is the throw)
            move(name + ': MK\'s full animation', [([b], 4), ([], 40)], after=30)
        for name, b in (('crouch: uppercut (down + Y)', 'y'), ('crouch: low kick (down + A)', 'a')):
            to(50)
            move(name, [(['down'], 8), (['down', b], 4), (['down'], 30)], after=60)
        to(30)
        move('throw (close, B): MK\'s roll throw, she lands behind him', [(['b'], 4)], after=120)
        to(70)
        move('jump + low kick', [(['up'], 4), ([], 12), (['a'], 4)])
        to(70)
        move('jump + high kick', [(['up'], 4), ([], 12), (['c'], 4)])
        to(150)
        move('flying jump kick', [(['up', 'fwd'], 4), ([], 10), (['c'], 4)], after=150)
        to(55)
        move('sweep', [(['down'], 6), (['down', 'c'], 4), (['down'], 8)], after=120)
        to(160)
        move('teleport punch (she is not by the far edge: a miss)', [(['down'], 3), ([], 2), (['back'], 3), (['y'], 4)], after=90)
        to(250)
        move('teleport punch (she is by the far edge: it hits)', [(['down'], 3), ([], 2), (['back'], 3), (['y'], 4)], after=150)
    # him getting hit: Shadow (player 2) punches him three times
    to(45)
    marks.append(('hit by Shadow: MK\'s hit reaction', r.frames))
    for _ in range(3):
        c.buttons[1] = {'y'}
        r.run(4)
        c.buttons[1] = set()
        r.run(50)
    FATAL_INPUT = {'subzero': ('fwd', 'down', 'fwd'),       # the spine rip
                   'johnny': ('fwd', 'fwd', 'fwd')}         # the decapitation uppercut
    if a.fighter in FATAL_INPUT:
        # his fatality: a deciding round, she's down to 3 health, his punch
        # leaves her dazed (FINISH HER), then his taps + Y up close
        c.poke_prg(0x31D26, (1).to_bytes(2, 'big'))
        c.poke_prg(0x31D28, (1).to_bytes(2, 'big'))
        c.poke_prg(P2 + 0x76, (3).to_bytes(2, 'big'))
        to(45)
        marks.append(('fatality: FINISH HER, then ' + ', '.join(FATAL_INPUT[a.fighter]) + ' + Y', r.frames))
        r.run(4, ['y'])
        r.run(80)
        t1, t2, t3 = FATAL_INPUT[a.fighter]
        for held, n in (([t1], 3), ([], 2), ([t2], 3), ([], 2), ([t3], 3), ([t3, 'y'], 3)):
            fwd = 'right' if x(r.ram(), P2) > x(r.ram(), P1) else 'left'
            r.run(n, [fwd if h == 'fwd' else h for h in held])
        r.run(420)
    r.run(30)
    r.close()
    for name, f in marks:
        print(f'{f / c.fps:6.1f}s  {name}')
    print(f'{r.frames / c.fps:.1f}s -> {os.path.relpath(a.out, ROOT)}')


if __name__ == '__main__':
    main()
