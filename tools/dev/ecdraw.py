#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Render any Eternal Champions fighter pose exactly, by running the game's own sprite routine.

The routine (SUB.BIN $F85C) runs on a savestate's memory under unicorn. It reads the
fighter object (a5): $1A sheet, $1B frame, $14 sprite node list, $20 flip flags. It
looks up the sheet in the resource table at $EF4(a6), unpacks compressed tiles
($11784) or picks pool tiles, queues VRAM copies via $CE1A (d0 = source address,
d1 = VRAM byte address, d2 = bytes), and fills sprite nodes (x, y, size, attr) for
$18(a5) pieces.

$CE1A is intercepted: each copy is applied to a private copy of the
savestate's VRAM, then the nodes are rendered with the savestate's palettes.

    ecdraw.py STATE --obj 0x2E330 [--sheet 0x41 --frame 0x4C] --out pose.png
"""
import argparse, os, sys
import numpy as np
from PIL import Image
import unicorn as U
import unicorn.m68k_const as M

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
from vdp import VDPState

STATE_PRGRAM = 0x3810D
STATE_WORDRAM = 0xB810D
DRAW = 0xF85C
DMA_QUEUE = 0xCE1A
STOP = 0x7FF00


def swap(b):
    b = bytearray(b)
    b[0::2], b[1::2] = b[1::2], b[0::2]
    return bytes(b)


class Drawer:
    def __init__(self, state_path):
        st = open(state_path, 'rb').read()
        self.prg = swap(st[STATE_PRGRAM:STATE_PRGRAM + 0x80000])
        self.word = swap(st[STATE_WORDRAM:STATE_WORDRAM + 0x40000])
        self.vdp = VDPState(st)

    def draw(self, obj, sheet=None, frame=None, flip=None):
        mu = U.Uc(U.UC_ARCH_M68K, U.UC_MODE_BIG_ENDIAN)
        mu.ctl_set_cpu_model(M.UC_CPU_M68K_M68000)
        mu.mem_map(0, 0x80000)
        mu.mem_map(0x80000, 0x40000)
        mu.mem_map(0xFF0000, 0x10000)                  # gate array etc: harmless scratch
        mu.mem_write(0, self.prg)
        mu.mem_write(0x80000, self.word)
        if sheet is not None:
            mu.mem_write(obj + 0x1A, bytes([sheet & 0xFF]))
        if frame is not None:
            mu.mem_write(obj + 0x1B, bytes([frame & 0xFF]))
        if flip is not None:
            f = int.from_bytes(mu.mem_read(obj + 0x20, 2), 'big') & ~0x1800 | flip
            mu.mem_write(obj + 0x20, f.to_bytes(2, 'big'))
        mu.mem_write(obj + 0x19E, b'\xff\xff')             # force a fresh unpack
        vram = bytearray(self.vdp.vram)
        copies = []

        def hook(uc, addr, size, ud):
            if addr == DMA_QUEUE:
                src = uc.reg_read(M.UC_M68K_REG_D0) & 0xFFFFFF
                dst = uc.reg_read(M.UC_M68K_REG_D1) & 0xFFFF
                n = uc.reg_read(M.UC_M68K_REG_D2) & 0xFFFF
                data = bytes(uc.mem_read(src, n))
                vram[dst:dst + n] = data[:max(0, 0x10000 - dst)]
                copies.append((src, dst, n))
                sp = uc.reg_read(M.UC_M68K_REG_A7)
                ret = int.from_bytes(uc.mem_read(sp, 4), 'big')
                uc.reg_write(M.UC_M68K_REG_A7, sp + 4)
                uc.reg_write(M.UC_M68K_REG_PC, ret)

        mu.hook_add(U.UC_HOOK_CODE, hook, begin=DMA_QUEUE, end=DMA_QUEUE)
        mu.mem_write(STOP, b'\x4e\x71' * 4)
        sp = 0x7FE00
        mu.mem_write(sp, STOP.to_bytes(4, 'big'))
        mu.reg_write(M.UC_M68K_REG_A7, sp)
        mu.reg_write(M.UC_M68K_REG_A5, obj)
        mu.reg_write(M.UC_M68K_REG_A6, 0x30000)
        mu.reg_write(M.UC_M68K_REG_D6, 0)
        mu.reg_write(M.UC_M68K_REG_D7, 0)
        # the unpacker may need several slices: call until the object isn't mid-unpack
        for _ in range(32):
            mu.emu_start(DRAW, STOP, timeout=5_000_000, count=5_000_000)
            if int.from_bytes(mu.mem_read(obj + 0x19E, 2), 'big') in (0, 0xFFFF):
                break
            mu.mem_write(sp, STOP.to_bytes(4, 'big'))
            mu.reg_write(M.UC_M68K_REG_A7, sp)
            mu.reg_write(M.UC_M68K_REG_A5, obj)
            mu.reg_write(M.UC_M68K_REG_A6, 0x30000)
        # sprite nodes: (x, y, size, attr) words, linked through +8
        n = int.from_bytes(mu.mem_read(obj + 0x18, 2), 'big')
        node = int.from_bytes(mu.mem_read(obj + 0x14, 4), 'big')
        pieces = []
        for _ in range(n):
            if not node:
                break
            x, y, size, attr = (int.from_bytes(mu.mem_read(node + 2 * i, 2), 'big', signed=(i < 2)) for i in range(4))
            pieces.append(dict(x=x, y=y, w=((size >> 10) & 3) + 1, h=((size >> 8) & 3) + 1,
                               tile=attr & 0x7FF, pal=(attr >> 13) & 3, hf=bool(attr & 0x800), vf=bool(attr & 0x1000)))
            node = int.from_bytes(mu.mem_read(node + 8, 4), 'big')
        return pieces, bytes(vram), copies

    def render(self, pieces, vram, size=(256, 256), origin=(128, 200), bg=(255, 0, 255)):
        v = VDPState.__new__(VDPState)
        v.vram, v.cram_raw, v.regs = vram, self.vdp.cram_raw, self.vdp.regs
        img = np.zeros((size[1], size[0], 3), np.uint8)
        img[:] = bg
        for p in reversed(pieces):                      # first piece drawn on top
            px = v.sprite_pixels(p)
            pal = np.array(v.palette(p['pal']), np.uint8)
            X, Y = origin[0] + p['x'], origin[1] + p['y']
            for yy in range(px.shape[0]):
                for xx in range(px.shape[1]):
                    c = px[yy, xx]
                    if c and 0 <= Y + yy < size[1] and 0 <= X + xx < size[0]:
                        img[Y + yy, X + xx] = pal[c]
        return Image.fromarray(img)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('state')
    ap.add_argument('--obj', type=lambda s: int(s, 0), required=True)
    ap.add_argument('--sheet', type=lambda s: int(s, 0))
    ap.add_argument('--frame', type=lambda s: int(s, 0))
    ap.add_argument('--out', default='pose.png')
    a = ap.parse_args()
    d = Drawer(a.state)
    pieces, vram, copies = d.draw(a.obj, a.sheet, a.frame)
    print(f'{len(pieces)} pieces, {len(copies)} VRAM copies')
    for p in pieces:
        print(' ', p)
    d.render(pieces, vram).save(a.out)
    print('wrote', a.out)


if __name__ == '__main__':
    main()
