#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""What's in the generated folder, build/, and deleting what you name (docs/maintaining.md).

build/ holds only generated files (.gitignore): the disc, and build/shots, runs, states and saves; this
lists their entries with size, age and what made them, and deletes nothing unless named.

    clean.py                      list every entry (largest first)
    clean.py --older 3            only entries untouched for 3 days or more
    clean.py --delete PATH ...    delete these entries (each must be inside one of those folders;
                                  the disc itself, build/Eternal Kombat, needs --disc too)

Kinds: 'disc' (the build), 'check states' (remade by the suite), 'fight states' (made by play.py test,
tools/lib/duelstate.py or the capture tools: keep), '32X disc' (build/Eternal Kombat 32X: tools/build.py
--32x, the gate's), the 32X kind (other 32X output: *32x* entries such as build32x.log, ares-* emulator
runs, 32x* shots), 'scratch', 'output'.
"""
import argparse, os, shutil, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
from inputs import ROOT

SUBS = ('shots', 'runs', 'states', 'saves')                 # build/'s emulator output: listed entry by entry
FOLDERS = ('build',) + tuple(os.path.join('build', d) for d in SUBS)


def kind(rel):
    parts = rel.split(os.sep)
    sub = parts[1] if len(parts) > 2 and parts[1] in SUBS else None
    name = parts[2] if sub else parts[1]
    if rel == os.path.join('build', 'Eternal Kombat'):
        return 'disc'
    if rel == os.path.join('build', 'Eternal Kombat 32X'):
        return '32X disc'                   # (tools/build.py --32x --out it: the gate's)
    if sub is None and ('32x' in name.lower() or name.startswith('ares-')):
        return '32X work'
    if sub == 'shots' and name.startswith('32x'):
        return '32X work'
    if sub == 'states':
        return 'check states' if name == 'checks' else 'fight states'
    if sub is None and (name in ('scratch', 'tmp', 'fresh') or name.startswith('wt-')):
        return 'scratch'
    return 'output'


def size(p):
    if os.path.isfile(p) or os.path.islink(p):
        return os.lstat(p).st_size
    return sum(os.lstat(os.path.join(d, f)).st_size for d, _, fs in os.walk(p) for f in fs)


def newest(p):
    if not os.path.isdir(p):
        return os.lstat(p).st_mtime
    return max([os.lstat(os.path.join(d, f)).st_mtime for d, _, fs in os.walk(p) for f in fs] or [os.lstat(p).st_mtime])


def human(n):
    for unit in ('B', 'K', 'M', 'G'):
        if n < 1024 or unit == 'G':
            return f'{n:.0f}{unit}' if unit == 'B' else f'{n:.1f}{unit}'
        n /= 1024


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--older', type=float, default=0, help='days')
    ap.add_argument('--delete', nargs='+', metavar='PATH')
    ap.add_argument('--disc', action='store_true', help='allow deleting build/Eternal Kombat')
    a = ap.parse_args()
    if a.delete:
        for p in a.delete:
            full = os.path.realpath(os.path.join(ROOT, p))
            rel = os.path.relpath(full, ROOT)
            if rel.split(os.sep)[0] != 'build' or rel in FOLDERS or rel.startswith('..'):
                sys.exit(f'refused: {p} (only entries inside {", ".join(FOLDERS)})')
            if kind(rel) == 'disc' and not a.disc:
                sys.exit(f'refused: {p} is the disc (add --disc)')
            if not os.path.lexists(full):
                print(f'not there: {rel}')
                continue
            n = size(full)
            shutil.rmtree(full) if os.path.isdir(full) and not os.path.islink(full) else os.remove(full)
            print(f'deleted {rel} ({human(n)})')
        return
    now, rows = time.time(), []
    for top in FOLDERS:
        d = os.path.join(ROOT, top)
        if not os.path.isdir(d):
            continue
        for e in os.listdir(d):
            p = os.path.join(d, e)
            rel = os.path.relpath(p, ROOT)
            if rel in FOLDERS:              # (build/shots ...: listed by their own entries)
                continue
            age = (now - newest(p)) / 86400
            if age >= a.older:
                rows.append((size(p), age, rel, kind(rel)))
    rows.sort(reverse=True)
    for n, age, rel, k in rows:
        print(f'{human(n):>8s}  {age:5.1f} d  {k:14s} {rel}')
    print(f'{human(sum(r[0] for r in rows)):>8s}  in {len(rows)} entries')


if __name__ == '__main__':
    main()
