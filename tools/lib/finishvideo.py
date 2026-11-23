#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Record Scorpion's FINISH HIM -> fatality as a shareable clip (with sound).

From build/states/duel_shadow.state (tools/lib/duelstate.py --p2 0 --out
build/states/duel_shadow.state): the deciding round (one round won each) with
Shadow low on health. Scorpion spears her (GET OVER HERE), uppercuts her
while she's dazed, and keeps hitting until the winning blow leaves her dazed:
FINISH HIM. Then hold Block (Z), Up, Up: the fatality, the match ends,
final statistics.

    finishvideo.py [--out build/shots/scorpion_fatality.mp4] [--hp 20]
"""
import argparse, os, subprocess, sys, tempfile, wave
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scd import Core
from inputs import ROOT

P1, P2 = 0x2E188, 0x2E330
DIZZY = 0x1F


def w(r, a):
    return int.from_bytes(r[a:a + 2], 'big')


def x(r, o):
    return int.from_bytes(r[o + 0x4E:o + 0x50], 'big', signed=True)


def stats_screen(frame):
    """The blue FINAL STATISTICS screen: one bluish colour over most of it."""
    import numpy as np
    px = np.asarray(frame)[::4, ::4].reshape(-1, 3).astype(int)
    vals, counts = np.unique(px, axis=0, return_counts=True)
    top = vals[counts.argmax()]
    return counts.max() > 0.8 * len(px) and top[2] > top[0] + 30 and top[2] > top[1] + 30


class Rec:
    def __init__(self, core, out, scale=2):
        self.c, self.out = core, out
        h, wd = core.frame.shape[:2]
        self.shape = (h, wd)
        self.tmp = tempfile.mkdtemp()
        self.ff = subprocess.Popen(
            ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
             '-s', f'{wd}x{h}', '-r', f'{core.fps:.4f}', '-i', '-',
             '-vf', f'scale={wd * scale}:{h * scale}:flags=neighbor',
             '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', os.path.join(self.tmp, 'v.mp4')],
            stdin=subprocess.PIPE)
        self.wav = wave.open(os.path.join(self.tmp, 'a.wav'), 'wb')
        self.wav.setnchannels(2)
        self.wav.setsampwidth(2)
        self.wav.setframerate(int(round(core.sample_rate)))
        self.frames = 0
        self.step = core.run                   # (kept: a caller may route core.run through tick)
        self.stats_seen = False

    def run(self, n=1, held=()):
        self.c.buttons[0] = set(held)
        self.tick(n)
        self.c.buttons[0] = set()

    def tick(self, n=1):
        """n frames recorded, the pads as they are. Nothing more once the
        stats screen is up (a frame almost all one blue)."""
        for _ in range(n):
            self.step(1)
            if self.stats_seen or self.frames % 10 == 0 and stats_screen(self.c.frame):
                self.stats_seen = True
                self.c.audio.clear()
                continue
            if self.c.frame.shape[:2] == self.shape:
                self.ff.stdin.write(self.c.frame.tobytes())
            self.wav.writeframes(b''.join(self.c.audio))
            self.c.audio.clear()
            self.frames += 1

    def ram(self):
        return self.c.prg_ram()

    def close(self):
        self.ff.stdin.close()
        self.ff.wait()
        self.wav.close()
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', os.path.join(self.tmp, 'v.mp4'),
                        '-i', os.path.join(self.tmp, 'a.wav'), '-c:v', 'copy', '-c:a', 'aac',
                        '-b:a', '160k', '-shortest', self.out], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(ROOT, 'build', 'shots', 'scorpion_fatality.mp4'))
    ap.add_argument('--hp', type=int, default=20, help="Shadow's health when the clip starts")
    a = ap.parse_args()

    c = Core(audio=True, saves=os.path.join(ROOT, 'build', 'shots', 'record-saves'))
    c.load(os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    c.load_state(os.path.join(ROOT, 'build', 'states', 'duel_shadow.state'))
    c.run(40)
    c.poke_prg(0x31D26, (1).to_bytes(2, 'big'))       # one round each: this one decides it
    c.poke_prg(0x31D28, (1).to_bytes(2, 'big'))
    c.poke_prg(P2 + 0x76, a.hp.to_bytes(2, 'big'))
    c.audio.clear()
    r = Rec(c, a.out)
    r.run(30)
    m = r.ram()
    assert (w(m, 0x31D26), w(m, 0x31D28)) == (1, 1), 'round wins not set'

    def gap():
        m = r.ram()
        return x(m, P2) - x(m, P1)

    def wait_idle(limit=120):
        for _ in range(limit):
            if w(r.ram(), P1 + 0xBE) & 0x7FFF == 0:
                return
            r.run(1)

    def approach(to, limit=150):
        for _ in range(limit):
            if gap() <= to or finish_him():
                return
            r.run(1, ['right'])

    def finish_him():
        m = r.ram()
        return w(m, P2 + 0xBE) == DIZZY and w(m, P2 + 0x76) == 1

    # spear from range
    print('spear', gap(), flush=True)
    approach(120)
    r.run(12)
    for held, n in [(['left'], 3), ([], 3), (['left'], 2), (['left', 'x'], 4)]:
        r.run(n, held)
    for _ in range(150):
        r.run(1)
        if w(r.ram(), P2 + 0xBE) == DIZZY or finish_him():
            break
    wait_idle()
    # dazed: uppercut (down + HP)
    if not finish_him():
        print('uppercut', gap(), hex(w(r.ram(), P2 + 0xBE)), w(r.ram(), P2 + 0x76), flush=True)
        approach(55)
        for held, n in [(['down'], 8), (['down', 'y'], 4), (['down'], 6)]:
            r.run(n, held)
        r.run(90)
        wait_idle()
    # keep at it until the winning blow: FINISH HIM
    for _ in range(40):
        if finish_him():
            break
        approach(50)
        print('jab', gap(), hex(w(r.ram(), P2 + 0xBE)), w(r.ram(), P2 + 0x76), flush=True)
        r.run(4, ['x'])
        for _ in range(40):
            r.run(1)
            if finish_him():
                break
    assert finish_him(), 'no FINISH HIM'
    wait_idle()
    r.run(70)                                        # let FINISH HIM sink in
    # MK: hold Block, Up, Up
    for held, n in [(['z'], 8), (['z', 'up'], 5), (['z'], 5), (['z', 'up'], 5), (['z'], 8)]:
        r.run(n, held)
    for _ in range(900):
        r.run(1)
        if r.ram()[0x30AB7] & 3 == 3:
            break
    r.run(240)                                       # the stats screen
    r.close()
    print(f'{r.frames / c.fps:.1f}s -> {os.path.relpath(a.out, ROOT)}')


if __name__ == '__main__':
    main()
