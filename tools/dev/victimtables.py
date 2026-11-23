#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Find EC's per-victim pose tables (an entry per victim id 2-24).

Each entry holds frame words in THAT victim's sheets. An MK fighter (in a hidden
fighter's slot) has none of his host's frames, so every such table needs his
entry pointed at his own poses (patches.mk_throw_victims, mk_victim_poses);
one that isn't crashes the fight when the move lands on him (Xavier's energy
grab on Raiden: Chin Wo's frame 73:67).

Each victim's sheets come from the stock throw tables (patches.throw_table).
Two shapes are searched, in every stock module (.CO .OC .VC .BGI .AI):
  - fixed stride: entry i at t + stride * (i - 2), a frame word first;
  - offset tables (as the throw tables): 23 longs, offsets from t to records
    whose first word is a frame word.

    victimtables.py      -> the tables found; the ones the patches don't cover marked NEW
"""
import os, sys
from collections import Counter, defaultdict
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import patches
from inputs import ROOT

E = os.path.join(ROOT, 'extracted', 'ec_us')


def victim_sheets():
    """{victim id: lowest sheet} from the stock throw tables."""
    seen = defaultdict(Counter)
    for n in sorted(os.listdir(E)):
        if n.endswith('.CO'):
            co = open(os.path.join(E, n), 'rb').read()
            found = patches.throw_table(co)
            if found:
                t, size, e = found
                for i in range(23):
                    for st in range(0, size, 10):
                        seen[i + 2][co[t + e[i] + st]] += 1
    return {i: min(s for s in c if s) for i, c in seen.items()}


def main():
    lo = victim_sheets()
    ok = lambda i, b: lo[i] <= b < lo[i] + 6
    near = lambda n, t: any(n == m and u <= t < u + size for m, u, size, _ in patches.VICTIM_POSES) \
        or any(n == m and u == t for m, u, _ in patches.VICTIM_STEPS)
    out = []
    for n in sorted(os.listdir(E)):
        if n.split('.')[-1] not in ('CO', 'OC', 'VC', 'BGI', 'AI'):
            continue
        b = open(os.path.join(E, n), 'rb').read()
        throw = patches.throw_table(b) if n.endswith('.CO') else None
        for stride in range(2, 82, 2):              # (Midknight's Vendetta: 66)
            for t in range(0, len(b) - 23 * stride):
                f = [b[t + stride * (i - 2)] for i in range(2, 25)]
                # (an id with no record of its own - Trident's, Midknight's Vendettas - is zeros)
                if ok(9, f[7]) and ok(19, f[17]) and sum(ok(i, f[i - 2]) for i in range(2, 25)) >= 12 \
                        and sum(ok(i, f[i - 2]) or not f[i - 2] for i in range(2, 25)) >= 21:
                    out.append((n, t, f'stride {stride}'))
        for t in range(0, len(b) - 92, 2):
            e = [int.from_bytes(b[t + 4 * i:t + 4 * i + 4], 'big', signed=True) for i in range(23)]
            if min(e) < 92 or max(e) > 0x3000:
                continue
            if sum(ok(i + 2, b[t + e[i]]) for i in range(23) if t + e[i] < len(b)) >= 19:
                out.append((n, t, 'throw table' if throw and throw[0] == t else 'offset table'))
    for n, t, kind in out:
        mark = '' if kind == 'throw table' or near(n, t) else '  (the Senator: Scorpion has his own SEN.CO)' \
            if n == 'SEN.CO' else '  NEW'
        print(f'{n:8s} ${t:04X}  {kind}{mark}')


if __name__ == '__main__':
    main()
