#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The disc's 32X support, with a 32X (PicoDrive) and without one (Genesis Plus GX).

(tools/lib/build32x.py, docs/32x.md.) Both by the same real controller route: boot, the warning screen,
Duel, player 1 on Scorpion against player 2's Shadow, the fight (Shadow kept on low health: Scorpion jabs
her out, round after round), the statistics, and back to the select screen. Checks, in both:
  - the warning screen is EC's blue (an old 32X test drew a portrait over it on a black ground),
  - the first select screen's MK row: the 32X's portraits with a 32X (100+ colours; the Genesis draws
    14), the Genesis portraits without,
  - the fight starts and player 1 moves when he holds toward her,
  - the match ends and the game is back on the select screen (the 32X disc hung before the fight
    once: the VBlank call left on the select hook's memory),
  - twice over: two matches, three visits to select, each with its portraits (32x_reentry.py: they
    showed on the first visit only, and a first re-entry froze the second).

    x32check.py [--disc CUE] [--only 32x|no32x]
"""
import argparse, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import numpy as np
import scd, pico
from inputs import ROOT

P1, P2 = 0x2E188, 0x2E330
MK_ROW = (slice(144, 192), slice(64, 256))       # the select screen's MK portraits
TITLE = (slice(8, 32), slice(40, 280))           # 'PLAYER SELECT'


def title_mask(frame):
    """The yellow 'PLAYER SELECT' letters (EC cycles the background's colours between visits)."""
    t = frame[TITLE].astype(int)
    return (t[..., 0] > 150) & (t[..., 1] > 150) & (t[..., 2] < 110)


def main_menu(frame):
    """The main menu's yellow 'MAIN MENU' (the title's PRESS START is lower down)."""
    t = frame[118:136, 60:260].astype(int)
    return int(((t[..., 0] > 150) & (t[..., 1] > 150) & (t[..., 2] < 110)).sum()) > 200


def colours(frame):
    return len({tuple(p) for p in frame[MK_ROW].reshape(-1, 3)})


def route(c, log, matches=2):
    """-> {check: (ok, detail)}: the warning screen, then MATCHES times: select, a match, back to select."""
    out = {}
    word = lambda o, f: int.from_bytes(c.prg_ram()[o + f:o + f + 2], 'big', signed=True)
    c.run(1500)
    corner = c.frame[4:60, 4:60].reshape(-1, 3).mean(0)
    out['warning'] = (corner[2] > 60 and corner[2] > 2 * corner[0], f'top-left mean RGB {corner.astype(int).tolist()}')
    for _ in range(8):                                   # warning, intro, title, PRESS START -> the menu
        if main_menu(c.frame):                           # (watched, not counted: the plain disc boots a
            break                                        #  little sooner, and a 4th press entered the Contest)
        c.press(['start']); c.run(300)
    c.press(['down']); c.run(30); c.press(['start']); c.run(400)
    select = c.frame.copy()
    for n in range(1, matches + 1):
        out[f'select {n}'] = (None, colours(c.frame))
        c.press(['start'], port=1); c.run(60)
        for _ in range(20):
            c.press(['right']); c.run(20)
        c.press(['start']); c.run(60); c.press(['start'], port=1); c.run(330)
        c.press(['start']); c.run(400)
        x0, moved, rounds, prev = None, 0, 0, None
        for t in range(60 * 90):
            h, gap = word(P2, 0x76), word(P2, 0x4E) - word(P1, 0x4E)
            if 4 < h <= 200:
                c.poke_prg(P2 + 0x76, (4).to_bytes(2, 'big'))
            if t < 120:                                  # (the fight's start: hold toward her)
                c.buttons[0] = {'right' if gap > 0 else 'left'}
            else:
                c.buttons[0] = {'right' if gap > 0 else 'left'} if abs(gap) > 58 else ({'x'} if t % 8 < 3 else set())
            c.run(1)
            x = word(P1, 0x4E)
            x0 = x if x0 is None else x0
            moved = max(moved, abs(x - x0))
            if prev is not None and prev > 0 and h == 0:
                rounds += 1
            prev = h
        out[f'fight {n}'] = (moved >= 40 and rounds >= 1, f'player 1 moved {moved} px, rounds won {rounds}')
        c.buttons[0] = set()
        back = False
        for i in range(40):                              # the statistics, then Start until select
            c.run(150)
            m, want = title_mask(c.frame), title_mask(select)
            if want.sum() > 200 and (m == want).mean() > 0.97:
                back = True
                break
            if i % 2:
                c.press(['start'])
        if not back:
            out[f'back {n}'] = (False, 'never back on the select screen')
            return out
        f0 = c.frame.copy(); c.run(120)
        alive = int((np.abs(c.frame.astype(int) - f0.astype(int)).sum(2) > 0).sum())
        out[f'back {n}'] = (alive > 0, f'back on the select screen, {alive} pixels changed in 2 s')
        if not alive:
            return out
    out[f'select {matches + 1}'] = (None, colours(c.frame))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    ap.add_argument('--only', choices=('32x', 'no32x'))
    a = ap.parse_args()
    if not os.path.exists(a.disc):
        sys.exit(f'no {a.disc}: run tools/build.py')
    bad = 0
    import tempfile
    for name, make in (('32x', lambda d: pico.core(saves=d)), ('no32x', lambda d: scd.Core(saves=d))):
        if a.only and a.only != name:
            continue
        with tempfile.TemporaryDirectory() as tmp:
            c = make(tmp)
            c._check_layout = lambda *x: None
            c.load(a.disc)
            r = route(c, print)
        for k in list(r):
            if k.startswith('select'):
                sel = r[k][1]
                ok = sel >= 100 if name == '32x' else sel < 40
                r[k] = (ok, f'{sel} colours in the MK row ({"32X portraits" if sel >= 100 else "Genesis portraits"})')
        for k, (ok, detail) in r.items():
            bad += not ok
            print(f'  {name:5s} {k:9s} {"ok" if ok else "FAIL"}  {detail}')
    print(f'32X support: {"ok" if not bad else f"{bad} FAIL"}')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
