#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Capture Scorpion's MK1 fatality from the MK disc, frame by frame.

From build/states/mk_2p.state: win two rounds by uppercutting a standing
Sub-Zero, at FINISH HIM step back half a screen, hold Block (B) and press Up,
Up. Then record, frame by frame:

  fatality/           Scorpion (palette line 0, near him): unmask, skull, fire breath
  fatality_fire/      the fire that lands on the victim (line 0, near the victim)
  fatality_victim/    the victim (line 1) as RGB: burning, charred, skeleton, bones
  fatality_skeleton/  the victim from the burning on, in Scorpion's palette (skeleton())

Each folder: indexed.npy (or rgb.npy), anchors.json, order.txt (pose per
frame), plus cram.json for the indexed ones. Used by scorpion_full /
the fatality patch.

    mkfatality.py              -> all four
    mkfatality.py skeleton     -> only fatality_skeleton/, from fatality_victim/
"""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scd
from vdp import VDPState
from inputs import ROOT, require
from PIL import Image

OUT = os.path.join(ROOT, 'extracted', 'mk_moves')
H, W = 240, 320
FIRST_BURNT = 10              # victim poses 0-8: Sub-Zero dazed, 9: a stray Scorpion frame
FRAMES = 330                  # input done -> bones on the floor


def canvas(v, pal, keep=lambda s: True, rgb=False):
    out = np.zeros((H, W, 3) if rgb else (H, W), np.uint8)
    cols = None
    if rgb:
        cols = np.array([((c & 7) * 36, ((c >> 3) & 7) * 36, ((c >> 6) & 7) * 36)
                         for c in v.cram_raw[pal * 16:pal * 16 + 16]], np.uint8)
    for s in reversed([s for s in v.sprites() if s['pal'] == pal and s['y'] > 40 and keep(s)]):
        px = v.sprite_pixels(s)
        ys, xs = np.nonzero(px)
        Y, X = ys + s['y'], xs + s['x']
        ok = (Y >= 0) & (Y < H) & (X >= 0) & (X < W)
        out[Y[ok], X[ok]] = cols[px[ys[ok], xs[ok]]] if rgb else px[ys[ok], xs[ok]]
    return out


def boxes(v):
    out = {}
    for pal in (0, 1):
        xs = [s['x'] for s in v.sprites() if s['pal'] == pal and s['y'] > 40]
        out[pal] = (min(xs) + max(xs)) // 2 if xs else None
    return out


def group(frames, key):
    poses, index, order = [], {}, []
    for f in frames:
        k = key(f)
        if k is None:
            order.append(-1)
            continue
        if k not in index:
            index[k] = len(poses)
            poses.append(f)
        order.append(index[k])
    return poses, order


def feet_anchor(p, cx):
    ys = np.nonzero(p.reshape(p.shape[0], -1).any(1))[0]
    return int(cx), int(ys.max()) + 1


def start(c, state=None):
    """From the fight state to the first frame after the fatality's input
    (what main() then records frame by frame)."""
    c.load_state(state or os.path.join(ROOT, 'build', 'states', 'mk_2p.state'))
    vdp = lambda: VDPState(c.snapshot())
    for k in range(1480):                                   # two rounds of uppercuts
        b = boxes(vdp())
        if b[0] is not None and b[1] is not None and abs(b[1] - b[0]) > 55:
            c.buttons[0] = {'right' if b[1] > b[0] else 'left'}
        else:
            c.buttons[0] = {'down', 'x'} if k % 20 < 6 else ({'down'} if k % 20 < 10 else set())
        c.run(1)
    for held, n in [('', 40), ('left', 40), ('', 4), ('b', 4), ('b+up', 4), ('b', 4), ('b+up', 4), ('b', 4)]:
        c.buttons[0] = set(held.split('+')) - {''}
        c.run(n)
    c.buttons[0] = set()


def main():
    c = scd.Core(saves=os.path.join(ROOT, 'build', 'shots', 'capture-saves'))
    c.load(require('mk_us').cue)
    start(c)
    vdp = lambda: VDPState(c.snapshot())
    v = vdp()
    b = boxes(v)
    sx, vx = b[0], b[1]
    split = (sx + vx) // 2
    cram0 = v.cram_raw[0:16]
    scorp, fire, victim = [], [], []
    for _ in range(FRAMES):
        c.run(1)
        v = vdp()
        scorp.append(canvas(v, 0, lambda s: s['x'] < split))
        fire.append(canvas(v, 0, lambda s: s['x'] >= split))
        victim.append(canvas(v, 1, rgb=True))
    for name, frames, rgb, cx in (('fatality', scorp, False, sx), ('fatality_fire', fire, False, vx),
                                  ('fatality_victim', victim, True, vx)):
        poses, order = group(frames, lambda f: f.tobytes() if f.any() else None)
        out = os.path.join(OUT, name)
        os.makedirs(out, exist_ok=True)
        np.save(os.path.join(out, 'rgb.npy' if rgb else 'indexed.npy'), np.array(poses))
        json.dump([feet_anchor(p, cx) for p in poses], open(os.path.join(out, 'anchors.json'), 'w'))
        open(os.path.join(out, 'order.txt'), 'w').write(' '.join(map(str, order)))
        if not rgb:
            json.dump(cram0, open(os.path.join(out, 'cram.json'), 'w'))
        # contact sheet
        if poses:
            pal = np.array([((q & 7) * 36, ((q >> 3) & 7) * 36, ((q >> 6) & 7) * 36) for q in cram0], np.uint8)
            ims = [Image.fromarray(p if rgb else pal[p]) for p in poses]
            sheet = Image.new('RGB', (160 * min(10, len(ims)), 120 * ((len(ims) + 9) // 10)))
            for i, im in enumerate(ims):
                sheet.paste(im.resize((160, 120)), ((i % 10) * 160, (i // 10) * 120))
            sheet.save(os.path.join(out, 'contact.png'))
        print(f'{name:16s} {len(poses):3d} poses over {len(order)} frames')
    fire_trim()
    skeleton()


FIRE_FROM = 5                 # fire poses 0-4: the stream in flight; 5 on: burst, column, ash


def fire_trim():
    """Keep the fire that's ON the victim (burst, column, ash): EC draws it on
    the victim's own sprite, which can't also show the stream in flight."""
    d = os.path.join(OUT, 'fatality_fire')
    poses = np.load(os.path.join(d, 'indexed.npy'))
    anchors = json.load(open(os.path.join(d, 'anchors.json')))
    if len(poses) <= len(anchors) - FIRE_FROM:
        return
    np.save(os.path.join(d, 'indexed.npy'), poses[FIRE_FROM:])
    json.dump(anchors[FIRE_FROM:], open(os.path.join(d, 'anchors.json'), 'w'))
    open(os.path.join(d, 'order.txt'), 'w').write(' '.join(map(str, range(len(poses) - FIRE_FROM))))
    print(f'fatality_fire trimmed to {len(poses) - FIRE_FROM} poses')


def skeleton():
    """fatality_skeleton/: the victim burning, then the skeleton (standing -> bones),
    converted to Scorpion's palette (nearest colour) so EC can draw them on
    the victim's sprite with the victim's palette line set to Scorpion's."""
    src = os.path.join(OUT, 'fatality_victim')
    rgb = np.load(os.path.join(src, 'rgb.npy'))
    anchors = json.load(open(os.path.join(src, 'anchors.json')))
    cram = json.load(open(os.path.join(OUT, 'idle', 'cram.json')))
    pal = np.array([((c & 7) * 36, ((c >> 3) & 7) * 36, ((c >> 6) & 7) * 36) for c in cram], float)
    # poses 0-8 are Sub-Zero dazed, 9 a stray Scorpion frame; from FIRST_BURNT on: burning, then the skeleton
    keep = [i for i in range(len(rgb)) if i >= FIRST_BURNT and rgb[i].any()]
    poses = []
    for i in keep:
        p = rgb[i].astype(float)
        m = p.any(-1)
        d = ((p[:, :, None, :] - pal[None, None, 1:, :]) ** 2).sum(-1)
        idx = (d.argmin(-1) + 1).astype(np.uint8) * m
        idx[:60] = 0                                       # 'FINISH HIM' text lives up there
        poses.append(idx)
    out = os.path.join(OUT, 'fatality_skeleton')
    os.makedirs(out, exist_ok=True)
    np.save(os.path.join(out, 'indexed.npy'), np.array(poses))
    json.dump([anchors[i] for i in keep], open(os.path.join(out, 'anchors.json'), 'w'))
    json.dump(cram, open(os.path.join(out, 'cram.json'), 'w'))
    open(os.path.join(out, 'order.txt'), 'w').write(' '.join(map(str, range(len(poses)))))
    print(f'fatality_skeleton {len(poses)} poses (victim poses {keep})')


if __name__ == '__main__':
    if sys.argv[1:] == ['skeleton']:            # (only fatality_skeleton/, from fatality_victim/)
        skeleton()
    else:
        main()
