#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The optional 32X support (docs/32x.md): MK CD's own portraits on the select screen.

tools/build.py --32x calls add_32x on the disc its patches made (the standard build leaves it out). On
a Sega CD with a 32X, the select screen shows MK CD's own portraits for the seven MK fighters, drawn
by the 32X (159 colours where the Genesis has 14), on every visit; without a 32X the disc plays as the
plain one. Emulator-tested only (PicoDrive, ares, Genesis Plus GX), not on hardware (docs/32x.md).

    build32x.py PLAIN_CUE OUT_DIR     (by hand: a plain disc's cue -> OUT_DIR/Eternal Kombat.cue)

The chain (tools/x32/, 2026-11-21/22), each step from the one before:
  1. 32x_art_probe.py          32X detection hooked into MAIN.BIN's startup (and its old portrait
                                test, replaced in step 4; its RAM cleanup kept)
  2. 32x_cd_roster_preview.py  the seven MK portraits, packed for the 32X framebuffer, from
                                extracted/ (prepare.py: MK's portraits from your disc)
  3. 32x_select_payload_probe.py  the payload appended to GAME.CO: the portraits, EC's cursor frames
                                (from your EC disc), the 32X renderer, the cursor hook and its guard
  4. 32x_repair_experiment.py  the startup reduced to detection and the adapter request; the VBlank
                                call restored as select exits (the fight hung: it reused the hook's
                                memory); the 32X layer enabled once select is ready
  5. 32x_reentry.py            every visit to select as the first: the exit hands VBlank back to the
                                coordinator, which re-arms the transfer and renderer when it sees select
                                again
Same inputs, same disc: the result is deterministic (checked by tools/dev/verify_fresh.py).
"""
import os, shutil, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inputs import ROOT
from disc import copy_disc

X32 = os.path.join(ROOT, 'tools', 'x32')
PAYLOAD_FLAGS = ['--sh2-render-demo', '--sh2-double-render-demo', '--sh2-cursor-demo', '--sh2-fallback-demo',
                 '--sh2-startup-demo', '--sh2-release-bus-demo', '--sh2-transfer-demo']


def add_32x(plain_cue, out_dir, name):
    """The 32X steps on the plain disc at plain_cue -> out_dir/name.cue (returned)."""
    work = os.path.join(ROOT, 'build', 'x32_work')
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    py = [sys.executable, '-P']
    steps = [('32X detection at startup', [os.path.join(X32, '32x_art_probe.py'), os.path.join(work, 'art'),
                                           '--source', plain_cue]),
             ('the MK portraits for the 32X', [os.path.join(X32, '32x_cd_roster_preview.py'),
                                                os.path.join(ROOT, 'extracted'), '-', os.path.join(work, 'roster')]),
             ('the select-screen payload', [os.path.join(X32, '32x_select_payload_probe.py'),
                                            os.path.join(work, 'art', 'probe.cue'), os.path.join(work, 'roster'),
                                            os.path.join(work, 'payload')] + PAYLOAD_FLAGS),
             ('startup, exit and first-select repairs', [os.path.join(X32, '32x_repair_experiment.py'),
                                                         os.path.join(work, 'payload'), os.path.join(work, 'repaired'),
                                                         '--enable-first-select-experiment']),
             ('the portraits on every visit to select', [os.path.join(X32, '32x_reentry.py'),
                                                         os.path.join(work, 'repaired'), os.path.join(work, 'final')])]
    for label, cmd in steps:
        r = subprocess.run(py + cmd, cwd=ROOT, capture_output=True, text=True)
        if r.returncode:
            sys.stdout.write(r.stdout[-2000:] + r.stderr[-2000:])
            sys.exit(f'failed: 32X: {label}')
        print(f'  ok    32X: {label}')
    cue = copy_disc(os.path.join(work, 'final', 'probe.cue'), out_dir, name)
    shutil.rmtree(work)
    return cue


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    print('output :', os.path.relpath(add_32x(sys.argv[1], sys.argv[2], 'Eternal Kombat'), ROOT))


if __name__ == '__main__':
    main()
