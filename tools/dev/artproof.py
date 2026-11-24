#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Do two versions of the art builder draw the same frames?

Builds every MK fighter's .PL with tools/lib/scorpion_full.py as it is and as it was at a git
revision, then decodes every frame of every sheet from the built files with EC's own unpacker
(tools/lib/ecunpack.py, SUB.BIN $11784) and compares its tile bytes and its record (boxes, points,
piece list): what the game reads. For changes to how the art is stored, not to what it shows.

    artproof.py REV [--fighters kano,raiden]   -> per fighter: poses, .PL size, frames that differ
"""
import argparse, hashlib, os, subprocess, sys, tempfile
LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib')
sys.path.insert(0, LIB)
if '--dump' in sys.argv and sys.argv[sys.argv.index('--dump') + 1] != '-':   # the old builder, under its own
    import importlib.util                                                      #  name before anything imports
    _s = importlib.util.spec_from_file_location(                               #  it (the library puts its own
        'scorpion_full', os.path.join(sys.argv[sys.argv.index('--dump') + 1], 'scorpion_full.py'))   #  dir first)
    sys.modules['scorpion_full'] = importlib.util.module_from_spec(_s)
    _s.loader.exec_module(sys.modules['scorpion_full'])
from inputs import ROOT

W = lambda pl, o: int.from_bytes(pl[o:o + 2], 'big')


def dump(fighters, out):
    """(in its own process: tools/lib/scorpion_full.py, or the old one first on sys.path)"""
    import json, patches, plsheet, ecunpack, scorpion_full as sf
    u = ecunpack.Unpacker(open(os.path.join(ROOT, 'extracted', 'ec_us', 'SUB.BIN'), 'rb').read())
    res = {}
    for spec in patches.MK_SPECS:
        if fighters and spec.key not in fighters:
            continue
        patches.use(spec)
        try:
            pl, rep = sf.build(open(os.path.join(ROOT, 'extracted', 'ec_us', 'BLA.PL'), 'rb').read(), ROOT)
        except ValueError as e:                  # (his art too big for this builder)
            res[spec.key] = {'error': str(e)}
            continue
        u.load(pl)
        fr = {}
        for sh in plsheet.all_sheets(pl):
            for f in range(sh['n']):
                tiles = (u.frame(sh['res'], f) if sh['kind'] == 'packed'
                         else plsheet.render_raw(pl, sh, f, raw=True).tobytes())
                q0 = sh['sheet'] + 6 + W(pl, sh['sheet'] + 6 + 2 * f)
                q = q0 + 2 + 4 * W(pl, q0)
                q += 2 + 2 * W(pl, q)
                while not W(pl, q) & 0x8000:
                    q += 6
                fr[f"{sh['sid']:02X}:{f:02X}"] = [hashlib.md5(tiles).hexdigest(), hashlib.md5(pl[q0:q + 2]).hexdigest()]
        res[spec.key] = {'poses': rep['poses'], 'len': len(pl), 'frames': fr}
    json.dump(res, open(out, 'w'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rev', nargs='?')
    ap.add_argument('--fighters', default='')
    ap.add_argument('--dump', nargs=2, metavar=('LIBDIR', 'OUT'), help=argparse.SUPPRESS)
    a = ap.parse_args()
    fighters = [f for f in a.fighters.split(',') if f]
    if a.dump:
        return dump(fighters, a.dump[1])
    import json
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, 'scorpion_full.py'), 'wb') as f:
            f.write(subprocess.run(['git', '-C', ROOT, 'show', f'{a.rev}:tools/lib/scorpion_full.py'],
                                   check=True, capture_output=True).stdout)
        runs = [subprocess.Popen([sys.executable, '-P', os.path.abspath(__file__), '--fighters', a.fighters,
                                  '--dump', d, os.path.join(tmp, f'{n}.json')]) for n, d in (('old', tmp), ('new', '-'))]
        if any(r.wait() for r in runs):
            sys.exit('a build failed')
        old, new = (json.load(open(os.path.join(tmp, f'{n}.json'))) for n in ('old', 'new'))
    bad = False
    for key in old:
        if 'error' in old[key] or 'error' in new[key]:
            print(f"{key}: not compared - old: {old[key].get('error', 'ok')}; new: {new[key].get('error', 'ok')}")
            bad = True
            continue
        fa, fb = old[key]['frames'], new[key]['frames']
        diff = sorted(k for k in fa.keys() | fb.keys() if fa.get(k) != fb.get(k))
        bad |= bool(diff)
        print(f"{key}: poses {old[key]['poses']} -> {new[key]['poses']}, .PL {old[key]['len']} -> {new[key]['len']} bytes; "
              f'{len(fa)} frames, {len(diff)} differ' + (f': {" ".join(diff[:12])}' if diff else ''), flush=True)
    print('artproof:', 'frames differ' if bad else 'every frame the same')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
