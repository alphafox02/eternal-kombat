#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Make build/states/duel.state: a 2-player Duel, saved the moment player 1 can move.

Both fighters are human-controlled, so player 2 stands still with no input; the
state is saved once holding forward actually moves player 1 (past the intro).
Used by ecprobe.py and the move tests.

Player 2 has to press start on the select screen *before* player 1 picks;
otherwise "Choose your opponent" makes player 2 a CPU fighter.

    duelstate.py [--disc build/.../Eternal Kombat.cue]
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scd
from inputs import ROOT

P1 = 0x2E188


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'build', 'states', 'duel.state'))
    ap.add_argument("--p2", type=int, default=20,
                    help="player 2's fighter: right presses on the select grid (0 Shadow, 1 Larcen, 7 Raiden, "
                         "8 Blade, 14 Blast, 15 Sub-Zero, 16 Sonya, 17 Liu Kang, 18 Kano, 19 Johnny Cage, 20 Scorpion)")
    ap.add_argument('--unlock', type=lambda v: [int(x) for x in v.split(',')], default=[],
                    help='fighter ids to switch on for the select screen (16 Thanatos, 22 the Senator): '
                         "GAME's unlock mask $1CC8(a6), a bit per id - 2")
    ap.add_argument('--p1', type=int, default=20,
                    help="player 1's fighter: right presses on the select grid (as --p2)")
    ap.add_argument('--cpu', action='store_true',
                    help="player 2 is the CPU: player 2 never joins, player 1 chooses the opponent (--p2 presses)")
    ap.add_argument('--p2-id', type=int,
                    help="player 2's fighter by id, picked or not on the select screen (11: Shang Tsung, "
                         "the Contest's boss): written over player 2's pick ($142A(a6) = id - 2) once both picked")
    ap.add_argument('--stage', type=lambda v: int(v, 16),
                    help="stage mode to fight on (hex, $11-$22; 13 = Blast's, 1F = the Pit (the Senator's)): "
                         "written over GAME.CO's stage-by-fighter table ($C28) in RAM once both picked, and over "
                         "the MK stages' pick's (an MK fighter's fight is on it too)")
    ap.add_argument('--mk-stage', help="with an MK fighter in it, the fight is on this MK stage (mkstages.STAGES' "
                    "keys: courtyard, gates, shrine, pit, throne, lair): the pick's tables (SUB.BIN) all say it")
    a = ap.parse_args()
    c = scd.Core(saves=os.path.join(ROOT, 'build', 'shots', 'duel-saves'))
    c.load(a.disc)
    c.load_state(os.path.join(ROOT, 'build', 'states', 'menu.state'))
    if a.mk_stage or a.stage:
        # the pick (mkstages.py) puts an MK fighter's fight on a random MK stage: its tables all say
        # this one (an MK stage by key, or --stage's mode)
        import mkstages, patches
        pit = patches.PIT_MODE
        keys = [k for k, _, _ in mkstages.STAGES]
        table = b''.join((pit if k == 'pit' else mkstages.MODE).to_bytes(2, 'big') for k in keys) + \
            bytes(mkstages.PACKED.index(k) if k in mkstages.PACKED else 0 for k in keys)
        at = c.prg_ram().find(table, 0x6000, 0x14000)
        assert at > 0, "the MK stages' pick tables aren't in SUB.BIN (an older build?)"
        k = a.mk_stage
        mode = a.stage if not k else pit if k == 'pit' else mkstages.MODE
        c.poke_prg(at, mode.to_bytes(2, 'big') * len(keys)
                   + bytes([mkstages.PACKED.index(k) if k in mkstages.PACKED else 0]) * len(keys))
    if a.unlock:
        mask = int.from_bytes(c.prg_ram()[0x31CC8:0x31CCC], 'big')
        for fid in a.unlock:
            mask |= 1 << (fid - 2)
        c.poke_prg(0x31CC8, mask.to_bytes(4, 'big'))
    c.press(['start']); c.run(240)                     # title -> main menu
    c.press(['down']); c.run(20)                       # Enter Duel
    c.press(['start']); c.run(240)
    if not a.cpu:
        c.press(['start'], port=1); c.run(40)          # player 2 joins first (cursor on slot 0)
    for _ in range(a.p1):                              # player 1
        c.press(['right']); c.run(20)
    c.press(['start']); c.run(40)
    if a.cpu:                                          # 'choose your opponent': player 1 picks the CPU's
        c.run(200)
        for _ in range(a.p2):
            c.press(['right']); c.run(20)
        c.press(['start'])
    else:
        for _ in range(a.p2):                          # player 2 picks with their own pad
            c.press(['right'], port=1); c.run(20)
        c.press(['start'], port=1)
    if a.stage or a.p2_id:
        c.run(2)
    if a.stage:
        c.poke_prg(0x14C28, bytes([0, a.stage]) * 25)
    if a.p2_id:                                        # (the game writes the pick again a while after)
        for _ in range(30):
            if c.prg_ram()[0x3142A:0x3142C] != (a.p2_id - 2).to_bytes(2, 'big'):
                c.poke_prg(0x3142A, (a.p2_id - 2).to_bytes(2, 'big'))
            c.run(10)
    else:
        c.run(300)
    c.press(['start']); c.run(400)
    c.press(['start'])
    tmp = f'{a.out}.{os.getpid()}.tmp'                 # (checks run in parallel can make the same state)
    W = lambda r: int.from_bytes(r[P1 + 0x4E:P1 + 0x50], 'big', signed=True)
    for t in range(0, 3000, 10):
        c.run(10)
        c.save_state(tmp)
        c.run(12)                                      # what happens on its own (intro walk-in)
        x_idle = W(c.prg_ram())
        c.load_state(tmp)
        c.buttons[0] = {'right'}
        c.run(12)
        c.buttons[0] = set()
        x_walk = W(c.prg_ram())
        c.load_state(tmp)
        if x_walk - x_idle >= 4:                       # the input itself moved him
            c.save_state(tmp)
            os.replace(tmp, a.out)                     # whole or not at all
            print(f'duel live after {t} frames; saved {os.path.relpath(a.out, ROOT)}')
            return
    os.remove(tmp)
    raise SystemExit('player 1 never responded')


if __name__ == '__main__':
    main()
