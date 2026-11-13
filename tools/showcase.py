#!/usr/bin/env python3
"""Record a shareable clip of Scorpion's moves against Shadow (with sound).

From states/duel_shadow.state (tools/duelstate.py --p2 0 --out
states/duel_shadow.state). Shadow stands still (no input, so she never
blocks). Scorpion, with EC's buttons (X/Y/Z punches, A/B/C kicks):
  walk in and out (MK's walk, both ways), straight-up jump + low kick (A),
  straight-up jump + high kick (C), the flying jump kick (forward jump + C,
  knocks down), the sweep (down + C), the teleport punch (down, back + Y) twice: with her
  away from the far edge (he comes in at the edge and misses) and near it (hit).
Every fighter ends with Shadow punching him (his MK hit reaction); the
others also throw.

    showcase.py [--out shots/scorpion_moves.mp4]
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scd import Core
from inputs import ROOT
from finishvideo import Rec, w, x, P1, P2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fighter', default='scorpion', choices=('scorpion', 'raiden', 'johnny', 'subzero'))
    ap.add_argument('--out')
    ap.add_argument('--state', help='duel state to start from (default: the fighter\'s)')
    a = ap.parse_args()
    a.out = a.out or os.path.join(ROOT, 'shots', f'{a.fighter}_moves.mp4')
    c = Core(audio=True, saves=os.path.join(ROOT, 'shots', 'record-saves'))
    c.load(os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    c.load_state(a.state or os.path.join(ROOT, 'states', 'duel_shadow.state' if a.fighter == 'scorpion'
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
        # first versions: Blade's moves with the fighter's MK poses
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
            move('split punch (down + Z)', [(['down'], 6), (['down', 'z'], 4), (['down'], 30)], after=60)
        # MK1's special inputs (mkinputs.GENERIC_MOVES); EC: X = MK low punch, A = low kick
        specials = {
            'raiden': [('lightning (down, forward + X)', [(['down'], 3), ([], 2), (['fwd'], 3), (['x'], 4)], 100),
                       ('torpedo (back, back, forward)', [(['back'], 3), ([], 2), (['back'], 3), ([], 2), (['fwd'], 3)], 200),
                       ('teleport (down, up)', [(['down'], 3), ([], 2), (['up'], 3)], 150)],
            'johnny': [('green bolt (back, forward + X)', [(['back'], 3), ([], 2), (['fwd'], 3), (['x'], 4)], 100),
                       ('shadow kick (back, forward + A)', [(['back'], 3), ([], 2), (['fwd'], 3), (['a'], 4)], 200)],
            'subzero': [('ice blast (down, forward + X): she freezes', [(['down'], 3), ([], 2), (['fwd'], 3), (['x'], 4)], 100),
                        ('slide (back + A + B)', [(['back'], 4), (['back', 'a', 'b'], 4)], 150)],
        }[a.fighter]
        for name, steps, dist in specials:
            to(dist)
            move(name, steps, after=240 if 'freezes' in name else 120)
        to(30)
        move('throw (close, toward + Y)', [(['fwd', 'y'], 4)], after=120)
    else:
        for name, b in (('low punch (X)', 'x'), ('high punch (Y)', 'y'), ('low kick (A)', 'a'),
                        ('high kick (B)', 'b'), ('roundhouse (C)', 'c')):
            to(55)
            move(name + ': MK\'s full animation', [([b], 4), ([], 40)], after=30)
        for name, b in (('crouch: uppercut (down + Y)', 'y'), ('crouch: low kick (down + A)', 'a')):
            to(50)
            move(name, [(['down'], 8), (['down', b], 4), (['down'], 30)], after=60)
        to(30)
        move('throw (close, toward + Y): MK\'s roll throw, she lands behind him', [(['fwd', 'y'], 4)], after=120)
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
    if a.fighter == 'subzero':
        # his spine rip: a deciding round, she's down to 3 health, his punch
        # leaves her dazed (FINISH HER), then forward, down, forward + Y up close
        c.poke_prg(0x31D26, (1).to_bytes(2, 'big'))
        c.poke_prg(0x31D28, (1).to_bytes(2, 'big'))
        c.poke_prg(P2 + 0x76, (3).to_bytes(2, 'big'))
        to(45)
        marks.append(('fatality: FINISH HER, then forward, down, forward + Y', r.frames))
        r.run(4, ['y'])
        r.run(80)
        for held, n in ((['fwd'], 3), ([], 2), (['down'], 3), ([], 2), (['fwd'], 3), (['fwd', 'y'], 3)):
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
