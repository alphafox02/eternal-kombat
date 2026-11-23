#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""MK's grunts: an MK fighter grunts once as he leaves the floor in a jump, not as he punches.

(mkscripts.GRUNT_RECORDS, patches.mk_punch_grunt, mkinputs.JUMP_GRUNT.) The jump's grunt is MALEJUMP
(FIGHT.SND $3F2; Sonya's is GIRLJUMP). His punches keep EC's swing, as his kicks do
(mkscripts.GRUNT_MOVES off: a grunt on every punch made the game sound worse); an EC fighter's
punches and jumps don't grunt. A sound is a PCM channel's play bit rising, named by the clip at the
channel's start (as feetcheck.py). Prints the frame after the press each grunt starts (MK: a
punch's 2, a jump's 3-6; ours on the strike step, where EC plays a swing: 8-11).

    gruntcheck.py [--disc CUE]
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT
from patches import mk_sample, to_rf5c164

CH, ON, RAM = 0x28085, 0x28085 + 0x86, 0x2810D
# fighter: (grid, the grunt his punches should play, or None: EC's swing)
CASES = {'kano': (18, 'MALEJUMP'), 'subzero': (15, 'MALEJUMP'), 'sonya': (16, 'GIRLJUMP'), 'blade': (8, None)}


def clip(name, hz=None):
    rate, body = mk_sample(name + '.SVX')
    hz = hz or rate
    pcm = to_rf5c164(body, rate, hz, int(len(body) * hz / rate))
    q = next((i for i, v in enumerate(pcm) if (v & 0x7F) > 6), 0)
    return q, bytes(pcm[q:q + 96])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    a = ap.parse_args()
    known = {'MALEJUMP': [clip('MALEJUMP'), clip('MALEJUMP', 8000)], 'GIRLJUMP': [clip('GIRLJUMP', 8000), clip('GIRLJUMP')]}
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        for who, (grid, want) in CASES.items():
            st = os.path.join(tmp, 'duel.state')
            subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', a.disc,
                            '--p1', str(grid), '--p2', '0', '--stage', '11', '--out', st], check=True, capture_output=True)
            c = scd.Core(saves=os.path.join(tmp, 'saves'))
            c.load(a.disc)
            c.load_state(st)
            c.run(60)
            base = c.snapshot()
            got = {}
            for b in ('x', 'y', 'a', 'c', 'up', 'up+right'):
                c.restore(base)
                mask, heard, keys, when = c.snapshot()[ON], {}, 0, None
                for t in range(70):
                    c.buttons[0] = set(b.split('+')) if t < 3 else set()
                    c.run(1)
                    s = c.snapshot()
                    for ch in range(8):
                        if s[ON] >> ch & 1 and not mask >> ch & 1:
                            keys += 1
                            start = int.from_bytes(s[CH + 16 * ch + 4:CH + 16 * ch + 8], 'little') >> 11
                            for name, forms in known.items():
                                for q, cl in forms:
                                    w = s[RAM + start + q:RAM + start + q + len(cl)]
                                    if sum(x == y for x, y in zip(w, cl)) >= 0.9 * len(cl):
                                        heard[name] = heard.get(name, 0) + 1
                                        when = t if when is None else when
                    mask = s[ON]
                got[b] = (heard, keys, when)
            punch = [got[b][0].get(want, 0) if want else sum(got[b][0].values()) for b in ('x', 'y')]
            jump = [got[b][0].get(want, 0) if want else sum(got[b][0].values()) for b in ('up', 'up+right')]
            kick = [sum(got[b][0].values()) for b in ('a', 'c')]
            swing = all(got[b][1] for b in ('a', 'c', 'x', 'y'))
            ok = (jump == [1, 1] if want else jump == [0, 0]) and punch == [0, 0] and kick == [0, 0] and swing
            bad += not ok
            print(f'  {who:8s} X/Y {want or "grunts"}: {punch} (frame ' + ','.join(str(got[b][2]) for b in ('x', 'y'))
                  + f'), jumps: {jump} (frame ' + ','.join(str(got[b][2]) for b in ('up', 'up+right'))
                  + f'), A/C grunts: {kick}, sounds ' + ' '.join(f'{b}:{got[b][1]}' for b in got)
                  + f' -> {"ok" if ok else "FAIL"}')
    print(f'jump grunts, none on punches: {"ok" if not bad else f"{bad} FAIL"}')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
