#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""MK captures as recipes (docs/research/reproducibility_2026-11.md).

Every captured pose is a 320x240 screen of one fighter's pixels; a recipe is the list of MK frames
drawn into it, in painting order: (source, frame number, mirrored, x, y) of each
frame's top-left corner, the source being the fight state and player that drew
it ('mk_2p:1'). The screen's edges clip; a later frame covers an earlier one.
Frames come from tools/lib/mkframes.py (MK draws frame N on demand).

    mkrecipes.py MK_DIR [ACTION ...] [--sources mk_2p:1,mk_subzero_2p:2]
        -> how many poses get an exact recipe (sources: SOURCES[MK_DIR] by default)
"""
import os, sys
import numpy as np
from scipy.signal import fftconvolve
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

H, W = 240, 320


def crop(p):
    ys, xs = np.nonzero(p)
    return p[ys.min():ys.max() + 1, xs.min():xs.max() + 1] if len(ys) else None


from mkmoves import TOP   # mkmoves.Session.frame keeps sprites at y > TOP (all of them now)


def draw(parts, frames):
    """The screen a recipe makes, by the capture's own rules: each frame's MK
    sprites at the frame's place (mirrored: flipped, positions mirrored), a
    sprite only if its y > TOP, clipped by the screen, later parts on top. A
    part is (src, f, mirrored, x, y) or (src, f, mirrored, x, y, bit mask of its sprites kept),
    ('line', y, x0, x1, colour): a one-pixel line of one colour (MK's spear rope), or
    ('cut', y, x0, x1): pixels cleared."""
    out = np.zeros((H, W), np.uint8)
    for part in parts:
        if part[0] == 'line':                               # ('line', y, x0, x1, colour): the spear's rope
            _, y, x0, x1, col = part
            out[y, x0:x1 + 1] = col
            continue
        if part[0] == 'cut':                                # ('cut', y, x0, x1): pixels cleared by hand
            _, y, x0, x1 = part
            out[y, x0:x1 + 1] = 0
            continue
        src, f, mir, x, y = part[:5]
        keep = part[5] if len(part) > 5 else None           # (only these sprites: a capture taken
        sp = frames[(src, f)]                               #  while MK rewrote its sprite list)
        # mirrored about the frame's drawn pixels (sprites are padded to 8-pixel blocks)
        fw = max(sx + int(np.nonzero(p.any(0))[0][-1]) + 1 for sx, sy, p in sp if p.any())
        for k, (sx, sy, p) in enumerate(sp):
            if keep is not None and not keep >> k & 1:
                continue
            if mir:
                sx, p = fw - sx - p.shape[1], p[:, ::-1]
            X, Y = x + sx, y + sy
            if Y <= TOP:
                continue
            ys, xs = np.nonzero(p)
            Ys, Xs = ys + Y, xs + X
            ok = (Ys >= 0) & (Ys < H) & (Xs >= 0) & (Xs < W)
            out[Ys[ok], Xs[ok]] = p[ys[ok], xs[ok]]
    return out


def placements(q, r, care=None, least=None):
    """(x, y, pixels compared) where r's pixels equal q's, best first. Only screen
    pixels count, and only where care is 1 (an upper frame hides the rest).
    Exact equality of colour indices via sums of squares == 0."""
    m = (r > 0).astype(np.float64)
    rf = r.astype(np.float64)
    ph, pw = r.shape
    Q = np.zeros((H + 2 * ph, W + 2 * pw))
    Q[ph:ph + H, pw:pw + W] = q
    on = np.zeros_like(Q)
    on[ph:ph + H, pw:pw + W] = 1 if care is None else care
    flip = lambda a: a[::-1, ::-1]
    s_qq = fftconvolve(Q * Q * on, flip(m), 'valid')
    s_qr = fftconvolve(Q * on, flip(m * rf), 'valid')
    s_rr = fftconvolve(on, flip(m * rf * rf), 'valid')
    seen = fftconvolve(on, flip(m), 'valid')
    ssd = s_qq - 2 * s_qr + s_rr
    ok = (np.abs(ssd) < 0.5) & (seen > (0.1 * m.sum() if least is None else least))
    ys, xs = np.nonzero(ok)
    out = [(int(x) - pw, int(y) - ph, int(round(seen[y, x]))) for y, x in zip(ys, xs)]
    return sorted(out, key=lambda t: -t[2])


def inside(q, r):
    """(x, y) where every pixel of q equals r's there (q is part of r), best first."""
    qm = (q > 0).astype(np.float64)
    qf = q.astype(np.float64)
    rf = r.astype(np.float64)
    ph, pw = r.shape
    flip = lambda a: a[::-1, ::-1]
    # over q's pixels: sum (q - R)^2, R = r placed at each offset (r is the kernel: correlate)
    s_qq = (qf * qf).sum()
    s_qr = fftconvolve(qf, flip(rf), 'full')
    s_rr = fftconvolve(qm, flip(rf * rf), 'full')
    ssd = s_qq - 2 * s_qr + s_rr
    ys, xs = np.nonzero(np.abs(ssd) < 0.5)
    # 'full' index (i, j): r's top-left at (i - (ph - 1), j - (pw - 1))
    return [(int(x) - (pw - 1), int(y) - (ph - 1)) for y, x in zip(ys, xs)]


def runs(rest, longest_gap=0):
    """rest as one-colour horizontal runs [('line', y, x0, x1, c)], or None if it isn't."""
    out = []
    for y in np.nonzero(rest.any(1))[0]:
        row = rest[y]
        xs = np.nonzero(row)[0]
        start = xs[0]
        for a, b in zip(xs, list(xs[1:]) + [None]):
            if b is None or b != a + 1 or row[b] != row[a]:
                if len(set(row[start:a + 1].tolist())) != 1:
                    return None
                out.append(('line', int(y), int(start), int(a), int(row[a])))
                start = b
    if not out or sum(x1 - x0 + 1 for _, _, x0, x1, _ in out) < 3 * len(out):
        return None                                         # (specks aren't a rope)
    return out


def runs_any(mask):
    """mask's horizontal runs [('run', y, x0, x1, 1)]."""
    out = []
    for y in np.nonzero(mask.any(1))[0]:
        xs = np.nonzero(mask[y])[0]
        start = xs[0]
        for a, b in zip(xs, list(xs[1:]) + [None]):
            if b is None or b != a + 1:
                out.append(('run', int(y), int(start), int(a), 1))
                start = b
    return out


def P(f, mir, x, y, keep=None):
    """A frame part: f is (source, frame number)."""
    return (f[0], f[1], mir, x, y) + (() if keep is None else (keep,))


def hist(a):
    return np.bincount(a[a > 0].ravel(), minlength=16)


class Library:
    """Frames of one or more sources ({(source, f): MK sprites}), with what's
    needed to find them fast. Below, f stands for (source, frame number)."""
    def __init__(self, frames, effects=(), lines=False, cuts=False):
        import mkframes
        self.frames = frames
        self.cuts = cuts                                    # (only hand-cleaned captures: CUTS)
        self.lines = lines                                  # (only where MK draws a rope: LINES)
        # frames another object draws over the fighter, some of their sprites at
        # a time (Raiden's electricity): matched sprite by sprite
        # (effects: frame numbers, or whole sources)
        self.effects = [(f, mir) for f in frames if f[1] in effects or f[0] in effects for mir in (0, 1)]
        seen = set()                                        # (one number per picture: the lowest)
        uniq = []
        for f in sorted((f for f in frames if ':' in f[0]), key=lambda f: (f[0], str(f[1]))):
            k = (f[0], mkframes.picture(frames[f]).tobytes())
            if k not in seen:
                seen.add(k)
                uniq.append(f)
        self.lib = [(f, mir, mkframes.picture(frames[f], mir)) for f in uniq for mir in (0, 1)]
        self.pieces = [(f, mir, mkframes.picture(sp, mir)) for f, sp in frames.items() for mir in (0, 1)
                       if ':' not in f[0] and (mir == 0 or sp[0][2].shape[1] > 0)]
        self.hists = {(f, mir): hist(r) for f, mir, r in self.lib + self.pieces}
        self.whole = {}
        for f, mir, r in self.ordered():
            self.whole.setdefault(r.tobytes(), (f, mir))

    def effect_parts(self, q, least=12):
        """Effect frames over the fighter: (f, mir, x, y, keep) for each place
        where some of an effect frame's sprites match q exactly (placed by
        sprites of at least LEAST pixels: smaller ones match anywhere)."""
        out = []
        for f, mir in self.effects:
            sp = self.frames[f]
            fw = max(sx + int(np.nonzero(p.any(0))[0][-1]) + 1 for sx, sy, p in sp if p.any())
            at = {}
            small = []
            for k, (sx, sy, p) in enumerate(sp):
                if mir:
                    sx, p = fw - sx - p.shape[1], p[:, ::-1]
                if not p.any():
                    continue
                if (p > 0).sum() < least:
                    small.append(k)
                    continue
                ys, xs = np.nonzero(p)
                r = p[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
                for x, y, _ in placements(q, r):
                    at.setdefault((x - sx - xs.min(), y - sy - ys.min()), []).append(k)
            for (x, y), ks in at.items():
                keep = 0
                for k in ks + small:
                    one = draw([P(f, mir, x, y, 1 << k)], self.frames)
                    if one.any() and (one[one > 0] == q[one > 0]).all():
                        keep |= 1 << k
                if keep:
                    out.append(P(f, mir, x, y, keep))
        return out

    def ordered(self, lib=None):
        """The library, the frames the last poses used and their neighbours
        first (a move's poses are mostly consecutive frames): only faster."""
        lib = self.lib if lib is None else lib
        hint = getattr(self, 'hint', ())
        near = {(src, n + d) for src, n in hint for d in (-2, -1, 1, 2, 3) if isinstance(n, int)}
        rank = lambda e: 0 if e[0] in hint else 1 if e[0] in near else 2
        return sorted(lib, key=rank)

    def recipe(self, q):
        """The parts that redraw q exactly, or None."""
        parts = self._recipe(q)
        if parts:
            self.hint = [(t[0], t[1]) for t in parts if t[0] not in ('line', 'cut')]
        return parts

    def _recipe(self, q):
        ys, xs = np.nonzero(q)
        if not len(ys):
            return []
        c = q[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        hit = self.whole.get(c.tobytes())
        if hit:                                            # a whole frame, on screen
            parts = [P(hit[0], hit[1], int(xs.min()), int(ys.min()))]
            if (draw(parts, self.frames) == q).all():
                return parts
        hq = hist(q)
        # one frame, cut (the screen's edge, the capture's top line): its visible part is q
        for f, mir, r in self.ordered():
            if (hq > self.hists[(f, mir)]).any():
                continue
            for x, y, _ in placements(q, r)[:4]:
                if (draw([P(f, mir, x, y)], self.frames) == q).all():
                    return [P(f, mir, x, y)]
        # part of one frame: some of its sprites missing from the capture
        for f, mir, r in self.ordered():
            if (hq > self.hists[(f, mir)]).any():
                continue
            for x, y in inside(q, r)[:4]:
                sp = self.frames[f]
                keep = 0
                for k in range(len(sp)):
                    one = draw([P(f, mir, x, y, 1 << k)], self.frames)
                    if one.any() and (q[one > 0] == one[one > 0]).all():
                        keep |= 1 << k
                parts = [P(f, mir, x, y, keep)]
                if keep and (draw(parts, self.frames) == q).all():
                    return parts
        # one frame with pixels cleared by hand (a cleaned capture): q is part of
        # it; the cleared pixels as runs - positions only
        for f, mir, r in (self.ordered() if self.cuts else ()):
            if (hq > self.hists[(f, mir)]).any():
                continue
            for x, y in inside(q, r)[:4]:
                d = draw([P(f, mir, x, y)], self.frames)
                gone = (d > 0) & (q == 0)
                if not gone.any() or gone.sum() > 0.4 * (d > 0).sum():
                    continue
                cut = [('cut', int(yy), int(a), int(b)) for _, yy, a, b, _ in runs_any(gone)]
                parts = [P(f, mir, x, y)] + cut
                if (draw(parts, self.frames) == q).all():
                    return parts
        # one frame and rope: the rest is one-colour horizontal lines (drawn over him)
        for f, mir, r in (self.ordered() if self.lines else ()):
            if (self.hists[(f, mir)] > hq).any():
                continue
            for x, y, _ in placements(q, r)[:3]:
                body = draw([P(f, mir, x, y)], self.frames)
                rest = np.where(body > 0, 0, q)
                lines = runs(rest)
                if lines is not None:
                    parts = [P(f, mir, x, y)] + lines
                    if (draw(parts, self.frames) == q).all():
                        return parts
        # two frames: the top one wholly visible (but for cuts)
        for f, mir, r in self.ordered():
            if (self.hists[(f, mir)] > hq).any():
                continue
            for x, y, _ in placements(q, r)[:3]:
                top = draw([P(f, mir, x, y)], self.frames)
                if (top[q > 0] > 0).all():
                    continue
                rest = np.where(top > 0, 0, q)
                hr = hist(rest)
                care = (top == 0).astype(np.float64)        # under the top frame: unseen
                for g, gm, s2 in self.ordered():
                    if (hr > self.hists[(g, gm)]).any():
                        continue
                    # (mostly hidden is fine: it must show all that's left, exactly)
                    for x2, y2, _ in placements(q, s2, care, least=0.9 * (rest > 0).sum())[:3]:
                        parts = [P(g, gm, x2, y2), P(f, mir, x, y)]
                        if (draw(parts, self.frames) == q).all():
                            return parts
        # a frame with pieces on top (each piece wholly visible): the pieces
        # first, where all their pixels match; then the frame under them
        if self.pieces or self.effects:
            top_parts = self.effect_parts(q)
            for f, mir, r in self.pieces:
                if (self.hists[(f, mir)] > hq).any() or (r > 0).sum() < 12:
                    continue
                for x, y, _ in placements(q, r):
                    one = draw([P(f, mir, x, y)], self.frames)
                    if (one[one > 0] == q[one > 0]).all() and one.any():
                        top_parts.append(P(f, mir, x, y))
            if top_parts:
                top = draw(top_parts, self.frames)
                care = (top == 0).astype(np.float64)
                rest = np.where(top > 0, 0, q)
                hr = hist(rest)
                for g, gm, s2 in self.ordered():
                    if (hr > self.hists[(g, gm)]).any():
                        continue
                    for x2, y2, _ in placements(q, s2, care)[:3]:
                        parts = [P(g, gm, x2, y2)] + top_parts
                        if (draw(parts, self.frames) == q).all():
                            for t in list(parts[1:]):        # only the pieces it needs
                                fewer = [u for u in parts if u is not t]
                                if (draw(fewer, self.frames) == q).all():
                                    parts = fewer
                            return parts
        # a frame, and effect bits apart from it (the loser's head leaving the
        # screen: a few pixels): what the frame leaves, matched sprite by sprite
        if self.effects:
            for f, mir, r in self.ordered():
                if (hq > self.hists[(f, mir)]).any() and (self.hists[(f, mir)] > hq).any():
                    continue
                for x, y, _ in placements(q, r)[:3]:
                    body = draw([P(f, mir, x, y)], self.frames)
                    rest = np.where(body > 0, 0, q)
                    if not rest.any() or (rest > 0).sum() > 400:
                        continue
                    bits = self.effect_parts(rest, least=1)
                    parts = [P(f, mir, x, y)] + bits
                    if bits and (draw(parts, self.frames) == q).all():
                        return parts
        return None


# where each fighter's captures were drawn: (fight state, player); both sides
# (some captures were taken from player 2's side, victims always)
SOURCES = {
    'mk_moves': ['mk_2p:1', 'mk_subzero_2p:2', 'mk_scorpion_sonya_2p:1'],
    'mk_moves_raiden': ['mk_raiden_2p:1', 'mk_subzero_raiden_2p:2'],
    'mk_moves_johnny': ['mk_johnny_2p:1', 'mk_subzero_johnny_2p:2', 'mk_johnny_sonya_2p:1'],
    'mk_moves_subzero': ['mk_2p:2', 'mk_subzero_kano_2p:1', 'mk_subzero_subzero_2p:2', 'szfatal'],
    'mk_moves_liukang': ['mk_liukang_2p:1', 'mk_subzero_liukang_2p:2'],
    'mk_moves_kano': ['mk_kano_2p:1', 'mk_subzero_kano_2p:2'],
    'mk_moves_sonya': ['mk_sonya_2p:1', 'mk_subzero_sonya_2p:2', 'mk_johnny_sonya_2p:2', 'mk_scorpion_sonya_2p:2'],
}


# frames drawn by another object over the fighter, some sprites at a time
EFFECTS = {
    'mk_moves_raiden': range(0xC7, 0xD9),                   # his electricity (PRG RAM $7D90E's lists; $C7-$CF his fatality's bolts)
}


# captures of someone other than the directory's fighter: the loser of his
# fatality is MK's player 2 (Sub-Zero: tools/capture/mkduelstate.py's player 2 cursor)
VICTIM = ['mk_2p:2']
CAPTURE_SOURCES = {
    ('mk_moves', 'fatality_victim'): VICTIM,
    **{(d, 'fatality_mk_victim'): VICTIM for d in ('mk_moves_johnny', 'mk_moves_kano', 'mk_moves_raiden',
                                                  'mk_moves_sonya', 'mk_moves_liukang')},
    # her kiss burns the loser down: BONES.OBJ's frames (his object's art then)
    ('mk_moves_sonya', 'fatality_mk_victim'): VICTIM + ['sonyafatal+57:1:1'],
    # Scorpion's fire: BONES.OBJ's frames, by the object after the players (line 0)
    ('mk_moves', 'fatality'): SOURCES['mk_moves'] + ['scfatal+5:2:0'],
    ('mk_moves', 'fatality_fire'): SOURCES['mk_moves'] + ['scfatal+5:2:0'],
}


# the loser's head knocked off (Johnny) or held up (Sub-Zero): his own frames
# $D1-$D8, drawn by another object (PRG RAM $7DA14)
HEAD = range(0xD1, 0xD9)
CAPTURE_EFFECTS = {**{(d, 'fatality_mk_victim'): HEAD for d in ('mk_moves_johnny', 'mk_moves_kano', 'mk_moves_raiden',
                                                               'mk_moves_sonya', 'mk_moves_liukang')},
                   ('mk_moves_kano', 'fatality_mk'): range(0xD1, 0xDB),   # the heart he holds up (his $D5-$DA)
                   ('mk_moves', 'fatality'): ['scfatal+5:2:0'],
                   ('mk_moves', 'fatality_fire'): ['scfatal+5:2:0']}
# MK's one drawn line: Scorpion's spear rope
LINES = {('mk_moves', 'spear')}
# captures cleaned by hand (pixels cleared; no tool did it): his teleport
CUTS = {('mk_moves', 'teleport_mk')}


def sources_for(mk_dir, act):
    return CAPTURE_SOURCES.get((mk_dir, act), SOURCES[mk_dir])


def effects_for(mk_dir, act):
    if (mk_dir, act) in CAPTURE_EFFECTS:
        return CAPTURE_EFFECTS[(mk_dir, act)]
    return EFFECTS.get(mk_dir, ()) if (mk_dir, act) not in CAPTURE_SOURCES else ()


# captures kept as colours (RGB), not palette indices: the palette (fight
# state:line) they were drawn with. Matched in canonical indices (each the
# lowest index of its colour: a palette can repeat a colour)
# (several: each pose its own, the first that has all its colours - Sub-Zero
# burning in Scorpion's fatality is in another palette from frame 236 on)
RGB = {('mk_moves_subzero', 'fatality_victim'): ['mk_subzero_2p:1'],
       ('mk_moves', 'fatality_victim'): ['mk_2p:1', 'scfatal@35:1']}
CAPTURE_SOURCES[('mk_moves_subzero', 'fatality_victim')] = ['mk_subzero_2p:2']      # (Scorpion, his loser)
CAPTURE_EFFECTS[('mk_moves_subzero', 'fatality_victim')] = HEAD
CAPTURE_SOURCES[('mk_moves', 'fatality_victim')] = VICTIM + ['scfatal+85:1:1']     # (Sub-Zero, burnt: BONES)
# captures made from others by a tool (prepare.py runs it after the rebuild):
# no recipes; the captures they're made from get every pose a recipe (FULL)
DERIVED = {('mk_moves_sonya', 'fatality_burn'): 'mkburn.py',
           ('mk_moves', 'fatality_skeleton'): 'mkfatality.py skeleton'}
# (the poses those tools use: all, or from a pose on - Scorpion's skeleton
# takes his loser's from mkfatality.FIRST_BURNT; before it: FINISH HIM's letters)
FULL = {('mk_moves_sonya', 'fatality_mk_victim'): 0, ('mk_moves', 'fatality_victim'): 10,
        ('mk_moves_subzero', 'fatality_victim'): 0}


def colours(cram):
    return np.array([((c & 7) * 36, ((c >> 3) & 7) * 36, ((c >> 6) & 7) * 36) for c in cram], np.uint8)


def canon(cram):
    """index -> the lowest index of the same colour (0 stays 0; black is 0 too:
    in an RGB capture black is the empty background)."""
    cols = colours(cram)
    out = np.arange(16, dtype=np.uint8)
    for i in range(1, 16):
        if not cols[i].any():
            out[i] = 0
            continue
        for j in range(1, i):
            if (cols[j] == cols[i]).all():
                out[i] = j
                break
    return out


def rgb_to_canon(rgb, cram):
    """rgb in canonical indices of cram, or None if a colour isn't in it."""
    cols, m = colours(cram), canon(cram)
    out = np.zeros(rgb.shape[:-1], np.uint8)
    for i in range(1, 16):
        if m[i] == i and cols[i].any():
            out[(rgb == cols[i]).all(-1) & rgb.any(-1)] = i
    return out if ((out > 0) == rgb.any(-1)).all() else None


def frames_of(sources, remap=None):
    """{(source, frame): sprites}; a source without ':' is a replay's pieces
    (mkframes.REPLAYS), its frames named by hash. remap: index -> index."""
    import mkframes
    out = {}
    for src in sources:
        got = mkframes.library(src) if ':' in src else mkframes.pieces(src)
        for f, sp in got.items():
            if remap is not None:                           # (from the top-left of what's left:
                sp, _ = mkframes.Frames.corner([(x, y, remap[p]) for x, y, p in sp])   # black is gone)
                if not sp:
                    continue
            out[(src, f)] = sp
    return out


def tojson(parts):
    return [[int(v) if isinstance(v, (int, np.integer)) else v for v in t] for t in parts]


def main():
    import argparse, glob, json, time
    from inputs import ROOT
    ap = argparse.ArgumentParser()
    ap.add_argument('mk_dir')
    ap.add_argument('actions', nargs='*')
    ap.add_argument('--sources', type=lambda v: v.split(','))
    ap.add_argument('--all', action='store_true', help='every pose, not only those the build reads')
    ap.add_argument('--out', action='store_true', help='write data/mk_recipes/MK_DIR/ACTION.json')
    ap.add_argument('--skip-done', action='store_true', help='with --out: leave captures that have their file')
    a = ap.parse_args()
    reads = json.load(open(os.path.join(ROOT, 'extracted', 'build_reads.json')))   # (tools/dev/buildreads.py)
    libs = {}

    def library(srcs, effects, lines, remap=None, cuts=False):
        k = (tuple(srcs), tuple(effects), lines, None if remap is None else remap.tobytes(), cuts)
        if k not in libs:
            libs[k] = Library(frames_of(srcs, remap), effects, lines, cuts)
        return libs[k]
    todo = a.actions or sorted({os.path.basename(os.path.dirname(d))
                                for d in glob.glob(os.path.join(ROOT, 'extracted', a.mk_dir, '*', 'indexed.npy'))} |
                               {act for d, act in RGB if d == a.mk_dir})
    tot = got = 0
    short = []
    for act in todo:
        if (a.mk_dir, act) in DERIVED:
            print(f'{act:18s} (made by tools/{DERIVED[(a.mk_dir, act)]})')
            continue
        rgb = RGB.get((a.mk_dir, act))
        key = f'extracted/{a.mk_dir}/{act}/' + ('rgb.npy' if rgb else 'indexed.npy')
        full = (a.mk_dir, act) in FULL
        first = FULL.get((a.mk_dir, act), 0)
        if not a.all and key not in reads and not full:
            print(f'{act:18s} (not read by the build)')
            continue
        done = os.path.join(ROOT, 'data', 'mk_recipes', a.mk_dir, act + '.json')
        if a.out and a.skip_done and os.path.exists(done):
            old = json.load(open(done))['poses']
            if all(old[i] is not None for i in (range(first, len(old)) if full else reads[key])):
                print(f'{act:18s} (done)')
                continue
        want = None if a.all else set(range(first, len(np.load(os.path.join(ROOT, key), mmap_mode='r')))) if full \
            else set(reads[key])
        srcs_used = a.sources or sources_for(a.mk_dir, act)
        eff, lines = effects_for(a.mk_dir, act), (a.mk_dir, act) in LINES
        pal_of = []
        if rgb:
            import mkcapmeta
            crams = [mkcapmeta.palette(src) for src in rgb]
            P_ = []
            for x in np.load(os.path.join(ROOT, key)):
                k = next(k for k, cr in enumerate(crams) if rgb_to_canon(x, cr) is not None)
                pal_of.append(k)
                P_.append(rgb_to_canon(x, crams[k]))
            libs_by_pal = [library(srcs_used, eff, lines, canon(cr)) for cr in crams]
        else:
            lib = library(srcs_used, eff, lines, cuts=(a.mk_dir, act) in CUTS)
            P_ = np.load(os.path.join(ROOT, key))
        t0 = time.time()
        n = m = 0
        srcs = {}
        poses = []
        for i, q in enumerate(P_):
            if want is not None and i not in want:
                poses.append(None)
                continue
            m += 1
            if rgb:
                lib = libs_by_pal[pal_of[i]]
            r = lib.recipe(q)
            poses.append(tojson(r) if r is not None else None)
            if r is not None:
                n += 1
                for part in r:
                    srcs[part[0]] = srcs.get(part[0], 0) + 1
            else:
                short.append(f'{act}[{i}]')
        tot += m
        got += n
        print(f'{act:18s} {n:3d}/{m:3d}  {srcs}  ({time.time() - t0:.0f}s)', flush=True)
        if a.out:
            d = os.path.join(ROOT, 'data', 'mk_recipes', a.mk_dir)
            os.makedirs(d, exist_ok=True)
            tmp = os.path.join(d, act + '.json.tmp')
            json.dump({'sources': srcs_used, 'effects': [e if isinstance(e, str) else int(e) for e in eff],
                       'lines': lines, **({'rgb': rgb, 'palette_of': pal_of} if rgb else {}), 'poses': poses}, open(tmp, 'w'), separators=(',', ':'))
            os.replace(tmp, os.path.join(d, act + '.json'))      # (a power cut can't leave half a file)
    print(f'{a.mk_dir}: {got}/{tot} poses have an exact recipe' + (f'; none for {" ".join(short)}' if short else ''))
    if short:
        sys.exit(1)


if __name__ == '__main__':
    main()
