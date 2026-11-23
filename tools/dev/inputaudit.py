#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""What does each direction + button do for the MK fighters?

For one MK fighter (player 1, the stage's floor, player 2 Shadow standing still): every pad
direction (none, toward, away, down, down-toward, down-away, up, up-toward) with every button
(EC's X Y Z A B C), far and close; each run records player 1's frame every frame for FRAMES
frames and names it by the MK animation (capture) its art comes from (mkcompare.art_map).
Printed per combination: the animations in the order shown (repeats collapsed), with the
frames each held; '?' = a frame no MK capture stands behind (Blade's art, a blank).

    inputaudit.py FIGHTER [--frames 70] [--range far|close|both] [--at 2] [--dirs down,d+fwd]
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT

P1, P2 = 0x2E188, 0x2E330
DIRS = [('-', set()), ('fwd', {'right'}), ('back', {'left'}), ('down', {'down'}),
        ('d+fwd', {'down', 'right'}), ('d+back', {'down', 'left'}), ('up', {'up'}), ('up+fwd', {'up', 'right'})]
BUTTONS = ['x', 'y', 'z', 'a', 'b', 'c']          # MK: LP HP Block LK HK roundhouse (ours)
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big')


def run(c, snap, held, button, frames, amap, close, at=2):
    c.restore(snap)
    if close:                                      # walk in until next to him
        c.buttons[0] = {'right'}
        for _ in range(240):
            c.run(1)
            r = c.prg_ram()
            if abs(W(r, P2 + 0x4E) - W(r, P1 + 0x4E)) < 70:
                break
        c.buttons[0] = set()
        c.run(20)
    seq = []
    for t in range(frames):
        b = set(held) if t < 30 else set()
        if at <= t < at + 4:
            b.add(button)
        c.buttons[0] = b
        c.run(1)
        f = W(c.prg_ram(), P1 + 0x1A)
        seq.append(amap.get(f, ('?', f))[0] if f in amap else f'?{f:04x}')
    out = []
    for a in seq:
        if out and out[-1][0] == a:
            out[-1][1] += 1
        else:
            out.append([a, 1])
    return out


def main():
    import patches, mkcompare
    ap = argparse.ArgumentParser()
    ap.add_argument('fighter')
    ap.add_argument('--frames', type=int, default=70)
    ap.add_argument('--range', default='both', choices=('far', 'close', 'both'))
    ap.add_argument('--at', type=int, default=2, help='frame the button goes down (the direction from 0)')
    ap.add_argument('--dirs', help='only these directions, e.g. down,d+fwd')
    a = ap.parse_args()
    spec = next(s for s in patches.MK_SPECS if s.key == a.fighter)
    amap = mkcompare.art_map(spec)
    with tempfile.TemporaryDirectory() as tmp:
        st = os.path.join(tmp, 'duel.state')
        subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'),
                        '--p1', str(mkcompare.GRID[spec.key]), '--p2', '0', '--stage', '11', '--out', st],
                       check=True, capture_output=True)
        c = scd.Core(saves=os.path.join(tmp, 'saves'))
        c.load(os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
        c.load_state(st)
        c.run(30)
        snap = c.snapshot()
        for close in ((False, True) if a.range == 'both' else (a.range == 'close',)):
            print(f'== {a.fighter} {"close" if close else "far"}')
            for dn, held in DIRS:
                if a.dirs and dn not in a.dirs.split(','):
                    continue
                for b in BUTTONS:
                    seq = run(c, snap, held, b, a.frames, amap, close, a.at)
                    print(f'{dn:7s} {b}: ' + ' '.join(f'{x}:{n}' for x, n in seq))


if __name__ == '__main__':
    main()
