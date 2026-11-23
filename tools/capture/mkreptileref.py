#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""MK CD's own Reptile fight, as the reference for ours.

MK CD's secret check ($21A44, sub-CPU PRG-RAM; called at $219A2 after a won
match) passes on the Pit ($8E8A = 3) with counter $8E9C = $12, the winner's
rounds = 2 and flag $7BA20 set; then $1508A sets $7BA28 = 1 (Reptile), the
stage to 6 (the Pit's bottom: the spiked floor) and loads player 2 as
fighter 4 (Scorpion's sprites in Reptile's green, PAC.PRG $1BF10; the health
bar still says SCORPION). Here the check is patched in RAM to pass
(ori #1,sr; rts) and Kano's first match is won quickly (the CPU kept at 1
health while Kano jabs), so the next fight is Reptile's.

    mkreptileref.py states   # build/states/mk_reptile_1p.state: Kano vs the CPU's
                             # Reptile, round 1 after FIGHT!
    mkreptileref.py video    # build/shots/reptile/mk_reptile.mp4: Kano still, then
                             # walking in and jabbing (the CPU's Reptile: his
                             # moves, his speed); data/frames in build/shots/reptile
"""
import os, subprocess, sys, tempfile
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
from inputs import ROOT

STATES = os.path.join(ROOT, 'build', 'states')
OUT = os.path.join(ROOT, 'build', 'shots', 'reptile')
CHECK = 0x21A44                   # MK's Reptile check: carry set = his fight next
REPTILE = 0x7BA28                 # 1 in his fight
STAGE = 0x8E8A                    # 3 the Pit, 6 its bottom (his)
P1_HP, P2_HP = 0x7D6C4, 0x7D7CA   # full 119


def session():
    import mkshangref
    return mkshangref.session()


def make_state():
    s = session()
    c = s.core
    W = lambda a: int.from_bytes(c.prg_ram()[a:a + 2], 'big')
    c.load_state(os.path.join(STATES, 'mk_select.state'))
    c.run(10)
    c.press(['start'])
    c.run(5 + 1200)                          # the ladder screen
    c.press(['start'])
    c.run(10)
    c.press(['a'])                           # Kano (the cursor's start)
    c.run(600)
    c.poke_prg(CHECK, bytes.fromhex('007c00014e75'))      # ori.w #1,sr ; rts
    for t in range(6000):                    # his first match, won fast
        c.poke_prg(P1_HP, (119).to_bytes(2, 'big'))
        if 0 < W(P2_HP) <= 119 and W(REPTILE) == 0:
            c.poke_prg(P2_HP, (1).to_bytes(2, 'big'))
        c.buttons[0] = {'right', 'a'} if (t // 4) % 2 else {'right'}
        c.run(1)
        if W(REPTILE) == 1:
            break
    else:
        raise SystemExit('no Reptile fight')
    c.buttons[0] = set()
    for t in range(3000):                    # his fight loads: health filled, then FIGHT!
        c.run(1)
        if W(P2_HP) == 119 and W(P1_HP) == 119 and s.frame(s.vdp()).any():
            break
    c.run(250)
    assert W(STAGE) == 6 and W(REPTILE) == 1, (W(STAGE), W(REPTILE))
    c.save_state(os.path.join(STATES, 'mk_reptile_1p.state'))
    print('mk_reptile_1p.state: Kano vs Reptile (MK CD, the Pit\'s bottom)')


def video(seconds_still=40, seconds_play=40):
    import scd
    from inputs import require
    os.makedirs(OUT, exist_ok=True)
    c = scd.Core(audio=True, saves=os.path.join(ROOT, 'build', 'shots', 'capture-saves'))
    c.load(require('mk_us').cue)
    c.load_state(os.path.join(STATES, 'mk_reptile_1p.state'))
    tmp = tempfile.mkdtemp()
    c.run(1)
    h, w = np.array(c.frame).shape[:2]
    v = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{w}x{h}',
                          '-r', '60', '-i', '-', '-vf', 'scale=iw*2:ih*2:flags=neighbor', '-pix_fmt', 'yuv420p',
                          '-c:v', 'libx264', '-crf', '18', f'{tmp}/v.mp4'], stdin=subprocess.PIPE)
    import wave
    wav = wave.open(f'{tmp}/a.wav', 'wb'); wav.setnchannels(2); wav.setsampwidth(2); wav.setframerate(int(c.sample_rate))
    for t in range(60 * (seconds_still + seconds_play)):
        if t >= 60 * seconds_still:          # then Kano walks in and jabs
            c.buttons[0] = {'right', 'a'} if (t // 6) % 3 == 0 else {'right'}
        c.audio.clear()
        c.run(1)
        v.stdin.write(np.asarray(c.frame).tobytes())
        wav.writeframes(b''.join(c.audio))
    v.stdin.close(); v.wait(); wav.close()
    out = os.path.join(OUT, 'mk_reptile.mp4')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', f'{tmp}/v.mp4', '-i', f'{tmp}/a.wav', '-c:v', 'copy',
                    '-c:a', 'aac', '-shortest', out], check=True)
    print(out)


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'states':
        make_state()
    elif cmd == 'video':
        video()
    else:
        print(__doc__)
