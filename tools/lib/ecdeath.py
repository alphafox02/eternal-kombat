#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""EC's per-fighter death art (Z<xx>.BIN), read and drawn as contact sheets.

One Z<xx>.BIN per EC fighter, loaded at $7C000 by stage Sudden Deaths (e.g. the
Chicago Theater usher's shotgun); LAR.BGI's table at +$284 maps victim id - 2 ->
file id $EC..$FD.

Each file: two raw-tile sources (type 0, flag 4) and two sprite sheets
(type 4). Frame record: A-box count + 4-byte boxes, B-point count + 2-byte points,
pieces (size word, attr word = tile | flags, x byte, y byte), $8000.

    ecdeath.py ZSH [cram.json [LINE]]   # build/shots/ec_deaths/ZSH_<sheet>.png contact sheets
                                        # (LINE: the CRAM palette line, default 0)
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from inputs import ROOT
from mkprojectile import chunks

W16 = lambda b, o: int.from_bytes(b[o:o + 2], 'big')
S8 = lambda v: v - 256 if v > 127 else v


def load(name):
    b = open(os.path.join(ROOT, 'extracted', 'ec_us', name + '.BIN'), 'rb').read()
    srcs, sheets = {}, []
    for o, ln, t in chunks(b):
        if t == 0 and W16(b, o + 12) == 4:
            srcs[W16(b, o + 10) // 4] = b[o + 20:o + ln]
        elif t == 4:
            sheets.append((W16(b, o + 10) // 4, W16(b, o + 12), b[o:o + ln]))
    return srcs, sheets


def tile(src, i):
    t = src[32 * i:32 * i + 32]
    a = np.zeros((8, 8), np.uint8)
    for r in range(8):
        for k in range(4):
            v = t[4 * r + k] if 4 * r + k < len(t) else 0
            a[r, 2 * k], a[r, 2 * k + 1] = v >> 4, v & 15
    return a


def frames(src, sheet):
    """-> one 256x256 indexed image per frame, the frame's origin at (128, 128)."""
    n = W16(sheet, 20)
    out = []
    for k in range(n):
        o = 22 + W16(sheet, 22 + 2 * k)
        na = W16(sheet, o); o += 2 + 4 * na
        nb = W16(sheet, o); o += 2 + 2 * nb              # B: 2-byte points (x, y)
        pieces = []
        while W16(sheet, o) != 0x8000 and o < len(sheet) - 6:
            size, attr = W16(sheet, o), W16(sheet, o + 2)
            pieces.append((size, attr, S8(sheet[o + 4]), S8(sheet[o + 5])))
            o += 6
        img = np.zeros((256, 256), np.uint8)
        for size, attr, x, y in pieces:
            w, h = ((size >> 10) & 3) + 1, ((size >> 8) & 3) + 1
            t0 = attr & 0x7FF
            hf, vf = attr & 0x800, attr & 0x1000
            for cx in range(w):
                for cy in range(h):
                    tt = tile(src, t0 + cx * h + cy)
                    px, py = (w - 1 - cx) if hf else cx, (h - 1 - cy) if vf else cy
                    if hf: tt = tt[:, ::-1]
                    if vf: tt = tt[::-1]
                    X, Y = 128 + x + 8 * px, 128 + y + 8 * py
                    if 0 <= X <= 248 and 0 <= Y <= 248:
                        reg = img[Y:Y + 8, X:X + 8]
                        reg[tt > 0] = tt[tt > 0]
        out.append(img)
    return out


def contact(name, cram=None, tag=''):
    from PIL import Image
    srcs, sheets = load(name)
    if cram:
        pal = np.array([((c & 7) * 36, ((c >> 3) & 7) * 36, ((c >> 6) & 7) * 36) for c in cram[:16]], np.uint8)   # 9-bit BGR, as vdp.cram_raw
    else:
        pal = np.array([(v * 17, v * 17, v * 17) for v in range(16)], np.uint8)
    pal[0] = (40, 40, 60)
    paths = []
    for sid, src_id, sh in sheets:
        fr = frames(srcs[src_id], sh)
        ys, xs = np.nonzero(np.any(np.array(fr) > 0, 0))
        crop = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
        ims = [Image.fromarray(pal[f]).crop(crop) for f in fr]
        cw, chh = ims[0].width + 4, ims[0].height + 4
        o = Image.new('RGB', (cw * 6, chh * ((len(ims) + 5) // 6)), (20, 20, 20))
        for i, im in enumerate(ims):
            o.paste(im, ((i % 6) * cw, (i // 6) * chh))
        o = o.resize((o.width * 2, o.height * 2), Image.NEAREST)
        p = os.path.join(ROOT, 'build', 'shots', 'ec_deaths', f'{name}_{sid:02X}{tag}.png')
        o.save(p)
        paths.append(p)
        print(p, len(fr), 'frames')
    return paths


if __name__ == '__main__':
    cram = json.load(open(sys.argv[2])) if len(sys.argv) > 2 else None
    line = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    contact(sys.argv[1], cram[16 * line:16 * line + 16] if cram else None)
