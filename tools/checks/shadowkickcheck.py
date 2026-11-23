#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check Johnny's shadow-kick pose, overflow object, hit and cleanup.

A fresh duel places Johnny against Shadow, or against another Johnny with
--mirror. The cropped flight pose must coincide with a visible effect object;
it must be removed after the move, and the kick must damage the opponent.

    shadowkickcheck.py [--as-p2] [--mirror] [--verify-art] [--state STATE] [--disc CUE]
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT

P1, P2 = 0x2E188, 0x2E330
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big')
EFFECT_FRAME = 0x771D       # Johnny's sheet $77, after four bolt + 25 fatality frames
CROPPED_FRAME = 0xDA31      # sheet $DA, MK shadow-kick pose 15
OBJECTS = range(0x2CABC, 0x2E188, 0xA6)     # EC's object records (pool -$35D2(a6))
PAL_POOL = 0x29348          # palette tasks' free stack (-$6CB8(a6)): count word, pointers
DRAW_HEAD = 0x2E16E         # the sprite priority list (-$1E92(a6)): next +$A, prev +$E
L = lambda r, o: int.from_bytes(r[o:o + 4], 'big')


def pools_ok(r):
    """An object deleted as anything but an object (API $6A14 is the palette-task
    free) lands on the palette pool while still in the sprite list; a palette fade
    then gets it and its countdown eats the list's links (the Dark Champion hang)."""
    wrong = [L(r, PAL_POOL + 2 + i) for i in range(0, W(r, PAL_POOL), 4)
             if L(r, PAL_POOL + 2 + i) in OBJECTS]
    bad, p, n = [], DRAW_HEAD, 0
    while L(r, p + 0xA) and n < 80:
        q = L(r, p + 0xA)
        if q & 0xFFF80001 or L(r, q + 0xE) != p:
            bad.append((p, q)); break
        p, n = q, n + 1
    return (not wrong and not bad,
            f'palette pool objects {["%05X" % w for w in wrong]}, list breaks {[("%05X" % a, "%X" % b) for a, b in bad]}')


def verify_art(cue):
    """Decode the built effect and compare it with every clipped source pixel."""
    import numpy as np
    import disc, ecdeath, mkprojectile, patches, scorpion_full as sf
    patches.use(patches.JOHNNY)
    poses, anchors, cram = sf.load_action(ROOT, 'shadowkick')
    full, (ax, ay) = sf.scale_pose(poses[15], anchors[15], cram)
    full = sf.remap_colours(full)
    x0, y0, x1, y1 = sf.kept_window(full, (ax, ay))
    lost = full.copy()
    lost[y0:y1, x0:x1] = 0
    yy, xx = np.nonzero(lost)
    expected = np.zeros((256, 256), np.uint8)
    y, x = yy - (ay - sf.FOOT_DROP) + 128, xx - ax + 128
    assert np.all((0 <= y) & (y < 256) & (0 <= x) & (x < 256))
    expected[y, x] = lost[yy, xx]
    pl = disc.Disc(cue).read_file('MON.PL')
    chunks = mkprojectile.chunks(pl)
    sheet, size = next((o, n) for o, n, t in chunks if t == 4 and W(pl, o + 10) // 4 == 0x77)
    sid = W(pl, sheet + 12)
    source, length = next((o, n) for o, n, t in chunks if t == 0 and W(pl, o + 10) // 4 == sid)
    got = ecdeath.frames(pl[source + 20:source + length], pl[sheet:sheet + size])[EFFECT_FRAME & 0xFF]
    missing = np.count_nonzero(got != expected)
    print(f'shadow effect: {len(xx)} clipped source pixels, {missing} incorrect')
    if missing or not len(xx):
        raise SystemExit('shadow effect does not reproduce the missing art')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--as-p2', action='store_true')
    ap.add_argument('--mirror', action='store_true')
    ap.add_argument('--verify-art', action='store_true', help='also decode and verify the built effect art')
    ap.add_argument('--state', help='duel state from this disc')
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    a = ap.parse_args()
    if a.verify_art:
        verify_art(a.disc)
    port = int(a.as_p2)
    with tempfile.TemporaryDirectory() as tmp:
        state = a.state or os.path.join(tmp, 'duel.state')
        if not a.state:
            p1, p2 = ('19', '19') if a.mirror else (('0', '19') if port else ('19', '0'))
            subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'),
                            '--disc', a.disc, '--p1', p1, '--p2', p2, '--stage', '1B', '--out', state],
                           check=True, capture_output=True)
        c = scd.Core(saves=os.path.join(tmp, 'saves'))
        c.load(a.disc)
        c.load_state(state)
        c.run(20)
        actor, victim = (P2, P1) if port else (P1, P2)
        r = c.prg_ram()
        assert r[actor + 0x4D] == 18, 'the selected fighter is not Johnny'
        before = W(r, victim + 0x76)
        fwd, back = ('left', 'right') if port else ('right', 'left')
        started = shown = cleaned = False
        for held, n in (({back}, 3), (set(), 2), ({fwd}, 3), ({'a'}, 4), (set(), 120)):
            c.buttons[port] = held
            for _ in range(n):
                c.run(1)
                r = c.prg_ram()
                move = W(r, actor + 0xBE) & 0x7FFF
                frame = W(r, actor + 0x1A)
                started |= move == 0x35
                objects = [o for o in range(0x2CABC, 0x2E080, 0xA6)
                           if W(r, o + 0x1A) == EFFECT_FRAME and any(r[o:o + 8])]
                if frame == CROPPED_FRAME:
                    shown |= any(W(r, o + 0x52) < 0xFF00 and
                                 abs(W(r, o + 0x4E) - W(r, actor + 0x4E)) < 20 for o in objects)
                if started and move == 0 and not objects:
                    cleaned = True
        r = c.prg_ram()
        after = W(r, victim + 0x76)
        sound, why = pools_ok(r)
        ok = started and shown and cleaned and after < before and sound
        print(f'shadow kick: started {started}, overflow visible {shown}, cleaned {cleaned}, '
              f'health {before} -> {after}, {why} -> {"ok" if ok else "FAILED"}')
        sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
