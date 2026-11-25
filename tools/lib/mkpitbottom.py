#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Extract MK CD's Pit bottom (spikes, heads, impaled body) from the MK disc.

The scene the Pit fatality scrolls down to when the loser is uppercut off the
bridge. The Pit is BACKGD4.BIN: a 6-long offset table, then sections packed with
Rob Northen's ProPack method 1 ('RNC\\x01'):
  0  tiles, 818 x 4bpp (in a fight they sit at VRAM tile 414 up)
  1  plane-A map, 110 x 86 cells, words: tile index | $0800 h-flip;
     palette line 3 for every cell. Rows 0-20 are the bridge the fight
     shows; rows 21-85 (pillars, brick wall, spike floor) only appear in
     the fatality.
  2  plane-B map (clouds), 64 x 15     3/4  not used here
  5  (not packed) 2 palettes: lines 2 and 3
PAC.PRG (loaded at PRG-RAM $9000) holds a second packed copy of section 1
at $242F8; the fatality ($1797C) unpacks that one and streams its rows
down the plane as the camera scrolls.

    mkpitbottom.py            static: decode BACKGD4.BIN from the MK disc
    mkpitbottom.py --disc-files DIR [--check EXTRACTED]
                              from DIR's BACKGD4.BIN and PAC.PRG; --check compares, writes nothing
    mkpitbottom.py --video    also play the fatality on the MK disc: record
                              build/shots/mk_pit_fatality.mp4 and dump the VDP at
                              the bottom (checks the static crop against it)

The fatality (victim's reaction code $178D4): stage $8E8A = 3 (Pit),
$8F6E = 0, the hit leaves the victim's health ($24(a6)) at 0 and the
winner's round count ($7BA82 / $7BA84) at 2 - i.e. a match-winning
uppercut at FINISH HIM. Here P1 uppercuts from where the jab left him
(gap about -20 px). Seen: when a walk-to-a-gap loop of 1-frame holds ran
first, Kano never crouched and threw a standing punch instead.

-> extracted/mk_stages/pit_bottom/
     pit_full.png / pit_full_indexed.png      the whole 880x688 map
     pit_bottom.png / pit_bottom_indexed.png  the 320x224 the fatality ends on
     pit_bottom.json   palette (line 3), crop, sizes, sources
     tiles.bin, map.bin  raw tiles (4bpp) and map (big-endian words)
     ingame_*          (--video) VDP planes, CRAM and screen at the bottom
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image
from inputs import ROOT, require
from disc import Disc

OUT = os.path.join(ROOT, 'extracted', 'mk_stages', 'pit_bottom')
MAP_W, MAP_H = 110, 86
PAC_BASE, PAC_BLOB = 0x9000, 0x242F8
# Where the fatality's camera stops: VSRAM A 544 with the map's row 0 on
# plane row 11, H scroll -280 -> map pixels x 280-599, y 456-679.
CROP = (280, 456, 320, 224)
LINE = 3
VDP = 0x12025


def rnc1(data, off=0):
    """Unpack an RNC ProPack method-1 block at data[off]."""
    assert data[off:off + 4] == b'RNC\x01', data[off:off + 4]
    ulen = int.from_bytes(data[off + 4:off + 8], 'big')
    # (a block can end on an odd byte at the file's end: BACKGD5.BIN's last; that byte still counts)
    lw = lambda q: (data[q] if q < len(data) else 0) | (data[q + 1] << 8 if q + 1 < len(data) else 0)
    s = dict(buf=lw(off + 18), cnt=16, p=off + 18)

    def adv(n):
        s['buf'] >>= n
        s['cnt'] -= n
        if s['cnt'] < 16:
            s['p'] += 2
            s['buf'] |= lw(s['p']) << s['cnt']
            s['cnt'] += 16

    def read(n):
        r = s['buf'] & ((1 << n) - 1)
        adv(n)
        return r

    def table():
        num = read(5)
        if not num:
            return []
        ln = [read(4) for _ in range(num)]
        t, code = [], 0
        for size in range(1, max(ln) + 1):
            for v in range(num):
                if ln[v] == size:
                    t.append((int(format(code, f'0{size}b')[::-1], 2), size, v))
                    code += 1
            code <<= 1
        return t

    def huf(t):
        for code, size, v in t:
            if s['buf'] & ((1 << size) - 1) == code:
                adv(size)
                return (1 << (v - 1)) | read(v - 1) if v >= 2 else v
        raise ValueError('bad RNC stream')

    out = bytearray()
    adv(2)
    while len(out) < ulen:
        raw, dist, length = table(), table(), table()
        for left in range(read(16), 0, -1):
            n = huf(raw)
            if n:
                out += data[s['p']:s['p'] + n]
                s['p'] += n
                s['cnt'] -= 16                      # re-fill from the new position
                s['buf'] &= (1 << s['cnt']) - 1
                s['buf'] |= lw(s['p']) << s['cnt']
                s['cnt'] += 16
            if left == 1:
                break
            back, n = huf(dist) + 1, huf(length) + 2
            for _ in range(n):
                out.append(out[-back])
    out = bytes(out[:ulen])
    assert crc16(out) == int.from_bytes(data[off + 12:off + 14], 'big'), f'RNC block at {off:#x}: bad unpack'
    return out


_CRC = []


def crc16(data):
    """RNC's CRC-16 (reflected polynomial $A001), as its header holds for the unpacked data."""
    if not _CRC:
        for i in range(256):
            v = i
            for _ in range(8):
                v = (v >> 1) ^ 0xA001 if v & 1 else v >> 1
            _CRC.append(v)
    c = 0
    for b in data:
        c = _CRC[(c ^ b) & 0xFF] ^ (c >> 8)
    return c


def rgb(words):
    return [(((w >> 1) & 7) * 36, ((w >> 5) & 7) * 36, ((w >> 9) & 7) * 36) for w in words]


def render(tiles, m):
    """Map words -> colour-index image."""
    h, w = m.shape
    t = np.frombuffer(tiles, np.uint8).reshape(-1, 8, 4)
    px = np.empty((len(t), 8, 8), np.uint8)
    px[:, :, 0::2], px[:, :, 1::2] = t >> 4, t & 15
    img = np.zeros((h * 8, w * 8), np.uint8)
    for y in range(h):
        for x in range(w):
            e = int(m[y, x])
            c = px[e & 0x7FF]
            if e & 0x800:
                c = c[:, ::-1]
            if e & 0x1000:
                c = c[::-1]
            img[y * 8:y * 8 + 8, x * 8:x * 8 + 8] = c
    return img


def save(idx, pal_words, name, out=OUT):
    cols = np.array(rgb(pal_words), np.uint8)
    Image.fromarray(np.dstack([cols[idx], (idx > 0) * 255]).astype(np.uint8), 'RGBA').save(
        os.path.join(out, name + '.png'))
    p = Image.fromarray(idx, 'P')
    p.putpalette([v for c in cols for v in c] + [0] * (768 - 48))
    p.info['transparency'] = 0
    p.save(os.path.join(out, name + '_indexed.png'), transparency=0)


def static(bg=None, pac=None, out=OUT):
    if bg is None or pac is None:
        d = Disc(require('mk_us').cue)
        bg, pac = d.read_file('BACKGD4.BIN'), d.read_file('PAC.PRG')
    offs = [int.from_bytes(bg[i:i + 4], 'big') for i in range(0, 24, 4)]
    tiles, mp = rnc1(bg, offs[0]), rnc1(bg, offs[1])
    pals = bg[offs[5]:offs[5] + 0x40]                # stored raw in BACKGD4
    assert rnc1(pac, PAC_BLOB - PAC_BASE) == mp, "PAC.PRG's copy differs"
    m = np.frombuffer(mp, '>u2').reshape(MAP_H, MAP_W)
    pal = [int.from_bytes(pals[32 + 2 * i:34 + 2 * i], 'big') for i in range(16)]
    pal_fatality = pal[:15] + [0]                   # the fatality fades colour 15 (navy sky) to black
    os.makedirs(out, exist_ok=True)
    idx = render(tiles, m)
    save(idx, pal, 'pit_full', out)
    x, y, w, h = CROP
    save(np.ascontiguousarray(idx[y:y + h, x:x + w]), pal_fatality, 'pit_bottom', out)
    open(os.path.join(out, 'tiles.bin'), 'wb').write(tiles)
    open(os.path.join(out, 'map.bin'), 'wb').write(mp)
    info = dict(
        source='MK CD (USA) BACKGD4.BIN: RNC sections 0 (tiles), 1 (map), 5 (palettes, 2nd = line 3)',
        pac_copy=f'PAC.PRG ${PAC_BLOB:X} (file +${PAC_BLOB - PAC_BASE:X}): same map, unpacked by the fatality',
        map_cells=[MAP_W, MAP_H], map_px=[MAP_W * 8, MAP_H * 8], tiles=len(tiles) // 32,
        map_word='tile index (0-817) | $0800 h-flip; palette line 3, VRAM tile = index + 414 in a fight',
        fight_rows='map rows 0-20 = plane A rows 11-31 during the fight (bridge)',
        crop_xywh=list(CROP), crop_cells=[CROP[0] // 8, CROP[1] // 8, CROP[2] // 8, CROP[3] // 8],
        palette_line=LINE, palette_genesis=[f'{v:04X}' for v in pal],
        palette_fatality_genesis=[f'{v:04X}' for v in pal_fatality],
        palette_rgb=rgb(pal), palette_fatality_rgb=rgb(pal_fatality),
        note='colour 0 is transparent ($0E0E placeholder in the file); pit_full uses the file palette '
             '(navy sky), pit_bottom the palette the fatality ends with (colour 15 black)')
    json.dump(info, open(os.path.join(out, 'pit_bottom.json'), 'w'), indent=1)
    print('map', MAP_W, 'x', MAP_H, 'cells,', len(tiles) // 32, 'tiles ->', os.path.relpath(out, ROOT))
    return idx, pal_fatality


def video(out, idx, pal_fatality):
    """Win on the Pit (Kano vs Kano from build/states/mk_pit_raw.state, P2 poked to
    2 hp each round), then at FINISH HIM wait and uppercut where they stand."""
    import scd
    from vdp import VDPState
    from finishvideo import Rec
    c = scd.Core(audio=True, saves=os.path.join(ROOT, 'build', 'shots', 'capture-saves'))
    c.load(require('mk_us').cue)
    c.load_state(os.path.join(ROOT, 'build', 'states', 'mk_pit_raw.state'))
    hp = lambda: tuple(int.from_bytes(c.prg_ram()[a:a + 2], 'big') for a in (0x7D6C4, 0x7D7CA))

    def gap():
        xs = {}
        for pal in (0, 1):
            x = [s['x'] for s in VDPState(c.snapshot()).sprites() if s['pal'] == pal and 80 < s['y'] < 230]
            xs[pal] = (min(x), max(x) + 16) if x else None
        return xs[1][0] - xs[0][1] if xs[0] and xs[1] else None

    def hold(b, n):
        c.buttons[0] = set(b)
        c.run(n)
        c.buttons[0] = set()

    c.run(60)
    c.poke_prg(0x7D7CA, (2).to_bytes(2, 'big'))     # round 1: one jab wins it
    for _ in range(40):
        hold(['right'], 2)
    hold(['a'], 3)
    c.run(20)
    for _ in range(150):
        if hp() == (119, 119):
            break
        c.run(10)
    c.run(240)
    c.poke_prg(0x7D7CA, (2).to_bytes(2, 'big'))     # round 2: jab -> FINISH HIM
    for _ in range(60):
        g = gap()
        if g is not None and g < -10:
            break
        hold(['right'], 2)
    hold(['a'], 3)
    c.run(5)
    c.audio.clear()
    r = Rec(c, out)
    r.run(150)                                       # FINISH HIM on screen; don't walk first
    r.run(8, ['down'])
    # frame numbers below count from the first frame of down + X (frame 0)
    r.run(4, ['down', 'x'])
    r.run(10, ['down'])
    log, prev = [], None
    for f in range(14, 660):
        r.run(1)
        st = c.snapshot()
        v = VDPState(st)
        vs = st[VDP + 0x10480] | st[VDP + 0x10481] << 8
        pr = c.prg_ram()
        k = (vs, v.cram_raw[63], v.cram_raw[33], int.from_bytes(pr[0x7BAA8:0x7BAAC], 'big') > 0)
        if k != prev:
            log.append((f, *k))
            prev = k
        if f == 300:
            for p in 'AB':
                img, used = v.plane(p)
                Image.fromarray(np.dstack([img, (used * 255).astype(np.uint8)]), 'RGBA').save(
                    os.path.join(OUT, f'ingame_plane_{p.lower()}.png'))
            json.dump(v.cram_raw, open(os.path.join(OUT, 'ingame_cram.json'), 'w'))
            Image.fromarray(c.frame).save(os.path.join(OUT, 'ingame_screen.png'))
            hs = int.from_bytes(v.vram[0xB800:0xB802], 'big')
            hs = hs - 0x10000 if hs & 0x8000 else hs
            pa = np.frombuffer(v.vram[0xE000:0xE000 + 128 * 32 * 2], '>u2').reshape(32, 128)
            # plane A as the screen sees it vs the static crop, colour indices
            x, y, w, h = CROP
            seen = np.zeros((h, w), np.uint8)
            for sy in range(h):
                py = (sy + vs) & 255
                e = pa[py >> 3]
                for sx in range(w):
                    px = (sx - hs) & 1023
                    word = int(e[px >> 3])
                    t = v.tile(word & 0x7FF)
                    if word & 0x800:
                        t = t[:, ::-1]
                    seen[sy, sx] = t[py & 7, px & 7]
            diff = int((seen != idx[y:y + h, x:x + w]).sum())
            print(f'frame {f}: vscroll {vs}, hscroll {hs}; static crop vs plane A: {diff} pixels differ;'
                  f' CRAM line 3 == crop palette: {v.cram_raw[48:64][1:] == [((p >> 1) & 7) | ((p >> 5) & 7) << 3 | ((p >> 9) & 7) << 6 for p in pal_fatality][1:]}')
    r.close()
    print('timeline, frames from the first frame of down + X (clip frame 158 = frame 0):')
    run = None                                       # collapse stretches where only VSRAM A moves
    for i, (f, vs, c3, c2, stream) in enumerate(log):
        if i and (c3, c2, stream) == log[i - 1][2:]:
            run = run or [log[i - 1][0], log[i - 1][1]]
            if i + 1 < len(log) and log[i + 1][2:] == (c3, c2, stream):
                continue
            print(f'   {run[0]:3}-{f:3}  VSRAM A {run[1]} -> {vs}')
            run = None
        else:
            print(f'   {f:3}      VSRAM A {vs}, CRAM 3:15 ${c3:03X}, CRAM 2:1 ${c2:03X}, map streaming {stream}')
    print('->', os.path.relpath(out, ROOT), r.frames, 'frames')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--video', action='store_true')
    ap.add_argument('--out', default=os.path.join(ROOT, 'build', 'shots', 'mk_pit_fatality.mp4'))
    ap.add_argument('--disc-files', help='directory containing extracted BACKGD4.BIN and PAC.PRG')
    ap.add_argument('--check', help='compare generated static files to this extracted directory')
    a = ap.parse_args()
    if a.check and a.video:
        ap.error('--check and --video cannot be combined')
    bg = open(os.path.join(a.disc_files, 'BACKGD4.BIN'), 'rb').read() if a.disc_files else None
    pac = open(os.path.join(a.disc_files, 'PAC.PRG'), 'rb').read() if a.disc_files else None
    if a.check:
        import tempfile
        files = ('pit_full.png', 'pit_full_indexed.png', 'pit_bottom.png', 'pit_bottom_indexed.png',
                 'tiles.bin', 'map.bin', 'pit_bottom.json')
        with tempfile.TemporaryDirectory() as tmp:
            static(bg, pac, tmp)
            bad = []
            for name in files:
                ref = os.path.join(a.check, 'mk_stages', 'pit_bottom', name)
                if not os.path.isfile(ref) or open(ref, 'rb').read() != open(os.path.join(tmp, name), 'rb').read():
                    bad.append(name)
            print(f'{len(files)-len(bad)}/{len(files)} static Pit-bottom files byte-identical',
                  ('different: ' + ', '.join(bad)) if bad else '')
            if bad: sys.exit(1)
        return
    idx, pal_f = static(bg, pac)
    if a.video:
        video(a.out, idx, pal_f)


if __name__ == '__main__':
    main()
