#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""How does an MK fighter take a hit? (the receiving side of mk_engine_plan)

Player 1 (an EC fighter, Shadow by default) walks up to player 2 (the MK fighter, standing still)
and does one attack; player 2's frame is recorded every frame from the hit and named by the MK
animation its art comes from (mkcompare.art_map), with how far he was pushed and the health lost.
Beside it: MK's own reaction to that kind of hit (the capture's frames from his first pose off the
stance to the stance again).

    hitaudit.py FIGHTER [--attacker 0] [--frames 120]
"""
import argparse, itertools, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT

P1, P2 = 0x2E188, 0x2E330
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big', signed=True)
# attack -> (player 1's pad presses [(buttons, frames)], MK capture of the victim's reaction)
ATTACKS = {
    'jab (X)': ([({'x'}, 4)], 'hit_high'),
    'high punch (Y)': ([({'y'}, 4)], 'hit_high'),
    'low kick (A)': ([({'a'}, 4)], 'hit_kick'),
    'high kick (B)': ([({'b'}, 4)], 'hit_kick'),
    'roundhouse (C)': ([({'c'}, 4)], 'knockdown'),
    'uppercut (down+Y)': ([({'down'}, 8), ({'down', 'y'}, 4), ({'down'}, 20)], 'knockdown'),
    'sweep (down+C)': ([({'down'}, 8), ({'down', 'c'}, 4), ({'down'}, 20)], 'swept'),
    'crouch kick (down+A)': ([({'down'}, 8), ({'down', 'a'}, 4), ({'down'}, 20)], 'hit_low'),
}


def mk_reaction(mk_dir, action):
    import numpy as np, scorpion_full as sf
    d = os.path.join(ROOT, 'extracted', mk_dir, action)
    if not os.path.exists(os.path.join(d, 'order.txt')):
        return None
    order = [int(v) for v in open(os.path.join(d, 'order.txt')).read().split()]
    poses = np.load(os.path.join(d, 'indexed.npy'), mmap_mode='r')
    lead = sf.stance_lead(poses) if len(poses) >= 3 else 0
    t0 = next((i for i, k in enumerate(order) if k >= lead), 0)
    t1 = len(order)
    while t1 > t0 and order[t1 - 1] < lead:
        t1 -= 1
    seq = order[t0:t1]
    return len(seq), ' '.join(f'{k}x{len(list(g))}' for k, g in itertools.groupby(seq))


def main():
    import patches, mkcompare
    ap = argparse.ArgumentParser()
    ap.add_argument('fighter')
    ap.add_argument('--attacker', type=int, default=0, help='player 1: right presses on the select grid (0 Shadow)')
    ap.add_argument('--frames', type=int, default=120)
    a = ap.parse_args()
    spec = next(s for s in patches.MK_SPECS if s.key == a.fighter)
    amap = mkcompare.art_map(spec)
    with tempfile.TemporaryDirectory() as tmp:
        st = os.path.join(tmp, 'duel.state')
        subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'),
                        '--p1', str(a.attacker), '--p2', str(mkcompare.GRID[spec.key]), '--stage', '11', '--out', st],
                       check=True, capture_output=True)
        c = scd.Core(saves=os.path.join(tmp, 'saves'))
        c.load(os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
        c.load_state(st)
        c.run(30)
        c.buttons[0] = {'right'}                       # walk in
        for _ in range(300):
            c.run(1)
            r = c.prg_ram()
            if abs(W(r, P2 + 0x4E) - W(r, P1 + 0x4E)) < 75:
                break
        c.buttons[0] = set()
        c.run(30)
        snap = c.snapshot()
        for name, (presses, cap) in ATTACKS.items():
            c.restore(snap)
            r = c.prg_ram()
            h0, x0 = W(r, P2 + 0x76), W(r, P2 + 0x4E)
            seq, hit_at, t = [], None, 0
            for b, n in presses + [(set(), a.frames)]:
                c.buttons[0] = set(b)
                for _ in range(n):
                    c.run(1)
                    r = c.prg_ram()
                    if hit_at is None and W(r, P2 + 0x76) < h0:
                        hit_at = t
                    if hit_at is not None:
                        f = W(r, P2 + 0x1A) & 0xFFFF
                        seq.append(amap.get(f, ('?', f))[0] if f in amap else f'?{f:04x}')
                    t += 1
            r = c.prg_ram()
            mk = mk_reaction(spec.mk_dir, cap)
            print(f'{name:22s} ' + ('no hit' if hit_at is None else
                  f'-{h0 - W(r, P2 + 0x76)} hp, pushed {abs(W(r, P2 + 0x4E) - x0)} px: '
                  + ' '.join(f'{k}:{len(list(g))}' for k, g in itertools.groupby(seq))))
            if mk:
                print(f'{"":22s} MK {cap}: {mk[0]} frames: {mk[1]}')


if __name__ == '__main__':
    main()
