#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Where do our MK fighters lose MK's animation? (mk_fidelity_spec 0g)

For every MK fighter and every action (MK capture) his art uses: how many distinct poses
MK's recording shows (its order.txt, frame by frame: the stance before and after a move
counted as one), how many distinct poses our frame slots can show for it (scorpion_map's
assignments, spread as scorpion_full.pick does, plus the exact pins: scripts, drives), and
how long MK's animation runs. Static: the build's own tables, no emulator.

    animaudit.py [--top N]     -> the actions losing the most poses, worst first
"""
import argparse, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import numpy as np
from inputs import ROOT


def audit(spec):
    import patches, scorpion_full as sf, scorpion_map
    patches.use(spec)
    cfg = sf.CFG
    want = scorpion_map.assignments(cfg['aliases'], cfg['exact'], cfg['extra'])
    shown = {}
    for (sid, f), (action, k, n) in want.items():
        d = os.path.join(ROOT, 'extracted', sf.capture_dir(action), sf.CAPTURE_OF.get(action, action))
        if not os.path.exists(os.path.join(d, 'indexed.npy')):
            continue
        poses = np.load(os.path.join(d, 'indexed.npy'), mmap_mode='r')
        try:
            pose = sf.pick(poses, k, n, action)
        except Exception:
            continue
        shown.setdefault(action, set()).add(int(pose))
    rows = []
    for action, ours in shown.items():
        d = os.path.join(ROOT, 'extracted', sf.capture_dir(action), sf.CAPTURE_OF.get(action, action))
        op = os.path.join(d, 'order.txt')
        if not os.path.exists(op):
            continue
        order = [int(v) for v in open(op).read().split()]
        poses = np.load(os.path.join(d, 'indexed.npy'), mmap_mode='r')
        lead = sf.stance_lead(poses) if len(poses) >= 3 else 0
        mk = {k for k in order if k >= lead} | ({0} if lead else set())   # stance counted once
        ours_n = len({k for k in ours if k >= lead} | ({0} if any(k < lead for k in ours) else set()))
        rows.append((spec.key, action, len(mk), ours_n, len(order)))
    return rows


def main():
    import patches
    ap = argparse.ArgumentParser()
    ap.add_argument('--top', type=int, default=40)
    a = ap.parse_args()
    rows = []
    for sp in patches.MK_SPECS:
        if sp.key == 'shang':
            continue
        rows += audit(sp)
    rows.sort(key=lambda r: -(r[2] - r[3]))
    print(f'{"fighter":9s} {"action":16s} {"MK poses":>8s} {"ours":>5s} {"lost":>5s} {"MK frames":>9s}')
    for key, action, mk, ours, frames in rows[:a.top]:
        print(f'{key:9s} {action:16s} {mk:8d} {ours:5d} {mk - ours:5d} {frames:9d}')
    lost = sum(max(0, r[2] - r[3]) for r in rows)
    total = sum(r[2] for r in rows)
    print(f'\n{len(rows)} actions; MK poses {total}, ours show {total - lost} ({100 * (total - lost) // max(1, total)}%)')


if __name__ == '__main__':
    main()
