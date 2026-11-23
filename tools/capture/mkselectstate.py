#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Make build/states/mk_select.state from a cold boot of your MK CD (US).

The character-select screen every MK capture starts from (tools/capture/mkduelstate.py).

The route: BIOS screen, Sega logo, MK's credits, 'Midway presents', the title
menu, then Start -> 'choose your fighter'. Start is pressed every 4 s; the
select screen is recognised by its stone background reaching the screen's
edges (the title menu has portraits there; measured: 0.83 vs <= 0.1), then
left to settle (its CD reads done: a state saved mid-read restores broken).

    mkselectstate.py [--out PATH]        -> build/states/mk_select.state
"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT, require

OUT = os.path.join(ROOT, 'build', 'states', 'mk_select.state')
SAVES = os.path.join(ROOT, 'build', 'saves', 'mk')


def stone(frame):
    """The share of the screen that's MK's grey-brown stone."""
    f = np.asarray(frame)[::2, ::2].astype(int)
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    grey = (abs(r - g) < 30) & (abs(g - b) < 45) & (r > 60) & (r < 200)
    return grey.mean()


def at_select(frame):
    f = np.asarray(frame)
    if f.ndim < 3 or f.shape[1] < 320:       # (no picture yet; the BIOS screen is narrower)
        return False
    return min(stone(f[30:200, 0:36]), stone(f[30:200, 284:320])) > 0.5


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=OUT)
    out = ap.parse_args().out
    os.makedirs(SAVES, exist_ok=True)
    c = scd.Core(saves=SAVES)
    c.load(require('mk_us').cue)
    found = None
    for t in range(60 * 120):
        if found is None and t > 600 and t % 240 == 0:
            c.buttons[0] = {'start'}
        elif t % 240 == 3:
            c.buttons[0] = set()
        c.run(1)
        if found is None and t % 10 == 0 and at_select(c.frame):
            found = t
        if found is not None and t >= found + 600:
            break
    else:
        sys.exit('MK: no select screen within 2 minutes')
    c.save_state(out)
    print(f'select screen at frame {found} -> {os.path.relpath(out, ROOT)}')


if __name__ == '__main__':
    main()
