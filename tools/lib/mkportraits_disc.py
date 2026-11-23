#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Rebuild the MK fighters' select portraits from the MK disc, Reptile's and Shang Tsung's included.

The seven from MK CD's RJC.PRG, and Reptile's: MK has none (he isn't on its
select screen); MK draws him as its ninjas in green, so his is Sub-Zero's with the blues turned green
(reptile(): hue only; saturation and brightness kept). And Shang Tsung's: MK1 has no picture of him
but his fighter art, so his is his standing pose's head and shoulders at their own size (shang(): MK's
own pixels and palette, brightened 1.6x: the select icons share one 15-colour palette, where his dark robe
and ground went to mud; enlarged, the 15-pixel face blurred), on EC's icons' blue ground, from
extracted/mk_moves_shang (prepare.py makes it first: mkshangmoves.py).

    mkportraits_disc.py --disc extracted/mk_us --check REFERENCE_EXTRACTED
    mkportraits_disc.py --disc extracted/mk_us --out extracted

The numeric tile maps below describe the crops used by mkportrait.py, inferred
from the original select screen. Pixel and palette data come from the disc.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # (tools run with python -P)
import argparse
import io
from pathlib import Path

import numpy as np
from PIL import Image
from mkpitbottom import rnc1

ROOT = Path(__file__).resolve().parent.parent.parent
TILES = 0x2474E
PALETTE = 0x7842
# x of the first 8-pixel tile in the 42x50 crop, followed by 7 rows x 6 tiles.
MAPS = {
 'scorpion': (-3, [[27,28,29,30,31,27],[27,59,60,61,62,27],[27,88,89,90,91,27],[27,116,117,118,119,27],[27,146,147,148,149,150],[180,181,182,183,184,185],[215,216,0,0,217,218]]),
 'raiden': (-1, [[3,22,23,24,25,26],[53,54,55,56,57,58],[82,83,84,85,86,87],[111,112,113,114,3,0],[140,141,142,143,144,0],[175,176,3,177,178,179],[209,210,211,212,213,214]]),
 'kano': (-1, [[11,12,13,14,15,16],[43,44,45,46,47,48],[72,73,74,75,76,77],[101,102,103,104,105,106],[130,131,132,133,134,135],[163,164,165,166,167,168],[198,199,200,201,202,203]]),
 'sonya': (-4, [[17,18,19,20,21,17],[17,49,50,51,52,17],[17,78,79,80,81,17],[17,107,108,109,110,17],[17,136,137,138,139,17],[169,170,171,172,173,174],[204,205,206,207,0,208]]),
 'liukang': (-2, [[6,7,8,9,10,6],[38,39,40,41,42,6],[67,68,69,70,71,6],[6,97,98,99,100,6],[6,126,127,128,129,6],[157,158,159,160,161,162],[192,193,194,195,196,197]]),
 'johnny': (0, [[0,1,2,3,4,5],[32,33,34,35,36,37],[3,63,64,65,66,0],[3,92,93,94,95,96],[120,121,122,123,124,122],[151,152,153,154,155,156],[186,187,188,189,190,0]]),
 'subzero': (-3, [[219,219,220,221,219,219],[219,250,251,3,252,219],[219,271,272,273,274,219],[295,296,297,298,299,219],[320,321,322,323,324,325],[338,339,340,341,342,343],[356,357,358,359,360,361]]),
}
# Genesis Plus GX's color conversion used by the existing captured PNGs.
RED_BLUE = (0, 32, 65, 98, 139, 172, 205, 238)
GREEN = (0, 34, 68, 101, 137, 170, 206, 238)


def portraits(data):
    packed = rnc1(data, TILES)
    raw = np.frombuffer(packed, np.uint8).reshape(-1, 8, 4)
    tiles = np.empty((len(raw), 8, 8), np.uint8)
    tiles[:, :, 0::2], tiles[:, :, 1::2] = raw >> 4, raw & 15
    words = [int.from_bytes(data[PALETTE + i:PALETTE + i + 2], 'big') for i in range(0, 32, 2)]
    pal = np.array([(RED_BLUE[(c >> 1) & 7], GREEN[(c >> 5) & 7], RED_BLUE[(c >> 9) & 7]) for c in words], np.uint8)
    for name, (start, rows) in MAPS.items():
        image = np.zeros((50, 42), np.uint8)
        for ry, row in enumerate(rows):
            y = -1 + ry * 8
            for rx, tile in enumerate(row):
                x = start + rx * 8
                y0, y1, x0, x1 = max(0,y), min(50,y+8), max(0,x), min(42,x+8)
                if y0 < y1 and x0 < x1:
                    image[y0:y1, x0:x1] = tiles[tile, y0-y:y1-y, x0-x:x1-x]
        out = io.BytesIO()
        Image.fromarray(pal[image]).save(out, format='PNG')
        yield name, out.getvalue()
        if name == 'subzero':
            out = io.BytesIO()
            reptile(Image.fromarray(pal[image])).save(out, format='PNG')
            yield 'reptile', out.getvalue()


def shang(extracted):
    """Shang's 42x50 portrait from his standing pose (extracted/mk_moves_shang/idle: indexed, MK's 9-bit
    palette), the crop centred on his head's top rows."""
    import json
    d = Path(extracted) / 'mk_moves_shang' / 'idle'
    a = np.load(d / 'indexed.npy')[0]
    cram = json.loads((d / 'cram.json').read_text())
    pal = np.array([(RED_BLUE[c & 7], GREEN[c >> 3 & 7], RED_BLUE[c >> 6 & 7]) for c in cram], np.uint8)
    im = np.clip(pal[a].astype(float) * 1.6, 0, 255).astype(np.uint8)
    im[a == 0] = (32, 34, 139)
    ys, xs = np.nonzero(a)
    top = int(ys.min())
    x = int(np.median(xs[ys < top + 12]))
    out = io.BytesIO()
    Image.fromarray(im).crop((x - 21, top - 3, x + 21, top + 47)).save(out, format='PNG')
    return out.getvalue()


def reptile(im):
    """Sub-Zero's portrait with its blues (PIL hue 120-185, saturated) turned green (hue - 70)."""
    hsv = np.array(im.convert('HSV')).astype(int)
    h, s = hsv[..., 0], hsv[..., 1]
    hsv[..., 0] = np.where((h >= 120) & (h <= 185) & (s >= 60), h - 70, h)
    return Image.fromarray(hsv.astype(np.uint8), 'HSV').convert('RGB')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--disc', type=Path, default=ROOT / 'extracted' / 'mk_us')
    ap.add_argument('--fighter', choices=sorted(MAPS) + ['reptile', 'shang'])
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', type=Path, metavar='REFERENCE_EXTRACTED')
    group.add_argument('--out', type=Path, metavar='EXTRACTED')
    a = ap.parse_args()
    bad = 0
    made = (list(portraits((a.disc / 'RJC.PRG').read_bytes())) if a.fighter != 'shang' else []) \
        + ([('shang', shang(a.out or a.check))] if a.fighter in (None, 'shang') else [])
    for name, png in made:
        if a.fighter and name != a.fighter:
            continue
        folder = {'reptile': 'mk_reptile', 'shang': 'mk_shang'}.get(name) or 'mk_moves' + ('' if name == 'scorpion' else '_' + name)
        target = (a.check or a.out) / folder / 'portrait.png'
        if a.check:
            try:
                equal = target.read_bytes() == png
            except OSError:
                equal = False
            print(f'{name}: {"identical" if equal else "DIFFERENT"}')
            bad += not equal
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(png)
            print(f'{name}: {target}')
    if bad:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
