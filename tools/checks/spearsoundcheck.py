#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Does the spear sound as MK's?

Its victim screams once at the hit (MALEHURT for a man, GIRLHURT for a woman), then the thrower says
GET OVER HERE once as he yanks. Scorpion (player 1) on Shadow; Reptile (player 2: his own lines in
his bank, CHA.SND - mkinputs.RS_SOUNDS) on Kano and on Sonya. A sound is a PCM channel's play bit
rising (the chip's channel mask); it is named by the clip at the channel's start (its first 256
bytes past its leading silence, at any of the voice rates). (A channel at its clip's end jumps back
to the start as it stops: no new sound, its bit falls.)

    spearsoundcheck.py [--disc CUE]
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT
from patches import mk_sample, to_rf5c164, VOICE_RATE, VOICE_RATES

CH, ON, RAM = 0x28085, 0x28085 + 0x86, 0x2810D   # the PCM chip in the core's save state: channels, play mask, sound RAM
P1, P2 = 0x2E188, 0x2E330
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big', signed=True)
LINES = ('GETOHERE.SVX', 'MALEHURT.SVX', 'GIRLHURT.SVX')
# (name, thrower's port, duelstate args, victim's scream)
CASES = (('Scorpion on Shadow', 0, ['--p1', '20', '--p2', '0', '--stage', '11'], 'GIRLHURT.SVX'),
         ('Reptile on Kano', 1, ['--p1', '18', '--p2', '0', '--p2-id', '26', '--stage', '1F'], 'MALEHURT.SVX'),
         ('Reptile on Sonya', 1, ['--p1', '16', '--p2', '0', '--p2-id', '26', '--stage', '1F'], 'GIRLHURT.SVX'))


def library():
    lib = []
    for name in LINES:
        rate, body = mk_sample(name)
        for hz in sorted({VOICE_RATE, *VOICE_RATES}):
            pcm = to_rf5c164(body, rate, hz, int(len(body) * hz / rate))
            q = next((i for i, v in enumerate(pcm) if (v & 0x7F) > 6), 0)
            lib.append((name, q, pcm[q:q + 256]))
    return lib


def who(lib, ram, start):
    for name, q, sm in lib:
        w = bytes(ram[start + q:start + q + len(sm)])
        if len(sm) >= 64 and sum(a == b for a, b in zip(w, sm)) >= 0.9 * len(sm):
            return name
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    cue = ap.parse_args().disc
    lib = library()
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        for name, port, args, scream in CASES:
            st = os.path.join(tmp, 'duel.state')
            subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', cue, *args,
                            '--out', st], check=True, capture_output=True)
            c = scd.Core(saves=os.path.join(tmp, 'saves'))
            c.load(cue)
            c.load_state(st)
            c.run(210)
            toward, back = ({'right'}, {'left'}) if port == 0 else ({'left'}, {'right'})
            for _ in range(300):                      # within the spear's reach
                r = c.prg_ram()
                if abs(W(r, P2 + 0x4E) - W(r, P1 + 0x4E)) < 110:
                    break
                c.buttons[port] = toward
                c.run(1)
            c.buttons[port] = set()
            c.run(20)
            victim = P2 if port == 0 else P1
            hp = W(c.prg_ram(), victim + 0x76)
            heard, mask = [], c.snapshot()[ON]
            for held, n in ((back, 3), (set(), 2), (back, 3), ({'x'}, 4), (set(), 150)):
                for _ in range(n):
                    c.buttons[port] = held
                    c.run(1)
                    s = c.snapshot()
                    for ch in range(8):
                        if s[ON] >> ch & 1 and not mask >> ch & 1:
                            start = int.from_bytes(s[CH + 16 * ch + 4:CH + 16 * ch + 8], 'little') >> 11
                            line = who(lib, s[RAM:RAM + 0x10000], start)
                            if line:
                                heard.append(line)
                    mask = s[ON]
            lost = hp - W(c.prg_ram(), victim + 0x76)
            ok = lost > 0 and heard == [scream, 'GETOHERE.SVX']
            bad += not ok
            print(f'  {name:20s} -{lost} hp, heard {" ".join(h[:-4] for h in heard) or "nothing"} -> {"ok" if ok else "FAIL"}')
    print(f'spear sounds: {"ok" if not bad else f"{bad} FAIL"}')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
