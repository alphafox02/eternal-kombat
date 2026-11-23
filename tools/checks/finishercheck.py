#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Unit-test the built disc's finisher checks for MK losers on an emulated 68000.

Unicorn, M68000 model; flags are read with an Scc after the call (unicorn's SR
read missed lazy flags).

The Cinekill check (PLYR.CO $14AA2) and the stage Sudden Death check ($1784C)
are jsrs to patched routines (patches.no_cinekill_mk); each must answer
'greater' (= no finisher) like EC's compare, plus for MK victims: no Cinekill
on any, no Sudden Death on those without death art (mkdeath.art_ids).

    finishercheck.py      -> a table; exits 1 if any answer is wrong
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN
from unicorn.m68k_const import UC_M68K_REG_A5, UC_M68K_REG_A7, UC_M68K_REG_D1, UC_CPU_M68K_M68000
import disc
import mkinputs, mkdeath
from inputs import ROOT

CINEKILL, SUDDEN = 0x14AA2, 0x1784C
LIMIT = {CINEKILL: 24, SUDDEN: 20}            # EC's: the victim's health at most this


def main():
    d = disc.Disc(os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    sub, plyr = d.read_file('SUB.BIN'), d.read_file('PLYR.CO')

    def target(site):
        o = site - 0x14000
        assert plyr[o:o + 2] == b'\x4e\xb9', f'no jsr at ${site:X}'
        return int.from_bytes(plyr[o + 2:o + 6], 'big')

    def skips(fn, fid, hp):
        mu = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
        mu.ctl_set_cpu_model(UC_CPU_M68K_M68000)
        mu.mem_map(0, 0x80000)
        mu.mem_write(0x6000, sub)
        mu.mem_write(0x14000, plyr)
        a5, stub = 0x30000, 0x40000
        mu.mem_write(a5 + 0x4C, fid.to_bytes(2, 'big'))
        mu.mem_write(a5 + 0x76, hp.to_bytes(2, 'big'))
        code = bytes.fromhex('4eb9') + fn.to_bytes(4, 'big') + bytes.fromhex('5ec1' '4e71')   # jsr ; sgt d1 ; nop
        mu.mem_write(stub, code)
        mu.reg_write(UC_M68K_REG_A5, a5)
        mu.reg_write(UC_M68K_REG_A7, 0x7F000)
        mu.reg_write(UC_M68K_REG_D1, 0)
        mu.emu_start(stub, stub + len(code) - 2)
        return bool(mu.reg_read(UC_M68K_REG_D1) & 0xFF)

    art, bad = mkdeath.art_ids(), 0
    for fid in (2, 3, 9) + tuple(mkinputs.MK_IDS):
        row = []
        for site, name in ((CINEKILL, 'Cinekill'), (SUDDEN, 'Sudden Death')):
            for hp in (LIMIT[site], LIMIT[site] + 1):
                want = hp > LIMIT[site] or (fid in mkinputs.MK_IDS and (site == CINEKILL or fid not in art))
                got = skips(target(site), fid, hp)
                bad += got != want
                row.append(f'{name} hp {hp}: {"skip " if got else "allow"}{"" if got == want else " WRONG"}')
        print(f'id {fid:2d}  ' + ' | '.join(row))
    print('all right' if not bad else f'{bad} wrong')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
