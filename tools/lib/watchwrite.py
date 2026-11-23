#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""A write watch for debugging: who writes a sub-CPU word.

The core's s68k memory map (40-byte entries: base, read8, read16, write8,
write16, per 64 KB block) gets Python write handlers for the block holding
ADDR; each write to ADDR is logged with the sub CPU's registers (cpuregs).
Read handlers never fire in this core, so reads can't be watched.

    watchwrite.py STATE ADDR [--frames N] [--hold BUTTONS:FROM-TO ...] [--run 30]
    e.g. watchwrite.py duel.state 2E1A2 --frames 45 --hold right:0-30
"""
import argparse, ctypes as C, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scd, cpuregs
from inputs import ROOT

ENTRY = 40


def watch(core, addr, on_write):
    """Hook writes to the word at addr - or to any of a set of words in one 64 KB block (a block takes one
    watch: a second call on it replaces the first); returns an unhook function, which also holds the
    handlers (keep it while watching). on_write(address, value, size)."""
    words = {a & 0xFFFFFE for a in addr} if isinstance(addr, (set, frozenset, list, tuple)) else {addr & 0xFFFFFE}
    assert len({a >> 16 for a in words}) == 1, 'watch: the words must share a 64 KB block'
    addr = next(iter(words))
    sym = cpuregs._symbols(core.lib._name)
    base = C.cast(core.lib.retro_init, C.c_void_p).value - sym['retro_init']
    ptrs = (C.c_void_p * 5).from_address(base + sym['s68k'] + ENTRY * (addr >> 16))
    mem = ptrs[0]
    assert mem, 'block has no direct memory'
    F = C.CFUNCTYPE(None, C.c_uint, C.c_uint)

    def w16(a, d):
        C.c_uint16.from_address(mem + (a & 0xFFFF)).value = d
        if (a & 0xFFFFFE) in words:
            on_write(a, d, 2)

    def w8(a, d):
        C.c_uint8.from_address(mem + ((a & 0xFFFF) ^ 1)).value = d
        if (a & 0xFFFFFE) in words:
            on_write(a, d, 1)

    f16, f8 = F(w16), F(w8)
    old = ptrs[3], ptrs[4]
    ptrs[3], ptrs[4] = C.cast(f8, C.c_void_p).value, C.cast(f16, C.c_void_p).value

    def unhook():
        ptrs[3], ptrs[4] = old
        unhook.keep = None
    unhook.keep = (f16, f8)
    return unhook


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('state')
    ap.add_argument('addr', type=lambda v: int(v, 16))
    ap.add_argument('--frames', type=int, default=60)
    ap.add_argument('--run', type=int, default=0, help='frames to run before watching')
    ap.add_argument('--hold', action='append', default=[], help='buttons:from-to (frames), e.g. right+b:0-30')
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    a = ap.parse_args()
    holds = []
    for h in a.hold:
        b, _, span = h.partition(':')
        f, _, t = span.partition('-')
        holds.append((set(b.split('+')), int(f), int(t)))
    c = scd.Core(saves=os.path.join(os.path.dirname(os.path.abspath(a.state)), 'saves'))
    c.load(a.disc)
    c.load_state(a.state)
    c.run(a.run)
    t = [0]
    log = []
    unhook = watch(c, a.addr, lambda ad, d, n: log.append((t[0], cpuregs.regs(c, 'sub'), ad, d, n)))
    for t[0] in range(a.frames):
        c.buttons[0] = set().union(*[b for b, f, to in holds if f <= t[0] < to])
        c.run(1)
    unhook()
    for f, r, ad, d, n in log:
        print(f'{f:4d} pc {r["pc"]:06X} {"b" if n == 1 else "w"} ${ad:06X} = {d:0{2 * n}X}  '
              + ' '.join(f'{k} {r[k]:06X}' for k in ('d0', 'd1', 'a0', 'a1', 'a5', 'a6')))


if __name__ == '__main__':
    main()
