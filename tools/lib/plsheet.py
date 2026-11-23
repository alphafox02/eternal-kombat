#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Every pose of an EC fighter art file (.PL) on one contact sheet.

Each is labelled SHEET:FRAME (the numbers a module's frame words use:
$1A(a5) = sheet, $1B = frame), drawn from its own data: tiles unpacked by the game's own code
(tools/lib/plmap.py runs SUB.BIN $11784), laid out by the sheet chunk's piece
list (w, h, x, y from the feet; tools/lib/ecpl.py's piece_record). Grey levels
(colour index), no palette: for telling which frame shows what.

    plsheet.py ECX.PL out.png [--disc extracted/ec_us] [--cols 12] [--sheets 4a,4b]
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image, ImageDraw
import plmap

W = lambda d, o: int.from_bytes(d[o:o + 2], 'big')
S8 = lambda v: v - 256 if v > 127 else v


def sheets(pl):
    """[(sheet id, resource offset, sheet chunk offset, frame count)]."""
    out = []
    for res, _ in plmap.resources(pl):
        sheet = res - 0x14 + int.from_bytes(pl[res - 0x14:res - 0x10], 'big') + 0x10   # the chunk after it
        sid = W(pl, sheet - 6) >> 2          # its header: long length, 0004 0000 0000, sheet * 4
        out.append((sid, res, sheet, W(pl, sheet + 4)))
    return out


def chunks(pl):
    """[chunk offset]: a .PL is a chain of chunks, each led by its length (long)."""
    out, pos = [], 0
    while pos + 8 <= len(pl) and int.from_bytes(pl[pos:pos + 4], 'big'):
        out.append(pos)
        pos += int.from_bytes(pl[pos:pos + 4], 'big')
    return out


def all_sheets(pl):
    """Every sheet, compressed or raw: [dict(sid, kind ('packed' or 'raw'),
    sheet (its frame table), n (frames), res (packed: the resource),
    tiles / ntiles / src (raw: its tile source chunk's data, tile count, chunk))].
    A sheet chunk (word +4 = 4) names its tile source (+$C); the source chunk
    (word +4 = 0, source * 4 at +$A) is compressed (+$C = $18, resource at
    +$E) or raw tiles (+$C = 4: tiles at +$E, byte count at +$12)."""
    L = lambda o: int.from_bytes(pl[o:o + 4], 'big')
    cs = chunks(pl)
    src = {W(pl, c + 0x0A) >> 2: c for c in cs if W(pl, c + 4) == 0}
    out = []
    for c in cs:
        if W(pl, c + 4) != 4:
            continue
        sid, s = W(pl, c + 0x0A) >> 2, src.get(W(pl, c + 0x0C))
        if s is None:
            continue
        d = dict(sid=sid, sheet=c + 0x10, n=W(pl, c + 0x14), chunk=c)
        if W(pl, s + 0x0C) == 0x18:
            d.update(kind='packed', res=L(s + 0x0E))
        else:
            d.update(kind='raw', tiles=L(s + 0x0E), ntiles=W(pl, s + 0x12) // 32, src=s)
        out.append(d)
    return out


def render_raw(pl, sh, f, raw=False):
    """A raw sheet's frame: each piece's tiles from its attribute word's tile number."""
    img = np.zeros((256, 256), np.uint8)
    q = sh['sheet'] + 6 + W(pl, sh['sheet'] + 6 + 2 * f)
    q += 2 + 4 * W(pl, q)
    q += 2 + 2 * W(pl, q)
    while not W(pl, q) & 0x8000:
        d6, t = W(pl, q), W(pl, q + 2) & 0x7FF
        w, h, x, y = ((d6 >> 10) & 3) + 1, ((d6 >> 8) & 3) + 1, S8(pl[q + 4]), S8(pl[q + 5])
        k = 0
        for cx in range(w):
            for cy in range(h):
                o = sh['tiles'] + 32 * (t + k)
                k += 1
                px = np.frombuffer(pl[o:o + 32], np.uint8)
                if len(px) < 32:
                    continue
                blk = np.empty((8, 8), np.uint8)
                blk[:, 0::2] = (px >> 4).reshape(8, 4)
                blk[:, 1::2] = (px & 15).reshape(8, 4)
                X, Y = 128 + x + cx * 8, 200 + y + cy * 8
                if 0 <= X <= 248 and 0 <= Y <= 248:
                    img[Y:Y + 8, X:X + 8] = np.where(blk > 0, blk if raw else 40 + blk * 13, img[Y:Y + 8, X:X + 8])
        q += 6
    return img


def pieces(pl, sheet, f):
    o = W(pl, sheet + 6 + 2 * f)
    q = sheet + 6 + o
    q += 2 + 4 * W(pl, q)
    q += 2 + 2 * W(pl, q)
    out = []
    while not W(pl, q) & 0x8000:
        d6 = W(pl, q)
        w, h = ((d6 >> 10) & 3) + 1, ((d6 >> 8) & 3) + 1
        out.append((w, h, S8(pl[q + 4]), S8(pl[q + 5])))
        q += 6
    return out


def render(pl, sub, res, sheet, f, sid, raw=False):
    """256 x 256, the feet's centre at (128, 200): grey levels, or (raw) colour indices."""
    _, tiles = plmap.frame_reads(pl, sub, res, f, sheet_byte=sid)
    ps = pieces(pl, sheet, f)
    img = np.zeros((256, 256), np.uint8)
    t = 0
    for w, h, x, y in ps:
        for cx in range(w):
            for cy in range(h):
                b = tiles[t * 32:t * 32 + 32]
                t += 1
                if len(b) < 32:
                    continue
                px = np.frombuffer(b, np.uint8)
                blk = np.empty((8, 8), np.uint8)
                blk[:, 0::2] = (px >> 4).reshape(8, 4)
                blk[:, 1::2] = (px & 15).reshape(8, 4)
                X, Y = 128 + x + cx * 8, 200 + y + cy * 8
                if 0 <= X <= 248 and 0 <= Y <= 248:
                    img[Y:Y + 8, X:X + 8] = np.where(blk > 0, blk if raw else 40 + blk * 13, img[Y:Y + 8, X:X + 8])
    return img


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('pl')
    ap.add_argument('out')
    ap.add_argument('--disc', default=os.path.join(plmap.ROOT, 'extracted', 'ec_us'))
    ap.add_argument('--cols', type=int, default=12)
    ap.add_argument('--sheets', type=lambda v: [int(x, 16) for x in v.split(',')])
    a = ap.parse_args()
    pl = open(a.pl if os.path.exists(a.pl) else os.path.join(a.disc, a.pl), 'rb').read()
    sub = open(os.path.join(a.disc, 'SUB.BIN'), 'rb').read()
    cells = []
    for sh in all_sheets(pl):
        sid, n = sh['sid'], sh['n']
        if a.sheets and sid not in a.sheets:
            continue
        for f in range(n):
            try:
                im = (render(pl, sub, sh['res'], sh['sheet'], f, sid) if sh['kind'] == 'packed'
                      else render_raw(pl, sh, f))
            except Exception as e:                      # noqa: BLE001
                print(f'{sid:02X}:{f}: {e}')
                continue
            ys, xs = np.nonzero(im)
            if len(ys):
                im = im[max(ys.min() - 2, 0):ys.max() + 3, max(xs.min() - 2, 0):xs.max() + 3]
            cells.append((f'{sid:02X}:{f}', im))
    cw, ch = 130, 150
    rows = (len(cells) + a.cols - 1) // a.cols
    out = Image.new('L', (a.cols * cw, rows * ch), 0)
    d = ImageDraw.Draw(out)
    for i, (lab, im) in enumerate(cells):
        x, y = (i % a.cols) * cw, (i // a.cols) * ch
        p = Image.fromarray(im)
        p.thumbnail((cw - 4, ch - 16))
        out.paste(p, (x + 2, y + 14))
        d.text((x + 2, y + 1), lab, fill=255)
    out.save(a.out)
    print(f'{len(cells)} poses -> {a.out}')


if __name__ == '__main__':
    main()
