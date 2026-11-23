#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Rebuild the MK Pit fight planes and palette from disc data.

BACKGD4.BIN's tiles and maps, PAC.PRG's palette lines 0 and 1 and the moon
(MOON: tiles on plane A) -> extracted/mk_stages/pit/plane_a.png, plane_b.png,
cram.json, laid out as MK's VDP planes in a fight.

    mkpit_disc.py --out extracted                (tools/prepare.py runs this)
    mkpit_disc.py --check REFERENCE_EXTRACTED

--check compares plane A and CRAM byte for byte. For plane B it compares all
pixels below row 31; EC blanks the HUD rows before using that layer.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # (tools run with python -P)
import argparse
import io
import json
from pathlib import Path
import numpy as np
from PIL import Image
from mkpitbottom import rnc1

ROOT = Path(__file__).resolve().parent.parent.parent
MOON = [[664,768,769,770,771,772,773,664],
        [774,775,776,777,778,779,780,664],
        [781,782,783,784,785,786,787,788],
        [789,790,791,792,793,794,795,796],
        [797,798,799,800,801,802,803,804],
        [805,806,807,808,809,810,811,664],
        [664,812,813,814,815,816,817,664]]


def words(data):
    return [int.from_bytes(data[i:i + 2], 'big') for i in range(0, len(data), 2)]


def cram(values):
    return [((v >> 1) & 7) | (((v >> 5) & 7) << 3) | (((v >> 9) & 7) << 6) for v in values]


def png(array):
    out = io.BytesIO()
    Image.fromarray(array, 'RGBA').save(out, format='PNG')
    return out.getvalue()


def build(bg, pac):
    offsets = [int.from_bytes(bg[i:i+4], 'big') for i in range(0, 24, 4)]
    source = rnc1(bg, offsets[0])
    raw = np.frombuffer(source, np.uint8).reshape(-1, 8, 4)
    tiles = np.empty((len(raw), 8, 8), np.uint8)
    tiles[:, :, 0::2], tiles[:, :, 1::2] = raw >> 4, raw & 15
    a = np.frombuffer(rnc1(bg, offsets[1]), '>u2').reshape(86, 110)
    b = np.frombuffer(rnc1(bg, offsets[2]), '>u2').reshape(15, 64)
    colors = (cram(words(pac[0x1c0d0:0x1c0f0])) + cram(words(pac[0x1c1f0:0x1c210]))
              + cram(words(bg[offsets[5]:offsets[5]+64])))
    for i in (0, 16, 32, 48): colors[i] = 0
    colors[41] = 33  # palette line 2 entry 9, set by the fight state
    palette = np.array([((v & 7)*36, ((v >> 3)&7)*36, ((v >> 6)&7)*36) for v in colors], np.uint8)
    result = [np.zeros((256, 1024, 4), np.uint8), np.zeros((256, 1024, 4), np.uint8)]

    def tile(dest, y, x, value, line):
        value = int(value)
        p = tiles[value & 0x7ff]
        if value & 0x800: p = p[:, ::-1]
        if value & 0x1000: p = p[::-1]
        dst = dest[y*8:y*8+8, x*8:x*8+8]
        dst[:, :, :3] = palette[line * 16 + p]
        dst[:, :, 3] = (p > 0).astype(np.uint8) * 255

    for y in range(32):
        if y == 11: continue
        row = a[0 if y < 11 else y - 11]
        for x, val in enumerate(row): tile(result[0], y, x, val, 3)
    for y,row in enumerate(MOON, 2):
        for x,val in enumerate(row, 15): tile(result[0], y, x, val, 2)
    for y,row in enumerate(b, 6):
        for x in range(128): tile(result[1], y, x, row[x % 64], 2)
    return {'plane_a.png': png(result[0]), 'plane_b.png': png(result[1]),
            'cram.json': json.dumps(colors).encode()}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--disc', type=Path, default=ROOT/'extracted'/'mk_us')
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', type=Path, metavar='REFERENCE_EXTRACTED')
    group.add_argument('--out', type=Path, metavar='EXTRACTED')
    a = ap.parse_args()
    results = build((a.disc/'BACKGD4.BIN').read_bytes(), (a.disc/'PAC.PRG').read_bytes())
    bad = 0
    for name, data in results.items():
        path = (a.check or a.out)/'mk_stages'/'pit'/name
        if a.check:
            try:
                ref = path.read_bytes()
                if name == 'plane_b.png':
                    expected = np.asarray(Image.open(io.BytesIO(ref)).convert('RGBA'))
                    got = np.asarray(Image.open(io.BytesIO(data)).convert('RGBA'))
                    equal = expected.shape == got.shape and np.array_equal(expected[32:], got[32:])
                else:
                    equal = ref == data
            except OSError:
                equal = False
            print(f'{name}: {"identical" if equal else "DIFFERENT"}' + (' below HUD' if name == 'plane_b.png' else ''))
            bad += not equal
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            print(path)
    if bad: raise SystemExit(1)


if __name__ == '__main__': main()
