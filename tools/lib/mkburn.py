#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The burning victim of Sonya's MK fatality (the kiss of death), for her art.

MK draws the burning body, the flames and the charred skeleton in the VICTIM's
palette (tools/lib/mkfatality_capture.py sonya: fatality_mk_victim/, Sub-Zero there:
blue fire). An EC loser can't have that art, so (as Scorpion's fatality) the
victim object shows frames of HER sheets in HER palette line: these frames,
MK's shapes recoloured by brightness - the flames into her warm browns and skin
tones, the skeleton into her greys.

    mkburn.py   -> extracted/mk_moves_sonya/fatality_burn/ (indexed in her MK
                   palette, facing right; anchors: the victim's feet)
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from inputs import ROOT

D = os.path.join(ROOT, 'extracted', 'mk_moves_sonya')
FIRE = [10, 11, 12]                     # victim capture poses: the flames, burning black (7, 8: her body
                                        #  shows: hers kept; 9 is 128 tiles - player 1 can't show it: a hang)
BONES = [13, 14, 16, 18, 20, 21]        # the skeleton: standing, then collapsing
FIRE_RAMP = [7, 8, 9, 10, 11, 15]       # her MK palette: dark brown-red ... light skin, white
BONE_RAMP = [12, 13, 14, 15]            # black, grey, light grey, white


def recolour(idx, cram, ramp):
    rgb = np.array([((c & 7) * 36, ((c >> 3) & 7) * 36, ((c >> 6) & 7) * 36) for c in cram], float)
    lum = rgb[idx].mean(-1)
    lit = idx > 0
    if not lit.any():
        return np.zeros_like(idx)
    lo, hi = lum[lit].min(), lum[lit].max()
    k = np.clip(((lum - lo) / max(1.0, hi - lo) * len(ramp)).astype(int), 0, len(ramp) - 1)
    out = np.array(ramp, np.uint8)[k]
    out[~lit] = 0
    return out


def main():
    vic = np.load(os.path.join(D, 'fatality_mk_victim', 'indexed.npy'))
    vcram = json.load(open(os.path.join(D, 'fatality_mk_victim', 'cram.json')))
    vx, vy = json.load(open(os.path.join(D, 'fatality_mk_victim', 'anchors.json')))[0]
    poses = [recolour(vic[k], vcram, FIRE_RAMP) for k in FIRE] + [recolour(vic[k], vcram, BONE_RAMP) for k in BONES]
    W = poses[0].shape[1]
    poses = [p[:, ::-1] for p in poses]          # the victim faced left in MK: stored facing right
    out = os.path.join(D, 'fatality_burn')
    os.makedirs(out, exist_ok=True)
    np.save(os.path.join(out, 'indexed.npy'), np.array(poses))
    json.dump([[W - 1 - vx, vy]] * len(poses), open(os.path.join(out, 'anchors.json'), 'w'))
    json.dump(json.load(open(os.path.join(D, 'idle', 'cram.json'))), open(os.path.join(out, 'cram.json'), 'w'))
    open(os.path.join(out, 'order.txt'), 'w').write(' '.join(map(str, range(len(poses)))))
    from PIL import Image
    cram = json.load(open(os.path.join(D, 'idle', 'cram.json')))
    pal = np.array([((c & 7) * 36, ((c >> 3) & 7) * 36, ((c >> 6) & 7) * 36) for c in cram], np.uint8)
    pal[0] = (40, 40, 60)
    ims = [Image.fromarray(pal[p]).crop((W - vx - 70, vy - 180, W - vx + 70, vy + 10)) for p in poses]
    sheet = Image.new('RGB', (140 * len(ims), 190))
    for i, im in enumerate(ims):
        sheet.paste(im, (140 * i, 0))
    sheet.save(os.path.join(out, 'contact.png'))
    print(f'{len(poses)} poses -> {os.path.relpath(out, ROOT)}')


if __name__ == '__main__':
    main()
