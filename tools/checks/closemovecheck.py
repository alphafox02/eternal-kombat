#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""MK fighters' close moves: MK CD's own up close (mkscripts CLOSE_ACTIONS).

Up close, MK CD's punches are one close punch (Kano's: his headbutt) and its low kick a knee (Sonya's
shows her far low kick's poses); here X and Y (EC's close moves $20 / $21) and A ($23). Raiden keeps
the far ones (no room in his .PL: mkscripts.CLOSE_DIRS). For each MK fighter, in 2-player duels with
Shadow, on both sides, next to her: each button plays its close move, the frames shown are its
script's (mkscripts.build: the close capture's poses, Blade's strike frame), and Shadow loses health.
Then at FINISH HIM (Shadow dazed on 1 health where his jab left her, ~50-66 px: EC's close range runs to
~70 px, and MK's close moves are short - their boxes reach as far as the far moves', scorpion_full
CLOSE_REACH), X, Y and A each finish her.

    closemovecheck.py [--fighters kano,sonya] [--disc CUE]
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT

P = (0x2E188, 0x2E330)                  # the fighters
GRID = {'scorpion': 20, 'raiden': 7, 'johnny': 19, 'subzero': 15, 'liukang': 17, 'kano': 18, 'sonya': 16}
SHADOW = 0
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big')
SW = lambda r, o: int.from_bytes(r[o:o + 2], 'big', signed=True)
MOVE = lambda r, p: W(r, p + 0xBE) & 0x7FFF
BUTTONS = (('x', 0x20), ('y', 0x21), ('a', 0x23))


def duel(disc, tmp, p1, p2):
    st = os.path.join(tmp, f'{p1}_{p2}.state')
    subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', disc,
                    '--p1', str(p1), '--p2', str(p2), '--out', st], check=True, capture_output=True)
    return st


def walk_up(c, port):
    me, other = P[port], P[1 - port]
    for _ in range(400):
        r = c.prg_ram()
        if abs(SW(r, other + 0x4E) - SW(r, me + 0x4E)) < 40:
            break
        c.buttons[port] = {'right' if port == 0 else 'left'}
        c.run(1)
    c.buttons[port] = set()
    c.run(20)


def expected(spec):
    """{move: [frame words shown, in order]} from his attack scripts, in his sheets' numbering."""
    import mkscripts
    co = open(os.path.join(ROOT, 'extracted', 'ec_us', 'BLA.CO'), 'rb').read()
    scripts = mkscripts.build(co, spec.mk_dir)[0]
    shift = spec.sheet_base - 0x40
    out = {}
    for _, mid in BUTTONS:
        s = scripts[mid]
        frames = [W(s, o) for o in range(20, len(s) - 12, 12)]
        frames = [((f >> 8) + shift) << 8 | (f & 0xFF) for f in frames]
        out[mid] = [f for k, f in enumerate(frames) if not k or frames[k - 1] != f]
    return out


def fighter(c, disc, tmp, who, spec):
    bad = []
    want = expected(spec)
    for port in (0, 1):
        st = duel(disc, tmp, GRID[who], SHADOW) if port == 0 else duel(disc, tmp, SHADOW, GRID[who])
        c.load_state(st)
        c.run(30)
        walk_up(c, port)
        near = c.snapshot()
        for button, mid in BUTTONS:
            c.restore(near)
            before = W(c.prg_ram(), P[1 - port] + 0x76)
            shown = []
            for frame in range(90):
                c.buttons[port] = {button} if frame < 4 else set()
                c.run(1)
                r = c.prg_ram()
                if MOVE(r, P[port]) == mid:
                    f = W(r, P[port] + 0x1A)
                    if not shown or shown[-1] != f:
                        shown.append(f)
            after = W(c.prg_ram(), P[1 - port] + 0x76)
            hexs = lambda fs: ' '.join(f'{f:04X}' for f in fs)
            if shown != want[mid]:
                bad.append(f'player {port + 1} up close {button.upper()}: frames {hexs(shown) or "(move never ran)"}, '
                           f'its script {hexs(want[mid])}')
            elif after >= before:
                bad.append(f'player {port + 1} up close {button.upper()}: Shadow not hurt ({before} -> {after})')
        for button, mid in BUTTONS:                   # FINISH HIM: the dazed victim where the jab left her
            c.load_state(st)
            c.run(30)
            c.poke_prg(0x31D26, (1).to_bytes(2, 'big'))   # one round each: this one decides it
            c.poke_prg(0x31D28, (1).to_bytes(2, 'big'))
            c.poke_prg(P[1 - port] + 0x76, (3).to_bytes(2, 'big'))
            walk_up(c, port)
            c.buttons[port] = {'x'}
            c.run(4)
            c.buttons[port] = set()
            for _ in range(120):
                c.run(1)
                if MOVE(c.prg_ram(), P[1 - port]) == 0x1F:
                    break
            c.run(60)
            r = c.prg_ram()
            gap, hp = abs(SW(r, P[1] + 0x4E) - SW(r, P[0] + 0x4E)), W(r, P[1 - port] + 0x76)
            c.buttons[port] = {button}
            c.run(4)
            c.buttons[port] = set()
            c.run(80)
            if hp != 1 or W(c.prg_ram(), P[1 - port] + 0x76) != 0:
                bad.append(f'player {port + 1} at FINISH HIM ({gap} px) {button.upper()}: Shadow {hp} -> '
                           f'{W(c.prg_ram(), P[1 - port] + 0x76)} health')
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fighters', default=','.join(GRID))
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    a = ap.parse_args()
    import patches
    specs = {s.key: s for s in patches.MK_SPECS}
    failed = False
    with tempfile.TemporaryDirectory(prefix='ek-close-') as tmp:
        c = scd.Core(saves=os.path.join(tmp, 'saves'))
        c.load(a.disc)
        for who in a.fighters.split(','):
            bad = fighter(c, a.disc, tmp, who, specs[who])
            print(f'{who}: ' + ('ok' if not bad else 'FAILED\n  ' + '\n  '.join(bad)), flush=True)
            failed |= bool(bad)
    print('close moves:', 'FAILED' if failed else 'ok')
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
