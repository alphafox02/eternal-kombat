#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""MK CD's recorded sounds rendered from the user's MK disc, without the emulator.

The fatality sounds and the Pit fall that prepare.py used to record by playing
MK (tools/lib/mkfatalsound.py, tools/lib/mkpitsound.py): byte for byte the same
WAVs (--check).

Each recording is described by data/mk_sound/NAME.json, measured once on the
pinned Genesis Plus GX core (tools/capture/mksound_measure.py;
docs/research/mk_sound_research.md), from the moment the recording run last restored a savestate (the core then
clears its resampler, so everything after is known):
  pcm, ram   the PCM chip's registers and its 64 KB wave RAM then (the RAM as
             pieces of the disc's SFX*.BIN samples, zero runs, a few bytes)
  events     every PCM register write ['r', tick, register, value] and sample
             upload ['m', tick, address, pieces] after it, in PCM chip ticks
  cd         per frame, which CD track plays from which byte of its file and
             the fader's target: runs [first frame, frames, track, offset, target]
             ([first frame, frames, None]: none plays); silent_tracks: the ones
             the recording muted (zero-filled files)
  skip, length   the output samples before the WAV starts, and its length
This tool replays them on a model of the core's PCM chip, CD-DA fader and
resampler (the same integer arithmetic), from the disc's samples and tracks.

    mksound_render.py [NAME ...] [--out DIR]   write the WAVs (default: under extracted/)
    mksound_render.py --check [NAME ...]       render and compare with extracted/ (exact or not)
    mksound_render.py --list
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # (tools run with python -P)
import argparse, json, wave
import numpy as np

from inputs import ROOT, require
from disc import parse_cue
from mksfx import banks, parse_bank

DATA = os.path.join(ROOT, 'data', 'mk_sound')
NAMES = ('sonya', 'subzero', 'johnny', 'raiden', 'liukang', 'kano', 'scorpion', 'scorpion_sonya', 'pit')

# Genesis Plus GX (1.7.5, as stable-retro 1.0.1 ships it): NTSC master clock,
# one frame = 262 lines of 3420 cycles; Sega CD clock 50 MHz, the PCM chip makes
# one sample every 1536 of its cycles; CD-DA at 44.1 kHz; output 44.1 kHz.
MCLOCK = 53693175
FRAME_CYCLES = 262 * 3420
SCD_CLOCK = 50000000
PCM_RATIO = 384 * 4
RATE = 44100
TIME_BITS = 52                     # blip_buf: time_bits = pre_shift (32) + 20


def blip_factor(clock_rate, sample_rate=float(RATE)):
    """blip_set_rates: ceil(2^52 * rate / clock), in double precision as the core does it."""
    f = float(1 << TIME_BITS) * sample_rate / clock_rate
    n = int(f)
    return n + 1 if n < f else n


F_FRAME = blip_factor(float(MCLOCK))            # FM/PSG blip: sets the samples per frame
F_PCM = blip_factor(SCD_CLOCK / PCM_RATIO)      # PCM chip ticks -> output samples
# (the CD-DA blip's factor is exactly 2^52: one CD sample per output sample)


def frame_sizes(n):
    """Output samples of each of n frames after an audio reset (blip offset starts at factor/2)."""
    off, out = F_FRAME // 2, []
    for _ in range(n):
        off += FRAME_CYCLES * F_FRAME
        k = off >> TIME_BITS
        out.append(k)
        off -= k << TIME_BITS
    return out


def to_chip(body):
    """MK's 8SVX sample as MK writes it to the PCM wave RAM: sign/magnitude bytes
    ($FF, the loop marker, never used for data: +127 becomes $FE), then $FF $00."""
    b = np.frombuffer(body, np.int8).astype(np.int16)
    out = np.where(b >= 0, 0x80 | b, -b).astype(np.uint8)
    out[out == 0xFF] = 0xFE
    return out.tobytes() + b'\xff\x00'


class Disc:
    """What a render reads from the MK disc: the SFX samples (chip bytes) and the audio tracks."""
    def __init__(self):
        d = require('mk_us')
        try:
            self.samples = {}
            for name, data in banks(d).items():
                for s in parse_bank(name, data):
                    self.samples[f'{name}:{s.index}'] = to_chip(s.body)
            self.cue = d.cue
        finally:
            d.close()
        self.tracks = {t.number: t.file for t in parse_cue(self.cue)}
        self._audio = {}

    def track(self, number):
        if number not in self._audio:
            self._audio[number] = open(self.tracks[number], 'rb').read()
        return self._audio[number]

    def pieces(self, pieces):
        """RAM bytes from their pieces."""
        out = bytearray()
        for p in pieces:
            if p[0] == 'sample':                     # ['sample', 'BANK:INDEX', offset, length]
                src = self.samples[p[1]]
                if p[2] + p[3] > len(src):
                    raise ValueError(f'{p[1]}: piece past the sample end')
                out += src[p[2]:p[2] + p[3]]
            elif p[0] == 'zero':                     # ['zero', length]
                out += bytes(p[1])
            elif p[0] == 'repeat':                   # ['repeat', 'hex', count]
                out += bytes.fromhex(p[1]) * p[2]
            elif p[0] == 'hex':                      # ['hex', 'literal bytes']
                out += bytes.fromhex(p[1])
            else:
                raise ValueError(f'unknown RAM piece {p[0]!r}')
        return bytes(out)


def render_pcm(meta, disc, nticks):
    """Run the PCM chip (core/cd_hw/pcm.c) for nticks ticks from the audio reset;
    return its output changes: (tick, left delta, right delta) arrays."""
    init = meta['pcm']
    ram = bytearray(disc.pieces(meta['ram']))
    if len(ram) != 0x10000:
        raise ValueError('wave RAM image is not 64 KB')
    # channel registers: addr (16.11), st, ls, fd, env, pan
    addr, st, ls, fd, env, pan = (list(x) for x in zip(*init['chan']))
    enabled, status, index = init['enabled'], init['status'], init['index']
    prev_l, prev_r = init['out']
    events = meta['events']
    loads = [disc.pieces(e[3]) if e[0] == 'm' else None for e in events]
    ev = 0
    next_t = events[0][1] if events else nticks
    ticks, dls, drs = [], [], []
    for t in range(nticks):
        while t == next_t:
            e = events[ev]
            if e[0] == 'm':                          # sample upload: ['m', tick, address, pieces]
                data = loads[ev]
                a = e[2]
                if a + len(data) > 0x10000:
                    raise ValueError('upload past the end of wave RAM')
                ram[a:a + len(data)] = data
            else:                                    # register write: ['r', tick, register, value]
                reg, v = e[2], e[3]
                if reg == 0:
                    env[index] = v
                elif reg == 1:
                    pan[index] = v
                elif reg == 2:
                    fd[index] = (fd[index] & 0xff00) | v
                elif reg == 3:
                    fd[index] = (fd[index] & 0x00ff) | (v << 8)
                elif reg == 4:
                    ls[index] = (ls[index] & 0xff00) | v
                elif reg == 5:
                    ls[index] = (ls[index] & 0x00ff) | (v << 8)
                elif reg == 6:
                    st[index] = v << 19
                    if not status & (1 << index):
                        addr[index] = st[index]
                elif reg == 7:
                    if v & 0x40:
                        index = v & 7
                    enabled = v & 0x80               # (the bank select only matters for uploads: in 'm')
                elif reg == 8:
                    status = ~v & 0xff
                    for j in range(8):
                        if v & (1 << j):
                            addr[j] = st[j]
                else:
                    raise ValueError(f'unexpected PCM register {reg}')
            ev += 1
            next_t = events[ev][1] if ev < len(events) else nticks
        l = r = 0
        if enabled:
            for j in range(8):
                if status & (1 << j):
                    a = addr[j]
                    data = ram[(a >> 11) & 0xffff]
                    if data == 0xff:
                        addr[j] = ls[j] << 11
                        data = ram[ls[j]]
                    else:
                        addr[j] = (a + fd[j]) & 0xffffffff
                    if data != 0xff:
                        v = data & 0x7f if data & 0x80 else -(data & 0x7f)
                        p = pan[j]
                        l += (v * env[j] * (p & 0x0f)) >> 5
                        r += (v * env[j] * (p >> 4)) >> 5
            l = -32768 if l < -32768 else 32767 if l > 32767 else l
            r = -32768 if r < -32768 else 32767 if r > 32767 else r
        if l != prev_l or r != prev_r:
            ticks.append(t)
            dls.append(l - prev_l)
            drs.append(r - prev_r)
            prev_l, prev_r = l, r
    return np.array(ticks, np.int64), np.array(dls, np.int64), np.array(drs, np.int64)


def pcm_positions(ticks):
    """blip_add_delta_fast for the PCM blip: output sample and 15-bit fraction of each tick
    ((tick * factor + factor / 2) >> 32, without overflowing 64 bits)."""
    hi, lo = F_PCM >> 32, F_PCM & 0xffffffff
    fixed = ticks * hi + ((ticks * lo + F_PCM // 2) >> 32)
    return fixed >> 20, (fixed >> 5) & 0x7fff


def cd_samples(meta, disc, sizes):
    """CD-DA (core/cd_hw/cdd.c cdd_read_audio) per frame: the faded 16-bit stereo output
    for each output sample, or None for frames where no track plays."""
    vol = meta['cd']['volume']
    silent = set(meta['cd']['silent_tracks'])
    out = []
    frame = 0
    for run in meta['cd']['runs']:
        if frame >= len(sizes):
            break
        if run[0] != frame:
            raise ValueError('CD runs are not contiguous')
        count = min(run[1], len(sizes) - frame)
        if run[2] is None:                           # [first frame, frames, None]: nothing plays
            out += [None] * count
            frame += count
            continue
        _, _, track, pos, end_vol = run              # [first frame, frames, track, file offset, fader target]
        for f in range(frame, frame + count):
            n = sizes[f]
            if track in silent:
                pcm = np.zeros((n, 2), np.int64)
            else:
                raw = disc.track(track)[pos:pos + 4 * n]
                if len(raw) != 4 * n:
                    raise ValueError(f'track {track}: read past its end')
                pcm = np.frombuffer(raw, '<i2').reshape(-1, 2).astype(np.int64)
            # the fader moves one step per sample towards its target; at 0 (and a target
            # of 0) the core stops this frame's samples (the output stays 0)
            vols = np.empty(n, np.int64)
            v = vol
            stop = n
            for i in range(n):
                vols[i] = v
                if v < end_vol:
                    v += 1
                elif v > end_vol:
                    v -= 1
                elif not v:
                    stop = i + 1
                    break
            vol = v
            vols = vols[:stop]
            mul = np.where(vols & 0x7fc, vols & 0x7fc, vols & 0x03)
            prod = pcm[:stop] * mul[:, None]
            lr = np.where(prod < 0, -((-prod) // 1024), prod // 1024)      # C division (towards 0)
            out.append(lr)
            pos += 4 * n
        frame += count
    return out


def render(meta, disc):
    """The recording's 16-bit stereo samples."""
    skip, length = meta['skip'], meta['length']
    total = skip + length
    sizes, off = [], F_FRAME // 2                    # (frame_sizes, as far as needed)
    while sum(sizes) < total:
        off += FRAME_CYCLES * F_FRAME
        sizes.append(off >> TIME_BITS)
        off -= sizes[-1] << TIME_BITS
    nframes = len(sizes)
    nsamples = sum(sizes)
    buf = np.zeros((nsamples + 32, 2), np.int64)
    # PCM: enough ticks for every output sample
    nticks = 0
    while True:
        nticks += 1 << 14
        pos, _ = pcm_positions(np.array([nticks], np.int64))
        if pos[0] > nsamples + 8:
            break
    t, dl, dr = render_pcm(meta, disc, nticks)
    pos, frac = pcm_positions(t)
    keep = pos + 8 < len(buf)
    pos, frac, dl, dr = pos[keep], frac[keep], dl[keep], dr[keep]
    for k, d in ((0, dl), (1, dr)):
        np.add.at(buf[:, k], pos + 7, d * 32768 - d * frac)
        np.add.at(buf[:, k], pos + 8, d * frac)
    # CD-DA: one sample per output sample, fraction exactly 1/2
    cd = cd_samples(meta, disc, sizes)
    if len(cd) < nframes:
        raise ValueError('CD runs end before the recording')
    prev = np.array(meta['cd']['prev'], np.int64)
    start = 0
    for f in range(nframes):
        lr = cd[f]
        if lr is None:
            if prev.any():
                buf[start + 7] += -prev * 16384
                buf[start + 8] += -prev * 16384
                prev = np.zeros(2, np.int64)
        elif len(lr):
            d = np.diff(np.vstack([prev[None, :], lr]), axis=0)
            buf[start + 7:start + 7 + len(lr)] += d * 16384
            buf[start + 8:start + 8 + len(lr)] += d * 16384
            prev = lr[-1].copy()
        start += sizes[f]
    # blip_mix_samples: one integrator for the three buffers, then the high-pass
    out = np.empty((total, 2), np.int16)
    for k in (0, 1):
        col = buf[:total, k].tolist()
        res = [0] * total
        s = 0
        for i in range(total):
            v = s >> 15
            s += col[i]
            v = -32768 if v < -32768 else 32767 if v > 32767 else v
            res[i] = v
            s -= v << 6
        out[:, k] = res
    return out[skip:]


def wav_bytes(pcm):
    import io
    b = io.BytesIO()
    w = wave.open(b, 'wb')
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(RATE)
    w.writeframes(pcm.astype('<i2').tobytes())
    w.close()
    return b.getvalue()


def load(name):
    return json.load(open(os.path.join(DATA, f'{name}.json')))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('names', nargs='*', metavar='NAME', help=f'any of {", ".join(NAMES)} (default: all)')
    ap.add_argument('--out', help='write under this folder instead of the repository (same relative paths)')
    ap.add_argument('--check', action='store_true', help='render and compare with the files under extracted/')
    ap.add_argument('--list', action='store_true')
    a = ap.parse_args()
    names = a.names or [n for n in NAMES if os.path.exists(os.path.join(DATA, f'{n}.json'))]
    for n in names:
        if n not in NAMES:
            raise SystemExit(f'unknown recording {n!r}: one of {", ".join(NAMES)}')
    if a.list:
        for n in names:
            print(f'{n:15s} -> {load(n)["file"]}')
        return
    disc = Disc()
    bad = []
    for n in names:
        meta = load(n)
        data = wav_bytes(render(meta, disc))
        if a.check:
            path = os.path.join(ROOT, meta['file'])
            if not os.path.exists(path):
                print(f'{n:15s} no {meta["file"]} to compare with')
                bad.append(n)
                continue
            ref = open(path, 'rb').read()
            if ref == data:
                print(f'{n:15s} exact ({len(data)} bytes) {meta["file"]}')
                continue
            bad.append(n)
            x = np.frombuffer(data[44:], '<i2').reshape(-1, 2).astype(int)
            y = np.frombuffer(ref[44:], '<i2').reshape(-1, 2).astype(int)
            m = min(len(x), len(y))
            diff = np.any(x[:m] != y[:m], axis=1)
            print(f'{n:15s} DIFFERENT: {len(data)} vs {len(ref)} bytes, header '
                  f'{"same" if data[:44] == ref[:44] else "differs"}, {int(diff.sum())} of {m} frames differ'
                  + (f' (first {int(np.argmax(diff))}), max |difference| {int(np.abs(x[:m] - y[:m]).max())}'
                     if diff.any() else ''))
        else:
            path = os.path.join(a.out or ROOT, meta['file'])
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, 'wb').write(data)
            print(f'{n:15s} -> {path}')
    if a.check and bad:
        sys.exit(f'{len(bad)} of {len(names)} not exact: {", ".join(bad)}')


if __name__ == '__main__':
    main()
