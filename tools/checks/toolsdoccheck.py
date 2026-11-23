#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Every tool has its line in docs/tools.md, and every tool named there exists.

docs/maintaining.md, rule 5: a tracked tools/**/*.py missing from the table, or a row naming no
file, fails.

    toolsdoccheck.py
"""
import os, re, subprocess, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
from inputs import ROOT


def main():
    files = subprocess.run(['git', '-C', ROOT, 'ls-files', 'tools'], capture_output=True, text=True,
                           check=True).stdout.split()
    tools = {f[len('tools/'):] for f in files if f.endswith('.py')}
    doc = open(os.path.join(ROOT, 'docs', 'tools.md')).read()
    sect, rows = '', set()
    for line in doc.splitlines():
        m = re.match(r'## tools/([a-z_0-9]+)/', line)
        if line.startswith('## '):
            sect = m.group(1) + '/' if m else ''
        r = re.match(r'\| `([a-z_0-9]+\.py)` \|', line)
        if r:
            rows.add(sect + r.group(1))
    missing, stale = sorted(tools - rows), sorted(rows - tools)
    for m in missing:
        print(f'no line in docs/tools.md: tools/{m}')
    for s in stale:
        print(f'docs/tools.md names a tool that isn\'t there: tools/{s}')
    print(f'{len(tools)} tools, {len(rows)} lines: {"ok" if not missing and not stale else "FAIL"}')
    sys.exit(1 if missing or stale else 0)


if __name__ == '__main__':
    main()
