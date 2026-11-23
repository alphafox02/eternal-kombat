#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Do the fight's sound banks load whole?

For each MK fighter (player 1) against Shadow: every clip of FIGHT.SND and of both fighters' voice
banks (a .SND's second bank) must be in sound RAM once the fight runs (the driver loads a bank's
clips as its table's entries name them, in order, and stops at a short clip: a silence left
mid-bank by mk-hit-sounds lost FIGHT.SND's last two clips, entries out of order lost Scorpion's
spear screams - the suite plays silently, so neither showed). A clip is found by its first 48
bytes past its leading silence. And no sound table on the disc may name a clip an earlier entry
took: the driver sets the end address (where it keys a channel off) only for the entry that loads
a clip - the other keeps 0 and its channel loops sound RAM from 0 (a hit sound stuck playing over
and over: FIGHT's $3EC and $3EF shared SMACK1). FIGHT.SND's clips must load whole and end below the
players' banks at $3F00 (MALEJUMP's tail went over player 1's first bank - the long clip this check
skips: the versus screens waited on it, a Contest froze).

    soundbankcheck.py [--fighters scorpion,raiden,...]
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd
from inputs import ROOT

RAM = 0x2810D                 # the PCM chip's sound RAM in the core's save state (64 KB)
FIGHT_END = 0x3F00            # the players' banks start here: FIGHT.SND's clips must end below
GRID = {'scorpion': 20, 'raiden': 7, 'subzero': 15, 'sonya': 16, 'liukang': 17, 'kano': 18, 'johnny': 19}


def clips(snd):
    """[(bank slot, clip bytes)] of every PCM chunk (type $20) in a .SND."""
    out, o = [], 0
    while o + 6 <= len(snd):
        ln, t = int.from_bytes(snd[o:o + 4], 'big'), int.from_bytes(snd[o + 4:o + 6], 'big')
        if ln <= 0:
            break
        if t == 0x20:
            slot = int.from_bytes(snd[o + 10:o + 12], 'big')
            p, n = o + 16, int.from_bytes(snd[o + 12:o + 16], 'big')
            while True:
                out.append((slot, snd[p:p + n]))
                p += n
                if p + 4 > o + ln:
                    break
                n = int.from_bytes(snd[p:p + 4], 'big')
                if not n:
                    break
                p += 4
        o += ln
    return out


def shared(snd):
    """['id->clip'] of the sound-table entries (type $1C chunks) naming a clip an earlier entry took."""
    out, o = [], 0
    while o + 6 <= len(snd):
        ln, t = int.from_bytes(snd[o:o + 4], 'big'), int.from_bytes(snd[o + 4:o + 6], 'big')
        if ln <= 0:
            break
        if t == 0x1C:
            seen = set()
            for i in range(int.from_bytes(snd[o + 0xC:o + 0xE], 'big')):
                e = o + int.from_bytes(snd[o + 0xE + 4 * i:o + 0x12 + 4 * i], 'big')
                clip = int.from_bytes(snd[e + 0x18:e + 0x1A], 'big')
                if clip in seen:
                    out.append(f'{int.from_bytes(snd[e:e + 2], "big"):04x}->{clip}')
                seen.add(clip)
        o += ln
    return out


def main():
    import disc, patches
    ap = argparse.ArgumentParser()
    ap.add_argument('--fighters', default=','.join(GRID))
    a = ap.parse_args()
    cue = os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue')
    ec = disc.Disc(cue)
    host = {s.key: s.host for s in patches.MK_SPECS}
    bad = []
    for f in sorted(n for n in ec.files() if n.endswith('.SND')):
        s = shared(ec.read_file(f))
        if s:
            print(f'  {f}: entries sharing a clip (no end address: they loop) {" ".join(s)}')
            bad += s
    print(f'  sound tables: {"no entry shares a clip" if not bad else f"{len(bad)} entries share a clip"}')
    with tempfile.TemporaryDirectory() as tmp:
        for who in a.fighters.split(','):
            st = os.path.join(tmp, f'{who}.state')
            subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--p1', str(GRID[who]),
                            '--p2', '0', '--stage', '11', '--out', st], check=True, capture_output=True)
            c = scd.Core(saves=os.path.join(tmp, 'saves'))
            c.load(cue)
            c.load_state(st)
            c.run(30)
            ram = c.snapshot()[RAM:RAM + 0x10000]
            missing = []
            for f in ('FIGHT.SND', host[who] + '.SND', 'SHA.SND'):
                banks = sorted({slot for slot, _ in clips(ec.read_file(f))}, key=lambda sl: [s for s, _ in clips(ec.read_file(f))].index(sl))
                for k, (slot, clip) in enumerate(clips(ec.read_file(f))):
                    if f != 'FIGHT.SND' and slot == banks[0]:
                        continue                  # (a fighter's first bank, one long clip, loads at other times: EC's own too)
                    if len(clip) <= 64:
                        continue                  # (the silences: nothing to find)
                    q = next((i for i, v in enumerate(clip) if (v & 0x7F) > 6), 0)
                    if ram.find(clip[q:q + 48]) < 0:
                        missing.append(f'{f} slot {slot:#x} clip {k}')
                    elif f == 'FIGHT.SND':        # whole, and below the players' banks
                        at = ram.find(clip)
                        if at < 0 or at + len(clip) > FIGHT_END:
                            missing.append(f'{f} clip {k} ' + ('cut' if at < 0 else f'ends at ${at + len(clip):X}, '
                                                                f'over the banks at ${FIGHT_END:X}'))
            print(f'  {who:9s} ' + ('all clips in sound RAM' if not missing else 'MISSING ' + ', '.join(missing)))
            bad += missing
    print(f'sound banks: {len(bad)} clips missing or shared -> {"FAIL" if bad else "ok"}')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
