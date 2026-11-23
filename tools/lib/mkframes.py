#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Draw any MK fighter frame by number (docs/research/reproducibility_2026-11.md).

MK's animations are lists of frame numbers in the fighter's .OBJ (loaded in
PRG RAM; Scorpion's idle is OBJ+$F000: $12-$17, $FFFF). From a fight state
where player 1 stands idle, his idle list (found by watching his animation
pointer, PRG RAM $7D702; player 2's $7D808) is overwritten with frame N: MK
draws exactly frame N, whatever the timing. The picture is player 1's palette-line-0 pixels, as
tools/lib/mkmoves.py captures them, cropped to the frame.

    mkframes.py STATE [--last 0xFF]      -> how many distinct frames it draws
    mkframes.py --recipes [--jobs N]     -> every library the recipes use (extracted/mk_frames/)
    mkframes.py --verify                 -> the decoder (tools/lib/mksch.py) against MK's own drawing
"""
import argparse, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mkmoves
from inputs import ROOT

ANIM = {1: 0x7D702, 2: 0x7D808}   # PRG RAM: each player's animation pointer (into his .OBJ's lists; $106 apart)
PAL = {1: 0, 2: 1}                # each player's palette line (as tools/lib/mkmoves.py / mkvictim.py capture them)
SLOT = 0x106                      # PRG RAM: MK's object blocks, from $7D702 (player 1, player 2, effects ...)
MOMENTS = (0, 3, 7, 12, 18)       # (frames after SETTLE: when other objects of his art can't be off)
LATER = 13                        # (frames: the second moment frames are drawn from, to tell real ones)
SETTLE = 40                # frames for MK to step into the list and draw


def crop(p):
    ys, xs = np.nonzero(p)
    return p[ys.min():ys.max() + 1, xs.min():xs.max() + 1] if len(ys) else None


class Frames:
    def __init__(self, state, player=1, replay=None, at=0, slot=None, pal=None):
        """Player PLAYER's frames from a fight STATE where he stands idle; or,
        with REPLAY (mkframes.REPLAYS), from AT frames into it, object SLOT
        (0 player 1, 1 player 2, 2.. effects) whose sprites are on palette line
        PAL (a fatality's art: BONES.OBJ's burning, ...)."""
        self.player = player
        self.pal = PAL[player] if pal is None else pal
        self.s = mkmoves.Session()
        c = self.c = self.s.core
        self.reset = None
        self.replay = bool(replay)
        self.zero = None                                    # (others off: decided on the first draw)
        if replay:
            replay_to(c, replay, at)
            self.base = bytes(c.snapshot())
            r = c.prg_ram()
            own = 0x7D702 + SLOT * slot
            p = int.from_bytes(r[own:own + 4], 'big') & 0xFFFFFF
            self.list_at, self.list_words = p - 8, 48      # (his list from there, and his pointer to it)
            self.reset = own
            self.others = self.same_art(r, own)
            return
        c.load_state(os.path.join(ROOT, 'build', 'states', state) if not os.path.isabs(state) else state, check=False)
        c.run(2)
        self.base = bytes(c.snapshot())
        L = lambda r: int.from_bytes(r[ANIM[player]:ANIM[player] + 4], 'big') & 0xFFFFFF
        seen = []
        for _ in range(90):                                 # his idle list: where the pointer goes
            c.run(1)
            seen.append(L(c.prg_ram()))
        r = c.prg_ram()
        seen = [v for v in seen if v < 0x70000]             # (player 2's starts in a work area)
        start = min(seen) - 2                               # (the pointer is past the entry it read)
        end = start
        while int.from_bytes(r[end:end + 2], 'big') != 0xFFFF and end < start + 64:
            end += 2
        assert start < end < start + 64 and max(seen) <= end, (hex(start), hex(end), [hex(v) for v in seen[:8]])
        self.list_at, self.list_words = start, (end - start) // 2
        self.reset = ANIM[player]                            # (each draw: from the list's start)
        # other objects drawing from his art (Raiden's electricity): off while
        # drawing his frames, so a frame is only his
        self.others = self.same_art(r, ANIM[player])

    @staticmethod
    def same_art(r, own):
        art = int.from_bytes(r[own + 0x3A:own + 0x3E], 'big')
        return [a for a in (0x7D702 + SLOT * k for k in range(8)) if a != own
                and int.from_bytes(r[a:a + 4], 'big') and int.from_bytes(r[a + 0x3A:a + 0x3E], 'big') == art]

    def sprites(self, f):
        """Frame f as MK's hardware sprites: [(x, y, pixels)] in drawing order (as
        mkmoves.Session.frame paints them: the first listed ends on top), from
        the frame's top-left corner; with that corner's screen (x, y)."""
        return self.corner(self.drawn(f))

    @staticmethod
    def corner(sp):
        sp = [(x, y, p) for x, y, p in sp if p.any()]
        if not sp:
            return None, None
        x0 = min(x + int(np.nonzero(p.any(0))[0][0]) for x, y, p in sp)
        y0 = min(y + int(np.nonzero(p.any(1))[0][0]) for x, y, p in sp)
        return [(x - x0, y - y0, p) for x, y, p in sp], (x0, y0)

    def drawn(self, f):
        """The screen's sprites on his palette line with frame f: [(x, y, pixels)].
        Other objects drawing from his art (Raiden's electricity) are off; where
        MK won't have that (Raiden as player 2) they're left on, and the screen is
        taken at several moments: what stays is his (they flicker, he doesn't)."""
        if self.zero is None:                               # (can they be off here? his frames must
            self.zero = bool(self.others)                   #  still change: as player 2 they don't)
            if self.zero:
                a = int.from_bytes(self.c.prg_ram()[self.list_at:self.list_at + 2], 'big') or 0x11
                try:
                    pa, pb = (self.shot(g, 0) for g in (a, a + 1))
                    self.zero = [p.tobytes() for _, _, p in pa] != [p.tobytes() for _, _, p in pb]
                except AssertionError:
                    self.zero = False
        shots = [self.shot(f, k) for k in ((0,) if self.zero or not self.others else MOMENTS)]
        key = lambda t: (t[0], t[1], t[2].shape, t[2].tobytes())
        keep = set.intersection(*(set(map(key, sp)) for sp in shots))
        return [t for t in shots[0] if key(t) in keep]

    def shot(self, f, later):
        c = self.c
        c.restore(self.base)
        if self.zero:
            for a in self.others:
                c.poke_prg(a, bytes(SLOT))
        c.poke_prg(self.list_at, f.to_bytes(2, 'big') * self.list_words)
        c.poke_prg(self.reset, self.list_at.to_bytes(4, 'big'))
        c.run(SETTLE + later)
        r = c.prg_ram()
        at = int.from_bytes(r[self.reset:self.reset + 4], 'big') & 0xFFFFFF
        assert self.list_at < at <= self.list_at + 2 * self.list_words and \
            int.from_bytes(r[at - 2:at], 'big') == f, f'frame {f:#x}: MK is not playing the poked list'
        v = self.s.vdp()
        return [(s['x'], s['y'], v.sprite_pixels(s)) for s in reversed(v.sprites()) if s['pal'] == self.pal]

    def all(self, last):
        """{frame: its sprites} for frames 1..last. From a replay, the sprites
        every frame's screen shares are someone else's (Scorpion's own, by his
        fire) and are left out."""
        got = {f: self.drawn(f) for f in range(1, last + 1)}         # (0 is a command in MK's lists)
        if not self.replay:
            # a number that's no frame of his leaves up what was showing: it
            # depends on the state's moment. Drawn again from a moment later,
            # only real frames look the same (else a fresh state differs)
            base = self.base
            self.c.restore(base)
            self.c.run(LATER)
            self.base = bytes(self.c.snapshot())
            pic = lambda sp: picture(self.corner(sp)[0]).tobytes() if any(p.any() for _, _, p in sp) else b''
            got = {f: sp for f, sp in got.items() if pic(sp) == pic(self.drawn(f))}
            self.base = base
        if self.replay:
            key = lambda t: (t[0], t[1], t[2].shape, t[2].tobytes())
            screens = {tuple(sorted(map(key, sp))): sp for sp in got.values()}
            assert len(screens) >= 3, 'the object ignores its frame number here'
            common = set.intersection(*(set(k) for k in screens))
            got = {f: [t for t in sp if key(t) not in common] for f, sp in got.items()}
        out = {}
        for f, sp in got.items():
            sp, _ = self.corner(sp)
            if sp:
                out[f] = sp
        return out


CACHE = os.path.join(ROOT, 'extracted', 'mk_frames')       # (drawn from your disc: never committed)


# Which art each source draws from: the fighter's .OBJ/.SCH on the MK disc
# (tools/lib/mksch.py decodes them), mirrored for a player facing left. Found by
# matching the frames MK drew in each fight state (emulator: drawn() above) -
# every real frame identical, sprites in the same order (2026-11-14).
ART = {
    'mk_2p:1': ('SCORPION', 0), 'mk_2p:2': ('XUBZERO', 1),
    'mk_johnny_2p:1': ('VANDAN', 0), 'mk_johnny_sonya_2p:1': ('VANDAN', 0), 'mk_johnny_sonya_2p:2': ('XIZ', 1),
    'mk_kano_2p:1': ('XANO', 0), 'mk_liukang_2p:1': ('KANG', 0), 'mk_raiden_2p:1': ('RAIDEN', 0),
    'mk_scorpion_sonya_2p:1': ('SCORPION', 0), 'mk_scorpion_sonya_2p:2': ('XIZ', 1),
    'mk_sonya_2p:1': ('XIZ', 0), 'mk_subzero_2p:2': ('SCORPION', 1), 'mk_subzero_johnny_2p:2': ('VANDAN', 1),
    'mk_subzero_kano_2p:1': ('XUBZERO', 0), 'mk_subzero_kano_2p:2': ('XANO', 1),
    'mk_subzero_liukang_2p:2': ('KANG', 1), 'mk_subzero_raiden_2p:2': ('RAIDEN', 1),
    'mk_subzero_sonya_2p:2': ('XIZ', 1), 'mk_subzero_subzero_2p:2': ('XUBZERO', 1),
    'scfatal+5:2:0': ('BONES', 0), 'scfatal+85:1:1': ('BONES', 0), 'sonyafatal+57:1:1': ('BONES', 0),
}
FIRST = 0x10                      # MK's animation frame number of the .OBJ's frame 0


def decoded(name, mirror):
    """{MK frame number: sprites} of an art file, every frame, as Frames draws
    them (16x16 cells, the grid's order reversed: the first ends on top;
    mirrored: the grid flipped)."""
    import mksch
    d = os.path.join(ROOT, 'extracted', 'mk_us')
    art = mksch.FighterArt(open(os.path.join(d, name + '.OBJ'), 'rb').read(),
                           open(os.path.join(d, name + '.SCH'), 'rb').read())
    out = {}
    for n in range(art.count):
        at = art.records + mksch.u16(art.obj, art.frame_table + n * 2)
        cells, w, h = (mksch.u16(art.obj, at + i) for i in (0, 2, 4))
        sp = []
        for i in range(cells):
            c = mksch.u16(art.obj, at + 10 + 2 * i)
            if c:
                y, x = divmod(i, w)
                p = art.cell(c)
                sp.append(((w - 1 - x) * 16 if mirror else x * 16, y * 16, p[:, ::-1] if mirror else p))
        sp, _ = Frames.corner(sp[::-1])
        if sp:
            out[FIRST + n] = sp
    return out


def library(source, last=0xFF):
    """{frame: sprites} for a source 'STATE:PLAYER' (e.g. 'mk_2p:1') or
    'REPLAY+AT:SLOT:PAL' (an object in a replayed fatality, AT frames after
    BONES.OBJ is first drawn from; e.g. 'sonyafatal+57:1:1': BONES's frames as
    her loser burns). Read from the disc's art (ART: no emulator); a source not
    in ART is drawn by MK in the emulator. Cached in extracted/mk_frames/."""
    import pickle
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, source.replace(':', '_p').replace('+', '_t') + '.pkl')
    if os.path.exists(path):
        return pickle.load(open(path, 'rb'))
    if source in ART:
        out = decoded(*ART[source])
    else:
        out = drawn_library(source, last)
    pickle.dump(out, open(path + '.tmp%d' % os.getpid(), 'wb'))
    os.replace(path + '.tmp%d' % os.getpid(), path)            # (several runs may build it at once)
    return out


def drawn_library(source, last=0xFF):
    """The frames as MK draws them in the emulator (what ART was checked
    against); frames that draw the same picture as a lower number left out."""
    if '+' in source:
        rp, rest = source.split('+')
        at, slot, pal = map(int, rest.split(':'))
        got = Frames(None, replay=rp, at=at, slot=slot, pal=pal).all(last)
    else:
        state, player = source.split(':')
        got = Frames(state + '.state', int(player)).all(last)
    seen, out = set(), {}
    for f, sp in sorted(got.items()):
        k = picture(sp).tobytes()
        if k not in seen:
            seen.add(k)
            out[f] = sp
    return out


# Pieces: sprites MK draws that are no fighter's frame (fighter frames are all
# 16x16 sprites): the spine Sub-Zero holds up, ... Their pictures come from
# decoding PAC.PRG for szfatal (other replay pieces use the emulator); each is
# named by a short hash of its pixels, so a recipe names it without holding its picture.
# name: (tool module with start(core, state, **kw), fight state, frames, palette line, kw)
REPLAYS = {
    'szfatal': ('mkfatality_subzero', 'mk_subzero_2p.state', 420, 0, {}),
    'sonyafatal': ('mkfatality_capture', 'mk_sonya_2p.state', 480, 1, {'name': 'sonya'}),
    'scfatal': ('mkfatality_capture', 'mk_2p.state', 480, 0, {'name': 'scorpion'}),
}
BONES = 0x9042                    # PRG RAM: BONES.OBJ (MK's fatality effects: fire, bones)


def replay_to(c, name, after):
    """Play replay NAME up to AFTER frames past the first frame an object draws
    from BONES.OBJ (a moment in the fatality, whatever the fight state's own
    timing: a fight state made afresh plays a frame or so apart)."""
    import importlib
    mod, st, n, _, kw = REPLAYS[name]
    importlib.import_module(mod).start(c, os.path.join(ROOT, 'build', 'states', st), **kw)
    for t in range(n):
        c.run(1)
        r = c.prg_ram()
        if any(int.from_bytes(r[a:a + 4], 'big') and int.from_bytes(r[a + 0x3A:a + 0x3E], 'big') == BONES
               for a in (0x7D702 + SLOT * k for k in range(8))):
            break
    else:
        raise AssertionError(f'{name}: no object draws from BONES.OBJ (the fatality didn\'t happen)')
    c.run(after)


def piece_name(p):
    import hashlib
    return hashlib.sha1(bytes(p.shape) + p.tobytes()).hexdigest()[:10]


def pieces(name):
    """{piece name: [(0, 0, pixels)]} (as frames: one sprite each) of a replay,
    cached in extracted/mk_frames/."""
    import importlib, pickle
    from inputs import require
    from vdp import VDPState
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, name + '.pkl')
    if os.path.exists(path):
        return pickle.load(open(path, 'rb'))
    if name == 'szfatal':
        import mkspine_disc
        with open(os.path.join(ROOT, 'extracted', 'mk_us', 'PAC.PRG'), 'rb') as f:
            out = mkspine_disc.extract(f.read())
        pickle.dump(out, open(path + '.tmp%d' % os.getpid(), 'wb'))
        os.replace(path + '.tmp%d' % os.getpid(), path)
        return out
    import scd
    mod, state, n, pal, kw = REPLAYS[name]
    c = scd.Core(saves=os.path.join(ROOT, 'build', 'shots', 'capture-saves'))
    c.load(require('mk_us').cue)
    importlib.import_module(mod).start(c, os.path.join(ROOT, 'build', 'states', state), **kw)
    out = {}
    for _ in range(n):
        c.run(1)
        v = VDPState(c.snapshot())
        for sp in v.sprites():
            if sp['pal'] == pal and (sp['w'], sp['h']) != (2, 2):
                p = v.sprite_pixels(sp)
                if p.any():
                    out.setdefault(piece_name(p), [(0, 0, p)])
    pickle.dump(out, open(path + '.tmp%d' % os.getpid(), 'wb'))
    os.replace(path + '.tmp%d' % os.getpid(), path)            # (several runs may build it at once)
    return out


def picture(sp, mirror=False):
    """A frame's sprites as one picture (as a capture shows it with nothing cut)."""
    w = max(x + p.shape[1] for x, y, p in sp)
    h = max(y + p.shape[0] for x, y, p in sp)
    out = np.zeros((h, w), np.uint8)
    for x, y, p in sp:
        ys, xs = np.nonzero(p)
        out[ys + y, xs + x] = p[ys, xs]
    out = out[:, ::-1] if mirror else out
    return crop(out) if out.any() else out


def build_one(src):
    got = library(src) if ':' in src else pieces(src)
    return src, len(got)


def verify_one(src):
    """(source, frames MK drew, how many the decoder gives identically - same
    sprites, same order -, the frame numbers that differ)."""
    key = lambda sp: [(x, y, p.tobytes()) for x, y, p in sp]
    drawn = drawn_library(src)
    dec = decoded(*ART[src])
    bad = [f for f, sp in drawn.items() if f not in dec or key(dec[f]) != key(sp)]
    return src, len(drawn), len(drawn) - len(bad), bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('state', nargs='?')
    ap.add_argument('--last', type=lambda v: int(v, 0), default=0xFF)
    ap.add_argument('--recipes', action='store_true',
                    help='draw every frame library the recipes (data/mk_recipes) use, into extracted/mk_frames/')
    ap.add_argument('--jobs', type=int, default=min(8, os.cpu_count() or 1))
    ap.add_argument('--verify', action='store_true',
                    help='every ART source: the decoded frames against the frames MK draws (emulator)')
    a = ap.parse_args()
    if a.verify:
        from multiprocessing import Pool
        wrong = 0
        with Pool(a.jobs) as pool:
            for src, n, ok, bad in pool.imap_unordered(verify_one, sorted(ART)):
                # (a number MK leaves up whatever was showing, 1 in some states, isn't a frame)
                bad = [f for f in bad if f >= FIRST]
                wrong += len(bad)
                print(f'{src:28s} {ok:3d}/{n:3d} decoded identically' + (f'  DIFFER {bad[:8]}' if bad else ''), flush=True)
        print('decoder: every frame identical' if not wrong else f'decoder: {wrong} frames differ')
        sys.exit(1 if wrong else 0)
    if a.recipes:
        import glob, json
        from multiprocessing import Pool
        srcs = set()
        for p in glob.glob(os.path.join(ROOT, 'data', 'mk_recipes', '*', '*.json')):
            srcs.update(json.load(open(p))['sources'])
        with Pool(a.jobs) as pool:
            for src, n in pool.imap_unordered(build_one, sorted(srcs)):
                print(f'{src:28s} {n:3d} frames', flush=True)
        open(os.path.join(CACHE, 'ALL'), 'w').write('\n'.join(sorted(srcs)) + '\n')   # (prepare.py: done)
        return
    fr = Frames(a.state)
    got = fr.all(a.last)
    print(f'idle list at ${fr.list_at:X} ({fr.list_words} words); {len(got)} frames drawn, '
          f'{len({picture(sp).tobytes() for sp in got.values()})} distinct')


if __name__ == '__main__':
    main()
