#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""MK's announcer says FIGHT! on MK's stages (mkstages.fight_voice_bank: a sound bank in the stage's code
the text director - the Pit's watch, ecstage.pit_fight_voice - hands EC's driver after the fighters' banks
are in).

For each of the six stages, a duel (Scorpion vs Shadow; Sub-Zero vs Dawson, the biggest bank, on the
Throne Room): once the round runs, FIGHT.SVX is whole in sound RAM, and every
clip of FIGHT.SND and of both fighters' voice banks is still whole (nothing was lowered or lost for it).
On the Courtyard and the Pit, round 2's FIGHT! is heard: the sound with the director's play call and without it
differ from the fight's start, and the difference is MK's FIGHT.SVX (correlation over 0.8).

    fightvoicecheck.py [--disc CUE]
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import scd, disc, mkstages, patches
from inputs import ROOT
from soundbankcheck import clips, RAM

P1, P2 = 0x2E188, 0x2E330
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big', signed=True)
DUELS = [('courtyard', 20, 0), ('gates', 20, 0), ('shrine', 20, 0), ('throne', 15, 13), ('lair', 20, 0), ('pit', 20, 0)]
HEARD = ('courtyard', 'pit')
CORR = 0.8


def voice_clip():
    bank, _, _ = mkstages.fight_voice_bank(0)
    return bank[0x14 + 0x1A + 16:]


def banks_whole(ec, ram, hosts):
    """[clip names missing]: FIGHT.SND's and each host's voice bank (its bigger PCM chunk)."""
    out = []
    for f in ['FIGHT.SND'] + [h + '.SND' for h in hosts]:
        cl = clips(ec.read_file(f))
        size = {}
        for slot, b in cl:
            size[slot] = size.get(slot, 0) + len(b)
        voice = max(size, key=size.get)
        out += [f'{f} clip {k}' for k, (slot, b) in enumerate(cl)
                if slot == voice and len(b) >= 64 and ram.find(b[:-1]) < 0]
    return out


def heard(cue, st):
    """Round 2's FIGHT! with and without the play call: (frame of the voice, correlation)."""
    call = bytes.fromhex('303c%04x4eb900006d58' % mkstages.FIGHT_VOICE_ID)

    def run(mute):
        c = scd.Core(audio=True)
        c.load(cue)
        c.load_state(st)
        c.run(30)
        if mute:
            r = c.prg_ram()
            i = r.find(call, 0x34000, 0x37000)
            assert i > 0, 'no play call in the stage code'
            c.poke_prg(i, bytes.fromhex('4e71') * 5)
        c.poke_prg(P2 + 0x76, (3).to_bytes(2, 'big'))       # round 1 lost: a jab on 3 health
        for _ in range(400):
            r = c.prg_ram()
            if abs(W(r, P2 + 0x4E) - W(r, P1 + 0x4E)) < 40:
                break
            c.buttons[0] = {'right'}
            c.run(1)
        c.buttons[0] = set()
        c.run(20)
        c.buttons[0] = {'x'}
        c.run(4)
        c.buttons[0] = set()
        c.audio.clear()
        flag = []
        for _ in range(1400):
            c.run(1)
            flag.append(c.prg_ram()[mkstages.FIGHT_FLAG] & 0x40)
        return np.frombuffer(b''.join(c.audio), '<i2').reshape(-1, 2).astype(float).mean(1), flag
    a, flag = run(False)
    b, _ = run(True)
    n = min(len(a), len(b))
    spf = n / 1400
    rises = [f for f in range(1, len(flag)) if flag[f] and not flag[f - 1]]
    if len(rises) < 2:
        return None, 0.0
    f0 = rises[-1]
    seg = (a[:n] - b[:n])[int(f0 * spf):int((f0 + 60) * spf)]
    rate, body = patches.mk_sample('FIGHT.SVX')
    src = np.frombuffer(body, np.int8).astype(float)
    x = np.interp(np.arange(0, len(src) / rate, 1 / (spf * 60)), np.arange(len(src)) / rate, src)
    if len(seg) < len(x):
        return None, 0.0
    k = int(np.argmax(np.abs(np.correlate(seg, x, 'valid'))))
    part = seg[k:k + len(x)]
    return f0 + k / spf, float(np.dot(part, x) / (np.linalg.norm(part) * np.linalg.norm(x) + 1e-9))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    a = ap.parse_args()
    ec = disc.Disc(a.disc)
    grid_host = {20: 'SEN', 15: 'DOG', 0: 'SHA', 13: 'DAW'}
    clip = voice_clip()
    bad = []
    with tempfile.TemporaryDirectory(prefix='ek-fightvoice-') as tmp:
        for key, p1, p2 in DUELS:
            st = os.path.join(tmp, f'{key}.state')
            subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', a.disc,
                            '--p1', str(p1), '--p2', str(p2), '--mk-stage', key, '--out', st], check=True, capture_output=True)
            c = scd.Core(saves=os.path.join(tmp, 'saves'))
            c.load(a.disc)
            c.load_state(st)
            c.run(120)
            ram = bytes(c.snapshot()[RAM:RAM + 0x10000])
            at = ram.find(clip)
            lost = banks_whole(ec, ram, [grid_host[p1], grid_host[p2]])
            msg = f'{key}: FIGHT.SVX ' + (f'at ${at:04X}' if at >= 0 else 'NOT in sound RAM') + \
                (f'; missing {lost}' if lost else '; the banks whole')
            if key in HEARD:
                frame, corr = heard(a.disc, st)
                msg += f'; heard at round 2\'s FIGHT! (frame {frame:.0f}), correlation {corr:.2f}'
                if corr < CORR:
                    bad.append(f'{key}: FIGHT! not heard (correlation {corr:.2f})')
            print(msg, flush=True)
            if at < 0:
                bad.append(f'{key}: FIGHT.SVX not loaded')
            if lost:
                bad.append(f'{key}: {lost}')
    print('FIGHT! voice:', 'FAILED (' + '; '.join(bad) + ')' if bad else 'ok')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
