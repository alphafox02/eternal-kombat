# SPDX-License-Identifier: MIT
"""Write Eternal Champions CD fighter sprite data (.PL) and frame records.

Pieces: a pose is a list of hardware sprites. On the compressed path the
game unpacks one block of tiles per pose and hands tiles to pieces in order
(the tile numbers stored in pieces are ignored), so a pose is fully described
by: pieces (w, h, x, y in tiles/pixels, relative to the fighter's feet) and
the concatenated tiles (column-major within each piece, as the VDP wants).

Compression, as measured from SUB.BIN $11784 (see docs/notes/2026-11.md):
    $00-$1D  n+1 zero words              (1..30)
    $1E-$49  n-$1D dictionary words, each a following index byte (1..44)
    $4A-$53  n-$49 literal words from the literal stream (1..10)
    $F8      yield (resumed next video frame: encode_bank)
    $FF      end of frame
A bank is: 256-word dictionary, then literal and opcode streams. A frame
record (6 bytes) is: bank#, dict2 offset/2 (unused here), literal stream
offset, opcode stream offset (both relative to the bank).
"""
from collections import Counter
import numpy as np

TILE = 32


def tiles_of(img, tx, ty, w, h):
    """Column-major list of 32-byte 4bpp tiles from an indexed image region."""
    out = []
    for cx in range(w):
        for cy in range(h):
            blk = img[(ty + cy) * 8:(ty + cy) * 8 + 8, (tx + cx) * 8:(tx + cx) * 8 + 8]
            b = bytearray(32)
            for r in range(8):
                for c in range(0, 8, 2):
                    b[r * 4 + c // 2] = (int(blk[r, c]) << 4) | int(blk[r, c + 1])
            out.append(bytes(b))
    return out


def pose_from_image(img, origin_x, origin_y, cell=4):
    """Cut an indexed image (0 = transparent) into <=4x4-tile pieces.

    origin_x/origin_y: pixel in img that becomes the fighter's (0, 0)
    (horizontal centre, feet). Returns (pieces, tiles) where pieces are
    dicts w, h, x, y and tiles is the concatenated tile list. The 4x4 grid
    is tried at every tile offset; the cut with the fewest pieces (then
    tiles) wins, since a frame record only has room for so many pieces.
    """
    best = None
    for sy in range(cell):
        for sx in range(cell):
            r = _cut(img, origin_x, origin_y, cell, sx, sy)
            if r and (best is None or (len(r[0]), len(r[1])) < (len(best[0]), len(best[1]))):
                best = r
    if best is None:
        raise ValueError('piece out of signed-byte range')
    if len(best[1]) > 150:
        raise ValueError(f'{len(best[1])} tiles in one pose; the game allows at most 150')
    return best


def _cut(img, origin_x, origin_y, cell, sx, sy):
    H, W = img.shape
    # shift the image right/down by whole tiles so the grid starts sx/sy tiles earlier
    th, tw = (H + 7) // 8 + sy, (W + 7) // 8 + sx
    pad = np.zeros((th * 8, tw * 8), np.uint8)
    pad[sy * 8:sy * 8 + H, sx * 8:sx * 8 + W] = img
    ox, oy = origin_x + sx * 8, origin_y + sy * 8
    used = np.array([[pad[y * 8:y * 8 + 8, x * 8:x * 8 + 8].any() for x in range(tw)] for y in range(th)])
    pieces, tiles = [], []
    for gy in range(0, th, cell):
        for gx in range(0, tw, cell):
            sub = used[gy:gy + cell, gx:gx + cell]
            if not sub.any():
                continue
            ys, xs = np.nonzero(sub)
            x0, x1, y0, y1 = gx + xs.min(), gx + xs.max(), gy + ys.min(), gy + ys.max()
            w, h = x1 - x0 + 1, y1 - y0 + 1
            px, py = x0 * 8 - ox, y0 * 8 - oy
            if not (-128 <= px <= 127 and -128 <= py <= 127):
                return None
            pieces.append(dict(w=int(w), h=int(h), x=int(px), y=int(py)))
            tiles += tiles_of(pad, x0, y0, w, h)
    return pieces, tiles


def words(tiles):
    b = b''.join(tiles)
    return [int.from_bytes(b[i:i + 2], 'big') for i in range(0, len(b), 2)]


def encode_bank(frames):
    """frames: list of word lists. Returns (bank_bytes, [(lit_off, ops_off)])."""
    freq = Counter(w for f in frames for w in f if w)
    dict_words = [w for w, _ in freq.most_common(256)]
    index = {w: i for i, w in enumerate(dict_words)}
    dict_bytes = b''.join(w.to_bytes(2, 'big') for w in dict_words).ljust(512, b'\0')
    lits, opss = [], []
    for f in frames:
        lit, ops, i = bytearray(), bytearray(), 0
        # $F8 = yield: the unpacker saves its state and returns, and the game
        # resumes it next video frame. Sega's frames all unpack in two slices
        # (<= 77 tiles each); a frame unpacked in one go overruns the sub
        # CPU's frame budget and deadlocks the game. Yield at the halfway
        # point, and again whenever a slice would pass 64 tiles.
        half = (len(f) // 2) // 16 * 16          # yields must fall on a tile boundary
        slice_words = 64 * 16
        last_yield = 0
        yielded_half = False
        while i < len(f):
            if (not yielded_half and i >= half) or i - last_yield >= slice_words:
                ops.append(0xF8)
                last_yield = i
                yielded_half = yielded_half or i >= half
            stop = min(len(f), half if not yielded_half else len(f), last_yield + slice_words)
            stop = max(stop, i + 1)
            if f[i] == 0:
                n = 1
                while i + n < stop and f[i + n] == 0 and n < 30:
                    n += 1
                ops.append(n - 1)
            elif f[i] in index:
                n = 1
                while i + n < stop and f[i + n] and f[i + n] in index and n < 44:
                    n += 1
                ops.append(0x1D + n)
                ops += bytes(index[w] for w in f[i:i + n])
            else:
                n = 1
                while i + n < stop and f[i + n] and f[i + n] not in index and n < 10:
                    n += 1
                ops.append(0x49 + n)
                for w in f[i:i + n]:
                    lit += w.to_bytes(2, 'big')
            i += n
        ops.append(0xFF)
        lits.append(bytes(lit))
        opss.append(bytes(ops))
    bank = bytearray(dict_bytes)
    offs = []
    for lit, ops in zip(lits, opss):
        lo = len(bank)
        bank += lit
        if len(bank) % 2:
            bank.append(0)
        oo = len(bank)
        bank += ops
        if len(bank) % 2:
            bank.append(0)
        offs.append((lo, oo))
    return bytes(bank), offs


def piece_record(pieces, flags=0x0050, attr=0x6000):
    """Serialise pieces as the frame record's piece list (without terminator)."""
    out = bytearray()
    for p in pieces:
        d6 = (((p['w'] - 1) << 2 | (p['h'] - 1)) << 8) | flags
        out += d6.to_bytes(2, 'big') + attr.to_bytes(2, 'big')
        out += (p['x'] & 0xFF).to_bytes(1, 'big') + (p['y'] & 0xFF).to_bytes(1, 'big')
    return bytes(out)


def genesis_colour(raw):
    """Genesis Plus GX internal CRAM (BBBGGGRRR) -> VDP colour word."""
    r, g, b = raw & 7, (raw >> 3) & 7, (raw >> 6) & 7
    return (b << 9) | (g << 5) | (r << 1)
