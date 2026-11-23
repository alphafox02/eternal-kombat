#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""MK projectiles as EC effect art, cut out of the MK captures.

The flying part of an MK special (Raiden's lightning ball, Sub-Zero's ice,
Johnny's green bolt, ...), cut out of the MK capture, written into the
fighter's effect sheet $44 (SHEET) and its raw-tile source
(Blade's, kept in every MK fighter's .PL), so an object of his can fly it
across the screen while he shows his own frame (mkinputs.emit_proj).

EC's effect art (docs/notes/2026-11.md 'Travelling projectiles'): a type-0 chunk
whose flag word (+12) is 4 holds RAW 4bpp tiles; a type-4 chunk is the sheet:
frame count at +20, offsets (from +22) at +22, then frame records: A-box count
and boxes (x1 x2 y1 y2), B count, pieces (size word, attr word = tile index |
$6000, x, y), $8000. Both chunks keep their sizes here (zero-padded), so the
file's chunk chain is untouched.

    mkprojectile.py [FIGHTER ...]  # writes build/shots/projectile_<fighter>.png (a preview; default: all of PROJ)
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
    'reptile': ('iceblast', [14], [18]),     # (Sub-Zero's: MK's ninjas are one set of sprites)
    'johnny':  ('greenbolt', [10, 12], [16, 18]),
    'liukang': ('fireball', [16, 17], [21]),        # (one burst: two overrun the effect source's 91 tiles)
    'kano':    ('knife', [21, 25], []),           # (MK: a spinning crescent, then the blade: alternating, it spins)
    'sonya':   ('rings', [16, 18], [23, 25]),
    # Shang Tsung: no capture (MK can't play him): his EMP.OBJ frames as MK draws them,
    # placed from his feet (mkshang.frames' anchors), so an object at his feet shows the
    # skull growing in his hand (13, 16), flying (17) and bursting (56, 57) where MK does.
    # The 91 tiles hold these five, packed to their non-empty tiles (12, 14, 15 and the
    # burst's 58-60 don't fit). Only the flying skull hits (BOXED). mkinputs.emit_skull.
    'shang':   ('emp', [13, 16, 17], [56, 57]),
}
BOXED = {'shang': {17}}
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


def tiles_and_pieces(img, ox, oy, first_tile, skip_empty=False):
    """Raw tiles (column-major within each piece, as the VDP) and pieces of at
    most 4x4 tiles for an indexed image; offsets from (ox, oy). skip_empty: no
    piece where the image is empty (scattered art: fewer tiles)."""
    h, w = img.shape
    th, tw = (h + 7) // 8, (w + 7) // 8
    pad = np.zeros((th * 8, tw * 8), np.uint8)
    pad[:h, :w] = img
    tiles, pieces = [], []
    for px in range(0, tw, 4):
        for py in range(0, th, 4):
            pw, ph = min(4, tw - px), min(4, th - py)
            x_, y_ = px, py
            if skip_empty:                               # the block trimmed to its tiles with art
                used = np.array([[pad[8 * (py + cy):8 * (py + cy) + 8, 8 * (px + cx):8 * (px + cx) + 8].any()
                                  for cx in range(pw)] for cy in range(ph)])
                if not used.any():
                    continue
                rs, cs = np.nonzero(used.any(1))[0], np.nonzero(used.any(0))[0]
                x_, y_ = px + int(cs[0]), py + int(rs[0])
                pw, ph = int(cs[-1] - cs[0]) + 1, int(rs[-1] - rs[0]) + 1
            px_, py_ = px, py
            px, py = x_, y_
            start = first_tile + len(tiles)
            for cx in range(pw):
                for cy in range(ph):
                    t = pad[8 * (py + cy):8 * (py + cy) + 8, 8 * (px + cx):8 * (px + cx) + 8]
                    tiles.append(bytes((int(t[r, 2 * k]) << 4) | int(t[r, 2 * k + 1]) for r in range(8) for k in range(4)))
            pieces.append(((pw - 1) << 10 | (ph - 1) << 8 | 0x50, 0x6000 | start,
                           8 * px - ox, 8 * py - oy))
            px, py = px_, py_
    return tiles, pieces


def frame_record(img, ox, oy, pieces, box=True):
    h, w = img.shape
    sb = lambda v: max(-128, min(127, v)) & 0xFF
    if box:
        rec = bytearray((1).to_bytes(2, 'big') + bytes((sb(-ox), sb(w - ox), sb(-oy), sb(h - oy))) + bytes(2))
    else:                               # (no hit box: it can't hit)
        rec = bytearray(bytes(4))
    for size, attr, x, y in pieces:
        rec += size.to_bytes(2, 'big') + attr.to_bytes(2, 'big') + bytes((sb(x), sb(y)))
    rec += b'\x80\x00'
    return bytes(rec)


def tight(img, ox, oy, first_tile):
    """As tiles_and_pieces, but pieces cover non-empty tiles only (rectangles of
    up to 4 x 4 grown right then down), on the 8 px grid offset that needs the
    fewest tiles."""
    h, w = img.shape
    best = None
    for dy in range(8):
        for dx in range(8):
            pad = np.zeros(((h + dy + 7) // 8 * 8, (w + dx + 7) // 8 * 8), np.uint8)
            pad[dy:dy + h, dx:dx + w] = img
            th, tw = pad.shape[0] // 8, pad.shape[1] // 8
            used = pad.reshape(th, 8, tw, 8).any(axis=(1, 3))
            if best is None or used.sum() < best[0]:
                best = (int(used.sum()), dx, dy, pad, used)
    _, dx, dy, pad, used = best
    left = used.copy()
    tiles, pieces = [], []
    for ty in range(used.shape[0]):
        for tx in range(used.shape[1]):
            if not left[ty, tx]:
                continue
            pw = 1
            while pw < 4 and tx + pw < used.shape[1] and left[ty, tx + pw]:
                pw += 1
            ph = 1
            while ph < 4 and ty + ph < used.shape[0] and left[ty + ph, tx:tx + pw].all():
                ph += 1
            left[ty:ty + ph, tx:tx + pw] = False
            start = first_tile + len(tiles)
            for cx in range(pw):
                for cy in range(ph):
                    t = pad[8 * (ty + cy):8 * (ty + cy) + 8, 8 * (tx + cx):8 * (tx + cx) + 8]
                    tiles.append(bytes((int(t[r, 2 * k]) << 4) | int(t[r, 2 * k + 1]) for r in range(8) for k in range(4)))
            pieces.append(((pw - 1) << 10 | (ph - 1) << 8 | 0x50, 0x6000 | start,
                           8 * tx - dx - ox, 8 * ty - dy - oy))
    return tiles, pieces


def emp_art(key, frames, remap, first_tile):
    """[(tiles, record)] for EMP.OBJ frames placed from his feet (anchor)."""
    import mkshang
    imgs = mkshang.frames(list(frames))
    out = []
    for f in frames:
        im, (ax, ay) = imgs[f]
        img = remap(np.asarray(im))
        t, p = tight(img, ax, ay, first_tile)
        first_tile += len(t)
        out.append((t, frame_record(img, ax, ay, p, box=f in BOXED.get(key, ()))))
    return out


def chunks(b):
    o, out = 0, []
    while o + 12 <= len(b):
        ln = int.from_bytes(b[o:o + 4], 'big')
        if ln == 0:
            break
        out.append((o, ln, int.from_bytes(b[o + 4:o + 6], 'big')))
        o += ln
    return out


def build(pl, key, mk_dir, remap=lambda a: a, extra=(), shrink=False, live_extra=None):
    """pl: the fighter's .PL (a copy of Blade's). Returns it with sheet SHEET
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
    for t, r in (emp_art(key, flight + impact, remap, 0) if action == 'emp' else ()):
        tiles += t
        recs.append(r)
    for pose in (() if action == 'emp' else flight + impact):
        img, ox, oy = cut(mk_dir, action, pose)
        img = remap(img)
        t, p = tiles_and_pieces(img, ox, oy, len(tiles))
        tiles += t
        recs.append(frame_record(img, ox, oy, p))
    if live_extra:
        live_tiles, live_record = live_extra(len(tiles))
        tiles += live_tiles
    recs += list(extra)                 # frames whose tiles are uploaded over these at need
    if live_extra:
        recs.append(live_record)        # static flight effect, after fatality frames
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
    if shrink:                          # the sheet chunk cut to what its records use (Blade's has room
        new_len = (22 + 2 * nfr + len(body) + 3) & ~3   # for 63 frames: ~2.8 KB of zeros); the chunks
        pl[sheet:sheet + 4] = new_len.to_bytes(4, 'big')   # after it are found by the chain, not by offset
        del pl[sheet + new_len:sheet + sheet_len]
    return bytes(pl), (len(flight), len(impact))


def preview(key):
    from PIL import Image
    if PROJ[key][0] == 'emp':                       # (Shang: his EMP.OBJ frames, his colours)
        import mkshang, mkshangmoves
        cram = mkshangmoves.cram()
        pal = np.array([((c & 7) * 36, ((c >> 3) & 7) * 36, ((c >> 6) & 7) * 36) for c in cram], np.uint8)
        pal[0] = (40, 40, 60)
        fr = mkshang.frames(PROJ[key][1] + PROJ[key][2])
        ims = [Image.fromarray(pal[np.asarray(fr[f][0])]) for f in PROJ[key][1] + PROJ[key][2]]
        return _sheet(ims, key)
    mk_dir = {'raiden': 'mk_moves_raiden', 'subzero': 'mk_moves_subzero', 'reptile': 'mk_moves_subzero', 'johnny': 'mk_moves_johnny',
              'liukang': 'mk_moves_liukang', 'kano': 'mk_moves_kano', 'sonya': 'mk_moves_sonya'}[key]
    action, flight, impact = PROJ[key]
    cram = json.load(open(os.path.join(ROOT, 'extracted', mk_dir, action, 'cram.json')))
    pal = np.array([((c & 7) * 36, ((c >> 3) & 7) * 36, ((c >> 6) & 7) * 36) for c in cram], np.uint8)
    pal[0] = (40, 40, 60)
    ims = [Image.fromarray(pal[cut(mk_dir, action, p)[0]]) for p in flight + impact]
    _sheet(ims, key)


def _sheet(ims, key):
    from PIL import Image
    w = sum(i.width + 8 for i in ims)
    out = Image.new('RGB', (w, max(i.height for i in ims)), (40, 40, 60))
    x = 0
    for i in ims:
        out.paste(i, (x, 0))
        x += i.width + 8
    out = out.resize((out.width * 3, out.height * 3), Image.NEAREST)
    path = os.path.join(ROOT, 'build', 'shots', f'projectile_{key}.png')
    out.save(path)
    print(path)


if __name__ == '__main__':
    for k in (sys.argv[1:] or list(PROJ)):
        preview(k)
