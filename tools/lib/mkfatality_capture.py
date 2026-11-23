#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Capture an MK CD fatality from the user's MK disc, frame by frame.

The winner (palette line 0) and the victim (line 1), each indexed in his own
palette. As tools/lib/mkfatality_subzero.py: from a 2-player MK state (tools/capture/mkduelstate.py)
the winner takes two rounds (the loser's health set low, one hit each), MK
says FINISH HIM, the winner walks in and enters the fatality.

    mkfatality_capture.py NAME      (a FATALITIES key: johnny, raiden, kano, ...)
        -> extracted/<his MK dir>/fatality_mk/ (him) and fatality_mk_victim/ (the loser):
           indexed.npy, order.txt (pose per frame), anchors.json (feet, the x
           where he stood), cram.json, contact.png; and timeline.json (per frame:
           his pose, her pose)
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import scd
from vdp import VDPState
from inputs import ROOT, require
from mkfatality import canvas, group
import mkfatality_subzero as m
from PIL import Image

# name: (his MK dir, state, input after FINISH HIM ('+'-joined buttons, frames), frames)
FATALITIES = {
    # Johnny Cage: forward, forward, forward + high punch (close): the uppercut
    # that knocks the head off
    'johnny': ('mk_moves_johnny', 'mk_johnny_2p.state',
               [('right', 4), ('', 2), ('right', 4), ('', 2), ('right', 4), ('right+x', 4)], 420),
    # Raiden: forward, back, back, back + high punch (close): he electrocutes the
    # loser until the head explodes
    'raiden': ('mk_moves_raiden', 'mk_raiden_2p.state',
               [('right', 6), ('', 6), ('left', 6), ('', 6), ('left', 6), ('', 6), ('left', 6), ('left+x', 6)], 480),
               # (MK CD needs these slower taps: at 4 frames it took them for a walk and an uppercut)
    # Kano: back, back + LP (MK CD; the arcade's is B, D, F + LP): the heart rip
    # (found with tools/capture/mkfataltrial.py: every 3-tap sequence ending B, B + LP / HP)
    'kano': ('mk_moves_kano', 'mk_kano_2p.state', [('left', 5), ('', 4), ('left+a', 5), ('', 6)], 480),
    # Scorpion: hold Block, Up, Up from sweep distance (a step back from close): the flame
    # (his own capture is tools/lib/mkfatality.py: these are for tools/lib/mkfatalsound.py)
    'scorpion': ('mk_moves', 'mk_2p.state',
                 [('left', 30), ('', 4), ('b', 6), ('b+up', 5), ('b', 5), ('b+up', 5), ('b', 8)], 480),
    'scorpion_sonya': ('mk_moves', 'mk_scorpion_sonya_2p.state',
                       [('left', 30), ('', 4), ('b', 6), ('b+up', 5), ('b', 5), ('b+up', 5), ('b', 8)], 480),
    # Sonya: forward, forward, back, back + Block (anywhere): the kiss of death
    # (found with tools/capture/mkfataltrial.py: MK's fatality music starts)
    'sonya': ('mk_moves_sonya', 'mk_sonya_2p.state',
              [('right', 6), ('', 6), ('right', 6), ('', 6), ('left', 6), ('', 6), ('left+b', 6)], 480),
    # Liu Kang: down, back, up, forward, down (MK CD; the arcade's is Block + a full circle):
    # the cartwheel and uppercut
    'liukang': ('mk_moves_liukang', 'mk_liukang_2p.state',
                [('down', 6), ('left', 6), ('up', 6), ('right', 6), ('down', 6), ('', 6)], 480),
}


def start(c, state=None, name=None):
    """From the fight state to the first frame after the fatality's input (what
    capture() then records frame by frame): (each player's centre x, palettes)."""
    mk_dir, st, inp, frames = FATALITIES[name]
    if os.environ.get('EK_FATAL_INPUT'):          # (trying an input: JSON [[held, frames], ...])
        inp = [tuple(x) for x in json.loads(os.environ['EK_FATAL_INPUT'])]
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

    c.load_state(state or os.path.join(ROOT, 'build', 'states', st))
    c.run(60)
    win_round()
    c.run(20)
    while hp() != (119, 119):
        c.run(10)
    c.run(240)
    win_round()                                  # FINISH HIM
    c.run(150)
    for _ in range(40):                          # up close (MK's 'close' fatalities)
        if gap() < -14:
            break
        hold(['right'], 2)
    c.run(4)
    v = VDPState(c.snapshot())
    xs = {pal: [s['x'] for s in v.sprites() if s['pal'] == pal and s['y'] > 40] for pal in (0, 1)}
    cx = {pal: (min(xs[pal]) + max(xs[pal])) // 2 + 8 for pal in (0, 1)}
    crams = {pal: v.cram_raw[16 * pal:16 * pal + 16] for pal in (0, 1)}
    for held, n in inp:
        c.buttons[0] = set(held.split('+')) - {''}
        c.run(n)
    c.buttons[0] = set()
    return cx, crams


def capture(name):
    mk_dir, state, inp, frames = FATALITIES[name]
    c = scd.Core(saves=os.path.join(ROOT, 'build', 'shots', 'capture-saves'))
    c.load(require('mk_us').cue)
    cx, crams = start(c, name=name)
    caps = {0: [], 1: []}
    for _ in range(frames):
        c.run(1)
        v = VDPState(c.snapshot())
        for pal in (0, 1):
            caps[pal].append(canvas(v, pal))
    base = os.path.join(ROOT, 'extracted', mk_dir)
    orders = {}
    for pal, sub in ((0, 'fatality_mk'), (1, 'fatality_mk_victim')):
        poses, order = group(caps[pal], lambda f: f.tobytes() if f.any() else None)
        orders[pal] = order
        out = os.path.join(base, sub)
        os.makedirs(out, exist_ok=True)
        np.save(os.path.join(out, 'indexed.npy'), np.array(poses))
        feet = int(np.nonzero(np.array(poses[0]).any(1))[0].max()) + 1
        json.dump([(int(cx[pal]), feet)] * len(poses), open(os.path.join(out, 'anchors.json'), 'w'))
        open(os.path.join(out, 'order.txt'), 'w').write(' '.join(map(str, order)))
        json.dump(crams[pal], open(os.path.join(out, 'cram.json'), 'w'))
        pal_rgb = np.array([((q & 7) * 36, ((q >> 3) & 7) * 36, ((q >> 6) & 7) * 36) for q in crams[pal]], np.uint8)
        pal_rgb[0] = (40, 40, 60)
        ims = [Image.fromarray(pal_rgb[p]) for p in poses]
        sheet = Image.new('RGB', (160 * 10, 120 * ((len(ims) + 9) // 10)))
        for i, im in enumerate(ims):
            sheet.paste(im.resize((160, 120)), ((i % 10) * 160, (i // 10) * 120))
        sheet.save(os.path.join(out, 'contact.png'))
        print(f'{sub:20s} {len(poses):3d} poses over {len(order)} frames -> {os.path.relpath(out, ROOT)}')
    json.dump({'his': orders[0], 'hers': orders[1]}, open(os.path.join(base, 'fatality_mk', 'timeline.json'), 'w'))


if __name__ == '__main__':
    capture(sys.argv[1])
