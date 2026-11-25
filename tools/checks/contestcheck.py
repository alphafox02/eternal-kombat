#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Does the one-player Contest (the ladder) run from match to match without freezing?

From the main menu: Enter Contest, player 1 takes GRID (select-grid presses).
Player 1 can't lose (his health is kept up) and the CPU's is kept low, so each
match is won quickly; player 1 walks in and punches. Between fights Start is
pressed now and then. A still picture for 2 s during a fight, or for long
anywhere, gets one Start press (it may be a pause, or a 'Press START' screen):
a freeze is a picture still for 20 s in spite of those.

    contestcheck.py GRID [--matches 6] [--frames 60000] [--sheet out.png] [--frozen-state S]
        -> the opponents met (fighter ids), matches won; exits 1 on a freeze
    contestcheck.py GRID --ending --sheet out.png [--frames 60000]
        after the first match the ladder's position (GAME.CO $1C04(a6): $31 and up =
        Eternal next) jumps to the end: Eternal, the last fight, then the winner's
        ending; the sheet shows it (a picture every 10 s). ok = the Dark Champion
        was met and the fighter's MK ending (patches.mk_endings) was loaded
    contestcheck.py GRID --ending --throws
        the same, walking up to the Dark Champion and throwing him (B up close): only a throw knocks him out (his health
        kept where a punch or kick can't)
"""
import argparse, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
FATAL_INPUTS = None
import scd
from inputs import ROOT

P1, P2 = 0x2E188, 0x2E330
W = lambda r, a: int.from_bytes(r[a:a + 2], 'big')
CUE = os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue')
FROZEN = 1200
LADDER = 0x30000 + 0x1C04                 # GAME.CO's $1C04(a6): the next opponent's place in the list
THROWS_LANDED = set()                      # (--throws: seconds in which the Dark Champion was being thrown)
THROW_HEALTH = 12                          # (--throws: his health before each blow - an MK throw takes 20, a punch 3 to 8)
ATTACKS = [{'x'}, {'a'}, {'down', 'x'}, {'y'}, {'down', 'a'}, {'c'}, {'z'}, {'b'}]   # (Eternal blocks punches)


def contest(grid, matches, frames, sheet=None, frozen_state=None, ending=False, rewind=None, fatality=None,
            on_frame=None, fatality_max=None, fatality_on=None, fatality_immediate=False, throws=False):
    """fatality: an MK fighter's name (tools/lib/mkfatalitycheck.INPUTS): when the
    loser is dazed (FINISH HIM), he does his MK fatality instead of attacking."""
    c = scd.Core(saves=os.path.join(ROOT, 'build', 'shots', 'duel-saves'))
    c.load(CUE)
    c.load_state(os.path.join(ROOT, 'build', 'states', 'menu.state'))
    c.press(['start']); c.run(240); c.press(['start']); c.run(240)      # Enter Contest
    for _ in range(grid):
        c.press(['right']); c.run(20)
    c.press(['start']); c.run(200)
    opps, shots, text = [], [], None
    throws_landed = THROWS_LANDED
    throws_landed.clear()
    prev, same, worst, kick = None, 0, 0, 0
    seq, fatalities = [], 0
    if fatality:
        from mkfatalitycheck import INPUTS as FATAL_INPUTS
    for f in range(frames):
        r = c.prg_ram()
        h1, h2 = W(r, P1 + 0x76), W(r, P2 + 0x76)
        fight = h1 > 0 and 0 < h2 < 200 and same < 120
        if ending and len(opps) == 1 and not fight and W(r, LADDER) < 0x31:
            c.poke_prg(LADDER, b'\x00\x31')
        if kick:                                        # a Start press, 2 frames, then wait
            c.buttons[0] = {'start'} if kick > 28 else set()
            kick -= 1
        elif fight and fatality and W(r, P2 + 0xBE) & 0x7FFF == 0x1F and not seq and \
                (fatality_max is None or fatalities < fatality_max) and \
                (fatality_on is None or r[P2 + 0x4D] in fatality_on) and \
                not fatality_immediate and W(r, P1 + 0xBE) != 0:
            # The winning hit can leave the winner recovering or being hit: no
            # fatality input (and no attack on the dazed loser) until he is
            # neutral. --fatality-immediate keeps the old sequence, to reproduce
            # timing-dependent failures.
            c.buttons[0] = set()
        elif fight and fatality and W(r, P2 + 0xBE) & 0x7FFF == 0x1F and not seq and \
                (fatality_max is None or fatalities < fatality_max) and \
                (fatality_on is None or r[P2 + 0x4D] in fatality_on):
            X = lambda o: int.from_bytes(r[o + 0x4E:o + 0x50], 'big', signed=True)
            fwd = 'right' if X(P2) > X(P1) else 'left'
            inp = FATAL_INPUTS[fatality]
            rel = {'fwd': fwd, 'back': 'left' if fwd == 'right' else 'right'}
            seq = [set()] * 20                          # (as the player: a moment after FINISH HIM)
            for k, t in enumerate(inp['taps']):
                btn = {inp['button']} if k == len(inp['taps']) - 1 and inp['button'] else set()
                seq += [set(inp['held']) | {rel.get(t, t)} | btn] * (5 if btn else 3) + [set(inp['held'])] * 4
            seq += [set()] * 400                        # (then hands off while it plays)
            fatalities += 1
            if os.environ.get('EK_VERBOSE'):
                print(f'  fatality {fatalities} at frame {f} on {r[P2 + 0x4D]} (health {W(r, P2 + 0x76)})', flush=True)
        elif seq:
            c.buttons[0] = seq.pop(0)
        elif fight:
            if not opps or opps[-1] != r[P2 + 0x4D]:
                opps.append(r[P2 + 0x4D])
            c.poke_prg(P1 + 0x76, b'\x00\x68')
            thrown = throws and r[P2 + 0x4D] == 25          # (the Dark Champion, to be thrown: kept on THROW_HEALTH,
            if thrown and h2 != THROW_HEALTH:               #  so that a throw knocks him out and a punch or kick -
                c.poke_prg(P2 + 0x76, THROW_HEALTH.to_bytes(2, 'big'))   # the throw's press from a step too far - doesn't)
            elif not thrown and h2 > 3:
                c.poke_prg(P2 + 0x76, b'\x00\x03')
            k = f % 24
            hit = ATTACKS[f // 24 % len(ATTACKS)] if ending else {'x'}
            toward = 'right' if W(r, P2 + 0x4E) > W(r, P1 + 0x4E) else 'left'   # (always right: the Dark Champion
            c.buttons[0] = {toward} if k < 12 else (hit if k < 15 else set())  #  teleports behind and was never reached)
            if thrown:                                      # walk up to him; next to him: MK's throw (B up close,
                near = abs(W(r, P2 + 0x4E) - W(r, P1 + 0x4E)) < 70   #  kickthrowcheck; toward + Y is MK's close punch
                c.buttons[0] = {toward, 'b'} if near and k % 12 < 3 else {toward}   #  now, closemovecheck)
                if W(r, P2 + 0xBE) & 0x7FFF == 0x37:
                    throws_landed.add(f // 60)
        else:
            c.buttons[0] = set()
            wait = 600 if ending and len(opps) > 1 else 90      # (the ending's pages: let them be read)
            if same >= wait and same % wait == 0 or not ending and f % 40 == 0 and same > 10:
                kick = 30
        if rewind and f % 300 == 0:                    # (states to step back from a freeze: the last 8)
            os.makedirs(rewind, exist_ok=True)
            c.save_state(os.path.join(rewind, f'at_{f // 300 % 8}.state'))
            open(os.path.join(rewind, f'at_{f // 300 % 8}.txt'), 'w').write(str(f))
        c.run(1)
        if on_frame:                                    # (a probe: (core, frame number))
            on_frame(c, f)
        fr = c.frame.tobytes()
        same = same + 1 if fr == prev else 0
        prev = fr
        worst = max(worst, same)
        if f % 600 == 0:
            shots.append(c.frame.copy())
        if ending and fight and text is None:
            text = ending_text(r[P1 + 0x4D]) or 'not an MK fighter'
        if ending and f % 300 == 0 and isinstance(text, bytes) and text and text in c.prg_ram():
            text = b''                                  # (seen: his ending's first line is loaded)
        if same >= FROZEN or len(opps) > matches and not ending:
            if same >= FROZEN and frozen_state:
                c.save_state(frozen_state)
            break
    if sheet:
        from PIL import Image
        k = len(shots)
        o = Image.new('RGB', (160 * 10, 112 * ((k + 9) // 10)))
        for i, s in enumerate(shots):
            o.paste(Image.fromarray(s).resize((160, 112)), ((i % 10) * 160, (i // 10) * 112))
        o.save(sheet)
    if ending:
        opps.append('text' if text == b'' else 'no text')
    if fatality:
        print(f'{fatalities} fatality inputs attempted')
    return opps, same >= FROZEN, f


def ending_text(fid):
    """The first line of the MK fighter fid's ending record (None if not an MK fighter)."""
    import patches, mkendings
    sp = next((sp for sp in patches.MK_SPECS if sp.host_id == fid), None)
    return mkendings.record(mkendings.endings()[sp.key])[:27] if sp else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('grid', type=int)
    ap.add_argument('--matches', type=int, default=6)
    ap.add_argument('--frames', type=int, default=60000)
    ap.add_argument('--sheet')
    ap.add_argument('--fatality', help="finish every match with this MK fighter's fatality (scorpion, subzero, ...)")
    ap.add_argument('--fatality-max', type=int, help='only the first N fatalities (then plain wins)')
    ap.add_argument('--fatality-on', type=lambda v: [int(x) for x in v.split(',')],
                    help='only on these opponents (fighter ids, e.g. 14 = Riptide)')
    ap.add_argument('--fatality-immediate', action='store_true',
                    help='send fatality inputs even while the winner is recovering (the old sequence: to reproduce timing-dependent failures)')
    ap.add_argument('--rewind', help='folder: keep states of the last 8 x 300 frames (to step back from a freeze)')
    ap.add_argument('--frozen-state', help='save a state here on a freeze')
    ap.add_argument('--ending', action='store_true', help='jump to the end of the ladder after match 1')
    ap.add_argument('--throws', action='store_true',
                    help="with --ending: next to the Dark Champion, throw him (an MK throw's knockout left him "
                         "standing in the air: the fight never ended)")
    a = ap.parse_args()
    opps, frozen, f = contest(a.grid, a.matches, a.frames, a.sheet, a.frozen_state, a.ending, a.rewind, a.fatality,
                              fatality_max=a.fatality_max, fatality_on=a.fatality_on,
                              fatality_immediate=a.fatality_immediate, throws=a.throws)
    if a.ending:                                       # (Dark Champion: 25)
        ok = not frozen and 25 in opps and opps[-1] == 'text' and (not a.throws or len(THROWS_LANDED) >= 1)
        if a.throws:
            print(f'the Dark Champion thrown in {len(THROWS_LANDED)} seconds of the fight')
        print(f'contest {a.grid} to the end: opponents {opps[:-1]}, ending text {opps[-1]}, {f} frames '
              f'-> {"ok" if ok else "FROZE" if frozen else "FAIL"}')
        sys.exit(0 if ok else 1)
    met = len(opps) - (not frozen and len(opps) > a.matches)
    ok = not frozen and met >= a.matches
    print(f'contest {a.grid}: opponents {opps[:a.matches + 1]}, {met} met in {f} frames '
          f'-> {"ok" if ok else "FROZE" if frozen else "FAIL (too few matches)"}')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
