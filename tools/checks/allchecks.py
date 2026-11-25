#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Every check, for every MK fighter, on the current build.

Run after tools/build.py: it starts with the test suite, which boots the new disc and
re-saves build/states/menu.state. In parallel where it can be (--jobs). Among them:

  - the test suite (tools/play.py test --no-build)
  - the finisher blocks (tools/checks/finishercheck.py)
  - each MK fatality vs Shadow, as player 1 and as player 2 - there with the other punch, where his input
    has one (tools/lib/mkfatalitycheck.py) - and in a mirror match won by player 2; quick taps at every
    timing (Scorpion's and Liu Kang's: the two fatality readers)
  - each against the CPU and in a mirror match: no freeze (tools/checks/fightcheck.py)
  - the Pit's fall with each MK winner, an EC winner, a jump kick: the winner stays up (tools/checks/pitcheck.py)
  - the one-player Contest with each: 10 matches, then to the end of the ladder
    (Shang Tsung, the Dark Champion) and his MK ending (tools/checks/contestcheck.py)
  - Shang Tsung against MK's own: glide, skull volley, backing off a jump-in
    (tools/checks/shangcheck.py)
  - Reptile (tools/checks/reptilecheck.py): on the Pit's bottom, his ice blast freezes, his slide knocks down;
    90 s of Kano jumping in at the CPU's Reptile never freezes (tools/checks/soakcheck.py); his versus
    portrait, Sub-Zero's turned green, not Shang's (tools/checks/versuscheck.py)
  - MK's jumps: straight up as long in the air as MK's, forward / back as before (tools/checks/jumpcheck.py)
  - Z blocks: standing and crouching, as MK's Block (tools/checks/blockcheck.py)
  - Sub-Zero's ice blast freezes, a blocked one doesn't (tools/checks/icecheck.py)
  - MK fighters' back + B is the roundhouse and back + A the sweep; the CPU's play unchanged (tools/checks/backkickcheck.py)
  - MK fighters throw with B up close, as MK CD's high kick (tools/checks/kickthrowcheck.py)
  - up close, X and Y are MK CD's close punch and A its knee (tools/checks/closemovecheck.py)
  - MK CD's other five stages as MK shows them: music, feet, camera, scroll bands, background, MK's
    animations (tools/checks/mkstagecheck.py); which stage a fight is on, every case
    (tools/checks/stagepickcheck.py); MK's FIGHT! and FINISH HIM / HER there (tools/checks/mktextcheck.py)
  - Johnny Cage's split punch on down + B, his down + Z a Block (tools/checks/splitpunchcheck.py)
  - the specials that name a punch take either punch, as on MK CD (tools/checks/eitherpunchcheck.py)
  - the spear's sounds: the victim's scream at the hit, GET OVER HERE at the yank - Scorpion's and
    Reptile's (tools/checks/spearsoundcheck.py); Scorpion's spear on a jumping Kano never hangs (tools/checks/airspearcheck.py);
    both spears from 70 px to their full reach pull the victim in and daze him (tools/checks/spearcheck.py)
  - the sound banks: every clip of FIGHT.SND and the MK fighters' voice banks in sound RAM
    (tools/checks/soundbankcheck.py)
  - round ends: knockouts at 8 moments (both victory routines, the knockdown) all reach round 2
    (tools/checks/roundendcheck.py)
  - and the rest of tools/checks/: one check per feature (the title, Kano's headbutt and knife,
    Sonya's specials, the teleports, the daze, the Vendettas on MK fighters, the 32X route, ...)

    allchecks.py [--jobs 4] [--quick] [--resume]     (--quick: no CPU / Pit / Contest runs)
        -> a table; exits 1 if anything failed

Each result is written as it finishes to build/allchecks.progress (JSON lines, keyed by the build:
its data track's SHA-1), so a run cut off (a reboot, a power cut) loses nothing; --resume skips
the checks that already passed on this build.
"""
import argparse, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
from inputs import ROOT

PY = [sys.executable, '-P', '-E']
def T(name):
    """A tool's path: tools/checks/ first, then capture/, dev/, the library (tools/lib/), the commands (tools/)."""
    for sub in ('checks', 'capture', 'dev', 'lib', ''):
        p = os.path.join(ROOT, 'tools', sub, name)
        if os.path.exists(p):
            return p
    raise FileNotFoundError(name)
FIGHTERS = {'scorpion': 20, 'raiden': 7, 'subzero': 15, 'sonya': 16, 'liukang': 17, 'kano': 18, 'johnny': 19}


PROGRESS = os.path.join(ROOT, 'build', 'allchecks.progress')
BUILD = {}
DONE = {}                                # label -> (ok, last) passed on this build (--resume)


def build_key():
    import hashlib, glob
    h = hashlib.sha1()
    with open(sorted(glob.glob(os.path.join(ROOT, 'build', 'Eternal Kombat', '*Track 01*.bin')))[0], 'rb') as f:
        for blk in iter(lambda: f.read(1 << 20), b''):
            h.update(blk)
    return h.hexdigest()


def run(label, cmd, timeout=1500):
    if label in DONE:
        return label, True, DONE[label] + '  (passed earlier on this build)'
    res = _run(label, cmd, timeout)
    import json, threading
    with BUILD.setdefault('lock', threading.Lock()):
        with open(PROGRESS, 'a') as f:
            f.write(json.dumps({'build': BUILD['key'], 'label': res[0], 'ok': res[1], 'last': res[2]}) + '\n')
        print(f'{"ok  " if res[1] else "FAIL"}  {res[0]:28s} {res[2][:110]}', flush=True)
    return res


def _run(label, cmd, timeout=1500):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=ROOT)
        tail = (r.stdout + r.stderr).strip().splitlines()
        verdict = [l for l in tail if '->' in l and 'build/shots/' not in l] or tail
        return label, r.returncode == 0, verdict[-1] if verdict else ''
    except subprocess.TimeoutExpired:
        return label, False, 'timed out'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--quick', action='store_true')
    ap.add_argument('--resume', action='store_true', help='skip checks that already passed on this build')
    a = ap.parse_args()
    import json
    BUILD['key'] = build_key()
    if a.resume and os.path.exists(PROGRESS):
        for line in open(PROGRESS):
            r = json.loads(line)
            if r['build'] == BUILD['key'] and r['ok'] and 'FAIL' not in r['last'] and 'FROZE' not in r['last']:
                DONE[r['label']] = r['last']
        print(f'resuming: {len(DONE)} checks passed earlier on this build', flush=True)
    import time
    started = time.time()
    results = [run('test suite', PY + [T('play.py'), 'test', '--no-build'], 3500),
               run('finisher blocks', PY + [T('finishercheck.py')]),
               run('sound banks load whole', PY + [T('soundbankcheck.py')]),
               run("MK captures not cut by MK's screen", PY + [T('mkunclip.py'), '--check']),
               run('Z blocks (MK Block)', PY + [T('blockcheck.py')]),
               run('ice blast: freezes, not when blocked', PY + [T('icecheck.py')]),
               run('back + B roundhouse, back + A sweep', PY + [T('backkickcheck.py')]),
               run('up close, B throws (MK CD\'s throw)', PY + [T('kickthrowcheck.py')]),
               run("up close, MK CD's close punch and knee", PY + [T('closemovecheck.py')]),
               run("Johnny's split punch: down + B", PY + [T('splitpunchcheck.py')]),
               run('specials with either punch', PY + [T('eitherpunchcheck.py')]),
               run('spear sounds', PY + [T('spearsoundcheck.py')]),
               run('spear on a jumper (no hang)', PY + [T('airspearcheck.py')]),
               run('spear from near to full reach: pulled in, dazed', PY + [T('spearcheck.py')]),
               run('FEETLAND on jump landings', PY + [T('feetcheck.py')]),
               run('MK jump grunts, none on punches (MALEJUMP, GIRLJUMP)', PY + [T('gruntcheck.py')]),
               run('unfinished FINISH HIM: no fatality music after', PY + [T('finishmusiccheck.py')]),
               run('a deciding throw: FINISH HIM', PY + [T('throwfinishcheck.py')]),
               run('no free effect object: no freeze', PY + [T('poolcheck.py')]),
               run('every tool has its line in docs/tools.md', PY + [T('toolsdoccheck.py')]),
               run('every Python file has the MIT licence tag', PY + [T('licensecheck.py')]),
               run('data/mk_meta palettes from the disc (no save state)', PY + [T('mkcapmeta.py'), '--portable']),
               run("the recipes draw every pose the build reads", PY + [T('mkfromrecipes.py'), '--check']),
               run('select, fight and back again, twice (x32check without a 32X)', PY + [T('x32check.py'), '--only', 'no32x']),
               run('MK art decoder', PY + [T('mkframes.py'), '--verify'], 3600)]
    checks = os.path.join(ROOT, 'build', 'states', 'checks')         # (the checks' own states: remade for this build)
    os.makedirs(checks, exist_ok=True)
    for f in os.listdir(checks) if os.path.isdir(checks) else ():
        if f.startswith(('fatal_', 'trident_', 'vendetta_')) and f.endswith('.state'):
            os.remove(os.path.join(checks, f))
    jobs = [('Kano headbutt (P1)', PY + [T('kanoheadcheck.py')]),
            ('Kano headbutt (P2)', PY + [T('kanoheadcheck.py'), '--as-p2']),
            ('Kano knife input (P1)', PY + [T('kanoknifecheck.py')]),
            ('Kano knife input (P2)', PY + [T('kanoknifecheck.py'), '--as-p2']),
            ("Kano's cannonball: toward, down, away, up", PY + [T('kanoballcheck.py')]),
            ('Sonya square wave (P1)', PY + [T('squarewavecheck.py')]),
            ('Sonya square wave (P2)', PY + [T('squarewavecheck.py'), '--as-p2']),
            ('Sonya leg grab (P1)', PY + [T('leggrabcheck.py')]),
            ('Sonya leg grab (P2)', PY + [T('leggrabcheck.py'), '--as-p2']),
            ('Sonya specials from the pad (forward + HP punches)', PY + [T('sonyainputcheck.py')]),
            ("Riptide's bubble on Kano (an even tint)", PY + [T('tintcheck.py')]),
            ("MK sweeps drop an EC fighter in place", PY + [T('sweepcheck.py')]),
            ("Blade's replaced scripts never run (code kept in them)", PY + [T('deadscriptcheck.py')]),
            ("Liu Kang's flying kick as MK's", PY + [T('flykickcheck.py')]),
            ("Reptile's fight starts on the Pit's bottom", PY + [T('pitstartcheck.py')]),
            ('The Pit: a jump kick decides it, the winner stays on the bridge (Dawson on Sub-Zero)',
             PY + [T('pitcheck.py'), '13:15j']),
            ('The Pit: an EC winner uppercuts an MK loser (Blade on Sub-Zero)', PY + [T('pitcheck.py'), '8:15']),
            ("MK's Courtyard, Palace Gates, Warrior Shrine, Throne Room and Lair as MK shows them", PY + [T('mkstagecheck.py')]),
            ('Which stage a fight is on (MK fighters on MK stages; the Duel setting; bosses)', PY + [T('stagepickcheck.py')]),
            ("MK's FIGHT! and FINISH HIM / FINISH HER on MK's stages", PY + [T('mktextcheck.py')]),
            ('The title screen says ETERNAL KOMBAT', PY + [T('titlecheck.py')]),
            ("The title plays EC's song then MK's Mortal Monday music, never the cues", PY + [T('menumusiccheck.py')]),
            ('Shang Tsung', PY + [T('shangcheck.py')]),
            ('Reptile (pit bottom, freeze, slide)', PY + [T('reptilecheck.py')]),
            ('Reptile fight soak (no freeze)', PY + [T('soakcheck.py')]),
            ("Reptile's versus portrait", PY + [T('versuscheck.py')]),
            ("MK's jumps (straight up as long as MK's)", PY + [T('jumpcheck.py')]),
            ('round ends: Kano KOs Kano (round 2)', PY + [T('roundendcheck.py'), '--p2', '18']),
            ('round ends: Kano KOs Sonya (round 2)', PY + [T('roundendcheck.py'), '--p2', '16'])]
    for side in (0, 1):
        for mirror in (False, True):
            jobs.append((f'Johnny shadow kick (P{side + 1}{" mirror" if mirror else ""})',
                         PY + [T('shadowkickcheck.py')] + (['--as-p2'] if side else []) + (['--mirror'] if mirror else [])
                         + (['--verify-art'] if side == 0 and not mirror else [])))
    # EC Vendettas with per-victim poses (their MK slots were empty or a host's: hangs);
    # the build's own switch (--keep-block), to the final statistics
    for name, w, l in (('Trident on Raiden', 4, 7), ('Midknight on Raiden', 5, 7), ('Blade on Sonya', 8, 16)):
        for side in (0, 1):
            jobs.append((f'{name} (P{side + 1})',
                         PY + [T('vendettacheck.py'), str(w), str(l), '--keep-block', '--frames', '1800', '--state',
                               os.path.join(checks, f'vendetta_{w}_{l}_{side}.state')] + (['--as-p2'] if side else [])))
    for who in ('raiden', 'scorpion'):
        art = ['--verify-art'] if who == 'scorpion' else []         # (Scorpion: his frozen double's art)
        jobs.append((f'{who} teleport (P1)', PY + [T('teleportcheck.py'), who] + art))
        jobs.append((f'{who} teleport (P2)', PY + [T('teleportcheck.py'), who, '--as-p2']))
    for side in (0, 1):                  # two Scorpions: the double and the punch are each his own
        jobs.append((f'scorpion teleport (P{side + 1} mirror)',
                     PY + [T('teleportcheck.py'), 'scorpion', '--mirror'] + (['--as-p2'] if side else [])))
    # quick taps (3 frames down, 4 up) at every timing of a 7-frame cycle, for both fatality readers
    # (Scorpion's, and the one the others share): they run every other frame or third, and a tap EC
    # showed for a frame in between was lost at 1 timing in 7
    for who in ('scorpion', 'liukang'):
        for wait in range(24, 31):
            jobs.append((f'{who} fatality, input {wait} frames on', PY + [T('mkfatalitycheck.py'), who,
                                                                        '--wait', str(wait)]))
    for who, grid in FIGHTERS.items():
        jobs.append((f'{who} daze (P1)', PY + [T('dazecheck.py'), who]))
        jobs.append((f'{who} daze (P2)', PY + [T('dazecheck.py'), who, '--as-p2']))
        effects = ['--check-raiden-effects', '--stage', '1B'] if who == 'raiden' else []
        jobs.append((f'{who} fatality (P1)', PY + [T('mkfatalitycheck.py'), who] + effects))
        jobs.append((f'{who} fatality (P2)', PY + [T('mkfatalitycheck.py'), who, '--as-p2', '--other-punch'] + effects))
        jobs.append((f'{who} fatality on Blast', PY + [T('mkfatalitycheck.py'), who, '--p2', '14']))
        jobs.append((f'{who} fatality on Thanatos', PY + [T('mkfatalitycheck.py'), who, '--p2', '15', '--unlock', '16']))
        jobs.append((f'{who} mirror match', PY + [T('fightcheck.py'), 'duel', str(grid)]))
        # (both slots hold his block: player 2's win must still reach his own; stage $11,
        #  not his own - on the Pit the jab can knock the dazed loser off the bridge)
        jobs.append((f'{who} mirror fatality (P2)', PY + [T('mkfatalitycheck.py'), who, '--p2', str(grid),
                                                         '--as-p2', '--stage', '11']))
        if not a.quick:
            jobs.append((f'{who} vs the CPU', PY + [T('fightcheck.py'), 'cpu', str(grid)]))
            jobs.append((f'{who} Pit fall', PY + [T('pitcheck.py'), f'{grid}:0']))
            jobs.append((f'{who} Contest (10 matches)', PY + [T('contestcheck.py'), str(grid), '--matches', '10',
                                                             '--frames', '120000']))
            jobs.append((f'{who} Contest ending', PY + [T('contestcheck.py'), str(grid), '--ending',
                                                       '--frames', '80000']))
            jobs.append((f'{who} Contest ending, the Dark Champion thrown', PY + [T('contestcheck.py'), str(grid),
                                                                              '--ending', '--throws', '--frames', '80000']))
    with ThreadPoolExecutor(a.jobs) as ex:
        results += list(ex.map(lambda j: run(*j), jobs))
    for f in os.listdir(os.path.join(ROOT, 'build', 'shots')):                 # (only what this run made)
        p = os.path.join(ROOT, 'build', 'shots', f)
        if f.startswith(('fatality_', 'pitcheck_')) and f.endswith('.png') and os.path.getmtime(p) >= started:
            os.remove(p)
    bad = 0
    for label, ok, last in results:
        if 'FAIL' in last or 'FROZE' in last or 'failed)' in last and '(0 failed)' not in last:
            ok = False
        bad += not ok
        print(f'{"ok  " if ok else "FAIL"}  {label:28s} {last[:110]}')
    print(f'{len(results) - bad} of {len(results)} passed')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
