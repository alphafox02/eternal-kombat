#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""An MK fighter's EC death art: a Z<xx>.BIN in EC's layout, drawn from MK.

EC's stage Sudden Deaths (the Chicago Theater's usher, ...) and some Vendettas
load the loser's Z<xx>.BIN by slot (docs/notes/2026-11.md "EC's own headless
deaths") and show frames of its two sheets by number. An MK fighter's slot
loads its EC owner's file (Scorpion in the Senator's slot: ZSN.BIN), so that file is
rebuilt here with HIS art in the same frame slots, under the same source and
sheet ids: EC's code uses it unchanged.

  sheet 1 ($100 + n, 18 frames): 0-2 lying on his back (the usher's victim),
      3-5 the same without the head; 6 the severed head, 7 it rolled over;
      8 the body arched in the air; 9 and 12-15 draped over (stages hang him
      on things); 10 the legs, 11 and 16 the upper body (torn in half); 17 none.
  sheet 2 ($112 + n, 27 frames): 0 none; 1-12 HEADLESS: standing (1-6),
      kneeling (7), falling forward (8), lying face down (9-12); 13 none;
      14-25 the same with the head; 26 none. Each has one point: the neck.

His art, all MK's own (the user's MK disc):
  - Sub-Zero's spine rip on him (tools/capture/mkvictim.py): MK's headless body as it
    stands, drops to its knees and falls flat; the severed head in Sub-Zero's
    hand; before the rip, his dazed stance (the with-head standing frames);
  - his knockdown (tools/lib/mkmoves.py): flat on his back, in the air.
The with-head kneeling / falling / lying frames have his standing head put
back on the neck (MK has no such poses).

Frames face right (EC's), at EC's scale for him (scorpion_full.SCALE), in his
EC palette (scorpion_full.remap_colours), placed over the EC owner's frames
(same bounding box edge per frame, so EC's per-victim offsets still fit).

    mkdeath.py FIGHTER     -> build/shots/mk_deaths/<who>_<sheet>.png (a FILES key: scorpion, raiden, ...)
"""
import json, os, sys
from contextlib import contextmanager
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from inputs import ROOT

# fighter -> (EC file whose layout and ids it takes, the disc file it's written to,
# extra sheet ids it also answers to: {sheet: [ids]}).
# Scorpion's and Raiden's slots load their EC owners' Z files (the Senator 22 ->
# ZSN, Chin Wo 19 -> ZCH). Scorpion's is laid out as Blast's (ZBS: his art was
# drawn to it; patches.mk_death_art gives every MK slot Blast's per-victim rows)
# and also answers to the Senator's sheet numbers. Johnny's (Zuni 18) and
# Sub-Zero's (Yappy 20) load files shared with others (ZEX, ZCH) and are given
# sheets $100 / $109 / $112 (EC's 'no art of his own'): they get files of their
# own instead - the Senator's and Chin Wo's Vendetta data, never loaded now
# (only their own modules loaded them; no MK fighter has a Vendetta move) -
# answering to those numbers and to Blast's ($110 / $121, Blast's rows).
FILES = {'scorpion': ('ZBS', 'ZSN.BIN', {0: [0x10F], 1: [0x120]}),
         'raiden': ('ZCH', 'ZCH.BIN', {}),
         'johnny': ('ZBS', 'SEN.VD', {0: [0x100, 0x109], 1: [0x112]}),
         'subzero': ('ZBS', 'CHW.VD', {0: [0x100, 0x109], 1: [0x112]}),
         # Liu Kang (the chicken's slot) and Kano (the snake's) load ZEC (Eternal's);
         # their files: the Senator's and Chin Wo's Vendetta code (never loaded now either)
         'liukang': ('ZBS', 'SEN.VC', {0: [0x100, 0x109], 1: [0x112]}),
         'kano': ('ZBS', 'CHW.VC', {0: [0x100, 0x109], 1: [0x112]}),
         # Sonya (the owl's slot) loads ZEX (Exodus's): hers is the Senator's old stage
         # object data, never loaded now (his stage is the Pit; CHA/ECX's #$79 is no load)
         'sonya': ('ZBS', 'SEN1.OD', {0: [0x100, 0x109], 1: [0x112]})}
FILE_IDS = {'ZSN.BIN': 0xFB, 'ZCH.BIN': 0xF9, 'SEN.VD': 0xDB, 'CHW.VD': 0xE7, 'SEN.VC': 0xDA, 'CHW.VC': 0xE6,
            'SEN1.OD': 0x79}   # EC's file ids (SUB.BIN's name list order)
SHEET2 = {'ZBS': 0x121, 'ZCH': 0x11E}   # the template's sheet 2 number: what the file answers to
SHEET1 = {'ZBS': 0x110, 'ZCH': 0x10D}   # its sheet 1 (the air pose, lying on the back, the head)


def spine_rip_entries():
    """{fighter id: (file id, sheet 2 number, sheet 1 number)} for Sub-Zero's spine
    rip on an MK loser (mkinputs.szf_tail), in FILES order (his head = mkinputs.Z_NAMES + k)."""
    return {spec_of(w).host_id: (FILE_IDS[f[1]], SHEET2[f[0]], SHEET1[f[0]]) for w, f in FILES.items()}


def art_ids():
    """Fighter ids ($4C) whose slot's Z file holds their MK death art."""
    return {spec_of(w).host_id for w in FILES}


HEAD_SLACK = 3               # px below the dazed-minus-headless height difference: the whole head


def spec_of(who):
    import patches
    return {sp.key: sp for sp in patches.MK_SPECS}[who]


# ---------------------------------------------------------------- EC template

W16 = lambda b, o: int.from_bytes(b[o:o + 2], 'big')
S8 = lambda v: v - 256 if v > 127 else v


def template(name):
    """The EC file's chunks: [(kind, header bytes, body)] and its sheets' frames."""
    from mkprojectile import chunks
    from ecdeath import frames
    b = open(os.path.join(ROOT, 'extracted', 'ec_us', name + '.BIN'), 'rb').read()
    out, srcs = [], {}
    for o, ln, t in chunks(b):
        out.append((t, b[o:o + 22], b[o:o + ln]))
        if t == 0:
            srcs[W16(b, o + 10) // 4] = b[o + 20:o + ln]
    sheets = []
    for t, hdr, ch in out:
        if t != 4:
            continue
        n = W16(ch, 20)
        imgs = frames(srcs[W16(ch, 12)], ch)
        recs = []
        for k in range(n):
            o = 22 + W16(ch, 22 + 2 * k)
            na = W16(ch, o)
            boxes = ch[o + 2:o + 2 + 4 * na]
            nb = W16(ch, o + 2 + 4 * na)
            pts = [(S8(ch[o + 4 + 4 * na + 2 * i]), S8(ch[o + 5 + 4 * na + 2 * i])) for i in range(nb)]
            m = imgs[k] > 0
            if m.any():
                ys, xs = np.nonzero(m)
                bbox = (xs.min() - 128, ys.min() - 128, xs.max() - 128 + 1, ys.max() - 128 + 1)
            else:
                bbox = None
            recs.append(dict(boxes=boxes, points=pts, bbox=bbox))
        sheets.append(dict(hdr=ch[:20], sid=W16(ch, 10) // 4, src=W16(ch, 12), frames=recs))
    return out, sheets


# ---------------------------------------------------------------- MK poses

def _load(d, name):
    p = np.load(os.path.join(d, name, 'indexed.npy'))
    a = json.load(open(os.path.join(d, name, 'anchors.json')))
    return p, a


def split_head_blob(f, cx):
    """(body, held head) of a spine-rip victim frame: the head is the blob
    Sub-Zero holds up, wholly above the body (the biggest blob)."""
    from scipy import ndimage
    lab, n = ndimage.label(f > 0, structure=np.ones((3, 3)))
    if n == 0:
        return f, np.zeros_like(f)
    sizes = ndimage.sum(f > 0, lab, range(1, n + 1))
    big = lab == (np.argmax(sizes) + 1)
    top = np.nonzero(big.any(1))[0].min()
    body, head = np.zeros_like(f), np.zeros_like(f)
    for k in range(1, n + 1):
        m = lab == k
        ys = np.nonzero(m.any(1))[0]
        if sizes[k - 1] > 60 and ys.max() < top - 2:
            head[m] = f[m]
        else:
            body[m] = f[m]
    return body, head


def victim_phases(d):
    """The spine rip's victim poses by phase (capture order, facing left):
    {'dazed': [...], 'stand': [...], 'kneel': [...], 'fall': [...], 'lying': [...]}
    of (body image, floor y, x where he stood); and his held head (image)."""
    p, a = _load(d, 'spinerip_victim')
    cx, fy = a[0]
    out = {k: [] for k in ('dazed', 'stand', 'kneel', 'fall', 'lying')}
    seen, held, ripped = set(), None, False
    for f in p:
        body, head = split_head_blob(f, cx)
        if head.any():
            held = head
            ripped = True                        # (the head in his hand: past the rip, lifted or not)
        ys, xs = np.nonzero(body)
        top, bot = ys.min() - fy, ys.max() - fy
        if bot > 3:                              # lifted by the spine: the rip itself
            ripped = True
            continue
        crop = body[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        key = crop.tobytes()
        if key in seen:
            continue
        seen.add(key)
        h = -top
        if not ripped:
            phase = 'dazed'
        elif h >= 70:
            phase = 'stand'
        elif h >= 48:
            phase = 'kneel'
        elif h >= 28:
            phase = 'fall'
        else:
            phase = 'lying'
        out[phase].append(body)
    return out, held, (cx, fy)


def knockdown_poses(d):
    """(flat on his back, the widest pose in the air) from his knockdown capture."""
    p, a = _load(d, 'knockdown')
    flat = air = None
    for f in p:
        ys, xs = np.nonzero(f)
        if not len(ys) or ys.min() < 4:          # flown off the top of the capture
            continue
        h, w = ys.max() - ys.min(), xs.max() - xs.min()
        if h < 26 and w > 60 and (flat is None or w > flat[1]):
            flat = (f, w)
        if ys.max() < a[0][1] - 24 and (air is None or w > air[1]):
            air = (f, w)
    return (flat[0] if flat else None), air[0]


# ---------------------------------------------------------------- art

def bbox(m):
    ys, xs = np.nonzero(m)
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


def crop(f):
    x0, y0, x1, y1 = bbox(f > 0)
    return f[y0:y1, x0:x1]


def scaled(f, cram):
    """MK px -> EC px (scorpion_full.SCALE), his EC palette, cropped to the art."""
    import scorpion_full
    x0, y0, x1, y1 = bbox(f > 0)
    out, _ = scorpion_full.scale_pose(f, ((x0 + x1) // 2, y1), cram)
    return crop(scorpion_full.remap_colours(out))


def rotate(img, deg):
    """Nearest-neighbour rotation (indexed), canvas grown to fit."""
    from PIL import Image
    return crop(np.asarray(Image.fromarray(img).rotate(deg, resample=Image.NEAREST, expand=True)))


def paste(dst, src, x, y):
    """src onto dst (both indexed), src's top-left at (x, y); dst grows as needed.
    Returns (image, (dx, dy)): how far dst's old pixels moved."""
    h, w = src.shape
    H, W = dst.shape
    ox, oy = max(0, -x), max(0, -y)
    out = np.zeros((max(H + oy, y + oy + h), max(W + ox, x + ox + w)), np.uint8)
    out[oy:oy + H, ox:ox + W] = dst
    reg = out[y + oy:y + oy + h, x + ox:x + ox + w]
    reg[src > 0] = src[src > 0]
    return out, (ox, oy)


def neck_of(img, kind):
    """Where the head goes on a headless body (img faces right)."""
    m = img > 0
    ys, xs = np.nonzero(m)
    if kind == 'lying':                          # head end: the right, its upper half
        x = xs.max()
        col = ys[xs >= x - 3]
        return x, int(np.median(col))
    if kind == 'fall':                           # leaning forward: up and right
        k = np.argmax(xs - ys)
        return xs[k] - 2, ys[k] + 2
    top = ys.min()                               # upright: the top of the stump
    return int(np.median(xs[ys <= top + 2])), top


def with_head(body, head, kind):
    """body + head on its neck: upright for kneeling, tipped forward for
    falling, pointing right (face down) for lying."""
    deg = {'kneel': 0, 'fall': -45, 'lying': -90}[kind]
    nx, ny = neck_of(body, kind)
    h = head if not deg else rotate(head, deg)
    hh, hw = h.shape
    if kind == 'lying':
        x, y = nx - 2, ny - hh // 2
    elif kind == 'fall':
        x, y = nx - hw // 3, ny - hh + hh // 4
    else:
        x, y = nx - hw // 2, ny - hh + 2
    out, (dx, dy) = paste(np.zeros_like(body), h, x, y)
    out2, (ex, ey) = paste(out, body, dx, dy)         # the body over the head's neck end
    return out2


FOLD = 65                     # degrees each half of the draped body hangs below level


def fold(lying):
    """The face-down body (head right) draped over something at the waist:
    head and arms hanging down on the left, legs down on the right, the waist
    at the frame's origin (EC's draped frames). -> ((image, ('at', x, y), None),
    the legs alone, the upper body alone)."""
    from PIL import Image
    body = lying[:, ::-1]                         # head on the left
    h, w = body.shape
    wx = int(w * 0.48)                            # the waist (head + torso ~ half the length)
    cols = np.nonzero(body[:, wx])[0]
    wy = int(cols.min()) if len(cols) else 0      # its top: the edge it hangs over
    S = 3 * max(h, w)
    parts = []
    for side, deg in (('upper', FOLD), ('legs', -FOLD)):
        c = np.zeros((S, S), np.uint8)
        part = body.copy()
        if side == 'upper':
            part[:, wx:] = 0
        else:
            part[:, :wx] = 0
        c[S // 2 - wy:S // 2 - wy + h, S // 2 - wx:S // 2 - wx + w] = part
        parts.append(np.asarray(Image.fromarray(c).rotate(deg, resample=Image.NEAREST, center=(S // 2, S // 2))))
    both = np.where(parts[0] > 0, parts[0], parts[1])
    x0, y0, x1, y1 = bbox(both > 0)
    return ((both[y0:y1, x0:x1], ('at', S // 2 - x0, S // 2 - y0), None), crop(parts[1]), crop(parts[0]))


DRAPE_FIRST = ('mk_moves_kano', 'mk_moves_raiden')   # their kick reaction's 2nd pose leaves the floor
                                                    # (Kano tumbles, Raiden flips): the 1st is bent over


def doubled_over(d, cram):
    """MK's kick reaction doubled over (the hit_kick capture: of the poses after the hit lands, feet on
    the floor and the head lowest - jack-knifed at the waist, as EC's draped frames 9, 12-15 hang),
    facing right, the waist (the top of his back) at the origin. A folded lying body made a squat
    shape instead (seen in Ramses' Vendetta on Sonya)."""
    import scorpion_full
    if not os.path.exists(os.path.join(d, 'hit_kick', 'indexed.npy')):
        return None
    P = np.load(os.path.join(d, 'hit_kick', 'indexed.npy'), mmap_mode='r')
    order = [int(v) for v in open(os.path.join(d, 'hit_kick', 'order.txt')).read().split()]
    first = {}
    for t, k in enumerate(order):
        first.setdefault(k, t)
    react = [k for k in sorted(first, key=first.get) if first[k] >= scorpion_full.HIT_LANDS and P[k].any()][:2]
    if not react:                                     # (the reaction's first two poses: the hit, then
        return None                                   #  doubled over - before the flight and the fall)
    if os.path.basename(d) in DRAPE_FIRST:
        react = react[:1]
    k = max(react, key=lambda k: int(np.nonzero(P[k].any(1))[0].min()))
    img = scaled(np.ascontiguousarray(P[k][:, ::-1]), cram)
    top = np.nonzero(img[:3].any(0))[0]
    return (img, ('at', int(round(top.mean())), 0), None)


@contextmanager
def as_fighter(who):
    """patches' fighter settings (his colours, scale) switched to him, and back."""
    import patches
    old = patches.SPEC
    patches.use(spec_of(who))
    try:
        yield spec_of(who)
    finally:
        patches.use(old)


def held_head(who):
    """MK's own art of his severed head, as Sub-Zero holds it up (his EC
    colours, facing right): mkinputs' spine rip shows it on MK losers."""
    with as_fighter(who) as spec:
        d = os.path.join(ROOT, 'extracted', spec.mk_dir)
        cram = json.load(open(os.path.join(d, 'idle', 'cram.json')))
        held = victim_phases(d)[1]
        return scaled(held[:, ::-1], cram)


def build_art(who):
    """{(sheet index, frame): (image facing right, align, neck point or None)}."""
    with as_fighter(who):
        return _build_art(who)


def _build_art(who):
    import scorpion_full
    spec = spec_of(who)
    d = os.path.join(ROOT, 'extracted', spec.mk_dir)
    cram = json.load(open(os.path.join(d, 'idle', 'cram.json')))
    ph, held, (cx, fy) = victim_phases(d)
    S = lambda f: scaled(f[:, ::-1], cram)            # MK capture -> EC, facing right
    dazed = [S(f) for f in ph['dazed']]
    stand = [S(f) for f in ph['stand']]
    kneel = [S(f) for f in ph['kneel']]
    fall = [S(f) for f in ph['fall']] or kneel[-1:]   # (Raiden goes from his knees straight down)
    lying = [S(f) for f in ph['lying']]
    # his head: the dazed stance above the headless body's height
    hh = (dazed[0].shape[0] - stand[0].shape[0]) + HEAD_SLACK
    head = crop(dazed[0][:hh])
    held_head = S(held)
    flat, air = knockdown_poses(d)
    air = scaled(air, cram)                           # (his own capture: already facing right)
    blood = sorted(getattr(spec, 'blood_moves', scorpion_full.COLOUR_MOVES)) if spec.blood else []

    pick = lambda xs, n: [xs[min(len(xs) - 1, round(i * (len(xs) - 1) / max(1, n - 1)))] for i in range(n)]
    art = {}
    # sheet 2: headless 1-12, with head 14-25
    seq = [(f, 'stand') for f in pick(stand, 6)] + [(pick(kneel, 1)[0], 'kneel'), (fall[-1], 'fall')] \
        + [(f, 'lying') for f in pick(lying, 4)]
    for i, (f, kind) in enumerate(seq):
        nx, ny = neck_of(f, 'lying' if kind == 'lying' else ('fall' if kind == 'fall' else 'stand'))
        art[(1, 1 + i)] = (f, 'right' if kind == 'lying' else 'feet', (nx, ny))
        if kind == 'stand':
            g = pick(dazed, 6)[i]
            art[(1, 14 + i)] = (g, 'feet', None)
        else:
            art[(1, 14 + i)] = (with_head(f, head, kind), 'right' if kind == 'lying' else 'feet', None)
    # sheet 1: the usher's victim on his back, head at the left
    hw = head.shape[0]
    if flat is None:                                  # (Johnny never lies still: he rolls back up)
        flat = art[(1, 22)][0][:, ::-1]               #  his face-down body, head on the left
    else:
        flat = scaled(flat, cram)
    art[(0, 0)] = art[(0, 1)] = art[(0, 2)] = (flat, 'left', None)
    cut = flat.copy()
    cut[:, :hw] = 0
    if blood:                                         # the stump
        ys = np.nonzero(cut[:, hw:hw + 3].any(1))[0]
        if len(ys):
            y0, y1 = ys.min(), ys.max() + 1
            cut[y0:y1, hw - 1:hw + 1] = blood[-1]
    art[(0, 3)] = art[(0, 4)] = art[(0, 5)] = (cut, 'left-of', (0, 0))   # placed as frames 0-2
    art[(0, 6)] = (held_head, 'feet', None)
    art[(0, 7)] = (rotate(held_head, 90), 'feet', None)
    art[(0, 8)] = (air, 'centre', None)
    drape, legs, upper = fold(art[(1, 22)][0])
    bent = doubled_over(d, cram)                      # EC's draped body hangs nearly straight down at
    for k in (9, 12, 13, 14, 15):                     #  both sides of the waist (Ramses' insect holds
        art[(0, k)] = bent or drape                   #  it in its jaws): MK's own doubled-over pose
    art[(0, 10)] = (legs, 'centre', None)
    art[(0, 11)] = art[(0, 16)] = (upper, 'centre', None)
    return art


# ---------------------------------------------------------------- the file

def place(img, align, ref):
    """Origin (ox, oy) in img so that img's box sits on the EC frame's box `ref`
    (x0, y0, x1, y1 from the origin): by feet (bottom centre), left or right
    end (and bottom), or centre."""
    h, w = img.shape
    x0, y0, x1, y1 = ref
    if align == 'feet':
        return w // 2 - (x0 + x1) // 2, h - y1
    if align == 'left':
        return -x0, h - y1
    if align == 'right':
        return w - x1, h - y1
    return w // 2 - (x0 + x1) // 2, h // 2 - (y0 + y1) // 2


def cut(img, ox, oy, tiles, index):
    """Pieces (<= 4x4 tiles) on the image's own 8 px grid; tiles shared
    through index (bytes -> tile number). Returns the piece list."""
    import ecpl
    H, W = img.shape
    th, tw = (H + 7) // 8, (W + 7) // 8
    pad = np.zeros((th * 8, tw * 8), np.uint8)
    pad[:H, :W] = img
    used = np.array([[pad[y * 8:y * 8 + 8, x * 8:x * 8 + 8].any() for x in range(tw)] for y in range(th)])
    pieces = []
    for gy in range(0, th, 4):
        for gx in range(0, tw, 4):
            sub = used[gy:gy + 4, gx:gx + 4]
            if not sub.any():
                continue
            ys, xs = np.nonzero(sub)
            tx0, tx1, ty0, ty1 = gx + xs.min(), gx + xs.max(), gy + ys.min(), gy + ys.max()
            w, h = tx1 - tx0 + 1, ty1 - ty0 + 1
            px, py = tx0 * 8 - ox, ty0 * 8 - oy
            if not (-128 <= px <= 127 and -128 <= py <= 127):
                continue                                  # (out of the format's reach)
            ts = ecpl.tiles_of(pad, tx0, ty0, w, h)
            # a piece's tiles must be consecutive in the source: share whole runs
            run = b''.join(ts)
            if run not in index:
                index[run] = len(tiles)
                tiles.extend(ts)
            pieces.append((int(w), int(h), int(px), int(py), index[run]))
    return pieces


def record(boxes, points, pieces):
    out = bytearray((len(boxes) // 4).to_bytes(2, 'big') + boxes)
    out += len(points).to_bytes(2, 'big')
    for x, y in points:
        out += bytes([x & 0xFF, y & 0xFF])
    for w, h, x, y, t in pieces:
        out += ((((w - 1) << 2 | (h - 1)) << 8) | 0x50).to_bytes(2, 'big')
        out += (0x6000 | t).to_bytes(2, 'big') + bytes([x & 0xFF, y & 0xFF])
    return bytes(out + b'\x80\x00')


def build(who):
    """The new Z file's bytes (and per-frame images for the contact sheet)."""
    tmpl, _, aliases = FILES[who]
    chunks_, sheets = template(tmpl)
    art = build_art(who)
    srcs_out, sheets_out, shown = [], [], {}
    for si, sh in enumerate(sheets):
        tiles, index, recs = [], {}, []
        for k, fr in enumerate(sh['frames']):
            a = art.get((si, k))
            if a is None or fr['bbox'] is None:
                recs.append(record(b'', fr['points'], []))
                continue
            img, align, neck = a
            if isinstance(align, tuple):              # ('at', x, y): the origin in the image
                ox, oy = align[1], align[2]
            elif align == 'left-of':                  # frames 3-5: exactly where 0-2 are
                ox, oy = place(art[(si, 0)][0], 'left', sh['frames'][0]['bbox'])
            else:
                ox, oy = place(img, align, fr['bbox'])
            pts = fr['points']
            if neck is not None and si == 1 and pts:
                pts = [(int(neck[0] - ox), int(neck[1] - oy))]
            pieces = cut(img, ox, oy, tiles, index)
            recs.append(record(b'', pts, pieces))
            shown[(si, k)] = (img, ox, oy)
        assert len(tiles) <= 0x7FF, f'{len(tiles)} tiles in one source'
        srcs_out.append(b''.join(tiles))
        sheets_out.append(recs)
    # chunks: source 1, sheet 1, source 2, sheet 2 (as EC's)
    out = bytearray()
    si = 0
    for t, hdr, ch in chunks_:
        if t == 0:
            data = srcs_out[si]
            off = len(out) + 20
            body = bytearray(ch[:20])
            body[0:4] = (20 + len(data)).to_bytes(4, 'big')
            body[14:18] = off.to_bytes(4, 'big')
            body[18:20] = len(data).to_bytes(2, 'big')
            assert len(data) < 0x10000
            out += body + data
        elif t == 4:
            recs = sheets_out[si]
            n = len(recs)
            offs, blob = [], bytearray()
            for r in recs:
                offs.append(2 * n + len(blob))
                blob += r
                if len(blob) & 1:
                    blob += b'\0'
            body = bytearray(sheets[si]['hdr'])
            body += n.to_bytes(2, 'big') + b''.join(o.to_bytes(2, 'big') for o in offs) + blob
            body[0:4] = len(body).to_bytes(4, 'big')
            out += body
            for sid in aliases.get(si, []):          # the same sheet under another number
                alias = bytearray(body)
                alias[10:12] = (4 * sid).to_bytes(2, 'big')
                out += alias
            si += 1
        else:
            out += ch
        if len(out) & 1:
            out += b'\0'
    return bytes(out), shown


def game_palette(spec):
    """His palette line as the game has it (patches.scorpion_palette): 9-bit BGR."""
    import scorpion_full
    c = list(json.load(open(os.path.join(ROOT, 'extracted', spec.mk_dir, 'idle', 'cram.json'))))
    for dst, src in getattr(spec, 'palette_set', {}).items():
        c[dst] = c[src]
    if spec.blood:
        for a, b in getattr(spec, 'blood_moves', scorpion_full.COLOUR_MOVES).items():
            c[b] = c[a]
        c[12], c[13] = 5, 7                       # dark red, red (as BLOOD's $00A / $00E)
    return c


def contact(who, shown):
    from PIL import Image
    spec = spec_of(who)
    pal = np.array([((c & 7) * 36, ((c >> 3) & 7) * 36, ((c >> 6) & 7) * 36) for c in game_palette(spec)], np.uint8)
    pal[0] = (40, 40, 60)
    os.makedirs(os.path.join(ROOT, 'build', 'shots', 'mk_deaths'), exist_ok=True)
    for si, n in ((0, 18), (1, 27)):
        o = Image.new('RGB', (6 * 200, ((n + 5) // 6) * 170), (20, 20, 20))
        for k in range(n):
            cell = np.zeros((170, 200, 3), np.uint8)
            cell[:] = (40, 40, 60)
            if (si, k) in shown:
                img, ox, oy = shown[(si, k)]
                X, Y = 100 - ox, 130 - oy
                h, w = img.shape
                for yy in range(h):
                    for xx in range(w):
                        if img[yy, xx] and 0 <= Y + yy < 170 and 0 <= X + xx < 200:
                            cell[Y + yy, X + xx] = pal[img[yy, xx]]
            cell[130, ::4] = (150, 0, 0)
            cell[::4, 100] = (150, 0, 0)
            o.paste(Image.fromarray(cell), ((k % 6) * 200, (k // 6) * 170))
        p = os.path.join(ROOT, 'build', 'shots', 'mk_deaths', f'{who}_{si + 1}.png')
        o.save(p)
        print(os.path.relpath(p, ROOT))


if __name__ == '__main__':
    who = sys.argv[1]
    data, shown = build(who)
    tmpl, out, _ = FILES[who]
    print(f'{who}: {out} {len(data)} bytes '
          f'(EC\'s {tmpl}.BIN {os.path.getsize(os.path.join(ROOT, "extracted", "ec_us", tmpl + ".BIN"))})')
    contact(who, shown)
