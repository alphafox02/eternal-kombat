#!/usr/bin/env python3
"""Does the Pit's fall work for every pairing? For each (winner, loser) on the
Pit (tools/duelstate.py --stage 13), the deciding round is set up (one round
each, the loser on low health), the winner walks in and uppercuts (down + Y,
repeated until the loser is down), and the loser must end up on the spikes:
the camera at the pit's floor and the loser lying there.

    pitcheck.py                       # the default pairings
    pitcheck.py 0:14 7:0              # winner:loser by select-grid presses

Grid presses: 0 Shadow, 1 Larcen, 4 Trident, 6 Xavier, 7 Raiden, 8 Blade,
9 Jetta, 11 Ramses, 14 Scorpion, 15 Sub-Zero, 16 Johnny Cage.
"""
import os, subprocess, sys, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scd
from inputs import ROOT

P1, P2 = 0x2E188, 0x2E330
CAM_Y = 0x2B074
NAMES = {0: 'Shadow', 1: 'Larcen', 4: 'Trident', 6: 'Xavier', 7: 'Raiden', 8: 'Blade', 9: 'Jetta',
         11: 'Ramses', 14: 'Scorpion', 15: 'Sub-Zero', 16: 'Johnny'}
PAIRS = [(14, 0), (0, 14), (7, 0), (15, 9), (16, 4), (0, 1), (8, 15)]
w = lambda r, a: int.from_bytes(r[a:a + 2], 'big')
sw = lambda r, a: int.from_bytes(r[a:a + 2], 'big', signed=True)


def check(c, state):
    c.load_state(state)
    c.run(30)
    c.poke_prg(0x31D26, (1).to_bytes(2, 'big'))       # one round each: this one decides it
    c.poke_prg(0x31D28, (1).to_bytes(2, 'big'))
    c.poke_prg(P2 + 0x76, (1).to_bytes(2, 'big'))
    for _ in range(300):                              # walk in
        r = c.prg_ram()
        if abs(sw(r, P2 + 0x4E) - sw(r, P1 + 0x4E)) <= 50:
            break
        c.buttons[0] = {'right' if sw(r, P2 + 0x4E) > sw(r, P1 + 0x4E) else 'left'}
        c.run(1)
    c.buttons[0] = set()
    best_cam, lay = 0, False
    for attempt in range(6):                          # uppercuts (EC's FINISH HIM grace may eat one)
        for held, n in ((['down'], 8), (['down', 'y'], 4), (['down'], 10)):
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
    c = scd.Core(saves=os.path.join(ROOT, 'shots', 'probe-saves'))
    c.load(os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    bad = 0
    try:
        for p1, p2 in pairs:
            st = os.path.join(tmp, f'{p1}_{p2}.state')
            subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'duelstate.py'),
                            '--p1', str(p1), '--p2', str(p2), '--stage', '13', '--out', st],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            cam, lay, y, frame = check(c, st)
            ok = cam >= 500 and lay
            bad += not ok
            print(f'{NAMES.get(p1, p1):9s} uppercuts {NAMES.get(p2, p2):9s}: camera down to {cam}, '
                  f'loser at y {y}, {"lying on the spikes" if lay else "NOT down there"}'
                  + ('' if ok else '   <-- FAIL'), flush=True)
            from PIL import Image
            Image.fromarray(frame).save(os.path.join(ROOT, 'shots', f'pitcheck_{p1}_{p2}.png'))
    finally:
        shutil.rmtree(tmp)
    raise SystemExit(1 if bad else 0)


if __name__ == '__main__':
    main()
