#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Measure what MK does with its sound chip and CD drive in each recording mksound_render.py reproduces.

Writes data/mk_sound/NAME.json (tools/lib/mksound_render.py renders from it). Research
only (the JSON files are committed): it plays MK as tools/lib/mkfatalsound.py /
tools/lib/mkpitsound.py record it, on a Genesis Plus GX core built with a log of
the PCM chip and CD-DA (tools/capture/mksound_measure.patch), from fight states made
from a cold boot (tools/capture/mkselectstate.py, mkduelstate.py, mkpitstate.py: as a
fresh prepare.py used to make them; the recordings were made from those).

The core: stable-retro 1.0.1's cores/genesis (the pinned core's source), patched
and built as stable-retro builds it:

    git clone --depth 1 --branch v1.0.1 https://github.com/Farama-Foundation/stable-retro.git
    cd stable-retro/cores/genesis && patch -p1 < .../tools/capture/mksound_measure.patch
    CFLAGS='-w -std=gnu17' LDFLAGS=-w make -f Makefile.libretro fpic=-fPIC
    (its recordings are identical to the pinned core's: checked on all nine)

    EK_CORE=.../genesis_plus_gx_libretro.so mksound_measure.py NAME ... [--states DIR] [--out DIR]

For each NAME it records the effects as mkfatalsound.py / mkpitsound.py do, checks that the
JSON renders those exact bytes (and says whether they equal the WAV under
extracted/, if there is one), and writes the JSON.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import argparse, ctypes, json, shutil, tempfile
import numpy as np

import scd
import mksound_render as R
from inputs import ROOT, require

FATALITIES = ('sonya', 'subzero', 'johnny', 'raiden', 'liukang', 'kano', 'scorpion', 'scorpion_sonya')


class MarkList(list):
    """Core.audio: marks in the log where the capture clears its audio."""
    def __init__(self, lib):
        super().__init__()
        self.lib = lib

    def clear(self):
        self.lib.retro_ek_mark(b'clear')
        super().clear()


def instrumented():
    """Make every scd.Core keep its audio in a MarkList; return the core's library."""
    lib = ctypes.CDLL(scd.find_core())
    if not hasattr(lib, 'retro_ek_log'):
        raise SystemExit('EK_CORE is not the instrumented core (tools/capture/mksound_measure.patch)')
    lib.retro_ek_log.argtypes = [ctypes.c_char_p]
    orig = scd.Core.__init__

    def init(self, *a, **k):
        orig(self, *a, **k)
        if self.audio is not None:
            self.audio = MarkList(self.lib)
    scd.Core.__init__ = init
    return lib


# --- the log -> the JSON --------------------------------------------------------

class Corpus:
    """Every SFX sample as chip bytes, to name RAM contents by."""
    def __init__(self, disc):
        self.data, self.index, seen = bytearray(), [], set()
        for key in sorted(disc.samples, key=lambda k: (k.split(':')[0], int(k.split(':')[1]))):
            c = disc.samples[key]
            if c in seen:
                continue
            seen.add(c)
            self.index.append((len(self.data), len(c), key))
            self.data += c
        self.data = bytes(self.data)

    def where(self, pos):
        for start, n, key in self.index:
            if start <= pos < start + n:
                return key, pos - start, start + n - pos
        raise ValueError(pos)

    def pieces(self, data, minlen=16):
        """data as mksound_render pieces: samples (whole or in part), zero runs, a
        repeated two-byte pattern (MK's silent loop: $80 $FF ...), literal bytes."""
        out, lit = [], bytearray()

        def flush():
            if lit:
                out.append(['hex', bytes(lit).hex()])
                lit.clear()
        a = 0
        while a < len(data):
            z = a
            while z < len(data) and data[z] == 0:
                z += 1
            if z - a >= minlen:
                flush()
                out.append(['zero', z - a])
                a = z
                continue
            if a + 4 <= len(data) and data[a] != data[a + 1]:
                pat, n = data[a:a + 2], 0
                while data[a + 2 * n:a + 2 * n + 2] == pat:
                    n += 1
                if n >= 16:
                    flush()
                    out.append(['repeat', pat.hex(), n])
                    a += 2 * n
                    continue
            best = None
            key = data[a:a + minlen]
            if len(key) == minlen:
                p = self.data.find(key)
                while p >= 0:
                    name, off, left = self.where(p)
                    n = 0
                    while a + n < len(data) and n < left and data[a + n] == self.data[p + n]:
                        n += 1
                    if best is None or n > best[0]:
                        best = (n, name, off)
                    p = self.data.find(key, p + 1)
            if best and best[0] >= minlen:
                flush()
                out.append(['sample', best[1], best[2], best[0]])
                a += best[0]
            else:
                lit.append(data[a])
                a += 1
        flush()
        return out


def from_log(path, corpus, k, length, silent, file, how):
    """The JSON's contents, from the log of one recording: from the last audio reset
    (a savestate restore: the core clears its resampler) before the capture's start."""
    lines = open(path).read().split('\n')
    clear = next(i for i, l in enumerate(lines) if l.startswith('M ') and l.endswith('clear'))
    r = max(i for i in range(clear) if lines[i].startswith('R '))
    t0 = int(lines[max(i for i in range(r) if lines[i].startswith('F '))].split()[3])
    reset_frame, clear_frame = int(lines[r].split()[1]), int(lines[clear].split()[1])
    pcm = ram = None
    events, cds, sizes, run = [], [], [], None
    for l in lines[r + 1:]:
        p = l.split(' ')
        if p[0] == 'R':
            raise SystemExit('the audio is reset again during the capture')
        if p[0] == 'PL':
            v = list(map(int, p[1:6]))
            pcm = dict(out=v[0:2], enabled=v[2], status=v[3], index=v[4],
                       chan=[list(map(int, c.split(','))) for c in p[7:15]])
        elif p[0] == 'PRAM':
            ram = bytes.fromhex(p[1])
        elif p[0] == 'D':
            raise SystemExit('a DMA into PCM RAM: not modelled')
        elif p[0] == 'W':
            t, a, d, bank = int(p[1]) - t0, int(p[2], 16), int(p[3], 16), int(p[4], 16)
            if a >= 0x1000:                          # wave RAM through the 4 KB bank: one upload per run
                at = bank + (a & 0xfff)
                if run and run[2] + len(run[3]) == at:
                    run[3].append(d)
                else:
                    run = ['m', t, at, [d]]
                    events.append(run)
            elif a <= 8:
                events.append(['r', t, a, d])
            else:
                raise SystemExit(f'PCM register {a:#x}')
        elif p[0] in ('C', 'C0'):
            cds.append(p)
        elif p[0] == 'F':
            sizes.append(int(p[2]))
            if int(p[4]):
                raise SystemExit('FM/PSG sound during the capture: not modelled')
    if pcm is None or ram is None:
        raise SystemExit('no PCM state at the reset')
    for e in events:
        if e[0] == 'm':
            e[3] = corpus.pieces(bytes(e[3]))
    if R.frame_sizes(len(sizes)) != sizes:
        raise SystemExit('samples per frame differ from the model')
    runs, vol, expect = [], None, None
    for f, p in enumerate(cds):
        if int(p[1]) - reset_frame != f:
            raise SystemExit('CD log out of step')
        if p[0] == 'C0':
            if runs and runs[-1][2] is None:
                runs[-1][1] += 1
            else:
                runs.append([f, 1, None])
            expect = None
            continue
        idx, n, pos, cur, end = (int(x) for x in p[2:7])
        if n != sizes[f]:
            raise SystemExit('CD samples per frame differ')
        vol = cur if vol is None else vol
        if runs and runs[-1][2] == idx + 1 and expect == (pos, end):
            runs[-1][1] += 1
        else:
            runs.append([f, 1, idx + 1, pos, end])
        expect = (pos + 4 * n, end)
    return dict(file=file, skip=sum(sizes[:clear_frame - reset_frame]) + k, length=length,
                measured=dict(how=how, frames=clear_frame - reset_frame, start=k),
                pcm=pcm, ram=corpus.pieces(ram), events=events,
                cd=dict(silent_tracks=silent, volume=vol if vol is not None else 0x400,
                        prev=[int(cds[0][-2]), int(cds[0][-1])], runs=runs))


def dump(meta):
    """JSON with one event / CD run / RAM piece per line."""
    out = ['{']
    keys = list(meta)
    for n, key in enumerate(keys):
        v = meta[key]
        end = ',' if n < len(keys) - 1 else ''
        if key in ('events', 'ram'):
            out.append(f' "{key}": [')
            out += ['  ' + json.dumps(x, separators=(',', ':')) + (',' if i < len(v) - 1 else '') for i, x in enumerate(v)]
            out.append(' ]' + end)
        elif key == 'cd':
            out.append(' "cd": {')
            out += [f'  "{k2}": {json.dumps(v[k2], separators=(",", ":"))},' for k2 in v if k2 != 'runs']
            out.append('  "runs": [')
            out += ['   ' + json.dumps(x, separators=(',', ':')) + (',' if i < len(v['runs']) - 1 else '')
                    for i, x in enumerate(v['runs'])]
            out.append('  ]')
            out.append(' }' + end)
        else:
            out.append(f' "{key}": {json.dumps(v, separators=(",", ":"))}{end}')
    return '\n'.join(out) + '\n}\n'


# --- the recordings -----------------------------------------------------------------

def measure(name, lib, states, logpath):
    """(the recorded samples, the JSON) of one recording."""
    cue = require('mk_us').cue
    if name == 'pit':
        import mkpitsound
        lib.retro_ek_log(logpath.encode())
        pcm, _ = mkpitsound.record(cue, states)
        lib.retro_ek_log(None)
        return pcm, dict(k=0, length=len(pcm), silent=[], file='extracted/mk_stages/pit_bottom/fall.wav',
                         how='tools/lib/mkpitsound.py')
    import mkfatalsound as m
    from disc import parse_cue, RAW
    t13 = {t.number: t for t in parse_cue(cue)}[13]
    raw = open(t13.file, 'rb').read()[t13.index01 * RAW:(t13.index01 + t13.length) * RAW]
    ref = np.frombuffer(raw, '<i2').reshape(-1, 2).mean(1)[:int(1.5 * 44100)].astype(float)
    k, q = m.onset(m.record(cue, name, states).mean(1), ref)
    if q < 0.5:
        raise SystemExit(f'{name}: track 13 not found in the recording')
    tmp = tempfile.mkdtemp()
    try:
        lib.retro_ek_log(logpath.encode())
        sfx = m.record(m.silent_copy(cue, tmp), name, states)
        lib.retro_ek_log(None)
    finally:
        shutil.rmtree(tmp)
    n = int(m.KEEP * 44100)
    out = np.clip(sfx[k:k + n], -32768, 32767).astype('<i2')
    return out, dict(k=k, length=n, silent=list(m.SILENT), file=os.path.relpath(m.OUT[name], ROOT),
                     how=f'tools/lib/mkfatalsound.py {name}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('names', nargs='+', metavar='NAME', choices=FATALITIES + ('pit',))
    ap.add_argument('--states', default=os.path.join(ROOT, 'build', 'states'),
                    help='the fight states (mk_*_2p.state, mk_pit_raw.state) made from a cold boot')
    ap.add_argument('--out', default=R.DATA)
    ap.add_argument('--keep-log', action='store_true', help='keep the core\'s log beside the JSON')
    a = ap.parse_args()
    lib = instrumented()
    disc = R.Disc()
    corpus = Corpus(disc)
    os.makedirs(a.out, exist_ok=True)
    for name in a.names:
        log = os.path.join(a.out, f'{name}.log')
        pcm, info = measure(name, lib, os.path.abspath(a.states), log)
        meta = from_log(log, corpus, info['k'], info['length'], info['silent'], info['file'], info['how'])
        if not a.keep_log:
            os.remove(log)
        rec = R.wav_bytes(pcm)
        if R.wav_bytes(R.render(json.loads(dump(meta)), disc)) != rec:
            raise SystemExit(f'{name}: the render differs from the recording')
        path = os.path.join(ROOT, info['file'])
        same = os.path.exists(path) and open(path, 'rb').read() == rec
        open(os.path.join(a.out, f'{name}.json'), 'w').write(dump(meta))
        print(f'{name}: renders the recording exactly; {"equal to" if same else "NOT equal to"} '
              f'{info["file"]} -> {os.path.relpath(os.path.join(a.out, name + ".json"), ROOT)}', flush=True)


if __name__ == '__main__':
    main()
