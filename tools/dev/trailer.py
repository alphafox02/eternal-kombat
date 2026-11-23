#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""A short trailer of the built disc, cut to MK CD's Mortal Monday music (MK track 20, the
menus' song: cdaudio.menu_song): from black into the title screen, the select screen, fights,
specials, fatalities, stage finishers and the Pit, back to the title, to black. The game's own
sound is left out; the music plays over it all.

    trailer.py record [--jobs 6]   every clip, recorded from build/Eternal Kombat with the
                                   project's recorders -> build/shots/trailer/clips/ (a clip
                                   already there is kept: delete it to record it again)
    trailer.py cut                 the clips cut together (CUTS) -> build/shots/trailer/eternal_kombat_trailer.mp4
    trailer.py sheet CLIP          a frame every half second of a clip, numbered (for choosing CUTS)

Needs ffmpeg, requirements-dev.txt and the BIOS (the emulator), and build/states/menu.state
(tools/play.py test). Takes about 15 minutes to record.
"""
import argparse, os, shutil, subprocess, sys, tempfile, wave
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
from inputs import ROOT

OUT = os.path.join(ROOT, 'build', 'shots', 'trailer')
CLIPS = os.path.join(OUT, 'clips')
DISC = os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue')
PY = [sys.executable, '-P']
T = lambda d, name: os.path.join(ROOT, 'tools', d, name)
W, H = 640, 448                 # 2x the Genesis' 320 x 224 (sharp pixels, and under GitHub's 10 MB for a video)
CRF = 25
FADE = 1.5                      # s: in from black, out to black

# select-grid presses (tools/lib/duelstate.py): MK's and some of EC's
MK = {'scorpion': 20, 'raiden': 7, 'subzero': 15, 'sonya': 16, 'liukang': 17, 'kano': 18, 'johnny': 19}
# a stage per showcase (stage modes, tools/lib/duelstate.py --stage)
SHOWCASE_STAGE = {'raiden': '21', 'subzero': '1A', 'liukang': '20', 'johnny': '1B', 'kano': '17', 'sonya': '19'}
FATALITIES = (('scorpion', 4), ('subzero', 1), ('raiden', 5), ('kano', 6), ('johnny', 8), ('liukang', 3),
              ('sonya', 10))
STAGES = (('dawson_sudden_kano', '21', 18, 13, 'sudden'), ('slash_overkill_johnny', '1A', 19, 3, 'overkill'),
          ('rax_overkill_raiden', '17', 7, 2, 'overkill'), ('shadow_overkill_sonya', '19', 16, 0, 'overkill'),
          ('jetta_sudden_scorpion', '20', 20, 9, 'sudden'))
VENDETTAS = (('dawson_on_subzero', 13, 15, 130),)

# The cut, in order: (clip, from s, length). The music (MK track 20) runs under it from MUSIC_FROM:
# the title until the song's first hit (15.8 s into it), the select and versus screens until its
# drums come in (21.07 s), then cuts a whole number of beats long (BEAT: 136 to the minute).
MUSIC_FROM = 12.0
BEAT = 0.4415
B = lambda n: n * BEAT
CUTS = (('title', 0.0, 3.8), ('select', 11.0, 2.6), ('select', 20.3, 21.07 - 15.8 - 2.6),
        # the specials, 4-5 beats each
        ('fight_scorpion', 2.4, B(4)), ('moves_raiden', 22.0, B(4)), ('moves_subzero', 18.2, B(5)),
        ('moves_kano', 22.1, B(4)), ('moves_liukang', 22.2, B(4)), ('moves_johnny', 9.85, B(4)),
        ('moves_sonya', 10.0, B(4)),
        # the finishers
        ('fatality_scorpion', 2.3, B(8)), ('stage_rax_overkill_raiden', 6.3, B(6)),
        ('fatality_subzero', 10.5, B(6)), ('pit_liukang', 8.4, B(8)),
        ('vendetta_dawson_on_subzero', 5.0, B(6)), ('fatality_kano', 10.5, B(6)),
        ('stage_shadow_overkill_sonya', 4.5, B(10)), ('fatality_raiden', 10.8, B(8)),
        ('stage_slash_overkill_johnny', 13.1, B(6)), ('stage_jetta_sudden_scorpion', 14.7, B(6)),
        ('fatality_sonya', 11.6, B(6)), ('fatality_johnny', 10.8, B(6)),
        ('stage_dawson_sudden_kano', 39.9, B(6)),
        ('title', 0.0, B(8)))


def jobs():
    """(clip name, [commands]) for every clip."""
    j = [('title', [PY + [__file__, '_title', os.path.join(CLIPS, 'title.mp4')]]),
         ('select', [PY + [__file__, '_select', os.path.join(CLIPS, 'select.mp4')]]),
         ('fight_scorpion', [PY + [T('dev', 'record.py'), '--state', 'scorpion_fight', '--bot', 'scorpion',
                                    '--seconds', '25', '--out', os.path.join(CLIPS, 'fight_scorpion.mp4')]])]
    for who, stage in SHOWCASE_STAGE.items():
        st = os.path.join(OUT, f'duel_{who}.state')
        j.append((f'moves_{who}', [
            PY + [T('lib', 'duelstate.py'), '--p1', str(MK[who]), '--p2', '0', '--stage', stage, '--out', st],
            PY + [T('dev', 'showcase.py'), '--fighter', who, '--state', st,
                  '--out', os.path.join(CLIPS, f'moves_{who}.mp4')]]))
    for who, p2 in FATALITIES:
        made = os.path.join(ROOT, 'build', 'shots', f'fatality_{who}_on_{p2}.mp4')
        j.append((f'fatality_{who}', [PY + [T('lib', 'mkfatalitycheck.py'), who, '--p2', str(p2), '--video'],
                                      ['mv', made, os.path.join(CLIPS, f'fatality_{who}.mp4')],
                                      ['rm', '-f', made[:-4] + '.png']]))
    for name, stage, loser, winner, kind in STAGES:
        j.append((f'stage_{name}', [PY + [T('dev', 'stagevideo.py'), stage, str(loser), str(winner), kind,
                                          '--tail', '900', '--out', os.path.join(CLIPS, f'stage_{name}.mp4')]]))
    for name, winner, loser, gap in VENDETTAS:
        j.append((f'vendetta_{name}', [PY + [T('lib', 'vendettacheck.py'), str(winner), str(loser), '--keep-block',
                                             '--gap', str(gap), '--frames', '1800',
                                             '--video', os.path.join(CLIPS, f'vendetta_{name}.mp4')]]))
    pit = os.path.join(OUT, 'duel_pit.state')
    j.append(('pit_liukang', [PY + [T('lib', 'duelstate.py'), '--p1', str(MK['liukang']), '--p2', '2',
                                    '--stage', '1F', '--out', pit],
                              PY + [T('dev', 'pitvideo.py'), '--state', pit,
                                    '--out', os.path.join(CLIPS, 'pit_liukang.mp4')]]))
    return j


def run_job(job):
    name, cmds = job
    if os.path.exists(os.path.join(CLIPS, name + '.mp4')):
        return f'kept     {name}'
    log = os.path.join(OUT, 'logs', name + '.log')
    with open(log, 'w') as f:
        for cmd in cmds:
            if subprocess.run(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT).returncode:
                return f'FAILED   {name} ({log})'
    ok = os.path.exists(os.path.join(CLIPS, name + '.mp4'))
    return f'{"recorded" if ok else "FAILED  "} {name}' + ('' if ok else f' ({log})')


def recorder(out):
    from scd import Core
    from finishvideo import Rec
    c = Core(audio=True, saves=os.path.join(OUT, 'saves'))
    c.load(DISC)
    c.load_state(os.path.join(ROOT, 'build', 'states', 'menu.state'))
    c.run(1)
    c.audio.clear()
    return c, Rec(c, out)


def title(out):
    """The title screen as the game shows it, 8 s."""
    c, r = recorder(out)
    r.run(8 * 60)
    r.close()


def select(out):
    """Title -> main menu -> Duel -> the select screen: player 2 joins, player 1's cursor runs
    along the grid to Scorpion, player 2's to Sub-Zero, both pick, the versus screen."""
    c, r = recorder(out)

    def press(button, port=0, after=20):
        c.buttons[port] = {button}
        r.tick(3)
        c.buttons[port] = set()
        r.tick(after)
    press('start', after=240)
    press('down')
    press('start', after=240)
    press('start', port=1, after=40)
    for _ in range(MK['scorpion']):
        press('right', after=12)
    press('start', after=40)
    for _ in range(MK['subzero']):
        press('right', port=1, after=12)
    press('start', port=1, after=300)
    r.close()


def cut():
    """CUTS over the music, from black and back to black."""
    import cdaudio
    if not CUTS:
        sys.exit('no CUTS yet: record, then choose them (trailer.py sheet CLIP)')
    from inputs import scan
    found, _, _ = scan()
    song = cdaudio.menu_song(found['mk_us'].cue)
    total = sum(d for _, _, d in CUTS)
    tmp = tempfile.mkdtemp(dir=os.path.join(ROOT, 'build', 'tmp'))
    wav = os.path.join(tmp, 'song.wav')
    with wave.open(wav, 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(44100)
        a = int(MUSIC_FROM * 44100) * 4
        w.writeframes(song[a:a + int((total + 1) * 44100) * 4])
    ins, parts = [], []
    for i, (clip, start, dur) in enumerate(CUTS):
        ins += ['-ss', f'{start:.3f}', '-t', f'{dur:.3f}', '-i', os.path.join(CLIPS, clip + '.mp4')]
        parts.append(f'[{i}:v]fps=60,scale={W}:{H}:flags=neighbor,setsar=1,settb=1/60,setpts=PTS-STARTPTS[v{i}]')
    n = len(CUTS)
    graph = ';'.join(parts) + ';' + ''.join(f'[v{i}]' for i in range(n)) + f'concat=n={n}:v=1:a=0[cat];' \
        f'[cat]fade=t=in:d={FADE},fade=t=out:st={total - FADE:.3f}:d={FADE}[v];' \
        f'[{n}:a]atrim=0:{total:.3f},volume=0.89,afade=t=in:d=0.5,afade=t=out:st={total - FADE * 1.5:.3f}:d={FADE * 1.5}[a]'
    out = os.path.join(OUT, 'eternal_kombat_trailer.mp4')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error'] + ins + ['-i', wav, '-filter_complex', graph,
                    '-map', '[v]', '-map', '[a]', '-c:v', 'libx264', '-preset', 'slow', '-crf', str(CRF), '-tune', 'animation',
                    '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k', '-movflags', '+faststart', out],
                   check=True)
    shutil.rmtree(tmp)
    print(f'{os.path.relpath(out, ROOT)}: {total:.1f} s, {os.path.getsize(out) / 1e6:.1f} MB')


def sheet(clip):
    """Every half second of a clip, numbered with its time -> build/shots/trailer/sheet_<clip>.png."""
    path = os.path.join(CLIPS, clip + '.mp4')
    out = os.path.join(OUT, f'sheet_{clip}.png')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', path, '-vf',
                    "fps=2,scale=320:224,drawtext=text='%{pts\\:hms}':x=4:y=4:fontcolor=yellow:fontsize=18:"
                    "box=1:boxcolor=black,tile=6x8", '-frames:v', '1', out], check=True)
    print(os.path.relpath(out, ROOT))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('what', choices=('record', 'cut', 'sheet', '_title', '_select'))
    ap.add_argument('arg', nargs='?')
    ap.add_argument('--jobs', type=int, default=6)
    a = ap.parse_args()
    if a.what == '_title':
        return title(a.arg)
    if a.what == '_select':
        return select(a.arg)
    if a.what == 'sheet':
        return sheet(a.arg)
    if a.what == 'cut':
        return cut()
    os.makedirs(os.path.join(OUT, 'logs'), exist_ok=True)
    os.makedirs(CLIPS, exist_ok=True)
    with ThreadPoolExecutor(a.jobs) as ex:
        for line in ex.map(run_job, jobs()):
            print(line, flush=True)


if __name__ == '__main__':
    main()
