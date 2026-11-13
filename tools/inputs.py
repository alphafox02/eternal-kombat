"""The discs this project reads, and how to find them under roms/.

Every disc is identified by the SHA-1 of its data track (track 1, raw 2352),
which doesn't depend on how the dump's files are named or split.
"""
import glob, os
from disc import Disc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROMS = os.path.join(ROOT, 'roms')

KNOWN = {
    'ec_us': dict(
        sha1='261809c666e5d91626a222f252caa383c50cecb9', tracks=19, required=True,
        title='Eternal Champions: Challenge from the Dark Side (USA)',
        role='ENGINE: the game this project patches'),
    'mk_us': dict(
        sha1='79e0dd945681f8ed25fa6857dcac6a3fc8bb3d5f', tracks=21, required=True,
        title='Mortal Kombat (USA) (Sega CD)',
        role='CONTENT: fighters, stages, sounds and music brought into EC'),
    'mk_jp': dict(
        sha1='8c498a7923b41f2e4f0a32766bbf2f8889991fdd', tracks=21, required=False,
        title='Mortal Kombat Kanzenban (Japan)',
        role='optional: same files as the US disc, different boot region'),
    'umk3_gen': dict(
        sha1='bf2da4a7ae7aa428b0b316581f65b280dc3ba356', tracks=0, required=False, cart=True,
        title='Ultimate Mortal Kombat 3 (USA) (Genesis cartridge)',
        role='optional: extra fighters and frames (larger roster, more moves)'),
    'mk_rfg': dict(
        sha1='ec00f47dbf628f042f1fde8f0a0a1e6eddab0224', tracks=23, required=False,
        title='Mortal Kombat - Psycho RFG Edition v1.1 (fan patch of MK USA)',
        role='optional: reference only'),
}

# fall-back identification by the boot header, for other revisions/dumps
HEADER_HINTS = {
    'ec_us': b'ETERNAL CHAMPIONS CD',
    'mk_us': b'MORTAL KOMBAT',
}


class Cart:
    """A cartridge ROM found under roms/ (no cue sheet)."""
    def __init__(self, path, sha):
        self.cue = self.path = path       # .cue kept so callers can print a location
        self.sha1 = sha


def scan_carts(root, found, other):
    import hashlib
    by_sha = {v['sha1']: k for k, v in KNOWN.items() if v.get('cart')}
    for ext in ('md', 'gen', 'smd', 'bin'):
        for p in glob.glob(os.path.join(root, '**', f'*.{ext}'), recursive=True):
            if os.path.getsize(p) > 8 << 20:
                continue
            with open(p, 'rb') as f:
                head = f.read(0x110)
            if not head[0x100:0x110].startswith(b'SEGA'):
                continue                      # not a Genesis cartridge (e.g. a disc track)
            sha = hashlib.sha1(open(p, 'rb').read()).hexdigest()
            key = by_sha.get(sha)
            if key and key not in found:
                found[key] = Cart(p, sha)
            elif not key:
                other.append((p, f'unrecognised cartridge (SHA-1 {sha})'))


def scan(root=ROMS):
    """Return ({id: Disc|Cart}, [(path, note)] unmatched, [archives])."""
    found, other = {}, []
    scan_carts(root, found, other)
    by_sha = {v['sha1']: k for k, v in KNOWN.items()}
    for cue in sorted(glob.glob(os.path.join(root, '**', '*.cue'), recursive=True)):
        try:
            d = Disc(cue)
            sha = d.data_sha1()
        except Exception as e:                       # noqa: BLE001
            other.append((cue, f'unreadable: {e}'))
            continue
        key = by_sha.get(sha)
        if key and key not in found:
            found[key] = d
            continue
        head = d.read(0)[:0x200]
        hint = next((k for k, h in HEADER_HINTS.items() if h in head), None)
        if hint and hint not in found:
            d.unverified = True
            found[hint] = d
            other.append((cue, f'looks like {hint} but data-track SHA-1 {sha} is not the known dump'))
        else:
            other.append((cue, f'unrecognised (SHA-1 {sha})'))
    archives = [p for ext in ('7z', 'rar', 'zip')
                for p in glob.glob(os.path.join(root, '**', f'*.{ext}'), recursive=True)]
    return found, other, archives


def require(key):
    found, _, _ = scan()
    if key not in found:
        raise SystemExit(f'{KNOWN[key]["title"]} not found under roms/. Run: python3 tools/checkinputs.py')
    return found[key]
