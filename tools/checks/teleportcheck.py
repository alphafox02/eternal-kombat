#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise Raiden's teleport and Scorpion's teleport punch on either side.

Creates a duel from this disc's freshly booted menu.state, or uses --state.
Raiden must not spawn Blade's old effect; Scorpion must show the full incoming
art and hit an opponent near the arrival edge, and leave MK's frozen double
(his stance, effect sheet $7C: patches.scorpion_ghost_art) where he took off,
in his palette and facing, until he lands - also in a mirror match (--mirror:
his opponent is Scorpion too, standing). --verify-art decodes the double from
the disc and compares it with MK's idle pose 3, pixel for pixel.

    teleportcheck.py raiden|scorpion [--as-p2] [--mirror] [--verify-art] [--state STATE] [--disc CUE]
"""
import argparse
import os
import subprocess
import sys
import tempfile

import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
from inputs import ROOT
import scd

P1, P2 = 0x2E188, 0x2E330
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big')
S = lambda r, o: int.from_bytes(r[o:o + 2], 'big', signed=True)
GHOST = 0x7C00                  # mkinputs.GHOST_FRAME


def verify_art(cue):
    """The double's frame, decoded from SEN.PL on the disc, against MK's idle pose 3."""
    import disc, ecdeath, mkprojectile, patches, scorpion_full as sf
    patches.use(patches.SCORPION)
    poses, anchors, cram = sf.load_action(ROOT, 'idle')
    full, (ax, ay) = sf.scale_pose(poses[3], anchors[3], cram)
    full = sf.remap_colours(full)
    yy, xx = np.nonzero(full)
    expected = np.zeros((256, 256), np.uint8)
    expected[yy - (ay - sf.FOOT_DROP) + 128, xx - ax + 128] = full[yy, xx]
    pl = disc.Disc(cue).read_file('SEN.PL')
    chunks = mkprojectile.chunks(pl)
    sheet, size = next((o, n) for o, n, t in chunks if t == 4 and W(pl, o + 10) // 4 == GHOST >> 8)
    sid = W(pl, sheet + 12)
    source, length = next((o, n) for o, n, t in chunks if t == 0 and W(pl, o + 10) // 4 == sid)
    got = ecdeath.frames(pl[source + 20:source + length], pl[sheet:sheet + size])[0]
    wrong = np.count_nonzero(got != expected)
    print(f'teleport double: {len(xx)} pixels of MK idle pose 3, {wrong} wrong')
    if wrong or not len(xx):
        raise SystemExit('the double does not reproduce MK\'s stance')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('fighter', choices=('raiden', 'scorpion'))
    ap.add_argument('--as-p2', action='store_true')
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    ap.add_argument('--state', help='duel state created for this disc')
    ap.add_argument('--mirror', action='store_true', help='Scorpion: his opponent is Scorpion too')
    ap.add_argument('--verify-art', action='store_true', help="Scorpion: decode the double's art and compare")
    a = ap.parse_args()
    if a.fighter == 'scorpion' and a.verify_art:
        verify_art(a.disc)
    with tempfile.TemporaryDirectory(prefix='ek-teleport-') as tmp:
        state = a.state or os.path.join(tmp, 'duel.state')
        grid = 7 if a.fighter == 'raiden' else 20
        other = grid if a.mirror else 0
        p1, p2 = (other, grid) if a.as_p2 else (grid, other)
        if not a.state:
            subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', a.disc,
                            '--p1', str(p1), '--p2', str(p2), '--stage', '11', '--out', state], check=True)
        c = scd.Core(saves=os.path.join(tmp, 'saves'))
        c.load(a.disc)
        c.load_state(state)
        c.run(60)
        actor, victim, port = (P2, P1, 1) if a.as_p2 else (P1, P2, 0)
        if a.fighter == 'scorpion':
            p = np.load(os.path.join(ROOT, 'extracted', 'mk_moves', 'teleport_mk', 'indexed.npy'))
            widths = [np.ptp(np.nonzero(p[i])[1]) + 1 for i in (5, 6)]
            if widths[0] < 90 or widths[1] < 45:
                raise SystemExit(f'incoming art is cropped: widths {widths}')
            cam = S(c.prg_ram(), 0x2B070)
            ax, vx = (cam + 240, cam + 45) if a.as_p2 else (cam + 80, cam + 275)
            for off in (0x36, 0x3A, 0x4E, 0x56, 0xB2, 0xBA):
                c.poke_prg(actor + off, ax.to_bytes(2, 'big'))
                c.poke_prg(victim + off, vx.to_bytes(2, 'big'))
            c.run(20)
            sequence = [(set(), 10), ({'down'}, 3), (set(), 2),
                        ({'right' if a.as_p2 else 'left'}, 3), ({'y'}, 4), (set(), 130)]
        else:
            sequence = [(set(), 10), ({'down'}, 3), (set(), 2), ({'up'}, 3), (set(), 180)]
        before = W(c.prg_ram(), victim + 0x76)
        started, effects, arrival = False, 0, None
        takeoff, doubles, double_bad, double_after = None, 0, [], 0
        for held, n in sequence:
            c.buttons[port] = held
            for _ in range(n):
                c.run(1)
                r = c.prg_ram()
                started |= W(r, actor + 0xBE) & 0x7FFF == (0x31 if a.fighter == 'raiden' else 0x35)
                if a.fighter == 'raiden':
                    for obj in range(0x2CABC, 0x2E080, 0xA6):
                        owner = int.from_bytes(r[obj + 0x90:obj + 0x94], 'big')
                        if owner == actor and 0x7600 <= W(r, obj + 0x1A) <= 0x7605:
                            effects += 1
                else:
                    move = W(r, actor + 0xBE) & 0x7FFF
                    if takeoff is None and move == 0x35:
                        takeoff = S(r, actor + 0x4E)
                    ghosts = [o for o in range(0x2CABC, 0x2E080, 0xA6)
                              if W(r, o + 0x1A) == GHOST and any(r[o:o + 8]) and not r[o + 0x82] & 4]
                    if move == 0x35:
                        doubles += bool(ghosts)
                        for o in ghosts:
                            if (abs(S(r, o + 0x4E) - takeoff) > 2 or W(r, o + 0x1E) & 0x6000 != W(r, actor + 0x1E) & 0x6000
                                    or W(r, o + 0x20) & 0x800 != W(r, actor + 0x20) & 0x800 and doubles == 1):
                                double_bad.append((S(r, o + 0x4E), takeoff, hex(W(r, o + 0x1E)), hex(W(r, actor + 0x1E))))
                    elif started:
                        double_after += bool(ghosts)
                    if arrival is None and W(r, actor + 0x1A) == 0x8662:
                        rel = S(r, actor + 0x4E) - S(r, 0x2B070)
                        if (rel < 160 if a.as_p2 else rel > 160):
                            arrival = rel
        after = W(c.prg_ram(), victim + 0x76)
        ok = started and (effects == 0 if a.fighter == 'raiden' else
                          after < before and arrival is not None and 80 <= arrival <= 240
                          and doubles >= 20 and not double_bad and not double_after)
        print(f'{a.fighter} teleport{" (mirror)" if a.mirror else ""}: started {started}, stray effects {effects}, '
              f'arrival {arrival}, victim health {before} -> {after}'
              + (f', double shown {doubles} frames, wrong {double_bad[:2]}, left after {double_after}'
                 if a.fighter == 'scorpion' else '') + f' -> {"ok" if ok else "FAILED"}')
        if not ok:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
