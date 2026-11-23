#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""MK CD's own Shang Tsung fight, as the reference for ours.

Which of his EMP frames MK shows, for how long and how he moves, action by action.

MK never lets a player pick Shang; this sets a game's opponent to him:
RAM word $7BAC6 (sub-CPU PRG-RAM) is player 2's fighter (0 Johnny, 1 Kano,
2 Raiden, 3 Liu Kang, 4 Scorpion, 5 Sub-Zero, 6 Sonya, 7 Goro, 8 Shang
Tsung; $7BAC4 player 1's). Written once the game has picked (the ladder's
first opponent, or player 2's choice), before the fight loads. ($8F50/$8F52
only cache which fighter's art is loaded: setting those loads nothing.)

    mkshangref.py states     # build/states/mk_shang_1p.state (Kano vs the CPU's Shang,
                             # round 1) and mk_shang_2p.state (Kano vs Shang, 2 players)
    mkshangref.py capture    # the scenarios below -> extracted/mk_shang_ref.json

Each captured frame's player-2 sprites (palette line 1) are split into
pieces (body, skull) and every piece matched pixel for pixel against
EMP.OBJ's frames (mkshang.frames; flipped as he faces left): MK
shows his frames unscaled, so a match is exact or not at all ('?': off
screen, or a morph's other fighter).
"""
import hashlib, json, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inputs import ROOT

STATES = os.path.join(ROOT, 'build', 'states')
OUT = os.path.join(ROOT, 'extracted', 'mk_shang_ref.json')
P2_FIGHTER = 0x7BAC6
SHANG = 8
KANO = 1

# (state, [(p1 buttons, p2 buttons, frames)], what it shows)
SCENARIOS = {
    # the CPU's Shang, Kano standing still: stance, three-skull volleys, morphs
    'cpu_idle': ('1p', [('', '', 2400)], 'CPU: stance, skull volleys, morph'),
    # Kano jumps in at him: he backs away
    'cpu_jumpin': ('1p', [('', '', 215), ('right', '', 47), ('up+right', '', 4), ('', '', 14), ('z', '', 4),
                          ('', '', 120)], 'CPU: backs away from a jump-in'),
    'walk_fwd': ('2p', [('', '', 20), ('', 'left', 50), ('', '', 30)], 'walks toward Kano'),
    'hit': ('2p', [('', '', 20), ('right', '', 70), ('x', '', 4), ('', '', 60)], "Kano's jab: hit reaction"),
    'knockdown': ('2p', [('', '', 20), ('right', '', 78), ('down', '', 8), ('down+x', '', 4), ('down', '', 20),
                         ('', '', 150)], "Kano's uppercut: knocked down, gets up"),
}


def session():
    import mkmoves
    mkmoves.PAL = 1                          # player 2's palette line
    return mkmoves.Session()


def make_states():
    s = session()
    c = s.core
    # 1 player: Kano (the cursor's start); the ladder's first opponent becomes Shang
    c.load_state(os.path.join(STATES, 'mk_select.state'))
    c.run(10)
    c.press(['start'])
    c.run(5 + 1200)                          # the ladder screen
    c.press(['start'])
    c.run(10)
    c.press(['a'])
    for _ in range(600):
        if c.prg_ram()[P2_FIGHTER:P2_FIGHTER + 2] != b'\xff\xff':
            break
        c.run(1)
    c.poke_prg(P2_FIGHTER, bytes([0, SHANG]))
    _until_fight(s, 'mk_shang_1p.state', settle=0)
    # 2 players: Kano vs player 2's pick (Sub-Zero, his cursor's start), made Shang
    c.load_state(os.path.join(STATES, 'mk_select.state'))
    c.run(10)
    c.press(['start'], port=1)
    c.run(30)
    c.press(['start'])
    c.run(20)
    c.press(['start'], port=1)
    for _ in range(600):
        if c.prg_ram()[P2_FIGHTER:P2_FIGHTER + 2] == b'\x00\x05':
            break
        c.run(1)
    c.poke_prg(P2_FIGHTER, bytes([0, SHANG]))
    _until_fight(s, 'mk_shang_2p.state', settle=250)    # past FIGHT!: both players respond


def _until_fight(s, name, settle):
    c = s.core
    for t in range(4000):
        c.run(1)
        if t > 300 and s.frame(s.vdp()).any():
            break
    else:
        raise SystemExit(f'{name}: Shang never appeared')
    c.run(settle)
    r = c.prg_ram()
    assert r[0x7BAC4:0x7BAC8] == bytes([0, KANO, 0, SHANG]), r[0x7BAC4:0x7BAC8].hex()
    c.save_state(os.path.join(STATES, name))
    print(f'{name}: Kano vs Shang Tsung')


def emp_frames():
    import mkshang
    out = {}
    for n, (img, _) in mkshang.frames(list(range(62))).items():
        a = np.asarray(img)
        if a.size and a.any():
            out[n] = _crop(a)
    return out


def _crop(p):
    ys, xs = np.nonzero(p)
    return p[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def pieces(pose, cut):
    """Separate sprites (body, skull) by empty columns >= 5 px wide."""
    pose = pose.copy()
    pose[:cut] = 0                           # (1 player: FIGHT! shares his line)
    cols = pose.any(0)
    out, x, w = [], 0, len(cols)
    while x < w:
        if cols[x]:
            s = x
            while x < w and cols[x:x + 5].any():
                x += 1
            if pose[:, s:x].any():
                out.append((s, pose[:, s:x]))
        x += 1
    return out


def label(piece, emp):
    q0 = _crop(piece)
    for flip in ('h', '', 'v', 'hv'):
        q = q0[:, ::-1] if 'h' in flip else q0
        q = q[::-1] if 'v' in flip else q
        for n, e in emp.items():
            if e.shape == q.shape and (e == q).all():
                return n
    return '?'


def capture():
    emp = emp_frames()
    s = session()
    c = s.core
    ref = {}
    for name, (st, script, what) in SCENARIOS.items():
        c.load_state(os.path.join(STATES, f'mk_shang_{st}.state'))
        cut = 100 if st == '1p' else 0
        seen, runs, t = {}, [], 0
        for p1, p2, n in script:
            for _ in range(n):
                c.buttons[0] = set(p1.split('+')) - {''}
                c.buttons[1] = set(p2.split('+')) - {''}
                c.run(1)
                f = s.frame(s.vdp())
                h = hashlib.md5(f.tobytes()).hexdigest()
                if h not in seen:
                    seen[h] = [[label(p, emp), int(x0)] for x0, p in pieces(f, cut)]
                lab = seen[h]
                frames = [l for l, _ in lab]
                x = lab[0][1] if lab else None
                if runs and runs[-1]['frames'] == frames:
                    runs[-1]['n'] += 1
                    runs[-1]['x1'] = x
                else:
                    runs.append({'t': t, 'n': 1, 'frames': frames, 'x0': x, 'x1': x})
                t += 1
        c.buttons = [set(), set()]
        ref[name] = {'what': what, 'runs': runs}
        print(f'{name:11s} {what}')
        for r in runs:
            if r['frames']:
                print(f"    {r['t']:5d} +{r['n']:3d}  {r['frames']}  x {r['x0']} -> {r['x1']}")
    json.dump(ref, open(OUT, 'w'), indent=0)
    print('wrote', OUT)


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'capture'
    {'states': make_states, 'capture': capture}[cmd]()
