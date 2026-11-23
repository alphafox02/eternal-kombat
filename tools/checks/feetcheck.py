#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""MK's FEETLAND plays as an MK fighter lands a jump, and not as he walks.

(mkinputs.emit_jump_drive, FEET_SOUND; its clip in FIGHT.SND: patches.FIGHT_NEW.) Once at each
landing of a jump forward, straight up and back, and never while he walks (EC's walk is the jump's
move too: its steps bob him off the floor). A sound is a PCM channel's play bit rising, named by the
clip at the channel's start (spearsoundcheck).

    feetcheck.py [--fighters subzero,kano,...] [--disc CUE]
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT
from patches import mk_sample, to_rf5c164

CH, ON, RAM = 0x28085, 0x28085 + 0x86, 0x2810D
GRID = {'scorpion': 20, 'raiden': 7, 'subzero': 15, 'sonya': 16, 'liukang': 17, 'kano': 18, 'johnny': 19}
P1, P2 = 0x2E188, 0x2E330
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big', signed=True)


def feet():
    rate, body = mk_sample('FEETLAND.SVX')
    pcm = to_rf5c164(body, rate, rate, len(body))
    q = next((i for i, v in enumerate(pcm) if (v & 0x7F) > 6), 0)
    return q, bytes(pcm[q:q + 128])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fighters', default=','.join(GRID))
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    a = ap.parse_args()
    q, clip = feet()
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        for who in a.fighters.split(','):
            st = os.path.join(tmp, 'duel.state')
            subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', a.disc,
                            '--p1', str(GRID[who]), '--p2', '0', '--stage', '11', '--out', st], check=True, capture_output=True)
            c = scd.Core(saves=os.path.join(tmp, 'saves'))
            c.load(a.disc)
            c.load_state(st)
            c.run(60)
            mask = c.snapshot()[ON]

            def run(held, n):
                nonlocal mask
                heard = 0
                for _ in range(n):
                    c.buttons[0] = held
                    c.run(1)
                    s = c.snapshot()
                    for ch in range(8):
                        if s[ON] >> ch & 1 and not mask >> ch & 1:
                            start = int.from_bytes(s[CH + 16 * ch + 4:CH + 16 * ch + 8], 'little') >> 11
                            w = s[RAM + start + q:RAM + start + q + len(clip)]
                            heard += sum(x == y for x, y in zip(w, clip)) >= 0.9 * len(clip)
                    mask = s[ON]
                return heard

            got = []
            for name, held in (('forward', {'up', 'right'}), ('up', {'up'}), ('back', {'up', 'left'})):
                n = run(held, 4) + run(set(), 100)
                got.append((name, n))
            walk = run({'right'}, 60) + run({'left'}, 60) + run(set(), 30)
            ok = all(n == 1 for _, n in got) and walk == 0
            bad += not ok
            print(f'  {who:9s} ' + ', '.join(f'{k} jump {n}' for k, n in got) + f', walking {walk} -> {"ok" if ok else "FAIL"}')
    print(f'feet on landing: {"ok" if not bad else f"{bad} FAIL"}')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
