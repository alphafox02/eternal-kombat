# SPDX-License-Identifier: MIT
"""Sega CD disc images: cue sheets, raw MODE1/2352 sectors, ISO9660, patching.

A disc is described by a cue sheet. Each FILE can hold one track (Redump
style, one .bin per track) or several (single-bin rips); both are handled by
remembering, for every track, which file it lives in and at what byte offset.

Track 1 is the MODE1 data track holding the ISO9660 filesystem. Patching a
file in place rewrites the 2048-byte user data of the sectors it occupies
and recomputes each sector's EDC and ECC, so the result is a valid raw image
for emulators, optical drive emulators and burners alike.
"""
import hashlib, os, re, shutil

RAW = 2352
USER = 2048
DATA_OFS = 16          # sync(12) + header(4)


# --------------------------------------------------------------------------
# cue sheets
# --------------------------------------------------------------------------
class Track:
    def __init__(self, number, mode, file, index01_frames):
        self.number, self.mode, self.file = number, mode, file
        self.index01 = index01_frames        # sectors from start of its FILE
        self.length = None                   # sectors, filled in later

    @property
    def is_data(self):
        return self.mode.startswith('MODE')

    def __repr__(self):
        return f'Track({self.number} {self.mode} {os.path.basename(self.file)} @{self.index01} len={self.length})'


def msf(s):
    m, sec, f = (int(x) for x in s.split(':'))
    return (m * 60 + sec) * 75 + f


def parse_cue(path):
    base = os.path.dirname(os.path.abspath(path))
    tracks, cur_file, cur = [], None, None
    for raw in open(path, encoding='latin-1'):
        line = raw.strip()
        if not line:
            continue
        m = re.match(r'FILE\s+"(.*)"\s+(\w+)', line) or re.match(r'FILE\s+(\S+)\s+(\w+)', line)
        if m:
            cur_file = os.path.join(base, m.group(1))
            continue
        m = re.match(r'TRACK\s+(\d+)\s+(\S+)', line)
        if m:
            cur = Track(int(m.group(1)), m.group(2), cur_file, None)
            tracks.append(cur)
            continue
        m = re.match(r'INDEX\s+01\s+(\d+:\d+:\d+)', line)
        if m and cur is not None:
            cur.index01 = msf(m.group(1))
    # lengths: up to the next track in the same file, else to end of file
    for i, t in enumerate(tracks):
        nxt = next((u for u in tracks[i + 1:] if u.file == t.file), None)
        end = nxt.index01 if nxt else os.path.getsize(t.file) // RAW
        t.length = end - t.index01
    return tracks


# --------------------------------------------------------------------------
# EDC / ECC  (ECMA-130, mode 1)
# --------------------------------------------------------------------------
_F = [0] * 256
_B = [0] * 256
_EDC = [0] * 256
for _i in range(256):
    _j = ((_i << 1) ^ (0x11D if _i & 0x80 else 0)) & 0xFF
    _F[_i] = _j
    _B[_i ^ _j] = _i
    _e = _i
    for _ in range(8):
        _e = (_e >> 1) ^ (0xD8018001 if _e & 1 else 0)
    _EDC[_i] = _e


def edc(data):
    e = 0
    for b in data:
        e = (e >> 8) ^ _EDC[(e ^ b) & 0xFF]
    return e


def _ecc_block(sec, major_count, minor_count, major_mult, minor_inc, dest):
    src = 0xC
    size = major_count * minor_count
    for major in range(major_count):
        index = (major >> 1) * major_mult + (major & 1)
        a = b = 0
        for _ in range(minor_count):
            t = sec[src + index]
            index += minor_inc
            if index >= size:
                index -= size
            a ^= t
            b ^= t
            a = _F[a]
        a = _B[_F[a] ^ b]
        sec[dest + major] = a
        sec[dest + major + major_count] = a ^ b


def fix_mode1(sec):
    """Recompute EDC + ECC of a raw MODE1 sector (bytearray, 2352) in place."""
    sec[0x814:0x81C] = bytes(8)
    sec[0x810:0x814] = edc(sec[0:0x810]).to_bytes(4, 'little')
    _ecc_block(sec, 86, 24, 2, 86, 0x81C)    # P parity
    _ecc_block(sec, 52, 43, 86, 88, 0x8C8)   # Q parity
    return sec


# --------------------------------------------------------------------------
# a disc image
# --------------------------------------------------------------------------
class Disc:
    def __init__(self, cue):
        self.cue = os.path.abspath(cue)
        self.tracks = parse_cue(cue)
        self.data = self.tracks[0]
        if not self.data.is_data:
            raise ValueError(f'{cue}: track 1 is not a data track')
        self._files = {}

    def _fh(self, path, write=False):
        # One handle per file once it's written: a separate read handle's
        # buffer would serve stale sectors after a write (a patch rereading a
        # file an earlier patch rewrote saw the old bytes and size).
        if (path, True) in self._files:
            return self._files[(path, True)]
        if write:
            old = self._files.pop((path, False), None)
            if old:
                old.close()
            self._files[(path, True)] = open(path, 'r+b')
            return self._files[(path, True)]
        if (path, False) not in self._files:
            self._files[(path, False)] = open(path, 'rb')
        return self._files[(path, False)]

    def close(self):
        for f in self._files.values():
            f.close()
        self._files = {}

    def raw_sector(self, lba):
        f = self._fh(self.data.file)
        f.seek((self.data.index01 + lba) * RAW)
        return bytearray(f.read(RAW))

    def read(self, lba, count=1):
        """User data (2048 bytes/sector) starting at track-1 LBA."""
        return b''.join(bytes(self.raw_sector(lba + i)[DATA_OFS:DATA_OFS + USER]) for i in range(count))

    def write_user(self, lba, data):
        """Overwrite user data starting at lba, fixing EDC/ECC of each sector.
        data may end mid-sector; the rest of that sector is preserved."""
        f = self._fh(self.data.file, write=True)
        for i in range(0, len(data), USER):
            sec = self.raw_sector(lba + i // USER)
            chunk = data[i:i + USER]
            sec[DATA_OFS:DATA_OFS + len(chunk)] = chunk
            fix_mode1(sec)
            f.seek((self.data.index01 + lba + i // USER) * RAW)
            f.write(sec)
        f.flush()

    def data_sha1(self):
        h = hashlib.sha1()
        f = self._fh(self.data.file)
        f.seek(self.data.index01 * RAW)
        left = self.data.length * RAW
        while left:
            b = f.read(min(left, 1 << 22))
            if not b:
                break
            h.update(b)
            left -= len(b)
        return h.hexdigest()

    # ---- ISO9660 --------------------------------------------------------
    def files(self):
        """{NAME: (lba, size)} for every file (root and subdirectories)."""
        pvd = self.read(16)
        if pvd[1:6] != b'CD001':
            raise ValueError('no ISO9660 volume descriptor at sector 16')
        out = {}

        def walk(lba, size, prefix):
            buf = self.read(lba, (size + USER - 1) // USER)
            pos = 0
            while pos < size:
                ln = buf[pos]
                if ln == 0:                      # records don't cross sectors
                    pos = (pos // USER + 1) * USER
                    continue
                rec = buf[pos:pos + ln]
                ext = int.from_bytes(rec[2:6], 'little')
                sz = int.from_bytes(rec[10:14], 'little')
                flags = rec[25]
                name = rec[33:33 + rec[32]]
                pos += ln
                if name in (b'\x00', b'\x01'):
                    continue
                name = name.decode('latin-1').split(';')[0]
                if flags & 2:
                    walk(ext, sz, prefix + name + '/')
                else:
                    out[prefix + name] = (ext, sz)

        root = pvd[156:156 + 34]
        walk(int.from_bytes(root[2:6], 'little'), int.from_bytes(root[10:14], 'little'), '')
        return out

    def read_file(self, name):
        lba, size = self.files()[name]
        return self.read(lba, (size + USER - 1) // USER)[:size]

    def patch_file(self, name, offset, new, expect=None):
        """Replace bytes [offset, offset+len(new)) of a file in place.
        If expect is given, the current bytes must match it first."""
        lba, size = self.files()[name]
        if offset + len(new) > size:
            raise ValueError(f'{name}: patch at {offset:#x}+{len(new)} runs past end ({size})')
        cur = self.read_file(name)
        if expect is not None and cur[offset:offset + len(expect)] != expect:
            raise ValueError(f'{name}@{offset:#x}: expected {expect!r}, found {cur[offset:offset + len(expect)]!r}')
        first = offset // USER
        last = (offset + len(new) - 1) // USER
        block = bytearray(cur[first * USER:(last + 1) * USER].ljust((last - first + 1) * USER, b'\0'))
        # keep any bytes past EOF in the last sector exactly as they were
        tail = self.read(lba + last)
        block[-USER:] = tail
        mid = bytearray(self.read(lba + first, last - first + 1))
        rel = offset - first * USER
        mid[rel:rel + len(new)] = new
        self.write_user(lba + first, bytes(mid))


def _bcd(n):
    return ((n // 10) << 4) | (n % 10)


def _raw_mode1(lba, user):
    """Build a raw MODE1 sector for track-1 LBA lba (2-second pregap)."""
    sec = bytearray(RAW)
    sec[0:12] = b'\x00' + b'\xff' * 10 + b'\x00'
    a = lba + 150
    sec[12:16] = bytes([_bcd(a // 4500), _bcd(a // 75 % 60), _bcd(a % 75), 1])
    sec[16:16 + USER] = user.ljust(USER, b'\0')
    return fix_mode1(sec)


def _replace_file(self, name, data):
    """Replace a file's contents. Same or smaller sector count: rewritten in
    place. Larger: written to new sectors appended to the end of the data
    track, and the file's ISO9660 directory record (extent + size) and the
    volume size are updated. Only for discs with a data track in its own file."""
    lba, size = self.files()[name]
    old_secs = (size + USER - 1) // USER
    new_secs = (len(data) + USER - 1) // USER
    padded = data.ljust(new_secs * USER, b'\0')
    if new_secs <= old_secs:
        self.write_user(lba, padded)
        new_lba = lba
    else:
        if any(t.file == self.data.file for t in self.tracks[1:]):
            raise ValueError('growing a file needs the data track in its own .bin')
        new_lba = self.data.length
        f = self._fh(self.data.file, write=True)
        f.seek((self.data.index01 + new_lba) * RAW)
        for i in range(new_secs):
            f.write(_raw_mode1(new_lba + i, padded[i * USER:(i + 1) * USER]))
        f.flush()
        self.data.length += new_secs
        pvd = bytearray(self.read(16))
        n = self.data.length
        pvd[80:88] = n.to_bytes(4, 'little') + n.to_bytes(4, 'big')
        self.write_user(16, bytes(pvd))
    # directory record: find it and update extent + size
    self._set_dir_record(name, new_lba, len(data))
    return new_lba


def _set_dir_record(self, name, lba, size):
    pvd = self.read(16)

    def walk(dlba, dsize, prefix):
        nsec = (dsize + USER - 1) // USER
        for s in range(nsec):
            sec = bytearray(self.read(dlba + s))
            pos = 0
            while pos < USER:
                ln = sec[pos]
                if ln == 0:
                    break
                rec = sec[pos:pos + ln]
                nm = rec[33:33 + rec[32]].decode('latin-1').split(';')[0]
                ext = int.from_bytes(rec[2:6], 'little')
                sz = int.from_bytes(rec[10:14], 'little')
                if rec[25] & 2 and nm not in ('\x00', '\x01'):
                    if walk(ext, sz, prefix + nm + '/'):
                        return True
                elif prefix + nm == name:
                    sec[pos + 2:pos + 10] = lba.to_bytes(4, 'little') + lba.to_bytes(4, 'big')
                    sec[pos + 10:pos + 18] = size.to_bytes(4, 'little') + size.to_bytes(4, 'big')
                    self.write_user(dlba + s, bytes(sec))
                    return True
                pos += ln
        return False

    root = pvd[156:156 + 34]
    if not walk(int.from_bytes(root[2:6], 'little'), int.from_bytes(root[10:14], 'little'), ''):
        raise KeyError(name)


Disc.replace_file = _replace_file
Disc._set_dir_record = _set_dir_record


def copy_disc(src_cue, out_dir, name):
    """Copy a disc to out_dir as NAME.cue + its files. Files holding the data
    track are copied (they will be patched); audio-only files are hard-linked
    when possible, since they never change. Returns the new cue path."""
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):                  # (a previous build's files: a track no cue lists
        if f.startswith(name) and f.endswith(('.bin', '.cue')):   #  stays behind otherwise)
            os.remove(os.path.join(out_dir, f))
    tracks = parse_cue(src_cue)
    data_files = {t.file for t in tracks if t.is_data}
    mapping = {}
    for t in tracks:
        if t.file in mapping:
            continue
        stem = os.path.basename(t.file)
        stem = f'{name} (Track {t.number:02d}).bin' if len({u.file for u in tracks}) > 1 else f'{name}.bin'
        dst = os.path.join(out_dir, stem)
        if os.path.exists(dst):
            os.remove(dst)
        if t.file in data_files:
            shutil.copyfile(t.file, dst)
        else:
            try:
                os.link(t.file, dst)
            except OSError:
                shutil.copyfile(t.file, dst)
        mapping[t.file] = stem
    src_dir = os.path.dirname(os.path.abspath(src_cue))
    out_cue = os.path.join(out_dir, name + '.cue')
    with open(out_cue, 'w', newline='\r\n') as o:
        for raw in open(src_cue, encoding='latin-1'):
            line = raw.rstrip('\r\n')
            m = re.match(r'(\s*FILE\s+)"(.*)"(\s+\w+)', line)
            if m:
                line = f'{m.group(1)}"{mapping[os.path.join(src_dir, m.group(2))]}"{m.group(3)}'
            o.write(line + '\n')
    return out_cue


def ec_file_ids(sub):
    """EC's file names by file id (SUB.BIN's name list: a word offset table at
    $CE9E-$6000, then length-prefixed 'NAME;1' strings)."""
    W = lambda o: int.from_bytes(sub[o:o + 2], 'big')
    end = sub.find(b'\nMISC.BIN')                  # the first name's length byte
    t = end - 2
    while t > 2 and W(t - 2) < W(t):
        t -= 2
    offs = [W(o) for o in range(t, end, 2)]
    base = end - offs[0]
    return [sub[base + o + 1:base + o + 1 + sub[base + o]].decode('latin-1').split(';')[0] for o in offs]


RUNTIME_FILES = 0x12E9E       # PRG RAM: EC's file table (8 bytes per id: sector, sectors), built at boot


def stale_files(ram, disc):
    """Files whose sector in a saved state's file table (built when THAT boot
    ran) isn't where the disc has them now: a state from before a build that
    moved files reads the wrong sectors (code loaded off by a sector, ...)."""
    names = ec_file_ids(disc.read_file('SUB.BIN'))
    where = disc.files()
    out = []
    for i, n in enumerate(names):
        if n in where:
            lba = int.from_bytes(ram[RUNTIME_FILES + 8 * i:RUNTIME_FILES + 8 * i + 4], 'big')
            if lba != where[n][0]:
                out.append((n, lba, where[n][0]))
    return out
