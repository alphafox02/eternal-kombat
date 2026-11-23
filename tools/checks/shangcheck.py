#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Shang Tsung (fighter 11, the Contest's first boss) against MK's own Shang.

MK's: tools/lib/mkshangref.py, docs/notes/2026-11.md. Kano vs Shang on his stage, made here
with tools/lib/duelstate.py (Shang is player 2: the side he is fought from).

  - glide (player 2 drives him): toward, his start pose (EMP 2, 40:66) then his
    held glide pose (3, 40:64) and nothing else, at MK's 1.875 px a frame; away,
    4 then 5 (40:67, 40:68) then 6 held (40:65), at MK's 3.375;
  - skull volley (the CPU's Shang, Kano standing): one cast (move $34) hits
    Kano three times, 10 each, ~40 frames apart, three staggers and no
    knockdown (MK: three skulls ~40 apart);
  - morph (the CPU's Shang, Kano kept alive): after a volley he blends through
    MK's three Kano blends (40:3B-3D) into Kano (his id 13: Kano's module in his
    slot, mkinputs.emit_morph), fights with Kano's moves (more than stance and
    walks), and blends back (40:3D-3B) into Shang, with no frozen screen; the
    volley and the jump-in below start once he is Shang again;
    every frame Shang's art shows in his colours and Kano's in a Kano mirror
    match's player 2's (EC's palette fade had shown Kano's art in Shang's
    colours, speckled; and art set in $1A is on screen two frames later, new
    colours one: he is blank as he swaps, mkinputs.MORPH_BLANK);
  - jump-in (the CPU's Shang): Kano walks in and jump-kicks; Shang backs away
    and the kick never reaches him, not even blocked (at Blade's walk speed it
    did; at MK's, EC's walking-away block stopped him: mkinputs.GLIDE_NO_BLOCK).

    shangcheck.py [--state 2P_STATE --cpu-state CPU_STATE]
"""
import argparse, ctypes, os, shutil, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT

P1, P2 = 0x2E188, 0x2E330
SHANG = 11
DISC = os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue')
TOWARD = (0x66, 0x64)              # 40:66 (EMP 2) then 40:64 (3) held  (mkinputs.glide_frames)
AWAY = (0x67, 0x68, 0x65)          # 40:67 (4), 40:68 (5) then 40:65 (6) held
SPEED = {'toward': (32, 60), 'away': (16, 54)}
STANCE = range(0x01, 0x07)           # 40:01-06: his stance sway     # held-pose frames, px (MK: 1.875, 3.375 a frame)
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big', signed=True)
MV = 0x21800 + 0x67E0              # his morph's phase (mkinputs.MORPH_MV in player 2's slot)
KANO = 13
KANO_BLENDS = (0x3B, 0x3C, 0x3D)   # 40:38 + 3 x Kano's place (mkinputs.MORPH_BLEND)


def cram_line(c, line):
    """The VDP's colours, one palette line (from a savestate)."""
    from vdp import VDPState
    n = c.lib.retro_serialize_size()
    b = ctypes.create_string_buffer(n)
    c.lib.retro_serialize(b, n)
    return VDPState(b.raw).cram_raw[16 * line:16 * line + 16]


def core(state):
    c = scd.Core()
    c.load(DISC)
    c.load_state(state, check=False)
    return c


def glide(state, side):
    """Poses (runs of $1A's frame byte) and px over the held pose's first frames."""
    c = core(state)
    c.run(10)
    r = c.prg_ram()
    toward = 'left' if W(r, P1 + 0x4E) < W(r, P2 + 0x4E) else 'right'
    pad = toward if side == 'toward' else {'left': 'right', 'right': 'left'}[toward]
    runs, xs = [], []
    for _ in range(60):
        c.buttons[1] = {pad}
        c.run(1)
        r = c.prg_ram()
        f = r[P2 + 0x1B]
        if runs and runs[-1][0] == f:
            runs[-1][1] += 1
        else:
            runs.append([f, 1])
        xs.append(W(r, P2 + 0x4E))
    # (a press reaches him on EC's every-other-frame input pass: 0-1 frames, more by
    #  where the duel state's round start falls - it shifts with file sizes, so up to
    #  2 frames of his stance first are allowed, not counted)
    if len(runs) > 1 and runs[0][0] in STANCE and runs[0][1] <= 2:
        runs, xs = runs[1:], xs[runs[0][1]:]
    held = sum(n for _, n in runs[:-1])          # frames before the held pose
    n, _ = SPEED[side]
    moved = abs(xs[held + n] - xs[held]) if held + n < len(xs) else None
    return runs, moved


def after_morph(state, theirs=None):
    """The CPU's duel, Kano kept alive (outside Shang's casts), through one whole
    morph: (core, {'in': blend frames, 'ids': his ids, 'moves': his moves while
    morphed, 'out': blend frames, 'back': Shang again, 'still': screen froze})."""
    c = core(state)
    m = {'in': [], 'ids': set(), 'moves': set(), 'out': [], 'back': False, 'still': False, 'wrong': []}
    mine, shown = None, [None, None]                  # (a frame set in $1A is on screen two frames later)
    same, prev, seen3 = 0, None, False
    for f in range(8000):
        r = c.prg_ram()
        if f % 20 == 0 and W(r, P1 + 0x76) < 60 and W(r, P2 + 0xBE) & 0x7FFF != 0x34:
            c.poke_prg(P1 + 0x76, (104).to_bytes(2, 'big'))
        c.run(1)
        r = c.prg_ram()
        ph, pid = r[MV], W(r, P2 + 0x4C)
        if ph in (1, 3) and r[P2 + 0x1A] == 0xED and 0x38 <= r[P2 + 0x1B] <= 0x4C:
            lst = m['in'] if ph == 1 else m['out']
            if not lst or lst[-1] != r[P2 + 0x1B]:
                lst.append(r[P2 + 0x1B])
        shown.append((r[P2 + 0x1A], r[P2 + 0x1B]))
        on_screen = shown.pop(0)
        if theirs is not None and (ph in (1, 3) or pid != SHANG) and on_screen:   # every frame: art and colours agree
            cr = cram_line(c, 2)
            sheet, fr = on_screen
            if (sheet, fr) != (0xED, 0x4D):           # (his blank, mkinputs.MORPH_BLANK: as the colours change)
                if (0xED <= sheet <= 0xF0 and cr != mine) or (not 0xED <= sheet <= 0xF0 and cr != theirs):
                    m['wrong'].append(f)
        elif mine is None or (ph == 0 and pid == SHANG):
            mine = cram_line(c, 2)                    # (his own colours)
        if pid != SHANG:
            m['ids'].add(pid)
            m['moves'].add(W(r, P2 + 0xBE) & 0x7FFF)
        seen3 |= ph == 3
        if seen3 and ph == 0 and pid == SHANG:
            m['back'] = True
            return c, m
        fr = c.frame.tobytes()
        same = same + 1 if fr == prev else 0
        prev = fr
        if same >= 300:
            m['still'] = True
            break
    return c, m


def volley(c):
    """([(frame, damage)] of Kano's hits, knocked down?) in Shang's first cast
    that starts with Kano standing; his stun meter emptied then (EC's $14C: hits
    left in it from earlier knock him down, a rule for every fighter)."""
    r = c.prg_ram()
    hp, was, hits, down = W(r, P1 + 0x76), W(r, P2 + 0xBE) & 0x7FFF, None, False
    for f in range(3600):
        if hits is None and f % 20 == 0 and W(r, P1 + 0x76) < 60:
            c.poke_prg(P1 + 0x76, (104).to_bytes(2, 'big'))
        c.run(1)
        r = c.prg_ram()
        move, h, kano = W(r, P2 + 0xBE) & 0x7FFF, W(r, P1 + 0x76), W(r, P1 + 0xBE) & 0x7FFF
        if move == 0x34 and was != 0x34 and hits is None and kano == 0:
            c.poke_prg(P1 + 0x14C, bytes(2))        # (his stun meter emptied, his health full: a clean volley
            c.poke_prg(P1 + 0x76, (104).to_bytes(2, 'big'))   #  - Kano took Shang-as-Kano's hits before)
            r = c.prg_ram()
            h = 104
            hits = []
        if hits is not None:
            if h < hp:
                hits.append((f, hp - h))
            down |= kano == 0x1C
            if move != 0x34 and was == 0x34:
                return hits, down
        hp, was = h, move
    return hits or [], down


MID = 500                                         # mid-stage x (the boss's stage, $12)


def jumpin(c):
    """Kano jump-kicks at Shang from 130 px: (the kick touched Shang - EC's hit routine gave him a hit's stun,
    $10C, blocked or not -, px he backed off). Set up directly: once both stand idle and Shang is himself
    (not blending), both are put 130 px apart about their middle (on screen: far off it the game puts them
    back) and Kano jumps at once. An attempt where Shang throws his volley before Kano leaves the floor (the
    CPU's choice: legitimate) is void and tried again. (A walk in from wherever the morph test left them hung
    on the CPU's choices: with some timings by the wall, or Kano knocked out by a volley on the way.)"""
    import mkinputs
    mv = mkinputs.SLOTS[1] + mkinputs.MORPH_MV
    result = (False, 0)
    for attempt in range(8):
        for _ in range(1800):
            for o in (P1, P2):
                c.poke_prg(o + 0x76, (104).to_bytes(2, 'big'))
            r = c.prg_ram()
            if (W(r, P1 + 0xBE) & 0x7FFF == 0 and W(r, P2 + 0xBE) & 0x7FFF == 0 and W(r, P2 + 0x4C) == SHANG
                    and r[mv] == 0):
                break
            c.buttons[0] = set()
            c.run(1)
        r = c.prg_ram()
        x1, x2 = W(r, P1 + 0x4E), W(r, P2 + 0x4E)
        mid, side = (x1 + x2) // 2, (1 if x2 > x1 else -1)
        for o, x in ((P1, mid - 65 * side), (P2, mid + 65 * side)):
            for f in (0x4E, 0xB2):
                c.poke_prg(o + f, (x & 0xFFFF).to_bytes(2, 'big'))
        c.run(1)
        x0, touched, volley = W(c.prg_ram(), P2 + 0x4E), False, False
        fwd = 'right' if side > 0 else 'left'
        for held, n in (({'up', fwd}, 4), (set(), 14), ({'z'}, 4), (set(), 60)):
            for _ in range(n):
                c.buttons[0] = held
                c.run(1)
                r = c.prg_ram()
                touched |= W(r, P2 + 0x10C) != 0
                volley |= W(r, P2 + 0xBE) & 0x7FFF == 0x34 and W(r, P1 + 0x52) >= W(r, P2 + 0x52) - 4
        result = (touched, abs(W(c.prg_ram(), P2 + 0x4E) - x0))
        if not volley:
            return result
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--state', help='Kano vs Shang, 2 players (default: made now)')
    ap.add_argument('--cpu-state', help='Kano vs the CPU\'s Shang (default: made now)')
    a = ap.parse_args()
    tmp = None
    if not (a.state and a.cpu_state):
        tmp = tempfile.mkdtemp()
        for name, extra in (('state', []), ('cpu_state', ['--cpu'])):
            if not getattr(a, name):
                out = os.path.join(tmp, f'{name}.state')
                subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'),
                                '--p1', '18', '--p2', '0', '--p2-id', str(SHANG), '--stage', '12', '--out', out]
                               + extra, check=True, capture_output=True)
                setattr(a, name, out)
    ok = True
    for side, want in (('toward', TOWARD), ('away', AWAY)):
        runs, moved = glide(a.state, side)
        poses = tuple(f for f, _ in runs)
        good = poses == want and moved is not None and abs(moved - SPEED[side][1]) <= 2
        ok &= good
        print(f'glide {side}: poses {" ".join(f"40:{f:02x}x{n}" for f, n in runs)}; '
              f'{moved} px in {SPEED[side][0]} frames (MK {SPEED[side][1]}) {"ok" if good else "WRONG"}')
    mirror = os.path.join(tmp or tempfile.mkdtemp(), 'mirror.state')     # Kano vs Kano: player 2's colours
    subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--p1', '18', '--p2', '18',
                    '--stage', '12', '--out', mirror], check=True, capture_output=True)
    mc = core(mirror)                             # (first: one emulator at a time in a process)
    mc.run(30)
    want = cram_line(mc, 2)
    os.remove(mirror)
    c, m = after_morph(a.cpu_state, want)
    good = not m['wrong']
    ok &= good
    print(f"morph colours: every frame, Shang's art in his colours and Kano's in a Kano mirror match's player 2's "
          f"{'ok' if good else 'WRONG at frames ' + str(m['wrong'][:8])}")
    good = (m['in'] == list(KANO_BLENDS) and m['ids'] == {KANO} and len(m['moves'] - {0, 4, 8, 0x7FFF}) >= 2
            and m['out'] == list(reversed(KANO_BLENDS)) and m['back'] and not m['still'])
    ok &= good
    print(f"morph: blends in {' '.join(f'40:{f:02x}' for f in m['in'])}, as id {sorted(m['ids'])} with moves "
          f"{' '.join(f'{x:X}' for x in sorted(m['moves']))}, blends out {' '.join(f'40:{f:02x}' for f in m['out'])}, "
          f"Shang again {m['back']}{', SCREEN STILL' if m['still'] else ''} {'ok' if good else 'WRONG'}")
    hits, down = volley(c)
    gaps = [b[0] - a_[0] for a_, b in zip(hits, hits[1:])]
    good = len(hits) == 3 and all(d == 10 for _, d in hits) and all(30 <= g <= 60 for g in gaps) and not down
    ok &= good
    print(f'volley: hits {[d for _, d in hits]}, {gaps} frames apart, knocked down {down} {"ok" if good else "WRONG"}')
    c, _ = after_morph(a.cpu_state)
    touched, backed = jumpin(c)
    good = not touched and backed >= 30
    ok &= good
    print(f'jump-in: the kick touched him {touched}, he backed off {backed} px {"ok" if good else "WRONG"}')
    if tmp:
        shutil.rmtree(tmp)
    print('Shang ->', 'ok' if ok else 'FAILED')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
