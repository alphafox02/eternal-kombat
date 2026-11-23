#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Record the sound effects of an MK CD fatality from the user's MK disc, lined up with track 13.

Sub-Zero's spine rip by default; OUT lists the others. Track 13 is MK's fatality music.

MK plays track 9 at FINISH HIM, track 13 a moment after the fatality's input,
then track 10; its sound effects (the rip and the splatter: the same for a man
and a woman - measured on Scorpion and on Sonya) are mixed on top by the sound
chip. To get the effects alone the fatality is played twice from
build/states/mk_subzero_2p.state (as tools/lib/mkfatality_subzero.py):

  1. from the real disc: where track 13 starts (matched against the track);
  2. from a copy of the disc layout whose music tracks (9, 10, 13) are silent
     (links to the other files, in a temporary folder): only the effects.

    mkfatalsound.py [subzero]  -> extracted/mk_moves_subzero/spinerip_sfx.wav
    mkfatalsound.py NAME       -> OUT[NAME], e.g. johnny: extracted/mk_moves_johnny/fatality_sfx.wav
                         (44.1 kHz stereo, from track 13's start; the others from
                         tools/lib/mkfatality_capture.py's state and input)

cdaudio.mk_jingle mixes each into MK's fatality music for that fighter's part.

prepare.py no longer runs this: tools/lib/mksound_render.py makes the same bytes
from the disc and data/mk_sound (measured from these recordings with
tools/capture/mksound_measure.py, from fight states made from a cold boot).
"""
import os, shutil, sys, tempfile, wave
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import scd
from vdp import VDPState
from inputs import ROOT, require
from disc import parse_cue, RAW
import mkfatality_subzero as m

OUT = {'subzero': os.path.join(ROOT, 'extracted', 'mk_moves_subzero', 'spinerip_sfx.wav'),
       'johnny': os.path.join(ROOT, 'extracted', 'mk_moves_johnny', 'fatality_sfx.wav'),
       'raiden': os.path.join(ROOT, 'extracted', 'mk_moves_raiden', 'fatality_sfx.wav'),
       'liukang': os.path.join(ROOT, 'extracted', 'mk_moves_liukang', 'fatality_sfx.wav'),
       'sonya': os.path.join(ROOT, 'extracted', 'mk_moves_sonya', 'fatality_sfx.wav'),
       'kano': os.path.join(ROOT, 'extracted', 'mk_moves_kano', 'fatality_sfx.wav'),
       'scorpion': os.path.join(ROOT, 'extracted', 'mk_moves', 'fatality_sfx_man.wav'),
       'scorpion_sonya': os.path.join(ROOT, 'extracted', 'mk_moves', 'fatality_sfx_woman.wav')}
SECONDS = 18.0                # recorded from the end of the input (track 13 starts ~1.5 s in)
KEEP = 15.0                   # s kept from track 13's start (the rip sounds, then MK's announcer ~9 s in)
SILENT = (9, 10, 13)          # MK's music tracks around a fatality


def record(cue, who='subzero', states=None):
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

    if who == 'subzero':
        state, inp = 'mk_subzero_2p.state', m.INPUT
    else:
        import mkfatality_capture
        _, state, inp, _ = mkfatality_capture.FATALITIES[who]
    c.load_state(os.path.join(states or os.path.join(ROOT, 'build', 'states'), state))
    c.run(60)
    win_round()
    c.run(20)
    while hp() != (119, 119):
        c.run(10)
    c.run(240)
    win_round()                                  # FINISH HIM
    c.run(150)
    if who != 'subzero':                         # up close, as tools/lib/mkfatality_capture.py
        for _ in range(40):
            if gap() < -14:
                break
            hold(['right'], 2)
        c.run(4)
    for held, n in inp:
        c.buttons[0] = set(held.split('+')) - {''}
        c.run(n)
    c.buttons[0] = set()
    c.audio.clear()
    c.run(int(SECONDS * 60))
    pcm = np.frombuffer(b''.join(c.audio), np.int16).reshape(-1, 2).astype(float)
    if int(c.sample_rate) != 44100:
        t = np.linspace(0, len(pcm) - 1, int(len(pcm) * 44100 / c.sample_rate))
        pcm = np.stack([np.interp(t, np.arange(len(pcm)), pcm[:, k]) for k in (0, 1)], 1)
    return pcm


def onset(sig, ref):
    """Where ref's start best matches in sig (normalised cross-correlation, FFT)."""
    r = ref - ref.mean()
    r /= np.sqrt((r * r).sum()) + 1e-9
    n = len(sig) + len(r)
    c = np.fft.irfft(np.fft.rfft(sig, n) * np.conj(np.fft.rfft(r, n)), n)[:len(sig) - len(r)]
    cs = np.concatenate([[0], np.cumsum(sig * sig)])
    e = np.sqrt(cs[len(r):len(r) + len(c)] - cs[:len(c)]) + 1e-9
    k = int(np.argmax(c / e))
    return k, float((c / e)[k])


def silent_copy(cue, tmp):
    """The disc's layout in folder tmp with the music tracks (SILENT) zero-filled: its cue."""
    for t in parse_cue(cue):
        dst = os.path.join(tmp, os.path.basename(t.file))
        if os.path.exists(dst):
            continue
        if t.number in SILENT:
            with open(dst, 'wb') as f:
                f.truncate(os.path.getsize(t.file))
        else:
            os.symlink(t.file, dst)
    shutil.copyfile(cue, os.path.join(tmp, os.path.basename(cue)))
    return os.path.join(tmp, os.path.basename(cue))


def main():
    who = sys.argv[1] if len(sys.argv) > 1 else 'subzero'
    cue = require('mk_us').cue
    tracks = {t.number: t for t in parse_cue(cue)}
    t13 = tracks[13]
    raw = open(t13.file, 'rb').read()[t13.index01 * RAW:(t13.index01 + t13.length) * RAW]
    ref = np.frombuffer(raw, '<i2').reshape(-1, 2).mean(1)[:int(1.5 * 44100)].astype(float)
    full = record(cue, who)
    k, q = onset(full.mean(1), ref)
    print(f'track 13 starts {k / 44100:.2f}s after the input (match {q:.2f})')
    if q < 0.5:
        raise SystemExit('track 13 not found in the recording')
    tmp = tempfile.mkdtemp()
    try:
        sfx = record(silent_copy(cue, tmp), who)
    finally:
        shutil.rmtree(tmp)
    out = sfx[k:k + int(KEEP * 44100)]
    out_path = OUT[who]
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    w = wave.open(out_path, 'wb')
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(44100)
    w.writeframes(np.clip(out, -32768, 32767).astype('<i2').tobytes())
    w.close()
    print(f'{len(out) / 44100:.1f}s -> {os.path.relpath(out_path, ROOT)}')


if __name__ == '__main__':
    main()
