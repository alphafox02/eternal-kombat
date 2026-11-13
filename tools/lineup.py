#!/usr/bin/env python3
"""Every fighter standing side by side, as the game draws them (player 1's
sprites only, bottom-aligned, standing height in px under each), to judge the
MK fighters' size against EC's.

    lineup.py [--presses 0-16 | --presses 1,2,8] [--victory] [--out shots/lineup.png] [--label TEXT]

--victory: each fighter wins the round (the opponent is left on 1 health and
jabbed) and the tallest frame of the win is drawn: EC's stances crouch, their
victory poses stand upright.

Makes a duel state per fighter (tools/duelstate.py --p1 N --p2 0) in a
scratch folder, renders, deletes the states.
"""
import argparse, os, subprocess, sys, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image, ImageDraw
import scd
from vdp import VDPState
from inputs import ROOT

P1 = 0x2E188
MK = {23: 'SCORPION', 19: 'RAIDEN', 18: 'JOHNNY', 20: 'SUB-ZERO'}


def figure(c):
    r = c.prg_ram()
    fid = int.from_bytes(r[P1 + 0x4C:P1 + 0x4E], 'big')
    line = (int.from_bytes(r[P1 + 0x7A:P1 + 0x7C], 'big') & 3) ^ 1
    v = VDPState(c.snapshot())
    pal = np.array([v.palette(line)[i] for i in range(16)], np.uint8)
    canvas = np.zeros((240, 340, 4), np.uint8)
    for s in reversed([s for s in v.sprites() if s['pal'] == line]):
        px = v.sprite_pixels(s)
        ys, xs = np.nonzero(px)
        Y, X = ys + s['y'], xs + s['x']
        ok = (Y >= 0) & (Y < 240) & (X >= 0) & (X < 340)
        canvas[Y[ok], X[ok], :3] = pal[px[ys[ok], xs[ok]]]
        canvas[Y[ok], X[ok], 3] = 255
    ys, xs = np.nonzero(canvas[:, :, 3])
    return fid, canvas[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def victory(c):
    """Win the round (player 2 on 1 health, walk up and jab until he is down)
    and return the tallest frame player 1 shows in the next 8 seconds."""
    P2 = 0x2E330
    x = lambda r, o: int.from_bytes(r[o + 0x4E:o + 0x50], 'big', signed=True)
    c.poke_prg(P2 + 0x76, (1).to_bytes(2, 'big'))
    for _ in range(400):
        r = c.prg_ram()
        if int.from_bytes(r[P2 + 0x76:P2 + 0x78], 'big', signed=True) <= 0:
            break
        c.buttons[0] = {'right'} if abs(x(r, P2) - x(r, P1)) > 50 else ({'x'} if c.frames % 8 < 4 else set())
        c.run(1)
    c.buttons[0] = set()
    best = None
    for i in range(480):
        c.run(1)
        if i % 4:
            continue
        try:
            f = figure(c)
        except ValueError:
            continue
        if best is None or f[1].shape[0] > best[1].shape[0]:
            best = f
    return best


def render(figs, label=''):
    H = max(f.shape[0] for _, f in figs) + 30 + (14 if label else 0)
    W = sum(f.shape[1] + 8 for _, f in figs) + 8
    img = Image.new('RGB', (W, H), (40, 40, 60))
    d = ImageDraw.Draw(img)
    if label:
        d.text((8, 2), label, fill=(255, 255, 255))
    x = 8
    for fid, f in figs:
        im = Image.fromarray(f, 'RGBA')
        img.paste(im, (x, H - 20 - f.shape[0]), im)
        d.text((x, H - 16), f"{MK.get(fid, 'EC ' + str(fid))} {f.shape[0]}",
               fill=(255, 255, 0) if fid in MK else (200, 200, 200))
        x += f.shape[1] + 8
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--presses', default='0-16')
    ap.add_argument('--out', default=os.path.join(ROOT, 'shots', 'lineup.png'))
    ap.add_argument('--label', default='')
    ap.add_argument('--victory', action='store_true')
    a = ap.parse_args()
    if ',' in a.presses:
        presses = [int(x) for x in a.presses.split(',')]
    else:
        lo, _, hi = a.presses.partition('-')
        presses = range(int(lo), int(hi or lo) + 1)
    tmp = tempfile.mkdtemp()
    c = scd.Core(saves=os.path.join(ROOT, 'shots', 'probe-saves'))
    c.load(os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    figs = []
    try:
        for n in presses:
            st = os.path.join(tmp, f'{n}.state')
            subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'duelstate.py'),
                            '--p1', str(n), '--p2', '0', '--out', st], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            c.load_state(st)
            c.run(30)
            if not a.victory:
                figs.append(figure(c))
                continue
            figs.append(victory(c))
    finally:
        shutil.rmtree(tmp)
    img = render(figs, a.label)
    img.resize((img.width * 2, img.height * 2), Image.NEAREST).save(a.out)
    for fid, f in figs:
        print(MK.get(fid, f'EC {fid}'), f.shape[0])
    print('->', os.path.relpath(a.out, ROOT))


if __name__ == '__main__':
    main()
