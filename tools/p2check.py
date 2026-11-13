#!/usr/bin/env python3
"""Check that Scorpion's art file survives as player 2 (scorpion_full.MAX_PL).

Player 2's .PL loads at PRG-RAM $51800, the last ~186 KB before the end of
PRG-RAM. This sets up a duel with Scorpion as player 2 (tools/duelstate.py
--p1 0 --p2 14) and checks that:
  - the whole file is in RAM once the fight is on (byte for byte, but for the
    sheet numbers the game writes into its chunk headers), so nothing loaded
    after it (the versus screen, the stage) overwrote its tail;
  - after 1200 frames of fighting (blood, specials, hits) it is still intact
    and the rest of PRG-RAM above it is untouched.

    p2check.py
"""
import os, random, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scd
from disc import Disc
from inputs import ROOT

BASE = 0x51800
CUE = os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue')


def main():
    state = os.path.join(ROOT, 'shots', 'p2check.state')
    subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'duelstate.py'),
                    '--p1', '0', '--p2', '14', '--out', state], check=True, stdout=subprocess.DEVNULL)
    d = Disc(CUE)
    pl = d.read_file('BST.PL')
    d.close()
    c = scd.Core(saves=os.path.join(ROOT, 'shots', 'probe-saves'))
    c.load(CUE)
    c.load_state(state)
    os.remove(state)
    c.run(2)
    r = c.prg_ram()
    p2 = int.from_bytes(r[0x2E330 + 0x4C:0x2E330 + 0x4E], 'big')
    assert p2 == 23, f'player 2 is fighter {p2}, not Scorpion'
    end = BASE + len(pl)
    # the game writes each art chunk's sheet number into its header once
    # loaded (Blade's own BLA.PL gets the same six words): allow those
    bad = sorted({a & ~1 for a in range(len(pl)) if r[BASE + a] != pl[a]})
    sheet_words = [a for a in bad if r[BASE + a] in (0, 1) and 0x8D <= int.from_bytes(r[BASE + a:BASE + a + 2], 'big') & 0x1FF <= 0x1FF]
    other = [a for a in bad if a not in sheet_words]
    assert len(sheet_words) <= 8 and not other, \
        f'BST.PL differs in RAM at {[hex(a) for a in other or bad]}'
    pl = bytearray(pl)
    for a in sheet_words:
        pl[a:a + 2] = r[BASE + a:BASE + a + 2]
    pl = bytes(pl)
    above = bytes(r[end:0x80000])
    rnd = random.Random(1)
    for _ in range(1200):
        c.buttons[0] = {rnd.choice(['x', 'y', 'a', 'b', 'left', 'right', 'down', 'z'])}
        c.buttons[1] = {rnd.choice(['x', 'y', 'a', 'c', 'left', 'right', 'down', 'z'])}
        c.run(1)
    r = c.prg_ram()
    assert bytes(r[BASE:end]) == pl, 'BST.PL changed in RAM during the fight'
    assert bytes(r[end:0x80000]) == above, 'PRG-RAM above BST.PL changed during the fight'
    print(f'ok: BST.PL ({len(pl)} bytes, to ${end:05X}) intact as player 2 through 1200 frames')


if __name__ == '__main__':
    main()
