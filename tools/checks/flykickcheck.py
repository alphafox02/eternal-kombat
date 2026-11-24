#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Liu Kang's flying kick (forward, forward + HK) gets going as MK's.

MK CD (live, tools/lib/mkmoves.py's script) leaves the floor 4-5 frames after HK and holds the kick
~9-10 frames after it, travelling all the way (mkinputs.flykick_plan). Ours stood 12 frames in place
first (slow to get going). From a 2-player duel, Liu Kang (player 1) against Shadow: after HK he
  - travels (x up 4+ px past where he stood) by HK + MOVING frames;
  - shows the kick (his dash's strike frame, xx:62) by HK + KICK frames;
  - flies on (x up 60+ px) at MK's speed (7.5 px a frame measured on MK CD: 6.5-8.5 here; was 2.5);
  - stops where it connects with her - no more than 12 px on after her health drops - and, as MK's,
    floats back in the kick (MK: ~56 px, the kick held 38 frames from the contact; here 35-75 px and
    30-46 frames), then lands, the move over within 70 frames of the hit.
Both sides: as player 2 he faces the other way (mkinputs.emit_flykick_stop's velocity is his own way round).

    flykickcheck.py [--disc CUE]     (run after play.py test has made the disc's build/states/menu.state)
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT

P1, P2 = 0x2E188, 0x2E330
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big', signed=True)
LIU_KANG, SHADOW = 17, 0
DASH = 0x35                                  # his flying kick's move (Blade's dash)
MOVING, KICK = 6, 10                         # frames after HK (MK: 4-5 off the floor, the kick at ~9-10)
INPUT = [('fwd', 4), ('', 3), ('fwd', 4), ('b', 4), ('', 90)]   # HK (EC's B) at frame 12


def side(disc, tmp, port):
    """-> problems, for Liu Kang as player port + 1 against Shadow."""
    me, her = (P1, P2) if port == 0 else (P2, P1)
    st = os.path.join(tmp, f'duel{port}.state')
    p = (LIU_KANG, SHADOW) if port == 0 else (SHADOW, LIU_KANG)
    subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', disc,
                    '--p1', str(p[0]), '--p2', str(p[1]), '--out', st], check=True, capture_output=True)
    c = scd.Core(saves=os.path.join(tmp, 'saves'))
    c.load(disc)
    c.load_state(st)
    c.run(30)
    way = 1 if port == 0 else -1                     # his forward, in x
    log, f, hk = [], 0, None
    for held, n in INPUT:
        for _ in range(n):
            c.buttons[port] = {('right' if port == 0 else 'left') if held == 'fwd' else held} - {''}
            c.run(1)
            f += 1
            if hk is None and held == 'b':
                hk = f
            r = c.prg_ram()
            log.append((f, W(r, me + 0xBE) & 0x7FFF, int.from_bytes(r[me + 0x1A:me + 0x1C], 'big'), way * W(r, me + 0x4E),
                        W(r, her + 0x76)))
    c.buttons[port] = set()
    dash = [(f, fr, x) for f, mv, fr, x, _ in log if mv == DASH]
    bad = []
    if not dash:
        return ['no flying kick (move $35)']
    x0 = next(x for f, mv, fr, x, _ in log if f == dash[0][0] - 1)
    moving = next((f for f, fr, x in dash if x - x0 >= 4), None)
    kick = next((f for f, fr, x in dash if fr & 0xFF == 0x62), None)
    far = max(x for f, fr, x in dash) - x0
    print(f'player {port + 1}: HK at frame {hk}; the kick move from {dash[0][0]}, travelling from {moving}, '
          f'the kick shown from {kick}; {far} px')
    if moving is None or moving - hk > MOVING:
        bad.append(f'travelling {None if moving is None else moving - hk} frames after HK (MK: 4-5; at most {MOVING})')
    if kick is None or kick - hk > KICK:
        bad.append(f'the kick {None if kick is None else kick - hk} frames after HK (MK: ~9-10; at most {KICK})')
    if far < 60:
        bad.append(f'flew only {far} px')
    fly = [(f, x) for f, fr, x in dash if fr & 0xFF == 0x62]
    hit = next((f for f, mv, fr, x, hp in log if hp < log[0][4]), None)
    before = [(f, x) for f, x in fly if hit is None or f < hit]
    speed = (before[-1][1] - before[0][1]) / (before[-1][0] - before[0][0]) if len(before) > 1 else 0
    print(f'  flight {speed:.1f} px a frame; Shadow hit at frame {hit}')
    if not 6.5 <= speed <= 8.5:
        bad.append(f'flew {speed:.1f} px a frame (MK 7.5)')
    if hit is None:
        return bad + ['the kick never hit Shadow']
    xh = next(x for f, mv, fr, x, _ in log if f == hit)
    on = max(x for f, mv, fr, x, _ in log if f >= hit) - xh
    held = [(f, x) for f, mv, fr, x, _ in log if f >= hit and mv == DASH and fr & 0xFF == 0x62]
    back = xh - min(x for f, x in held)
    end = next((f for f, mv, fr, x, _ in log if f > hit and mv != DASH), None)
    print(f'  after the hit: {on} px on, {back} px back in the kick held {len(held)} frames, '
          f'the move over {None if end is None else end - hit} frames later')
    if on > 12:
        bad.append(f'flew {on} px on after the hit (MK stops there)')
    if not 35 <= back <= 75 or not 30 <= len(held) <= 46:
        bad.append(f'floated back {back} px in {len(held)} frames (MK: ~56 px, the kick held 38)')
    if end is None or end - hit > 70:
        bad.append(f'the move went on {None if end is None else end - hit} frames after the hit')
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    a = ap.parse_args()
    bad = []
    with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, 'build')) as tmp:
        for port in (0, 1):
            bad += [f'player {port + 1}: {b}' for b in side(a.disc, tmp, port)]
    print('flykickcheck:', 'FAIL ' + '; '.join(bad) if bad else 'ok')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
