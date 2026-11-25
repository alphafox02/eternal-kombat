#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""MK's spear beside ours, recorded with sound, from the same distances.

Scorpion (player 1) at Sub-Zero on the Courtyard in both: MK CD from build/states/mk_2p.state, ours a
2-player duel made now (duelstate.py --mk-stage courtyard). The gap is the distance between the two
fighters' sprite centres on the screen, set before the throw (MK: by walking, ours: placed). Data in
build/shots/spear/data (not in git).

    spearcmp.py mk GAP...           MK CD: the spear (back, back + A) from about GAP px
    spearcmp.py ec GAP... [--disc CUE]   ours (back, back + X)
    spearcmp.py sheet GAP [FROM,TO,STEP]   MK above ours, every STEP frames from the press, enlarged
                                    -> build/shots/spear/GAP.png
    spearcmp.py video GAP...        side by side: at speed with MK's sound, again with ours, then at
                                    half speed -> build/shots/spear/spear.mp4
"""
import argparse, ctypes, os, pickle, subprocess, sys, tempfile, wave
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
from inputs import ROOT

OUT = os.path.join(ROOT, 'build', 'shots', 'spear')
DATA = os.path.join(OUT, 'data')
P1, P2 = 0x2E188, 0x2E330
W = lambda r, a: int.from_bytes(r[a:a + 2], 'big', signed=True)
BEFORE, AFTER = 20, 170
LINES = {'mk': (0, 1), 'ec': (3, 2)}           # (the fighters' palette lines: Scorpion's, Sub-Zero's)
THROW = {'mk': [('left', 3), ('', 3), ('left', 3), ('a', 4)],
         'ec': [('left', 3), ('', 2), ('left', 3), ('x', 4)]}


def record(game, gap, disc=None):
    import scd
    from vdp import VDPState
    c = scd.Core(audio=True, saves=os.path.join(ROOT, 'build', 'shots', 'capture-saves'))
    out = {'frames': [], 'audio': [], 'mark': None, 'gap': None, 'pos': []}

    def centres():
        n = c.lib.retro_serialize_size(); b = ctypes.create_string_buffer(n); c.lib.retro_serialize(b, n)
        d = []
        for line in LINES[game]:
            ss = [s for s in VDPState(b.raw).sprites() if s['pal'] == line and s['y'] > 30]
            if len(ss) > 3:
                d.append((min(s['x'] for s in ss) + max(s['x'] + 8 * s['w'] for s in ss)) / 2)
            else:
                d.append(None)
        return d

    def now():
        x = centres()
        return abs(x[1] - x[0]) if None not in x else None

    def tick(p1=(), p2=(), keep=True):
        c.buttons[0], c.buttons[1] = set(p1), set(p2)
        c.audio.clear()
        c.run(1)
        if keep:
            out['frames'].append(np.array(c.frame)); out['audio'].append(b''.join(c.audio)); out['pos'].append(centres())

    if game == 'mk':
        from inputs import require
        c.load(require('mk_us').cue)
        c.load_state(os.path.join(ROOT, 'build', 'states', 'mk_2p.state'))
        c.run(5)
        for _ in range(240):                    # walk: Scorpion in, or Sub-Zero back
            g = now()
            if g is None or abs(g - gap) < 3:
                break
            tick(('right',) if g > gap else (), () if g > gap else ('right',), keep=False)
    else:
        disc = disc or os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue')
        st = os.path.join(tempfile.mkdtemp(dir=os.path.join(ROOT, 'build', 'tmp')), 'duel.state')
        subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', disc,
                        '--p1', '20', '--p2', '15', '--mk-stage', 'courtyard', '--out', st], check=True, capture_output=True)
        c.load(disc)
        c.load_state(st, check=False)
        os.remove(st)
        c.run(30)
        for _ in range(3):                      # place Sub-Zero, then correct by the sprites' gap
            c.run(8)
            g = now()
            if g is None or abs(g - gap) < 3:
                break
            r = c.prg_ram()
            for o in (0xB2, 0x4E):
                c.poke_prg(P2 + o, ((W(r, P2 + o) + round(gap - g)) & 0xFFFF).to_bytes(2, 'big'))
    for _ in range(12):
        tick(keep=False)
    out['gap'] = now()
    for _ in range(BEFORE):
        tick()
    out['mark'] = len(out['frames'])
    for btn, n in THROW[game]:
        for _ in range(n):
            tick([x for x in btn.split('+') if x])
    for _ in range(AFTER):
        tick()
    out['rate'] = c.sample_rate
    os.makedirs(DATA, exist_ok=True)
    pickle.dump(out, open(os.path.join(DATA, f'{game}_{gap}.pkl'), 'wb'))
    print(game, gap, f'(on the screen {out["gap"]:.0f} px)', len(out['frames']), 'frames')


def load(game, gap):
    return pickle.load(open(os.path.join(DATA, f'{game}_{gap}.pkl'), 'rb'))


def sheet(gap, rng=(0, 96, 4)):
    from PIL import Image, ImageDraw
    A, B = load('mk', gap), load('ec', gap)
    idx = list(range(*rng))
    per = 6
    rows = (len(idx) + per - 1) // per
    o = Image.new('RGB', (320 * per, 150 * 2 * rows))
    for r, D in enumerate((A, B)):
        for k, i in enumerate(idx):
            im = Image.fromarray(D['frames'][D['mark'] + i]).crop((0, 74, 320, 224))
            ImageDraw.Draw(im).text((2, 2), f"{'MK' if r == 0 else 'ours'} {i}", fill=(255, 255, 0))
            o.paste(im, ((k % per) * 320, (2 * (k // per) + r) * 150))
    out = os.path.join(OUT, f'{gap}.png')
    o.save(out)
    print(out)


def video(gaps):
    from PIL import Image, ImageDraw
    segs = [(g, load('mk', g), load('ec', g)) for g in gaps]
    h, w = 224, 320
    tmp = tempfile.mkdtemp(dir=os.path.join(ROOT, 'build', 'tmp'))
    v = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{2 * w}x{h + 24}',
                          '-r', '60', '-i', '-', '-vf', 'scale=iw*2:ih*2:flags=neighbor', '-pix_fmt', 'yuv420p', '-c:v',
                          'libx264', '-crf', '18', f'{tmp}/v.mp4'], stdin=subprocess.PIPE)
    rate = int(segs[0][1]['rate'])
    wav = wave.open(f'{tmp}/a.wav', 'wb'); wav.setnchannels(2); wav.setsampwidth(2); wav.setframerate(rate)
    for sound, rep in (('MK CD', 1), ('Eternal Kombat', 1), ('none (half speed)', 2)):
        for g, A, B in segs:
            k = min(len(A['frames']), len(B['frames']))
            for i in range(k):
                img = Image.new('RGB', (2 * w, h + 24))
                img.paste(Image.fromarray(A['frames'][i]), (0, 0)); img.paste(Image.fromarray(B['frames'][i]), (w, 0))
                dr = ImageDraw.Draw(img); dr.rectangle([w - 1, 0, w, h], fill=(255, 255, 255))
                t = i - A['mark']
                dr.text((4, h + 2), f'MK CD   {A["gap"]:.0f} px apart', fill=(255, 255, 255))
                dr.text((w + 4, h + 2), f'Eternal Kombat   {B["gap"]:.0f} px apart', fill=(255, 255, 255))
                dr.text((4, h + 12), f'sound: {sound}   frame {t:+d} from the press', fill=(255, 220, 80))
                for _ in range(rep):
                    v.stdin.write(np.asarray(img).tobytes())
            want = 4 * round(k * rep * rate / 60)
            au = b''.join(A['audio'][:k] if sound == 'MK CD' else B['audio'][:k]) if rep == 1 else b''
            wav.writeframes((au + bytes(want))[:want])
    v.stdin.close(); v.wait(); wav.close()
    out = os.path.join(OUT, 'spear.mp4')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', f'{tmp}/v.mp4', '-i', f'{tmp}/a.wav', '-c:v', 'copy',
                    '-c:a', 'aac', '-shortest', out], check=True)
    print(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=('mk', 'ec', 'sheet', 'video'))
    ap.add_argument('args', nargs='+')
    ap.add_argument('--disc')
    a = ap.parse_args()
    if a.cmd in ('mk', 'ec'):
        for g in a.args:
            record(a.cmd, int(g), a.disc)
    elif a.cmd == 'sheet':
        sheet(int(a.args[0]), tuple(int(x) for x in a.args[1].split(',')) if len(a.args) > 1 else (0, 96, 4))
    else:
        video([int(g) for g in a.args])


if __name__ == '__main__':
    main()
