#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read the Genesis VDP out of a Genesis Plus GX savestate and render it.

    vdp.py STATE --sprites out.png        # sprite layer only, on magenta
    vdp.py STATE --list                   # sprite table
    vdp.py STATE --cram                   # palettes

In this core build the VDP block starts at state offset 0x12025:
sat cache (0x400), VRAM (0x10000, 16-bit words byte-swapped), CRAM (64 x
16-bit native, 9-bit BBBGGGRRR), VSRAM (0x80), registers (0x20).
"""
import argparse
import numpy as np
from PIL import Image

VDP = 0x12025


class VDPState:
    def __init__(self, state_bytes):
        s = state_bytes
        v = bytearray(s[VDP + 0x400:VDP + 0x10400])
        v[0::2], v[1::2] = v[1::2], v[0::2]
        self.vram = bytes(v)
        c = s[VDP + 0x10400:VDP + 0x10480]
        self.cram_raw = [c[2 * i] | c[2 * i + 1] << 8 for i in range(64)]
        self.regs = s[VDP + 0x10500:VDP + 0x10520]

    @classmethod
    def from_file(cls, path):
        return cls(open(path, 'rb').read())

    def palette(self, line):
        out = []
        for i in range(16):
            v = self.cram_raw[line * 16 + i]
            r, g, b = v & 7, (v >> 3) & 7, (v >> 6) & 7
            out.append((r * 36, g * 36, b * 36))
        return out

    @property
    def h40(self):
        return bool(self.regs[12] & 0x81)

    def plane_size(self):
        """(cells wide, cells high) of planes A and B (reg 16)."""
        dims = {0: 32, 1: 64, 3: 128}
        return dims.get(self.regs[16] & 3, 32), dims.get((self.regs[16] >> 4) & 3, 32)

    def plane(self, which):
        """Whole plane 'A' or 'B' as RGB (every cell, its own palette line),
        and a mask of cells that aren't tile 0."""
        base = ((self.regs[2] & 0x38) << 10) if which == 'A' else ((self.regs[4] & 7) << 13)
        w, h = self.plane_size()
        pals = [np.array(self.palette(l), np.uint8) for l in range(4)]
        img = np.zeros((h * 8, w * 8, 3), np.uint8)
        used = np.zeros((h * 8, w * 8), bool)
        for cy in range(h):
            for cx in range(w):
                e = int.from_bytes(self.vram[base + 2 * (cy * w + cx):base + 2 * (cy * w + cx) + 2], 'big')
                t = self.tile(e & 0x7FF)
                if e & 0x800:
                    t = t[:, ::-1]
                if e & 0x1000:
                    t = t[::-1]
                img[cy * 8:cy * 8 + 8, cx * 8:cx * 8 + 8] = pals[(e >> 13) & 3][t]
                used[cy * 8:cy * 8 + 8, cx * 8:cx * 8 + 8] = t > 0
        return img, used

    @property
    def sat_addr(self):
        return (self.regs[5] & (0x7E if self.h40 else 0x7F)) << 9

    def tile(self, index):
        """8x8 array of colour indices for tile number index."""
        d = np.frombuffer(self.vram[(index & 0x7FF) * 32:(index & 0x7FF) * 32 + 32], np.uint8).reshape(8, 4)
        px = np.empty((8, 8), np.uint8)
        px[:, 0::2] = d >> 4
        px[:, 1::2] = d & 15
        return px

    def sprites(self):
        """Sprite list in link order: dicts with x, y, w, h (tiles), tile, pal, hf, vf, prio."""
        out, link, seen = [], 0, set()
        limit = 80 if self.h40 else 64
        while link not in seen and len(out) < limit:
            seen.add(link)
            e = self.vram[self.sat_addr + link * 8:self.sat_addr + link * 8 + 8]
            y = (int.from_bytes(e[0:2], 'big') & 0x3FF) - 128
            size = e[2]
            nxt = e[3] & 0x7F
            attr = int.from_bytes(e[4:6], 'big')
            x = (int.from_bytes(e[6:8], 'big') & 0x1FF) - 128
            out.append(dict(n=link, x=x, y=y, w=((size >> 2) & 3) + 1, h=(size & 3) + 1,
                            tile=attr & 0x7FF, pal=(attr >> 13) & 3, hf=bool(attr & 0x800),
                            vf=bool(attr & 0x1000), prio=bool(attr & 0x8000)))
            if nxt == 0:
                break
            link = nxt
        return out

    def sprite_pixels(self, s):
        """(h*8, w*8) colour-index array for one sprite (tiles are column-major)."""
        img = np.zeros((s['h'] * 8, s['w'] * 8), np.uint8)
        for cx in range(s['w']):
            for cy in range(s['h']):
                img[cy * 8:cy * 8 + 8, cx * 8:cx * 8 + 8] = self.tile(s['tile'] + cx * s['h'] + cy)
        if s['hf']:
            img = img[:, ::-1]
        if s['vf']:
            img = img[::-1, :]
        return img

    def render_sprites(self, width=320, height=224, bg=(255, 0, 255)):
        """RGBA image of the sprite layer; earlier sprites in the link list win."""
        out = np.zeros((height, width, 4), np.uint8)
        out[:, :, :3] = bg
        done = np.zeros((height, width), bool)
        for s in self.sprites():
            px = self.sprite_pixels(s)
            pal = np.array(self.palette(s['pal']), np.uint8)
            for yy in range(px.shape[0]):
                Y = s['y'] + yy
                if not 0 <= Y < height:
                    continue
                for xx in range(px.shape[1]):
                    X = s['x'] + xx
                    c = px[yy, xx]
                    if c and 0 <= X < width and not done[Y, X]:
                        out[Y, X, :3] = pal[c]
                        out[Y, X, 3] = 255
                        done[Y, X] = True
        return Image.fromarray(out, 'RGBA')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('state')
    ap.add_argument('--sprites')
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--cram', action='store_true')
    a = ap.parse_args()
    v = VDPState.from_file(a.state)
    print('regs', v.regs.hex(), 'H40' if v.h40 else 'H32', f'SAT ${v.sat_addr:04X}')
    if a.cram:
        for i in range(4):
            print(i, ' '.join('%02x%02x%02x' % c for c in v.palette(i)))
    if a.list:
        for s in v.sprites():
            print(s)
    if a.sprites:
        v.render_sprites().save(a.sprites)
        print('wrote', a.sprites)


if __name__ == '__main__':
    main()
