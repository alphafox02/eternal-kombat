#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""MK CD's FIGHT! and FINISH HIM / FINISH HER, as numbers: where each letter is, how big, which colours.

MK grows each letter from PAC.PRG's full-size letters (32 x 32 sprites at PAC $1CDC2 + 512 n:
LETTERS) while it runs, redrawing one letter's tiles every 2 frames at the zoom of that moment, and
spreads them apart; then they flash (palette line 2: red, line 1: grey). Played from the battle
states (tools/capture/mkstagestates.py): FIGHT! at round 2 of the Palace Gates battle, FINISH HIM
there (Kano down), FINISH HER from Scorpion vs Sonya (mkduelstate.py). Each frame, each letter
sprite (4 x 4 tiles in the text's VRAM) is matched against the PAC letters scaled by s / 32
(scale(): nearest pixel, MK's top-left anchored growth) - the letter and the s whose picture
differs least (MK's own picture is caught mid-redraw now and then: a few pixels off).

    mktext.py   -> data/mk_text.json: {event: [frame: [[letter, x, y, s, palette line], ...]]}
"""
import argparse, json, os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT, require
from vdp import VDPState

LETTERS = 'F I G H T N S M E R !'.split()      # PAC.PRG's big letters, in its order (from $1DDC2: F)
PAC_F = 0x1DDC2
EVENT_FRAMES = 150                             # frames recorded from the text's first appearance
TEXT_TILES = 0x180                             # MK's big text's VRAM (its fighters' tiles are far above)


def pac_letters(pac):
    out = {}
    for k, name in enumerate(LETTERS):
        raw = np.frombuffer(pac[PAC_F + 512 * k:PAC_F + 512 * (k + 1)], np.uint8).reshape(16, 8, 4)
        t = np.empty((16, 8, 8), np.uint8)
        t[:, :, 0::2], t[:, :, 1::2] = raw >> 4, raw & 15
        img = np.zeros((32, 32), np.uint8)
        for i in range(16):
            img[(i % 4) * 8:(i % 4) * 8 + 8, (i // 4) * 8:(i // 4) * 8 + 8] = t[i]
        out[name] = img
    return out


def scale(img, s):
    """img (32 x 32) at s / 32: each pixel the source pixel at ((x + 1/2) * 32 / s), top-left anchored."""
    out = np.zeros((32, 32), np.uint8)
    n = (32 * s + 31) // 32
    for y in range(min(32, n)):
        sy = int((y + 0.5) * 32 / s)
        if sy >= 32:
            continue
        for x in range(min(32, n)):
            sx = int((x + 0.5) * 32 / s)
            if sx < 32:
                out[y, x] = img[sy, sx]
    return out


def best(px, letters, cache):
    best_ = None
    for name, img in letters.items():
        for s in range(1, 33):
            key = (name, s)
            if key not in cache:
                cache[key] = scale(img, s)
            d = int((cache[key] != px).sum())
            if best_ is None or d < best_[0]:
                best_ = (d, name, s)
    return best_


def record(c, letters, start_test, frames=EVENT_FRAMES):
    """Run until start_test(frame image) says the text is up; then EVENT_FRAMES frames of letters."""
    cache, out = {}, []
    for _ in range(60 * 60):
        c.run(1)
        if start_test(c):
            break
    else:
        raise SystemExit('the text never came up')
    for _ in range(frames):
        v = VDPState(c.snapshot())
        row = []
        for s in v.sprites():
            if s['w'] == 4 and s['h'] == 4 and s['tile'] < TEXT_TILES:
                px = v.sprite_pixels(s)
                if not px.any():
                    continue
                d, name, sc = best(px, letters, cache)
                row.append([name, s['x'], s['y'], sc, s['pal'], d])
        out.append(row)
        c.run(1)
    return out


def cut(ev, word):
    """The frames of ev from the first showing word's letters (each letter of the word there, none
    other) to the last such frame."""
    want = sorted(word.replace(' ', ''))
    ok = [sorted(r[0] for r in fr) == want for fr in ev]
    # (a letter can be too small to tell early on: from the first frame whose letters are all the word's)
    first = next(i for i, fr in enumerate(ev) if fr and all(r[0] in want for r in fr) and len(fr) == len(want))
    last = max(i for i, o in enumerate(ok) if o)
    return ev[first:last + 1]


def red_text(c):
    """MK's big text is up: a 4 x 4 sprite from the text's VRAM."""
    return any(s['w'] == 4 and s['h'] == 4 and s['tile'] < TEXT_TILES and s['y'] < 160
               for s in VDPState(c.snapshot()).sprites())


def main():
    ap = argparse.ArgumentParser()
    ap.parse_args()
    pac = open(os.path.join(ROOT, 'extracted', 'mk_us', 'PAC.PRG'), 'rb').read()
    letters = pac_letters(pac)
    c = scd.Core(saves=os.path.join(ROOT, 'build', 'shots', 'capture-saves'))
    c.load(require('mk_us').cue)
    out = {}

    def centre(pal):
        xs = [sp['x'] for sp in VDPState(c.snapshot()).sprites() if sp['pal'] == pal and sp['y'] > 40]
        return (min(xs) + max(xs)) // 2 if xs else None

    def beat(winner, victim_pal, until):
        """The winner (port) walks in and crouch-punches until until(c)."""
        a = b = None
        for k in range(60 * 60 * 3):
            if k % 15 == 0:
                a, b = centre(1 - victim_pal), centre(victim_pal)
            far = a is not None and b is not None and abs(b - a) > 55
            c.buttons = [set(), set()]
            c.buttons[winner] = {'left' if (b or 0) < (a or 0) else 'right'} if far else \
                ({'down', 'x'} if k % 20 < 6 else ({'down'} if k % 20 < 10 else set()))
            c.run(1)
            if until(c):
                c.buttons = [set(), set()]
                return
        raise SystemExit('never got there')
    # FIGHT! (round 2 of the Gates battle: player 2 wins round 1), then FINISH HIM (round 2)
    c.load_state(os.path.join(ROOT, 'build', 'states', 'mk_battle_2.state'))
    c.run(2)
    beat(1, 0, red_text)                           # round 1 lost: the next text is round 2's FIGHT!
    c.buttons = [set(), set()]
    out['fight'] = cut(record(c, letters, lambda c: True, 300), 'FIGHT!')
    beat(1, 0, red_text)                           # round 2 down to FINISH HIM
    out['finish_him'] = cut(record(c, letters, lambda c: True, 300), 'FINISH HIM')
    # FINISH HER: Scorpion (1) beats Sonya (2) twice
    c.load_state(os.path.join(ROOT, 'build', 'states', 'mk_scorpion_sonya_2p.state'))
    c.run(2)
    beat(0, 1, red_text)                           # (round 2's FIGHT!)
    record(c, letters, lambda c: True, 300)
    beat(0, 1, red_text)
    out['finish_her'] = cut(record(c, letters, lambda c: True, 300), 'FINISH HER')
    for k, ev in out.items():
        words = sorted({tuple(sorted({(r[0], r[1] // 4) for r in fr})) for fr in ev[-10:] if fr})
        print(k, len(ev), 'frames; last letters', ''.join(r[0] for r in sorted(ev[-1], key=lambda r: r[1])) if ev[-1] else '-',
              'worst match', max((r[5] for fr in ev for r in fr), default=0), flush=True)
    json.dump({k: [[r[:5] for r in fr] for fr in ev] for k, ev in out.items()},
              open(os.path.join(ROOT, 'data', 'mk_text.json'), 'w'), separators=(',', ':'))


if __name__ == '__main__':
    main()
