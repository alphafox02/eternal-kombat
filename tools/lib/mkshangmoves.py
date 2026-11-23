#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Shang Tsung's MK moves as capture folders, drawn straight from MK's EMP.OBJ frames.

The format tools/lib/mkmoves.py writes for the playable fighters, in MK's own
order and timing (tools/lib/mkshangref.py: MK's Shang fight).

MK can't be played as Shang, so his moves can't be captured the usual way;
but MK draws him unscaled, his frames as they are on the disc, so placing
those frames on the screen as MK does gives the same pictures a capture
would. Writes extracted/mk_moves_shang/<action>/: indexed.npy (poses on a
240 x 320 screen, facing right as player 1), order.txt (pose per frame),
anchors.json, cram.json (his colours, PAC.PRG $1C130, as the VDP holds them).

His own moves (EMP frame numbers, game frames each, seen in MK):
  stance 1; walk toward 2 (3) then 3 held; walk away 4 (5), 5 (3), 6 held;
  skull volley 7 (2), 8 (2), 9 (5), 10 (4), 11 held (the skulls themselves, 12-17
  and their burst 56-59, are mkprojectile's); hit 53 (5), 54 (3), 55 (5);
  knockdown 46, 47 (in the air), 48, 49, 50 (on the floor).
MK gave him no punches, kicks, jumps, crouches or blocks: those actions are
his stance (the CPU's Shang never uses them; see mkinputs' Shang filter).

    mkshangmoves.py      -> extracted/mk_moves_shang/ (tools/prepare.py runs this)
"""
import json, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inputs import ROOT
import mkshang

OUT = os.path.join(ROOT, 'extracted', 'mk_moves_shang')
CANVAS = (240, 320)
FEET = (100, 212)              # where MK's captures stand player 1 (x of his anchor, floor row)
STANCE = 1
GLIDE_FWD, GLIDE_BACK = 3, 6     # the poses he holds gliding toward / away (mkinputs.walk_plan)
PALETTE_AT = 0x1C130          # PAC.PRG: his colours (checked live in MK's fight; $1C110 is Goro's)

# action: [(EMP frame, game frames)] - timings from MK's own fight (docs/notes/2026-11.md,
# "MK's own Shang Tsung fight"); the captures' lead-ins (stance before the move)
# as tools/lib/mkmoves.py's scripts give them, so the planners find the move where
# they look for it (hit captures: the reaction from scorpion_full.HIT_LANDS)
OWN = {
    'idle':      [(1, 90)],
    'walk_fwd':  [(1, 1), (2, 3), (3, 116)],
    'walk_back': [(1, 1), (4, 5), (5, 3), (6, 111)],
    # (MK gave him no throw: Blade's throw keeps its code with his cast's poses; the
    # CPU's Shang never throws - mkinputs' Shang filter)
    'throw':     [(1, 20), (7, 6), (8, 6), (9, 10), (10, 8), (11, 30), (1, 40)],
    # his skull volley (Blade's cast, move $34; the Spec aliases 'spear' to it): 11 held
    # while three skulls go (mkinputs.skull_plan / emit_skull)
    'skull':     [(1, 14), (7, 2), (8, 2), (9, 5), (10, 4), (11, 130), (1, 30)],
    # his morph's blends into each MK fighter (mkinputs.emit_morph: 3 per fighter, MK's order)
    'morph':     [(f, 1) for f in range(22, 43)],
    'hit_high':  [(1, 66), (53, 5), (54, 3), (55, 5), (1, 65)],
    'hit_low':   [(1, 66), (53, 5), (54, 3), (55, 5), (1, 65)],
    'hit_kick':  [(1, 66), (53, 5), (54, 3), (55, 5), (1, 65)],
    'knockdown': [(1, 66), (46, 9), (47, 36), (48, 6), (49, 6), (50, 40), (49, 6), (48, 6), (1, 37)],
    'lying':     [(50, 60)],
    'swept':     [(1, 66), (46, 9), (47, 20), (48, 6), (49, 6), (50, 40), (49, 6), (48, 6), (1, 45)],
}
NONE = ('btn_a', 'btn_b', 'btn_c', 'btn_x', 'btn_y', 'btn_z', 'crouch', 'crouch_a', 'crouch_b', 'crouch_c',
        'crouch_x', 'crouch_y', 'crouch_z', 'crouch_block', 'block', 'uppercut', 'sweep', 'roundhouse',
        'jump_up', 'jump_fwd', 'jump_back', 'jump_a', 'jump_b', 'jump_c', 'jump_x', 'jump_y', 'jump_z',
        'jumpup_a', 'jumpup_b', 'jumpup_c', 'jumpup_x', 'jumpup_y', 'jumpup_z', 'dizzy',
        'teleport')


def cram():
    out = []
    raw = open(os.path.join(mkshang.MK, 'PAC.PRG'), 'rb').read()[PALETTE_AT:PALETTE_AT + 32]
    for w in (int.from_bytes(raw[i:i + 2], 'big') for i in range(0, 32, 2)):
        r, g, b = (w >> 1) & 7, (w >> 5) & 7, (w >> 9) & 7
        out.append(b << 6 | g << 3 | r)
    out[0] = 0                    # (transparent: the VDP shows 0 there, as the captures hold)
    return out


def place(img, anchor):
    """An EMP frame on the screen with its feet anchor at FEET."""
    a = np.asarray(img)
    c = np.zeros(CANVAS, np.uint8)
    x0, y0 = FEET[0] - anchor[0], FEET[1] - anchor[1]
    ys, xs = np.nonzero(a)
    Y, X = ys + y0, xs + x0
    ok = (Y >= 0) & (Y < CANVAS[0]) & (X >= 0) & (X < CANVAS[1])
    c[Y[ok], X[ok]] = a[ys[ok], xs[ok]]
    return c


def build():
    import mkmoves
    frames = mkshang.frames(list(range(1, 62)))
    pal = cram()
    acts = dict(OWN)
    for a in NONE:
        acts[a] = [(STANCE, 60)]
    for name, steps in acts.items():
        order_f = [f for f, n in steps for _ in range(n)]
        nums = list(dict.fromkeys(order_f))
        poses = [place(*frames[f]) for f in nums]
        order = [nums.index(f) for f in order_f]
        d = os.path.join(OUT, name)
        os.makedirs(d, exist_ok=True)
        np.save(os.path.join(d, 'indexed.npy'), np.array(poses))
        json.dump([mkmoves.anchor(p) for p in poses], open(os.path.join(d, 'anchors.json'), 'w'))
        open(os.path.join(d, 'order.txt'), 'w').write(' '.join(map(str, order)))
        json.dump(pal, open(os.path.join(d, 'cram.json'), 'w'))
        json.dump(pal, open(os.path.join(d, 'cram_p2.json'), 'w'))
        json.dump(nums, open(os.path.join(d, 'emp.json'), 'w'))       # (which EMP frame each pose is)
        if name == 'walk_fwd':
            # his glide, both ways from this one action: MK steps into it (toward: 2;
            # away: 4, 5) and then holds 3 toward, 6 away (mkinputs.walk_plan, glide_scripts)
            back = [f for f, _ in OWN['walk_back'][1:]]
            more = [f for f in back if f not in nums]
            nums += more
            poses += [place(*frames[f]) for f in more]
            np.save(os.path.join(d, 'indexed.npy'), np.array(poses))
            json.dump([mkmoves.anchor(p) for p in poses], open(os.path.join(d, 'anchors.json'), 'w'))
            json.dump(nums, open(os.path.join(d, 'emp.json'), 'w'))
            start = lambda act, held: [[nums.index(f), n] for f, n in OWN[act][1:] if f != held]
            json.dump({'fwd': nums.index(GLIDE_FWD), 'back': nums.index(GLIDE_BACK),
                       'fwd_start': start('walk_fwd', GLIDE_FWD), 'back_start': start('walk_back', GLIDE_BACK)},
                      open(os.path.join(d, 'glide.json'), 'w'))
    print(f'{len(acts)} actions -> {OUT}')


if __name__ == '__main__':
    build()
