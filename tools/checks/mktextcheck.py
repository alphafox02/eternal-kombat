#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""MK's FIGHT! and FINISH HIM / FINISH HER on MK's stages (tools/lib/mkstages.py's text director).

For each stage (Scorpion against Shadow - FINISH HER - and against Larcen - FINISH HIM):
  - FIGHT!: from the menu into a duel on the stage, the text's letters come up once the fight
    begins (EC's BEGIN CONTEST over) - six of them, growing (their frames change) - and are gone
    within MK's time; the fight goes on (player 1 moves);
  - round 2: round 1 lost, FIGHT! again when round 2's fight begins (not at the fight flag's short
    blink between the rounds);
  - FINISH HIM / HER: one round each, the loser on 3 health jabbed to FINISH HIM: within a few frames
    of the daze the word's letters come up (nine), drawn in the stage's red, grow, and are gone
    again within MK's time.
The text's letters are told from other sprites by their tiles: each letter object's VRAM block
shows one of the text sheet's letters (mkstages.text_art), in palette line 0.

    mktextcheck.py [--stages courtyard,throne] [--disc CUE]
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import numpy as np
import scd
from inputs import ROOT
from vdp import VDPState
import mkstages, patches

P1, P2 = 0x2E188, 0x2E330
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big', signed=True)
SHADOW, LARCEN = 0, 1
TEXT_TIME = 140                         # frames the text may stay (MK's: 113 FIGHT!, 85-94 FINISH)


def letters(c):
    """The text's sprites on screen: pal 0, high priority, in the top third, not the HUD's."""
    v = VDPState(c.snapshot())
    return [s for s in v.sprites() if s['pal'] == 0 and s['prio'] and 24 < s['y'] < 100 and s['x'] < 330]


def watch(c, frames):
    seen = []
    for _ in range(frames):
        c.run(1)
        seen.append(len(letters(c)))
    return seen


def fight(c, key, disc):
    """FIGHT!: from the menu (as duelstate.py walks it, the pick fixed on key)."""
    keys = [k for k, _, _ in mkstages.STAGES]
    table = b''.join((patches.PIT_MODE if k == 'pit' else mkstages.MODE).to_bytes(2, 'big') for k in keys) + \
        bytes(mkstages.PACKED.index(k) if k in mkstages.PACKED else 0 for k in keys)
    c.load_state(os.path.join(ROOT, 'build', 'states', 'menu.state'))
    at = c.prg_ram().find(table, 0x6000, 0x14000)
    c.poke_prg(at, mkstages.MODE.to_bytes(2, 'big') * len(keys) + bytes([mkstages.PACKED.index(key)]) * len(keys))
    c.press(['start']); c.run(240); c.press(['down']); c.run(20); c.press(['start']); c.run(240)
    c.press(['start'], port=1); c.run(40)
    for _ in range(20):
        c.press(['right']); c.run(20)
    c.press(['start']); c.run(40); c.press(['start'], port=1)
    c.run(300); c.press(['start']); c.run(400); c.press(['start'])
    flag = []
    seen = []
    for _ in range(900):
        c.run(1)
        flag.append(c.prg_ram()[mkstages.FIGHT_FLAG] & 0x40)
        seen.append(len(letters(c)))
    begins = next((f for f in range(1, len(flag)) if flag[f] and not flag[f - 1]), None)
    bad = []
    if begins is None:
        return ['the fight never began (FIGHT_FLAG)']
    up = [f for f, n in enumerate(seen) if n >= 6]
    if not up or not begins <= up[0] <= begins + 14:          # (the director waits 4 ticks of it)
        bad.append(f'FIGHT!: six letters {"at frame " + str(up[0]) if up else "never"} (the fight began at {begins})')
    elif up[-1] - up[0] > TEXT_TIME or any(seen[up[-1] + 4:]):
        bad.append(f'FIGHT!: up frames {up[0]}-{up[-1]}, not gone after')
    x0 = W(c.prg_ram(), P1 + 0x4E)
    c.buttons[0] = {'right'}
    c.run(20)
    c.buttons[0] = set()
    if W(c.prg_ram(), P1 + 0x4E) == x0:
        bad.append('after FIGHT!, player 1 doesn\'t move')
    return bad


def round2(c, disc, tmp, key):
    """Round 1 lost (a jab on 3 health), round 2's FIGHT! once its fight begins - not at the flag's
    short blink between the rounds - and gone."""
    st = os.path.join(tmp, f'{key}_r2.state')
    subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', disc,
                    '--p1', '20', '--p2', str(LARCEN), '--mk-stage', key, '--out', st], check=True, capture_output=True)
    c.load_state(st)
    c.run(30)
    c.poke_prg(P2 + 0x76, (3).to_bytes(2, 'big'))
    for _ in range(400):
        r = c.prg_ram()
        if abs(W(r, P2 + 0x4E) - W(r, P1 + 0x4E)) < 40:
            break
        c.buttons[0] = {'right'}
        c.run(1)
    c.buttons[0] = set()
    c.run(20)
    c.buttons[0] = {'x'}
    c.run(4)
    c.buttons[0] = set()
    flag, seen = [], []
    for _ in range(1500):
        c.run(1)
        flag.append(c.prg_ram()[mkstages.FIGHT_FLAG] & 0x40)
        seen.append(len(letters(c)))
    rises = [f for f in range(1, len(flag)) if flag[f] and not flag[f - 1]]
    up = [f for f, n in enumerate(seen) if n >= 6]
    if len(rises) < 2:
        return [f'round 2: the fight never began again (flag rises {rises})']
    begins = rises[-1]
    if not up or not begins <= up[0] <= begins + 14 or up[-1] - up[0] > TEXT_TIME:
        return [f'round 2: FIGHT!\'s letters {f"at {up[0]}-{up[-1]}" if up else "never"} (the fight began at {begins}, '
                f'the flag rose at {rises})']
    return []


def finish(c, disc, tmp, key, victim):
    st = os.path.join(tmp, f'{key}_{victim}.state')
    subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', disc,
                    '--p1', '20', '--p2', str(victim), '--mk-stage', key, '--out', st], check=True, capture_output=True)
    c.load_state(st)
    c.run(30)
    c.poke_prg(0x31D26, (1).to_bytes(2, 'big'))
    c.poke_prg(0x31D28, (1).to_bytes(2, 'big'))
    c.poke_prg(P2 + 0x76, (3).to_bytes(2, 'big'))
    for _ in range(400):
        r = c.prg_ram()
        if abs(W(r, P2 + 0x4E) - W(r, P1 + 0x4E)) < 40:
            break
        c.buttons[0] = {'right'}
        c.run(1)
    c.buttons[0] = set()
    c.run(20)
    c.buttons[0] = {'x'}
    c.run(4)
    c.buttons[0] = set()
    dazed, seen = None, []
    for f in range(300):
        c.run(1)
        r = c.prg_ram()
        if dazed is None and (W(r, P2 + 0xBE) & 0x7FFF) == mkstages.DAZED and W(r, P2 + 0x76) <= 1:
            dazed = f
        seen.append(len(letters(c)))
    word = 'FINISH HER' if victim == SHADOW else 'FINISH HIM'
    if dazed is None:
        return [f'{word}: no daze']
    up = [f for f, n in enumerate(seen) if n >= 9]
    if not up or not dazed <= up[0] <= dazed + 8:
        return [f'{word}: nine letters {"at frame " + str(up[0]) if up else "never"} (dazed at {dazed})']
    if up[-1] - up[0] > TEXT_TIME or any(seen[up[-1] + 4:]):
        return [f'{word}: up frames {up[0]}-{up[-1]}, not gone after']
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stages', default=','.join(mkstages.PACKED))
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    a = ap.parse_args()
    failed = False
    with tempfile.TemporaryDirectory(prefix='ek-mktext-') as tmp:
        c = scd.Core(saves=os.path.join(tmp, 'saves'))
        c.load(a.disc)
        for key in a.stages.split(','):
            bad = fight(c, key, a.disc) + round2(c, a.disc, tmp, key) + finish(c, a.disc, tmp, key, SHADOW) + \
                finish(c, a.disc, tmp, key, LARCEN)
            print(f'{key}: ' + ('ok' if not bad else 'FAILED\n  ' + '\n  '.join(bad)), flush=True)
            failed |= bool(bad)
    print('MK text:', 'FAILED' if failed else 'ok')
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
