#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""MK CD's camera on each 2-player stage: its limits and how each plane scrolls, line by line.

From the battle states (tools/capture/mkstagestates.py). Both fighters walk left for LEG frames
(the camera to its left stop), then right for 2 * LEG (to its right stop). Every frame the VDP's
scroll registers are read: the horizontal scroll table (reg 13; per line when reg 11's low bits
are 3, per 8 lines when 2, one entry when 0) for planes A and B, and VSRAM. A plane's scroll on a
line is a fixed function of the camera x (how much of the camera's movement that line follows:
1 = moves with the fighters, 0.5 = half as fast, ...); the camera's own x is plane A's scroll at
the floor line. Also the lowest fighter pixel on screen (the floor line, from the sprites).

    mkstagecamera.py [--battles 1,2,3,5,6] [--out build/shots/mk_stages/camera.json]
"""
import argparse, json, os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT, require
from vdp import VDPState, VDP

LEG = 900                    # frames walking each way (enough for the widest stage, the Throne Room, to reach its stops)


def scroll(st, v):
    """(hscroll A per line, hscroll B per line, vscroll A, vscroll B) for the 224 lines."""
    mode = v.regs[11] & 3
    base = (v.regs[13] & 0x3F) << 10
    tab = np.frombuffer(v.vram[base:base + 224 * 4], '>i2').reshape(224, 2).astype(int)
    if mode == 0:
        tab = np.repeat(tab[:1], 224, 0)
    elif mode == 2:
        tab = np.repeat(tab[::8][:28], 8, 0)
    vsa = st[VDP + 0x10480] | st[VDP + 0x10481] << 8
    vsb = st[VDP + 0x10482] | st[VDP + 0x10483] << 8
    return tab[:, 0], tab[:, 1], vsa, vsb


def measure(c, n):
    """Walk the fighters left then right from battle n's state (loaded); the camera's limits and
    each plane's scroll bands (lines, rate, scroll at the left stop), the vscroll and feet."""
    c.load_state(os.path.join(ROOT, 'build', 'states', f'mk_battle_{n}.state'))
    rows, feet = [], []
    for f in range(3 * LEG):
        way = 'left' if f < LEG else 'right'
        c.buttons = [{way}, {way}]
        c.run(1)
        st = c.snapshot()
        v = VDPState(st)
        rows.append(scroll(st, v))
        ys = [s['y'] + s['h'] * 8 for s in v.sprites() if s['pal'] in (0, 1) and s['y'] > 40]
        feet.append(max(ys) if ys else None)
    c.buttons = [set(), set()]
    ha = np.array([r[0] for r in rows])                  # frames x lines
    hb = np.array([r[1] for r in rows])
    vs = sorted({(int(r[2]), int(r[3])) for r in rows})
    span = ha.max(0) - ha.min(0)                         # camera x: -(plane A scroll) on the line
    ref = int(np.argmax(span))                           #  that moves most
    cam = -ha[:, ref]
    cmin, cmax = int(cam.min()), int(cam.max())
    moved = cmax - cmin
    rate = lambda h: [round(float((h[:, y].max() - h[:, y].min()) / moved), 3) if moved else 0 for y in range(224)]

    def runs(h):
        r = rate(h)
        left = h[int(np.argmin(cam))]
        out, y0 = [], 0
        for y in range(1, 225):
            if y == 224 or r[y] != r[y0] or (r[y] == 0 and left[y] != left[y0]):
                out.append(dict(lines=[y0, y - 1], rate=r[y0], scroll_at_left=int(left[y0])))
                y0 = y
        return out
    return dict(camera=[cmin, cmax], ref_line=ref, vscroll=vs, plane_a=runs(ha), plane_b=runs(hb),
                feet=[min(x for x in feet if x), max(x for x in feet if x)],
                hscroll_mode=int(VDPState(c.snapshot()).regs[11] & 3))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--battles', default='1,2,3,4,5,6')
    ap.add_argument('--out', default=os.path.join(ROOT, 'build', 'shots', 'mk_stages', 'camera.json'))
    a = ap.parse_args()
    c = scd.Core(saves=os.path.join(ROOT, 'build', 'shots', 'capture-saves'))
    c.load(require('mk_us').cue)
    result = {}
    for n in [int(x) for x in a.battles.split(',')]:
        r = result[n] = measure(c, n)
        print(f'battle {n}: camera x {r["camera"][0]}..{r["camera"][1]} (line {r["ref_line"]}); vscroll {r["vscroll"]}; '
              f'feet y {r["feet"]}', flush=True)
        for p in ('plane_a', 'plane_b'):
            print(f'  {p}: ' + '; '.join(f'{b["lines"][0]}-{b["lines"][1]} x{b["rate"]} @{b["scroll_at_left"]}'
                                       for b in r[p]), flush=True)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(result, open(a.out, 'w'), indent=1)


if __name__ == '__main__':
    main()
