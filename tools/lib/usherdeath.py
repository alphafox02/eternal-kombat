#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Play the Chicago Theater's Sudden Death (the usher's shotgun) on a loser; trace the death object.

From a 2-player duel on the theater (stage mode $1B; made with tools/lib/duelstate.py
if missing): the deciding round, the loser (player 2) on 6 health with 40 damage
taken, both walked to the right end of the stage (the Sudden Death wants the
loser facing right at x $284-$2C4), and LAR.BGI's +0 check patched in RAM to take
the Sudden Death branch ($34054: bne -> bra; its own +2 check wants a flag the
hit path rewrites - docs/notes/2026-11.md "EC's own headless deaths"). Player 1 hits.

    usherdeath.py WINNER_PRESSES LOSER_PRESSES [--frames N]
        -> the death object's frame words, and build/shots/usher_<loser id>.png
"""
import argparse, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scd
from inputs import ROOT

P1, P2 = 0x2E188, 0x2E330
WINS = 0x31D26
FORCE_AT, BRA = 0x34054, b'\x60'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('winner', type=int)
    ap.add_argument('loser', type=int)
    ap.add_argument('--frames', type=int, default=1300)
    ap.add_argument('--at', default='', help='frames (after the hit, comma-separated) to save full size, around the loser')
    a = ap.parse_args()
    state = os.path.join(ROOT, 'build', 'states', f'theater_{a.winner}_{a.loser}.state')
    if not os.path.exists(state):
        subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'),
                        '--p1', str(a.winner), '--p2', str(a.loser), '--stage', '1B', '--out', state], check=True)
    c = scd.Core(saves=os.path.join(ROOT, 'build', 'shots', 'record-saves'))
    c.load(os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    c.load_state(state)
    c.run(30)

    def setx(o, v):
        for f in (0x36, 0x3A, 0x4E, 0x56, 0xB2, 0xBA):
            c.poke_prg(o + f, v.to_bytes(2, 'big'))
    c.poke_prg(WINS, (1).to_bytes(2, 'big'))
    c.poke_prg(WINS + 2, (1).to_bytes(2, 'big'))
    c.buttons[0] = {'right'}                      # both walk right: the camera follows
    c.buttons[1] = {'right'}
    c.run(200)
    c.buttons[0] = set()
    c.buttons[1] = set()
    setx(P2, 670)                                 # (the camera clamps them to ~707 / ~757)
    setx(P1, 710)
    c.run(10)
    c.poke_prg(P2 + 0x76, (6).to_bytes(2, 'big'))
    c.poke_prg(P2 + 0x190, (40).to_bytes(2, 'big'))
    c.run(20)
    r = c.prg_ram()
    print('loser id', r[P2 + 0x4D], 'x', int.from_bytes(r[P2 + 0x4E:P2 + 0x50], 'big'),
          'facing left' if r[P2 + 0x20] & 8 else 'facing right')
    c.poke_prg(FORCE_AT, BRA)
    c.buttons[0] = {'y'}
    c.run(4)
    c.buttons[0] = set()
    shots, seen, full = [], {}, []
    at = {int(v) for v in a.at.split(',') if v}
    for f in range(a.frames):
        c.run(1)
        r = c.prg_ram()
        for o in range(0x2C000, 0x2E188, 2):                      # the death object: type $2AFC
            if r[o + 0x4C:o + 0x4E] == b'\x2a\xfc':
                key = (r[o + 0x1A:o + 0x1C].hex(), r[o + 0x28:o + 0x2A].hex())
                if key not in seen:
                    seen[key] = f
        if f % 30 == 0:
            shots.append(c.frame.copy())
        if f in at:
            full.append(c.frame.copy())
    kind = int.from_bytes(c.prg_ram()[0x31CD4:0x31CD6], 'big')
    print('finisher type', kind, '(2 = Sudden Death)')
    print('death object frames ($1A, $28) first seen:', sorted(seen.items(), key=lambda kv: kv[1]))
    from PIL import Image
    ims = [Image.fromarray(s).resize((160, 112)) for s in shots]
    o = Image.new('RGB', (160 * 10, 112 * ((len(ims) + 9) // 10)))
    for i, im in enumerate(ims):
        o.paste(im, ((i % 10) * 160, (i // 10) * 112))
    out = os.path.join(ROOT, 'build', 'shots', f'usher_{r[P2 + 0x4D]}.png')
    o.save(out)
    print(os.path.relpath(out, ROOT))
    if full:
        z = Image.new('RGB', (3 * 200 * len(full), 3 * 90))
        for i, fr in enumerate(full):
            z.paste(Image.fromarray(fr).crop((120, 130, 320, 220)).resize((600, 270), Image.NEAREST), (600 * i, 0))
        out = os.path.join(ROOT, 'build', 'shots', f'usher_{r[P2 + 0x4D]}_close.png')
        z.save(out)
        print(os.path.relpath(out, ROOT))


if __name__ == '__main__':
    main()
