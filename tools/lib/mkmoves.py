#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Capture a fighter's MK poses action by action, from a 2-player MK match.

Player 2 stands still (build/states/mk_2p.state: Scorpion vs Sub-Zero; FIGHTERS
names the other fighters' states).

    mkmoves.py [--fighter=raiden] [action ...]   # default: Scorpion, all actions

For each action the match is restored, the input script played, and every
distinct pose of player 1 (sprites on palette line PAL) recorded in order.
Writes extracted/<his MK dir>/<action>/ (mk_moves for Scorpion): indexed.npy
(poses x H x W, 0 = transparent, all actions share one canvas and origin so
poses line up), order.txt (pose index per captured frame), anchors.json,
cram.json, cram_p2.json and contact.png.

Input steps: (p1 buttons, p2 buttons, frames). Buttons: up down left right
a b c x y z start, joined with '+'. The fighter faces right (player 1).
"""
import ctypes as C, hashlib, json, os, sys
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scd
from inputs import ROOT, require
from vdp import VDPState

PAL = 0
OUT = os.path.join(ROOT, 'extracted', 'mk_moves')
CANVAS = (240, 320)          # full screen; cropped per pose later by consumers
NUMBER_TOP = 40              # poses are told apart (numbered) by their sprites at y > 40, as the first
                             # captures were: order.txt, the recipes and the pose numbers pinned in the
                             # build keep their meaning. But a pose is stored whole (TOP): the y > 40
                             # rule was meant for the HUD - and MK's HUD is a plane, no sprites - so
                             # it cut his head piece off whenever he was that high (jumps, knockdowns:
                             # Sub-Zero lost his head in his jump kick)
TOP = -129                   # every sprite of his


def hold(p1='', n=4, p2=''):
    return (p1, p2, n)


ACTIONS = {
    'idle':        [hold('', 60)],
    'walk_fwd':    [hold('right', 90)],
    'walk_back':   [hold('left', 90)],
    'crouch':      [hold('down', 40), hold('', 30)],
    'jump_up':     [hold('up', 4), hold('', 70)],
    'jump_fwd':    [hold('up+right', 4), hold('', 70)],
    'jump_back':   [hold('up+left', 4), hold('', 70)],
}
# MK1 Genesis 6-button: A low punch, X high punch, B/Y block, C low kick, Z high kick
ACTIONS.update({
    'block':       [hold('b', 40), hold('', 10)],
    'crouch_block': [hold('down', 10), hold('down+b', 40), hold('', 10)],
    'uppercut':    [hold('down', 8), hold('down+x', 4), hold('down', 40), hold('', 20)],
    'sweep':       [hold('left+c', 4), hold('', 50)],
    'roundhouse':  [hold('left+z', 4), hold('', 50)],
    'spear':       [hold('left', 3), hold('', 3), hold('left', 3), hold('a', 4), hold('', 110)],
    # MK's spear when it doesn't hit (Sub-Zero crouching under it) and when blocked: no pull - the
    # rope shrinks away / the spear stops at the blocker; Scorpion holds the throw, then his stance
    'spear_miss':  [hold('left', 3, 'down'), hold('', 3, 'down'), hold('left', 3, 'down'), hold('a', 4, 'down'),
                    hold('', 110, 'down')],
    'spear_block': [hold('left', 3, 'b'), hold('', 3, 'b'), hold('left', 3, 'b'), hold('a', 4, 'b'), hold('', 110, 'b')],
    'teleport':    [hold('down', 3), hold('', 2), hold('left', 3), hold('x', 4), hold('', 90)],
    # Sub-Zero walks over and attacks: Scorpion's hit reactions
    'hit_high':    [hold('', 50, 'left'), hold('', 4, 'x'), hold('', 60)],
    'hit_low':     [hold('', 50, 'left'), hold('', 4, 'down+a'), hold('', 60)],
    'hit_kick':    [hold('', 50, 'left'), hold('', 4, 'z'), hold('', 60)],
    'knockdown':   [hold('', 50, 'left'), hold('', 8, 'down'), hold('', 4, 'down+x'), hold('', 120)],
    'swept':       [hold('', 50, 'left'), hold('', 4, 'right+c'), hold('', 120)],
    # Scorpion close to Sub-Zero: throw
    # walk into him, then toward + Z: MK CD's throw (Sub-Zero lands ~120 px
    # behind; low punch up close is the close punch, close_punch below)
    'throw':       [hold('right', 60), hold('right+z', 3), hold('right', 3), hold('', 120)],
    # up close, MK CD's own close moves: low punch (high punch plays the same) and low kick
    # (Kano's close punch is his headbutt; Sonya's close low kick shows her far one's poses)
    'close_punch': [hold('right', 70), hold('', 5), hold('a', 4), hold('', 65)],
    'close_knee':  [hold('right', 70), hold('', 5), hold('c', 4), hold('', 65)],
})
for b in 'abcxyz':
    ACTIONS[f'btn_{b}'] = [hold(b, 4), hold('', 45)]
    ACTIONS[f'crouch_{b}'] = [hold('down', 12), hold(f'down+{b}', 4), hold('down', 40), hold('', 20)]
    ACTIONS[f'jump_{b}'] = [hold('up+right', 4), hold('', 14), hold(b, 4), hold('', 60)]
    # straight up: MK's neutral jump attacks are their own (near-upright) poses
    ACTIONS[f'jumpup_{b}'] = [hold('up', 4), hold('', 14), hold(b, 4), hold('', 60)]


class Session:
    def __init__(self):
        self.core = scd.Core(saves=os.path.join(ROOT, 'build', 'shots', 'capture-saves'))
        self.core.load(require('mk_us').cue)

    def vdp(self):
        n = self.core.lib.retro_serialize_size()
        b = C.create_string_buffer(n)
        self.core.lib.retro_serialize(b, n)
        return VDPState(b.raw)

    def frame(self, v, top=TOP):
        canvas = np.zeros(CANVAS, np.uint8)
        for s in reversed([s for s in v.sprites() if s['pal'] == PAL and s['y'] > top]):
            px = v.sprite_pixels(s)
            ys, xs = np.nonzero(px)
            Y, X = ys + s['y'], xs + s['x']
            ok = (Y >= 0) & (Y < CANVAS[0]) & (X >= 0) & (X < CANVAS[1])
            canvas[Y[ok], X[ok]] = px[ys[ok], xs[ok]]
        return canvas

    def run(self, steps, state):
        c = self.core
        c.load_state(state)
        poses, index, order = [], {}, []
        for p1, p2, n in steps:
            c.buttons[0] = set(p1.split('+')) - {''}
            c.buttons[1] = set(p2.split('+')) - {''}
            for _ in range(n):
                c.run(1)
                v = self.vdp()
                f = self.frame(v, NUMBER_TOP)
                if not f.any():
                    continue
                ys, xs = np.nonzero(f)
                h = hashlib.md5(f[ys.min():ys.max() + 1, xs.min():xs.max() + 1].tobytes()).hexdigest()
                if h not in index:
                    index[h] = len(poses)
                    poses.append(self.frame(v))
                order.append(index[h])
        c.buttons = [set(), set()]
        v = self.vdp()
        cram = v.cram_raw[PAL * 16:PAL * 16 + 16]
        self.cram_p2 = v.cram_raw[16:32]          # player 2's line (Sub-Zero in mk_2p)
        return poses, order, cram


def anchor(p):
    """(x, y) of the fighter's origin in a full-screen pose: feet = lowest
    pixel row, horizontal = centre of the head (top 12 rows), which stays
    put while arms and legs swing."""
    ys, xs = np.nonzero(p)
    top = ys.min()
    head = xs[ys < top + 12]
    return int(round(head.mean())), int(ys.max()) + 1


def save(name, poses, order, cram):
    out = os.path.join(OUT, name)
    os.makedirs(out, exist_ok=True)
    np.save(os.path.join(out, 'indexed.npy'), np.array(poses))
    json.dump([anchor(p) for p in poses], open(os.path.join(out, 'anchors.json'), 'w'))
    open(os.path.join(out, 'order.txt'), 'w').write(' '.join(map(str, order)))
    json.dump(cram, open(os.path.join(out, 'cram.json'), 'w'))
    rgb = np.array([((c & 7) * 36, ((c >> 3) & 7) * 36, ((c >> 6) & 7) * 36) for c in cram], np.uint8)
    rgb[0] = (40, 40, 60)
    stack = np.array(poses)
    ys, xs = np.nonzero(stack.any(axis=0))
    crop = stack[:, max(0, ys.min() - 2):ys.max() + 3, max(0, xs.min() - 2):xs.max() + 3]
    h, w = crop.shape[1:]
    cols = min(len(crop), 10)
    rows = (len(crop) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * w, rows * h), (0, 0, 0))
    for i, p in enumerate(crop):
        sheet.paste(Image.fromarray(rgb[p]), ((i % cols) * w, (i // cols) * h))
    sheet.save(os.path.join(out, 'contact.png'))


# Each MK fighter: his own 2-player state (fighter as player 1, player 2 idle),
# output folder and specials (Scorpion's are in ACTIONS: SCORPION_ONLY).
FIGHTERS = {
    'scorpion': ('mk_2p.state', 'mk_moves', {}),
    'raiden': ('mk_raiden_2p.state', 'mk_moves_raiden', {
        'lightning': [hold('down', 3), hold('', 2), hold('right', 3), hold('a', 4), hold('', 90)],
        'teleport':  [hold('down', 3), hold('', 2), hold('up', 3), hold('', 90)],
        'torpedo':   [hold('left', 3), hold('', 3), hold('left', 3), hold('', 3), hold('right', 4), hold('', 120)],
    }),
    # tools/capture/mkduelstate.py makes these states (Johnny vs Sub-Zero; Sub-Zero vs Scorpion)
    'johnny': ('mk_johnny_2p.state', 'mk_moves_johnny', {
        'greenbolt':  [hold('left', 3), hold('', 2), hold('right', 3), hold('a', 4), hold('', 90)],
        'shadowkick': [hold('left', 3), hold('', 2), hold('right', 3), hold('c', 4), hold('', 100)],
        # MK1's split punch (Block + LP) up close: Sub-Zero walks over first
        'nutpunch':   [hold('right', 70), hold('b', 6), hold('b+a', 4), hold('b', 40), hold('', 40)],
        'nutpunch2':  [hold('right', 70), hold('y', 6), hold('y+a', 4), hold('y', 40), hold('', 40)],
        'nutpunch3':  [hold('right', 70), hold('b+a', 4), hold('', 60)],
    }),
    'subzero': ('mk_subzero_2p.state', 'mk_moves_subzero', {
        'iceblast':   [hold('down', 3), hold('', 2), hold('right', 3), hold('a', 4), hold('', 110)],
        'slide':      [hold('left', 10), hold('left+c+z', 8), hold('', 90)],   # MK CD: back + LK + HK (back + LK + Block is his low kick)
    }),
    # MK1's specials (MK pad: LP a, HP x, LK c, HK z, Block b); tools/capture/mkduelstate.py
    # liukang / kano / sonya make the states (each vs Sub-Zero)
    'liukang': ('mk_liukang_2p.state', 'mk_moves_liukang', {
        'fireball':   [hold('right', 4), hold('', 3), hold('right', 4), hold('x', 4), hold('', 100)],   # F, F + HP
        'flyingkick': [hold('right', 4), hold('', 3), hold('right', 4), hold('z', 4), hold('', 110)],   # F, F + HK
    }),
    'kano': ('mk_kano_2p.state', 'mk_moves_kano', {
        'headbutt':   [hold('right', 70), hold('', 5), hold('a', 4), hold('', 65)],  # close low punch
        'knife':      [hold('b', 4), hold('b+left', 4), hold('b', 3), hold('b+right', 4), hold('', 100)],   # Block held: B, F
        'cannonball': [hold('b', 4), hold('b+right', 3), hold('b+down', 3), hold('b+left', 3), hold('b+up', 3),
                       hold('b+right', 3), hold('', 120)],                                                  # Block held: a circle
    }),
    'sonya': ('mk_sonya_2p.state', 'mk_moves_sonya', {
        'rings':      [hold('x', 5), hold('', 4), hold('left', 5), hold('', 4), hold('x', 5), hold('', 100)],   # punch, back,
                                         # punch (MK CD; found by watching for the rings: LP, B, LP and B, B, LP only jab)
        'squarewave': [hold('right', 4), hold('', 3), hold('left', 4), hold('x', 4), hold('', 110)],    # F, B + HP
        'leggrab':    [hold('right', 70), hold('down+a+c+b', 6), hold('', 100)],                        # D + LP + LK + Block, close
    }),
}
SCORPION_ONLY = ('spear', 'spear_miss', 'spear_block', 'teleport')
LEAD_IN = {'subzero': 30, 'liukang': 30, 'kano': 30, 'sonya': 30}   # frames of no input first (these states' first frames ignore the pad)


def main():
    global OUT
    args = sys.argv[1:]
    fighter = 'scorpion'
    if args and args[0].startswith('--fighter='):
        fighter = args.pop(0).split('=', 1)[1]
    state_name, out, specials = FIGHTERS[fighter]
    OUT = os.path.join(ROOT, 'extracted', out)
    actions = dict(ACTIONS)
    if fighter != 'scorpion':
        for k in SCORPION_ONLY:
            actions.pop(k)
    actions.update(specials)
    if fighter in LEAD_IN:                   # his state ignores the pad for its first frames
        actions = {k: [hold('', LEAD_IN[fighter])] + v for k, v in actions.items()}
    names = args or list(actions)
    s = Session()
    state = os.path.join(ROOT, 'build', 'states', state_name)
    for name in names:
        poses, order, cram = s.run(actions[name], state)
        save(name, poses, order, cram)
        json.dump(s.cram_p2, open(os.path.join(OUT, name, 'cram_p2.json'), 'w'))
        print(f'{name:12s} {len(poses):3d} poses over {len(order)} frames')


if __name__ == '__main__':
    main()
