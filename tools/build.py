#!/usr/bin/env python3
"""Build the Eternal Kombat disc from your own Eternal Champions and MK discs.

    python3 tools/build.py                 # -> build/Eternal Kombat/Eternal Kombat.cue
    python3 tools/build.py --skip title-text
    python3 tools/build.py --list

The build always starts from a fresh copy of the original EC disc, then
applies tools/patches.py in order. Same inputs, same output, byte for byte.
"""
import argparse, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from disc import Disc, copy_disc
from inputs import ROOT, scan
from patches import PATCHES

NAME = 'Eternal Kombat'
OUT = os.path.join(ROOT, 'build', NAME)
# MK's fatality music (MK CD track 13) is appended to EC's last track (19,
# the menu music), after a second of silence. Tried and dropped: a 20th
# track (EC fights freeze with 20 tracks; a longer disc is fine) and the
# pregap of track 2 (emulators play pregaps as silence). The fatality starts
# it by disc time (BIOS MSCPLAYT): patches.fatality_music. Side effect: a
# menu left running for its full 110 s loop plays the jingle once.
MK_FATAL_TRACK = 13
# MK CD's CD-audio cues (measured: docs/re_notes.md): track 9 at FINISH HIM,
# track 13 from the fatality, then track 10 (the losing music) 6.2 s into 13's file
MK_FINISH_TRACK = 9
MK_LOSE_TRACK = 10
FATAL_TO_LOSE = 4.2           # s of track 13 (from INDEX 01: the 2 s pregap is skipped, as MK plays) before track 10
JINGLE_TRACK = 19
JINGLE_GAP = 75               # sectors (1 s) of silence before each part
FIRE_DELAY = 108 / 59.92 - 0.2   # s: fatality start -> fire on the victim (108 frames), less the CD jump delay (measured 0.2 s)
SFX_GAIN = 150                # MK's 8-bit samples into 16-bit CD audio
# MK's burning sounds (SFX3E.BIN, Scorpion's fatality bank, played together when the fire hits)
BURN = ('SFX3E.BIN', 'BURNUP.SVX')
SCREAM_MAN = ('SFX3E.BIN', 2)       # the unnamed 16 kHz scream after BURNUP
SCREAM_WOMAN = ('SFX1.BIN', 'GIRLHURT.SVX')   # MK has no woman's fatality scream: Sonya's cry


# The Pit's fall (ecstage.pit_fall_code starts it as the loser is launched):
# MK's own soundtrack from the uppercut - CD track 10 with the falling man's
# yell and the blood splatter on top - recorded by tools/mkpitsound.py. For a
# woman: track 10 from the same point with MK's smack, Sonya's cry and the
# splatter mixed in at the man's yell's times (MK CD has no other woman's yell).
PIT_FALL_WAV = os.path.join(ROOT, 'extracted', 'mk_stages', 'pit_bottom', 'fall.wav')
PIT_T10_AT = 0.68             # s after the uppercut that MK's track 10 starts (INDEX 01; measured in fall.wav)
PIT_FALL_SFX = ((('SFX1.BIN', 'SMACK1.SVX'), 0.0), (('SFX1.BIN', 'GIRLHURT.SVX'), 0.6),
                (('SFX1.BIN', 'BLOOD.SVX'), 4.5))
PIT_FALL_SECONDS = 5.0           # (track 10 and the yell are over by then)
# then MK's announcer for an MK winner (as MK: "KANO WINS" ~7 s after the
# uppercut, "FLAWLESS VICTORY" ~3 s later when he took no damage)
PIT_WINS = (('SFX4F.BIN', 'SCORwins.SVX'), ('SFX4C.BIN', 'RAIDwins.SVX'),
            ('SFX4A.BIN', 'CAGEWINS.SVX'), ('SFX4E.BIN', 'ZEROWINS.SVX'))   # ecstage.PIT_MK_WINNERS' order
PIT_FLAWLESS = ('SFX4A.BIN', 'FLAWVICT.SVX')
PIT_FLAWLESS_AT = 1.9            # s (MK: ~3 s; EC moves on to its stats screen ~3 s after the announcer starts, cutting the disc off)


def mk_jingle(mk_cue):
    """The parts appended to the last track, in order:
    0: MK's track 9 from INDEX 01 (started at FINISH HIM, as MK does)
    1: track 13 (the fatality music), then track 10 (the losing music) as MK
       plays them, with MK's flame and a man's scream mixed in at FIRE_DELAY
    2: the same with Sonya's cry (for a woman)
    3: the Pit's fall, a man's (tools/mkpitsound.py's recording; silence without it)
    4: the Pit's fall, a woman's
    5-12: MK's announcer for the Pit: "<NAME> WINS" for Scorpion, Raiden,
       Johnny Cage, Sub-Zero, each plain and with "FLAWLESS VICTORY"
    Each is a whole number of CD sectors."""
    import numpy as np
    from disc import parse_cue, RAW
    from patches import mk_form
    tracks = {t.number: t for t in parse_cue(mk_cue)}

    def audio(n):
        t = tracks[n]
        raw = open(t.file, 'rb').read()
        return raw, np.frombuffer(raw[t.index01 * RAW:(t.index01 + t.length) * RAW], '<i2').reshape(-1, 2).astype(float)
    fin = tracks[MK_FINISH_TRACK]
    full = audio(MK_FINISH_TRACK)[0][fin.index01 * RAW:(fin.index01 + fin.length) * RAW]   # heard at once, as MK's
    fatal = audio(MK_FATAL_TRACK)[1]
    lose = audio(MK_LOSE_TRACK)[1]
    music = np.concatenate([fatal[:int(FATAL_TO_LOSE * 44100)], lose])

    def sfx(src):
        rate, body = mk_form(*src)
        x = np.frombuffer(body, np.int8).astype(float)
        return np.interp(np.arange(int(len(x) * 44100 / rate)) * rate / 44100, np.arange(len(x)), x) * SFX_GAIN

    def mix(*srcs):
        out = music.copy()
        at = int(FIRE_DELAY * 44100)
        for src in srcs:
            y = sfx(src)
            n = min(len(y), len(out) - at)
            out[at:at + n] += y[:n, None]
        pcm = np.clip(out, -32768, 32767).astype('<i2').tobytes()
        return pcm + bytes(-len(pcm) % RAW)
    def sectors(x):
        pcm = np.clip(x, -32768, 32767).astype('<i2').tobytes()
        return pcm + bytes(-len(pcm) % RAW)
    n = int(PIT_FALL_SECONDS * 44100)
    man = np.zeros((n, 2))
    if os.path.exists(PIT_FALL_WAV):
        import wave
        w = wave.open(PIT_FALL_WAV)
        x = np.frombuffer(w.readframes(w.getnframes()), '<i2').reshape(-1, 2).astype(float)[:n]
        man[:len(x)] = x
    t10 = lose
    woman = np.zeros((n, 2))
    k0 = int(PIT_T10_AT * 44100)
    lead = t10[:n - k0]
    woman[k0:k0 + len(lead)] = lead * 0.68        # the gain MK's track 10 has in the recording
    for src, at in PIT_FALL_SFX:
        y = sfx(src)
        k = int(at * 44100)
        m = min(len(y), n - k)
        woman[k:k + m] += y[:m, None]
    wins = []
    for src in PIT_WINS:
        for flawless in (False, True):
            v = sfx(src)
            out = np.zeros((int((PIT_FLAWLESS_AT + 2.0 if flawless else len(v) / 44100 + 0.3) * 44100), 2))
            out[:len(v)] += v[:, None]
            if flawless:
                f = sfx(PIT_FLAWLESS)
                k = int(PIT_FLAWLESS_AT * 44100)
                out[k:k + len(f)] += f[:len(out) - k, None]
            wins.append(sectors(out))
    return [full, mix(BURN, SCREAM_MAN), mix(BURN, SCREAM_WOMAN), sectors(man), sectors(woman)] + wins


# The Pit (patches.pit_stage, on Blast's stage) plays MK's music: EC track 17
# is the music of Blast's stage alone (matched by audio in a fight there);
# MK's fights on the Pit (and the Courtyard) play MK track 4. Both files hold
# their 2 s pregap (INDEX 01 00:02:00), so the file is swapped whole.
STAGE_MUSIC = {17: 4}         # EC track -> MK track


def add_stage_music(cue, mk_cue):
    import shutil
    from disc import parse_cue
    ec = {t.number: t for t in parse_cue(cue)}
    mk = {t.number: t for t in parse_cue(mk_cue)}
    for e, m in STAGE_MUSIC.items():
        os.remove(ec[e].file)
        shutil.copyfile(mk[m].file, ec[e].file)


def add_mk_jingle(cue, mk_cue):
    """Append the mk_jingle parts (each after JINGLE_GAP of silence) to EC track
    JINGLE_TRACK's file. Writes a new file: the copied one is a hard link to
    the original disc."""
    from disc import parse_cue, RAW
    t = {t.number: t for t in parse_cue(cue)}[JINGLE_TRACK]
    old = open(t.file, 'rb').read()
    os.remove(t.file)
    with open(t.file, 'wb') as f:
        f.write(old)
        for part in mk_jingle(mk_cue):
            f.write(bytes(JINGLE_GAP * RAW) + part)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--skip', action='append', default=[], help='patch name to leave out (repeatable)')
    ap.add_argument('--list', action='store_true', help='list patches and exit')
    ap.add_argument('--out', default=OUT)
    a = ap.parse_args()

    if a.list:
        for name, doc, _ in PATCHES:
            print(f'  {name:16s} {doc}')
        return
    unknown = set(a.skip) - {n for n, _, _ in PATCHES}
    if unknown:
        raise SystemExit(f'unknown patch(es): {", ".join(sorted(unknown))}; see --list')

    t0 = time.time()
    found, _, _ = scan()
    if 'ec_us' not in found:
        raise SystemExit('Eternal Champions CD not found under roms/. Run: python3 tools/checkinputs.py')
    src = found['ec_us']
    print(f'engine : {os.path.relpath(src.cue, ROOT)}')
    cue = copy_disc(src.cue, a.out, NAME)
    if 'mk_us' in found:
        add_mk_jingle(cue, found['mk_us'].cue)
        add_stage_music(cue, found['mk_us'].cue)
    ec = Disc(cue)
    for name, doc, fn in PATCHES:
        if name in a.skip:
            print(f'  skip  {name}')
            continue
        fn(ec, found)
        print(f'  ok    {name:16s} {doc}')
    sha = ec.data_sha1()
    ec.close()
    print(f'output : {os.path.relpath(cue, ROOT)}')
    print(f'data track SHA-1 {sha}  ({time.time() - t0:.1f}s)')


if __name__ == '__main__':
    main()
