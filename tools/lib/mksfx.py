#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read MK Sega CD's 8SVX sound samples directly from its disc.

    mksfx.py list [BANK]                   list sample names, rates and lengths
    mksfx.py extract BANK:INDEX OUT.wav    write one unmixed sample as 16-bit PCM (or BANK:NAME)
    mksfx.py --check [EXTRACTED_MK_US]     compare disc sound banks with extracted/

The single-sample WAV uses the rate in the 8SVX header. It is not a rendering
of the Sega CD sound chip, and does not replace the mixed fatality recordings.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # (tools run with python -P)
import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
import wave

from inputs import ROOT, require


@dataclass(frozen=True)
class Sample:
    bank: str
    index: int
    name: str
    rate: int
    body: bytes


def parse_bank(bank, data):
    """Yield the complete uncompressed 8SVX FORM records in an MK bank."""
    pos = 0
    index = 0
    while True:
        pos = data.find(b'FORM', pos)
        if pos < 0:
            return
        if pos + 12 > len(data):
            raise ValueError(f'{bank}: truncated FORM header at {pos:#x}')
        length = int.from_bytes(data[pos + 4:pos + 8], 'big')
        end = pos + 8 + length
        if end > len(data) or length < 4 or data[pos + 8:pos + 12] != b'8SVX':
            raise ValueError(f'{bank}: invalid 8SVX FORM at {pos:#x}')
        chunks = {}
        cursor = pos + 12
        while cursor < end:
            if cursor + 8 > end:
                raise ValueError(f'{bank}:{index}: truncated chunk header')
            kind = data[cursor:cursor + 4]
            size = int.from_bytes(data[cursor + 4:cursor + 8], 'big')
            stop = cursor + 8 + size
            if stop > end:
                raise ValueError(f'{bank}:{index}: truncated {kind!r} chunk')
            chunks[kind] = data[cursor + 8:stop]
            cursor = stop + (size & 1)
        header = chunks.get(b'VHDR', b'')
        body = chunks.get(b'BODY')
        if len(header) < 20 or body is None:
            raise ValueError(f'{bank}:{index}: missing VHDR or BODY')
        rate = int.from_bytes(header[12:14], 'big')
        if not rate or header[15] != 0:
            raise ValueError(f'{bank}:{index}: unsupported rate or compression')
        name = chunks.get(b'NAME', b'').split(b'\0', 1)[0].decode('latin-1')
        yield Sample(bank, index, name, rate, body)
        index += 1
        pos = end + (length & 1)


def banks(disc):
    """Read all SFX banks from the disc image, independent of extracted/."""
    names = sorted(name for name in disc.files()
                   if '/' not in name and name.startswith('SFX') and name.endswith('.BIN'))
    if not names:
        raise ValueError('no MK SFX banks found on disc')
    return {name: disc.read_file(name) for name in names}


def write_wav(sample, output):
    # 8SVX BODY contains signed 8-bit PCM; place it in the high byte of a
    # signed little-endian 16-bit sample without changing its amplitude.
    pcm = bytearray(2 * len(sample.body))
    pcm[1::2] = sample.body
    with wave.open(str(output), 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sample.rate)
        out.writeframes(pcm)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='cmd', required=True)
    listing = sub.add_parser('list', help='list disc sound samples')
    listing.add_argument('bank', nargs='?')
    extraction = sub.add_parser('extract', help='extract one unmixed sample as WAV')
    extraction.add_argument('sample', help='BANK:INDEX or BANK:NAME')
    extraction.add_argument('output')
    check = sub.add_parser('check', help='compare disc SFX banks with extracted files')
    check.add_argument('extracted', nargs='?', default=str(Path(ROOT) / 'extracted' / 'mk_us'))
    argv = sys.argv[1:]
    if argv and argv[0] == '--check':
        argv = ['check', *argv[1:]]
    args = parser.parse_args(argv)
    disc = require('mk_us')
    try:
        source = banks(disc)
        if args.cmd == 'check':
            root = Path(args.extracted)
            failures = []
            total = 0
            for name, data in source.items():
                total += len(list(parse_bank(name, data)))
                path = root / name
                if not path.is_file() or path.read_bytes() != data:
                    failures.append(name)
            if failures:
                raise SystemExit('missing or different banks: ' + ', '.join(failures))
            print(f'{len(source)} disc banks match {root}; {total} samples parsed')
            return
        if args.cmd == 'list':
            selected = [args.bank.upper()] if args.bank else list(source)
            for name in selected:
                if name not in source:
                    raise SystemExit(f'bank not found: {name}')
                for s in parse_bank(name, source[name]):
                    print(f'{s.bank}:{s.index:<2} {s.name or "(unnamed)":20} {s.rate:5} Hz  {len(s.body):6} samples')
            return
        try:
            name, index_or_name = args.sample.split(':', 1)
            name = name.upper()
            if name not in source:
                raise ValueError(f'bank not found: {name}')
            records = list(parse_bank(name, source[name]))
            if index_or_name.isdecimal():
                matches = [s for s in records if s.index == int(index_or_name)]
            else:
                matches = [s for s in records if s.name.upper() == index_or_name.upper()]
            if len(matches) != 1:
                raise ValueError(f'expected one matching sample, found {len(matches)}')
            write_wav(matches[0], args.output)
            print(f'{matches[0].bank}:{matches[0].index} {matches[0].name or "(unnamed)"} -> {args.output}')
        except ValueError as e:
            raise SystemExit(str(e)) from e
    finally:
        disc.close()


if __name__ == '__main__':
    main()
