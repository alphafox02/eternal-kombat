#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Find an MK disc sample in a recorded fatality WAV (research only).

Scans nearby playback rates by normalised cross-correlation. This identifies
likely samples and timing; it does not reproduce the sound hardware or WAV.

    mksound_probe.py WAV --sample SFX3G.BIN:1 --window 2.3:2.7 [--rate-min 0.98 --rate-max 1.04 --steps 121]
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import argparse
import wave
import numpy as np
from scipy.signal import fftconvolve
from patches import mk_form


def search(audio, hz, sample, rate, start, end, low, high, steps):
    if not 0 <= start < end <= len(audio) / hz or low <= 0 or high < low or steps < 1:
        raise ValueError('invalid search window or rate range')
    sample = np.asarray(sample, np.float64)
    if not len(sample) or not np.any(sample):
        raise ValueError('sample is empty or silent')
    # Include enough of the WAV after the candidate onset window for a full sample.
    first = int(start * hz)
    max_length = int(np.ceil(len(sample) * hz / (rate * low)))
    section = audio[first:min(len(audio), int(end * hz) + max_length)]
    sq = np.r_[0., np.cumsum(section * section)]
    best = None
    for ratio in np.linspace(low, high, steps):
        length = int(len(sample) * hz / (rate * ratio))
        if not 0 < length <= len(section):
            continue
        times = np.arange(length) * rate * ratio / hz
        source = np.interp(times, np.arange(len(sample)), sample)
        source -= source.mean()
        norm = np.sqrt(np.sum(source * source))
        if not norm:
            continue
        corr = fftconvolve(section, source[::-1], mode='valid')
        power = np.sqrt(np.maximum(1., sq[length:] - sq[:-length]))
        scores = np.abs(corr) / (norm * power)
        scores = scores[:min(len(scores), int((end - start) * hz) + 1)]
        i = int(np.argmax(scores))
        result = (float(scores[i]), (first + i) / hz, float(ratio), float(corr[i] / (norm * norm)))
        if best is None or result[0] > best[0]: best = result
    if best is None:
        raise ValueError('no sample fits in search window')
    return best


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('wav')
    ap.add_argument('--sample', required=True, help='SFX filename:index, or filename:sample-name')
    ap.add_argument('--window', required=True, help='earliest:latest possible start in seconds')
    ap.add_argument('--rate-min', type=float, default=0.98)
    ap.add_argument('--rate-max', type=float, default=1.04)
    ap.add_argument('--steps', type=int, default=121)
    a = ap.parse_args()
    bank, index = a.sample.split(':', 1)
    try: index = int(index, 0)
    except ValueError: pass
    start, end = map(float, a.window.split(':', 1))
    rate, body = mk_form(bank, index)
    with wave.open(a.wav, 'rb') as f:
        if f.getsampwidth() != 2 or f.getnchannels() not in (1, 2):
            raise ValueError('expected mono or stereo signed 16-bit WAV')
        hz = f.getframerate()
        audio = np.frombuffer(f.readframes(f.getnframes()), '<i2').reshape(-1, f.getnchannels()).mean(axis=1)
    score, onset, ratio, gain = search(audio, hz, np.frombuffer(body, np.int8), rate,
                                       start, end, a.rate_min, a.rate_max, a.steps)
    print(f'{bank}:{index}, source {rate} Hz; correlation {score:.5f}; '
          f'start {onset:.6f} s; rate {rate * ratio:.3f} Hz; fitted gain {gain:.3f}')
    print('Approximate match only: other channels, chip processing and timing can affect the result.')


if __name__ == '__main__': main()
