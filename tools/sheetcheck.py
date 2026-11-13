#!/usr/bin/env python3
"""Check that Scorpion never shows a frame on Blade's art sheets ($40-$43).

Scorpion's art lives on his own sheets ($8D-$90, patches.renumber_sheets);
a frame word in his module that was missed would still point at $40-$43:
Blade's art when Blade is the opponent, nothing (a crash) otherwise. This
plays every action of tools/ecprobe.py plus MK specials, at range and up
close, as Scorpion (player 1) vs Shadow, and reports any such frame; Shadow
also does every action at him (idle, then blocking). Every frame he showed
goes to extracted/ec_probe/scorpion_seen.json (Blade's numbering).

    sheetcheck.py            # needs states/duel_shadow.state (duelstate.py --p2 0)
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scd
from inputs import ROOT
from ecprobe import ACTIONS, F, B

P1, P2 = 0x2E188, 0x2E330
BLADE_ART = range(0x40, 0x44)
SHIFT = 0x4D                       # patches.SHEET_SHIFT: Scorpion's sheets, written in Blade's numbering
EXTRA = {
    'spear':     [([B], [], 3), ([], [], 3), ([B], [], 2), ([B, 'x'], [], 4), ([], [], 90)],
    'teleport':  [(['down'], [], 3), ([], [], 2), ([B], [], 3), (['y'], [], 4), ([], [], 90)],
    'uppercut':  [(['down'], [], 8), (['down', 'y'], [], 4), (['down'], [], 6), ([], [], 90)],
    'block_z':   [(['z'], [], 40), ([], [], 10)],
}


def x(r, o):
    return int.from_bytes(r[o + 0x4E:o + 0x50], 'big', signed=True)


def main():
    c = scd.Core(saves=os.path.join(ROOT, 'shots', 'probe-saves'))
    c.load(os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    state = os.path.join(ROOT, 'states', 'duel_shadow.state')
    bad = {}
    seen = set()
    actions = dict(ACTIONS)
    actions.update(EXTRA)
    # Shadow does every action at him too (hit, swept, knocked down, thrown),
    # with him idle or blocking: his frames as the victim
    mirror = {F: B, B: F}
    for name, steps in ACTIONS.items():
        theirs = [([], [mirror.get(b, b) for b in p1], n) for p1, p2, n in steps]
        actions['vs_' + name] = theirs
        actions['vs_' + name + '_blocked'] = [([B], p2, n) for _, p2, n in theirs]
    for close in (False, True):
        for name, steps in actions.items():
            c.load_state(state)
            c.run(20)
            if close:
                for _ in range(200):
                    r = c.prg_ram()
                    if x(r, P2) - x(r, P1) <= 50:
                        break
                    c.buttons[0] = {F}
                    c.run(1)
                c.buttons[0] = set()
                c.run(10)
            for p1, p2, n in steps:
                c.buttons[0], c.buttons[1] = set(p1), set(p2)
                for _ in range(n):
                    c.run(1)
                    r = c.prg_ram()
                    f = (r[P1 + 0x1A], r[P1 + 0x1B])
                    seen.add(f)
                    if f[0] in BLADE_ART:
                        bad.setdefault(f, set()).add(name + (' (close)' if close else ''))
            c.buttons = [set(), set()]
    sheets = sorted({s for s, _ in seen})
    print(f'{len(seen)} distinct frames on sheets {[hex(s) for s in sheets]}')
    for sh in sheets:
        print(f'  sheet {sh:02x}:', ' '.join(f'{f:02x}' for s, f in sorted(seen) if s == sh))
    out = os.path.join(ROOT, 'extracted', 'ec_probe', 'scorpion_seen.json')
    json.dump(sorted(f'{s - SHIFT:02x}:{f:02x}' for s, f in seen if s >= SHIFT), open(out, 'w'))
    if bad:
        for f, names in sorted(bad.items()):
            print(f'  Blade sheet frame {f[0]:02x}:{f[1]:02x} in {sorted(names)}')
        raise SystemExit(1)
    print('ok: no frame on Blade\'s art sheets')


if __name__ == '__main__':
    main()
