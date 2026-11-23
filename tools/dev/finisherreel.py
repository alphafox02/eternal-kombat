#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compilation videos of the finishers, MK against EC and back, each clip after a title card.

    finisherreel.py mk_on_ec [--jobs 3] [--only scorpion,raiden]
        every MK fighter's fatality on every EC fighter (tools/lib/mkfatalitycheck.py)
        -> build/shots/reel_<fighter>_fatalities.mp4, one per MK fighter
    finisherreel.py mk_on_mk
        every MK fatality on the other MK fighters -> build/shots/reel_mk_on_mk.mp4
    finisherreel.py vendettas
        each EC fighter's Vendetta on an EC fighter (as the stock game shows
        it), then on MK fighters (tools/lib/vendettacheck.py --keep-block: what
        the build allows) -> build/shots/reel_vendettas.mp4
    finisherreel.py stages
        not made yet (the theater's finishers: tools/lib/usherdeath.py, overkillvideo.py)

Clips are kept in build/shots/reel_clips/ (a clip already there is reused: delete it
to re-record); a clip whose run failed gets a card saying so.
"""
import argparse, os, shutil, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
from inputs import ROOT

PY = [sys.executable, '-P', '-E']
T = lambda name: next(p for p in (os.path.join(ROOT, 'tools', d, name) for d in ('lib', 'checks', 'dev'))
                      if os.path.exists(p))
CLIPS = os.path.join(ROOT, 'build', 'shots', 'reel_clips')
# select-grid presses -> name (tools/lib/duelstate.py)
EC = {0: 'Shadow', 1: 'Larcen', 2: 'R.A.X.', 3: 'Slash', 4: 'Trident', 5: 'Midknight', 6: 'Xavier',
      8: 'Blade', 9: 'Jetta', 10: 'Riptide', 11: 'Ramses III', 12: 'Raven', 13: 'Dawson'}
MK = {20: 'Scorpion', 7: 'Raiden', 15: 'Sub-Zero', 16: 'Sonya', 17: 'Liu Kang', 18: 'Kano', 19: 'Johnny Cage'}
KEY = {20: 'scorpion', 7: 'raiden', 15: 'subzero', 16: 'sonya', 17: 'liukang', 18: 'kano', 19: 'johnny'}
FATALITY = {'scorpion': 'fire breath', 'raiden': 'electrocution', 'subzero': 'spine rip', 'sonya': 'kiss of death',
            'liukang': 'uppercut', 'kano': 'heart rip', 'johnny': 'decapitation uppercut'}


def fatality_clip(who, loser):
    """(title, clip path, command) for his fatality on the fighter at loser presses."""
    out = os.path.join(CLIPS, f'fatality_{who}_on_{loser}.mp4')
    name = MK[next(g for g, k in KEY.items() if k == who)]
    victim = EC.get(loser) or MK[loser]
    made = os.path.join(ROOT, 'build', 'shots', f'fatality_{who}_on_{loser}.mp4')
    cmd = PY + [T('mkfatalitycheck.py'), who, '--p2', str(loser), '--video']
    return f"{name}'s {FATALITY[who]}\non {victim}", out, cmd, made


# px apart for the input: each Vendetta has its range (40 for most; measured)
VENDETTA_GAP = {10: 90, 12: 130, 13: 130, 3: 70, 6: 70}   # Riptide, Raven, Dawson; Slash, Xavier (on MK fighters)
# a second MK loser for a Vendetta: Blade on Sonya too (his grab hung on six MK fighters until 2026-11-16)
ALSO_ON_MK = {8: 16}
# Vendettas not allowed on MK losers (never seen on them): shown once more, allowed for the clip
UNTESTED_ON_MK = ()                   # (none now: Trident's and Midknight's allowed since 2026-11-16)


def vendetta_clip(winner, loser, keep=True):
    out = os.path.join(CLIPS, f'vendetta_{winner}_on_{loser}{"" if keep else "_allowed"}.mp4')
    base = VENDETTA_GAP.get(winner, 40)
    cmd = [PY + [T('vendettacheck.py'), str(winner), str(loser), '--video', out, '--gap', str(g), '--frames', '1800']
           + (['--keep-block'] if keep else []) for g in (base, base + 30, base + 60, max(20, base - 20))]
    return (f"{EC[winner]}'s Vendetta\non {EC.get(loser) or MK[loser]}"
            + ('' if keep else '\n(allowed for this test: the game blocks it on him)')), out, cmd, None


def record(job):
    title, out, cmd, made = job
    log = out + '.log'
    disc = os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat (Track 01).bin')
    if os.path.exists(out) and os.path.exists(log) and os.path.getmtime(log) > os.path.getmtime(disc):
        return title, out, note(open(log).read())         # (a clip of an older build is made again)
    for one in (cmd if isinstance(cmd[0], list) else [cmd]):     # (Vendettas: a few distances, the first that plays)
        r = subprocess.run(one, capture_output=True, text=True, cwd=ROOT)
        if r.returncode == 0 and '$1CD4 = 0' not in r.stdout:
            break
    open(log, 'w').write(r.stdout + r.stderr)
    if made and os.path.exists(made):
        shutil.move(made, out)
    for strip in (made and made[:-4] + '.png', ):          # (the run's frame strip: not kept)
        if strip and os.path.exists(strip):
            os.remove(strip)
    for f in os.listdir(os.path.join(ROOT, 'build', 'shots')):        # (vendettacheck's strips)
        if f.startswith('vendetta_') and f.endswith('.png'):
            os.remove(os.path.join(ROOT, 'build', 'shots', f))
    tail = (r.stdout + r.stderr).strip().splitlines()
    verdict = next((l for l in reversed(tail) if '->' in l or 'finisher type' in l), tail[-1] if tail else '')
    ok = r.returncode == 0 and os.path.exists(out)
    print(f'{"ok  " if ok else "FAIL"} {title.replace(chr(10), " ")}: {verdict[:90]}', flush=True)
    return title, out if ok else None, note(r.stdout + r.stderr) if ok else verdict


def note(log):
    """A line for the card when the run went through but the finisher didn't happen."""
    if 'finisher type $1CD4 = 0' in log:
        return '(no finisher happened: the input or the setup missed)'
    if 'FROZE' in log:
        return '(the game froze)'
    return ''


def card(text, out, secs=2.0, size=(640, 448)):
    """A title card clip (silent) matching the clips' format."""
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new('RGB', size, (8, 8, 16))
    d = ImageDraw.Draw(im)
    def font(size):
        try:
            return ImageFont.truetype('DejaVuSans-Bold.ttf', size)
        except OSError:
            return ImageFont.load_default()
    lines = text.split('\n')
    fonts = [font(30 if k < 2 else 18) for k in range(len(lines))]
    hs = [d.textbbox((0, 0), l, font=f) for l, f in zip(lines, fonts)]
    y = (size[1] - sum(b[3] - b[1] + 14 for b in hs)) // 2
    for k, (l, f, b) in enumerate(zip(lines, fonts, hs)):
        d.text(((size[0] - (b[2] - b[0])) // 2, y), l, font=f,
               fill=(230, 200, 60) if k == 0 else (230, 230, 230) if k == 1 else (240, 120, 100))
        y += b[3] - b[1] + 14
    png = out + '.png'
    im.save(png)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-loop', '1', '-t', str(secs), '-i', png,
                    '-f', 'lavfi', '-t', str(secs), '-i', 'anullsrc=r=44100:cl=stereo',
                    '-r', '60', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18',
                    '-c:a', 'aac', '-b:a', '160k', '-shortest', out], check=True)
    os.remove(png)


def join(parts, out):
    """Concatenate clips (re-encoded to one format: 640x448, 60 fps, 44.1 kHz)."""
    tmp = out + '.parts'
    os.makedirs(tmp, exist_ok=True)
    norm = []
    for i, p in enumerate(parts):
        n = os.path.join(tmp, f'{i:03d}.mp4')
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', p, '-vf', 'scale=640:448:flags=neighbor,fps=60',
                        '-af', 'aresample=44100', '-ac', '2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '20',
                        '-c:a', 'aac', '-b:a', '160k', n], check=True)
        norm.append(n)
    lst = os.path.join(tmp, 'list.txt')
    open(lst, 'w').write(''.join(f"file '{n}'\n" for n in norm))
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', lst, '-c', 'copy', out],
                   check=True)
    shutil.rmtree(tmp)


def reel(jobs, out, heading, n_jobs):
    os.makedirs(CLIPS, exist_ok=True)
    with ThreadPoolExecutor(n_jobs) as ex:
        done = list(ex.map(record, jobs))
    parts, tmpcards = [], []
    c0 = out + '.title.mp4'
    card(heading, c0, 3)
    parts.append(c0)
    tmpcards.append(c0)
    for k, (title, clip, verdict) in enumerate(done):
        c = f'{out}.card{k:03d}.mp4'
        card(title + (f'\n{verdict}' if verdict else '') if clip else f'{title}\n(this one failed: {verdict[:40]})', c)
        parts.append(c)
        tmpcards.append(c)
        if clip:
            parts.append(clip)
    join(parts, out)
    for c in tmpcards:
        os.remove(c)
    bad = [t for t, c, _ in done if not c]
    print(f'{os.path.relpath(out, ROOT)}: {len(done) - len(bad)} of {len(done)} clips'
          + (f'; failed: {", ".join(t.replace(chr(10), " ") for t in bad)}' if bad else ''))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('section', choices=('mk_on_ec', 'mk_on_mk', 'vendettas', 'stages'))
    ap.add_argument('--jobs', type=int, default=3)
    ap.add_argument('--only', help='MK fighters (keys, comma-separated) for mk_on_ec')
    a = ap.parse_args()
    shots = os.path.join(ROOT, 'build', 'shots')
    if a.section == 'mk_on_ec':
        whos = a.only.split(',') if a.only else list(KEY.values())
        for who in whos:
            name = MK[next(g for g, k in KEY.items() if k == who)]
            reel([fatality_clip(who, l) for l in EC], os.path.join(shots, f'reel_{who}_fatalities.mp4'),
                 f"{name}'s {FATALITY[who]}\non every EC fighter", a.jobs)
    elif a.section == 'mk_on_mk':
        jobs = [fatality_clip(KEY[w], l) for w in MK for l in MK if l != w]
        reel(jobs, os.path.join(shots, 'reel_mk_on_mk.mp4'), 'MK fatalities\non MK fighters', a.jobs)
    elif a.section == 'vendettas':
        mk = list(MK)
        jobs = []
        for k, w in enumerate(EC):
            ref = next(l for l in EC if l != w)                # (an EC victim: the stock look)
            jobs += [vendetta_clip(w, ref), vendetta_clip(w, mk[k % len(mk)])]
            if w in ALSO_ON_MK:
                jobs.append(vendetta_clip(w, ALSO_ON_MK[w]))
            if w in UNTESTED_ON_MK:
                jobs.append(vendetta_clip(w, mk[k % len(mk)], keep=False))
        reel(jobs, os.path.join(shots, 'reel_vendettas.mp4'), 'EC Vendettas\non EC, then on MK fighters', a.jobs)
    else:
        sys.exit('stages: not yet (the theater: tools/lib/usherdeath.py, tools/lib/overkillvideo.py)')


if __name__ == '__main__':
    main()
