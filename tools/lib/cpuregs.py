#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Both 68000s' registers, read from the Genesis Plus GX core itself (a debugging aid).

The libretro API gives no registers, but the core's symbol table names its own
m68k_get_reg / s68k_get_reg (main / sub CPU); they are called through ctypes at
the core's load address (from `nm`, so any unstripped build works).

    from cpuregs import regs
    r = regs(core, 'sub')      # {'d0'..'d7', 'a0'..'a7', 'pc', 'sr', 'sp', 'usp', 'isp'}

    cpuregs.py STATE [--disc CUE]   # load a state (the built disc by default), print both CPUs
"""
import ctypes as C, os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

NAMES = [f'd{i}' for i in range(8)] + [f'a{i}' for i in range(8)] + ['pc', 'sr', 'sp', 'usp', 'isp']
_fns = {}


def _symbols(path):
    out = subprocess.run(['nm', path], capture_output=True, text=True, check=True).stdout
    return {l.split()[2]: int(l.split()[0], 16) for l in out.splitlines() if len(l.split()) == 3}


def _getters(core):
    key = id(core.lib)
    if key not in _fns:
        sym = _symbols(core.lib._name)
        base = C.cast(core.lib.retro_init, C.c_void_p).value - sym['retro_init']
        f = C.CFUNCTYPE(C.c_uint, C.c_int)
        _fns[key] = {'main': f(base + sym['m68k_get_reg']), 'sub': f(base + sym['s68k_get_reg'])}
    return _fns[key]


def regs(core, cpu='sub'):
    g = _getters(core)[cpu]
    return {n: g(i) & 0xFFFFFFFF for i, n in enumerate(NAMES)}


def show(r):
    return ('pc %06X sr %04X  ' % (r['pc'], r['sr'] & 0xFFFF)
            + ' '.join('%s %08X' % (n, r[n]) for n in NAMES[:16]))


if __name__ == '__main__':
    import argparse, scd
    from inputs import ROOT
    ap = argparse.ArgumentParser()
    ap.add_argument('state')
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    a = ap.parse_args()
    c = scd.Core()
    c.load(a.disc)
    c.load_state(a.state, check=False)
    for cpu in ('main', 'sub'):
        print(cpu, show(regs(c, cpu)))
