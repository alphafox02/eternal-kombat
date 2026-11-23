#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Decode Eternal Champions CD fighter sprite frames (.PL) by running the game's own unpacker.

The unpacker (SUB.BIN $11784) runs under a 68000 emulator (unicorn), called the way the game
calls it at $FC24:
    a0 = .PL file, d0 = frame number, a1 = output buffer, a5 = fighter object,
    d6 = flags (bit 8 selects another path, kept clear).
It returns with a1 past the last word written. The game requires output
<= $12C0 bytes (150 tiles).

Format, as read from the code:
    +0   long  offset of the bank section (relative to file start)
    +4   6-byte frame records: bank#, dict offset/2, literal stream offset,
         opcode stream offset (both relative to the bank)
    bank section: +2 + 4*bank -> long offset of the bank
Each opcode byte dispatches through a jump table at $1180C into unrolled
"copy literal word / copy dictionary word" sequences.

    ecsprite.py BLA.PL --frame 3 --out f3.bin     # raw 4bpp tiles of one frame
    ecsprite.py BLA.PL --scan                      # tiles per frame for every frame
"""
import argparse, os
import unicorn as U
import unicorn.m68k_const as M

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SUB_BASE = 0x6000
UNPACK = 0x11784
PL_AT = 0x40000          # anywhere free in the emulated 512K
OUT_AT = 0x60000
OBJ_AT = 0x70000
STOP = 0x7FF00
MAX_OUT = 0x12C0


def frames_resource(pl):
    """File offset of the compressed-frames resource (type $18) in a .PL.
    Header: long, long, long, then (word type, long offset) entries."""
    for o in range(0x0C, 0x40, 6):
        if int.from_bytes(pl[o:o + 2], 'big') == 0x18:
            return int.from_bytes(pl[o + 2:o + 6], 'big')
    raise ValueError('no type-$18 resource in header')


class Unpacker:
    def __init__(self, sub_path=None):
        sub_path = sub_path or os.path.join(ROOT, 'extracted', 'ec_us', 'SUB.BIN')
        self.sub = open(sub_path, 'rb').read()

    def frame(self, pl, n):
        """Unpacked tile bytes for frame n of a .PL file (bytes)."""
        mu = U.Uc(U.UC_ARCH_M68K, U.UC_MODE_BIG_ENDIAN)
        try:
            mu.ctl_set_cpu_model(M.UC_CPU_M68K_M68000)
        except Exception:                                   # noqa: BLE001
            pass
        mu.mem_map(0, 0x80000)
        mu.mem_write(SUB_BASE, self.sub)
        mu.mem_write(PL_AT, pl)
        mu.mem_write(OBJ_AT + 0x19E, b'\xff\xff')            # "no frame cached"
        mu.mem_write(STOP, b'\x4e\x71' * 4)                   # nops at the return address
        sp = 0x7FE00
        mu.mem_write(sp, STOP.to_bytes(4, 'big'))             # jsr return address
        mu.reg_write(M.UC_M68K_REG_A7, sp)
        mu.reg_write(M.UC_M68K_REG_A0, PL_AT + frames_resource(pl))
        mu.reg_write(M.UC_M68K_REG_A1, OUT_AT)
        mu.reg_write(M.UC_M68K_REG_A5, OBJ_AT)
        mu.reg_write(M.UC_M68K_REG_A6, 0x30000)               # game's global base
        # The unpacker is time-sliced: when it runs out of budget it saves its
        # registers at -$3F6E(a6), sets $19E(a5) = frame and returns. Calling
        # again with the same frame resumes. Keep calling until the mark clears.
        end = OUT_AT
        for _ in range(64):
            mu.mem_write(sp, STOP.to_bytes(4, 'big'))
            mu.reg_write(M.UC_M68K_REG_A7, sp)
            mu.reg_write(M.UC_M68K_REG_A5, OBJ_AT)
            mu.reg_write(M.UC_M68K_REG_A6, 0x30000)
            mu.reg_write(M.UC_M68K_REG_D0, n & 0xFF)
            mu.reg_write(M.UC_M68K_REG_D6, 0)
            mu.emu_start(UNPACK, STOP, timeout=2_000_000, count=2_000_000)
            end = max(end, mu.reg_read(M.UC_M68K_REG_A1))
            if int.from_bytes(mu.mem_read(OBJ_AT + 0x19E, 2), 'big') != (n & 0xFF):
                break
        else:
            raise ValueError(f'frame {n}: unpacker never finished')
        size = end - OUT_AT
        if not 0 <= size <= MAX_OUT * 2:
            raise ValueError(f'frame {n}: implausible output size {size:#x}')
        return bytes(mu.mem_read(OUT_AT, size))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pl')
    ap.add_argument('--frame', type=int)
    ap.add_argument('--out')
    ap.add_argument('--scan', action='store_true')
    a = ap.parse_args()
    pl = open(a.pl, 'rb').read()
    u = Unpacker()
    if a.scan:
        for n in range(256):
            try:
                t = u.frame(pl, n)
                print(f'{n:3d}: {len(t) // 32:3d} tiles')
            except Exception as e:                          # noqa: BLE001
                print(f'{n:3d}: {e}')
    elif a.frame is not None:
        t = u.frame(pl, a.frame)
        print(f'frame {a.frame}: {len(t)} bytes = {len(t) // 32} tiles')
        if a.out:
            open(a.out, 'wb').write(t)


if __name__ == '__main__':
    main()

