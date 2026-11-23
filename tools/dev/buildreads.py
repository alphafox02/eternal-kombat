#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Which captured poses does the build read?

Runs tools/build.py with every extracted/**/indexed.npy it loads wrapped so that
each pose read is recorded (going through all of them counts as all). The recipes
must be exact for these (docs/research/reproducibility_2026-11.md); a pose never
read only keeps its place.

    buildreads.py [--out PATH]      -> JSON {capture path: [pose numbers read]},
                                       and build_files.txt beside it: every file under extracted/ read
"""
import argparse, json, os, runpy, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
from inputs import ROOT

USED = {}


class Recorded(np.ndarray):
    def __array_finalize__(self, obj):
        self._name = None

    def _mark(self, k):
        if self._name is None:
            return
        u = USED.setdefault(self._name, set())
        n = self.shape[0]
        k = k[0] if isinstance(k, tuple) else k
        if isinstance(k, (int, np.integer)):
            u.add(int(k) % n)
        elif isinstance(k, slice):
            u.update(range(*k.indices(n)))
        elif isinstance(k, (list, np.ndarray)):
            a = np.asarray(k)
            u.update(np.nonzero(a)[0].tolist() if a.dtype == bool else (a % n).tolist())
        else:
            u.update(range(n))

    def __getitem__(self, k):
        self._mark(k)
        out = np.ndarray.__getitem__(self, k)
        if isinstance(out, Recorded):
            out._name = None
        return out

    def __iter__(self):
        self._mark(slice(None))
        for i in range(self.shape[0]):
            yield np.ndarray.__getitem__(self, i)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(ROOT, 'extracted', 'build_reads.json'))
    a = ap.parse_args()
    load = np.load
    import builtins
    opened = set()
    real_open = builtins.open

    def logging_open(path, *args, **kw):                    # every file under extracted/ it opens
        try:
            q = os.path.relpath(os.path.abspath(os.fspath(path)), ROOT)
            if q.startswith('extracted') and not (args and 'w' in str(args[0])) and 'w' not in str(kw.get('mode', '')):
                opened.add(q)
        except TypeError:
            pass
        return real_open(path, *args, **kw)
    builtins.open = logging_open

    def recording_load(path, *args, **kw):
        arr = load(path, *args, **kw)
        p = os.path.relpath(os.path.abspath(str(path)), ROOT)
        if p.startswith('extracted'):
            opened.add(p)
        if p.startswith('extracted') and p.endswith('indexed.npy') and isinstance(arr, np.ndarray) and arr.ndim == 3:
            r = arr.view(Recorded)
            r._name = p
            USED.setdefault(p, set())
            return r
        return arr
    np.load = recording_load
    sys.argv = [os.path.join(ROOT, 'tools', 'build.py')]
    try:
        runpy.run_path(sys.argv[0], run_name='__main__')
    finally:
        builtins.open = real_open
        json.dump({k: sorted(v) for k, v in sorted(USED.items())}, open(a.out, 'w'), indent=0)
        files = os.path.join(os.path.dirname(a.out), 'build_files.txt')
        open(files, 'w').write('\n'.join(sorted(opened)) + '\n')
        print(f'{len(opened)} files under extracted/ read -> {os.path.relpath(files, ROOT)}')
        n = sum(len(v) for v in USED.values())
        print(f'{len(USED)} captures loaded, {n} poses read -> {os.path.relpath(a.out, ROOT)}')


if __name__ == '__main__':
    main()
