#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""MK's throws beside ours, recorded with sound.

With each fighter's sprite box per frame (the VDP's sprite list by palette line),
the victim's path, the thrower's facing, and comparison sheets. Data in
build/shots/throws/data (not in git).

    throwcmp.py mk WHO            MK CD: WHO's throw on Sub-Zero (build/states/mk_WHO_2p.state;
                                  scorpion: mk_2p; sonya_leg: her leg grab)
    throwcmp.py ec WHO [--victim GRID] [--disc CUE]
                                  ours: a 2-player duel (made now), WHO throws (toward + Y;
                                  sonya_leg: down + X + A + Z) the victim (select-grid presses,
                                  default 1: Larcen)
    throwcmp.py path WHO          the victim's place (px from the thrower, px up) and the
                                  thrower's facing every 4 frames from the input, MK and ours
    throwcmp.py trace WHO [FROM,TO]  ours per frame: each fighter's state, frame, x, y, the
                                  victim's sprite box
    throwcmp.py sheet WHO [FROM,TO,STEP]   MK above ours, cropped round both, enlarged ->
                                  build/shots/throws/WHO.png
    throwcmp.py track WHO...      the 7-step track (patches.THROW_TRACK) and timing
                                  (mkinputs.THROW_SHAPE) from MK's recording: step 0 holds him
                                  from EC's first step (~6 frames in) to MK's lift, six even
                                  steps follow MK's path to his landing; the thrower turns by
                                  the side swap on the last step if MK's turns by then, else as
                                  he stands at MK's turn
    throwcmp.py video WHO...      side by side with sound, twice (MK's sound, then ours)
                                  -> build/shots/throws/throws.mp4
WHO: scorpion subzero raiden johnny liukang kano sonya sonya_leg, or FIGHTER_sweep (MK's back +
low kick, ours down + C) - the same tools for the sweep
"""
import argparse, ctypes, os, pickle, subprocess, sys, tempfile, wave
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
from inputs import ROOT

DATA = os.path.join(ROOT, 'build', 'shots', 'throws', 'data')
GRID = {'scorpion': 20, 'subzero': 15, 'raiden': 7, 'johnny': 19, 'liukang': 17, 'kano': 18,
        'sonya': 16, 'sonya_leg': 16}
P1, P2 = 0x2E188, 0x2E330
GROUND = {'mk': 227, 'ec': None}          # (ours: the victim's floor line at the start)
W = lambda r, a: int.from_bytes(r[a:a + 2], 'big', signed=True)
base = lambda who: who.split('_')[0]      # (scorpion_sweep, sonya_leg: the fighter)


def record(game, who, victim=1, disc=None, frames_after=200):
    import scd
    from vdp import VDPState
    c = scd.Core(audio=True, saves=os.path.join(ROOT, 'build', 'shots', 'capture-saves'))
    lines = (0, 1) if game == 'mk' else (3, 2)          # (thrower's palette line, victim's)
    out = {'frames': [], 'audio': [], 'boxes': [], 'ram': [], 'lines': lines, 'rate': None, 'mark': None}

    def boxes():
        n = c.lib.retro_serialize_size(); b = ctypes.create_string_buffer(n); c.lib.retro_serialize(b, n)
        v = VDPState(b.raw)
        d = {}
        for line in lines:
            ss = [s for s in v.sprites() if s['pal'] == line and s['y'] > 30]
            if ss:
                d[line] = (min(s['x'] for s in ss), min(s['y'] for s in ss),
                           max(s['x'] + 8 * s['w'] for s in ss), max(s['y'] + 8 * s['h'] for s in ss),
                           sum(s['vf'] for s in ss), sum(s['hf'] for s in ss), len(ss))
        return d

    def tick(btn=()):
        c.buttons[0] = set(btn)
        c.audio.clear()
        c.run(1)
        out['frames'].append(np.array(c.frame)); out['audio'].append(b''.join(c.audio)); out['boxes'].append(boxes())
        if game == 'ec':                    # (thrower, victim): state $BE, frame $1A, x, y
            r = c.prg_ram()
            out['ram'].append(tuple((W(r, f + 0xBE) & 0xFFFF, W(r, f + 0x1A) & 0xFFFF, W(r, f + 0x4E), W(r, f + 0x52))
                                    for f in (P1, P2)))

    if game == 'mk':
        from inputs import require
        c.load(require('mk_us').cue)
        c.load_state(os.path.join(ROOT, 'build', 'states', 'mk_2p.state' if base(who) == 'scorpion' else
                                  f'mk_{base(who)}_2p.state'))
        script = ([('right', 70), ('down+a+c+b', 6)] if who.endswith('_leg') else
                  [('right', int(os.environ.get('MKWALK', 60))), ('', 8), ('left', 4), (os.environ.get('MKSWEEP', 'left+c'), 4)] if who.endswith('_sweep') else
                  [('right', 60), ('right+z', 3), ('right', 3)])
        for btn, n in script:
            if out['mark'] is None and btn not in ('right', 'left', ''):
                out['mark'] = len(out['frames'])
            for _ in range(n):
                tick(tuple(x for x in btn.split('+') if x))
        for _ in range(frames_after):
            tick()
    else:
        disc = disc or os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue')
        st = os.path.join(tempfile.mkdtemp(), 'duel.state')
        subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', disc,
                        '--p1', str(GRID[base(who)]), '--p2', str(victim), '--out', st], check=True, capture_output=True)
        c.load(disc)
        c.load_state(st, check=False)
        os.remove(st)
        for _ in range(300):                                # walk in (bodies stop ~50-57 px apart)
            r = c.prg_ram()
            if abs(W(r, P2 + 0x4E) - W(r, P1 + 0x4E)) < 60:
                break
            tick(('right',) if W(r, P2 + 0x4E) > W(r, P1 + 0x4E) else ('left',))
        for _ in range(6):
            tick()
        r = c.prg_ram()
        fwd = 'right' if W(r, P2 + 0x4E) > W(r, P1 + 0x4E) else 'left'
        if who.endswith('_sweep'):                          # (crouched first: down + C at once kicks high)
            for _ in range(8):
                tick(('down',))
        out['mark'] = len(out['frames'])
        btn = (('down', 'x', 'a', 'z') if who.endswith('_leg') else ('down', 'c') if who.endswith('_sweep')
               else (fwd, 'y'))
        for _ in range(6):
            tick(btn)
        for _ in range(frames_after):
            tick()
    out['rate'] = c.sample_rate
    os.makedirs(DATA, exist_ok=True)
    pickle.dump(out, open(os.path.join(DATA, f'{game}_{who}.pkl'), 'wb'))
    print(game, who, len(out['frames']), 'frames, input at', out['mark'])


def load(game, who):
    return pickle.load(open(os.path.join(DATA, f'{game}_{who}.pkl'), 'rb'))


def path(who, to=180):
    for game in ('mk', 'ec'):
        d = load(game, who)
        th, vi = d['lines']; m = d['mark']
        v0 = d['boxes'][m].get(vi)
        ground = GROUND[game] or (v0[3] if v0 else 204)
        row = []
        for i in range(0, to, 4):
            b = d['boxes'][m + i]; t = b.get(th); v = b.get(vi)
            if not (t and v):
                row.append(f'{i}:-'); continue
            # MK draws its fighters facing right unflipped, EC's art (ours) the other way round
            flipped = t[5] * 2 > t[6]
            face = ('L' if flipped else 'R') if game == 'mk' else ('R' if flipped else 'L')
            row.append(f"{i}:{(v[0] + v[2]) // 2 - (t[0] + t[2]) // 2:+d}/{ground - v[3]}{face}")
        print(f'{game:2s} {who}:', ' '.join(row))


EC_START = 6                              # frames from the input to EC's first throw step


def mk_track(who):
    d = load('mk', who)
    th, vi = d['lines']; m = d['mark']
    pts = {}
    for i in range(0, len(d['boxes']) - m):
        b = d['boxes'][m + i]; t = b.get(th); v = b.get(vi)
        if t and v:
            pts[i] = ((v[0] + v[2]) // 2 - (t[0] + t[2]) // 2, max(0, 227 - v[3]), t[5] * 2 > t[6])
    at = lambda i: pts[min(pts, key=lambda k: abs(k - i))]
    lift = next(i for i in sorted(pts) if i >= (40 if who.endswith('_leg') else EC_START) and pts[i][1] >= 8)
    peak = max((i for i in pts if i >= lift), key=lambda i: pts[i][1])
    land = next(i for i in sorted(pts) if i > peak and pts[i][1] <= 6)
    turn = next(i for i in sorted(pts) if i > lift and pts[i][2])
    track = [((at(lift - 2)[0], 0), max(1, round((lift - EC_START) / 2)))]
    edges = [lift + round((land - lift) * k / 6) for k in range(7)]
    for k in range(1, 7):
        a, u = at(edges[k])[:2]
        track.append(((a, 0 if k == 6 else u), max(1, round((edges[k] - edges[k - 1]) / 2))))
    release = EC_START + 2 * sum(t for _, t in track)
    swap = turn <= release + 4
    return track, swap, turn


def track(who):
    tr, swap, turn = mk_track(who)
    print(f"    '{who}': {tr},")
    print(f"        # (mkinputs.THROW_SHAPE: ticks {tuple(t for _, t in tr)}, "
          f"{'swap on the last step' if swap else f'turns as he stands, MK frame {turn}'})")


def trace(who, frm=0, to=110):
    """Ours, per frame from the input: each fighter's state ($BE), frame ($1A), x, y."""
    d = load('ec', who)
    for i in range(frm, min(to, len(d['ram']) - d['mark'])):
        (ts, tf, tx, ty), (vs, vf, vx, vy) = d['ram'][d['mark'] + i]
        print(f'{i:3d}  thrower {ts:04X} {tf:04X} {tx:4d},{ty:3d}   victim {vs:04X} {vf:04X} {vx:4d},{vy:3d}  box {d["boxes"][d["mark"] + i].get(d["lines"][1])}')


def crop(d, i, w=240):
    from PIL import Image
    th, vi = d['lines']; b = d['boxes'][d['mark'] + i]; t = b.get(th); v = b.get(vi)
    xs = ([t[0], t[2]] if t else [160]) + ([v[0], v[2]] if v else [])
    cx = (min(xs) + max(xs)) // 2
    x0 = max(0, min(320 - w, cx - w // 2))
    return Image.fromarray(d['frames'][d['mark'] + i]).crop((x0, 50, x0 + w, 224))


def sheet(who, rng=(0, 128, 8)):
    from PIL import Image, ImageDraw
    A, B = load('mk', who), load('ec', who)
    idx = list(range(*rng))
    per = 8
    rows = (len(idx) + per - 1) // per
    o = Image.new('RGB', (240 * per, 174 * 2 * rows))
    for r, D in enumerate((A, B)):
        for k, i in enumerate(idx):
            im = crop(D, i); ImageDraw.Draw(im).text((2, 2), f"{'MK' if r == 0 else 'ours'} {i}", fill=(255, 255, 0))
            o.paste(im, ((k % per) * 240, (2 * (k // per) + r) * 174))
    out = os.path.join(ROOT, 'build', 'shots', 'throws', f'{who}.png')
    o.resize((o.width * 3 // 2, o.height * 3 // 2), Image.NEAREST).save(out)
    print(out)


def video(whos, before=20, n=170):
    from PIL import Image, ImageDraw
    segs = []
    for who in whos:
        A, B = load('mk', who), load('ec', who)
        a0, b0 = A['mark'] - before, B['mark'] - before
        k = min(len(A['frames']) - a0, len(B['frames']) - b0, n)
        segs.append((who, A['frames'][a0:a0 + k], B['frames'][b0:b0 + k], A['audio'][a0:a0 + k], B['audio'][b0:b0 + k], int(A['rate'])))
    h, w = segs[0][1][0].shape[:2]
    tmp = tempfile.mkdtemp()
    v = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{2 * w}x{h + 24}',
                          '-r', '60', '-i', '-', '-vf', 'scale=iw*2:ih*2:flags=neighbor', '-pix_fmt', 'yuv420p', '-c:v',
                          'libx264', '-crf', '18', f'{tmp}/v.mp4'], stdin=subprocess.PIPE)
    rate = segs[0][5]
    wav = wave.open(f'{tmp}/a.wav', 'wb'); wav.setnchannels(2); wav.setsampwidth(2); wav.setframerate(rate)
    for sound in ('MK CD', 'Eternal Kombat'):
        for who, fa, fb, aa, ab, _ in segs:
            for x, y in zip(fa, fb):
                img = Image.new('RGB', (2 * w, h + 24)); img.paste(Image.fromarray(x), (0, 0)); img.paste(Image.fromarray(y), (w, 0))
                dr = ImageDraw.Draw(img); dr.rectangle([w - 1, 0, w, h], fill=(255, 255, 255))
                dr.text((4, h + 2), f'MK CD: {who} (on Sub-Zero)', fill=(255, 255, 255))
                dr.text((w + 4, h + 2), 'Eternal Kombat (on Larcen)', fill=(255, 255, 255))
                dr.text((4, h + 12), f'sound: {sound}', fill=(255, 220, 80))
                v.stdin.write(np.asarray(img).tobytes())
            au = b''.join(aa if sound == 'MK CD' else ab)
            want = 4 * round(len(fa) * rate / 60)
            wav.writeframes((au + bytes(want))[:want])
    v.stdin.close(); v.wait(); wav.close()
    out = os.path.join(ROOT, 'build', 'shots', 'throws', 'throws.mp4')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', f'{tmp}/v.mp4', '-i', f'{tmp}/a.wav', '-c:v', 'copy',
                    '-c:a', 'aac', '-shortest', out], check=True)
    print(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=('mk', 'ec', 'path', 'sheet', 'video', 'track', 'trace'))
    ap.add_argument('who', nargs='+')
    ap.add_argument('--victim', type=int, default=1)
    ap.add_argument('--disc')
    a = ap.parse_args()
    if a.cmd in ('mk', 'ec'):
        for who in a.who:
            record(a.cmd, who, a.victim, a.disc)
    elif a.cmd == 'track':
        for who in a.who:
            track(who)
    elif a.cmd == 'trace':
        trace(a.who[0], *(int(x) for x in a.who[1].split(',')) if len(a.who) > 1 else ())
    elif a.cmd == 'path':
        for who in a.who:
            path(who)
    elif a.cmd == 'sheet':
        rng = tuple(int(x) for x in a.who[1].split(',')) if len(a.who) > 1 else (0, 128, 8)
        sheet(a.who[0], rng)
    else:
        video(a.who)


if __name__ == '__main__':
    main()
