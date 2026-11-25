#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""MK CD's 2-player stages, in its order: a state at the start of each battle, and its music.

From your MK CD. MK's 2-player mode moves to the next stage each battle (tools/capture/
mkpitstate.py: the Courtyard, the Palace Gates, the Warrior Shrine, the Pit, ...). From
build/states/mk_kano_2p.state (tools/capture/mkduelstate.py kano: battle 1) player 2
crouch-punches player 1 down (walking in when far) and player 1 presses Start every second
(to continue, with the same pick), as mkpitstate.py does. In each battle, once the fight
has begun (SETTLE frames after MK's HUD), the state is saved and SECONDS of its sound are
matched against every MK CD audio track (normalised cross-correlation): the battle's track.

    mkstagestates.py [--battles 8]
        -> build/states/mk_battle_<n>.state, build/shots/mk_stages/battle_<n>.png, and a line per battle
"""
import argparse, os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scd
from disc import parse_cue, RAW
from inputs import ROOT, require
from vdp import VDPState
from mkpitstate import in_fight

SETTLE = 300                  # frames after the fighters show up: the round has begun
SECONDS = 8                   # of the battle's sound, matched against MK's tracks
RATE = 44100 / 4              # Hz, to match at


def mono(pcm):
    return np.frombuffer(pcm, '<i2').reshape(-1, 2).astype(np.float32).mean(1)


def best_track(rec, tracks, rate):
    """(track, score): the MK track the recording is part of (both at RATE Hz)."""
    rec = np.interp(np.arange(0, len(rec), rate / RATE), np.arange(len(rec)), rec)
    rec = (rec - rec.mean()) / (rec.std() + 1e-9)
    best = (None, 0.0)
    for n, t in tracks.items():
        if len(t) < len(rec):
            continue
        size = 2 ** int(np.ceil(np.log2(len(t) + len(rec))))
        corr = np.fft.irfft(np.fft.rfft(t, size) * np.conj(np.fft.rfft(rec, size)), size)[:len(t) - len(rec)]
        # normalise by the track's energy under the window
        c2 = np.concatenate([[0], np.cumsum(t.astype(np.float64) ** 2)])
        energy = np.sqrt(c2[len(rec):len(rec) + len(corr)] - c2[:len(corr)]) + 1e-9
        score = float((corr / energy).max() / np.sqrt(len(rec)))
        if score > best[1]:
            best = (n, score)
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--battles', type=int, default=8)
    a = ap.parse_args()
    cue = require('mk_us').cue
    tracks = {}
    for t in parse_cue(cue):
        if t.mode == 'AUDIO':
            raw = open(t.file, 'rb').read()
            tracks[t.number] = mono(raw[::1])[::4]          # 11 kHz is plenty to match
    tracks = {n: (t - t.mean()) for n, t in tracks.items()}
    c = scd.Core(audio=True, saves=os.path.join(ROOT, 'build', 'shots', 'capture-saves'))
    c.load(cue)
    c.load_state(os.path.join(ROOT, 'build', 'states', 'mk_kano_2p.state'))
    c.run(2)
    shots = os.path.join(ROOT, 'build', 'shots', 'mk_stages')
    os.makedirs(shots, exist_ok=True)

    def centre(pal):
        xs = [sp['x'] for sp in VDPState(c.snapshot()).sprites() if sp['pal'] == pal and sp['y'] > 40]
        return (min(xs) + max(xs)) // 2 if xs else None
    battle, fight, away, since, p1, p2, pcm, saved = 1, True, 0, 0, None, None, [], False
    for k in range(60 * 60 * 40):
        if k % 15 == 0:
            now = in_fight(c.frame)
            if now and not fight and away >= 600:          # a new battle (the HUD back after 10 s+)
                battle += 1
                since, pcm, saved = k, [], False
            away = 0 if now else away + 15
            fight = now
            p1, p2 = centre(0), centre(1)
        if battle > a.battles:
            return
        settled = fight and k >= since + SETTLE
        if settled and not saved:
            c.save_state(os.path.join(ROOT, 'build', 'states', f'mk_battle_{battle}.state'))
            c.shot(os.path.join(shots, f'battle_{battle}.png'))
            saved, pcm = True, []
        if saved and pcm is not None and len(pcm) < 60 * SECONDS:
            pcm.append(b''.join(c.audio))
            if len(pcm) == 60 * SECONDS:
                n, score = best_track(mono(b''.join(pcm))[::4], tracks, c.sample_rate / 4)
                print(f'battle {battle}: MK track {n} (match {score:.2f}) -> build/states/mk_battle_{battle}.state',
                      flush=True)
                pcm = None
        c.audio.clear()
        # the first battles: player 2 wins (walking in when far); player 1 presses Start every second
        far = p1 is not None and p2 is not None and abs(p2 - p1) > 55
        if settled and pcm is not None:
            c.buttons = [set(), set()]                      # (quiet while the music is recorded)
        else:
            c.buttons[1] = {'left' if p2 > p1 else 'right'} if far else \
                ({'down', 'x'} if k % 20 < 6 else ({'down'} if k % 20 < 10 else set()))
            c.buttons[0] = {'start'} if k % 60 < 3 else set()
        c.run(1)
    sys.exit(f'MK: only {battle} battles in 40 minutes')


if __name__ == '__main__':
    main()
