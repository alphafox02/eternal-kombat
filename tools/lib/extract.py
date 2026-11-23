#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Unpack every recognised disc's filesystem to extracted/<id>/.

    extract.py            # all discs found under roms/
    extract.py ec_us      # just one

The build reads some of these (EC's modules as shipped, MK's sounds, its
ending text): tools/prepare.py runs this first. Also for the disassembler,
diffing and art tools.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inputs import ROOT, scan

OUT = os.path.join(ROOT, 'extracted')


def main():
    found, _, _ = scan()
    want = sys.argv[1:] or list(found)
    for key in want:
        d = found.get(key)
        if d is None:
            print(f'{key}: not found under roms/')
            continue
        if not hasattr(d, 'files'):
            print(f'{key}: cartridge, nothing to unpack ({os.path.relpath(d.path, ROOT)})')
            continue
        dst = os.path.join(OUT, key)
        os.makedirs(dst, exist_ok=True)
        files = d.files()
        for name in files:
            path = os.path.join(dst, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'wb') as f:
                f.write(d.read_file(name))
        # the 16-sector system area (boot header, IP/SP) isn't a file; keep it too
        with open(os.path.join(dst, '_SYSTEM_AREA.bin'), 'wb') as f:
            f.write(d.read(0, 16))
        print(f'{key}: {len(files)} files -> {os.path.relpath(dst, ROOT)}/')


if __name__ == '__main__':
    main()
