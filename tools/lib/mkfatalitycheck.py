#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""End-to-end check of an MK fighter's fatality in a real 2-player duel, on any opponent.

The deciding round, the loser on 3 health; the winner walks in and jabs (EC X:
MK's low punch), which leaves the loser dazed on 1 health (MK's FINISH HIM);
then his MK fatality input. Checks, frame by frame:
  - the loser is dazed ($BE $1F) after the jab (FINISH HIM),
  - the game keeps running (the picture changes: no freeze),
  - the round ends as a finisher ($1CD4 = 3) with the loser on 0 health,
  - Sonya's victim shows both fire and skeleton frames; Kano holds the heart up 3 s.
Writes build/shots/fatality_<winner>_on_<loser id>.png (a frame strip) and, with
--video, an .mp4 with sound.

    mkfatalitycheck.py FIGHTER [--p2 PRESSES] [--video]     (FIGHTER: scorpion, subzero, kano, ...)

The duel state is made (tools/lib/duelstate.py) if missing: build/states/checks/fatal_<who>_<p2>.state
(tools/checks/allchecks.py clears build/states/checks/ after a build: they're remade).
"""
import argparse, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scd
from inputs import ROOT

P1, P2 = 0x2E188, 0x2E330
GRID = {'scorpion': 20, 'raiden': 7, 'subzero': 15, 'sonya': 16, 'liukang': 17, 'kano': 18, 'johnny': 19}   # (select-grid presses)
# his MK fatality: taps ('fwd' / 'back' toward / away from her, 'down', 'up'),
# then the button held with the last tap; held: buttons held through the taps. A punch ('x' / 'y': EC's
# X low, Y high) is either punch, as on MK CD: --other-punch presses the other one
INPUTS = {
    'scorpion': dict(held=['z'], taps=['up', 'up'], button=None),       # hold Block, Up, Up (MK: the flame)
    'subzero': dict(held=[], taps=['fwd', 'down', 'fwd'], button='y'),  # the spine rip
    'johnny': dict(held=[], taps=['fwd', 'fwd', 'fwd'], button='y'),    # the decapitation uppercut
    'raiden': dict(held=[], taps=['fwd', 'back', 'back', 'back'], button='y'),   # the electrocution
    'liukang': dict(held=[], taps=['down', 'back', 'up', 'fwd', 'down'], button=None),   # the uppercut (MK CD: no button)
    'sonya': dict(held=[], taps=['fwd', 'fwd', 'back', 'back'], button='z'),   # the kiss (MK's Block: EC Z)
    'kano': dict(held=[], taps=['back', 'back'], button='x'),   # the heart rip (MK CD: B, B + a punch)
}
W = lambda r, a: int.from_bytes(r[a:a + 2], 'big')
X = lambda r, o: int.from_bytes(r[o + 0x4E:o + 0x50], 'big', signed=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('who', choices=sorted(INPUTS))
    ap.add_argument('--p2', type=int, default=0, help='the loser: right presses on the select grid (0 Shadow)')
    ap.add_argument('--video', action='store_true')
    ap.add_argument('--frames', type=int, default=700, help='frames to watch after the input')
    ap.add_argument('--trace', action='store_true', help="print the loser's $1A/$1C, his palette line and EC's "
                    "palette-changed flag as they change")
    ap.add_argument('--check-raiden-effects', action='store_true',
                    help="require Raiden's four victim-palette flashes and explosion droplets")
    ap.add_argument('--as-p2', action='store_true', help='he is player 2 (--p2 is then player 1, the loser)')
    ap.add_argument('--other-punch', action='store_true',
                    help="a punch in his input is the other punch (X for Y, Y for X: MK CD takes either); others' as they are")
    ap.add_argument('--stage', help='stage mode (hex, $11-$22: tools/lib/duelstate.py --stage); default the game\'s')
    ap.add_argument('--back', type=int, default=0, help='frames he walks away after FINISH HIM, before the input')
    ap.add_argument('--wait', type=int, default=30, help='frames from the daze (and his punch over) to the input')
    ap.add_argument('--cpu', action='store_true', help='the loser is the CPU (a one-player duel)')
    ap.add_argument('--unlock', default='', help='fighter ids to show on the select grid first (duelstate.py --unlock): '
                    '16 Thanatos (then at 15 presses, the MK fighters after him one further)')
    ap.add_argument('--after', type=int, default=0,
                    help='then N frames more, Start pressed now and then: into the next fight (its pictures '
                         'join the sheet; both fighters\' $2A printed: a player-2 win must leave player 1 able to draw)')
    a = ap.parse_args()
    if a.check_raiden_effects and a.who != 'raiden':
        ap.error('--check-raiden-effects requires raiden')
    os.makedirs(os.path.join(ROOT, 'build', 'states', 'checks'), exist_ok=True)
    state = os.path.join(ROOT, 'build', 'states', 'checks', f'fatal_{a.who}_{a.p2}{"_p2" if a.as_p2 else ""}'
                         f'{"_s" + a.stage if a.stage else ""}{"_cpu" if a.cpu else ""}{"_u" + a.unlock if a.unlock else ""}.state')
    if not os.path.exists(state):
        me = GRID[a.who] + (1 if '16' in a.unlock.split(',') and GRID[a.who] >= 15 else 0)   # (Thanatos at 15)
        p1, p2 = (a.p2, me) if a.as_p2 else (me, a.p2)
        subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'),
                        '--p1', str(p1), '--p2', str(p2), '--out', state]
                       + (['--stage', a.stage] if a.stage else []) + (['--cpu'] if a.cpu else [])
                       + (['--unlock', a.unlock] if a.unlock else []), check=True)
    global P1, P2
    port = 0
    if a.as_p2:                                   # (the roles swap: he's the object at P2, pad 2)
        P1, P2 = P2, P1
        port = 1
    c = scd.Core(audio=a.video, saves=os.path.join(ROOT, 'build', 'shots', 'record-saves'))
    c.load(os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    c.load_state(state)
    c.run(20)
    rec = None
    if a.video:
        from finishvideo import Rec
        rec = Rec(c, os.path.join(ROOT, 'build', 'shots', f'fatality_{a.who}_on_{a.p2}.mp4'))

    def run(n, held=()):
        c.buttons[port] = set(held)
        if rec:
            rec.run(n, list(held) if port == 0 else [])
        else:
            c.run(n)
        c.buttons[port] = set()
    c.poke_prg(0x31D26, (1).to_bytes(2, 'big'))       # one round each: this one decides it
    c.poke_prg(0x31D28, (1).to_bytes(2, 'big'))
    c.poke_prg(P2 + 0x76, (3).to_bytes(2, 'big'))
    for _ in range(150):
        r = c.prg_ram()
        if abs(X(r, P2) - X(r, P1)) < 45:
            break
        run(2, ['right' if X(r, P2) > X(r, P1) else 'left'])
    run(4, ['x'])
    dazed = False
    for _ in range(90):
        run(1)
        if W(c.prg_ram(), P2 + 0xBE) & 0x7FFF == 0x1F:
            dazed = True
            break
    r = c.prg_ram()
    print(f'FINISH HIM: loser {"dazed" if dazed else "NOT dazed"} on {W(r, P2 + 0x76)} health')
    for _ in range(90):                            # his punch over first (MK CD's close punch holds its
        if W(c.prg_ram(), P1 + 0xBE) & 0x7FFF not in (1, 2, 0x20, 0x21):   # strike ~40 frames in all:
            break                                  #  an input during it is lost, as on MK CD)
        run(1)
    run(a.wait)
    if a.back:                                     # (from afar: MK's fatalities are done up close)
        r = c.prg_ram()
        run(a.back, ['left' if X(r, P2) > X(r, P1) else 'right'])
        r = c.prg_ram()
        print(f'walked away: {abs(X(r, P2) - X(r, P1))} px apart')
    inp = dict(INPUTS[a.who])
    if a.other_punch:
        inp['button'] = {'x': 'y', 'y': 'x'}.get(inp['button'], inp['button'])
    for k, t in enumerate(inp['taps']):
        r = c.prg_ram()
        fwd = 'right' if X(r, P2) > X(r, P1) else 'left'
        rel = {'fwd': fwd, 'back': 'left' if fwd == 'right' else 'right'}
        last = k == len(inp['taps']) - 1
        btn = [inp['button']] if last and inp['button'] else []
        run(5 if btn else 3, inp['held'] + [rel.get(t, t)] + btn)   # (a player's taps: 3 frames down, 4 up;
        run(4, inp['held'])                            #  the button with the last tap, held a moment, as in MK)
    shots, kind, frames_seen, last_frame, stuck = [], 0, 0, None, 0
    fire_seen = bones_seen = False
    palettes, max_droplets, final_flash_frame = [], 0, None
    if a.who == 'sonya':
        import mkinputs, patches
        shift = (patches.SONYA.sheet_base - 0x40) << 8
        fire = {f + shift for f in mkinputs.BURN_FIRE[:3]}
        bones = {f + shift for f in mkinputs.BURN_BONES}
    heart_frames = 0
    if a.who == 'kano':                  # the heart held up beating, as MK's ~4 s (mkinputs.CAP_FATALS: its
        import mkinputs, patches         #  poses 9, 11, 12 - pinned to his fatality slots 5-7)
        heart = {f + ((patches.KANO.sheet_base - 0x40) << 8) for f in mkinputs.SZF_HIS_SLOTS[5:8]}
    for f in range(a.frames):
        run(1)
        r = c.prg_ram()
        kind = max(kind, W(r, 0x31CD4))
        if a.check_raiden_effects:
            line = ((W(r, P2 + 0x7A) & 3) ^ 1) * 32
            palette = r[0x296AA + line + 2:0x296AA + line + 32]
            if not palettes or palettes[-1] != palette:
                palettes.append(palette)
                if len(palettes) == 9:
                    final_flash_frame = f
            # Exclude blood left by the jab used to set up the fatality.
            if final_flash_frame is not None and f - final_flash_frame <= 30:
                max_droplets = max(max_droplets, sum(
                    W(r, obj + 0x1A) == 0x1B07 for obj in range(0x2CABC, 0x2E080, 0xA6)))
        if a.trace:
            line = ((W(r, P2 + 0x7A) & 3) ^ 1) * 32
            now = (W(r, P2 + 0x1A), W(r, P2 + 0x1C), W(r, 0x2982C), r[0x296AA + line:0x296AA + line + 8].hex())
            if now != getattr(main, 'last', None):
                print(f'  {f:4d} $1A {now[0]:04X} $1C {now[1]:04X} pal flag {now[2]:04X} line {now[3]}')
                main.last = now
        if a.who == 'kano':
            heart_frames += W(r, P1 + 0x1A) in heart
        if a.who == 'sonya':
            victim_frame = W(r, P2 + 0x1A)
            fire_seen |= victim_frame in fire
            bones_seen |= victim_frame in bones
        fr = c.frame.tobytes()
        stuck = stuck + 1 if fr == last_frame and r[0x30AB7] & 3 != 3 else 0   # (after the round: stills)
        last_frame = fr
        if f % 35 == 0:
            shots.append(c.frame.copy())
    r = c.prg_ram()
    hp = W(r, P2 + 0x76)
    ok = dazed and kind == 3 and hp == 0 and stuck < 120
    if a.who == 'sonya':
        ok = ok and fire_seen and bones_seen
    if a.who == 'kano':                  # (a broken build showed it ~1 s, then his empty fist)
        print(f'Kano holds the heart up {heart_frames} frames (at least 180)')
        ok = ok and heart_frames >= 180
    if a.check_raiden_effects:
        effects_ok = len(palettes) == 9 and len(set(palettes)) == 2 and palettes[0] == palettes[-1] and max_droplets > 0
        print(f'Raiden effects: {len(palettes) - 1} palette changes, restored '
              f'{bool(palettes) and palettes[0] == palettes[-1]}, max {max_droplets} droplets '
              f'-> {"ok" if effects_ok else "FAILED"}')
        ok = ok and effects_ok
    for f in range(a.after):
        c.buttons[0] = c.buttons[1] = {'start'} if f % 120 < 2 else set()
        c.run(1)
        if f % 150 == 0:
            shots.append(c.frame.copy())
    if a.after:
        q = c.prg_ram()
        fight = 0 < W(q, 0x2E188 + 0x76) <= 104 and 0 < W(q, 0x2E330 + 0x76) <= 104
        print(f'after {a.after} frames: {"a fight" if fight else "no fight"}; player 1 $2A ${W(q, 0x2E188 + 0x2A):04X}, '
              f'player 2 $2A ${W(q, 0x2E330 + 0x2A):04X}; $20 ${W(q, 0x2E188 + 0x20):04X} / ${W(q, 0x2E330 + 0x20):04X}')
    print(f'finisher type $1CD4 = {kind} (3 = finisher), loser health {hp}, '
          f'longest still picture {stuck} frames -> {"ok" if ok else "FAILED"}')
    if a.who == 'sonya':
        print(f'Sonya victim animation: flames {"seen" if fire_seen else "MISSING"}, '
              f'skeleton {"seen" if bones_seen else "MISSING"}')
    if rec:
        rec.close()
    from PIL import Image
    ims = [Image.fromarray(s).resize((256, 180)) for s in shots]
    o = Image.new('RGB', (256 * 5, 180 * ((len(ims) + 4) // 5)))
    for i, im in enumerate(ims):
        o.paste(im, ((i % 5) * 256, (i // 5) * 180))
    out = os.path.join(ROOT, 'build', 'shots', f'fatality_{a.who}_on_{a.p2}.png')
    o.save(out)
    print(os.path.relpath(out, ROOT))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
