#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The 32X portraits on every visit to the select screen, not just the first (docs/32x.md).

32x_repair_experiment.py hands MAIN.BIN's VBlank call ($FF053A: jsr) back to EC's own routine ($FF1540)
as select exits: the fight reuses the cursor hook's and renderer's scratch RAM, and calling into it
hung the game. That also took the coordinator ($FF5940: detect select, copy the payload to the 32X,
install the renderer and hook) out of the chain for good, so a second visit got the Genesis portraits.

Two changes, so every visit starts as the first did:
  - the select exit (the cursor hook's guard, in GAME.CO's payload: 26 bytes, the same length) turns
    the bitmap off (clr.b, 2 bytes shorter than its move.b #0), hands VBlank to the coordinator instead
    of EC's routine, clears the transfer's state ($FF5BF0) and, as before, the hook's marker ($FF7600).
    The coordinator calls EC's routine first, as always; through a fight it only reads main RAM and the
    32X's registers, waiting for the select screen's signature in RAM;
  - when it sees select (its move.b #1,$FF5BF0), it calls an arm routine instead (in MAIN.BIN's
    resident image at $5BBA, free bytes before its markers at $5BE0): the transfer marker set, and the
    renderer's state ($FF6C00-$FF6C07) cleared so it is copied and started again. That RAM is the
    game's between visits (a first try cleared it at the exit: by the next select it held the game's
    data, the renderer wasn't re-copied, and the game jumped into junk and froze).
Without a 32X none of this runs (the coordinator's 'absent' flag; the hook is never installed).

    32x_reentry.py SOURCE_DIR OUT_DIR      (SOURCE_DIR: 32x_repair_experiment.py's output)
"""
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'lib'))
from disc import Disc, copy_disc
from mkinputs import Asm

ARM = 0x5BBA                     # MAIN.BIN offset = RAM $FF5BBA (free up to the markers at $5BE0)
SELECT_SEEN = bytes.fromhex('13fc000100ff5bf0')                 # the coordinator: move.b #1,$FF5BF0
EXIT = bytes.fromhex('13fc000000a1518133fc154000ff053e4e714e71423900ff7600')   # 32x_repair_experiment.py's
EXIT_NEW = (bytes.fromhex('423900a15181')        # clr.b $A15181        the 32X bitmap off
            + bytes.fromhex('33fc594000ff053e')  # move.w #$5940,$FF053E VBlank -> the coordinator
            + bytes.fromhex('423900ff5bf0')      # clr.b $FF5BF0        the transfer starts over at select
            + bytes.fromhex('423900ff7600'))     # clr.b $FF7600        the hook's marker (as before)


def arm_code():
    a = Asm(0xFF0000 + ARM)
    a.w(0x13FC, 0x0001); a.l(0xFF5BF0)            # move.b #1,$FF5BF0   (what the coordinator did)
    a.w(0x42B9); a.l(0xFF6C00)                    # clr.l $FF6C00       the renderer: copied and started again
    a.w(0x42B9); a.l(0xFF6C04)                    # clr.l $FF6C04
    a.w(0x4E75)                                   # rts
    return a.build()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('source', type=Path)
    ap.add_argument('output', type=Path)
    a = ap.parse_args()
    if a.output.exists():
        ap.error('choose a new output directory')
    assert len(EXIT_NEW) == len(EXIT)
    cue = copy_disc(str(a.source / 'probe.cue'), str(a.output), 'probe')
    disc = Disc(cue)
    code = arm_code()
    m = disc.read_file('MAIN.BIN')
    assert len(code) <= 0x5BE0 - ARM and m[ARM:ARM + len(code)] == bytes(len(code)), 'MAIN.BIN $5BBA not free'
    assert m.count(SELECT_SEEN) == 1, "the coordinator's select detection not found once"
    disc.patch_file('MAIN.BIN', ARM, code, expect=bytes(len(code)))
    at = m.index(SELECT_SEEN)
    disc.patch_file('MAIN.BIN', at, bytes.fromhex('4EB9') + (0xFF0000 + ARM).to_bytes(4, 'big') + bytes.fromhex('4E71'),
                    expect=SELECT_SEEN)                              # jsr $FF5BBA; nop
    g = disc.read_file('GAME.CO')
    assert g.count(EXIT) == 1, 'the select exit repair not found once'
    disc.patch_file('GAME.CO', g.index(EXIT), EXIT_NEW, expect=EXIT)
    print('Created:', cue)


if __name__ == '__main__':
    main()
