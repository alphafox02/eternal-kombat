#!/usr/bin/env python3
"""MK projectiles as EC effect art: the flying part of an MK special (Raiden's
lightning ball, Sub-Zero's ice, Johnny's green bolt), cut out of the MK
capture, written into the fighter's effect sheet $45 and its raw-tile source
(Blade's, kept in every MK fighter's .PL), so an object of his can fly it
across the screen while he shows his own frame (mkinputs.emit_proj).

EC's effect art (docs/re_notes.md 'Travelling projectiles'): a type-0 chunk
whose flag word (+12) is 4 holds RAW 4bpp tiles; a type-4 chunk is the sheet:
frame count at +20, offsets (from +22) at +22, then frame records: A-box count
and boxes (x1 x2 y1 y2), B count, pieces (size word, attr word = tile index |
$6000, x, y), $8000. Both chunks keep their sizes here (zero-padded), so the
file's chunk chain is untouched.

    mkprojectile.py [fighter]      # writes shots/projectile_<fighter>.png (a preview)
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from scipy import ndimage
from inputs import ROOT

SHEET = 0x44                       # Blade's effect sheet the projectile takes over ($45 is the
                                   # explosion EC draws where a projectile hits: kept)
# fighter key -> (MK capture, flight poses, impact poses)
PROJ = {
    'raiden':  ('lightning', [14, 15], []),
    'subzero': ('iceblast', [14], [18]),
    'johnny':  ('greenbolt', [10, 12], [16, 18]),
}
NEAR = 40                          # px past his anchor where the projectile part starts


def cut(mk_dir, action, pose):
    """The projectile part of a capture pose: its components beyond NEAR px
    in front of him, cropped. -> (indexed image, anchor x, anchor y = centre)."""
    d = os.path.join(ROOT, 'extracted', mk_dir, action)
    P = np.load(os.path.join(d, 'indexed.npy'))
    ax = json.load(open(os.path.join(d, 'anchors.json')))[0][0]
    img = P[pose]
    lab, n = ndimage.label(img > 0)
    keep = np.zeros(img.shape, bool)
    for i in range(1, n + 1):
        ys, xs = np.nonzero(lab == i)
        if xs.min() > ax + NEAR and len(xs) > 8:
            keep |= lab == i
    ys, xs = np.nonzero(keep)
    if not len(xs):
        raise ValueError(f'{action} pose {pose}: no projectile part')
    out = np.where(keep, img, 0)[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    return out, out.shape[1] // 2, out.shape[0] // 2


def strip(img, ax):
    """A cast pose without its projectile part (the object flies that)."""
    lab, n = ndimage.label(img > 0)
    out = img.copy()
    for i in range(1, n + 1):
        xs = np.nonzero(lab == i)[1]
        if xs.min() > ax + NEAR:
            out[lab == i] = 0
    return out


def tiles_and_pieces(img, ox, oy, first_tile):
    """Raw tiles (column-major within each piece, as the VDP) and pieces of at
    most 4x4 tiles for an indexed image; offsets from (ox, oy)."""
    h, w = img.shape
    th, tw = (h + 7) // 8, (w + 7) // 8
    pad = np.zeros((th * 8, tw * 8), np.uint8)
    pad[:h, :w] = img
    tiles, pieces = [], []
    for px in range(0, tw, 4):
        for py in range(0, th, 4):
            pw, ph = min(4, tw - px), min(4, th - py)
            start = first_tile + len(tiles)
            for cx in range(pw):
                for cy in range(ph):
                    t = pad[8 * (py + cy):8 * (py + cy) + 8, 8 * (px + cx):8 * (px + cx) + 8]
                    tiles.append(bytes((int(t[r, 2 * k]) << 4) | int(t[r, 2 * k + 1]) for r in range(8) for k in range(4)))
            pieces.append(((pw - 1) << 10 | (ph - 1) << 8 | 0x50, 0x6000 | start,
                           8 * px - ox, 8 * py - oy))
    return tiles, pieces


def frame_record(img, ox, oy, pieces):
    h, w = img.shape
    sb = lambda v: max(-128, min(127, v)) & 0xFF
    rec = bytearray((1).to_bytes(2, 'big') + bytes((sb(-ox), sb(w - ox), sb(-oy), sb(h - oy))) + bytes(2))
    for size, attr, x, y in pieces:
        rec += size.to_bytes(2, 'big') + attr.to_bytes(2, 'big') + bytes((sb(x), sb(y)))
    rec += b'\x80\x00'
    return bytes(rec)


def chunks(b):
    o, out = 0, []
    while o + 12 <= len(b):
        ln = int.from_bytes(b[o:o + 4], 'big')
        if ln == 0:
            break
        out.append((o, ln, int.from_bytes(b[o + 4:o + 6], 'big')))
        o += ln
    return out


def build(pl, key, mk_dir, remap=lambda a: a, extra=()):
    """pl: the fighter's .PL (a copy of Blade's). Returns it with sheet $45
    and its tile source holding his MK projectile: frames 0..k-1 the flight,
    then the impact; (flight frame count, impact frame count)."""
    action, flight, impact = PROJ[key]
    pl = bytearray(pl)
    ch = chunks(pl)
    sheet = next(o for o, ln, t in ch if t == 4 and int.from_bytes(pl[o + 10:o + 12], 'big') // 4 == SHEET)
    src_id = int.from_bytes(pl[sheet + 12:sheet + 14], 'big')
    src, src_len = next((o, ln) for o, ln, t in ch if t == 0 and int.from_bytes(pl[o + 10:o + 12], 'big') // 4 == src_id)   # (stored x4)
    assert int.from_bytes(pl[src + 12:src + 14], 'big') == 4, 'not a raw effect tile source'
    room_tiles = (src_len - 20) // 32
    sheet_len = int.from_bytes(pl[sheet:sheet + 4], 'big')
    nfr = int.from_bytes(pl[sheet + 20:sheet + 22], 'big')
    tiles, recs = [], []
    for pose in flight + impact:
        img, ox, oy = cut(mk_dir, action, pose)
        img = remap(img)
        t, p = tiles_and_pieces(img, ox, oy, len(tiles))
        tiles += t
        recs.append(frame_record(img, ox, oy, p))
    recs += list(extra)                 # frames whose tiles are uploaded over these at need
                                        # (mkinputs: Sub-Zero's fatality heads)
    assert len(tiles) <= room_tiles, f'{key}: {len(tiles)} tiles, room {room_tiles}'
    data = b''.join(tiles).ljust(src_len - 20, b'\0')
    pl[src + 20:src + src_len] = data
    table = sheet + 22
    body = bytearray()
    offs = []
    for k in range(nfr):
        r = recs[min(k, len(recs) - 1)] if k < len(recs) else recs[0]
        if k < len(recs):
            offs.append(2 * nfr + len(body))
            body += r
        else:
            offs.append(offs[0])                     # unused frames: the first flight frame
    room = sheet_len - 22 - 2 * nfr
    assert len(body) <= room, f'{key}: frame records {len(body)} bytes, room {room}'
    pl[table:table + 2 * nfr] = b''.join(o.to_bytes(2, 'big') for o in offs)
    pl[table + 2 * nfr:sheet + sheet_len] = bytes(body).ljust(room, b'\0')
    return bytes(pl), (len(flight), len(impact))


def preview(key):
    from PIL import Image
    mk_dir = {'raiden': 'mk_moves_raiden', 'subzero': 'mk_moves_subzero', 'johnny': 'mk_moves_johnny'}[key]
    action, flight, impact = PROJ[key]
    cram = json.load(open(os.path.join(ROOT, 'extracted', mk_dir, action, 'cram.json')))
    pal = np.array([((c & 7) * 36, ((c >> 3) & 7) * 36, ((c >> 6) & 7) * 36) for c in cram], np.uint8)
    pal[0] = (40, 40, 60)
    ims = [Image.fromarray(pal[cut(mk_dir, action, p)[0]]) for p in flight + impact]
    w = sum(i.width + 8 for i in ims)
    out = Image.new('RGB', (w, max(i.height for i in ims)), (40, 40, 60))
    x = 0
    for i in ims:
        out.paste(i, (x, 0))
        x += i.width + 8
    out = out.resize((out.width * 3, out.height * 3), Image.NEAREST)
    path = os.path.join(ROOT, 'shots', f'projectile_{key}.png')
    out.save(path)
    print(path)


if __name__ == '__main__':
    for k in (sys.argv[1:] or list(PROJ)):
        preview(k)
