#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Record a stage finisher (with sound) on an MK loser: its Overkill or Sudden Death.

From a deciding round on that stage with the MK fighter (player 1) nearly beaten and the EC winner
(player 2) landing the last punch at the spot where the stage plays it (found by walking the loser
along the stage, as tools/dev/stageaudit.py does).

    stagevideo.py STAGE LOSER WINNER {overkill,sudden} --out OUT.mp4
        STAGE: stage mode (hex, $11-$22; e.g. 21 Dawson's train, 1A Slash's, 20 Jetta's circus);
        LOSER, WINNER: select-grid presses (tools/lib/duelstate.py: 18 Kano, 13 Dawson, ...)
"""
import argparse, os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stageaudit
from inputs import ROOT

KIND = {'overkill': 1, 'sudden': 2}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('stage', type=lambda v: int(v, 16))
    ap.add_argument('loser', type=int)
    ap.add_argument('winner', type=int)
    ap.add_argument('kind', choices=KIND)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tail", type=int, default=300, help="frames recorded after the round ends")
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    a = ap.parse_args()
    want = KIND[a.kind]
    with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, 'build')) as tmp:
        st = stageaudit.duel(a.disc, a.stage, a.loser, tmp, winner=a.winner)
        spot = None
        for side in (50, -50):
            for x in stageaudit.SPOTS_FINE:
                if stageaudit.finisher(a.disc, st, x, side) == want:
                    spot = (x, side)
                    break
            if spot:
                break
        if spot is None:
            print(f'finisher type $1CD4 = 0 (no {a.kind} found on stage ${a.stage:X})')
            sys.exit(1)
        from scd import Core
        from finishvideo import Rec
        c = Core(audio=True, saves=os.path.join(tmp, 'saves'))
        c.load(a.disc)
        c.load_state(st)
        real_run = c.run
        stageaudit.setup(c, *spot)                  # (not recorded: the walk to the spot)
        c.audio.clear()
        r = Rec(c, a.out)
        fin = ended = 0
        for f in range(3600):
            r.tick(1)
            m = r.ram()
            fin = fin or stageaudit.W(m, 0x31CD4)
            if not ended and m[0x30AB7] & 3 == 3:
                ended = f
            if ended and f > ended + a.tail or r.stats_seen:
                break
        r.close()
        c.run = real_run
    print(f'{a.kind} at x {spot[0]} (winner {spot[1]:+d} px); finisher type $1CD4 = {fin}; '
          f'{r.frames / c.fps:.1f}s -> {a.out}')
    sys.exit(0 if fin == want else 1)


if __name__ == '__main__':
    main()
