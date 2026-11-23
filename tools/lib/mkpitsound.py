#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Record MK CD's own Pit fall soundtrack, from the user's MK disc.

On the Pit (build/states/mk_pit_raw.state, 2 players), player 1 wins a round, then the
deciding one: at FINISH HIM he waits, then uppercuts the dazed loser off the
bridge (MK's Pit fatality). From the uppercut MK plays CD track 10 (the
losing music) with the falling man's yell (MK's unnamed SFX2.BIN:3) and the
blood splatter on top: the game's own output is recorded.
Stage music is already stopped (FINISH HIM's track 9 ends at the uppercut).

    mkpitsound.py   -> extracted/mk_stages/pit_bottom/fall.wav (44.1 kHz stereo)

cdaudio.mk_jingle appends it to the disc's last track; the Pit's stage code
(ecstage.pit_fall_code) starts it when the loser is launched.

prepare.py no longer runs this: tools/lib/mksound_render.py pit makes the same
bytes from the disc and data/mk_sound/pit.json (tools/capture/mksound_measure.py).
"""
import os, sys, wave
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import scd
from vdp import VDPState
from inputs import ROOT, require

OUT = os.path.join(ROOT, 'extracted', 'mk_stages', 'pit_bottom', 'fall.wav')
SECONDS = 6.5                 # uppercut -> before MK's "KANO WINS" (about 7 s)
HP_P1, HP_P2 = 0x7D6C4, 0x7D7CA


def record(cue, states=None):
    """The game's 44.1 kHz stereo output from the uppercut, and the loser's health."""
    c = scd.Core(audio=True, saves=os.path.join(ROOT, 'build', 'shots', 'capture-saves'))
    c.load(cue)
    hp = lambda: tuple(int.from_bytes(c.prg_ram()[a:a + 2], 'big') for a in (HP_P1, HP_P2))

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
        c.poke_prg(HP_P2, (2).to_bytes(2, 'big'))
        for _ in range(80):
            if gap() < -10:
                break
            hold(['right'], 2)
        hold(['a'], 3)

    c.load_state(os.path.join(states or os.path.join(ROOT, 'build', 'states'), 'mk_pit_raw.state'))
    c.run(60)
    win_round()
    c.run(20)
    while hp() != (119, 119):
        c.run(10)
    c.run(240)
    win_round()                       # FINISH HIM
    c.run(150)                        # MK ignores inputs for a while after it
    hold(['down'], 8)
    c.audio.clear()                   # from the uppercut
    hold(['down', 'x'], 4)
    hold(['down'], 10)
    c.run(int(SECONDS * 60) - 14)
    pcm = np.frombuffer(b''.join(c.audio), np.int16).reshape(-1, 2)
    if int(c.sample_rate) != 44100:
        n = int(len(pcm) * 44100 / c.sample_rate)
        t = np.linspace(0, len(pcm) - 1, n)
        pcm = np.stack([np.interp(t, np.arange(len(pcm)), pcm[:, k]) for k in (0, 1)], 1).astype(np.int16)
    return pcm, hp()[1]


def main():
    pcm, loser = record(require('mk_us').cue)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    w = wave.open(OUT, 'wb')
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(44100)
    w.writeframes(pcm.astype('<i2').tobytes())
    w.close()
    print(f'{len(pcm) / 44100:.1f}s -> {os.path.relpath(OUT, ROOT)}  (loser health {loser})')


if __name__ == '__main__':
    main()
