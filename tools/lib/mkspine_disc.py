#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Extract Sub-Zero fatality sprite pieces directly from MK CD's PAC.PRG.

    mkspine_disc.py --disc extracted/mk_us --check REFERENCE_EXTRACTED
    mkspine_disc.py --disc extracted/mk_us --out extracted

The cache uses the existing mkframes.pieces format. --check compares both
piece names/pixels and serialized cache bytes against a capture.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # (tools run with python -P)
import argparse
import hashlib
import pickle
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
# Offset, dimensions, horizontal flip, expected pixel hash. Order matches the
# first occurrence of each piece in the original fatality replay.
PIECES = (
    (0x1FCA2,8,32,1,'e1f9009034'), (0x1FD22,8,16,1,'19ef34d7db'),
    (0x1FD62,16,24,1,'39e0872c70'), (0x1FE22,8,16,1,'8999c0bbd2'),
    (0x1FBE2,8,32,0,'d346e71c74'), (0x1FC62,8,16,0,'11d2f5dd82'),
    (0x1FCA2,8,32,0,'42b78c8421'), (0x1FD22,8,16,0,'7a6326d6f1'),
    (0x1FD62,16,24,0,'f0c2f899c6'), (0x1FE22,8,16,0,'f473d1bc63'),
)


def extract(data):
    out = {}
    for off, width, height, flip, expected in PIECES:
        raw = data[off:off + width*height//2]
        if len(raw) != width*height//2:
            raise ValueError(f'truncated PAC.PRG at {off:#x}')
        a = np.frombuffer(raw, np.uint8).reshape(width//8, height//8, 8, 4)
        p = np.empty((width//8, height//8, 8, 8), np.uint8)
        p[:,:,:,0::2], p[:,:,:,1::2] = a >> 4, a & 15
        p = p.transpose(1,2,0,3).reshape(height,width)
        if flip: p = p[:, ::-1]
        name = hashlib.sha1(bytes(p.shape) + p.tobytes()).hexdigest()[:10]
        if name != expected:
            raise ValueError(f'unexpected spine pixels at {off:#x}: {name}')
        out[name] = [(0, 0, p)]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--disc', type=Path, default=ROOT/'extracted'/'mk_us')
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', type=Path, metavar='REFERENCE_EXTRACTED')
    group.add_argument('--out', type=Path, metavar='EXTRACTED')
    a = ap.parse_args()
    pieces = extract((a.disc/'PAC.PRG').read_bytes())
    data = pickle.dumps(pieces)
    path = (a.check or a.out)/'mk_frames'/'szfatal.pkl'
    if a.check:
        reference = pickle.loads(path.read_bytes())
        if list(reference) != list(pieces) or any(
            not np.array_equal(reference[k][0][2], pieces[k][0][2]) for k in pieces):
            raise SystemExit('spine pieces differ')
        if path.read_bytes() != data:
            raise SystemExit('all spine pixels match, but serialized cache bytes differ')
        print(f'{len(pieces)} spine pieces and serialized cache identical')
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        print(f'{len(pieces)} spine pieces -> {path}')


if __name__ == '__main__': main()
