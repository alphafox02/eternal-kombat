#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Make everything tools/build.py reads, from your own discs.

Run once on a new machine (after tools/checkinputs.py says the discs are there).

What it makes (none of it is in the repository: it's your discs' data):
  - extracted/ec_us, extracted/mk_us: the discs' files (tools/lib/extract.py)
  - extracted/mk_moves*: fighter poses, palettes and portraits decoded from
    MK's disc; their anchors and timings from data/mk_meta; fatality sounds
    rendered from MK's samples and CD tracks (data/mk_sound)
  - extracted/mk_stages: the Pit's layers and bottom and Goro's Lair's layers
    decoded from the disc; the fall's sound rendered as the fatality sounds

Reads only the discs and data/: no emulator, no BIOS. A step whose output is
already there (and whose inputs haven't changed) is skipped, so an interrupted
run picks up where it stopped.

    prepare.py [--force] [--list] [--keep-going]
"""
import argparse, os, subprocess, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lib'))   # (the library: tools/lib/)
from inputs import ROOT

E = lambda *p: os.path.join(ROOT, 'extracted', *p)
MK_DIR = {'scorpion': 'mk_moves', 'raiden': 'mk_moves_raiden', 'johnny': 'mk_moves_johnny',
          'subzero': 'mk_moves_subzero', 'liukang': 'mk_moves_liukang', 'kano': 'mk_moves_kano',
          'sonya': 'mk_moves_sonya'}
CAP = ('johnny', 'raiden', 'liukang', 'kano', 'sonya')          # (fatality_sfx.wav in their MK_DIR)


def steps():
    """[(label, command (tools/ script + args), the file that shows it's done)] in order."""
    out = [('extract the discs', ['extract.py'], E('mk_us', 'RJC.PRG'))]
    for who, d in MK_DIR.items():
        out.append((f'{who}: portrait', ['mkportraits_disc.py', '--fighter', who, '--out', E()],
                    E(d, 'portrait.png')))
    out.append(('reptile: portrait', ['mkportraits_disc.py', '--fighter', 'reptile', '--out', E()],
                E('mk_reptile', 'portrait.png')))
    # the fighters' poses: MK draws each frame the recipes name (data/mk_recipes), by number
    out += [("MK's frames, by number", ['mkframes.py', '--recipes'], E('mk_frames', 'ALL')),
            ("the fighters' poses, from the recipes", ['mkfromrecipes.py'],
             E('mk_moves_subzero', 'walk_fwd', 'indexed.npy')),
            ("their anchors, timings and palettes", ['mkcapmeta.py'], E('mk_moves_subzero', 'walk_fwd', 'anchors.json')),
            ("every fighter's MK daze", ['mkdazed.py'], E('mk_moves_sonya', 'dizzy', 'indexed.npy')),
            ('sonya: the burn', ['mkburn.py'], E('mk_moves_sonya', 'fatality_burn', 'indexed.npy')),
            ('scorpion: the skeleton', ['mkfatality.py', 'skeleton'], E('mk_moves', 'fatality_skeleton', 'indexed.npy')),
            # Shang Tsung (the Contest's first boss): his moves from MK's EMP.OBJ frames
            ('shang tsung: his moves', ['mkshangmoves.py'], E('mk_moves_shang', 'walk_fwd', 'glide.json')),
            ('shang tsung: portrait', ['mkportraits_disc.py', '--fighter', 'shang', '--out', E()],
             E('mk_shang', 'portrait.png'))]
    # the fatalities' sounds and the Pit fall's: rendered from MK's samples and CD
    # tracks as MK played them (data/mk_sound; byte for byte the recordings
    # tools/lib/mkfatalsound.py and mkpitsound.py made playing MK)
    out += [("scorpion: fatality sound (a man)", ['mksound_render.py', 'scorpion'], E('mk_moves', 'fatality_sfx_man.wav')),
            ("scorpion: fatality sound (a woman)", ['mksound_render.py', 'scorpion_sonya'],
             E('mk_moves', 'fatality_sfx_woman.wav')),
            ("subzero: spine rip sound", ['mksound_render.py', 'subzero'], E('mk_moves_subzero', 'spinerip_sfx.wav'))]
    out += [(f'{who}: fatality sound', ['mksound_render.py', who], E(MK_DIR[who], 'fatality_sfx.wav')) for who in CAP]
    out += [("MK's Pit: its layers", ['mkpit_disc.py', '--out', E()], E('mk_stages', 'pit', 'plane_a.png')),
            ("MK's Pit: the bottom", ['mkpitbottom.py'], E('mk_stages', 'pit_bottom', 'pit_full.png')),
            ("MK's Pit: the fall's sound", ['mksound_render.py', 'pit'], E('mk_stages', 'pit_bottom', 'fall.wav')),
            ("MK's Goro's Lair: its layers", ['mklair_disc.py', '--out', E()], E('mk_stages', 'lair', 'plane_a.png')),
            ("MK's Courtyard, Palace Gates, Warrior Shrine and Throne Room: their layers",
             ['mkstage_disc.py', '--out', E()], E('mk_stages', 'throne', 'prio.json'))]
    return out


# what each step is made from, beside its own tool: when any of it changes, the
# step is redone (a done-file alone can't tell a step made from older recipes)
FROM_DATA = (os.path.join('data', 'mk_meta'), os.path.join('data', 'mk_recipes'))
INPUTS = {'mkportraits_disc.py': ('tools/lib/mkpitbottom.py',),
          'mkpit_disc.py': ('tools/lib/mkpitbottom.py',),
          'mklair_disc.py': ('tools/lib/mkpitbottom.py', 'tools/lib/mkpit_disc.py'),
          'mkstage_disc.py': ('tools/lib/mkpitbottom.py', 'tools/lib/mkpit_disc.py', 'tools/lib/mklair_disc.py',
                              os.path.join('data', 'mk_stages')),
          'mkframes.py': ('tools/lib/mksch.py', 'tools/lib/mkspine_disc.py') + FROM_DATA,
          'mkfromrecipes.py': ('tools/lib/mkrecipes.py', 'tools/lib/mkframes.py', 'tools/lib/mksch.py',
                               'tools/lib/mkspine_disc.py', 'tools/lib/mkcapmeta.py', 'tools/lib/mkpalettes.py') + FROM_DATA,
          'mkcapmeta.py': ('tools/lib/mkpalettes.py',) + FROM_DATA, 'mkburn.py': FROM_DATA, 'mkfatality.py': FROM_DATA,
          'mkdazed.py': ('tools/lib/mksch.py', 'tools/lib/mkframes.py') + FROM_DATA,
          'mkshangmoves.py': ('tools/lib/mkshang.py', 'tools/lib/mkmoves.py'),
          'mksound_render.py': ('tools/lib/mksfx.py', os.path.join('data', 'mk_sound'))}
STAMPS = E('prepare_stamps.json')


def fingerprint(cmd):
    """A hash of the step's tool, its arguments and INPUTS (files, or every file in a folder)."""
    import hashlib
    h = hashlib.sha1(' '.join(cmd).encode())
    paths = [os.path.join('tools', 'lib', cmd[0])] + list(INPUTS.get(cmd[0], ()))
    for p in paths:
        full = os.path.join(ROOT, p)
        files = [full] if os.path.isfile(full) else sorted(
            os.path.join(d, f) for d, _, fs in os.walk(full) for f in fs)
        for f in files:
            h.update(os.path.relpath(f, ROOT).encode())
            h.update(open(f, 'rb').read())
    return h.hexdigest()


def main():
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument('--force', action='store_true', help='redo every step')
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--keep-going', action='store_true', help='after a failed step, go on (and list the failures)')
    a = ap.parse_args()
    failed = []
    todo = steps()
    t0 = time.time()
    for d in (('build', 'states'), ('extracted',), ('build', 'saves')):
        os.makedirs(os.path.join(ROOT, *d), exist_ok=True)
    stamps = json.load(open(STAMPS)) if os.path.exists(STAMPS) else {}

    def save():
        json.dump(stamps, open(STAMPS + '.tmp', 'w'), indent=0, sort_keys=True)
        os.replace(STAMPS + '.tmp', STAMPS)
    for n, (label, cmd, done) in enumerate(todo, 1):
        fp = fingerprint(cmd)
        if os.path.exists(done) and label not in stamps:
            stamps[label] = fp                              # (made before stamps: taken as it is)
        have = os.path.exists(done) and stamps.get(label) == fp
        if a.list:
            print(f'{n:2d}. {"done" if have else "redo" if os.path.exists(done) else "    "}  {label:38s} '
                  f'tools/{" ".join(cmd)}')
            continue
        if have and not a.force:
            continue
        print(f'[{n}/{len(todo)}] {label} ...', flush=True)
        r = subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', cmd[0])] + cmd[1:], cwd=ROOT)
        if r.returncode or not os.path.exists(done):
            msg = (f'failed: {label} (tools/{" ".join(cmd)}); {os.path.relpath(done, ROOT)} '
                   f'{"missing" if not os.path.exists(done) else "made, but the step exited " + str(r.returncode)}')
            if not a.keep_going:
                sys.exit(msg)
            print(msg, flush=True)
            failed.append(msg)
        else:
            stamps[label] = fp
            save()
    if not a.list:
        save()
    if failed:
        sys.exit('\n'.join(failed))
    if not a.list:
        print(f'ready to build ({(time.time() - t0) / 60:.0f} min): tools/build.py')


if __name__ == '__main__':
    main()
