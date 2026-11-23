#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""MK CD's endings (the story after beating Shang Tsung), for EC's ending scroller (patches.mk_endings).

MK keeps them in RJC.PRG after the fighters' bios: per fighter (Cage, Kano,
Rayden, Liu Kang, Scorpion, Sub-Zero, Sonya) a story page, then a narrow
column shown beside his picture. Lines end in $FF ($FF $FF: a blank line
too); 00 02 14 ends the first page, 00 02 04 the second.

EC's records (CREDITS.CO): lines of [02 00] + 24 characters + 00, a blank
line is 00 00 00; after the text 30 blank lines scroll it off, then FF 00.

    mkendings.py         -> each ending as EC will show it
"""
import os, re, sys, textwrap
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inputs import ROOT

ORDER = ('johnny', 'kano', 'raiden', 'liukang', 'scorpion', 'subzero', 'sonya')
WIDTH = 24
TAIL_BLANKS = 30


def endings():
    """{key: [paragraph, ...]}: MK's words, each paragraph one string (its
    lines joined), the story page's then the column's."""
    b = open(os.path.join(ROOT, 'extracted', 'mk_us', 'RJC.PRG'), 'rb').read()
    start = b.find(b' THROUGH THE BATTLES AND LIFE OR')
    end = b.find(b'GORO LIVES...')
    assert 0 < start < end, 'MK endings not found in RJC.PRG'
    seg = b[start:end]
    seg = re.sub(rb'[^\x20-\x7e\xff]+$', b'', seg)               # (the block's own end codes)
    pages = re.split(rb'\x00\x02[\x04\x14][\x00-\x1f]', seg)    # (4th byte: the page's layout)
    assert len(pages) == 2 * len(ORDER), len(pages)
    out = {}
    for k, key in enumerate(ORDER):
        paras = []
        for page in pages[2 * k:2 * k + 2]:
            for para in re.split(rb'\xff\xff+', page):
                words = b' '.join(l.strip() for l in para.split(b'\xff') if l.strip())
                if words:
                    paras.append(words.decode('ascii'))
        out[key] = paras
    return out


def lines(paras):
    """EC lines (24 wide, None = blank) for the paragraphs."""
    out = []
    for p in paras:
        if out:
            out.append(None)
        out += textwrap.wrap(p, WIDTH)
    return out


def record(paras):
    """EC's ending record bytes."""
    rec = bytearray()
    for l in lines(paras):
        rec += b'\x00\x00\x00' if l is None else b'\x02\x00' + l.ljust(WIDTH).encode('ascii') + b'\x00'
    return bytes(rec + b'\x00\x00\x00' * TAIL_BLANKS + b'\xff\x00')


def main():
    for key, paras in endings().items():
        print(f'--- {key} ({len(record(paras))} bytes)')
        for l in lines(paras):
            print('   ', l or '')


if __name__ == '__main__':
    main()
