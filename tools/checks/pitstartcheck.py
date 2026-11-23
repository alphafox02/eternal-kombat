#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Reptile's fight starts on the Pit's bottom, not its bridge.

The Pit's stage task switched to the bottom (ecstage rbot) only from its watch, after its 300-frame
palette settle loop, so the fight faded in on the bridge with both fighters up there for about a
second, then cut to the spikes. rbot now runs from the settle loop's first frame when this fight's
picks include Reptile.

From the select screen to the live fight (tools/lib/duelstate.py, every frame sampled):
  - Kano against Reptile on the Pit: on every frame shown (not black) with Reptile's fighter object there,
    the floor line ($1496(a6)) is already the bottom's (PIT_REPTILE_FLOOR; it is set a frame after his
    object appears, on a black screen);
  - Kano against Shadow on the Pit: the floor line is never the bottom's (the bridge's fight stays up).

    pitstartcheck.py [--disc CUE]     (run after play.py test has made the disc's build/states/menu.state)
"""
import argparse, os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import numpy as np
import scd, duelstate
from inputs import ROOT

P1, P2 = 0x2E188, 0x2E330
FLOOR = 0x31496
BOTTOM = 757                  # patches.PIT_REPTILE_FLOOR
REPTILE = 26
KANO, SHADOW = 18, 0
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big')


def trace(disc, p2, p2_id):
    """[(floor, P1 id, P2 id, anything on screen)] every frame from the select screen to the live fight."""
    log = []
    run = scd.Core.run

    def sampled(self, n=1):
        for _ in range(n):
            run(self, 1)
            r = self.prg_ram()
            log.append((W(r, FLOOR), r[P1 + 0x4D], r[P2 + 0x4D], bool(np.asarray(self.frame).any())))
    scd.Core.run = sampled
    try:
        with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, 'build')) as tmp:
            sys.argv = ['duelstate.py', '--disc', disc, '--p1', str(KANO), '--p2', str(p2), '--stage', '1F',
                        '--out', os.path.join(tmp, 'duel.state')] + (['--p2-id', str(p2_id)] if p2_id else [])
            duelstate.main()
    finally:
        scd.Core.run = run
    return log


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    a = ap.parse_args()
    bad = []
    rep = trace(a.disc, SHADOW, REPTILE)
    seen = [k for k, (f, i1, i2, lit) in enumerate(rep) if REPTILE in (i1, i2) and lit]   # (shown: not black)
    early = [k for k in seen if rep[k][0] != BOTTOM]
    print(f'Kano vs Reptile on the Pit: Reptile on screen for {len(seen)} frames, the floor not the bottom\'s on '
          f'{len(early)} of them' + (f' (from frame {early[0]}: floor {rep[early[0]][0]})' if early else ''))
    if not seen:
        bad.append('no Reptile fight')
    elif early:
        bad.append(f'the bridge shown {len(early)} frames into Reptile\'s fight')
    plain = trace(a.disc, SHADOW, None)
    low = [k for k, (f, i1, i2, lit) in enumerate(plain) if f == BOTTOM]
    print(f'Kano vs Shadow on the Pit: floors {sorted({f for f, _, _, _ in plain})}; the bottom\'s on {len(low)} frames')
    if low:
        bad.append('a plain Pit fight went to the bottom')
    print('pitstartcheck:', 'FAIL ' + '; '.join(bad) if bad else 'ok')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
