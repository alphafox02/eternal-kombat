#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Every tracked Python file carries the licence tag (LICENSE: MIT).

'# SPDX-License-Identifier: MIT' as one of its first two lines (after the #! line). A new tool
without it fails.

    licensecheck.py
"""
import os, subprocess, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
from inputs import ROOT


def main():
    files = subprocess.run(['git', '-C', ROOT, 'ls-files', '*.py'], capture_output=True, text=True, check=True).stdout.split()
    bad = [f for f in files if '# SPDX-License-Identifier: MIT' not in open(os.path.join(ROOT, f)).read().split('\n', 2)[:2]]
    ok = os.path.exists(os.path.join(ROOT, 'LICENSE')) and not bad
    for f in bad:
        print('no licence tag:', f)
    print(f'{len(files) - len(bad)} of {len(files)} Python files tagged, LICENSE '
          f'{"there" if os.path.exists(os.path.join(ROOT, "LICENSE")) else "MISSING"}: {"ok" if ok else "FAIL"}')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
