#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build the Eternal Kombat disc from your own Eternal Champions and MK discs.

The build always starts from a fresh copy of the original EC disc, then
applies tools/lib/patches.py in order; with --32x it then adds the 32X support
(tools/lib/build32x.py: MK's portraits on the select screen when a 32X is
attached; without one the disc plays as the plain one) and writes the CD cues'
disc times again (the 32X steps move the audio tracks on). Same inputs, same
output, byte for byte.

    python3 tools/build.py                 # -> build/Eternal Kombat/Eternal Kombat.cue
    python3 tools/build.py --32x --out "build/Eternal Kombat 32X"   # with the (experimental) 32X support
    python3 tools/build.py --skip title-text
    python3 tools/build.py --list
"""
import argparse, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lib'))   # (the library: tools/lib/)
from disc import Disc, copy_disc
from inputs import ROOT, scan
from patches import PATCHES
from cdaudio import add_mk_jingle, add_stage_music

NAME = 'Eternal Kombat'
OUT = os.path.join(ROOT, 'build', NAME)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--skip', action='append', default=[], help='patch name to leave out (repeatable)')
    ap.add_argument('--list', action='store_true', help='list patches and exit')
    ap.add_argument('--out', default=OUT)
    ap.add_argument('--32x', dest='x32', action='store_true',
                    help='add the 32X support (experimental, emulator-tested: docs/32x.md)')
    a = ap.parse_args()

    if a.list:
        for name, doc, _ in PATCHES:
            print(f'  {name:16s} {doc}')
        return
    unknown = set(a.skip) - {n for n, _, _ in PATCHES}
    if unknown:
        raise SystemExit(f'unknown patch(es): {", ".join(sorted(unknown))}; see --list')

    t0 = time.time()
    found, _, _ = scan()
    if 'ec_us' not in found:
        raise SystemExit('Eternal Champions CD not found under roms/. Run: python3 tools/checkinputs.py')
    src = found['ec_us']
    print(f'engine : {os.path.relpath(src.cue, ROOT)}')
    plain = os.path.join(ROOT, 'build', 'plain_work') if a.x32 else a.out   # (the 32X steps' input)
    cue = copy_disc(src.cue, plain, NAME)
    if 'mk_us' in found:
        add_mk_jingle(cue, found['mk_us'].cue)
        add_stage_music(cue, found['mk_us'].cue)
    ec = Disc(cue)
    for name, doc, fn in PATCHES:
        if name in a.skip:
            print(f'  skip  {name}')
            continue
        fn(ec, found)
        print(f'  ok    {name:16s} {doc}')
    ec.close()
    if a.x32:
        import shutil
        import build32x
        cue = build32x.add_32x(cue, a.out, NAME)
        shutil.rmtree(plain)
        import patches
        ec = Disc(cue)
        patches.cd_times(ec, found, first=False)
        ec.close()
        print('  ok    32X: the CD cues\' disc times again')
    ec = Disc(cue)
    sha = ec.data_sha1()
    ec.close()
    print(f'output : {os.path.relpath(cue, ROOT)}{" (with the 32X support)" if a.x32 else ""}')
    print(f'data track SHA-1 {sha}  ({time.time() - t0:.1f}s)')


if __name__ == '__main__':
    main()
