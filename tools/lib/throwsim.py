#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""EC's throw, simulated: where the victim is after each step.

PLYR's step loop $19124, the victim's state $37 at $17EB8 (docs/notes/2026-11.md
"EC's throw step loop"). Checked against Kano throwing Larcen (measured from RAM): 56, 54,
49/16 up, 23/69, -3/72, -65 (at the ground), -105.

    throwsim.py [MODULE.CO] [victim id]   (default SNA.CO, 3 Larcen; the built disc)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import disc, patches
from inputs import ROOT
S16 = lambda b, o: int.from_bytes(b[o:o + 2], 'big', signed=True)
U16 = lambda b, o: int.from_bytes(b[o:o + 2], 'big')


def lists(co, victim_id, list_at=0x1B10):
    t, size, e = patches.throw_table(co)
    recs = [tuple(U16(co, t + e[victim_id - 2] + 10 * s + k) if k in (0, 6, 8) else S16(co, t + e[victim_id - 2] + 10 * s + k)
                  for k in (0, 2, 4, 6, 8)) for s in range(size // 10)]
    tl, o = [], list_at
    while U16(co, o) != 0xFFFF:
        tl.append((U16(co, o), U16(co, o + 2))); o += 4
    return recs, tl


def simulate(recs, tl, start_gap=0):
    """-> [(step, ahead, up, victim flips)] after each step (thrower at 0 facing right, victim ahead facing left)."""
    tx, vx, vy = 0, start_gap, 0
    vflags = 0x0800                         # victim $100: bit 11 facing left (dx's sign), bit 12 upside down
    out = []
    for k, (rec, (tframe, cw)) in enumerate(zip(recs, tl)):
        d5 = 0
        if cw & 0x8000:                     # sides swap: both turn, the victim mirrored across
            d5 = 2 * (vx - tx)
            old = vflags & 0x0800
            vflags ^= 0x0800
            if not old:
                d5 = -d5
        if cw & 0x4000 and not (rec[3] & 0x0800):
            d5 = -d5
        frame, dx, dy, flags, ticks = rec
        d1 = dx - d5
        vflags ^= flags
        vx += d1 if vflags & 0x0800 else -d1
        vy -= dy
        out.append((k, vx - tx, vy, '%04X' % frame, '%04X' % (vflags & 0x1800), ticks, '%04X' % cw))
    return out


def bottoms(read, names):
    """-> bottom(frame word, upside down): how far a frame's art reaches below its
    anchor (px, down positive) as EC draws it, from its sheet's piece list in
    whichever .PL holds that sheet (None: no pieces). EC turns a frame upside down
    about the anchor (measured: art at y..y2 is drawn at 1-y2..1-y), so an
    upside-down frame hangs below the place a record puts him."""
    import plsheet
    sheets = {}
    for n in sorted(names):
        if n.endswith('.PL'):
            pl = read(n)
            for sh in plsheet.all_sheets(pl):
                sheets.setdefault(sh['sid'], (pl, sh['sheet']))

    def bottom(frame, flipped):
        pl, at = sheets[frame >> 8]
        ps = plsheet.pieces(pl, at, frame & 0xFF)
        if not ps:
            return None
        return 1 - min(y for _, _, _, y in ps) if flipped else max(y + 8 * h for _, h, _, y in ps)
    return bottom


def solve(recs, tl, track, bottom=None):
    """The records rebuilt to follow track [((ahead, up), ticks)] per step: each
    step's dy from the heights, its dx solved through simulate (a step's place is
    linear in its dx); frames and flags kept. With bottom (bottoms()), up is the
    height of the art's lowest pixel, as MK's was measured (the sprite box), not
    the anchor's: each step's frame (upside down or not) raised by how far it
    reaches below the anchor, beyond his first step's (on the ground). The
    landing step's anchor is kept off the ground's underside."""
    new = [list(r) for r in recs]
    flips = [int(row[4], 16) & 0x1000 for row in simulate(recs, tl)]
    lows = [bottom(r[0], f) if bottom else None for r, f in zip(recs, flips)]
    foot = lows[0]
    prev_up = 0
    for k, ((ahead, up), ticks) in enumerate(track):
        if foot is not None and lows[k] is not None:
            up = max(0, up + lows[k] - foot)
        new[k][2] = -(up - prev_up)
        new[k][4] = ticks

        def at(dx):
            new[k][1] = dx
            return simulate(new[:k + 1], tl)[k][1]
        a0, a1 = at(0), at(100)
        new[k][1] = round((ahead - a0) * 100 / (a1 - a0))
        assert simulate(new[:k + 1], tl)[k][1] == ahead
        prev_up = up
    return [tuple(r) for r in new]


if __name__ == '__main__':
    d = disc.Disc(os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    co = d.read_file(sys.argv[1] if len(sys.argv) > 1 else 'SNA.CO')
    recs, tl = lists(co, int(sys.argv[2]) if len(sys.argv) > 2 else 3)
    print('thrower list:', ['%04X/%04X' % x for x in tl])
    for row in simulate(recs, tl, 0): print(row)
