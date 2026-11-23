#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Does a fresh clone build exactly this disc?

The gate's last step (docs/maintaining.md): clones this repo's HEAD into build/fresh/repo, links your
roms/ and bios/ into it, makes a new venv from requirements.txt (as a newcomer would), runs
tools/prepare.py and tools/build.py there, and compares every file of its disc with build/Eternal
Kombat/ here. Prints IDENTICAL, or the files that differ, and exits 0 / 1.

    verify_fresh.py              (HEAD; build first, so build/ here is HEAD's disc)
    verify_fresh.py --keep       leave build/fresh/ for a look (else removed when identical)
    verify_fresh.py --venv PATH  use an existing venv instead of making one (faster, less fresh)

Run on the main disk only (build/ is): /tmp may be a small RAM disk. Takes about 15 minutes.
"""
import argparse, hashlib, os, shutil, subprocess, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
from inputs import ROOT

DISC = os.path.join('build', 'Eternal Kombat')


def sha1(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def run(cmd, log, cwd, env):
    t = time.time()
    with open(log, 'w') as f:
        r = subprocess.run(cmd, cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT)
    print(f'  {os.path.basename(log)[:-4]:8s} {"ok" if r.returncode == 0 else "FAILED"} ({time.time() - t:.0f}s; {log})')
    return r.returncode == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--keep', action='store_true')
    ap.add_argument('--venv', help='an existing venv to use')
    a = ap.parse_args()
    git = lambda *args: subprocess.run(['git', '-C', ROOT] + list(args), capture_output=True, text=True, check=True).stdout
    head = git('rev-parse', 'HEAD').strip()
    dirty = [l for l in git('status', '--porcelain', '--untracked-files=no').splitlines()]
    if dirty:
        print('warning: uncommitted changes here - the fresh clone builds HEAD without them:')
        print('  ' + '\n  '.join(dirty[:10]))
    mine = os.path.join(ROOT, DISC)
    if not os.path.isdir(mine):
        sys.exit(f'no {DISC} here: build first')
    base = os.path.join(ROOT, 'build', 'fresh')
    repo = os.path.join(base, 'repo')
    shutil.rmtree(base, ignore_errors=True)
    os.makedirs(base)
    print(f'fresh clone of {head[:10]} in {repo}')
    subprocess.run(['git', 'clone', '-q', ROOT, repo], check=True)
    subprocess.run(['git', '-C', repo, 'checkout', '-q', head], check=True)
    for d in ('roms', 'bios'):
        src = os.path.realpath(os.path.join(ROOT, d))
        if os.path.isdir(src):
            dst = os.path.join(repo, d)
            shutil.rmtree(dst, ignore_errors=True)     # (the clone's own: just its README.md)
            os.symlink(src, dst)
    tmp = os.path.join(base, 'tmp')
    os.makedirs(tmp)
    env = dict(os.environ, TMPDIR=tmp)
    if a.venv:
        py = os.path.join(os.path.abspath(a.venv), 'bin', 'python')
    else:
        venv = os.path.join(base, 'venv')
        subprocess.run([sys.executable, '-m', 'venv', venv], check=True)
        py = os.path.join(venv, 'bin', 'python')
        if not run([py, '-m', 'pip', 'install', '-q', '-r', 'requirements.txt'], os.path.join(base, 'pip.log'), repo, env):
            sys.exit(1)
    for step in ('prepare', 'build'):
        if not run([py, '-P', os.path.join('tools', step + '.py')], os.path.join(base, step + '.log'), repo, env):
            sys.exit(1)
    bad = 0
    for disc in (DISC,):
        here, theirs = os.path.join(ROOT, disc), os.path.join(repo, disc)
        names = sorted(set(os.listdir(here)) | set(os.listdir(theirs)))
        diff = [n for n in names if not (os.path.isfile(os.path.join(here, n)) and os.path.isfile(os.path.join(theirs, n)))
                or sha1(os.path.join(here, n)) != sha1(os.path.join(theirs, n))]
        if diff:
            print(f'DIFFERENT: {disc}: {len(diff)} of {len(names)} files: ' + ', '.join(diff))
            bad += 1
        else:
            print(f'IDENTICAL: all {len(names)} files of {disc}')
    if bad:
        print(f'(kept {base} to compare)')
        sys.exit(1)
    if not a.keep:
        shutil.rmtree(base)


if __name__ == '__main__':
    main()
