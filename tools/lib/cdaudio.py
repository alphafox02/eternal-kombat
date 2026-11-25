# SPDX-License-Identifier: MIT
"""MK CD's CD audio on the Eternal Kombat disc, from the player's MK disc.

tools/build.py runs it before the patches: MK's Mortal Monday menu music, FINISH HIM, fatality and
losing cues, the Pit fall's soundtrack and the Pit announcer are appended to EC's last track, and MK's
Pit music replaces the Senator's stage track; patches.fatality_music then points the game at the cues
by disc time."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inputs import ROOT

# MK's fatality music (MK CD track 13) is appended to EC's last track (19,
# the menu music), after a second of silence. (Tried and dropped then: a 20th
# track - fights seemed to freeze, which a cold-booted test later disproved:
# STAGE_TRACKS below - and the pregap of track 2: emulators play pregaps as silence.) The fatality starts
# it by disc time (BIOS MSCPLAYT): patches.fatality_music. (A menu left running can play on into
# them: MENU_SONG_TRACK below.)
MK_FATAL_TRACK = 13
# MK CD's CD-audio cues (measured: docs/notes/2026-11.md): track 9 at FINISH HIM,
# track 13 from the fatality, then track 10 (the losing music) 6.2 s into 13's file
MK_FINISH_TRACK = 9
MK_LOSE_TRACK = 10
FATAL_TO_LOSE = 4.2           # s of track 13 (from INDEX 01: the 2 s pregap is skipped, as MK plays) before track 10
JINGLE_TRACK = 19
JINGLE_GAP = 75               # sectors (1 s) of silence before each part
# ... but 30 s after FINISH HIM's part 0: the CD plays on past a part's end, and a FINISH HIM left
# unfinished ran into part 1, the fatality music with its flame and scream, over EC's fade to the stats
# (as if a fatality had been done; measured 9 s after part 0 began). The stats screen stops the CD
# first (16 s after FINISH HIM in a Contest timed out).
FINISH_TAIL = 30 * 75


# The menus' music (EC track 19, which EC plays with the BIOS's repeat, MSCPLAYR) is followed by MK
# CD's Mortal Monday music (its track 20: MK's intro video plays it from the ARENA logo), then the
# cues above. Repeating, the CD would play on past EC's song into them (left on the title, it played
# random MK announcer lines). The title and main menu hand over to EC's intro video at 5:00,
# inside MK's song; a menu screen with no such timeout (Controller Setup) left ~5:40 still reaches
# the cues (a restart at the song's end needs code in SUB.BIN, which is full: docs/notes/2026-11.md,
# 2026-11-23).
MENU_SONG_TRACK = 20
MENU_SONG_GAP = 75            # sectors (1 s) of silence between EC's song and MK's
MENU_TAIL = 3 * 75            # sectors of silence after MK's song, before the cues


def menu_song(mk_cue):
    """MK's track 20 from INDEX 01 (the 2 s pregap skipped), raw sectors."""
    from disc import parse_cue, RAW
    t = {t.number: t for t in parse_cue(mk_cue)}[MENU_SONG_TRACK]
    return open(t.file, 'rb').read()[150 * RAW:]


def jingle_gap(i):
    """Sectors of silence before mk_jingle part i."""
    return FINISH_TAIL if i == 1 else JINGLE_GAP
FIRE_DELAY = 108 / 59.92 - 0.2   # s: fatality start -> fire on the victim (108 frames), less the CD jump delay (measured 0.2 s)
SFX_GAIN = 150                # MK's 8-bit samples into 16-bit CD audio
# MK's burning sounds (SFX3E.BIN, Scorpion's fatality bank, played together when the fire hits)
BURN = ('SFX3E.BIN', 'BURNUP.SVX')
SCREAM_MAN = ('SFX3E.BIN', 2)       # the unnamed 16 kHz scream after BURNUP
SCREAM_WOMAN = ('SFX1.BIN', 'GIRLHURT.SVX')   # MK has no woman's fatality scream: Sonya's cry


# The Pit's fall (ecstage.pit_fall_code starts it as the loser is launched):
# MK's own soundtrack from the uppercut: track 10, the long falling yell and
# blood (mksound_render.py pit, run by prepare.py). MK uses the same long yell
# for a woman (Sonya, recorded on MK's Pit) as for a man, so one recording
# serves both.
PIT_FALL_WAV = os.path.join(ROOT, 'extracted', 'mk_stages', 'pit_bottom', 'fall.wav')
PIT_FALL_SECONDS = 5.0           # (track 10 and the yell are over by then)
# then MK's announcer for an MK winner (as MK: "KANO WINS" ~7 s after the
# uppercut, "FLAWLESS VICTORY" ~3 s later when he took no damage)
PIT_WINS = (('SFX4F.BIN', 'SCORwins.SVX'), ('SFX4C.BIN', 'RAIDwins.SVX'),
            ('SFX4A.BIN', 'CAGEWINS.SVX'), ('SFX4E.BIN', 'ZEROWINS.SVX'))   # ecstage.PIT_MK_WINNERS' order
PIT_WINS_MORE = (('SFX4D.BIN', 'LUIKWINS.SVX'), ('SFX4B.BIN', 'KANOWINS.SVX'),
                 ('SFX4G.BIN', 'SONYwins.SVX'))   # ecstage.PIT_MK_WINNERS 5-7: parts after the fatalities'
PIT_FLAWLESS = ('SFX4A.BIN', 'FLAWVICT.SVX')
# Sub-Zero's spine rip: MK's fatality music (13 then 10) with the rip's sound
# effects on top as MK mixes them (tools/lib/mkfatalsound.py recorded them with MK's
# music silenced, from track 13's start; prepare.py renders the same with
# mksound_render.py). The recording's level is the sound
# chip's next to CD audio that MK plays at about PIT_MUSIC_GAIN of the file's.
SPINE_SFX_WAV = os.path.join(ROOT, 'extracted', 'mk_moves_subzero', 'spinerip_sfx.wav')
PIT_MUSIC_GAIN = 0.68
JOHNNY_SFX_WAV = os.path.join(ROOT, 'extracted', 'mk_moves_johnny', 'fatality_sfx.wav')   # (mksound_render.py johnny)
SCORP_SFX_MAN = os.path.join(ROOT, 'extracted', 'mk_moves', 'fatality_sfx_man.wav')     # (mksound_render.py scorpion)
SCORP_SFX_WOMAN = os.path.join(ROOT, 'extracted', 'mk_moves', 'fatality_sfx_woman.wav') # (mksound_render.py scorpion_sonya)
RAIDEN_SFX_WAV = os.path.join(ROOT, 'extracted', 'mk_moves_raiden', 'fatality_sfx.wav')   # (mksound_render.py raiden)
LIUKANG_SFX_WAV = os.path.join(ROOT, 'extracted', 'mk_moves_liukang', 'fatality_sfx.wav')   # (mksound_render.py liukang)
SONYA_SFX_WAV = os.path.join(ROOT, 'extracted', 'mk_moves_sonya', 'fatality_sfx.wav')   # (mksound_render.py sonya)
KANO_SFX_WAV = os.path.join(ROOT, 'extracted', 'mk_moves_kano', 'fatality_sfx.wav')   # (mksound_render.py kano)
PIT_FLAWLESS_AT = 1.9            # s (MK: ~3 s; EC moves on to its stats screen ~3 s after the announcer starts, cutting the disc off)


def mk_jingle(mk_cue):
    """The parts appended to the last track, in order:
    0: MK's track 9 from INDEX 01 (started at FINISH HIM, as MK does)
    1: Scorpion's fatality: track 13 (the fatality music), then track 10 (the losing
       music) as MK plays them, with MK's recorded effects (SCORP_SFX_MAN; without it,
       MK's flame and a man's scream mixed in at FIRE_DELAY)
    2: the same for a woman (SCORP_SFX_WOMAN, or Sonya's cry)
    3: the Pit's fall, a man's (PIT_FALL_WAV; silence without it)
    4: the Pit's fall, a woman's
    5-12: MK's announcer for the Pit: "<NAME> WINS" for Scorpion, Raiden,
       Johnny Cage, Sub-Zero, each plain and with "FLAWLESS VICTORY"
    13: Sub-Zero's spine rip: track 13 then 10 with MK's rip sounds (SPINE_SFX_WAV)
    14: Johnny Cage's decapitation: the same with his fatality's sounds (JOHNNY_SFX_WAV)
    15: Raiden's electrocution: the same with his (RAIDEN_SFX_WAV)
    16: Liu Kang's uppercut: the same with his (LIUKANG_SFX_WAV)
    17: Sonya's kiss: the same with hers (SONYA_SFX_WAV)
    18: Kano's heart rip: the same with his (KANO_SFX_WAV)
    19-24: the Pit's announcer for Liu Kang, Kano, Sonya, each plain and flawless
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
    woman = man.copy()                            # MK uses the same long fall yell for Sonya
    def announce(srcs):
        out = []
        for src in srcs:
            for flawless in (False, True):
                v = sfx(src)
                o = np.zeros((int((PIT_FLAWLESS_AT + 2.0 if flawless else len(v) / 44100 + 0.3) * 44100), 2))
                o[:len(v)] += v[:, None]
                if flawless:
                    f = sfx(PIT_FLAWLESS)
                    k = int(PIT_FLAWLESS_AT * 44100)
                    o[k:k + len(f)] += f[:len(o) - k, None]
                out.append(sectors(o))
        return out
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
    def with_sfx(wav):                       # the fatality music with MK's recorded effects (from track 13's start)
        out = music.copy()
        if os.path.exists(wav):
            import wave
            w = wave.open(wav)
            x = np.frombuffer(w.readframes(w.getnframes()), '<i2').reshape(-1, 2).astype(float) / PIT_MUSIC_GAIN
            n = min(len(x), len(out))
            out[:n] += x[:n]
        return sectors(out)
    # Scorpion's: MK's own recording (flame, scream, announcer: tools/lib/mkfatalsound.py scorpion /
    # scorpion_sonya) when there, else MK's samples mixed at FIRE_DELAY
    scorp = [with_sfx(w) if os.path.exists(w) else mix(BURN, s)
             for w, s in ((SCORP_SFX_MAN, SCREAM_MAN), (SCORP_SFX_WOMAN, SCREAM_WOMAN))]
    return [full] + scorp + [sectors(man), sectors(woman)] + wins \
        + [with_sfx(SPINE_SFX_WAV), with_sfx(JOHNNY_SFX_WAV), with_sfx(RAIDEN_SFX_WAV), with_sfx(LIUKANG_SFX_WAV),
           with_sfx(SONYA_SFX_WAV), with_sfx(KANO_SFX_WAV)] + announce(PIT_WINS_MORE)


# The Pit plays MK's music: MK's fights on the Pit (and the Courtyard) play MK
# track 4. The Pit is the Senator's stage mode ($1F, patches.PIT_MODE), whose music
# is EC track 13 (SUB.BIN $ABEC stage ids / $AC12 tracks: $1F -> $0D, no other stage).
# (It was track 17 while the Pit was on Blast's stage; moving the Pit without changing this
# table gave the Pit the Senator's own theme and Blast's stage MK's Pit music.) Both files
# hold their 2 s pregap (INDEX 01 00:02:00), so the file is swapped whole.
STAGE_MUSIC = {13: 4}         # EC track -> MK track


def add_stage_music(cue, mk_cue):
    import shutil
    from disc import parse_cue
    ec = {t.number: t for t in parse_cue(cue)}
    mk = {t.number: t for t in parse_cue(mk_cue)}
    for e, m in STAGE_MUSIC.items():
        os.remove(ec[e].file)
        shutil.copyfile(mk[m].file, ec[e].file)


def add_mk_jingle(cue, mk_cue):
    """Append MK's menu song (menu_song, between silences) and the mk_jingle parts (each after
    jingle_gap's silence) to EC track JINGLE_TRACK's file. Writes a new file: the copied one is a
    hard link to the original disc."""
    from disc import parse_cue, RAW
    t = {t.number: t for t in parse_cue(cue)}[JINGLE_TRACK]
    old = open(t.file, 'rb').read()
    os.remove(t.file)
    with open(t.file, 'wb') as f:
        f.write(old)
        f.write(bytes(MENU_SONG_GAP * RAW) + menu_song(mk_cue) + bytes(MENU_TAIL * RAW))
        for i, part in enumerate(mk_jingle(mk_cue)):
            f.write(bytes(jingle_gap(i) * RAW) + part)
        f.write(bytes(JINGLE_TAIL * RAW))


# After the last part, silence: the CD plays on past a part's end, and track 19 is no longer the
# disc's last (STAGE_TRACKS follow it): a last part left playing would run into MK's stage music.
JINGLE_TAIL = 60 * 75


# MK CD's stage tracks that aren't on EC's disc, as tracks 20-22 (mkstages.MK_TRACK_EC: the Warrior
# Shrine and Goro's Lair play MK track 3, the Palace Gates 6, the Throne Room 7; the Courtyard plays
# 4, the Pit's: STAGE_MUSIC). Each file whole, its 2 s pregap too (INDEX 01 00:02:00, as EC's).
# (A note from before said EC fights froze on a 20-track disc: not so - a cold-booted 20-track disc
# fights through rounds, KOs and the stats as the 19-track one; docs/notes/2026-11.md.)
STAGE_TRACKS = {20: 3, 21: 6, 22: 7}  # our track -> MK's


def add_stage_tracks(cue, mk_cue):
    """Append STAGE_TRACKS to the disc: MK's files hard-linked (they never change) next to the cue."""
    from disc import parse_cue
    mk = {t.number: t for t in parse_cue(mk_cue)}
    ours = parse_cue(cue)
    assert max(t.number for t in ours) == JINGLE_TRACK, 'stage tracks: the disc should end at track 19'
    name = os.path.splitext(os.path.basename(cue))[0]
    lines = []
    for n, m in sorted(STAGE_TRACKS.items()):
        stem = f'{name} (Track {n:02d}).bin'
        dst = os.path.join(os.path.dirname(cue), stem)
        if os.path.exists(dst):
            os.remove(dst)
        try:
            os.link(mk[m].file, dst)
        except OSError:
            import shutil
            shutil.copyfile(mk[m].file, dst)
        lines += [f'FILE "{stem}" BINARY', f'  TRACK {n:02d} AUDIO', '    INDEX 00 00:00:00', '    INDEX 01 00:02:00']
    with open(cue, 'a', newline='\r\n') as o:
        for line in lines:
            o.write(line + '\n')
