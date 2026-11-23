#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Are the discs this project needs under roms/, and are they the right dumps?

Put your own rips anywhere under roms/ (any folder names, bin/cue,
one-bin-per-track or single-bin). Discs are recognised by the SHA-1 of their
data track, so file names don't matter. A different revision is a warning,
not a refusal.

    python3 tools/checkinputs.py
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lib'))   # (the library: tools/lib/)
from inputs import KNOWN, ROMS, scan

BIOS = os.path.join(os.path.dirname(ROMS), 'bios')
BIOS_MD5 = {'bios_CD_U.bin': '2efd74e3232ff260e371b99f84024f7f'}


def main():
    found, other, archives = scan()
    ok = True
    print(f'Looking in {ROMS}\n')
    for key, k in KNOWN.items():
        d = found.get(key)
        tag = 'required' if k['required'] else 'optional'
        if d is None:
            print(f'  [missing]  {k["title"]}  ({tag})\n             {k["role"]}')
            ok &= not k['required']
        else:
            warn = getattr(d, 'unverified', False)
            print(f'  [{"differs" if warn else "ok"}]{" " * (7 - (7 if warn else 2))}  {k["title"]}\n'
                  f'             {os.path.relpath(d.cue, ROMS)}')
            if warn:
                print('             different dump/revision than the one offsets were measured on; may still work')
    for cue, note in other:
        if 'looks like' not in note:
            print(f'\n  note: {os.path.relpath(cue, ROMS)}: {note}')
    if archives:
        print('\n  Archives under roms/ (only extracted discs are read):')
        for a in archives:
            print(f'    {os.path.relpath(a, ROMS)}')
        if any(KNOWN[k]['required'] and k not in found for k in KNOWN):
            print('  Extract one into its own folder, e.g.\n    7z x "roms/archive.7z" -o"roms/<name>"'
                  '\n    unrar x "roms/archive.rar" "roms/<name>/"')

    print('\nBIOS (needed only to run the emulator, not to build):')
    import hashlib
    for fn, md5 in BIOS_MD5.items():
        p = os.path.join(BIOS, fn)
        if not os.path.exists(p):
            print(f'  [missing]  bios/{fn}  (Sega CD Model 1 v1.10 USA, md5 {md5})')
        else:
            got = hashlib.md5(open(p, 'rb').read()).hexdigest()
            print(f'  [{"ok" if got == md5 else "differs"}]  bios/{fn}')
    print('\nReady to build.' if ok else '\nNot ready: a required disc is missing.')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
