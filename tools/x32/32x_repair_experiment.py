#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The 32X build's fourth step: the startup, select-exit and first-select repairs.

On 32x_select_payload_probe.py's disc (its directory: probe.cue and info.json): the startup hook
(32x_art_probe.py's) is reduced to the 32X detection and the adapter request, keeping its RAM
cleanup; the select exit hands MAIN.BIN's VBlank call back to EC's own routine (the fight reused
the hook's memory and hung); with --enable-first-select-experiment (the build's), the 32X layer
is turned on once the select renderer is ready. Emulator-tested only (docs/32x.md).

    32x_repair_experiment.py SOURCE_DIR OUT_DIR [--enable-first-select-experiment]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'lib'))
from disc import Disc, copy_disc
from mkinputs import Asm


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='directory containing probe.cue and info.json')
    parser.add_argument('output', type=Path, help='new output directory')
    parser.add_argument('--enable-first-select-experiment', action='store_true',
                        help='also try enabling the bitmap during the first select visit')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('choose a new output directory')
    info = json.loads((args.source / 'info.json').read_text())
    cue = copy_disc(str(args.source / 'probe.cue'), str(args.output), 'probe')
    disc = Disc(cue)
    main = disc.read_file('MAIN.BIN')
    assert main[0x42:0x46] == bytes.fromhex('6100515c')
    assert main[0x51a0:0x51ae] == bytes.fromhex('48e7c0c00cb94d41525300a130ec')
    # Keep the original register save and cleanup: the cleanup clears the
    # temporary startup code, image and palette from game work RAM.
    asm = Asm(0x51a0)
    asm.w(0x48e7, 0xc0c0)  # same MOVEM as the original portrait probe
    asm.w(0x0cb9); asm.l(0x4d415253); asm.l(0xa130ec)
    asm.bccw(0x66, 'done')
    asm.w(0x13fc, 3); asm.l(0xa15101)
    asm.label('done'); asm.w(0x4ef9); asm.l(0xff523c)  # original cleanup
    code = asm.build()
    disc.patch_file('MAIN.BIN', 0x51a0, code, expect=main[0x51a0:0x51a0 + len(code)])
    # The guard already disables the bitmap when select exits. Replace its
    # debug readback with restoration of the original VBlank call target.
    start = info['game_co_original_size'] + info['cursor_hook_offset']
    game = disc.read_file('GAME.CO')
    hook = game[start:start + info['cursor_hook_size']]
    before = bytes.fromhex('13fc000000a15181103900a1518113c000ff761d423900ff7600')
    after = bytes.fromhex('13fc000000a1518133fc154000ff053e4e714e71423900ff7600')
    assert len(before) == len(after) and hook.count(before) == 1
    offset = start + hook.index(before)
    disc.patch_file('GAME.CO', offset, after, expect=before)
    if args.enable_first_select_experiment:
        # The original early portrait code enabled the bitmap. The cleaned-up
        # startup does not, so experimentally enable it from the cursor hook's
        # ordinary non-confirmation path once the select renderer is ready.
        before_mode = bytes.fromhex('4a3900ff761c67000036523900ff761c')
        after_mode = bytes.fromhex('4a3900ff761c67000014523900ff761c')
        assert hook.count(before_mode) == 1
        mode_offset = start + hook.index(before_mode)
        disc.patch_file('GAME.CO', mode_offset, after_mode, expect=before_mode)
    (args.output / 'repair.json').write_text(json.dumps({
        'source': str(args.source), 'main_offset': 0x51a0,
        'game_co_offset': offset, 'first_select_mode_test': args.enable_first_select_experiment,
        'status': 'experimental diagnostic only',
    }, indent=2) + '\n')
    print('Created diagnostic disc:', cue)


if __name__ == '__main__':
    main()
