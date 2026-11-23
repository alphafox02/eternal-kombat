#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Record a video (with sound) of the game from a savestate.

--mash plays player 1 with random 6-button input (like the 'mash' scenario
command), so the CPU opponent has someone to fight. --bot scorpion plays
player 1 as an MK player would, with MK inputs only: back, back + LP spear
from range, uppercut (down + HP) when the opponent is pulled in, teleport
(down, back + HP), and MK normals up close; --bot normals plays MK normals
only; --bot lookahead tries each MK-style option from savestates and plays
the best. Needs ffmpeg.

    record.py --state fight --seconds 60 --mash --out build/shots/cpu_scorpion.mp4
"""
import argparse, os, random, subprocess, sys, tempfile, wave
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))                     # (tools/: play.py)
from scd import Core
from play import resolve_disc, state_path, BUTTONS, DIRS

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


P1, P2 = 0x2E188, 0x2E330


def scorpion_bot(r, rnd, me=P1, them=P2, specials=True):
    """Next input plan [(buttons, frames)] for one fighter using MK inputs.
    EC buttons as mapped: X = LP, Y = HP, A = LK, B = HK, C = roundhouse.
    Plays like an MK Scorpion: spear from range, uppercut a dazed or
    pulled-in opponent, block when close, low punches / sweeps / roundhouse.
    specials=False: normals only (e.g. Sub-Zero in the mirror match)."""
    x = lambda o: int.from_bytes(r[o + 0x4E:o + 0x50], 'big', signed=True)
    w = lambda o: int.from_bytes(r[o:o + 2], 'big')
    gap = x(them) - x(me)
    fwd, back = ('right', 'left') if gap > 0 else ('left', 'right')
    dist = abs(gap)
    their = w(them + 0xBE) & 0x7FFF
    if their == 0x1F:                                          # dazed: walk in and uppercut
        if dist > 62:
            return [([fwd], 4)]
        return [(['down'], 10), (['down', 'y'], 4), (['down'], 6), ([], 10)]
    if 0x1A <= their <= 0x1D and dist < 70:                    # reeling up close: low punches
        return [(['x'], 3), ([], 3), (['x'], 3), ([], 6)]
    if dist > 105 and specials and rnd.random() < 0.8:        # spear: back, back + LP
        return [([back], 3), ([], 3), ([back], 2), ([back, 'x'], 4), ([], 24)]
    if dist > 70:
        if rnd.random() < 0.35:                                # wait for them, guarding
            return [([back], rnd.choice((10, 16)))]
        return [([fwd], rnd.choice((6, 10)))]
    if rnd.random() < 0.4:                                     # block
        return [([back], rnd.choice((12, 20, 28)))]
    move = rnd.choice([(['x'],), (['x'],), (['y'],), (['down', 'c'],), (['c'],),
                       (['down', 'y'],), (['a'],), (['b'],)])
    hold = [(['down'], 8)] if 'down' in move[0] else []
    return hold + [(move[0], 4), ([], rnd.choice((8, 14)))]


# MK-style options for the look-ahead bot: (name, plan); 'F'/'B' = toward/away
OPTIONS = [
    ('spear',     [('B', 3), ('', 3), ('B', 2), ('B+x', 4), ('', 20)]),
    ('uppercut',  [('down', 8), ('down+y', 4), ('down', 6), ('', 8)]),
    ('low punch', [('x', 3), ('', 3), ('x', 3), ('', 6)]),
    ('high punch', [('y', 4), ('', 12)]),
    ('sweep',     [('down', 8), ('down+c', 4), ('', 14)]),
    ('roundhouse', [('c', 4), ('', 16)]),
    ('high kick', [('b', 4), ('', 14)]),
    ('low kick',  [('a', 4), ('', 12)]),
    ('block',     [('B', 16)]),
    ('crouch block', [('down+B', 16)]),
    ('step in',   [('F', 10)]),
    ('back off',  [('B', 10)]),
    ('jump kick', [('up+F', 4), ('', 12), ('b', 4), ('', 24)]),
]


def lookahead_bot(core, rnd, me=P1, them=P2, horizon=90):
    """Try every option from the current moment (savestates), score each by
    damage dealt vs taken over `horizon` frames (+ daze / knock-down bonus),
    return the best plan as [(buttons, frames)]. All inputs are real presses;
    only the choice is made by looking ahead."""
    r = core.prg_ram()
    w = lambda r, o: int.from_bytes(r[o:o + 2], 'big')
    x = lambda r, o: int.from_bytes(r[o + 0x4E:o + 0x50], 'big', signed=True)
    fwd, back = ('right', 'left') if x(r, them) > x(r, me) else ('left', 'right')
    base = core.snapshot()
    h_me, h_them = w(r, me + 0x76), w(r, them + 0x76)
    best, best_score = None, None
    for name, steps in OPTIONS:
        plan = [([fwd if b == 'F' else back if b == 'B' else b for b in s.split('+') if b], n)
                for s, n in steps]
        core.restore(base)
        n_total = 0
        for held, n in plan:
            core.buttons[0] = set(held)
            core.run(n)
            n_total += n
        core.buttons[0] = set()
        core.run(max(0, horizon - n_total))
        rr = core.prg_ram()
        st = w(rr, them + 0xBE) & 0x7FFF
        score = 2 * (h_them - w(rr, them + 0x76)) - 3 * (h_me - w(rr, me + 0x76))
        score += 12 if st == 0x1F else 5 if st == 0x1C else 0
        if name not in ('block', 'crouch block', 'back off'):
            score += 0.6                     # ties go to attacking, like an MK player
        if abs(x(rr, them) - x(rr, me)) < 70:
            score += 0.4                     # keep the pressure on
        score += rnd.random() * 0.5
        if best_score is None or score > best_score:
            best, best_score = plan, score
    core.restore(base)
    core.audio.clear()
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--disc')
    ap.add_argument('--state', required=True)
    ap.add_argument('--seconds', type=float, default=30)
    ap.add_argument('--mash', action='store_true')
    ap.add_argument('--bot', choices=['scorpion', 'normals', 'lookahead'])
    ap.add_argument('--p2-mash', action='store_true', help='random input for player 2 too (Duel mode)')
    ap.add_argument('--p2-bot', action='store_true', help='player 2 plays MK normals (mirror match: Sub-Zero)')
    ap.add_argument('--script', help="player 1 inputs first: 'left:3,:3,left:2,left+x:4' (buttons:frames)")
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--scale', type=int, default=2)
    ap.add_argument('--out', default=os.path.join(ROOT, 'build', 'shots', 'recording.mp4'))
    a = ap.parse_args()

    core = Core(audio=True, saves=os.path.join(ROOT, 'build', 'shots', 'record-saves'))
    core.load(resolve_disc(a.disc))
    core.load_state(state_path(a.state))
    core.run(1)
    h, w = core.frame.shape[:2]
    tmp = tempfile.mkdtemp()
    wav_path = os.path.join(tmp, 'a.wav')
    vid_path = os.path.join(tmp, 'v.mp4')
    ff = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
                           '-s', f'{w}x{h}', '-r', f'{core.fps:.4f}', '-i', '-',
                           '-vf', f'scale={w * a.scale}:{h * a.scale}:flags=neighbor',
                           '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', vid_path],
                          stdin=subprocess.PIPE)
    wav = wave.open(wav_path, 'wb')
    wav.setnchannels(2)
    wav.setsampwidth(2)
    wav.setframerate(int(round(core.sample_rate)))
    rnd = random.Random(a.seed)
    left = 0
    plan = []
    if a.script:
        plan = [((b.split('+') if b else []), int(n)) for b, n in
                (step.split(':') for step in a.script.split(','))]
        a.bot = a.bot or 'script'
    left2 = 0
    plan2 = []
    for _ in range(int(a.seconds * core.fps)):
        if a.p2_bot:
            if not plan2:
                plan2 = scorpion_bot(core.prg_ram(), rnd, P2, P1, specials=False)
            held2, n2 = plan2[0]
            core.buttons[1] = set(held2)
            plan2[0] = (held2, n2 - 1)
            if n2 <= 1:
                plan2.pop(0)
        if a.p2_mash:
            if left2 <= 0:
                held = {rnd.choice(DIRS)} if rnd.random() < 0.5 else set()
                if rnd.random() < 0.5:
                    held.add(rnd.choice(BUTTONS))
                core.buttons[1] = held
                left2 = rnd.choice((6, 10, 14, 20))
            left2 -= 1
        if a.bot:
            if not plan:
                if a.bot == 'lookahead':
                    plan = lookahead_bot(core, rnd)
                else:
                    plan = (scorpion_bot(core.prg_ram(), rnd, specials=a.bot == 'scorpion')
                            if a.bot in ('scorpion', 'normals') else [([], 1)])
            held, n = plan[0]
            core.buttons[0] = set(held)
            plan[0] = (held, n - 1)
            if n <= 1:
                plan.pop(0)
        elif a.mash:
            if left <= 0:
                held = {rnd.choice(DIRS)} if rnd.random() < 0.6 else set()
                if rnd.random() < 0.7:
                    held.add(rnd.choice(BUTTONS))
                core.buttons[0] = held
                left = rnd.choice((4, 6, 8, 12))
            left -= 1
        core.run(1)
        frame_no = locals().get('frame_no', 0) + 1
        if frame_no % 600 == 0 and a.bot:
            rr = core.prg_ram()
            print(f'{frame_no // 60:3d}s  health P1 {int.from_bytes(rr[P1 + 0x76:P1 + 0x78], "big")}'
                  f'  P2 {int.from_bytes(rr[P2 + 0x76:P2 + 0x78], "big")}', flush=True)
        if core.frame.shape[:2] == (h, w):
            ff.stdin.write(core.frame.tobytes())
        wav.writeframes(b''.join(core.audio))
        core.audio.clear()
    ff.stdin.close()
    ff.wait()
    wav.close()
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', vid_path, '-i', wav_path,
                    '-c:v', 'copy', '-c:a', 'aac', '-b:a', '160k', '-shortest', a.out], check=True)
    print(f'{a.seconds:.0f}s -> {os.path.relpath(a.out, ROOT)}')


if __name__ == '__main__':
    main()
