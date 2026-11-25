#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Which stage a fight is on (tools/lib/mkstages.py's pick), every case, run on the built SUB.BIN.

The pick (GAME's jmp $6C98 -> it -> $7134 with d0 = the stage mode) runs under unicorn with SUB.BIN
at $6000, the fight's set-up in RAM (a6 = $30000: the players' slots $1428/$142A, the game - the return
address its fight start leaves in $143C -, the Duel's BACKGROUND SETTING $1CFC) and EC's random routine
($6C68) answering from a list. Cases:
the bosses' arenas stay; two EC fighters keep EC's stage, but an MK stage (the Pit, the packed
mode) becomes EC's own random one; an MK fighter on either side gets one of MK's six (each of the
six reachable, never the last one twice), except a Duel whose BACKGROUND SETTING names a stage
or is PLAYER 2 with an EC player 2, and Reptile's Contest match (the Pit).

    stagepickcheck.py [--disc CUE]
"""
import argparse, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import unicorn as U, unicorn.m68k_const as M
from inputs import ROOT
from disc import Disc
import mkstages, patches

STUB, QUEUE, STOP = 0x7F000, 0x7F800, 0x7FF00
A6 = 0x30000


class Pick:
    def __init__(self, sub):
        self.mu = mu = U.Uc(U.UC_ARCH_M68K, U.UC_MODE_BIG_ENDIAN)
        try:
            mu.ctl_set_cpu_model(M.UC_CPU_M68K_M68000)
        except Exception:
            pass
        mu.mem_map(0, 0x80000)
        mu.mem_write(0x6000, sub)
        entry = sub[mkstages.PICK_ENTRY - 0x6000:mkstages.PICK_ENTRY - 0x6000 + 6]
        assert entry[:2] == b'\x4e\xf9', 'no pick at $6C98'
        self.pick = int.from_bytes(entry[2:], 'big')
        keys = [k for k, _, _ in mkstages.STAGES]
        table = b''.join((patches.PIT_MODE if k == 'pit' else mkstages.MODE).to_bytes(2, 'big') for k in keys)
        self.mkmode = sub.find(table) + 0x6000
        self.var, self.last = self.mkmode - 6, self.mkmode - 5          # (sub_code's data: var, last, cur, mkmode)
        # EC's random routine: d0 from the queue (and its range noted)
        mu.mem_write(0x6C68, b'\x4e\xf9' + STUB.to_bytes(4, 'big'))
        mu.mem_write(STUB, bytes.fromhex('2f09' '2279') + QUEUE.to_bytes(4, 'big')
                     + bytes.fromhex('3019' '23c9') + QUEUE.to_bytes(4, 'big') + bytes.fromhex('225f' '4e75'))
        self.ranges = []
        mu.hook_add(U.UC_HOOK_CODE, lambda uc, addr, size, _: self.ranges.append(
            (uc.reg_read(M.UC_M68K_REG_D1) & 0xFFFF, uc.reg_read(M.UC_M68K_REG_D2) & 0xFFFF)), begin=STUB, end=STUB)

    def run(self, d0, p1, p2, game, setting=0, randoms=(), last=0xFF):
        mu = self.mu
        w = lambda o, v: mu.mem_write(A6 + o, v.to_bytes(2, 'big'))
        w(0x1428, p1); w(0x142A, p2)
        mu.mem_write(A6 + 0x143C, game.to_bytes(4, 'big'))           # the fight start that called
        mu.mem_write(A6 + 0x1CFC, bytes([setting]))
        mu.mem_write(self.last, bytes([last]))
        mu.mem_write(self.var, b'\xee')
        mu.mem_write(QUEUE, (QUEUE + 8).to_bytes(4, 'big'))
        mu.mem_write(QUEUE + 8, b''.join(v.to_bytes(2, 'big') for v in randoms) + b'\xde\xad' * 4)
        self.ranges = []
        sp = 0x7FE00
        mu.reg_write(M.UC_M68K_REG_A7, sp)
        mu.reg_write(M.UC_M68K_REG_A6, A6)
        mu.reg_write(M.UC_M68K_REG_D0, d0)
        mu.emu_start(self.pick, mkstages.FIGHT_START, timeout=2_000_000, count=100_000)
        assert mu.reg_read(M.UC_M68K_REG_PC) == mkstages.FIGHT_START
        assert mu.reg_read(M.UC_M68K_REG_A7) == sp, 'the stack moved'
        return mu.reg_read(M.UC_M68K_REG_D0) & 0xFFFF, mu.mem_read(self.var, 1)[0], mu.mem_read(self.last, 1)[0], self.ranges


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    a = ap.parse_args()
    d = Disc(a.disc)
    sub, game = d.read_file('SUB.BIN'), d.read_file('GAME.CO')
    d.close()
    p = Pick(sub)
    mk = {sp.key: sp.host_id - 2 for sp in patches.MK_SPECS}
    ec_list = sorted({int.from_bytes(game[mkstages.EC_RANDOM + 2 * i:mkstages.EC_RANDOM + 2 * i + 2], 'big')
                      for i in range(25)} - {0})
    SHADOW, LARCEN = 0, 1                                   # EC fighters' slots
    PIT, MODE = patches.PIT_MODE, mkstages.MODE
    keys = [k for k, _, _ in mkstages.STAGES]
    want_mk = lambda k: (PIT if k == 'pit' else MODE, mkstages.PACKED.index(k) if k in mkstages.PACKED else None)
    bad = []

    def case(name, got, mode, var=None, ranges=None):
        d0, v, last, rng = got
        ok = d0 == mode and (var is None or v == var) and (ranges is None or rng == ranges)
        print(f'{"ok  " if ok else "FAIL"} {name}: stage ${d0:X}' + (f', variant {v}' if mode == MODE else '')
              + ('' if ok else f'  (want ${mode:X}{f", variant {var}" if var is not None else ""}, randoms {rng})'))
        if not ok:
            bad.append(name)

    CONTEST, DUEL, TOURNAMENT = mkstages.CONTEST_RET, mkstages.DUEL_RET, mkstages.TOURNAMENT_RET
    for boss in (0x11, 0x12):
        case(f'boss arena ${boss:X}, MK vs EC', p.run(boss, mk['scorpion'], SHADOW, CONTEST, randoms=(0,)), boss, ranges=[])
    case('EC vs EC, an EC stage', p.run(0x19, SHADOW, LARCEN, CONTEST, randoms=(0,)), 0x19, ranges=[])
    for k, st in enumerate((PIT, MODE)):
        case(f'EC vs EC, Duel RANDOM landing on MK stage ${st:X}: EC\'s random',
             p.run(st, SHADOW, LARCEN, DUEL, randoms=(k * 5,)), ec_list[k * 5], ranges=[(0, len(ec_list) - 1)])
    for i, key in enumerate(keys):                          # every MK stage reachable
        mode, var = want_mk(key)
        case(f'Contest, MK (Scorpion) vs EC, random {i} -> {key}',
             p.run(0x19, mk['scorpion'], SHADOW, CONTEST, randoms=(i,)), mode, var, ranges=[(0, 5)])
    case('Contest, EC vs MK (Sonya)', p.run(0x1F, SHADOW, mk['sonya'], CONTEST, randoms=(1,)), *want_mk('gates'))
    case('Contest, MK vs MK', p.run(0x1F, mk['kano'], mk['raiden'], CONTEST, randoms=(4,)), *want_mk('throne'))
    case('never the last one twice: last 2, randoms 2 then 5', p.run(0x19, mk['scorpion'], SHADOW, CONTEST,
                                                                     randoms=(2, 5), last=2), *want_mk('lair'),
         ranges=[(0, 5), (0, 5)])
    got = p.run(0x19, mk['scorpion'], SHADOW, CONTEST, randoms=(4,))
    case('the pick is remembered as the last', got, *want_mk('throne'))
    if got[2] != 4:
        bad.append('last not kept')
    case("Contest, Reptile's match: the Pit", p.run(PIT, mk['scorpion'], mk['reptile'], CONTEST, randoms=(0,)), PIT,
         ranges=[])
    case('Contest, Shang Tsung (boss slot) as player 2 outside his arena', p.run(0x19, SHADOW, mk['shang'], CONTEST,
                                                                             randoms=(5,)), *want_mk('lair'))
    case('Duel RANDOM, MK vs EC', p.run(0x1A, mk['johnny'], SHADOW, DUEL, setting=0, randoms=(0,)), *want_mk('courtyard'))
    case('Duel, a stage by name (Shadow\'s), MK vs EC', p.run(0x19, mk['johnny'], SHADOW, DUEL, setting=1, randoms=(0,)),
         0x19, ranges=[])
    case('Duel, a stage by name, MK vs MK', p.run(0x1C, mk['johnny'], mk['kano'], DUEL, setting=10, randoms=(0,)),
         0x1C, ranges=[])
    case('Duel PLAYER 2, an EC player 2: his home', p.run(0x19, mk['johnny'], SHADOW, DUEL, setting=14, randoms=(0,)),
         0x19, ranges=[])
    case('Duel PLAYER 2, an MK player 2: MK\'s', p.run(PIT, SHADOW, mk['kano'], DUEL, setting=14, randoms=(2,)),
         *want_mk('shrine'))
    case('Tournament, MK vs EC', p.run(0x1B, mk['subzero'], LARCEN, TOURNAMENT, randoms=(3,)), PIT)
    case('Tournament, EC vs EC', p.run(0x1B, SHADOW, LARCEN, TOURNAMENT, randoms=(3,)), 0x1B, ranges=[])
    print('stage pick:', 'FAILED (' + ', '.join(bad) + ')' if bad else 'ok')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
