#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Capture the victim of MK CD's Sub-Zero spine rip, indexed in his own palette.

MK's headless body (it stands, drops to its knees and falls flat), from your MK
disc; tools/lib/mkdeath.py builds his EC death art from it.

Same run as tools/lib/mkfatality_subzero.py (Sub-Zero wins two rounds, FINISH HIM,
forward, down, forward + high punch), from an MK duel state with the victim as
player 2 (tools/capture/mkduelstate.py subzero / subzero_raiden / subzero_johnny /
subzero_subzero). The victim is palette line 1.

    mkvictim.py scorpion|raiden|johnny|subzero|liukang|kano|sonya
        -> extracted/<his MK dir>/spinerip_victim/ (indexed.npy, anchors.json,
           order.txt, cram.json, contact.png; anchors: his feet, the x where he stood)
"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import numpy as np
import scd
from vdp import VDPState
from inputs import ROOT, require
from mkfatality import canvas, group
import mkfatality_subzero as m
from PIL import Image

VICTIMS = {'scorpion': ('mk_moves', 'mk_subzero_2p.state'),
           'raiden': ('mk_moves_raiden', 'mk_subzero_raiden_2p.state'),
           'johnny': ('mk_moves_johnny', 'mk_subzero_johnny_2p.state'),
           'subzero': ('mk_moves_subzero', 'mk_subzero_subzero_2p.state'),
           'liukang': ('mk_moves_liukang', 'mk_subzero_liukang_2p.state'),
           'kano': ('mk_moves_kano', 'mk_subzero_kano_2p.state'),
           'sonya': ('mk_moves_sonya', 'mk_subzero_sonya_2p.state')}
FRAMES = 420


def main():
    who = sys.argv[1]
    mk_dir, state = VICTIMS[who]
    c = scd.Core(saves=os.path.join(ROOT, 'build', 'shots', 'capture-saves'))
    c.load(require('mk_us').cue)
    hp = lambda: tuple(int.from_bytes(c.prg_ram()[a:a + 2], 'big') for a in (m.HP_P1, m.HP_P2))

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
        c.poke_prg(m.HP_P2, (2).to_bytes(2, 'big'))
        for _ in range(80):
            if gap() < -10:
                break
            hold(['right'], 2)
        hold(['a'], 3)

    c.load_state(os.path.join(ROOT, 'build', 'states', state))
    c.run(60)
    first = c.frame.copy()
    win_round()
    c.run(20)
    while hp() != (119, 119):
        c.run(10)
    c.run(240)
    win_round()                                  # FINISH HIM
    c.run(150)
    for held, n in m.INPUT:
        c.buttons[0] = set(held.split('+')) - {''}
        c.run(n)
    c.buttons[0] = set()
    v = VDPState(c.snapshot())
    cram = v.cram_raw[16:32]
    xs = [s['x'] for s in v.sprites() if s['pal'] == 1 and s['y'] > 40]
    cx = (min(xs) + max(xs)) // 2 + 8
    frames = []
    for _ in range(FRAMES):
        c.run(1)
        frames.append(canvas(VDPState(c.snapshot()), 1))
    poses, order = group(frames, lambda f: f.tobytes() if f.any() else None)
    out = os.path.join(ROOT, 'extracted', mk_dir, 'spinerip_victim')
    os.makedirs(out, exist_ok=True)
    np.save(os.path.join(out, 'indexed.npy'), np.array(poses))
    feet = int(np.nonzero(np.array(poses[0]).any(1))[0].max()) + 1     # where he stood: the floor
    json.dump([(int(cx), feet)] * len(poses), open(os.path.join(out, 'anchors.json'), 'w'))
    open(os.path.join(out, 'order.txt'), 'w').write(' '.join(map(str, order)))
    json.dump(cram, open(os.path.join(out, 'cram.json'), 'w'))
    pal = np.array([((q & 7) * 36, ((q >> 3) & 7) * 36, ((q >> 6) & 7) * 36) for q in cram], np.uint8)
    pal[0] = (40, 40, 60)
    ims = [Image.fromarray(pal[p]).crop((cx - 80, 60, cx + 80, 230)) for p in poses]
    sheet = Image.new('RGB', (160 * 10, 170 * ((len(ims) + 9) // 10)))
    for i, im in enumerate(ims):
        sheet.paste(im, ((i % 10) * 160, (i // 10) * 170))
    sheet.save(os.path.join(out, 'contact.png'))
    Image.fromarray(first).save(os.path.join(out, 'duel.png'))
    print(f'{who}: {len(poses)} poses over {len(order)} frames -> {os.path.relpath(out, ROOT)}')


if __name__ == '__main__':
    main()
