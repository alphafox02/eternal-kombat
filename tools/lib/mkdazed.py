#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Every MK fighter's own FINISH HIM daze (MK's 7-pose sway), from his art on the MK disc.

Drawn with tools/lib/mksch.py and placed as MK places each frame: the frame's
origin offset (its .OBJ descriptor) relative to his idle pose's. Only
Scorpion's was captured (tools/capture/mkdizzy.py); the others are made here.
Checked by making Scorpion's: identical to his capture.

MK's animation table (the .OBJ header's longword at $0E, +$CC: a longword per
animation) has the daze as entry 14: Scorpion's and Sub-Zero's $BC-$C2,
Johnny's $B8-$BE, Kano's $B6-$BC, Liu Kang's $B0-$B6, Raiden's $B3-$B9,
Sonya's $A5-$AB.

    mkdazed.py [MK_DIR ...]          -> extracted/MK_DIR/dizzy/ (indexed.npy, anchors.json,
                                        cram.json, order.txt), as tools/capture/mkdizzy.py writes Scorpion's
    mkdazed.py --check               -> Scorpion's, made this way, against his capture
"""
import argparse, json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inputs import ROOT
import mkframes, mkrecipes, mksch

ANIMS = 0xCC                      # the animation table, from the header's longword at $0E
DAZE = 14                         # its entry for FINISH HIM's daze
# each fighter's idle (his capture's first pose) is the reference: its recipe's source
FIGHTERS = {'mk_moves': 'mk_2p:1', 'mk_moves_subzero': 'mk_2p:2', 'mk_moves_johnny': 'mk_johnny_2p:1',
            'mk_moves_kano': 'mk_kano_2p:1', 'mk_moves_liukang': 'mk_liukang_2p:1',
            'mk_moves_raiden': 'mk_raiden_2p:1', 'mk_moves_sonya': 'mk_sonya_2p:1'}


# Scorpion's is his existing capture; the other fighters are decoded here.
SKIP = ('mk_moves',)


def art(name):
    d = os.path.join(ROOT, 'extracted', 'mk_us')
    return mksch.FighterArt(open(os.path.join(d, name + '.OBJ'), 'rb').read(),
                            open(os.path.join(d, name + '.SCH'), 'rb').read())


def anim(a, k):
    """MK frame numbers of animation k (up to its $FFFF). Only a plain list of
    frames: some lists hold control words (0, $FFxx) and run on into the next
    script before any $FFFF (docs/research/p2_fatality_animation_research.md) - refused."""
    base = mksch.u32(a.obj, 0x0E) + ANIMS
    p = mksch.u32(a.obj, base + 4 * k)
    out = []
    while mksch.u16(a.obj, p) != 0xFFFF:
        f = mksch.u16(a.obj, p)
        assert mkframes.FIRST <= f < mkframes.FIRST + a.count, f'animation {k}: {f:#x} is no frame (a control word)'
        out.append(f)
        p += 2
    assert 0 < len(out) <= 16, f'animation {k}: {len(out)} frames'
    return out


def origin(a, f, mirror):
    """Where MK puts frame f's drawn top-left, from the object's position:
    the descriptor's offset, plus the empty cells/pixels before the first
    drawn pixel (mirrored: measured from the right)."""
    n = f - mkframes.FIRST
    at = a.records + mksch.u16(a.obj, a.frame_table + n * 2)
    w = mksch.u16(a.obj, at + 2)
    s = lambda v: v - 65536 if v > 32767 else v
    dx, dy = s(mksch.u16(a.obj, at + 6)), s(mksch.u16(a.obj, at + 8))
    img = a.frame(n)
    ys, xs = np.nonzero(img)
    if mirror:                    # (the grid flipped about its own width: x runs from its right edge)
        return -(dx + w * 16) + (w * 16 - 1 - xs.max()), dy + ys.min()
    return dx + xs.min(), dy + ys.min()


def make(mk_dir):
    """The daze poses on the capture's 240x320 screen, with the idle's palette
    and anchor."""
    src = FIGHTERS[mk_dir]
    name, amir = mkframes.ART[src]
    a = art(name)
    idle = json.load(open(os.path.join(ROOT, 'data', 'mk_recipes', mk_dir, 'idle.json')))
    ref = next(p for p in idle['poses'] if p and len(p) == 1 and p[0][0] == src)[0]
    _, f0, mir0, x0, y0 = ref[:5]
    mirror = bool(amir) ^ bool(mir0)
    ox, oy = origin(a, f0, mirror)
    frames = mkrecipes.frames_of([src])
    poses = []
    for f in anim(a, DAZE):
        fx, fy = origin(a, f, mirror)
        poses.append(mkrecipes.draw([(src, f, mir0, x0 - ox + fx, y0 - oy + fy)], frames))
    return poses


def save(mk_dir, poses):
    d = os.path.join(ROOT, 'extracted', mk_dir)
    out = os.path.join(d, 'dizzy')
    os.makedirs(out, exist_ok=True)
    np.save(os.path.join(out, 'indexed.npy'), np.array(poses))
    anchor = json.load(open(os.path.join(d, 'idle', 'anchors.json')))[0]
    json.dump([anchor] * len(poses), open(os.path.join(out, 'anchors.json'), 'w'))
    open(os.path.join(out, 'cram.json'), 'w').write(open(os.path.join(d, 'idle', 'cram.json')).read())
    open(os.path.join(out, 'order.txt'), 'w').write(' '.join(map(str, range(len(poses)))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('dirs', nargs='*')
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    if a.check:
        have = np.load(os.path.join(ROOT, 'extracted', 'mk_moves', 'dizzy', 'indexed.npy'))
        got = make('mk_moves')
        same = [bool((h == g).all()) for h, g in zip(have, got)]
        print(f"Scorpion's daze made from his art: {sum(same)}/{len(have)} poses identical to his capture")
        sys.exit(0 if all(same) and len(got) == len(have) else 1)
    for mk_dir in a.dirs or [d for d in FIGHTERS if d not in SKIP]:
        poses = make(mk_dir)
        save(mk_dir, poses)
        print(f'{mk_dir}: {len(poses)} daze poses -> extracted/{mk_dir}/dizzy')


if __name__ == '__main__':
    main()
