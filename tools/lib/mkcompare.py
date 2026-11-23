#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""How close one of our MK fighters' actions is to MK's own, frame by frame.

(docs/research/mk_engine_plan.md) MK's side is the action's capture (extracted/MK_DIR/ACTION: order.txt = MK's pose every frame,
the recording starting in his stance); ours is a recording of our fighter's frame word ($1A)
every frame after the same input, each frame mapped back to the capture pose it shows through
the build's art map (scorpion_map assignments, spread as scorpion_full.pick). Both start at
their first frame off the stance. Reported: frames on MK's pose (allowing 1 frame either way),
the start (input to first pose off the stance) and the length.

    mkcompare.py FIGHTER ACTION [--gap PX]     e.g. mkcompare.py kano btn_a
    mkcompare.py FIGHTER all                   every action in ACTIONS
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import scd
from inputs import ROOT

P1, P2 = 0x2E188, 0x2E330
GRID = {'scorpion': 20, 'raiden': 7, 'johnny': 19, 'subzero': 15, 'liukang': 17, 'kano': 18, 'sonya': 16}
# action -> (our pad presses: [(buttons, frames)], frames to record). MK pad: LP a, HP x, LK c, HK z;
# ours (EC): X = MK LP, Y = HP, A = LK, B = HK, C = roundhouse (MK: back + HK)
ACTIONS = {
    'btn_a': ([({'x'}, 4)], 60), 'btn_x': ([({'y'}, 4)], 60),
    'btn_c': ([({'a'}, 4)], 60), 'btn_z': ([({'b'}, 4)], 60),
    'roundhouse': ([({'c'}, 4)], 70),
    'spear': ([({'left'}, 3), (set(), 2), ({'left'}, 3), ({'x'}, 4)], 130),   # back, back + LP (the button after)
    'uppercut': ([({'down'}, 6), ({'down', 'y'}, 4), ({'down'}, 30)], 60),
    'crouch_c': ([({'down'}, 6), ({'down', 'a'}, 4), ({'down'}, 30)], 60),
    'jump_up': ([({'up'}, 4)], 70), 'jump_fwd': ([({'up', 'right'}, 4)], 70),
    'jump_back': ([({'up', 'left'}, 4)], 70),
    'walk_fwd': ([({'right'}, 80)], 80), 'walk_back': ([({'left'}, 80)], 80),
}
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big')


def art_map(spec):
    """{our frame word: (action, capture pose)} for this fighter (his sheet numbering)."""
    import patches, scorpion_full as sf, scorpion_map
    patches.use(spec)
    cfg = sf.CFG
    shift = spec.sheet_base - 0x40
    out = {}
    for (sid, f), (action, k, n) in scorpion_map.assignments(cfg['aliases'], cfg['exact'], cfg['extra']).items():
        d = os.path.join(ROOT, 'extracted', sf.capture_dir(action), sf.CAPTURE_OF.get(action, action))
        if not os.path.exists(os.path.join(d, 'indexed.npy')):
            continue
        poses = np.load(os.path.join(d, 'indexed.npy'), mmap_mode='r')
        try:
            out[(sid + shift) << 8 | f] = (action, int(sf.pick(poses, k, n, action)))
        except Exception:
            pass
    return out


def mk_seq(spec, action):
    import scorpion_full as sf
    d = os.path.join(ROOT, 'extracted', sf.capture_dir(action), sf.CAPTURE_OF.get(action, action))
    order = [int(v) for v in open(os.path.join(d, 'order.txt')).read().split()]
    poses = np.load(os.path.join(d, 'indexed.npy'), mmap_mode='r')
    lead = sf.stance_lead(poses) if len(poses) >= 3 else 0    # his stance cycle: poses below it
    t0 = next(i for i, k in enumerate(order) if k >= lead)
    t1 = len(order)
    while t1 > t0 and order[t1 - 1] < lead:
        t1 -= 1
    return order[t0:t1]


def our_seq(spec, action, amap, gap):
    presses, frames = ACTIONS[action]
    with tempfile.TemporaryDirectory() as tmp:
        st = os.path.join(tmp, 'duel.state')
        subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'),
                        '--p1', str(GRID[spec.key]), '--p2', '0', '--stage', '11', '--out', st],
                       check=True, capture_output=True)
        c = scd.Core(saves=os.path.join(tmp, 'saves'))
        c.load(os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
        c.load_state(st)
        c.run(30)
        seq, t = [], 0
        for b, n in presses + [(set(), max(0, frames - sum(n for _, n in presses)))]:
            c.buttons[0] = set(b)
            for _ in range(n):
                c.run(1)
                f = W(c.prg_ram(), P1 + 0x1A)
                seq.append(amap.get(f, ('?', f)))
                t += 1
    start = next((i for i, (a, k) in enumerate(seq) if a == action), None)
    if start is None:
        return None, seq
    end = len(seq)
    while end > start and seq[end - 1][0] != action:
        end -= 1
    return start, [k if a == action else None for a, k in seq[start:end]]


def compare(spec, action, amap, gap=150):
    mk = mk_seq(spec, action)
    start, ours = our_seq(spec, action, amap, gap)
    if start is None:
        return dict(action=action, mk=len(mk), ours=0, match=0.0, start=None,
                    note='never shows this action (' + ' '.join(sorted({a for a, _ in ours})) + ')')
    # aligned where they overlap best (MK's captures may show what ours plays as another group -
    # the crouch before a crouching move): MK's sequence shifted up to 15 frames either way
    def score(sh):
        hit = 0
        for i, k in enumerate(ours):
            if k is not None and any(0 <= j + sh < len(mk) and mk[j + sh] == k for j in (i - 1, i, i + 1)):
                hit += 1
        return hit
    sh = max(range(-15, 16), key=score)
    span = max(len(ours), len([k for k in mk[max(0, sh):max(0, sh) + len(ours)]]))
    return dict(action=action, mk=len(mk), ours=len(ours), match=score(sh) / max(1, span), start=start,
                mk_poses=len(set(mk)), our_poses=len({k for k in ours if k is not None}), shift=sh)


def main():
    import patches
    ap = argparse.ArgumentParser()
    ap.add_argument('fighter')
    ap.add_argument('action')
    ap.add_argument('--gap', type=int, default=150)
    a = ap.parse_args()
    spec = next(s for s in patches.MK_SPECS if s.key == a.fighter)
    amap = art_map(spec)
    acts = list(ACTIONS) if a.action == 'all' else [a.action]
    for act in acts:
        try:
            r = compare(spec, act, amap, a.gap)
        except (FileNotFoundError, StopIteration) as e:
            print(f'{act:12s} no capture ({e.__class__.__name__})')
            continue
        if r.get('note'):
            print(f'{act:12s} {r["note"]}')
            continue
        print(f'{act:12s} match {100 * r["match"]:3.0f}%  frames MK {r["mk"]:3d} ours {r["ours"]:3d}  '
              f'poses MK {r["mk_poses"]:2d} ours {r["our_poses"]:2d}  start +{r["start"]}  (MK from frame {r["shift"]})')


if __name__ == '__main__':
    main()
