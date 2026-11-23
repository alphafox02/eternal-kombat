#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Play an EC fighter's Vendetta on an MK loser and save a frame strip.

From a 2-player duel (tools/lib/duelstate.py, made here if missing): the deciding
round, the loser on low health and dazed (EC's generic dizzy, PLYR.CO $17C9A,
state $1F), then the winner's Vendetta input:
four direction taps then a button, from his move list (PLYR.CO $153A0 lists,
type $24 entries: $8000 | 2 down, 4 away, 8 toward; then the button word, 0,
the move id), each within 10 frames of the last. By default Vendettas on MK losers are
allowed in RAM for the test (PLYR.CO $15F1B, a byte per loser id - 2).

    vendettacheck.py WINNER_PRESSES LOSER_PRESSES [--keep-block] [--video OUT.mp4]
        -> build/shots/vendetta_<winner id>_on_<loser id>.png, and $1CD4 (3 = Vendetta)

Presses: right presses on the select grid (tools/lib/duelstate.py).
"""
import argparse, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scd
from inputs import ROOT

P1, P2 = 0x2E188, 0x2E330
WINS = 0x31D26
VENDETTA_OK = 0x15F1B
LISTS = 0x153A0
DIZZY = 0x17C9A                # PLYR.CO: EC's generic dizzy (a fighter's move task resumed here)
DIRS = {2: 'down', 4: 'away', 8: 'toward'}
BUTTONS = {0x400: 'x', 0x200: 'y', 0x100: 'z', 0x40: 'a', 0x10: 'b', 0x20: 'c'}   # (EC's pad bits)


def vendetta_taps(plyr, fid):
    """His Vendetta's four taps from his move list in PLYR.CO (in RAM)."""
    L = lambda a: int.from_bytes(plyr[a:a + 4], 'big')
    W = lambda a: int.from_bytes(plyr[a:a + 2], 'big')
    h = L(LISTS + 4 * (fid - 2))
    for k in range(0, 40, 2):                     # its 'lea list,a2'
        op = W(h + k)
        if op == 0x45F9:
            lst = L(h + k + 2)
            break
        if op == 0x45FA:
            lst = h + k + 2 + int.from_bytes(plyr[h + k + 2:h + k + 4], 'big', signed=True)
            break
    else:
        return None
    while L(lst) != 0xFFFFFFFF:
        e = L(lst)
        if W(e + 4) == 0x24:                      # $8000|dir words, then a button word, 0, move id
            seq, k = [], e + 6
            while W(k) & 0x8000:
                seq.append(DIRS[W(k) & 0xF])
                k += 2
            return seq + [BUTTONS[W(k)]]
        lst += 4
    return None


def main():
    global P1, P2
    ap = argparse.ArgumentParser()
    ap.add_argument('winner', type=int)
    ap.add_argument('loser', type=int)
    ap.add_argument('--keep-block', action='store_true', help="leave the build's Vendetta flags as they are")
    ap.add_argument('--gap', type=int, default=40, help='px between them (x) for the input')
    ap.add_argument('--big', action='store_true', help='full-size frames, 5 a row')
    ap.add_argument('--stage', default='1B', help="stage mode for a new duel state (hex; 1B: the theater, where they can stand close)")
    ap.add_argument('--video', help='also record an .mp4 with sound (from the walk in to the end)')
    ap.add_argument('--as-p2', action='store_true', help='make the winner player 2')
    ap.add_argument('--state', help='use this duel state instead of the cached one')
    ap.add_argument('--disc', help='use this disc instead of the standard build')
    ap.add_argument('--frames', type=int, default=900, help='frames to wait for the statistics')
    ap.add_argument('--trace', action='store_true', help="print the loser's frame word ($1A) as it changes")
    ap.add_argument('--save-at', type=int, help='save a state this many frames after the input (to --save)')
    ap.add_argument('--save', help='where --save-at saves')
    a = ap.parse_args()
    port = int(a.as_p2)
    if a.as_p2:
        P1, P2 = P2, P1                     # winner, victim throughout this test
    state = a.state or os.path.join(ROOT, 'build', 'states', f'vendetta_{a.winner}_{a.loser}{"_p2" if a.as_p2 else ""}.state')
    if not os.path.exists(state):                 # (made aside, then moved: runs in parallel may share it)
        tmp = f'{state}.{os.getpid()}'
        p1, p2 = (a.loser, a.winner) if a.as_p2 else (a.winner, a.loser)
        cmd = [sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'),
               '--p1', str(p1), '--p2', str(p2), '--stage', a.stage, '--out', tmp]
        if a.disc:
            cmd += ['--disc', a.disc]
        subprocess.run(cmd, check=True)
        os.replace(tmp, state)
    c = scd.Core(audio=bool(a.video), saves=os.path.join(ROOT, 'build', 'shots', 'record-saves'))
    c.load(a.disc or os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    c.load_state(state)
    c.run(10)
    rec = None
    if a.video:
        from finishvideo import Rec
        rec = Rec(c, a.video)
        c.run = rec.tick                          # every frame from here is recorded
    r = c.prg_ram()
    w, l = r[P1 + 0x4D], r[P2 + 0x4D]
    taps = vendetta_taps(r, w)
    print(f'winner id {w}, loser id {l}, Vendetta {taps}')
    if not taps:
        raise SystemExit('no Vendetta input found')
    X = lambda o: int.from_bytes(c.prg_ram()[o + 0x4E:o + 0x50], 'big')

    def run(n, held=()):
        c.buttons[port] = set(held)
        c.run(n)
        c.buttons[port] = set()
    for _ in range(80):                           # close in
        if abs(X(P2) - X(P1)) < a.gap:
            break
        run(2, ['right' if X(P2) > X(P1) else 'left'])
    c.poke_prg(WINS, (1).to_bytes(2, 'big'))      # one round each: this one decides it
    c.poke_prg(WINS + 2, (1).to_bytes(2, 'big'))
    if not a.keep_block:
        # an MK loser's own block rewrites his byte every frame (mkinputs.emit_vendetta_ok:
        # move.b vok(a0,d0.w),VENDETTA_OK+id-2): that write is NOPed in RAM for the test
        site = bytes.fromhex('13f00000') + (VENDETTA_OK + l - 2).to_bytes(4, 'big')
        ram = c.prg_ram()
        at = ram.find(site)
        while at >= 0:
            c.poke_prg(at, bytes.fromhex('4e71') * 4)
            at = ram.find(site, at + 1)
        c.poke_prg(VENDETTA_OK + l - 2, b'\x01')
    c.poke_prg(P2 + 0x76, (20).to_bytes(2, 'big'))
    # dazed: EC's generic dizzy, his move task (the 2nd) resumed at PLYR.CO $17C9A
    r = c.prg_ram()
    t1 = int.from_bytes(r[P2 + 0x88:P2 + 0x8C], 'big')
    t2 = int.from_bytes(r[t1:t1 + 4], 'big')
    c.poke_prg(t2 + 4, DIZZY.to_bytes(4, 'big'))
    c.poke_prg(t2 + 8, bytes(2))
    for _ in range(30):
        c.run(1)
        if int.from_bytes(c.prg_ram()[P2 + 0xBE:P2 + 0xC0], 'big') & 0x7FFF == 0x1F:
            break
    c.run(20)                                     # (let the daze settle before the input)
    print('loser state', c.prg_ram()[P2 + 0xBE:P2 + 0xC0].hex())
    for t in taps:
        if t == taps[-1]:                         # EC compares the loser's state with exactly $001F
            for _ in range(8):                    # (a daze flips to $801F as its steps end)
                if int.from_bytes(c.prg_ram()[P2 + 0xBE:P2 + 0xC0], 'big') == 0x1F:
                    break
                c.run(1)
        toward = 'right' if X(P2) > X(P1) else 'left'
        away = 'left' if toward == 'right' else 'right'
        run(3, [{'toward': toward, 'away': away, 'down': 'down'}.get(t, t)])
        c.run(2)
    r = c.prg_ram()
    print('after the input: winner state', r[P1 + 0xBE:P1 + 0xC0].hex(), 'gap', abs(X(P2) - X(P1)))
    from finishvideo import stats_screen
    shots, kind, finished = [], 0, False
    last = None
    for f in range(a.frames):
        c.run(1)
        kind = max(kind, int.from_bytes(c.prg_ram()[0x31CD4:0x31CD6], 'big'))
        if a.save_at == f:
            c.save_state(a.save)
        if a.trace:
            r = c.prg_ram()
            now = (r[P2 + 0x1A:P2 + 0x1C].hex(), r[P2 + 0xBE:P2 + 0xC0].hex(),
                   r[P1 + 0x1A:P1 + 0x1C].hex(), r[P1 + 0xBE:P1 + 0xC0].hex(),
                   r[P2 + 0x4E:P2 + 0x50].hex(), r[P2 + 0x52:P2 + 0x54].hex(), r[P2 + 0x28:P2 + 0x2A].hex())
            if now != last:
                print(f'  {f:4d} loser frame {now[0]} state {now[1]} x {now[4]} y {now[5]} $28 {now[6]},'
                      f' winner frame {now[2]} state {now[3]}')
                last = now
        if f % 10 == 0 and stats_screen(c.frame):
            finished = True
            break
        if f % 30 == 0:
            shots.append(c.frame.copy())
    print(f'finisher type $1CD4 = {kind} (3 = Vendetta)')
    from PIL import Image
    cw, ch, per = (320, 224, 5) if a.big else (160, 112, 10)
    ims = [Image.fromarray(s).resize((cw, ch)) for s in shots]
    o = Image.new('RGB', (cw * per, ch * ((len(ims) + per - 1) // per)))
    for i, im in enumerate(ims):
        o.paste(im, ((i % per) * cw, (i // per) * ch))
    out = os.path.join(ROOT, 'build', 'shots', f'vendetta_{w}_on_{l}{"_p2" if a.as_p2 else ""}.png')
    o.save(out)
    print(os.path.relpath(out, ROOT))
    if rec:
        rec.close()
        print(a.video)
    print('final statistics:', 'reached' if finished else 'NOT REACHED')
    if kind != 3 or not finished:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
