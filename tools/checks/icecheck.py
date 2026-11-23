#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Sub-Zero's ice blast freezes, and a blocked one doesn't (as on MK CD).

In a 2-player duel (Sub-Zero player 1, Shadow player 2), Sub-Zero throws his ice blast (down,
forward + LP: EC's X) twice from the same state:
  - Shadow standing: she is frozen (EC's dazed move $1F held 40 frames or more), no damage;
  - Shadow holding back (blocking): she blocks it (EC's block, move 7) and is never frozen.
mkinputs.emit_freeze: EC calls the projectile's hit back for a blocked shot too.

    icecheck.py [--disc CUE]
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT

P1, P2 = 0x2E188, 0x2E330
SUBZERO_GRID, SHADOW_GRID = 15, 0
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big')
MOVE = lambda r, p: W(r, p + 0xBE) & 0x7FFF


def throw(c, state, p2_held):
    """Load the duel, have player 2 hold p2_held, throw the ice blast; (frames frozen, blocked, hp lost)."""
    c.load_state(state)
    c.run(30)
    hp = W(c.prg_ram(), P2 + 0x76)
    st = {'run': 0, 'frozen': 0, 'blocked': False}

    def watch(r):
        st['run'] = st['run'] + 1 if MOVE(r, P2) == 0x1F else 0
        st['frozen'] = max(st['frozen'], st['run'])
        st['blocked'] |= MOVE(r, P2) in (0x07, 0x0C)
    c.buttons[1] = set(p2_held)
    for held, n in (({'down'}, 3), ((), 2), ({'right'}, 3), ({'x'}, 4), ((), 150)):
        c.buttons[0] = set(held)
        for _ in range(n):
            c.run(1)
            watch(c.prg_ram())
    c.buttons = [set(), set()]
    return st['frozen'], st['blocked'], hp - W(c.prg_ram(), P2 + 0x76)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        state = os.path.join(tmp, 'duel.state')
        subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', a.disc,
                        '--p1', str(SUBZERO_GRID), '--p2', str(SHADOW_GRID), '--out', state],
                       check=True, capture_output=True)
        c = scd.Core(saves=os.path.join(tmp, 'saves'))
        c.load(a.disc)
        frozen, blocked, lost = throw(c, state, ())
        hit_ok = frozen >= 40 and lost == 0
        print(f'standing: frozen {frozen} frames, {lost} hp lost -> {"ok" if hit_ok else "FAIL"}')
        frozen, blocked, lost = throw(c, state, {'right'})
        block_ok = blocked and frozen == 0
        print(f'blocking: blocked {blocked}, frozen {frozen} frames -> {"ok" if block_ok else "FAIL"}')
    ok = hit_ok and block_ok
    print('icecheck:', 'ok' if ok else 'FAIL')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
