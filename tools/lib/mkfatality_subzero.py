#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Capture Sub-Zero's MK1 fatality (the spine rip) from the MK disc, frame by frame.

From build/states/mk_subzero_2p.state (Sub-Zero vs Scorpion): he wins two rounds
(the loser's health set low, one hit each), MK says FINISH HIM, he walks in and
does forward, down, forward + high punch (MK pad X). Then, frame by frame:

  fatality/         Sub-Zero (palette line 0): the grab, the pull, the head and spine held up
  fatality_victim/  the victim (line 1) as RGB: the headless body, the blood

Same layout as tools/lib/mkfatality.py (indexed.npy / rgb.npy, anchors.json,
order.txt, cram.json, contact.png).

    mkfatality_subzero.py          # capture, then the corpse and the held head
    mkfatality_subzero.py corpse   # only fatality_corpse/ and fatality_held/ (from the capture)
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import scd
from vdp import VDPState
from inputs import ROOT, require
from mkfatality import canvas, group, feet_anchor
from PIL import Image

OUT = os.path.join(ROOT, 'extracted', 'mk_moves_subzero')
HP_P1, HP_P2 = 0x7D6C4, 0x7D7CA
FRAMES = 420
INPUT = [('right', 4), ('', 2), ('down', 4), ('', 2), ('right', 4), ('right+x', 4)]


def start(c, state=None):
    """From the fight state to the first frame after the fatality's input
    (what main() then captures frame by frame)."""
    hp = lambda: tuple(int.from_bytes(c.prg_ram()[a:a + 2], 'big') for a in (HP_P1, HP_P2))

    def gap():
        v = VDPState(c.snapshot())
        out = {}
        for pal in (0, 1):
            x = [s['x'] for s in v.sprites() if s['pal'] == pal and 80 < s['y'] < 230]
            out[pal] = (min(x), max(x) + 16) if x else None
        return out[1][0] - out[0][1] if out[0] and out[1] else 99

    def hold(b, n):
        c.buttons[0] = set(b)
        c.run(n)
        c.buttons[0] = set()

    def win_round():
        c.poke_prg(HP_P2, (2).to_bytes(2, 'big'))
        for _ in range(80):
            if gap() < -10:
                break
            hold(['right'], 2)
        hold(['a'], 3)

    c.load_state(state or os.path.join(ROOT, 'build', 'states', 'mk_subzero_2p.state'))
    c.run(60)
    win_round()
    c.run(20)
    while hp() != (119, 119):
        c.run(10)
    c.run(240)
    win_round()                                  # FINISH HIM
    c.run(150)                                   # MK ignores the pad for a while after it
    for held, n in INPUT:
        c.buttons[0] = set(held.split('+')) - {''}
        c.run(n)
    c.buttons[0] = set()


def main():
    c = scd.Core(saves=os.path.join(ROOT, 'build', 'shots', 'capture-saves'))
    c.load(require('mk_us').cue)
    start(c)
    v = VDPState(c.snapshot())
    cram0 = v.cram_raw[0:16]
    xs = {pal: [s['x'] for s in v.sprites() if s['pal'] == pal and s['y'] > 40] for pal in (0, 1)}
    sx = (min(xs[0]) + max(xs[0])) // 2
    vx = (min(xs[1]) + max(xs[1])) // 2 if xs[1] else sx + 60
    him, victim = [], []
    for _ in range(FRAMES):
        c.run(1)
        v = VDPState(c.snapshot())
        him.append(canvas(v, 0))
        victim.append(canvas(v, 1, rgb=True))
    for name, frames, rgb, cx in (('fatality', him, False, sx), ('fatality_victim', victim, True, vx)):
        poses, order = group(frames, lambda f: f.tobytes() if f.any() else None)
        out = os.path.join(OUT, name)
        os.makedirs(out, exist_ok=True)
        np.save(os.path.join(out, 'rgb.npy' if rgb else 'indexed.npy'), np.array(poses))
        json.dump([feet_anchor(p, cx) for p in poses], open(os.path.join(out, 'anchors.json'), 'w'))
        open(os.path.join(out, 'order.txt'), 'w').write(' '.join(map(str, order)))
        if not rgb:
            json.dump(cram0, open(os.path.join(out, 'cram.json'), 'w'))
        if poses:
            pal = np.array([((q & 7) * 36, ((q >> 3) & 7) * 36, ((q >> 6) & 7) * 36) for q in cram0], np.uint8)
            ims = [Image.fromarray(p if rgb else pal[p]) for p in poses]
            sheet = Image.new('RGB', (160 * min(10, len(ims)), 120 * ((len(ims) + 9) // 10)))
            for i, im in enumerate(ims):
                sheet.paste(im.resize((160, 120)), ((i % 10) * 160, (i // 10) * 120))
            sheet.save(os.path.join(out, 'contact.png'))
        print(f'{name:16s} {len(poses):3d} poses over {len(order)} frames')


PASTE_HEAD = False                  # a pasted skin-tone head looked wrong on EC losers (Larcen)
HEAD_H = 20                         # px: the loser's head, from the top of her standing frame
HEAD_X, HEAD_Y = 192, 112           # the held head: left of the body, above his shoulder (capture px)
RAMP = (30, 100, 170)               # brightness steps: black, dark blue-grey, grey, white


def shade(rgb_px):
    """RGB pixels -> his capture palette's neutrals by brightness."""
    lum = rgb_px.mean(-1)
    idx = np.full(lum.shape, 12, np.uint8)
    for k, t in zip((10, 9, 15), RAMP):
        idx[lum > t] = k
    return idx


def held():
    """fatality_held/: his poses with the head (the loser's colours in MK,
    so captured with her) put back on the spine he holds, from the loser's
    frame shown with each of his poses."""
    his = np.load(os.path.join(OUT, 'fatality', 'indexed.npy'))
    vic = np.load(os.path.join(OUT, 'fatality_victim', 'rgb.npy')).astype(float)
    oh = [int(v) for v in open(os.path.join(OUT, 'fatality', 'order.txt')).read().split()]
    ov = [int(v) for v in open(os.path.join(OUT, 'fatality_victim', 'order.txt')).read().split()]
    out = his.copy()
    # MK's held head is two small blobs: a whole head reads better - the
    # loser's own, from her standing frame (the top HEAD_H rows of her body)
    v0 = vic[0]
    ys, xs = np.nonzero(v0.any(-1))
    top = ys.min()
    hrows = v0[top:top + HEAD_H]
    hx = np.nonzero(hrows.any(-1).any(0))[0]
    head = hrows[:, hx.min():hx.max() + 1]
    hm = head.any(-1)
    lum = head.mean(-1)
    hidx = np.full(lum.shape, 12, np.uint8)
    hidx[lum > 40] = 4
    hidx[lum > 120] = 3
    for k in range(len(his) if PASTE_HEAD else 0):   # (off: the loser's own head comes from EC's art)
        ts = [t for t, h in enumerate(oh) if h == k]
        if not ts:
            continue
        v = vic[ov[ts[0]]]
        m = v.any(-1)
        m[HEAD_Y:, :] = False
        m[:, HEAD_X:] = False
        if m.any():                      # her head where MK's blobs are: on the spine's top
            ys, xs = np.nonzero(m)
            cx, by = int(xs.mean()), ys.max()
            y0, x0 = by - head.shape[0] + 1, cx - head.shape[1] // 2
            for yy in range(head.shape[0]):
                for xx in range(head.shape[1]):
                    if hm[yy, xx] and 0 <= y0 + yy < out.shape[1] and 0 <= x0 + xx < out.shape[2]:
                        out[k][y0 + yy, x0 + xx] = hidx[yy, xx]
    d = os.path.join(OUT, 'fatality_held')
    os.makedirs(d, exist_ok=True)
    np.save(os.path.join(d, 'indexed.npy'), out)
    for f in ('anchors.json', 'cram.json', 'order.txt'):
        open(os.path.join(d, f), 'w').write(open(os.path.join(OUT, 'fatality', f)).read())
    print(f'fatality_held {len(out)} poses')


def corpse():
    """fatality_corpse/: the victim's frames (MK draws the loser's own
    headless body; an EC loser has none) in Sub-Zero's palette as a dark
    figure - black and greys by brightness - so his fatality can draw it on
    any loser's sprite with the loser's palette line set to his."""
    src = os.path.join(OUT, 'fatality_victim')
    rgb = np.load(os.path.join(src, 'rgb.npy')).astype(float)
    anchors = json.load(open(os.path.join(src, 'anchors.json')))
    cram = json.load(open(os.path.join(OUT, 'idle', 'cram.json')))
    # his capture palette's dark-to-light neutrals (entry, RGB)
    ramp = [12, 10, 9, 15]                      # black, dark blue-grey, grey, white
    poses = []
    for i in range(len(rgb)):
        m = rgb[i].any(-1)
        idx = shade(rgb[i])                            # (only near-black stays black: on a dark
        idx[~m] = 0                                    #  stage a black body disappears)
        idx[:60] = 0                            # (the FINISH HIM text sits up there)
        poses.append(idx)
    # the head he holds up is drawn in the loser's colours: it's in these
    # frames, at his hand - it goes to his poses (held()), not the body's
    for idx in poses:
        idx[:HEAD_Y, :HEAD_X] = 0
    # the loser faced left in the capture; EC treats a frame as facing right
    # and mirrors it for a fighter facing left: stored mirrored, so the body
    # falls toward him as in MK
    W = poses[0].shape[1]
    poses = [idx[:, ::-1] for idx in poses]
    anchors = [[W - 1 - x, y] for x, y in anchors]
    out = os.path.join(OUT, 'fatality_corpse')
    os.makedirs(out, exist_ok=True)
    np.save(os.path.join(out, 'indexed.npy'), np.array(poses))
    json.dump(anchors, open(os.path.join(out, 'anchors.json'), 'w'))
    json.dump(cram, open(os.path.join(out, 'cram.json'), 'w'))
    open(os.path.join(out, 'order.txt'), 'w').write(' '.join(map(str, range(len(poses)))))
    print(f'fatality_corpse {len(poses)} poses')


if __name__ == '__main__':
    if sys.argv[1:] == ['corpse']:
        corpse()
        held()
    else:
        main()
        corpse()
        held()
