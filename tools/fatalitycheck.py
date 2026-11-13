#!/usr/bin/env python3
"""End-to-end check of Scorpion's MK fatality in a real 2-player duel.

From states/duel_shadow.state (tools/duelstate.py --p2 0 --out
states/duel_shadow.state): one round won each (deciding round), Shadow's
health set low; Scorpion walks in and jabs: the winning blow leaves her
dazed on 1 health (FINISH HIM). Then he holds Z (MK Block) and taps Up
twice. Checks that the timeline plays to the bones, Shadow's health
is 0, the round ends as a finisher ($1CD4 = 3) and the stats screen follows.
Writes a contact sheet to shots/fatality_check.png.

    fatalitycheck.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scd
from inputs import ROOT
from PIL import Image, ImageDraw

P1, P2 = 0x2E188, 0x2E330
BONES = (0x41 + 0x4D, 0x45)              # last skeleton pose (scorpion_map fatality_skeleton; his sheets moved +$4D)


def w(r, a):
    return int.from_bytes(r[a:a + 2], 'big')


def x(r, o):
    return int.from_bytes(r[o + 0x4E:o + 0x50], 'big', signed=True)


def main():
    c = scd.Core(saves=os.path.join(ROOT, 'shots', 'capture-saves'))
    c.load(os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    c.load_state(os.path.join(ROOT, 'states', 'duel_shadow.state'))
    c.run(30)
    # deciding round: one round each; Shadow nearly beaten
    c.poke_prg(0x31D26, (1).to_bytes(2, 'big'))
    c.poke_prg(0x31D28, (1).to_bytes(2, 'big'))
    c.poke_prg(P2 + 0x76, (4).to_bytes(2, 'big'))
    while x(c.prg_ram(), P2) - x(c.prg_ram(), P1) > 50:
        c.buttons[0] = {'right'}
        c.run(1)
    c.buttons[0] = set()
    for _ in range(12):                          # the winning blow -> FINISH HIM
        c.buttons[0] = {'x'}
        c.run(4)
        c.buttons[0] = set()
        for _ in range(40):
            c.run(1)
            if w(c.prg_ram(), P2 + 0xBE) == 0x1F:
                break
        if w(c.prg_ram(), P2 + 0xBE) == 0x1F:
            break
    r = c.prg_ram()
    assert w(r, P2 + 0xBE) == 0x1F, f"no FINISH HIM daze (BE {w(r, P2 + 0xBE):#x}, hp {w(r, P2 + 0x76)})"
    assert w(r, P2 + 0x76) == 1, 'FINISH HIM leaves the loser on 1 health'
    for _ in range(200):
        c.run(1)
        if w(c.prg_ram(), P1 + 0xBE) == 0:
            break
    c.run(30)
    for held, n in [('z', 6), ('z+up', 4), ('z', 4), ('z+up', 4), ('z', 6), ('', 2)]:
        c.buttons[0] = set(held.split('+')) - {''}
        c.run(n)
    c.buttons[0] = set()
    ims, bones, ended = [], None, None
    for i in range(700):
        c.run(1)
        r = c.prg_ram()
        if bones is None and (r[P2 + 0x1A], r[P2 + 0x1B]) == BONES:
            bones = i
            assert w(r, P2 + 0x76) <= 1
        if ended is None and r[0x30AB7] & 3 == 3:
            ended = i
            assert w(r, 0x31CD4) == 3, 'round did not end as a finisher'
            assert w(r, P2 + 0x76) == 0, "Shadow's health not 0"
        if i % 14 == 0 and len(ims) < 30:
            im = Image.fromarray(c.frame).copy()
            ImageDraw.Draw(im).text((2, 2), str(i), fill=(255, 255, 0))
            ims.append(im)
    assert bones is not None, 'fatality never reached the bones'
    assert ended is not None, 'round never ended'
    c.run(200)
    sheet = Image.new('RGB', (320 * 6, 224 * 6))
    for k, im in enumerate(ims + [Image.fromarray(c.frame)]):
        sheet.paste(im, ((k % 6) * 320, (k // 6) * 224))
    out = os.path.join(ROOT, 'shots', 'fatality_check.png')
    sheet.resize((1440, 1008)).save(out)
    print(f'fatality ok: bones at +{bones}, round over at +{ended} -> {os.path.relpath(out, ROOT)}')


if __name__ == '__main__':
    main()
