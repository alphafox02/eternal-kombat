#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Sonya's leg grab (MK CD: down + LP + LK, close, Block held or not; here down + X + A, Z or not).

From a 2-player duel (Sonya vs Shadow, made here with tools/lib/duelstate.py):
  - out of range: no throw (EC's own attack for the buttons);
  - close, down + X + A and down + X + A + Z: EC's throw (move $0D) showing her leg grab's arch
    (mkinputs.leg_plan), the victim thrown and damaged;
  - then an ordinary throw (toward + Y): her throw's poses again, not the leg grab's.

    leggrabcheck.py [--as-p2] [--state STATE]
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
import mkinputs, patches
from inputs import ROOT

P1, P2 = 0x2E188, 0x2E330
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big')
SHIFT = (patches.SONYA.sheet_base - 0x40) << 8
LEG = {f + SHIFT for f in mkinputs.leg_plan(patches.SONYA.mk_dir)[0]}
THROW = {f + SHIFT for f in mkinputs.THROW_LIST}
ARCH = max(mkinputs.leg_plan(patches.SONYA.mk_dir)[0], key=mkinputs.leg_plan(patches.SONYA.mk_dir)[0].count) + SHIFT


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--as-p2', action='store_true', help='Sonya is player 2')
    ap.add_argument('--state', help='a duel state (default: made now)')
    a = ap.parse_args()
    port = int(a.as_p2)
    me, him = (P2, P1) if a.as_p2 else (P1, P2)
    state = a.state
    if not state:
        state = os.path.join(tempfile.mkdtemp(), 'duel.state')
        p1, p2 = ('0', '16') if a.as_p2 else ('16', '0')
        subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'),
                        '--p1', p1, '--p2', p2, '--out', state], check=True, capture_output=True)
    c = scd.Core()
    c.load(os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    c.load_state(state)
    c.run(20)
    X = lambda o: W(c.prg_ram(), o + 0x4E)

    def act(btn, n=6, frames=100):
        c.buttons[port] = set(btn)
        states, frames_seen = set(), set()
        for f in range(frames):
            if f == n:
                c.buttons[port] = set()
            c.run(1)
            r = c.prg_ram()
            states.add(W(r, me + 0xBE) & 0x7FFF)
            if W(r, me + 0xBE) & 0x7FFF == mkinputs.THROW_MOVE:
                frames_seen.add(W(r, me + 0x1A))
        return states, frames_seen

    far_states, _ = act({'down', 'x', 'a'})
    far_ok = mkinputs.THROW_MOVE not in far_states
    print(f'out of range ({abs(X(him) - X(me))} px): {"no throw" if far_ok else "THREW"}')
    for _ in range(120):
        if abs(X(him) - X(me)) < 50:
            break
        c.buttons[port] = {'right' if X(him) > X(me) else 'left'}
        c.run(2)
    c.buttons[port] = set()
    c.run(10)
    near = c.snapshot()
    close_ok = True
    for btn in (('down', 'x', 'a'), ('down', 'x', 'a', 'z')):
        c.restore(near)
        hp = W(c.prg_ram(), him + 0x76)
        st, seen = act(set(btn))
        dmg = hp - W(c.prg_ram(), him + 0x76)
        ok_ = mkinputs.THROW_MOVE in st and ARCH in seen and not (seen & THROW - LEG) and dmg > 0
        close_ok &= ok_
        print(f'close, {" + ".join(btn)}: throw {mkinputs.THROW_MOVE in st}, arch shown {ARCH in seen}, '
              f'throw poses {sorted(hex(f) for f in seen & THROW - LEG)}, damage {dmg}')
    c.run(120)                                    # (she gets up)
    for _ in range(120):
        if abs(X(him) - X(me)) < 50:
            break
        c.buttons[port] = {'right' if X(him) > X(me) else 'left'}
        c.run(2)
    c.buttons[port] = set()
    c.run(10)
    fwd = 'right' if X(him) > X(me) else 'left'
    st, seen = act({fwd, 'y'})
    throw_ok = mkinputs.THROW_MOVE in st and not (seen & LEG - THROW) and bool(seen & THROW)
    print(f'then a throw: throw {mkinputs.THROW_MOVE in st}, leg grab poses {sorted(hex(f) for f in seen & LEG - THROW)}')
    ok = far_ok and close_ok and throw_ok
    print('leg grab ->', 'ok' if ok else 'FAILED')
    if not a.state:
        os.remove(state)
        os.rmdir(os.path.dirname(state))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
