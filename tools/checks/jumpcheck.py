#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""MK's jumps: the straight-up jump as long in the air as the forward one, and lower.

(patches.mk_jump_height, mkinputs.jump_up_launch.) Per fighter (player 1 in a duel), feet more than
12 px off the floor:
  - straight up: MK's frames (mkinputs.JUMP_UP_AIR) within 3; it was EC's gravity at MK's height
    (Kano 33 frames to MK's 43);
  - forward and back: EC's gravity again (the roll sets it with MK's launch): 40-48 frames, the
    height MK's x1.08 (mkinputs.JUMP_VY_FWD, set ~21 px after the takeoff) within 12 px;
  - a jump kick (B) in either lands within 4 frames of the plain jump.

    jumpcheck.py [--disc CUE] [--grid 18 20 7 15]     (select-grid presses; run after play.py test)
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
import mkinputs
from inputs import ROOT

P1 = 0x2E188
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big', signed=True)


def jump(c, held, kick=False):
    """(peak px, frames above 12 px, landing frame) of player 1's jump."""
    c.buttons[0] = set(); c.run(90)
    floor = W(c.prg_ram(), P1 + 0x52)
    c.buttons[0] = set(held)
    ys = []
    for f in range(130):
        if f == 4:
            c.buttons[0] = set()
        if kick and f == 14:
            c.buttons[0] = {'b'}
        if kick and f == 16:
            c.buttons[0] = set()
        c.run(1)
        ys.append(floor - W(c.prg_ram(), P1 + 0x52))
    s = next(i for i, y in enumerate(ys) if y > 12)
    e = next(i for i in range(s, len(ys)) if ys[i] <= 12)
    return max(ys), e - s, next(i for i in range(s, len(ys)) if ys[i] <= 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    ap.add_argument('--grid', type=int, nargs='*', default=[18, 20, 7, 15])
    a = ap.parse_args()
    bad = []
    with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, 'build')) as tmp:
        for g in a.grid:
            st = os.path.join(tmp, f'{g}.state')
            subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', a.disc,
                            '--p1', str(g), '--p2', '0', '--out', st], check=True, capture_output=True)
            c = scd.Core()
            c.load(a.disc)
            c.load_state(st)
            fid = int.from_bytes(c.prg_ram()[0x31428:0x3142A], 'big') + 2
            c.run(60)
            up, fwd, back = jump(c, ['up']), jump(c, ['up', 'right']), jump(c, ['up', 'left'])
            upk, fwdk = jump(c, ['up'], True), jump(c, ['up', 'right'], True)
            want = mkinputs.JUMP_UP_AIR[fid]
            h = 21 + mkinputs.JUMP_VY_FWD[fid] ** 2 / (2 * mkinputs.EC_GRAVITY)   # (set ~21 px up: mkinputs)
            print(f'id {fid}: up {up[1]} frames (MK {want}), {up[0]} px; forward {fwd[1]} frames, {fwd[0]} px '
                  f'(~{h:.0f}); back {back[1]}, {back[0]} px; landings plain/kick: up {up[2]}/{upk[2]}, '
                  f'forward {fwd[2]}/{fwdk[2]}')
            if abs(up[1] - want) > 3:
                bad.append(f'id {fid}: straight up {up[1]} frames in the air, MK {want}')
            for name, j in (('forward', fwd), ('back', back)):
                if not 40 <= j[1] <= 48 or abs(j[0] - h) > 12:
                    bad.append(f'id {fid}: {name} {j[1]} frames, {j[0]} px (want 40-48, ~{h:.0f})')
            for name, p, k in (('up', up, upk), ('forward', fwd, fwdk)):
                if abs(p[2] - k[2]) > 4:
                    bad.append(f'id {fid}: a kick in the {name} jump lands at {k[2]}, the jump at {p[2]}')
    for b in bad:
        print('FAIL:', b)
    print('jumpcheck:', 'FAIL' if bad else 'ok')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
