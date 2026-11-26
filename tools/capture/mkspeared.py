#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Capture MK CD's speared fighter: the pose he holds on Scorpion's rope.

MK shows a speared fighter in one pose of his own, leaning back, from the hit
until the yank brings him in (about 50 frames); then he stands dazed. None of
his move captures has it. Scorpion (player 1) spears him (player 2, palette
line 1) from about 130 px, from tools/capture/mkduelstate.py's states.

The poses are flipped to face right, as his move captures (player 1) do. The
anchor is his stance's (centre of the head, the floor) before the throw: MK
leans him back from where he stood.

    mkspeared.py scorpion|raiden|johnny|subzero|liukang|kano|sonya
        -> extracted/<his MK dir>/speared/ (indexed.npy: the pose he holds on the rope,
           order.txt: 0 where it shows from the hit on, anchors.json, cram.json;
           contact.png: every pose from the hit to the daze)
"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
from collections import Counter
import numpy as np
from PIL import Image
import scd
from vdp import VDPState
from inputs import ROOT, require
from mkfatality import canvas, group
from mkmoves import anchor

VICTIMS = {'scorpion': ('mk_moves', 'mk_scorpion_scorpion_2p.state'),
           'raiden': ('mk_moves_raiden', 'mk_scorpion_raiden_2p.state'),
           'johnny': ('mk_moves_johnny', 'mk_scorpion_johnny_2p.state'),
           'subzero': ('mk_moves_subzero', 'mk_2p.state'),
           'liukang': ('mk_moves_liukang', 'mk_scorpion_liukang_2p.state'),
           'kano': ('mk_moves_kano', 'mk_scorpion_kano_2p.state'),
           'sonya': ('mk_moves_sonya', 'mk_scorpion_sonya_2p.state')}
GAP = 130                       # px between the two fighters' centres (tools/dev/spearcmp.py)
THROW = [('left', 3), ('', 3), ('left', 3), ('a', 4)]
FRAMES = 140                    # from the press: the hit (~34), the pin, the yank, the daze
STANCE = 60                     # frames of his stance recorded before the throw (not his poses on the rope)


def main():
    who = sys.argv[1]
    mk_dir, state = VICTIMS[who]
    c = scd.Core(saves=os.path.join(ROOT, 'build', 'shots', 'capture-saves'))
    c.load(require('mk_us').cue)
    c.load_state(os.path.join(ROOT, 'build', 'states', state))
    c.run(220)                                  # (past FIGHT!: MK takes no input before)

    def centres():
        v = VDPState(c.snapshot())
        out = []
        for pal in (0, 1):
            ss = [s for s in v.sprites() if s['pal'] == pal and s['y'] > 30]
            out.append((min(s['x'] for s in ss) + max(s['x'] + 8 * s['w'] for s in ss)) / 2 if len(ss) > 3 else None)
        return out

    for _ in range(240):                        # walk: Scorpion in, or him back
        x = centres()
        if None in x or abs(x[1] - x[0] - GAP) < 3:
            break
        far = x[1] - x[0] > GAP
        c.buttons[0], c.buttons[1] = ({'right'} if far else set()), (set() if far else {'right'})
        c.run(1)
    c.buttons[0], c.buttons[1] = set(), set()
    c.run(12)
    v = VDPState(c.snapshot())
    stance = canvas(v, 1)
    idle = set()                                # his stance's poses (MK's breathing): a second of it
    for _ in range(STANCE):
        c.run(1)
        idle.add(canvas(VDPState(c.snapshot()), 1).tobytes())
    frames = []
    for btn, n in THROW:
        for _ in range(n):
            c.buttons[0] = set(btn.split('+')) - {''}
            c.run(1)
            frames.append(canvas(VDPState(c.snapshot()), 1))
    c.buttons[0] = set()
    for _ in range(FRAMES - len(frames)):
        c.run(1)
        frames.append(canvas(VDPState(c.snapshot()), 1))
    poses, order = group(frames, lambda f: f.tobytes() if f.any() and f.tobytes() not in idle else None)
    poses = [np.ascontiguousarray(p[:, ::-1]) for p in poses]     # facing right, as his moves
    ax, floor = anchor(np.ascontiguousarray(stance[:, ::-1]))
    # MK shakes him 2 px up and down on the rope: the same image twice, the two poses held the
    # longest. The lower one (his feet nearer the floor) is kept
    two = [q for q, _ in Counter(o for o in order if o >= 0).most_common(2)]
    held = max(two, key=lambda q: int(np.nonzero(poses[q].any(1))[0].max()))
    out = os.path.join(ROOT, 'extracted', mk_dir, 'speared')
    os.makedirs(out, exist_ok=True)
    np.save(os.path.join(out, 'indexed.npy'), np.array([poses[held]]))
    json.dump([(ax, floor)], open(os.path.join(out, 'anchors.json'), 'w'))
    open(os.path.join(out, 'order.txt'), 'w').write(' '.join('0' if o == held else '-1' for o in order))
    # his own colours (his move captures, player 1's): MK gives a mirror match's player 2 others
    # (the build maps scaled art back to the palette by colour)
    cram = json.load(open(os.path.join(ROOT, 'extracted', mk_dir, 'idle', 'cram.json')))
    json.dump(cram, open(os.path.join(out, 'cram.json'), 'w'))
    pal = np.array([((q & 7) * 36, ((q >> 3) & 7) * 36, ((q >> 6) & 7) * 36) for q in cram], np.uint8)
    pal[0] = (40, 40, 60)
    ims = [Image.fromarray(pal[p]).crop((ax - 80, 60, ax + 80, 230)) for p in poses]
    sheet = Image.new('RGB', (160 * 10, 170 * ((len(ims) + 9) // 10)))
    for i, im in enumerate(ims):
        sheet.paste(im, ((i % 10) * 160, (i // 10) * 170))
    sheet.save(os.path.join(out, 'contact.png'))
    print(f'{who}: {len(poses)} poses besides his stance; held: pose {held} '
          f'({order.count(held)} frames, {sum(order.count(q) for q in two)} with the shake) -> {os.path.relpath(out, ROOT)}')


if __name__ == '__main__':
    main()
