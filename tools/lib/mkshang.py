#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""MK's Shang Tsung (EMP.OBJ/EMP.SCH on the MK disc) as the art of EC's Eternal Champion.

Both forms (ECH.PL, fighter 11, and ECX.PL, fighter 26) keep their code,
their moves and their boss sequence; every pose shows the Shang pose whose
outline is closest (MK's Shang only stands, casts, raises his arms, reels and
falls: he never punches, kicks or jumps). The reskin is not in the build
(patches.shang_tsung is kept unregistered: Shang is his own fighter);
frames() is what mkshangmoves.py and mkprojectile.py draw his art from.

Colours: Eternal is drawn in palette line 2 (player 2's), from a list of
palettes in his module (CHA.CO / ECX.CO: his own, alternates, glow fades
and one per special, whose entries 12-15 colour its glow). Shang gets
entries 1-8 and 11 in all of them (patches.shang_tsung); the 15 colours at
PAC.PRG $1C110 are fitted to those 9 (Goro's palette: Shang's own is at $1C130,
mkshangmoves.PALETTE_AT).

    mkshang.py sheet OUT.png           Shang's poses as fitted (a contact sheet)
    mkshang.py match HOST.PL OUT.png   each host pose beside the Shang pose it gets
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import json
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MK = os.path.join(ROOT, 'extracted', 'mk_us')
PALETTE_AT = 0x1C110                       # PAC.PRG: Goro's colours (Shang's: $1C130, mkshangmoves)
FLOOR = 108                                # EMP frames: y offset + height = 108 at his feet
BODY = list(range(1, 12)) + [19, 20, 21] + list(range(46, 56))   # his own poses (not the
                                           # skull, the morphs into others, the smoke)
SKULL = list(range(12, 19))                # the flaming skull: forming, flying
SMOKE = list(range(56, 61))                # the morph's smoke rings
ALL = BODY + SKULL + SMOKE
FX = ('skull', 'smoke')                    # kinds drawn centred on the EC pose (not on feet)
OWN = [1, 2, 3, 4, 5, 6, 7, 8, 11]         # palette line 2 (player 2's, his own) entries he may set:
                                           # 9, 10 are EC's blood reds, 12-15 the glow of each
                                           # special (its palettes change them)
FIXED = {}
SCALE = 1.08                               # as the other MK fighters (scorpion_full.SCALE)


def hw_rgb(w):
    return np.array([(w >> 1) & 7, (w >> 5) & 7, (w >> 9) & 7], float) * 36


def art():
    from mksch import FighterArt
    return FighterArt(open(os.path.join(MK, 'EMP.OBJ'), 'rb').read(), open(os.path.join(MK, 'EMP.SCH'), 'rb').read())


def frames(numbers=BODY):
    """{n: (indexed image, (anchor x, anchor y))}: anchor = his feet, centre."""
    from mksch import u16
    f = art()
    out = {}
    for n in numbers:
        at = f.records + u16(f.obj, f.frame_table + n * 2)
        xo, yo = (u16(f.obj, at + i) for i in (6, 8))
        xo, yo = (v - 65536 if v > 32767 else v for v in (xo, yo))
        out[n] = (f.frame(n), (-xo, FLOOR - yo))
    return out


def mk_palette():
    raw = open(os.path.join(MK, 'PAC.PRG'), 'rb').read()[PALETTE_AT:PALETTE_AT + 32]
    return [int.from_bytes(raw[i:i + 2], 'big') for i in range(0, 32, 2)]


def fit_palette(imgs):
    """(colour words for entries OWN, lut: MK index -> palette index).
    Each MK colour that is (near) a fixed one takes it; the rest are
    weighted by use and merged down to len(OWN) (closest pair first)."""
    mk = mk_palette()
    use = np.zeros(16)
    for im in imgs:
        use += np.bincount(im.ravel(), minlength=16)
    lut = np.zeros(16, np.uint8)
    free = []
    for i in range(1, 16):
        if not use[i]:
            continue
        rgb = hw_rgb(mk[i])
        best = min(FIXED, key=lambda k: ((hw_rgb(FIXED[k]) - rgb) ** 2).sum()) if FIXED else None
        if best is not None and ((hw_rgb(FIXED[best]) - rgb) ** 2).sum() <= 36 ** 2:
            lut[i] = best
        else:
            free.append([[i], rgb, use[i]])
    while len(free) > len(OWN):              # merge the two closest (use-weighted mean)
        a, b = min(((a, b) for a in range(len(free)) for b in range(a + 1, len(free))),
                   key=lambda p: ((free[p[0]][1] - free[p[1]][1]) ** 2).sum())
        A, B = free[a], free[b]
        w = A[2] + B[2]
        free[a] = [A[0] + B[0], (A[1] * A[2] + B[1] * B[2]) / w, w]
        del free[b]
    words = []
    for slot, (members, rgb, _) in zip(OWN, free):
        r, g, b = (int(round(v / 36)) for v in rgb)
        words.append((b << 9) | (g << 5) | (r << 1))
        for i in members:
            lut[i] = slot
    words += [0] * (len(OWN) - len(words))
    return words, lut


def line1(words):
    """RGB of his palette line as Shang is drawn (entries OWN his)."""
    pal = np.zeros((16, 3), np.uint8)
    for k, w in zip(OWN, words):
        pal[k] = hw_rgb(w)
    for k, w in FIXED.items():
        pal[k] = hw_rgb(w)
    return pal


def scaled(img, anchor, scale=SCALE):
    """Nearest-neighbour resize about the anchor (index art: no new colours)."""
    from PIL import Image
    h, w = img.shape
    W, H = round(w * scale), round(h * scale)
    out = np.asarray(Image.fromarray(img).resize((W, H), Image.NEAREST))
    return out, (round(anchor[0] * scale), round(anchor[1] * scale))


def silhouette(img, anchor, box=(-96, -160, 96, 16)):
    """Bool mask in a fixed window around the anchor (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = box
    m = np.zeros((y1 - y0, x1 - x0), bool)
    ys, xs = np.nonzero(img)
    X, Y = xs - anchor[0] - x0, ys - anchor[1] - y0
    k = (X >= 0) & (X < x1 - x0) & (Y >= 0) & (Y < y1 - y0)
    m[Y[k], X[k]] = True
    return m


def iou(a, b):
    u = (a | b).sum()
    return (a & b).sum() / u if u else 0.0


def host_poses(pl_name):
    """{(sheet, frame): (indexed image, anchor)} for every pose of an EC .PL."""
    import plsheet
    pl = open(os.path.join(ROOT, 'extracted', 'ec_us', pl_name), 'rb').read()
    sub = open(os.path.join(ROOT, 'extracted', 'ec_us', 'SUB.BIN'), 'rb').read()
    out = {}
    for sh in body_sheets(pl, pl_name):
        sid = sh['sid']
        for f in range(sh['n']):
            try:
                img = (plsheet.render(pl, sub, sh['res'], sh['sheet'], f, sid, raw=True) if sh['kind'] == 'packed'
                       else plsheet.render_raw(pl, sh, f, raw=True))
            except Exception:                       # noqa: BLE001  (an empty frame)
                img = np.zeros((256, 256), np.uint8)
            out[(sid, f)] = (img, (128, 200))
    return out


# raw-tile sheets that are his body (the rest of the raw sheets are effects:
# slashes, sparks, smoke, the windows' creatures, kept)
RAW_BODY = {'ECX.PL': (0x9F,)}       # the second form's whole fighting moveset


def body_sheets(pl, pl_name):
    import plsheet
    return [sh for sh in plsheet.all_sheets(pl) if sh['kind'] == 'packed' or sh['sid'] in RAW_BODY.get(pl_name, ())]


def match(host, shang):
    """{(sheet, frame): Shang frame} by outline overlap; an empty host pose: None."""
    sil = {n: silhouette(*scaled(*shang[n])) for n in shang}
    out = {}
    for key, (img, anchor) in host.items():
        if not img.any():
            out[key] = None
            continue
        h = silhouette(img, anchor)
        out[key] = max(sil, key=lambda n: iou(h, sil[n]))
    return out


# Shang's poses by what they show (tools/lib/mkshang.py sheet): an EC pose of a kind
# gets these in order, along a run of consecutive frames of that kind
KINDS = {'stance': [1, 2, 3, 4, 5, 6], 'attack': [7, 8, 10], 'cast': [7, 8, 9, 10, 11],
         'raise': [19, 20, 21], 'crouch': [9], 'hit': [51, 52, 53, 54], 'air': [55, 46],
         'tumble': [46, 47], 'fall': [47, 48, 49], 'lying': [50],
         'skull': [12, 13, 14, 15, 16, 17, 18], 'smoke': [56, 57, 58, 59, 60]}


def _ranges(sheet, *spans):
    return {(sheet, f): k for k, a, b in spans for f in range(a, b + 1)}


# what the outline can't tell (from tools/lib/plsheet.py's sheets): jumps are drawn
# feet on the frame's floor (the object rises), the stance sway leans, the
# spins in a ring of energy are knock-backs, not lying
OVERRIDES = {
    'ECH.PL': {**_ranges(0x9B, ('stance', 0, 11), ('stance', 105, 108), ('stance', 112, 112),
                         ('stance', 134, 140), ('stance', 180, 183), ('stance', 187, 190),
                         ('stance', 249, 252)),
               **_ranges(0x9C, ('stance', 0, 1), ('air', 2, 32), ('tumble', 33, 40), ('hit', 41, 41),
                         ('fall', 42, 48), ('raise', 49, 58), ('cast', 59, 63), ('tumble', 64, 71),
                         ('lying', 72, 73), ('stance', 74, 78), ('raise', 79, 83), ('cast', 84, 100),
                         ('stance', 101, 102), ('lying', 103, 107), ('stance', 108, 111))},
    # the second form floats (sits in the air), throws fire, turns to a smoke serpent
    'ECX.PL': {**_ranges(0x9D, ('stance', 0, 36), ('stance', 41, 41), ('tumble', 42, 42), ('cast', 59, 63),
                         ('skull', 64, 73), ('stance', 74, 93), ('cast', 94, 100), ('stance', 101, 111),
                         ('fall', 112, 115), ('lying', 116, 116), ('stance', 117, 119)),
               **_ranges(0x9E, ('smoke', 0, 26), ('raise', 27, 48), ('cast', 50, 68)),
               **_ranges(0xA0, ('hit', 41, 41), ('fall', 42, 44), ('lying', 45, 48), ('cast', 84, 93)),
               # its fighting moves (a raw sheet, laid out as the first form's $9B)
               **_ranges(0x9F, ('stance', 0, 11), ('stance', 64, 69), ('stance', 128, 133),
                         ('stance', 169, 178), ('stance', 240, 244))},
}


def measure(img, anchor):
    """(height above the feet, front reach, back reach, lowest pixel's height above the feet)."""
    ys, xs = np.nonzero(img)
    if not len(ys):
        return None
    return anchor[1] - ys.min(), xs.max() - anchor[0], anchor[0] - xs.min(), anchor[1] - 1 - ys.max()


def kind(m, stance, same):
    """What an EC pose shows, from its outline against the fighter's stance
    (same: how much of its outline is the stance's, 0-1)."""
    h, front, back, low = m
    sh, sf, sb, _ = stance
    if h < 50:
        return 'lying'
    if low > 18:
        return 'air' if h > 0.75 * sh else 'tumble'
    if h < 0.62 * sh:
        return 'crouch'                         # (a sweep: falls are labelled, OVERRIDES)
    if h < 0.85 * sh:
        return 'crouch'
    if h > sh + 14:
        return 'raise'
    return 'stance' if same >= STANCE_SAME else 'attack'


STANCE_SAME = 0.72


def assign(host, overrides=None):
    """{(sheet, frame): (kind, Shang frame)} along each sheet's frame order."""
    out, run = {}, []
    keys = sorted(host)
    stance = measure(*host[keys[0]])
    stance_sil = silhouette(*host[keys[0]])

    def flush():
        if not run:
            return
        k = run[0][1]
        seq = KINDS[k]
        for i, (key, _) in enumerate(run):
            n = seq[i % len(seq)] if k == 'stance' else seq[min(len(seq) - 1, i * len(seq) // len(run))]
            out[key] = (k, n)
        run.clear()
    prev = None
    for key in keys:
        m = measure(*host[key])
        if m is None:
            flush()
            out[key] = (None, None)
            prev = None
            continue
        k = (overrides or {}).get(key) or kind(m, stance, iou(silhouette(*host[key]), stance_sil))
        if run and (k != run[-1][1] or key[0] != run[-1][0][0]):
            flush()
        run.append((key, k))
    flush()
    return out


MAX_PL = 188416                            # player 2's room (scorpion_full.MAX_PL: ECX.PL's own footprint)


def pose(img, anchor, lut, host=None):
    """A Shang image in line-1 colours, scaled, on a canvas with room around
    it: (full image, anchor). host = (EC pose, its anchor) for an effect
    (skull, smoke): drawn centred where the EC pose's outline is."""
    full, (ax, ay) = scaled(lut[img], anchor)
    if host is not None:
        ys, xs = np.nonzero(full)
        hy, hx = np.nonzero(host[0])
        ax = round((xs.min() + xs.max()) / 2 - ((hx.min() + hx.max()) / 2 - host[1][0]))
        ay = round((ys.min() + ys.max()) / 2 - ((hy.min() + hy.max()) / 2 - host[1][1]))
    pad = 256
    out = np.zeros((full.shape[0] + 2 * pad, full.shape[1] + 2 * pad), np.uint8)
    out[pad:pad + full.shape[0], pad:pad + full.shape[1]] = full
    return out, (ax + pad, ay + pad)


def build_pl(pl, assignment, shang, lut, host, pl_name):
    """pl (an EC .PL, bytes) with every body pose's art replaced: assignment
    {(sheet, frame): (kind, Shang frame or None)}. Packed sheets: the art
    region (the shared bank section up to the first sheet chunk) is rewritten
    as scorpion_full does Blade's. Raw sheets (RAW_BODY): their tile source
    holds the Shang poses' tiles one after another, each piece's attribute
    word its first tile's number. Each frame keeps its collision boxes (the
    boss's reach and body as EC balanced them). Returns (bytes, report)."""
    import ecpl, ecpl2
    import scorpion_full as sf
    L = lambda o: int.from_bytes(pl[o:o + 4], 'big')
    W = lambda o: int.from_bytes(pl[o:o + 2], 'big')
    pl = bytearray(pl)
    sheets = body_sheets(pl, pl_name)
    packed = [sh for sh in sheets if sh['kind'] == 'packed']
    res0 = min(sh['res'] for sh in packed)
    A5, END = res0 + L(res0), L(0)
    for sh in packed:
        assert (sh['res'] + L(sh['res'])) & 0xFFFFFFFF == A5, (hex(sh['sid']), 'resources share one bank section')
    sf.CFG.update(colour_moves={}, colour_map={})
    cut, chosen = {None: ([], [])}, {}
    for key, (k, n) in assignment.items():
        if n is None:
            chosen[key] = None
            continue
        full, anc = pose(*shang[n], lut, host[key] if k in FX else None)
        ck = (n, anc if k in FX else None)
        if ck not in cut:
            cut[ck] = sf.pose_pieces(full, anc)
        chosen[key] = ck
    order_key = lambda g: (g[0], g[1] or (0, 0))
    report = {'poses': len(cut) - 1}

    # --- packed: banks of the poses the packed sheets show
    used = sorted({chosen.get((sh['sid'], f)) for sh in packed for f in range(sh['n'])} - {None}, key=order_key)
    banks, placed, group = [], {None: None}, []

    def flush(group):
        frames_ = [ecpl.words(cut[g][1]) for g in group]
        data, offs = ecpl2.encode_bank(frames_)
        assert len(data) <= 0x8000
        sf.check_bank(data, offs, frames_)
        for g, o in zip(group, offs):
            placed[g] = (len(banks), o)
        banks.append(data)
    est = 512
    for g in [None] + used:
        size = len(cut[g][1]) * 32 * 0.65 + 64
        if group and est + size > 30000:
            flush(group)
            group, est = [], 512
        group.append(g)
        est += size
    flush(group)
    head = 2 + 4 * len(banks)
    sec, body = bytearray(head.to_bytes(2, 'big')), bytearray()
    for data in banks:
        if (head + len(body)) % 2:
            body.append(0)
        sec += (head + len(body)).to_bytes(4, 'big')
        body += data
    blob = sec + body
    room = END - A5
    grow = max(0, (len(blob) - room + 1) & ~1)
    pl[A5:A5 + min(len(blob), room)] = blob[:room]
    if not grow:
        pl[A5 + len(blob):END] = bytes(room - len(blob))
    report.update(banks=len(banks), bytes=len(blob), room=room)

    # --- new records: (offset of what changes, old length, new bytes, fix) per chunk
    edits = []
    for sh in sheets:
        sid, sheet, nframes = sh['sid'], sh['sheet'], sh['n']
        offsets = [W(sheet + 6 + 2 * i) for i in range(nframes)]
        assigned, recs = {}, {}
        if sh['kind'] == 'raw':
            poses = sorted({chosen.get((sid, f)) for f in range(nframes)} - {None}, key=order_key)
            base, tiles = {}, bytearray()
            for g in poses:
                base[g] = len(tiles) // 32
                tiles += b''.join(cut[g][1])
            assert len(tiles) // 32 <= 0x800, f'sheet ${sid:X}: {len(tiles) // 32} tiles (11-bit numbers)'
            report[f'raw_{sid:X}'] = (len(poses), len(tiles) // 32, sh['ntiles'])
        for f in range(nframes):
            o = offsets[f]
            g = assigned.setdefault(o, chosen.get((sid, f)))     # frames sharing a record share a pose
            if sh['kind'] == 'packed':
                b, (lo, oo) = placed[g] or placed[None]
                r = sh['res'] + 4 + 6 * f
                pl[r:r + 6] = bytes([b, 0]) + lo.to_bytes(2, 'big') + oo.to_bytes(2, 'big')
            if o in recs:
                continue
            q0 = q = sheet + 6 + o
            q += 2 + 4 * W(q)
            q += 2 + 2 * W(q)
            ps = cut[g][0]
            if sh['kind'] == 'raw':
                rec, t = bytearray(), base.get(g, 0)
                for p in ps:
                    rec += ecpl.piece_record([p], attr=0x6000 | t)
                    t += p['w'] * p['h']
            else:
                rec = ecpl.piece_record(ps)
            recs[o] = bytes(pl[q0:q]) + bytes(rec) + b'\x80\x00'
        new_at, body_ = {}, bytearray()
        for o in sorted(recs):
            new_at[o] = 2 * nframes + len(body_)
            body_ += recs[o]
            if len(body_) % 2:
                body_.append(0)
        table = b''.join(new_at[o].to_bytes(2, 'big') for o in offsets)
        assert 2 * nframes + len(body_) < 0x10000
        chunk = sh['chunk']
        new_chunk = bytearray(pl[chunk:sheet + 6]) + table + body_
        new_chunk[0:4] = len(new_chunk).to_bytes(4, 'big')
        edits.append((chunk, bytes(new_chunk)))
        if sh['kind'] == 'raw':                       # its tile source: the new tiles
            s0 = sh['src']
            hdr = bytearray(pl[s0:sh['tiles']])
            hdr[0:4] = (len(hdr) + len(tiles)).to_bytes(4, 'big')
            hdr[0x12:0x14] = len(tiles).to_bytes(2, 'big')
            edits.append((s0, bytes(hdr) + bytes(tiles)))
    for chunk, data in sorted(edits, reverse=True):   # last chunk first: earlier ones stay put
        old_len = L(chunk)
        pl[chunk:chunk + old_len] = data
        sf.shift_after(pl, chunk, len(data) - old_len)
    if len(pl) + grow > MAX_PL:
        raise ValueError(f'Shang\'s art: the .PL would be {len(pl) + grow} bytes, over {MAX_PL}')
    if grow:
        saved = sf.A5, sf.REGION_END
        sf.A5, sf.REGION_END = A5, END
        try:
            pl = bytearray(sf.splice(pl, blob, grow))
        finally:
            sf.A5, sf.REGION_END = saved
    report['grow'] = grow
    report['size'] = len(pl)
    return bytes(pl), report


def build(pl_name, pl=None):
    """(new .PL bytes, line-1 words for entries OWN, report) for ECH.PL or ECX.PL."""
    shang = frames(ALL)
    words, lut = fit_palette([im for im, _ in shang.values()])
    host = host_poses(pl_name)
    asg = assign(host, OVERRIDES.get(pl_name))
    if pl is None:
        pl = open(os.path.join(ROOT, 'extracted', 'ec_us', pl_name), 'rb').read()
    data, rep = build_pl(pl, asg, shang, lut, host, pl_name)
    return data, words, rep


def main():
    import argparse
    from PIL import Image, ImageDraw
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=('sheet', 'match'))
    ap.add_argument('args', nargs='+')
    a = ap.parse_args()
    shang = frames(ALL)
    words, lut = fit_palette([im for im, _ in shang.values()])
    pal = line1(words)
    if a.cmd == 'sheet':
        out = Image.new('RGB', (len(shang) * 70, 150), (40, 40, 40))
        for i, (n, (im, anc)) in enumerate(shang.items()):
            rgb = pal[lut[im]]
            rgb[im == 0] = (40, 40, 40)
            p = Image.fromarray(rgb)
            p.thumbnail((68, 130))
            out.paste(p, (i * 70, 18))
            ImageDraw.Draw(out).text((i * 70 + 2, 2), str(n), fill=(255, 255, 255))
        out.save(a.args[0])
        print('line 1 entries 1-8:', ' '.join(f'{w:04x}' for w in words), '->', a.args[0])
        return
    host_pl, dst = a.args
    host = host_poses(host_pl)
    asg = assign(host, OVERRIDES.get(host_pl))
    m = {k: v[1] for k, v in asg.items()}
    kinds = {k: v[0] for k, v in asg.items()}
    keys = list(host)
    cols = 12
    out = Image.new('RGB', (cols * 140, ((len(keys) + cols - 1) // cols) * 120), (30, 30, 30))
    d = ImageDraw.Draw(out)
    for i, k in enumerate(keys):
        x, y = (i % cols) * 140, (i // cols) * 120
        img = host[k][0]
        ys, xs = np.nonzero(img)
        if len(ys):
            g = Image.fromarray((img[ys.min():ys.max() + 1, xs.min():xs.max() + 1] > 0).astype(np.uint8) * 200)
            g.thumbnail((66, 100))
            out.paste(g, (x + 2, y + 16))
        if m[k] is not None:
            im = shang[m[k]][0]
            rgb = pal[lut[im]]
            rgb[im == 0] = (30, 30, 30)
            p = Image.fromarray(rgb)
            p.thumbnail((66, 100))
            out.paste(p, (x + 70, y + 16))
        d.text((x + 2, y + 2), f'{k[0]:02X}:{k[1]} {kinds[k]} {m[k]}', fill=(255, 255, 0))
    out.save(dst)
    json.dump({f'{k[0]:02X}:{k[1]}': v for k, v in m.items()}, open(os.path.splitext(dst)[0] + '.json', 'w'))
    print(f'{len(keys)} poses -> {dst}')


if __name__ == '__main__':
    main()
