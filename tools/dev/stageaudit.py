#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Every stage's round end, Overkill and Sudden Death with every MK fighter as the loser.

Against an EC loser (Shadow) in the same scene: what the stage draws only for the MK loser. A
striped block showed where Slash's stage draws its pterodactyl, only with Liu Kang beaten there.
This runs, per stage (modes $11-$22) and loser, a deciding round with the loser nearly beaten
and the winner (Slash, or --winner, player 2) landing the last hit:
  - ko: where the fight starts;
  - overkill / sudden: at a spot where the reference loser triggers the stage's Overkill ($1CD4 = 1) /
    Sudden Death (2), found by walking him along the stage (some stages have none).
Every 6 frames to the round's end it reads the sprite table (VDP, from the emulator's state) and
keeps each different picture drawn in palette lines 0 and 1 (the stage's and the effects'; the
fighters draw in 2 and 3), and any sprite whose tiles lie in the VDP's maps (planes, window, sprite
and scroll tables: it draws map data - that striped block). Reported per case:
  - sprites drawn from map data (in any run, the reference's too);
  - pictures the MK loser's run drew that the reference run never did (a sheet of them);
  - the finisher that played, if it isn't the reference's;
  - a still picture for 20 s (a freeze).

    stageaudit.py [--stages 1a,11] [--losers liukang,kano] [--jobs 4]
        -> build/shots/stageaudit/report.md and a picture per flagged case
"""
import argparse, hashlib, os, subprocess, sys, tempfile
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
from inputs import ROOT

P1, P2 = 0x2E188, 0x2E330
LOSERS = {'shadow': 0, 'scorpion': 20, 'raiden': 7, 'subzero': 15, 'sonya': 16, 'liukang': 17, 'kano': 18,
          'johnny': 19}                               # select-grid presses (tools/lib/duelstate.py); shadow: the reference
WINNER = 3                                            # Slash
STAGES = range(0x11, 0x23)
OUT = os.path.join(ROOT, 'build', 'shots', 'stageaudit')
SPOTS = range(40, 960, 60)
SPOTS_FINE = range(40, 960, 30)
FRAMES = 1800
FREEZE = 1200


def W(r, o):
    return int.from_bytes(r[o:o + 2], 'big')


def duel(disc, stage, grid, tmp, winner=None):
    winner = WINNER if winner is None else winner
    st = os.path.join(tmp, f'duel_{stage:02x}_{grid}_{winner}.state')
    if not os.path.exists(st):
        subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', disc,
                        '--p1', str(grid), '--p2', str(winner), '--stage', f'{stage:X}', '--out', st],
                       check=True, capture_output=True)
    return st


def setup(c, spot, side):
    """The deciding round, the loser (player 1) walked to spot (the winner side px on his right), nearly
    beaten; the winner's punch."""
    c.run(30)
    c.poke_prg(0x31D26, (1).to_bytes(2, 'big'))
    c.poke_prg(0x31D28, (1).to_bytes(2, 'big'))
    if spot is not None:
        for _ in range(120):
            x = W(c.prg_ram(), P1 + 0x4E)
            if abs(x - spot) <= 6:
                break
            x = x - 12 if x > spot else x + 12
            for o, v in ((P1, x), (P2, x + side)):
                for f in (0x4E, 0xB2):
                    c.poke_prg(o + f, (v & 0xFFFF).to_bytes(2, 'big'))
            c.run(3)
    c.run(40)
    c.poke_prg(P1 + 0x76, (6).to_bytes(2, 'big'))
    c.poke_prg(P1 + 0x190, (40).to_bytes(2, 'big'))    # (an Overkill also wants 10+ damage taken)
    c.run(60)
    c.buttons[1] = {'y'}
    c.run(4)
    c.buttons[1] = set()


def finisher(disc, st, spot, side, frames=300):
    import scd
    c = scd.Core()
    c.load(disc)
    c.load_state(st)
    setup(c, spot, side)
    fin = 0
    for _ in range(frames):
        c.run(1)
        fin = fin or W(c.prg_ram(), 0x31CD4)
    return fin


def find_spots(disc, st):
    """{1: (spot, side), 2: (spot, side)}: where the reference loser triggers each finisher."""
    out = {}
    for side in (50, -50):
        for spot in SPOTS:
            fin = finisher(disc, st, spot, side)
            if fin in (1, 2) and fin not in out:
                out[fin] = (spot, side)
            if len(out) == 2:
                return out
    return out


def run_case(disc, st, spot, side):
    """(finisher type, {picture hash: (pal, RGB pixels)}, longest still picture)."""
    import numpy as np
    import scd
    from vdp import VDPState
    c = scd.Core()
    c.load(disc)
    c.load_state(st)
    setup(c, spot, side)
    pics, fin, prev, still, worst, ended, bad = {}, 0, None, 0, 0, None, {}
    for f in range(FRAMES):
        c.run(1)
        r = c.prg_ram()
        fin = fin or W(r, 0x31CD4)
        fr = c.frame.tobytes()
        still = still + 1 if fr == prev else 0
        prev, worst = fr, max(worst, still)
        if ended is None and r[0x30AB7] & 3 == 3:
            ended = f
        if ended is not None and f > ended + 240:
            break
        if f % 6:
            continue
        v = VDPState(c.snapshot())
        maps = reserved(v)
        for s in v.sprites():
            if s['y'] <= -32 or s['y'] >= 224 or s['x'] <= -32 or s['x'] >= 320:
                continue
            lo, hi = s['tile'] * 32, (s['tile'] + s['w'] * s['h']) * 32
            if any(lo < b and a < hi for a, b in maps) and s['w'] * s['h'] > 0:
                px = v.sprite_pixels(s)
                if px.any() and len(bad) < 8:
                    pal = np.array(v.palette(s['pal']), np.uint8)
                    bad.setdefault(s['tile'], (f, pal[px]))
            if s['pal'] > 1:
                continue
            px = v.sprite_pixels(s)
            if not px.any():
                continue
            h = hashlib.sha1(bytes([s['pal']]) + px.tobytes() + bytes(px.shape)).hexdigest()
            if h not in pics:
                pal = np.array(v.palette(s['pal']), np.uint8)
                pics[h] = pal[px]
    return fin, pics, worst, bad


def reserved(v):
    """VRAM byte ranges the VDP uses for other things than sprite tiles: planes A and B, the window,
    the sprite table, the scroll table (from its registers). A sprite drawn from them draws map data."""
    r = v.regs
    w, h = v.plane_size()
    plane = 2 * w * h
    rows = r[18] & 0x1F                               # (the window: only its rows from the top, if that's
    window = rows * 128 if r[17] == 0 and not r[18] & 0x80 else 0x1000   #  all it shows: the HUD's 3)
    out = [(((r[2] & 0x38) << 10), plane), (((r[4] & 7) << 13), plane), (((r[3] & 0x3E) << 10), window),
           (v.sat_addr, 0x280), (((r[13] & 0x3F) << 10), 0x400)]
    return [(a, a + n) for a, n in out]


def job(args):
    disc, stage, who, tmp, spots, winner = args
    st = duel(disc, stage, LOSERS[who], tmp, winner)
    out = {}
    for case, (spot, side) in [('ko', (None, 50))] + [(('overkill', 'sudden')[k - 1], v) for k, v in sorted(spots.items())]:
        res = run_case(disc, st, spot, side)
        want = {'ko': 0, 'overkill': 1, 'sudden': 2}[case]
        if res[0] != want and who != 'shadow':        # (an MK loser flies a different distance: his own spot)
            own = next(((sp, sd) for sd in (side, -side) for sp in SPOTS_FINE
                        if finisher(disc, st, sp, sd) == want), None)
            if own:
                res = run_case(disc, st, *own) + (own,)
        out[case] = res
    return stage, who, out


def sheet(pictures, path):
    from PIL import Image
    pics = sorted(pictures, key=lambda p: -p.size)[:40]
    w = sum(p.shape[1] + 4 for p in pics) or 1
    h = max((p.shape[0] for p in pics), default=1)
    im = Image.new('RGB', (w, h), (255, 0, 255))
    x = 0
    for p in pics:
        im.paste(Image.fromarray(p), (x, 0))
        x += p.shape[1] + 4
    im.resize((im.width * 3, im.height * 3), Image.NEAREST).save(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    ap.add_argument('--stages', type=lambda v: [int(x, 16) for x in v.split(',')], default=list(STAGES))
    ap.add_argument('--losers', type=lambda v: v.split(','), default=[k for k in LOSERS if k != 'shadow'])
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--winner', type=int, default=WINNER,
                    help='the winner, player 2 (select-grid presses: 3 Slash; an MK fighter: 15 Sub-Zero ...)')
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    tmp = tempfile.mkdtemp(dir=os.path.join(ROOT, 'build'))
    with ProcessPoolExecutor(a.jobs) as ex:
        spot_jobs = {s: ex.submit(find_spots, a.disc, duel(a.disc, s, LOSERS['shadow'], tmp, a.winner)) for s in a.stages}
        spots = {s: f.result() for s, f in spot_jobs.items()}
        for s in a.stages:
            print(f'stage ${s:02X}: overkill {spots[s].get(1)}, sudden death {spots[s].get(2)}', flush=True)
        work = [(a.disc, s, w, tmp, spots[s], a.winner) for s in a.stages for w in ['shadow'] + a.losers]
        results = {}
        for stage, who, out in ex.map(job, work):
            results[stage, who] = out
            print(f'  ${stage:02X} {who:9s} ' + ', '.join(f'{k}: finisher {v[0]}, {len(v[1])} pictures, still {v[2]}, map sprites {len(v[3])}'
                                                       for k, v in out.items()), flush=True)
    lines = ['# Stage audit: what stages draw for MK losers', '',
             f'Disc: `{os.path.relpath(a.disc, ROOT)}`. Reference loser: Shadow. Winner: grid {a.winner} (3: Slash).', '']
    flagged = 0
    for s in a.stages:
        ref = results[s, 'shadow']
        lines += [f'## Stage ${s:02X}', '',
                  f'Overkill at {spots[s].get(1)}, Sudden Death at {spots[s].get(2)} (spot, winner side).', '']
        for who in a.losers:
            for case, (fin, pics, worst, bad, *own) in results[s, who].items():
                rfin, rpics, _, rbad = ref[case][:4]
                new = [p for h, p in pics.items() if h not in rpics]
                notes = []
                if fin != rfin:
                    notes.append(f'finisher {fin} (Shadow: {rfin}; none at any spot)')
                elif own:
                    notes.append(f'(at his own spot {own[0]})')
                if worst >= FREEZE:
                    notes.append(f'STILL {worst} frames')
                if bad:
                    name = f'{s:02x}_{who}_{case}_maps.png'
                    sheet([p for _, p in bad.values()], os.path.join(OUT, name))
                    notes.append(f'SPRITES FROM MAP DATA at frames {sorted(f for f, _ in bad.values())[:4]}: ![]({name})')
                if new:
                    name = f'{s:02x}_{who}_{case}.png'
                    sheet(new, os.path.join(OUT, name))
                    notes.append(f'{len(new)} pictures Shadow\'s run never drew: ![]({name})')
                if notes and notes != [f'(at his own spot {own[0]})' if own else None]:
                    flagged += 1
                    lines.append(f'- **{who}, {case}:** ' + '; '.join(notes))
        lines.append('')
    open(os.path.join(OUT, 'report.md'), 'w').write('\n'.join(lines))
    print(f'{flagged} flagged cases: {os.path.relpath(os.path.join(OUT, "report.md"), ROOT)}')


if __name__ == '__main__':
    main()
