#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Locate an MK fighter's untouched .SCH bytes in a live fight state.

A probe, not an extractor: MK loads a fighter's .SCH across two RAM areas, and
expands cells to VDP tiles only while drawing a frame. It shows where each run of
the file landed in RAM (for tracing that renderer) and changes no state, disc image
or capture.

    mksch_probe.py SCORPION [STATE]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
from inputs import ROOT
from mkmoves import Session


def anchors(data, width=64):
    """Non-blank, aligned source windows suitable for unambiguous searches."""
    for off in range(0, len(data) - width + 1, width):
        part = data[off:off + width]
        if part.count(0) < width // 3:
            yield off, part


def mapping(source, ram):
    """Return contiguous source/RAM runs proved by unique 64-byte anchors."""
    hits = []
    for off, part in anchors(source):
        at = ram.find(part)
        if at >= 0:
            hits.append((off, at))
    if not hits:
        return []
    runs = []
    start_src, start_ram = prev_src, prev_ram = hits[0]
    for src, ram_at in hits[1:]:
        if src != prev_src + 64 or ram_at != prev_ram + 64:
            runs.append((start_src, prev_src + 64, start_ram))
            start_src, start_ram = src, ram_at
        prev_src, prev_ram = src, ram_at
    runs.append((start_src, prev_src + 64, start_ram))
    return runs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('fighter', help='disc basename, e.g. SCORPION or SUBZERO')
    ap.add_argument('state', nargs='?', default='mk_2p.state')
    ap.add_argument('--disc', default='mk_us', help='extracted disc directory (default: mk_us)')
    ap.add_argument('--verbose', action='store_true', help='show every proved non-blank run')
    args = ap.parse_args()

    fighter = args.fighter.upper()
    path = os.path.join(ROOT, 'extracted', args.disc, fighter + '.SCH')
    source = open(path, 'rb').read()
    s = Session()
    state = args.state if os.path.isabs(args.state) else os.path.join(ROOT, 'build', 'states', args.state)
    s.core.load_state(state, check=False)
    runs = mapping(source, s.core.prg_ram())
    if not runs:
        raise SystemExit('no unchanged .SCH anchors found (wrong state/fighter?)')

    print(f'{os.path.basename(path)}: {len(source):#x} bytes')
    # Blank source runs do not make good search anchors, so collapse the many
    # little proofs into the actual placement transforms first.
    transforms = sorted({ram0 - src0 for src0, _, ram0 in runs})
    print('  proved PRG-RAM placements: ' + ', '.join(f'RAM = file + ${d:X}' for d in transforms))
    if args.verbose:
        for src0, src1, ram0 in runs:
            print(f'    file ${src0:05X}-${src1 - 1:05X} -> PRG RAM ${ram0:05X}-${ram0 + src1 - src0 - 1:05X}')
    print('These are compressed source bytes; decoded 4bpp tiles are only in VDP RAM after MK draws a frame.')


if __name__ == '__main__':
    main()
