#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Find an MK CD fatality's input by trying candidates.

MK starts its fatality music (CD track 13) only when a fatality begins, so each
candidate is played from FINISH HIM (as tools/lib/mkfatality_capture.py) with audio,
and the recording is matched against track 13's start (as tools/lib/mkfatalsound.py).

    mkfataltrial.py kano candidates.json [--close]
        candidates.json: [[label, [[buttons, frames], ...]], ...]
        -> per candidate: track 13 heard (match >= 0.5) or not
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import numpy as np
import scd
from vdp import VDPState
from inputs import ROOT, require
from disc import parse_cue, RAW
import mkfatality_subzero as m
import mkfatality_capture as fc
from mkfatalsound import onset


def trial(cue, state, inp, close, back=0):
    c = scd.Core(audio=True, saves=os.path.join(ROOT, 'build', 'shots', 'capture-saves'))
    c.load(cue)
    hp = lambda: tuple(int.from_bytes(c.prg_ram()[a:a + 2], 'big') for a in (m.HP_P1, m.HP_P2))

    def gap():
        v = VDPState(c.snapshot())
        out = {}
        for pal in (0, 1):
            x = [s['x'] for s in v.sprites() if s['pal'] == pal and 80 < s['y'] < 230]
            out[pal] = (min(x), max(x) + 16) if x else None
        return out[1][0] - out[0][1] if out[0] and out[1] else 99

    def hold(b, n):
        c.buttons[0] = set(b)
        c.run(n)
        c.buttons[0] = set()

    def win_round():
        c.poke_prg(m.HP_P2, (2).to_bytes(2, 'big'))
        for _ in range(80):
            if gap() < -10:
                break
            hold(['right'], 2)
        hold(['a'], 3)
    c.load_state(os.path.join(ROOT, 'build', 'states', state))
    c.run(60)
    win_round()
    c.run(20)
    while hp() != (119, 119):
        c.run(10)
    c.run(240)
    win_round()
    c.run(150)
    if close:
        for _ in range(40):
            if gap() < -14:
                break
            hold(['right'], 2)
        c.run(4)
    if back:
        hold(['left'], back)
        c.run(4)
    for held, n in inp:
        c.buttons[0] = set(held.split('+')) - {''}
        c.run(n)
    c.buttons[0] = set()
    c.audio.clear()
    c.run(int(6 * 60))
    pcm = np.frombuffer(b''.join(c.audio), np.int16).reshape(-1, 2).astype(float)
    if int(c.sample_rate) != 44100:
        t = np.linspace(0, len(pcm) - 1, int(len(pcm) * 44100 / c.sample_rate))
        pcm = np.stack([np.interp(t, np.arange(len(pcm)), pcm[:, k]) for k in (0, 1)], 1)
    return pcm.mean(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('who')
    ap.add_argument('candidates')
    ap.add_argument('--close', action='store_true')
    ap.add_argument('--back', type=int, default=0, help='frames to walk back first (sweep distance)')
    a = ap.parse_args()
    cue = require('mk_us').cue
    tracks = {t.number: t for t in parse_cue(cue)}
    t13 = tracks[13]
    raw = open(t13.file, 'rb').read()[t13.index01 * RAW:(t13.index01 + t13.length) * RAW]
    ref = np.frombuffer(raw, '<i2').reshape(-1, 2).mean(1)[:int(1.5 * 44100)].astype(float)
    state = fc.FATALITIES[a.who][1] if a.who in fc.FATALITIES else {'scorpion': 'mk_2p.state'}.get(a.who, f'mk_{a.who}_2p.state')
    for label, inp in json.load(open(a.candidates)):
        sig = trial(cue, state, inp, a.close, a.back)
        k, q = onset(sig, ref)
        print(f'{label:40s} track 13 {"HEARD" if q >= 0.5 else "no   "} (match {q:.2f} at {k / 44100:.2f}s)', flush=True)


if __name__ == '__main__':
    main()
