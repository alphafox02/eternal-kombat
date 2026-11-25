#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The spear, from near to across the screen (MK's: mkspear.py), pins the victim, pulls him in and dazes him.

(mkinputs.emit_spear_rope, SPEAR_TICKS / SPEAR_FRAMES, PULL_SPEED, r_drag.) Scorpion (player 1) and Reptile
(player 2) against Shadow, from 70 to 215 px. Each throw must hit (the victim reels, or is in EC's projectile
hit state - the rope's hit) by HIT_BY frames from the press (MK CD: the rope is out ~15 frames after it, the
hit 25-46 frames in, tools/dev/spearcmp.py), pin the victim where he stands at least PINNED frames (MK ~34:
EC's own hit lets him walk free ~48 frames after it, his stun held meanwhile) and then pull him in (within
PULL_GAP + 8 px) and daze him. And the rope flies over a crouching fighter (MK's), from either side; and
Scorpion at Shadow cornered at the arena's end, ~50 px: hit, his throw over.

    spearcheck.py [--disc CUE]     (run after play.py test has made the disc's build/states/menu.state)
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
import mkinputs
from inputs import ROOT

P1, P2 = 0x2E188, 0x2E330
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big', signed=True)
GAPS = (70, 110, 140, 180, 215)
PINNED = 26                # frames the victim is held where the rope hit him (MK ~34)
HIT_BY = 50                # frames from the press to the hit, at the most (MK: 46 from 225 px)


def throw(disc, st, thrower, gap, victim_holds=()):
    """One spear from gap px: (hit, frames he stayed pinned, daze start, the gap after) - frames from the press;
    with victim_holds, the health he lost."""
    victim = P1 if thrower == P2 else P2
    port, back = (0, 'left') if thrower == P1 else (1, 'right')
    c = scd.Core()
    c.load(disc)
    c.load_state(st)
    c.run(30)
    r = c.prg_ram()
    d = W(r, thrower + 0xB2) + (gap if thrower == P1 else -gap) - W(r, victim + 0xB2)
    for o in (0xB2, 0x4E):
        c.poke_prg(victim + o, ((W(r, victim + o) + d) & 0xFFFF).to_bytes(2, 'big'))
    c.buttons[1 - port] = set(victim_holds)
    c.run(20)
    hp = W(c.prg_ram(), victim + 0x76)
    hit = daze = pinned = x0 = None
    t = -8                                   # (0: the press)
    for b, n in [({back}, 3), (set(), 2), ({back}, 3), ({'x'}, 4), (set(), 220)]:
        c.buttons[port] = set(b)
        for _ in range(n):
            c.run(1)
            t += 1
            r = c.prg_ram()
            s = W(r, victim + 0xBE) & 0x7FFF
            if hit is None and (mkinputs.HIT_FIRST <= s <= mkinputs.HIT_LAST or s == mkinputs.ROPE_STATE):
                hit, x0 = t, W(r, victim + 0xB2)
            if hit is not None and pinned is None and abs(W(r, victim + 0xB2) - x0) > 4:
                pinned = t - hit
            if hit is not None and daze is None and s == mkinputs.DIZZY:
                daze = t
            if daze is not None and t > daze + 20:
                return hit, pinned, daze, abs(W(r, thrower + 0xB2) - W(r, victim + 0xB2))
    if victim_holds:
        return hp - W(c.prg_ram(), victim + 0x76)
    return hit, pinned, daze, abs(W(c.prg_ram(), thrower + 0xB2) - W(c.prg_ram(), victim + 0xB2))


def cornered(disc, st):
    """Scorpion (player 2, facing left) at Shadow backed into the arena's left end, ~50 px away: the rope's
    head starts past her (a Contest once stuck there: the rope gone, his throw held for good). She must be
    hit, and his throw must end. -> (health lost, his move 300 frames on)."""
    c = scd.Core()
    c.load(disc)
    c.load_state(st)
    c.run(20)
    for _ in range(600):
        r = c.prg_ram()
        d = W(r, P2 + 0x4E) - W(r, P1 + 0x4E)
        c.buttons = [{'left'}, {'left'} if d > 50 else ({'right'} if d < 44 else set())]
        c.run(1)
    c.buttons = [set(), set()]
    c.run(10)
    hp = W(c.prg_ram(), P1 + 0x76)
    for b, n in [({'right'}, 3), (set(), 2), ({'right'}, 3), ({'x'}, 4), (set(), 300)]:
        c.buttons[1] = set(b)
        c.run(n)
    r = c.prg_ram()
    return hp - W(r, P1 + 0x76), W(r, P2 + 0xBE) & 0x7FFF


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    a = ap.parse_args()
    bad = []
    with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, 'build')) as tmp:
        for name, thrower, args in (('Scorpion', P1, ['--p1', '20', '--p2', '0']),
                                    ('Reptile', P2, ['--p1', '0', '--p2', '0', '--p2-id', '26', '--unlock', '26'])):
            st = os.path.join(tmp, name + '.state')
            subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', a.disc,
                            '--stage', '11', '--out', st] + args, check=True, capture_output=True)
            for gap in GAPS:
                hit, pinned, daze, after = throw(a.disc, st, thrower, gap)
                print(f'{name} from {gap} px: hit at {hit}, pinned {pinned} frames, dazed at {daze}, {after} px apart')
                if hit is None or hit > HIT_BY:
                    bad.append(f'{name} from {gap} px: ' + ('no hit' if hit is None else f'the hit {hit} frames in'))
                elif pinned is None or pinned < PINNED:
                    bad.append(f'{name} from {gap} px: pinned {pinned} frames (MK ~34)')
                elif daze is None:
                    bad.append(f'{name} from {gap} px: not dazed (he walks free)')
                elif after > mkinputs.PULL_GAP + 8:
                    bad.append(f'{name} from {gap} px: left {after} px away')
            lost = throw(a.disc, st, thrower, 140, {'down'})          # MK's spear goes over a crouch
            print(f'{name} at a crouching Shadow from 140 px: she loses {lost} health')
            if lost:
                bad.append(f'{name}: the spear hit a crouching fighter')
        st = os.path.join(tmp, 'cornered.state')
        subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', a.disc,
                        '--stage', '11', '--out', st, '--p1', '0', '--p2', '20'], check=True, capture_output=True)
        lost, move = cornered(a.disc, st)
        print(f'Scorpion at Shadow in the corner: she loses {lost} health; his move after: ${move:X}')
        if not lost or move == mkinputs.SPEAR_MOVE:
            bad.append('Scorpion at a cornered Shadow: ' + ('no hit' if not lost else 'his throw never ended'))
    for b in bad:
        print('FAIL:', b)
    print('spearcheck:', 'FAIL' if bad else 'ok')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
