#!/usr/bin/env python3
"""Record which sheet frames an EC fighter uses for each action, by playing
the actions in a 2-player duel (states/duel.state: P1 left facing right,
P2 right, both full health, fight live) and sampling P1's object.

    ecprobe.py [--obj 0x2E188] [--out extracted/ec_probe/blade.json]

Output: {action: [["40:12", count], ...]} in order of first appearance.
tools/scorpion_map.py uses it to pick the Scorpion action for each frame.
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scd
from inputs import ROOT

F, B = 'right', 'left'


def seq(*steps):
    return list(steps)


# action -> [(p1 buttons, p2 buttons, frames)]
ACTIONS = {
    'idle':        seq(([], [], 120)),
    'walk_fwd':    seq(([F], [], 60)),
    'walk_back':   seq(([B], [], 60)),
    'crouch':      seq((['down'], [], 40)),
    'jump_up':     seq((['up'], [], 4), ([], [], 60)),
    'jump_fwd':    seq((['up', F], [], 4), ([], [], 60)),
    'jump_back':   seq((['up', B], [], 4), ([], [], 60)),
    'projectile':  seq((['down'], [], 3), (['down', F], [], 3), ([F, 'c'], [], 4), ([], [], 60)),
    # P2 walks in and attacks; P1 stands, blocks (holds back) or crouch-blocks
    'hit_high':    seq(([], [B], 40), ([], ['y'], 4), ([], [], 50)),
    'hit_low':     seq(([], [B], 40), ([], ['down', 'x'], 4), ([], [], 50)),
    'hit_kick':    seq(([], [B], 40), ([], ['b'], 4), ([], [], 50)),
    'knockdown':   seq(([], [B], 40), ([], ['down', 'z'], 4), ([], [], 120)),
    'swept':       seq(([], [B], 40), ([], ['down', 'c'], 4), ([], [], 120)),
    'block':       seq(([B], [B], 40), ([B], ['y'], 4), ([B], [], 40)),
    'crouch_block': seq((['down', B], [B], 40), (['down', B], ['down', 'x'], 4), (['down', B], [], 40)),
}
for b in 'abcxyz':
    ACTIONS[f'btn_{b}'] = seq(([b], [], 4), ([], [], 50))
    ACTIONS[f'crouch_{b}'] = seq((['down'], [], 10), (['down', b], [], 4), (['down'], [], 40))
    ACTIONS[f'jump_{b}'] = seq((['up', F], [], 4), ([], [], 12), ([b], [], 4), ([], [], 50))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    ap.add_argument('--state', default=os.path.join(ROOT, 'states', 'duel.state'))
    ap.add_argument('--obj', type=lambda s: int(s, 0), default=0x2E188)
    ap.add_argument('--out', default=os.path.join(ROOT, 'extracted', 'ec_probe', 'blade.json'))
    a = ap.parse_args()
    c = scd.Core(saves=os.path.join(ROOT, 'shots', 'probe-saves'))
    c.load(a.disc)
    result = {}
    for name, steps in ACTIONS.items():
        c.load_state(a.state)
        c.run(20)                       # the duel state ignores input for a few frames
        counts, order = {}, []
        for p1, p2, n in steps:
            c.buttons[0], c.buttons[1] = set(p1), set(p2)
            for i in range(n):
                c.run(1)
                if i % 2:
                    continue
                r = c.prg_ram()
                k = f'{r[a.obj + 0x1A]:02x}:{r[a.obj + 0x1B]:02x}'
                if k not in counts:
                    counts[k] = 0
                    order.append(k)
                counts[k] += 1
        c.buttons = [set(), set()]
        result[name] = [[k, counts[k]] for k in order]
        print(f'{name:13s} {" ".join(order[:14])}')
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(result, open(a.out, 'w'), indent=1)
    print('->', os.path.relpath(a.out, ROOT))


if __name__ == '__main__':
    main()
