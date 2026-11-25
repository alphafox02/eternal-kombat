#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""MK's Courtyard, Palace Gates, Warrior Shrine, Throne Room and Goro's Lair in our build, as MK shows them.

For each (tools/lib/mkstages.py), a duel on it (Scorpion vs Shadow, duelstate.py --mk-stage):
  - the stage's music is its MK track (EC's track number for it: $1A42(a6));
  - our fighters stand where MK's do (lowest fighter pixel, mkstages.MK_FEET, within 1);
  - both fighters walk to the camera's left stop, then its right: our camera's range is MK's
    (data/mk_stages/<stage>.json), and every band with art moves between the stops as MK's does
    (its scroll registers' change on each line: MK's rate x the range, within 1 px);
  - the background (planes only, no sprites: the VDP's scroll and priorities) at each stop against
    MK's as it would be there (its planes from the disc - tools/lib/mkstage_disc.py - placed by its
    measured bands, the disc's frame of the tiles MK animates): at most MAX_DIFF of the pixels differ,
    each line allowed 1 px off (EC's band scroll drops the fraction MK rounds) - what's left is the
    colour fit (EC's palette has 23 colours for the stage, MK's 30).

    mkstagecheck.py [--stages courtyard,gates] [--disc CUE]
"""
import argparse, json, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import numpy as np
from PIL import Image
import scd
from inputs import ROOT
from vdp import VDPState
import mkstages

WALK = 900                        # frames walking to each stop
# Pixels unlike MK's at most (measured 2026-11-24 + 2%, each line allowed 1 px: the courtyard 5.0 / 5.4%,
# the gates 7.4 / 7.3%, the shrine 7.6 / 8.1% - the colour fit, 23 colours for MK's 30 -, the throne and
# the lair 0.1%)
MAX_DIFF = {'courtyard': 0.075, 'gates': 0.095, 'shrine': 0.10}
MAX_DIFF_OTHER = 0.02


def scroll(st, v):
    mode = v.regs[11] & 3
    base = (v.regs[13] & 0x3F) << 10
    tab = np.frombuffer(v.vram[base:base + 224 * 4], '>i2').reshape(224, 2).astype(int)
    if mode == 0:
        tab = np.repeat(tab[:1], 224, 0)
    elif mode == 2:
        tab = np.repeat(tab[::8][:28], 8, 0)
    from vdp import VDP
    vsa = st[VDP + 0x10480] | st[VDP + 0x10481] << 8
    vsb = st[VDP + 0x10482] | st[VDP + 0x10483] << 8
    return tab[:, 0], tab[:, 1], vsa, vsb


def compose(planes, prio, ha, hb, vsa, vsb):
    """The background as the VDP draws it: planes {A, B: RGBA}, prio {A, B: per-pixel 0/1}, scrolls."""
    out = np.zeros((224, 320, 3), np.uint8)
    layers = {}
    for p, hs, vs in (('A', ha, vsa), ('B', hb, vsb)):
        img = planes[p]
        H, W = img.shape[:2]
        ys = (np.arange(224)[:, None] + vs) % H
        xs = (np.arange(320)[None, :] - hs[:, None]) % W
        layers[p] = (img[ys, xs, :3], img[ys, xs, 3] > 0, prio[p][ys, xs] > 0)
    (ai, au, ap), (bi, bu, bp) = layers['A'], layers['B']
    out[bu] = bi[bu]
    out[au] = ai[au]
    m = bu & bp & ~(au & ap)
    out[m] = bi[m]
    return out


def ours(st):
    v = VDPState(st)
    w, h = v.plane_size()
    planes, prio = {}, {}
    for p in 'AB':
        img, used = v.plane(p)
        planes[p] = np.dstack([img, used * 255]).astype(np.uint8)
        base = ((v.regs[2] & 0x38) << 10) if p == 'A' else ((v.regs[4] & 7) << 13)
        nt = np.frombuffer(v.vram[base:base + w * h * 2], '>u2').reshape(h, w)
        prio[p] = np.kron((nt >> 15) & 1, np.ones((8, 8), np.uint8))
    ha, hb, vsa, vsb = scroll(st, v)
    return compose(planes, prio, ha, hb, vsa, vsb), (ha, hb)


def mk_expected(key, side):
    """MK's background at its camera's left or right stop, from its planes and measured bands."""
    planes, _, prio = mkstages.art(key)
    planes = {p: planes[p] for p in 'AB'}
    pp = {p: np.kron(prio[p], np.ones((8, 8), np.uint8)) for p in 'AB'}
    cam = mkstages._json(key)['camera']
    lo, hi = cam['camera']
    c = lo if side == 'left' else hi
    hs = {}
    for p in 'AB':
        h = np.zeros(224, int)
        for b in cam['plane_' + p.lower()]:
            l0, l1 = b['lines']
            h[l0:l1 + 1] = int(round(b['scroll_at_left'] - b['rate'] * (c - lo)))
        hs[p] = h
    return compose(planes, pp, hs['A'], hs['B'], mkstages.VSCROLL, mkstages.VSCROLL)


def feet(v):
    lows = []
    for s in v.sprites():
        if s['pal'] not in (2, 3) or s['y'] < 40:
            continue
        ys = np.nonzero(v.sprite_pixels(s).any(1))[0]
        if len(ys):
            lows.append(s['y'] + int(ys.max()))
    return max(lows) if lows else None


def stage(c, disc, tmp, key, shots=None):
    bad = []
    st = os.path.join(tmp, f'{key}.state')
    subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', disc,
                    '--p1', '20', '--p2', '0', '--mk-stage', key, '--out', st], check=True, capture_output=True)
    c.load_state(st)
    c.run(2)
    r = c.prg_ram()
    word = lambda o: int.from_bytes(r[0x30000 + o:0x30000 + o + 2], 'big', signed=True)
    track = word(0x1A42)
    want = mkstages.MK_TRACK_EC[dict((k, t) for k, _, t in mkstages.STAGES)[key]]
    if word(0xAB2) != mkstages.MODE or track != want:
        bad.append(f'stage ${word(0xAB2):X}, track {track} (want ${mkstages.MODE:X}, {want})')
    f = []
    for _ in range(10):
        c.run(1)
        f.append(feet(VDPState(c.snapshot())) or 0)
    f = sorted(set(f))
    if abs(f[-1] - mkstages.MK_FEET[key]) > 1:
        bad.append(f'feet at {f} (MK {mkstages.MK_FEET[key]})')
    cam = mkstages._json(key)['camera']
    lo, hi = cam['camera']
    stops, diffs = {}, []
    for side in ('left', 'right'):
        for _ in range(WALK):
            c.buttons = [{side}, {side}]
            c.run(1)
        c.buttons = [set(), set()]
        snap = c.snapshot()
        img, hs = ours(snap)
        stops[side] = (int.from_bytes(c.prg_ram()[0x2B070:0x2B072], 'big', signed=True), hs)
        exp = mk_expected(key, side)
        # each line may sit 1 px off (EC's band scroll drops the fraction MK rounds: 0 to 1 px at the far stop)
        d = np.ones(img.shape[:2], bool)
        for dx in (-1, 0, 1):
            d &= np.any(np.roll(img, dx, axis=1) != exp, axis=2)
        diffs.append(float(d.mean()))
        if shots:
            Image.fromarray(np.concatenate([exp, img, (d[:, :, None] * 255).repeat(3, 2).astype(np.uint8)], 1)).save(
                os.path.join(shots, f'{key}_{side}.png'))
    if (stops['left'][0], stops['right'][0]) != (0, hi - lo):
        bad.append(f'camera {stops["left"][0]}..{stops["right"][0]} (MK\'s range {hi - lo})')
    for p, k in (('a', 0), ('b', 1)):
        moved = stops['right'][1][k] - stops['left'][1][k]
        for b in cam['plane_' + p]:
            l0, l1 = b['lines']
            want = -b['rate'] * (hi - lo)
            got = moved[l0:l1 + 1]
            layers = [x for x in mkstages.bands(key)[0] if x['plane'] == p.upper()]
            has_art = any(x['y'] <= l0 + mkstages.VSCROLL < x['y'] + x['h'] for x in layers)
            if has_art and np.abs(got - want).max() > 1.5:
                bad.append(f'plane {p.upper()} lines {l0}-{l1}: moved {sorted(set(got.tolist()))[:3]} (MK {want:.0f})')
    limit = MAX_DIFF.get(key, MAX_DIFF_OTHER)
    if max(diffs) > limit:
        bad.append(f'background {100 * diffs[0]:.1f}% / {100 * diffs[1]:.1f}% unlike MK\'s (at most {100 * limit:.0f}%)')
    return bad, diffs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stages', default=','.join(mkstages.PACKED))
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    ap.add_argument('--shots', help='folder for MK | ours | difference pictures at each stop')
    a = ap.parse_args()
    if a.shots:
        os.makedirs(a.shots, exist_ok=True)
    failed = False
    with tempfile.TemporaryDirectory(prefix='ek-mkstage-') as tmp:
        c = scd.Core(saves=os.path.join(tmp, 'saves'))
        c.load(a.disc)
        for key in a.stages.split(','):
            bad, diffs = stage(c, a.disc, tmp, key, a.shots)
            print(f'{key}: ' + ('ok' if not bad else 'FAILED\n  ' + '\n  '.join(bad))
                  + f'  (background {100 * diffs[0]:.1f}% / {100 * diffs[1]:.1f}% unlike MK\'s)', flush=True)
            failed |= bool(bad)
    print('MK stages:', 'FAILED' if failed else 'ok')
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
