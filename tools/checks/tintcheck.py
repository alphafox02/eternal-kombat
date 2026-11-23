#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Riptide's bubble tints an MK fighter evenly, from his own colours.

EC fades a fighter it catches to one of his module's tint palettes (patches.tint_palette: an MK
fighter's own colours mapped onto the tint's). With Blade's, made for his art's slots, Kano came out
in red and blue blotches. From a 2-player duel, Kano (player 1) against Riptide (player 2),
Riptide's bubble (down, down-forward, forward + Y) twice:
  - Kano's palette line fades (most of its slots change);
  - at the deepest tint no shade is red (red 3+ steps over blue; spark slots
    12/13 aside); Blade's put pure red in Kano's white;
  - his own colours come back afterwards (EC keeps a caught fighter tinted 10-20 s: Blade too).

    tintcheck.py [--disc CUE]     (run after play.py test has made the disc's build/states/menu.state)
"""
import argparse, ctypes as C, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd, cpuregs
from inputs import ROOT

KANO, RIPTIDE = 18, 10              # select-grid right presses
BUBBLE = [({'down'}, 4), ({'down', 'left'}, 4), ({'left', 'y'}, 4)]   # player 2 faces left


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    a = ap.parse_args()
    with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, 'build')) as tmp:
        st = os.path.join(tmp, 'duel.state')
        subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', a.disc,
                        '--p1', str(KANO), '--p2', str(RIPTIDE), '--out', st], check=True, capture_output=True)
        c = scd.Core()
        c.load(a.disc)
        c.load_state(st)
    sym = cpuregs._symbols(c.lib._name)
    cram_at = C.cast(c.lib.retro_init, C.c_void_p).value - sym['retro_init'] + sym['cram']

    def lines():                     # the core's CRAM: 9-bit BBBGGGRRR words, 16 per line
        b = C.string_at(cram_at, 0x80)
        w = [int.from_bytes(b[i:i + 2], 'little') for i in range(0, 0x80, 2)]
        return [w[16 * n:16 * n + 16] for n in range(4)]
    own = lines()
    frames = []
    for held, n in BUBBLE + [(set(), 40)] + BUBBLE + [(set(), 1500)]:
        c.buttons[1] = set(held)
        for _ in range(n):
            c.run(1)
            frames.append(lines())
    c.buttons[1] = set()
    # Kano's line: the one that changes most from its start
    line = max(range(4), key=lambda n: max(sum(a != b for a, b in zip(f[n], own[n])) for f in frames))
    changed = [sum(a != b for a, b in zip(f[line], own[line])) for f in frames]
    far = lambda p: sum(abs((a >> s & 7) - (b >> s & 7)) for a, b in zip(p, own[line]) for s in (0, 3, 6))
    deepest = max(range(len(frames)), key=lambda k: far(frames[k][line]))   # (the fade's end)
    pal = frames[deepest][line]
    red = [i for i in range(1, 16) if i not in (12, 13) and (pal[i] & 7) - (pal[i] >> 6 & 7) >= 3]
    back = frames[-1][line] == own[line]
    fmt = lambda p: ' '.join('%d%d%d' % (v >> 6 & 7, v >> 3 & 7, v & 7) for v in p)
    print(f'line {line}: own    {fmt(own[line])}')
    print(f'        deepest {fmt(pal)}  ({changed[deepest]} slots changed, frame {deepest})')
    bad = []
    if changed[deepest] < 10:
        bad.append(f'the bubble barely tinted him ({changed[deepest]} slots)')
    if red:
        bad.append(f'slots {red} redder than blue in the tint')
    if not back:
        bad.append('his own colours never came back')
    print('tintcheck:', 'FAIL ' + '; '.join(bad) if bad else 'ok')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
