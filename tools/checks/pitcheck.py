#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Does the Pit's fall work for every pairing?

For each (winner, loser) on the Pit (tools/lib/duelstate.py --stage 1F), the
deciding round is set up (one round each, the loser on low health), the winner
walks in and uppercuts (down + Y, repeated until the loser is down), and the
loser must end up on the spikes: the camera at the pit's floor and the loser
lying there.

    pitcheck.py                       # the default pairings
    pitcheck.py 0:20 7:0              # winner:loser by select-grid presses

Grid presses: 0 Shadow, 1 Larcen, 4 Trident, 6 Xavier, 7 Raiden, 8 Blade,
9 Jetta, 11 Ramses, 14 Blast, 20 Scorpion, 15 Sub-Zero, 16 Sonya, 17 Liu Kang, 18 Kano, 19 Johnny Cage.
"""
import os, subprocess, sys, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT

P1, P2 = 0x2E188, 0x2E330
CAM_Y = 0x2B074
NAMES = {0: 'Shadow', 1: 'Larcen', 4: 'Trident', 6: 'Xavier', 7: 'Raiden', 8: 'Blade', 9: 'Jetta',
         11: 'Ramses', 14: 'Blast', 20: 'Scorpion', 15: 'Sub-Zero', 16: 'Sonya', 17: 'Liu Kang', 18: 'Kano', 19: 'Johnny'}
PAIRS = [(20, 0), (0, 20), (7, 0), (15, 9), (16, 4), (0, 1), (8, 15)]
w = lambda r, a: int.from_bytes(r[a:a + 2], 'big')
sw = lambda r, a: int.from_bytes(r[a:a + 2], 'big', signed=True)


MK_GRID = (7, 20, 15, 16, 17, 18, 19)   # MK winners: MK's rule - FINISH HIM first (tools/dev/pitvideo.py)


def check(c, state, mk=False):
    c.load_state(state)
    c.run(30)
    c.poke_prg(0x31D26, (1).to_bytes(2, 'big'))       # one round each: this one decides it
    c.poke_prg(0x31D28, (1).to_bytes(2, 'big'))
    c.poke_prg(P2 + 0x76, (3 if mk else 1).to_bytes(2, 'big'))
    if mk:                                            # a jab leaves her dazed on 1: FINISH HIM
        for _ in range(300):
            r = c.prg_ram()
            if abs(sw(r, P2 + 0x4E) - sw(r, P1 + 0x4E)) <= 45:
                break
            c.buttons[0] = {'right' if sw(r, P2 + 0x4E) > sw(r, P1 + 0x4E) else 'left'}
            c.run(1)
        c.buttons[0] = {'x'}
        c.run(4)
        c.buttons[0] = set()
        for _ in range(90):
            c.run(1)
            if w(c.prg_ram(), P2 + 0xBE) & 0x7FFF == 0x1F:
                break
        c.run(50)
    for _ in range(300):                              # walk in
        r = c.prg_ram()
        if abs(sw(r, P2 + 0x4E) - sw(r, P1 + 0x4E)) <= 50:
            break
        c.buttons[0] = {'right' if sw(r, P2 + 0x4E) > sw(r, P1 + 0x4E) else 'left'}
        c.run(1)
    c.buttons[0] = set()
    best_cam, lay = 0, False
    for attempt in range(6):                          # uppercuts (EC's FINISH HIM grace may eat one)
        # EC crouches on a fresh press of down from idle (tools/dev/pitvideo.py): step in
        # (the jab pushed her back), wait until he's idle, press it until he's really
        # crouching ($BE 9), then the uppercut
        for _ in range(200):
            r = c.prg_ram()
            if abs(sw(r, P2 + 0x4E) - sw(r, P1 + 0x4E)) <= 56:
                break
            c.buttons[0] = {'right' if sw(r, P2 + 0x4E) > sw(r, P1 + 0x4E) else 'left'}
            c.run(1)
        c.buttons[0] = set()
        c.run(6)
        for _ in range(8):
            c.buttons[0] = set()
            for _ in range(60):
                if w(c.prg_ram(), P1 + 0xBE) == 0:
                    break
                c.run(1)
            c.run(2)
            for _ in range(12):
                c.buttons[0] = {'down'}
                c.run(1)
                if w(c.prg_ram(), P1 + 0xBE) & 0x7FFF == 9:
                    break
            if w(c.prg_ram(), P1 + 0xBE) & 0x7FFF == 9:
                break
        c.buttons[0] = {'down'}
        c.run(6)
        for held, n in ((['down', 'y'], 4), (['down'], 10)):
            c.buttons[0] = set(held)
            c.run(n)
        c.buttons[0] = set()
        for _ in range(400):
            c.run(1)
            r = c.prg_ram()
            best_cam = max(best_cam, w(r, CAM_Y))
            if best_cam >= 500 and w(r, P2 + 0xBE) == 0x7FFF:
                lay = True
                break
        if lay or best_cam >= 500:
            break
        r = c.prg_ram()
        if w(r, P2 + 0xBE) & 0x7FFF not in (0x1C, 0x7FFF):   # standing or dazed (MK's FINISH HIM): back in
            for _ in range(200):
                r = c.prg_ram()
                if abs(sw(r, P2 + 0x4E) - sw(r, P1 + 0x4E)) <= 50:
                    break
                c.buttons[0] = {'right' if sw(r, P2 + 0x4E) > sw(r, P1 + 0x4E) else 'left'}
                c.run(1)
            c.buttons[0] = set()
    r = c.prg_ram()
    return best_cam, lay, sw(r, P2 + 0x52), c.frame


def main():
    pairs = [tuple(int(v) for v in a.split(':')) for a in sys.argv[1:]] or PAIRS
    tmp = tempfile.mkdtemp()
    c = scd.Core(saves=os.path.join(ROOT, 'build', 'shots', 'probe-saves'))
    c.load(os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    bad = 0
    try:
        for p1, p2 in pairs:
            st = os.path.join(tmp, f'{p1}_{p2}.state')
            subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'),
                            '--p1', str(p1), '--p2', str(p2), '--stage', '1F', '--out', st],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            cam, lay, y, frame = check(c, st, p1 in MK_GRID)
            ok = cam >= 500 and lay
            bad += not ok
            print(f'{NAMES.get(p1, p1):9s} uppercuts {NAMES.get(p2, p2):9s}: camera down to {cam}, '
                  f'loser at y {y}, {"lying on the spikes" if lay else "NOT down there"}'
                  + ('' if ok else '   <-- FAIL'), flush=True)
            from PIL import Image
            Image.fromarray(frame).save(os.path.join(ROOT, 'build', 'shots', f'pitcheck_{p1}_{p2}.png'))
    finally:
        shutil.rmtree(tmp)
    raise SystemExit(1 if bad else 0)


if __name__ == '__main__':
    main()
