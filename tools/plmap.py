"""Which bytes of an EC .PL file each compressed frame reads.

Every frame of every type-$18 resource is unpacked by the game's own code
(SUB.BIN $11784) under unicorn with a memory-read hook, so the result covers
dictionaries, literal and opcode streams, and any shared sub-frames a frame
calls. Bytes read only by frames you are replacing are free to reuse.
"""
import os
import unicorn as U
import unicorn.m68k_const as M

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = 0x40000
STOP = 0x7FF00
OBJ = 0x70000


def resources(pl):
    """[(resource offset, frame count)] for each type-$18 resource. The frame
    count is the following sheet's count (the sheet chunk comes next)."""
    W = lambda o: int.from_bytes(pl[o:o + 2], 'big')
    L = lambda o: int.from_bytes(pl[o:o + 4], 'big')
    out = []
    for p in range(0, len(pl) - 8, 2):
        if W(p) == 0x18 and L(p + 2) == p + 8:
            res = p + 8
            length = L(res - 0x14)
            # sheet chunk header follows the resource: long len, 0004 0000 0000 01xx 00yy 0000, sheet
            sheet = res - 0x14 + length + 0x10 if res != 0x14 else None
            out.append((res, sheet))
    return out


def frame_reads(pl, sub, res, frame, sheet_byte=0x40):
    """Set of file offsets read while unpacking one frame, and the output."""
    mu = U.Uc(U.UC_ARCH_M68K, U.UC_MODE_BIG_ENDIAN)
    mu.ctl_set_cpu_model(M.UC_CPU_M68K_M68000)
    mu.mem_map(0, 0x80000)
    mu.mem_write(0x6000, sub)
    mu.mem_write(BASE, pl)
    mu.mem_write(STOP, b'\x4e\x71' * 4)
    d0 = (sheet_byte << 8) | frame
    mu.mem_write(OBJ + 0x19E, b'\xff\xff')
    mu.mem_write(OBJ + 0x1A, d0.to_bytes(2, 'big'))
    reads = set()
    lo, hi = BASE, BASE + len(pl)

    def hook(uc, access, addr, size, value, ud):
        if lo <= addr < hi:
            for k in range(size):
                reads.add(addr - BASE + k)

    mu.hook_add(U.UC_HOOK_MEM_READ, hook, begin=lo, end=hi)
    end = 0x60000
    for k in range(32):
        mu.mem_write(0x7FE00, STOP.to_bytes(4, 'big'))
        regs = [(M.UC_M68K_REG_A7, 0x7FE00), (M.UC_M68K_REG_A5, OBJ), (M.UC_M68K_REG_A6, 0x30000),
                (M.UC_M68K_REG_D0, d0), (M.UC_M68K_REG_D6, 0x4000)]
        if k == 0:
            regs += [(M.UC_M68K_REG_A0, BASE + res), (M.UC_M68K_REG_A1, 0x60000)]
        for r, v in regs:
            mu.reg_write(r, v)
        mu.emu_start(0x11784, STOP, count=3_000_000)
        end = max(end, mu.reg_read(M.UC_M68K_REG_A1))
        if int.from_bytes(mu.mem_read(OBJ + 0x19E, 2), 'big') != d0:
            break
    reads -= set(range(res, res + 4)) | set(range(res + 4 + 6 * frame, res + 10 + 6 * frame))
    return reads, bytes(mu.mem_read(0x60000, end - 0x60000))
