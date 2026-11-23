#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""An MK fighter's FINISH HIM daze is MK's 7-pose sway, at MK's timing.

The poses: mkinputs.DAZE_FRAMES; the timing: DAZE_SEQ (~10 frames a pose, looped).

From a 2-player duel (him vs Scorpion, or Sub-Zero for Scorpion: FINISH HIM
is an MK winner's; made here with tools/lib/duelstate.py), the deciding round, him
on 3 health: the winner jabs him to FINISH HIM. While he waits,
dazed (EC's dizzy, $1F), the poses drawn ($1C) must
  - be his 7 sway poses, in MK's order, round and round;
  - each be held as MK holds it (8-12 frames). A pose shown for a frame or two
    is EC's own dizzy loop cutting into the sway (mkinputs.dizzy_hold).

    dazecheck.py FIGHTER [--as-p2] [--state STATE] [--disc CUE]
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
import mkinputs, patches
from inputs import ROOT

P1, P2 = 0x2E188, 0x2E330
GRID = {'scorpion': 20, 'raiden': 7, 'subzero': 15, 'sonya': 16, 'liukang': 17, 'kano': 18, 'johnny': 19}
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big')
X = lambda r, o: int.from_bytes(r[o + 0x4E:o + 0x50], 'big', signed=True)
WATCH = 300                    # frames of the daze watched (~4 sways)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('fighter', choices=sorted(GRID))
    ap.add_argument('--as-p2', action='store_true', help='he is player 2')
    ap.add_argument('--state', help='a duel state (default: made now)')
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    a = ap.parse_args()
    spec = next(s for s in patches.MK_SPECS if s.key == a.fighter)
    shift = (spec.sheet_base - 0x40) << 8
    poses = [f + shift for f in mkinputs.DAZE_FRAMES]
    me, him = (P2, P1) if a.as_p2 else (P1, P2)
    port = 0 if a.as_p2 else 1                     # (the winner's)
    winner = GRID['subzero' if a.fighter == 'scorpion' else 'scorpion']
    state = a.state
    if not state:
        state = os.path.join(tempfile.mkdtemp(), 'duel.state')
        p1, p2 = (str(winner), str(GRID[a.fighter])) if a.as_p2 else (str(GRID[a.fighter]), str(winner))
        subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'),
                        '--disc', a.disc, '--p1', p1, '--p2', p2, '--stage', '11', '--out', state],
                       check=True, capture_output=True)
    c = scd.Core()
    c.load(a.disc)
    c.load_state(state)
    c.run(10)
    c.poke_prg(0x31D26, (1).to_bytes(2, 'big'))   # one round each: this one decides it
    c.poke_prg(0x31D28, (1).to_bytes(2, 'big'))
    c.poke_prg(me + 0x76, (3).to_bytes(2, 'big'))
    for _ in range(150):                          # the winner walks up and jabs
        r = c.prg_ram()
        if abs(X(r, me) - X(r, him)) < 45:
            break
        c.buttons[port] = {'right' if X(r, me) > X(r, him) else 'left'}
        c.run(2)
    c.buttons[port] = {'x'}
    c.run(4)
    c.buttons[port] = set()
    drawn, start = [], None
    for f in range(90 + WATCH):
        c.run(1)
        r = c.prg_ram()
        if W(r, me + 0xBE) & 0x7FFF != mkinputs.DIZZY:
            if start is not None:
                break
            continue
        if start is None:
            start = f
        if f - start >= WATCH:
            break
        if not drawn or drawn[-1][1] != W(r, me + 0x1C):
            drawn.append((f, W(r, me + 0x1C)))
    if not a.state:
        os.remove(state)
        os.rmdir(os.path.dirname(state))
    if start is None:
        print(f'{a.fighter} daze -> FAILED (not dazed)')
        sys.exit(1)
    sway = [(f, p) for f, p in drawn if p in poses]
    holds = [g - f for (f, _), (g, _) in zip(sway, sway[1:])][1:]          # (not the first: EC's start)
    order = all(poses.index(q) == (poses.index(p) + 1) % len(poses) for (_, p), (_, q) in zip(sway, sway[1:]))
    seen = {p for _, p in sway}
    others = sorted({hex(p) for _, p in drawn[1:] if p not in poses})     # (drawn[0]: his pose before)
    ok = (seen == set(poses) and order and holds and min(holds) >= 8 and max(holds) <= 12 and not others
          and drawn[-1][0] - start >= WATCH - 20)
    print(f'{a.fighter} as P{2 if a.as_p2 else 1}: dazed {drawn[-1][0] - start + 1} frames, '
          f'{len(seen)} of 7 sway poses, in order {order}, holds {min(holds, default=0)}-{max(holds, default=0)} frames'
          f'{", other poses " + " ".join(others) if others else ""} -> {"ok" if ok else "FAILED"}')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
