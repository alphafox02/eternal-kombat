#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The small files beside each MK capture that the build reads, kept as data/mk_meta/.

(docs/research/reproducibility_2026-11.md) anchors.json (where the feet are), order.txt (pose per frame), timeline.json
(his pose and hers per frame) are numbers from the original capture runs and
are kept in data/mk_meta/; cram.json / cram_p2.json (palettes: from your disc)
are named there by the fight state and palette line they come from. Known
references are read from the disc; unrecognized sources fall back to a state.

    mkcapmeta.py --out      -> data/mk_meta/MK_DIR/ACTION.json, from extracted/ (needs
                               extracted/build_files.txt: tools/dev/buildreads.py)
    mkcapmeta.py            -> those files in extracted/, from data/mk_meta/ and the disc
    mkcapmeta.py --check    -> compare with extracted/, write nothing
    mkcapmeta.py --portable -> every palette in data/mk_meta is read from the disc, none from a save
                               state (a fresh machine has no states and, without the dev
                               requirements, no emulator): fast, in allchecks
"""
import argparse, glob, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inputs import ROOT

DATA = os.path.join(ROOT, 'data', 'mk_meta')
NUMBERS = ('anchors.json', 'order.txt', 'timeline.json')
PALETTES = ('cram.json', 'cram_p2.json')
SETTLE = 120                      # frames run from a fight state before its palettes are read


def state_lines():
    """{palette (16 words): 'STATE:LINE'} over build/states/mk_*.state, the first
    (sorted) state that has it."""
    import mkmoves
    s = mkmoves.Session()
    out = {}
    for st in sorted(glob.glob(os.path.join(ROOT, 'build', 'states', 'mk_*.state'))):
        name = os.path.basename(st)[:-6]
        if name in ('mk_select', 'mk_pit_raw'):
            continue
        s.core.load_state(st, check=False)
        s.core.run(SETTLE)
        v = s.vdp()
        for ln in range(4):
            out.setdefault(tuple(v.cram_raw[16 * ln:16 * ln + 16]), f'{name}:{ln}')
    return out


def palette(src, cache={}):
    """Palette line 'STATE:LINE' (SETTLE frames into the fight state) or
    'REPLAY@T:LINE' (a replay, T frames after BONES.OBJ is first drawn from:
    mkframes.replay_to)."""
    import mkpalettes
    if src in mkpalettes.OFFSETS:
        return mkpalettes.palette(src, os.path.join(ROOT, 'extracted', 'mk_us'))
    import mkmoves
    where, ln = src.split(':')
    if where not in cache:
        s = mkmoves.Session()
        if '@' in where:                                    # (T: after BONES.OBJ is first drawn from)
            import mkframes
            rp, t = where.split('@')
            mkframes.replay_to(s.core, rp, int(t))
        else:
            s.core.load_state(os.path.join(ROOT, 'build', 'states', where + '.state'), check=False)
            s.core.run(SETTLE)
        cache[where] = s.vdp().cram_raw
    ln = int(ln)
    return list(cache[where][16 * ln:16 * ln + 16])


# what the tools that make captures from others read (mkrecipes.DERIVED:
# mkburn.py, mkfatality.py skeleton), beside what the build reads
DERIVED_READS = {'mk_moves_sonya/fatality_mk_victim': ['cram.json', 'anchors.json'],
                 'mk_moves/fatality_victim': ['anchors.json']}


# captures prepare makes whole after this step (their own tool writes these files): not data.
# (--out once wrote Shang's, with palettes only a save state had: a fresh prepare stopped)
PREPARE_MADE = ('mk_moves_shang/',)


def prepare_made(cap):
    """Made by a later prepare step: Shang's moves (mkshangmoves.py), every daze mkdazed.py draws."""
    import mkdazed
    d, action = cap.split('/')
    return cap.startswith(PREPARE_MADE) or (action == 'dizzy' and d in mkdazed.FIGHTERS and d not in mkdazed.SKIP)


def captures():
    """{MK_DIR/ACTION: [file names the build (or a DERIVED_READS tool) reads there]}."""
    out = {k: list(v) for k, v in DERIVED_READS.items()}
    for line in open(os.path.join(ROOT, 'extracted', 'build_files.txt')):
        p = line.strip().split('/')
        if len(p) == 4 and p[1].startswith('mk_moves') and (p[3] in NUMBERS or p[3] in PALETTES) \
                and not prepare_made(f'{p[1]}/{p[2]}'):
            files = out.setdefault(f'{p[1]}/{p[2]}', [])
            if p[3] not in files:
                files.append(p[3])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', action='store_true')
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--portable', action='store_true')
    a = ap.parse_args()
    import mkpalettes
    if a.portable:
        bad = [(os.path.relpath(p, DATA), f, v) for p in sorted(glob.glob(os.path.join(DATA, '*', '*.json')))
               for f, v in json.load(open(p)).items() if f in PALETTES and v not in mkpalettes.OFFSETS]
        for b in bad:
            print('from a save state, not the disc: %s %s = %s' % b)
        print(f'data/mk_meta palettes: {"all from the disc" if not bad else f"{len(bad)} need a save state"}')
        sys.exit(1 if bad else 0)
    if a.out:
        lines = state_lines()
        for cap, files in sorted(captures().items()):
            d = os.path.join(ROOT, 'extracted', cap)
            meta = {}
            for f in files:
                txt = open(os.path.join(d, f)).read()
                if f in PALETTES:
                    pal = tuple(json.loads(txt))
                    src = lines.get(pal)                    # (its STATE:LINE name: mkpalettes reads the known ones from the disc)
                    assert src, f'{cap}/{f}: no fight state has this palette'
                    assert src in mkpalettes.OFFSETS, f'{cap}/{f}: palette {src} only from a save state (mkpalettes.OFFSETS)'
                    meta[f] = src
                else:
                    meta[f] = txt                            # (kept as written: byte for byte)
            os.makedirs(os.path.join(DATA, os.path.dirname(cap)), exist_ok=True)
            json.dump(meta, open(os.path.join(DATA, cap + '.json'), 'w'), indent=0, sort_keys=True)
        print(f'{len(captures())} captures -> {os.path.relpath(DATA, ROOT)}/')
        return
    bad = 0
    for p in sorted(glob.glob(os.path.join(DATA, '*', '*.json'))):
        cap = os.path.relpath(p, DATA)[:-5]
        d = os.path.join(ROOT, 'extracted', cap)
        for f, v in json.load(open(p)).items():
            txt = json.dumps(palette(v)) if f in PALETTES else v
            dst = os.path.join(d, f)
            if a.check:
                if not os.path.exists(dst) or open(dst).read() != txt:
                    print(f'differs: {cap}/{f}')
                    bad += 1
            else:
                os.makedirs(d, exist_ok=True)
                open(dst, 'w').write(txt)
    if a.check:
        print('all the same' if not bad else f'{bad} differ')
        sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
