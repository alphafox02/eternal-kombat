#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The title screen says ETERNAL KOMBAT (ectitle.py).

From the built disc's title screen (build/states/menu.state) and its main menu (Start pressed), the
picture on plane B is
  - ectitle's, pixel for pixel (colour indices: the menu cycles line 2's colour 11), with line 2's
    slots 12-15 the glow's reds;
  - EC's everywhere but the cells ectitle redraws (CHAMPIONS' and KOMBAT's), as made from the
    player's GAME.DAT and GAME.CO.

    titlecheck.py [--disc CUE]     (after play.py test has made build/states/menu.state)
"""
import argparse, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import numpy as np
import scd, vdp, ectitle
from inputs import ROOT


def screen_indices(v):
    """Plane B's colour indices as drawn (its tiles in VRAM, mirrored as the cells say)."""
    base, (w, _) = (v.regs[4] & 7) << 13, v.plane_size()
    out = np.zeros((ectitle.H, ectitle.W), np.uint8)
    for cy in range(ectitle.H // 8):
        for cx in range(ectitle.W // 8):
            e = int.from_bytes(v.vram[base + 2 * (cy * w + cx):base + 2 * (cy * w + cx) + 2], 'big')
            t = v.tile(e & 0x7FF)
            if e & 0x800:
                t = t[:, ::-1]
            if e & 0x1000:
                t = t[::-1]
            out[cy * 8:cy * 8 + 8, cx * 8:cx * 8 + 8] = t
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    a = ap.parse_args()
    src = os.path.join(ROOT, 'extracted', 'ec_us')
    dat, co = open(os.path.join(src, 'GAME.DAT'), 'rb').read(), open(os.path.join(src, 'GAME.CO'), 'rb').read()
    cells = ectitle.load_map()
    ec_pic, line = ectitle.picture(dat, cells)
    ours, _ = ectitle.kombat(ec_pic, line, ectitle.palettes(co))
    redrawn = ec_pic != ours
    c = scd.Core()
    c.load(a.disc)
    c.load_state(os.path.join(ROOT, 'build', 'states', 'menu.state'))
    bad = []
    for screen in ('title', 'main menu'):
        if screen == 'main menu':
            c.press(['start'], 3)
            c.run(120)
        else:
            c.run(2)
        v = vdp.VDPState(c.snapshot())
        pic = screen_indices(v)
        slots = [v.palette(2)[i] for i in ectitle.NEW]
        off = int((pic != ours).sum())
        same_ec = bool((pic[~redrawn] == ec_pic[~redrawn]).all())
        print(f'{screen}: {off} pixels off ectitle\'s picture ({int(redrawn.sum())} redrawn); '
              f'EC\'s elsewhere: {same_ec}; line 2 slots 12-15 {slots}')
        if off or not same_ec or slots != list(ectitle.NEW.values()):
            bad.append(screen)
    print('titlecheck:', 'FAIL ' + ', '.join(bad) if bad else 'ok')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
