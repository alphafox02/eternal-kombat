#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""An unfinished FINISH HIM must not run into the fatality music.

FINISH HIM plays MK's track 9 from the last track (cdaudio.mk_jingle part 0), and the CD plays on
past a part's end: with only 1 s of silence after it, a FINISH HIM left alone ran into part 1 (the
fatality music, its flame and scream) over EC's fade to the stats (cdaudio.FINISH_TAIL). Sub-Zero
against Midknight, Midknight kept on low health until FINISH HIM, then no input to the stats screen;
each second of sound after FINISH HIM is matched against part 1 (normalised cross-correlation; the
bug measured 0.97-0.99). Prints the best match and its second.

    finishmusiccheck.py [--disc CUE]
"""
import argparse, glob, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import numpy as np
import scd, cdaudio
from inputs import ROOT

P1, P2 = 0x2E188, 0x2E330


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    a = ap.parse_args()
    mk = glob.glob(os.path.join(ROOT, 'roms', 'mk_us', '*', '*.cue'))[0]
    fatal = np.frombuffer(cdaudio.mk_jingle(mk)[1], '<i2').reshape(-1, 2).astype(float).mean(1)
    with tempfile.TemporaryDirectory() as tmp:
        st = os.path.join(tmp, 'duel.state')
        subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', a.disc,
                        '--p1', '15', '--p2', '0', '--p2-id', '7', '--stage', '19', '--out', st],
                       check=True, capture_output=True)
        c = scd.Core(audio=True, saves=os.path.join(tmp, 'saves'))
        c.load(a.disc)
        c.load_state(st)
        word = lambda o, f: int.from_bytes(c.prg_ram()[o + f:o + f + 2], 'big', signed=True)
        finish, pcm = None, []
        for f in range(60 * 60):
            if finish is None:
                if word(P2, 0x76) > 4:
                    c.poke_prg(P2 + 0x76, (4).to_bytes(2, 'big'))
                if word(P2, 0xBE) & 0x7FFF == 0x1F:
                    finish = f
                gap = word(P2, 0x4E) - word(P1, 0x4E)
                c.buttons[0] = {'right' if gap > 0 else 'left'} if abs(gap) > 60 else ({'y'} if f % 8 < 3 else set())
            else:
                c.buttons[0] = set()
            c.run(1)
            if finish is not None:
                pcm.append(b''.join(c.audio))
            c.audio.clear()
    if finish is None:
        print('FAIL: no FINISH HIM')
        sys.exit(1)
    rec = np.frombuffer(b''.join(pcm), '<i2').reshape(-1, 2).astype(float).mean(1)
    r = int(round(c.sample_rate))
    n = 2 ** int(np.ceil(np.log2(len(fatal) + r)))
    spec = np.fft.rfft(fatal, n)
    best = (0.0, None)
    for t in range(7, len(rec) // r):                       # after part 0 (6.4 s) to the stats screen
        seg = rec[t * r:(t + 1) * r]
        if not seg.any():
            continue
        corr = np.fft.irfft(spec * np.conj(np.fft.rfft(seg, n)))[:len(fatal) - r]
        k = int(np.argmax(corr))
        v = corr[k] / (np.linalg.norm(seg) * np.linalg.norm(fatal[k:k + r]) + 1e-9)
        best = max(best, (float(v), t))
    ok = best[0] < 0.5
    print(f'FINISH HIM at frame {finish}; after its music, best match with the fatality music {best[0]:.2f}'
          f' (second {best[1]}) -> {"ok" if ok else "FAIL"}')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
