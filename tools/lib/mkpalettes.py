#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read the fight palettes used by mk_meta directly from MK CD's PAC.PRG.

    mkpalettes.py --disc extracted/mk_us --check REFERENCE_EXTRACTED

--check compares every palette referenced by data/mk_meta byte for byte with
the existing captured JSON; it never writes to the reference directory.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # (tools run with python -P)
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
# File offsets in the USA disc's PAC.PRG. The first word ($0E0E) is a
# transparent placeholder: the VDP backdrop entry in the reference is zero.
OFFSETS = {
    'mk_2p:0': 0x1C050, 'mk_2p:1': 0x1C030,
    'mk_raiden_2p:0': 0x1C070, 'mk_johnny_sonya_2p:1': 0x1C090,
    'mk_liukang_2p:0': 0x1C0B0, 'mk_kano_2p:0': 0x1C0D0,
    'mk_johnny_2p:0': 0x1C0F0,
    # Two RGB capture recipes name palettes outside data/mk_meta.
    'mk_subzero_2p:1': 0x1C050, 'scfatal@35:1': 0x1C050,
    # Reptile (MK CD's secret fight: player 2 as Scorpion's sprites in these colours)
    'mk_reptile_1p:1': 0x1BF10,
}


def palette(source, disc=None):
    """Return 16 Genesis Plus GX CRAM values for a known STATE:LINE."""
    if source not in OFFSETS:
        raise KeyError(f'unknown palette source: {source}')
    path = Path(disc or ROOT / 'extracted' / 'mk_us') / 'PAC.PRG'
    data = path.read_bytes()
    off = OFFSETS[source]
    words = data[off:off + 32]
    if len(words) != 32 or words[:2] != bytes.fromhex('0e0e'):
        raise ValueError(f'unexpected palette at {path}+{off:#x}')
    out = [0]
    for i in range(2, 32, 2):
        word = int.from_bytes(words[i:i + 2], 'big')
        if word & ~0x0EEE:
            raise ValueError(f'invalid Genesis color {word:#x} at {off+i:#x}')
        out.append(((word >> 1) & 7) | (((word >> 5) & 7) << 3) | (((word >> 9) & 7) << 6))
    return out


def check(reference, disc, meta):
    errors, checked = [], 0
    for file in sorted(Path(meta).glob('*/*.json')):
        for name, source in json.loads(file.read_text()).items():
            if name not in ('cram.json', 'cram_p2.json'):
                continue
            dest = Path(reference) / file.parent.name / file.stem / name
            try:
                expected = json.dumps(palette(source, disc)).encode()
                if dest.read_bytes() != expected:
                    errors.append(f'{dest}: differs')
            except (OSError, KeyError, ValueError) as e:
                errors.append(f'{dest}: {e}')
            checked += 1
    for error in errors:
        print(error)
    print(f'{checked - len(errors)}/{checked} palette files identical')
    if not checked or errors:
        raise SystemExit(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--disc', type=Path, default=ROOT / 'extracted' / 'mk_us')
    ap.add_argument('--check', type=Path, required=True, metavar='REFERENCE_EXTRACTED')
    ap.add_argument('--meta', type=Path, default=ROOT / 'data' / 'mk_meta')
    a = ap.parse_args()
    check(a.check, a.disc, a.meta)


if __name__ == '__main__':
    main()
