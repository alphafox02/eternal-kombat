#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Scorpion's spear as MK throws it: a rope of its own that flies across the screen.

MK CD (measured: a Scorpion vs Sonya duel, the spear thrown from 131 to 233 px apart) draws the
spear apart from Scorpion: a wavy rope - one 32 px wave repeated, ~240 px of it - with the head in
front, sliding forward ~7.5 px a frame from ~89 px in front of him, through him and on, until it
hits (from any distance on the screen) or flies off it; on a hit the rope is a straight line from
behind him to the victim (24 px pieces, shaking 4 px up and down) while he holds it and pulls.

Ours: the same as an object (mkinputs.emit_spear_rope) with a raw sprite sheet of its own in his
.PL (patches 'scorpion-rope'): the rope's art cut from MK's capture of the throw
(extracted/mk_moves/spear: the wave behind him in pose 11, its head in front, the straight rope of
pose 16), at MK's size (thin lines don't scale), placed at his poses' scale (scorpion_full.SCALE).
His spear poses lose their rope (strip_rope). Frames:
  FLY + 2 k (+ 1)  the flying rope: the head, its tip at +127 from the object, and k waves back towards
                   his hand (the waves flipped in the second: MK's wiggle); the hit box at the head
  STRAIGHT + n     the straight rope, n + 1 pieces from -128 (n = 0 .. STRAIGHT_MAX - 1); no box
  EMPTY            nothing
EC's raw draw gives each piece tiles of its own in the object's VRAM block (SUB $FD20), copied
from the source every time the frame changes: the block holds the biggest frame (max_tiles).

    mkspear.py      -> build/shots/mkspear.png: the frames (a preview)
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from inputs import ROOT

ACTION = os.path.join('mk_moves', 'spear')
WAVE_POSE, STRAIGHT_POSE = 11, 16
WAVE_COLS = (7, 39)                # pose 11: one wave, crossing to crossing (behind him: no body there)
WAVE_ROWS = (-83, -67)             # rows from his feet: the wave (peak -84, trough -67) in 2 tiles (EC's raw draw
                                   #  gives every piece tiles of its own: a pixel off the peak and the trough)
HEAD_W = 32                        # the head piece: the 32 px up to the tip (pose 11) ...
HEAD_ROWS = (-81, -73)             # ... these rows (its shaft at -79..-77, meeting the wave's crossing)
STRAIGHT_COLS = (60, 84)           # pose 16: 24 px of the straight rope, from the anchor
STRAIGHT_ROWS = (-88, -80)
STRAIGHT_MAX = 10                  # pieces: -128 .. +112
TIP = 127                          # the head's tip, from the object (a piece's x is a signed byte)
UNITS = 6                          # waves behind the head at most (from his hand: the rope he has out)
FLY = 0                            # frames FLY + 2 k + wiggle: the head and k waves
STRAIGHT = 2 * (UNITS + 1)         # frames STRAIGHT + n: n + 1 pieces of the straight rope
EMPTY = STRAIGHT + STRAIGHT_MAX    # nothing (no VRAM block: nothing to draw into)
HAND = 55                          # the rope's waves reach back to his hand: k = (its x from him + HAND) / 32
BOX_Y = (-10, -3)                  # the hit box's top and bottom from the rope's line: a crouching EC fighter's
                                   #  head is ~70 px up (Shadow), the line ~74: MK's spear goes over him
SPEED = 15                         # px per run of its task (every other frame): MK's ~7.5 a frame
START = 89                         # px in front of him where MK's head first shows
ATTR = 0x6000                      # a piece's attribute bits (as the fighters' projectile art, mkprojectile:
                                   #  EC's draw turns them into his palette line)
HAND_BACK = 40                     # the straight rope starts this far behind him (MK: through him)


def _load():
    d = os.path.join(ROOT, 'extracted', ACTION)
    return (np.load(os.path.join(d, 'indexed.npy')), json.load(open(os.path.join(d, 'anchors.json'))),
            json.load(open(os.path.join(d, 'cram.json'))))


def _ec_y(row):
    """A row from MK's feet line -> y from our object (at his feet line: his poses' scale, FOOT_DROP)."""
    import scorpion_full as sf
    return int(round(row * sf.SCALE)) + sf.FOOT_DROP


def _tiles(img):
    """An image (8h x 8w) -> its tiles, column by column (as EC draws a piece)."""
    h, w = img.shape[0] // 8, img.shape[1] // 8
    return [img[8 * r:8 * r + 8, 8 * c:8 * c + 8].copy() for c in range(w) for r in range(h)]


def art(remap=lambda a: a):
    """-> (tiles, frames): tiles 8 x 8 colour indices (his palette: remap), frames
    [(pieces [(w, h, first tile | flags, x, y)], box or None)]."""
    P, A, _ = _load()
    ax, ay = A[WAVE_POSE]
    m = P[WAVE_POSE]
    wave = remap(m[ay + WAVE_ROWS[0]:ay + WAVE_ROWS[1], WAVE_COLS[0]:WAVE_COLS[1]])   # (the pieces only: his own
    cols = np.nonzero(m[:, ax + 45:].any(0))[0]                                     #  colours aren't the rope's)
    tip = ax + 45 + int(cols.max())
    head = remap(m[ay + HEAD_ROWS[0]:ay + HEAD_ROWS[1], tip - HEAD_W + 1:tip + 1].copy())
    sx, sy = A[STRAIGHT_POSE]
    straight = remap(P[STRAIGHT_POSE][sy + STRAIGHT_ROWS[0]:sy + STRAIGHT_ROWS[1],
                                      sx + STRAIGHT_COLS[0]:sx + STRAIGHT_COLS[1]])
    assert wave.any() and head.any() and straight.any()
    tiles = _tiles(wave) + _tiles(head) + _tiles(straight)
    t_wave, t_head, t_str = 0, 8, 12
    y = _ec_y(WAVE_ROWS[0])
    yh = y + HEAD_ROWS[0] - WAVE_ROWS[0]                 # (as MK's: the head 2 rows under the wave's top)
    line = y + (WAVE_ROWS[1] - WAVE_ROWS[0]) // 2
    # (x1 x2 y1 y2): the head and the rope behind it, back to 1 px in front of him as it's thrown (from
    # up close - a cornered victim - the head starts past the victim)
    box = (TIP - (START - 1), TIP, line + BOX_Y[0], line + BOX_Y[1])
    frames = []
    for k in range(UNITS + 1):
        for flip in (0, 0x1000):
            pieces = [(4, 1, t_head, TIP - HEAD_W + 1, yh)]
            for i in range(k):
                pieces.append((4, 2, t_wave | flip, TIP - HEAD_W + 1 - 32 * (i + 1), y))
            frames.append((pieces, box))
    ys = _ec_y(STRAIGHT_ROWS[0])
    for n in range(STRAIGHT_MAX):
        frames.append(([(3, 1, t_str, -128 + 24 * k, ys) for k in range(n + 1)], None))
    frames.append(([], None))
    assert len(frames) == EMPTY + 1
    return tiles, frames


def max_tiles():
    """The most VRAM tiles a frame takes (its pieces' tiles, each piece its own)."""
    return max(sum(w * h for w, h, *_ in p) for p, _ in art()[1])


def chunks(sid, slot, remap=lambda a: a):
    """Two chunk makers (ecstage.raw_sheet's form, with the head's hit box): a raw tile source
    (slot) and the sheet (sid). -> (makers {kind: f(at)}, tile count)."""
    import ecstage
    tiles, frames = art(remap)
    makers = ecstage.raw_sheet(sid, slot, tiles, [p for p, _ in frames])
    recs = []
    for pieces, box in frames:
        r = bytearray()
        if box:
            r += (1).to_bytes(2, 'big') + bytes(v & 0xFF for v in box)
        else:
            r += (0).to_bytes(2, 'big')
        r += bytes(2)                                   # no points
        for w, h, t, x, yy in pieces:
            r += (((w - 1) << 10) | ((h - 1) << 8) | 0x50).to_bytes(2, 'big') + (ATTR | t).to_bytes(2, 'big') \
                + bytes([x & 0xFF, yy & 0xFF])
        r += (0x8000).to_bytes(2, 'big')
        recs.append(bytes(r))

    def sheet_chunk(at):
        table = bytearray((len(tiles) * 32 - 1).to_bytes(2, 'big') + bytes(2) + len(recs).to_bytes(2, 'big'))
        off, body = 2 * len(recs), b''
        for r in recs:
            table += off.to_bytes(2, 'big')
            off += len(r)
            body += r
        c = bytes(table) + body
        if len(c) & 1:
            c += b'\0'
        return (0x10 + len(c)).to_bytes(4, 'big') + (4).to_bytes(2, 'big') + bytes(4) + (sid * 4).to_bytes(2, 'big') \
            + (slot * 2).to_bytes(2, 'big') + bytes(2) + c
    makers[('sheet', sid)] = sheet_chunk
    return makers, len(tiles)


def strip_rope(pose, anchor):
    """His spear pose without MK's rope and spear head (the object draws them): what is thinner
    than 4 px both ways goes (the rope, the shaft), and what is left that isn't joined to his body
    (the head out in front)."""
    from scipy import ndimage
    mask = pose > 0
    if not mask.any():
        return pose
    body = ndimage.binary_opening(mask, np.ones((4, 4), bool))
    lab, n = ndimage.label(body)
    if n == 0:
        return pose
    ax, ay = anchor
    sizes = ndimage.sum(body, lab, range(1, n + 1))
    keep = np.zeros_like(body)
    big = int(np.argmax(sizes)) + 1
    for i in range(1, n + 1):
        ys, xs = np.nonzero(lab == i)
        if i == big or (sizes[i - 1] >= 12 and abs(xs.mean() - ax) < 48):
            keep |= lab == i
    near = ndimage.binary_dilation(keep, np.ones((5, 5), bool))
    return np.where(mask & near, pose, 0).astype(pose.dtype)


def preview():
    from PIL import Image
    tiles, frames = art()
    _, _, cram = _load()
    pal = np.array([[(c & 7) * 36, ((c >> 3) & 7) * 36, ((c >> 6) & 7) * 36] for c in cram], np.uint8)
    rows = []
    for pieces, box in frames:
        img = np.zeros((48, 320), np.uint8)
        for w, h, t, x, y in pieces:
            k = t & 0x7FF
            for c in range(w):
                for r in range(h):
                    tile = tiles[k + c * h + r]
                    if t & 0x1000:
                        tile = tiles[k + c * h + (h - 1 - r)][::-1]
                    yy, xx = y + 100 + 8 * r - 40, x + 160 + 8 * c
                    sub = img[yy:yy + 8, xx:xx + 8]
                    sub[tile > 0] = tile[tile > 0]
        rgb = pal[img]
        rgb[img == 0] = (30, 30, 60)
        rows.append(rgb)
    out = np.concatenate(rows, 0)
    Image.fromarray(out).resize((out.shape[1] * 3, out.shape[0] * 3), Image.NEAREST).save(
        os.path.join(ROOT, 'build', 'shots', 'mkspear.png'))


if __name__ == '__main__':
    preview()
