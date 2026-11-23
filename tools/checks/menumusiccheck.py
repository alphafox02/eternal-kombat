#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The title's music: EC's song, then MK's Mortal Monday music, never the MK cues after them.

The menus' track (19) holds EC's song, MK's (cdaudio.MENU_SONG_TRACK), then the cues for fights. EC
repeats the track with the BIOS, and left on the title the CD played on into the cues (random MK
announcer lines). The title hands over to EC's intro video at 5:00, inside MK's song. Left there 4 min
55 s, each 3 s of sound every 10 s is matched (normalised cross-correlation) against EC's song (the EC
disc's track 19), MK's track 20 and the cue section of the built disc's track 19:
  - EC's song first, then MK's (0.9+, 10 windows or more);
  - nothing like the cues (under 0.5).

    menumusiccheck.py [--disc CUE]     (after play.py test has made build/states/menu.state)
"""
import argparse, glob, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import numpy as np
from scipy.signal import fftconvolve, decimate
import scd, cdaudio
from disc import parse_cue, RAW
from inputs import ROOT

SECONDS = 295
R = 44100 / 4


def mono(x):
    return decimate(x.reshape(-1, 2).mean(1).astype(float), 4)


def ncc(src, q):
    q = (q - q.mean()) / (q.std() + 1e-9)
    c = fftconvolve(src, q[::-1], 'valid')
    e = np.sqrt(np.maximum(fftconvolve(src ** 2, np.ones(len(q)), 'valid'), 1e-9))
    n = c / e / np.sqrt(len(q))
    n[e < 0.2 * np.median(e)] = 0                  # (not the sources' silences)
    k = int(np.argmax(n))
    return float(n[k]), k / R


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    a = ap.parse_args()
    track = lambda cue, n: {t.number: t for t in parse_cue(cue)}[n].file
    ec_cue = glob.glob(os.path.join(ROOT, 'roms', 'ec_us', '*', '*.cue'))[0]
    mk_cue = glob.glob(os.path.join(ROOT, 'roms', 'mk_us', '*', '*.cue'))[0]
    ec = np.fromfile(track(ec_cue, 19), np.int16)
    ours = np.fromfile(track(a.disc, 19), np.int16)
    song = np.frombuffer(cdaudio.menu_song(mk_cue), np.int16)
    cut = (len(ec) * 2 + (cdaudio.MENU_SONG_GAP + cdaudio.MENU_TAIL) * RAW + len(song) * 2) // 2
    src = {'EC': mono(ec), 'MK': mono(song), 'cues': mono(ours[cut:])}

    c = scd.Core(audio=True)
    c.load(a.disc)
    c.load_state(os.path.join(ROOT, 'build', 'states', 'menu.state'))
    c.run(1)
    c.audio.clear()
    c.run(SECONDS * 60)
    A = mono(np.frombuffer(b''.join(c.audio), np.int16))

    seq, worst_cue = [], 0.0
    for t in range(0, SECONDS - 3, 10):
        q = A[int(t * R):int((t + 3) * R)]
        if q.std() < 50:
            seq.append((t, 'silent', 0, 0))
            continue
        m = {k: ncc(v, q) for k, v in src.items()}
        worst_cue = max(worst_cue, m['cues'][0])
        k = max(('EC', 'MK'), key=lambda k: m[k][0])
        seq.append((t, k if m[k][0] >= 0.9 else '?', m[k][0], m[k][1]))
    print(' '.join(f'{t}:{k}@{at:.0f}' for t, k, _, at in seq))
    mk_at = [i for i, s in enumerate(seq) if s[1] == 'MK']
    ok = seq[0][1] == 'EC' and len(mk_at) >= 10 and worst_cue < 0.5
    print(f'EC first: {seq[0][1] == "EC"}; MK\'s song: {len(mk_at)} windows; best match with the cues {worst_cue:.2f}')
    print('menumusiccheck:', 'ok' if ok else 'FAIL')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
