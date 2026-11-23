#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Blast's stage (mode $13) finishers, recorded with sound.

The Overkill (the Huey gunship; the loser facing left at x $1B0-$218) or the Sudden
Death (the watchtower gunner; facing right at x $268-$2C8). A 2-player duel there
(tools/lib/duelstate.py), the deciding round, the loser (player 2) on 6 health;
BST.BGI's +0 check forced past its armed flag ($34054, as tools/lib/usherdeath.py
does the theater's); player 1 hits. docs/notes/2026-11.md "Scorpion in the
Senator's slot".

    blastfinisher.py WINNER LOSER OUT.mp4 [--kind overkill|sudden] [--frames N]
        e.g. blastfinisher.py 14 20 build/shots/blast/helicopter_overkill_on_scorpion.mp4 --kind overkill
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT
from finishvideo import Rec

P1, P2 = 0x2E188, 0x2E330
WINS = 0x31D26
FORCE_AT = 0x34054                     # BST.BGI: beq.w (no armed flag: no finisher) -> nops

ap = argparse.ArgumentParser()
ap.add_argument('winner', type=int)
ap.add_argument('loser', type=int)
ap.add_argument('out')
ap.add_argument('--kind', default='sudden', choices=('sudden', 'overkill'))
ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
ap.add_argument('--frames', type=int, default=900)
a = ap.parse_args()
tmp = tempfile.mkdtemp()
st = os.path.join(tmp, 'd.state')
subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', a.disc,
                '--p1', str(a.winner), '--p2', str(a.loser), '--stage', '13', '--out', st], check=True, capture_output=True)
c = scd.Core(audio=True, saves=os.path.join(tmp, 'saves'))
c.load(a.disc)
c.load_state(st)
c.run(30)


def setx(o, v):
    for f in (0x36, 0x3A, 0x4E, 0x56, 0xB2, 0xBA):
        c.poke_prg(o + f, v.to_bytes(2, 'big'))


c.poke_prg(WINS, (1).to_bytes(2, 'big'))
c.poke_prg(WINS + 2, (1).to_bytes(2, 'big'))
if a.kind == 'sudden':                       # loser facing right at x $268-$2C8: both at the right end
    c.buttons[0] = c.buttons[1] = {'right'}
    c.run(200)
    c.buttons[0] = c.buttons[1] = set()
    setx(P2, 660)
    setx(P1, 700)
else:                                        # the loser facing left at x $1B0-$218
    setx(P1, 420)
    setx(P2, 480)
c.run(10)
c.poke_prg(P2 + 0x76, (6).to_bytes(2, 'big'))
c.poke_prg(P2 + 0x190, (40).to_bytes(2, 'big'))
c.run(20)
r = c.prg_ram()
print('loser id', r[P2 + 0x4D], 'x', int.from_bytes(r[P2 + 0x4E:P2 + 0x50], 'big'),
      'facing left' if r[P2 + 0x20] & 8 else 'facing right')
rec = Rec(c, a.out)
rec.tick(30)
assert c.prg_ram()[FORCE_AT:FORCE_AT + 2] == b'\x67\x00', c.prg_ram()[FORCE_AT:FORCE_AT + 4].hex()
c.poke_prg(FORCE_AT, bytes.fromhex('4e714e71'))
c.buttons[0] = {'y'}
rec.tick(4)
c.buttons[0] = set()
kind = 0
for f in range(a.frames):
    rec.tick(1)
    kind = max(kind, int.from_bytes(c.prg_ram()[0x31CD4:0x31CD6], 'big'))
rec.close()
print('finisher type', kind, '(1 Overkill, 2 Sudden Death)', '->', a.out)
