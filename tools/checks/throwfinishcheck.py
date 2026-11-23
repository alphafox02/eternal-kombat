#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""A throw that would win the match leaves the loser on FINISH HIM (patches.throw_finish).

Sub-Zero against Shadow, round 1 won with jabs, then in the deciding round Shadow on 4 health and
Sub-Zero's throw (toward + Y up close). EC takes a throw's damage in the thrown fighter's own module
as he lands; it set his health to 0 and the round ended with no FINISH HIM. Passes when she lands on
1 health and is dazed ($BE $1F) without the round ending.

    throwfinishcheck.py [--disc CUE]
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT

P1, P2 = 0x2E188, 0x2E330


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        st = os.path.join(tmp, 'duel.state')
        subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', a.disc,
                        '--p1', '15', '--p2', '0', '--out', st], check=True, capture_output=True)
        c = scd.Core(saves=os.path.join(tmp, 'saves'))
        c.load(a.disc)
        c.load_state(st)
        word = lambda o, f: int.from_bytes(c.prg_ram()[o + f:o + f + 2], 'big', signed=True)
        phase, t, thrown, log = 'round1', 0, None, []
        for f in range(4000):
            h, gap = word(P2, 0x76), word(P2, 0x4E) - word(P1, 0x4E)
            fwd = 'right' if gap > 0 else 'left'
            if phase == 'round1':                       # jabs on 4 health until she's out
                if h > 4:
                    c.poke_prg(P2 + 0x76, (4).to_bytes(2, 'big'))
                c.buttons[0] = {fwd} if abs(gap) > 58 else ({'x'} if f % 8 < 3 else set())
                if h == 0:
                    phase = 'between'
            elif phase == 'between':                    # the next round's start
                c.buttons[0] = set()
                if h > 50:
                    phase, t = 'wait', f
            elif phase == 'wait':
                if f - t >= 300:
                    phase = 'throw'
                    c.poke_prg(P2 + 0x76, (4).to_bytes(2, 'big'))
            else:
                if thrown is None:
                    c.buttons[0] = {fwd} if abs(gap) > 58 else {fwd, 'y'}
                    if abs(gap) <= 58:
                        thrown = f
                else:
                    c.buttons[0] = {fwd, 'y'} if f - thrown < 4 else set()
                    state = word(P2, 0xBE) & 0x7FFF
                    if not log or log[-1][1:] != (h, state):
                        log.append((f - thrown, h, state))
                    if state == 0x1F or state == 0x7FFF or f - thrown > 400:
                        break
            c.run(1)
    thrown_ok = any(s == 0x37 for _, _, s in log)
    ok = thrown_ok and bool(log) and log[-1][2] == 0x1F and log[-1][1] == 1
    print('after the throw (frame, health, state):', [(d, h, hex(s)) for d, h, s in log][:10])
    print(f'deciding throw: {"thrown, " if thrown_ok else "never thrown, "}'
          f'{"dazed on 1 (FINISH HIM)" if ok else "no FINISH HIM"} -> {"ok" if ok else "FAIL"}')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
