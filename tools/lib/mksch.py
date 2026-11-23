#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Decode MK Sega CD fighter frames directly from a fighter's OBJ/SCH files.

    mksch.py extracted/mk_us/SCORPION.OBJ 5 --out scorpion.png

Frame numbers address the OBJ frame table (MK animation numbers $10 and up
normally correspond to OBJ frame number minus $10). Output is indexed PNG; index 0 is
transparent. Supply --palette with 16 Genesis CRAM values in JSON, such as a
cram.json produced by mkmoves.py, to use the fighter's colors.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image


def u16(data, at):
    if at < 0 or at + 2 > len(data):
        raise ValueError(f'word outside file: {at:#x}')
    return int.from_bytes(data[at:at + 2], 'big')


def u32(data, at):
    if at < 0 or at + 4 > len(data):
        raise ValueError(f'longword outside file: {at:#x}')
    return int.from_bytes(data[at:at + 4], 'big')


class FighterArt:
    def __init__(self, obj, sch):
        self.obj, self.sch = obj, sch
        self.records = u32(obj, 0)
        self.frame_table = u32(obj, 4)
        self.count = u16(obj, 12)
        self.dictionary = u32(obj, 0x1A)
        if len(sch) % 64:
            raise ValueError('SCH length is not a whole number of cells')

    def cell(self, number):
        if not 0 <= number < len(self.sch) // 64:
            raise ValueError(f'cell outside SCH: {number}')
        at = self.dictionary + (number // 32) * 512
        if at + 512 > len(self.obj):
            raise ValueError(f'missing dictionary for cell {number}')
        first, second = self.obj[at:at + 256], self.obj[at + 256:at + 512]
        codes = self.sch[number * 64:(number + 1) * 64]
        raw = bytes(v for i in range(0, 64, 4) for table in (first, second)
                    for v in (table[k] for k in codes[i:i + 4]))
        b = np.frombuffer(raw, dtype=np.uint8)
        return np.stack((b >> 4, b & 15), axis=1).reshape(2, 2, 8, 8).transpose(1, 2, 0, 3).reshape(16, 16)

    def frame(self, number):
        if not 0 <= number < self.count:
            raise ValueError(f'frame must be between 0 and {self.count - 1}')
        at = self.records + u16(self.obj, self.frame_table + number * 2)
        cells, width, height = (u16(self.obj, at + i) for i in (0, 2, 4))
        if cells != width * height or width > 64 or height > 64:
            raise ValueError(f'unsupported frame descriptor {number}: {cells}, {width} x {height}')
        if at + 10 + cells * 2 > len(self.obj):
            raise ValueError('frame descriptor exceeds OBJ')
        image = np.zeros((height * 16, width * 16), dtype=np.uint8)
        for i in range(cells):
            cell = u16(self.obj, at + 10 + 2 * i)
            if cell:
                y, x = divmod(i, width)
                image[y * 16:y * 16 + 16, x * 16:x * 16 + 16] = self.cell(cell)
        return image


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('obj', type=Path)
    ap.add_argument('frame', type=lambda s: int(s, 0), nargs='?', help='OBJ frame index')
    ap.add_argument('--all', action='store_true', help='export all OBJ frames into --out directory')
    ap.add_argument('--sch', type=Path, help='defaults to the OBJ path with .SCH extension')
    ap.add_argument('--palette', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    if args.all == (args.frame is not None):
        ap.error('supply a frame number or --all')
    art = FighterArt(args.obj.read_bytes(), (args.sch or args.obj.with_suffix('.SCH')).read_bytes())
    colors = json.loads(args.palette.read_text()) if args.palette else [i | (i << 3) | (i << 6) for i in range(8)] * 2
    if len(colors) != 16:
        raise ValueError('palette must contain exactly 16 CRAM values')
    palette = [c for v in colors for c in ((v & 7) * 36, ((v >> 3) & 7) * 36, ((v >> 6) & 7) * 36)]
    if args.all:
        args.out.mkdir(parents=True, exist_ok=True)
    for number in range(art.count) if args.all else (args.frame,):
        pixels = art.frame(number)
        image = Image.frombytes('P', (pixels.shape[1], pixels.shape[0]), pixels.tobytes())
        image.putpalette(palette + [0] * (768 - len(palette)))
        image.info['transparency'] = 0
        path = args.out / f'frame_{number:03d}.png' if args.all else args.out
        image.save(path)
    print(f'{art.count if args.all else 1} frame(s) -> {args.out}')


if __name__ == '__main__':
    main()
