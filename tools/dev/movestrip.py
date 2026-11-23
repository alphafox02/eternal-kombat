#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Real frames of one move, side by side, to look at.

Player 1 (an MK fighter) against player 2 (Shadow by default, standing still) on the stage's floor; the
pad inputs are held as given and the frames from..to (every EVERY) are saved side by side, full screen
height (a horizontal crop only: nothing above or below is cut off), enlarged, each labelled with its
frame number and player 1's frame word ($1A).

    movestrip.py FIGHTER OUT.png --hold up+right:0-12 --hold b:6-10 [--from 0 --to 60 --every 3]
                 [--x0 0 --x1 320] [--scale 2] [--p2 0] [--close] [--state FILE]
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT

P1, P2 = 0x2E188, 0x2E330
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big')


def main():
    from PIL import Image, ImageDraw
    import mkcompare
    ap = argparse.ArgumentParser()
    ap.add_argument('fighter')
    ap.add_argument('out')
    ap.add_argument('--hold', action='append', default=[], help='buttons:from-to, e.g. up+right:0-12')
    ap.add_argument('--from', dest='t0', type=int, default=0)
    ap.add_argument('--to', dest='t1', type=int, default=60)
    ap.add_argument('--every', type=int, default=3)
    ap.add_argument('--x0', type=int, default=0)
    ap.add_argument('--x1', type=int, default=320)
    ap.add_argument('--scale', type=int, default=2)
    ap.add_argument('--p2', type=int, default=0, help='player 2: right presses on the select grid')
    ap.add_argument('--close', action='store_true', help='walk up to player 2 first')
    ap.add_argument('--swap', action='store_true', help='the MK fighter is player 2 (player 1 = --p2 attacks)')
    ap.add_argument('--state', help='start from this state instead of a new duel')
    a = ap.parse_args()
    holds = []
    for h in a.hold:
        b, _, span = h.partition(':')
        f, _, t = span.partition('-')
        holds.append((set(b.split('+')), int(f), int(t)))
    with tempfile.TemporaryDirectory() as tmp:
        st = a.state
        if not st:
            st = os.path.join(tmp, 'duel.state')
            mk, other = str(mkcompare.GRID[a.fighter]), str(a.p2)
            p1, p2 = (other, mk) if a.swap else (mk, other)
            subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--p1', p1,
                            '--p2', p2, '--stage', '11', '--out', st], check=True, capture_output=True)
        c = scd.Core(saves=os.path.join(tmp, 'saves'))
        c.load(os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
        c.load_state(st)
        c.run(30)
        if a.close:
            c.buttons[0] = {'right'}
            for _ in range(300):
                c.run(1)
                r = c.prg_ram()
                if abs(W(r, P2 + 0x4E) - W(r, P1 + 0x4E)) < 70:
                    break
            c.buttons[0] = set()
            c.run(20)
        me = P2 if a.swap else P1
        tiles = []
        for t in range(a.t1 + 1):
            c.buttons[0] = set().union(*[b for b, f, to in holds if f <= t < to])
            c.run(1)
            if t >= a.t0 and (t - a.t0) % a.every == 0:
                img = Image.fromarray(c.frame[:, a.x0:a.x1])
                img = img.resize((img.width * a.scale, img.height * a.scale), Image.NEAREST)
                d = ImageDraw.Draw(img)
                d.rectangle((0, 0, 110, 12), fill=(0, 0, 0))
                d.text((2, 1), f'{t} {W(c.prg_ram(), me + 0x1A):04X}', fill=(255, 255, 0))
                tiles.append(img)
        w, h = tiles[0].size
        sheet = Image.new('RGB', (w * len(tiles) + 2 * (len(tiles) - 1), h), (255, 0, 255))
        for i, im in enumerate(tiles):
            sheet.paste(im, (i * (w + 2), 0))
        sheet.save(a.out)
        print(a.out, sheet.size)


if __name__ == '__main__':
    main()
