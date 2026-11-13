"""Rebuild all of Blade's compressed sprite art (BLA.PL sheets $40-$43) as
Scorpion, from MK poses captured by tools/mkmoves.py.

Blade's four type-$18 resources share one bank section at $2B8. Every bank
is replaced, so the whole region from $2B8 to the first sheet chunk is
rewritten: a new bank section (no shared sub-frames), then banks of at most
~30 KB (stream offsets are signed 16-bit), each with its own dictionary.
The file keeps its size, so it fits both player slots.
"""
import json, os
import numpy as np
import ecpl
import ecpl2
from scorpion_map import assignments

A5 = 0x2B8
REGION_END = 0x1D7E8            # next chunk (sheet $40) starts here: its length long must survive
RESOURCES = {0x40: (0x14, 0x1D7F8), 0x41: (0x206C0, 0x20926),
             0x42: (0x23CB8, 0x23E4C), 0x43: (0x25DFA, 0x25E7A)}
MAX_DX, MAX_UP = 120, 127


ANCHOR_JUMP, ANCHOR_AGREE = 25, 15
# MK doesn't move the fighter during these: the planted foot stays put in
# every capture (measured on Scorpion's and Johnny's), only head and limbs swing
KEEP_HEIGHT = {'torpedo'}    # Raiden flies head first ~45 px up (MK); pose 0 is his stance
IN_PLACE = {'btn_a', 'btn_b', 'btn_c', 'btn_x', 'btn_y', 'btn_z', 'roundhouse', 'uppercut',
            'crouch', 'crouch_a', 'crouch_b', 'crouch_c', 'crouch_x', 'crouch_y', 'crouch_z',
            'crouch_block', 'block', 'sweep', 'jump_up', 'jumpup_a', 'jumpup_c', 'jumpup_x',
            'jumpup_z', 'lightning', 'iceblast', 'greenbolt'}   # (projectiles: the bolt can sit above his head)


def steady_anchors(name, anchors):
    """mkmoves.anchor puts a pose's x at the centre of its top 12 rows (the
    head). That re-centres every pose on the head: MK's own lean was
    cancelled (Scorpion's jab: the head goes 26 px forward, so his fist fell
    26 px short of MK's), and in a high kick, where the foot is above the
    head, the body was drawn ~55 px back. MK's fighter doesn't move in the
    IN_PLACE actions: every pose there takes the first (stance) pose's x, as
    MK draws them. Elsewhere a pose whose x is ANCHOR_JUMP px off two
    neighbouring poses that agree with each other takes their x."""
    out = [list(a) for a in anchors]
    if name in KEEP_HEIGHT:                 # airborne poses: MK's height over his stance feet,
        for a in out:                       # not each pose's own lowest pixel on the floor
            a[1] = anchors[0][1]
    if name in IN_PLACE:
        for a in out:
            a[0] = anchors[0][0]
        return out
    for i in range(1, len(out) - 1):
        p, n = anchors[i - 1][0], anchors[i + 1][0]
        x = anchors[i][0]
        if abs(p - n) <= ANCHOR_AGREE and min(abs(x - p), abs(x - n)) > ANCHOR_JUMP:
            out[i][0] = round((p + n) / 2)
    return out


def load_order(root, name):
    d = os.path.join(root, 'extracted', CFG['mk_dir'], CAPTURE_OF.get(name, name))
    return [int(v) for v in open(os.path.join(d, 'order.txt')).read().split()]


CAPTURE_OF = {'hit_seq': 'hit_high', 'throw_seq': 'throw'}   # art groups drawn from another action's capture


def load_action(root, name):
    d = os.path.join(root, 'extracted', CFG['mk_dir'], CAPTURE_OF.get(name, name))
    poses = np.load(os.path.join(d, 'indexed.npy'))
    if name in PROJECTILES and name != 'spear':  # his cast without the bolt (its object flies it)
        import mkprojectile
        ax = json.load(open(os.path.join(d, 'anchors.json')))[0][0]
        poses = np.array([mkprojectile.strip(p, ax) for p in poses])
    anchors = steady_anchors(name, json.load(open(os.path.join(d, 'anchors.json'))))
    cram = json.load(open(os.path.join(d, 'cram.json')))
    return poses, anchors, cram


# MK's Scorpion stands 98 px; EC's fighters stand ~100-110 (Shadow ~108,
# Blade ~118), so he read as small. SCALE grows him to ~106 px. EC poses also
# reach ~7 px below the anchor (feet on the shadow); MK's end at it.
SCALE = float(os.environ.get('EK_SCALE', '1.08'))
FOOT_DROP = 7
# The game unpacks a frame in two time slices (<= ~77 tiles each); bigger
# frames are still unpacking when shown and draw as scrambled tiles (seen on
# the 140+ tile spear throws, whose MK sprite includes the rope EC draws
# anyway). Wider poses are cropped narrower around the body until they fit.
TILE_CAP = 112


def scale_pose(full, anchor, cram, scale=SCALE):
    """Resize an indexed pose (0 = transparent) about its anchor, filtering in
    colour and mapping back to the 15 palette colours."""
    if abs(scale - 1) < 1e-3:
        return full, anchor
    from PIL import Image
    ys, xs = np.nonzero(full)
    if not len(ys):
        return full, anchor
    x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    crop = full[y0:y1, x0:x1]
    pal = np.array([[(c & 7) * 36, ((c >> 3) & 7) * 36, ((c >> 6) & 7) * 36] for c in cram], np.float32)
    w, h = round((x1 - x0) * scale), round((y1 - y0) * scale)
    rgb = Image.fromarray(pal[crop].astype(np.uint8)).resize((w, h), Image.LANCZOS)
    alpha = Image.fromarray(((crop > 0) * 255).astype(np.uint8)).resize((w, h), Image.BILINEAR)
    rgb, alpha = np.asarray(rgb, np.float32), np.asarray(alpha) >= 128
    d = ((rgb[:, :, None, :] - pal[None, None, 1:, :]) ** 2).sum(-1)
    idx = (d.argmin(-1) + 1).astype(np.uint8) * alpha
    ax, ay = anchor
    nax, nay = round((ax - x0) * scale), round((ay - y0) * scale)
    pad = 8
    out = np.zeros((h + 2 * pad, w + 2 * pad + 256), np.uint8)
    out[pad:pad + h, pad + 128:pad + 128 + w] = idx
    return out, (nax + pad + 128, nay + pad)


# Scorpion's palette has two exact duplicates (7 = 2, 8 = 5); scaled art maps
# to the lower one, so 7 and 8 never appear. His black (12) and dark blue (13)
# move there, freeing 12 and 13 for blood red: EC's hit-spark tile is drawn
# in colours 12 and 13, so sparks drawn with his palette line are red drops
# (mkinputs r_blood, patches.scorpion_palette).
COLOUR_MOVES = {12: 7, 13: 8}
# which MK fighter is being built (patches.use sets these): his captures,
# the action names to use for actions he has no capture of, whether Blade's
# effect sheets $44/$45 are dropped, the palette entries moved for EC's blood
CFG = {'mk_dir': 'mk_moves', 'aliases': {}, 'exact': True, 'strip': True, 'colour_moves': COLOUR_MOVES,
       'extra': (), 'colour_map': {}}


def remap_colours(full):
    cmap = CFG['colour_map']                 # a fighter's own palette entries moved (all at once)
    if cmap:
        lut = np.arange(256, dtype=np.uint8)
        for a, b in cmap.items():
            lut[a] = b
        full = lut[full]
    moves = CFG['colour_moves']
    if not moves:
        return full
    assert not np.isin(full, list(moves.values())).any(), f'palette entries {list(moves.values())} are in use'
    out = full.copy()
    for a, b in moves.items():
        out[full == a] = b
    return out


SPEAR_AHEAD = 159              # px kept in front of him in spear poses: a piece may start at +127 and is 32 wide


def pose_pieces(full, anchor, cram=None, ahead=None):
    """Crop a full-screen pose around its anchor and cut it into pieces,
    clipping to what the format can address and to 150 tiles. ahead: keep
    this much in front of him and clip only behind (the spear: its head
    flies out up to ~145 px in front, its slack trails behind)."""
    if cram is not None:
        full, anchor = scale_pose(full, anchor, cram)
    full = remap_colours(full)
    ax, ay = anchor
    ay -= FOOT_DROP
    tries = [(dx, dx) for dx in (MAX_DX, 96, 80, 72, 64, 56, 48)]
    if ahead:
        tries = [(dx, ahead) for dx in (MAX_DX, 96, 80, 64, 48, 40, 32)] + tries
    for dx, dr in tries:
        x0, x1 = max(0, ax - dx), min(full.shape[1], ax + dr)
        y0, y1 = max(0, ay - MAX_UP), min(full.shape[0], ay + FOOT_DROP + 8)
        crop = full[y0:y1, x0:x1]
        if not crop.any():
            return [], []
        ys, xs = np.nonzero(crop)
        cy0, cx0 = ys.min(), xs.min()
        crop = crop[cy0:ys.max() + 1, cx0:xs.max() + 1]
        ox, oy = ax - x0 - cx0, ay - y0 - cy0
        try:
            r = ecpl.pose_from_image(crop, ox, oy)
        except ValueError:
            continue
        if len(r[1]) <= TILE_CAP or (dx == 48 and dr == 48):
            return r
    raise ValueError('pose does not fit in 150 tiles even clipped')


# most poses an action may contribute (evenly sampled); keeps the art in budget
CAP = {'idle': 7, 'walk_fwd': 9, 'walk_back': 2, 'spear': 8, 'teleport': 3, 'knockdown': 6, 'dizzy': 7,
       'hit_high': 5, 'hit_low': 5, 'hit_kick': 5, 'block': 4, 'crouch_block': 4,
       'fatality': 8, 'fatality_fire': 6, 'fatality_skeleton': 6}
DEFAULT_CAP = 6               # (an action shows at most as many poses as EC has frames for it)


JUMP_ATTACKS = ('jump_a', 'jump_x', 'jump_c', 'jump_z')


def widest(poses, k, n):
    """Jump-attack captures also hold the plain jump before and after the
    strike: use the n widest poses (limb out), in capture order."""
    w = []
    for i, p in enumerate(poses):
        xs = np.nonzero(p.any(0))[0]
        w.append((xs.max() - xs.min()) if len(xs) else 0)
    top = sorted(sorted(range(len(poses)), key=lambda i: -w[i])[:n])
    return top[min(k, len(top) - 1)]


def double_rope(p):
    """True if the pose's rope runs as two strands (MK shows that for a frame
    while the rope snaps taut): beyond the body, most sampled columns have
    two separate runs of pixels."""
    cnt = p.astype(bool).sum(0)
    body = np.nonzero(cnt > 12)[0]
    if not len(body):
        return False
    runs = []
    for x in range(body.max() + 30, p.shape[1], 10):
        rows = np.nonzero(p[:, x])[0]
        if len(rows):
            runs.append(1 + int(np.sum(np.diff(rows) > 1)))
    return len(runs) >= 4 and sum(r >= 2 for r in runs) > len(runs) // 2


def knockdown_pose(poses, k, n):
    """EC's knockdown plays two frames (scorpion_map 'knockdown': 42:18 the
    whole flight, 42:17 the landing) and lying is 42:0c (a fighter with no
    'lying' capture aliases it here, n == 1). MK's knockdown captures run
    standing, hit, flying, tumbling, landing, flat, getting up - so the poses
    are picked by shape, not spread evenly (that gave the first and last:
    standing, and a fighter fell into the Pit standing up): the flight is the
    flattest pose well off the ground, the landing the first pose back down
    after it, lying the flattest pose on the ground after that."""
    box = []
    for p in poses:
        ys, xs = np.nonzero(p)
        box.append((ys.min(), ys.max(), xs.max() - xs.min(), ys.max() - ys.min()))
    ground = box[0][1]
    air = [i for i, b in enumerate(box) if b[1] < ground - 40]
    if not air:
        return 0
    if n == 1:                                      # lying
        down = [i for i in range(air[-1] + 1, len(box)) if box[i][1] >= ground - 16]
        return min(down, key=lambda i: box[i][3] - box[i][2]) if down else len(box) - 1
    if k == 0:                                      # the flight: lying flat, most of him showing
        flat = [i for i in air if box[i][2] > 1.2 * box[i][3]] or air   # (EC holds it the whole
        return max(flat, key=lambda i: int(np.count_nonzero(poses[i])))   # flight: not an edge-on blur)
    down = [i for i in range(air[-1] + 1, len(box)) if box[i][1] >= ground - 16]
    return down[0] if down else air[-1]


HIT_KEYS = {(0x42, f) for f in (0x26, 0x24, 0x01, 0x25, 0x27)}   # scorpion_map's hit group
HIT_LANDS = 64                # hit captures: P2 presses at frame 50; MK's reaction shows from ~67 (Raiden's stance runs to 61)


def hit_pose(poses, k, n):
    """EC's hit frames by role (scorpion_map 'hit_high'): k 0 the hit (MK's
    first reaction pose), 2 the recovery flinch (late in MK's reaction; EC also
    shows it for 6 frames before the hit pose), otherwise the stagger."""
    m = len(poses)
    at = {0: 0.25, 2: 0.7}.get(k, 0.4)             # MK's recoil peaks a quarter in
    return round(at * (m - 1))


def pick(poses, k, n, action=''):
    if action == 'hit':
        return hit_pose(poses, k, n)
    if action in JUMP_ATTACKS:
        return widest(poses, k, n)
    if action == 'knockdown':
        return knockdown_pose(poses, k, n)
    p = len(poses)
    if n is None:                                   # an exact pose (scorpion_map 'frame=pose')
        return k
    cap = min(p, CAP.get(action, DEFAULT_CAP))
    slot = 0 if n == 1 or cap == 1 else round(k * (cap - 1) / (n - 1))
    i = 0 if cap == 1 else round(slot * (p - 1) / (cap - 1))
    if action == 'spear':
        # EC holds a spear pose while the spear is stuck in the victim: a
        # double-strand one (a one-frame flash in MK) would stay on screen;
        # and a pose whose spear head only fits clipped off is passed over
        while i + 1 < p and (double_rope(poses[i]) or i in SPEAR_CLIPPED):
            i += 1
    return i


SPEAR_CLIPPED = set()          # spear poses whose head doesn't fit the tile cap (build fills it)


def spear_clipped(poses, anchors, cram):
    out = set()
    for i in range(len(poses)):
        full, (ax, _) = scale_pose(poses[i], anchors[i], cram)
        xs = np.nonzero(full.any(0))[0]
        if not len(xs):
            continue
        pieces, _ = pose_pieces(poses[i], anchors[i], cram, ahead=SPEAR_AHEAD)
        right = max((q['x'] + 8 * q['w'] for q in pieces), default=0)
        if right < min(xs.max() - ax, SPEAR_AHEAD) - 8:
            out.add(i)
    return out


def _sb(v):
    return v - 256 if v > 127 else v


def extents(pieces):
    """(back, front, top) of a piece list in pixels from the anchor (x forward, y up negative)."""
    if not pieces:
        return None
    return (min(p['x'] for p in pieces), max(p['x'] + 8 * p['w'] for p in pieces),
            min(p['y'] for p in pieces))


def extents_raw(rec):
    """extents() of a frame record's piece list as stored in the file."""
    pieces = []
    for i in range(0, len(rec) - 5, 6):
        s = rec[i]
        pieces.append({'w': ((s >> 2) & 3) + 1, 'h': (s & 3) + 1,
                       'x': _sb(rec[i + 4]), 'y': _sb(rec[i + 5])})
    return extents(pieces)


STRIKE_SLACK = 0              # px past the MK pose's front (already rounded up to its 8 px tile)


def fit_boxes(pl, q, blade, scorpion, report):
    """Rescale a frame's collision data (A boxes x1 x2 y1 y2, then B points x y,
    signed bytes from the anchor) from Blade's outline to Scorpion's, so hits
    land where Scorpion's fist or foot actually is. Front, back and height are
    scaled separately; below the anchor (feet) is left alone."""
    if not blade or not scorpion:
        return
    # never smaller than Blade's: his reach and his body boxes are what the
    # EC fighters are balanced against (tools/hitmatrix.py); a little bigger
    # where the MK pose reaches further
    def ratio(s, b):
        return min(1.3, max(1.0, s / b)) if b and (s * b) > 0 else 1.0
    fx, bx, ty = ratio(scorpion[1], blade[1]), ratio(scorpion[0], blade[0]), ratio(scorpion[2], blade[2])
    X = lambda v: max(-128, min(127, round(v * (fx if v > 0 else bx))))
    Y = lambda v: max(-128, min(127, round(v * ty))) if v < 0 else v
    n = int.from_bytes(pl[q:q + 2], 'big')
    for i in range(n):
        o = q + 2 + 4 * i
        x1, x2, y1, y2 = (_sb(v) for v in pl[o:o + 4])
        # only the outer edges grow: the far side and the top; the inner
        # side and the bottom stay Blade's (scaling both lifted low punches
        # over crouching victims - tools/hitmatrix.py)
        far = max((x1, x2), key=abs)
        x1, x2 = (X(v) if v == far else v for v in (x1, x2))
        top = min(y1, y2)
        y1, y2 = (Y(v) if v == top else v for v in (y1, y2))
        if i == 0 and x2 > scorpion[1] + STRIKE_SLACK:
            # box 0 is the strike box (spear_reach). Blade's strikes reach
            # past his fist with his arm blade (his jab's box: 44-94 px, his
            # pose 98; Scorpion's MK jab reaches 44): it is moved back, same
            # size, to end at the MK pose's front - or hits land on victims
            # the fist is well short of (the Pit video's last jab, at 107 px)
            d = x2 - (scorpion[1] + STRIKE_SLACK)
            x1, x2 = max(-128, x1 - d), x2 - d
        pl[o:o + 4] = bytes(v & 0xFF for v in (x1, x2, y1, y2))
    q += 2 + 4 * n
    m = int.from_bytes(pl[q:q + 2], 'big')
    for i in range(m):
        o = q + 2 + 2 * i
        x, y = _sb(pl[o]), _sb(pl[o + 1])
        pl[o:o + 2] = bytes((X(x) & 0xFF, Y(y) & 0xFF))
    report.setdefault('fit', []).append((round(fx, 2), round(bx, 2), round(ty, 2)))


# strike frame -> the move whose poses' reach its box gets (both crouching
# punches are MK CD's uppercut: down + Y strikes on 42:03, down + X on 40:09)
SWEEP_STRIKES = {(0x42, 0x03): 'uppercut', (0x40, 0x09): 'uppercut'}


# art groups on Blade's projectile move ($34): Scorpion's spear, the others'
# bolts (their strike box is the spear's: stretched on 42:2E, off elsewhere)
PROJECTILES = ('spear', 'lightning', 'iceblast', 'greenbolt')
SPEAR_REACH = 127             # px; boxes are signed bytes, so this is the most data allows


SPEAR_STRIKE = (0x42, 0x2E)   # the one frame whose strike box (box 0) stays live


def no_strike(pl, q):
    """A cast frame's strike box (box 0) out of reach: the MK projectile
    object (mkinputs.emit_proj) carries the hit."""
    if int.from_bytes(pl[q:q + 2], 'big'):
        pl[q + 2:q + 4] = bytes((0x80, 0x80))


def spear_reach(pl, q, frame):
    """Spear frames keep Blade's body boxes (1-4). Box 0 is the strike box:
    on the rope-out frame it is stretched to SPEAR_REACH; on every other spear
    frame it is moved out of reach (x -128). Otherwise the pull holds the
    victim inside the strike boxes and each new frame hits him again (one
    throw took 67 of 104 health)."""
    o = q + 2
    if frame == SPEAR_STRIKE:
        pl[o + 1] = SPEAR_REACH
    else:
        pl[o:o + 2] = bytes((0x80, 0x80))


# The game loads player 2's .PL at PRG-RAM $51800 (player 1's into Word RAM,
# with more room). EC's own player-2 files prove the space: MID.PL (selectable,
# 184160 bytes) and ECX.PL (the final boss, always the CPU = player 2, 187332).
# (RAM.PL, 190718, would run past PRG-RAM's end at $51800, so it isn't proof.)
# Growing past Blade's 166756 bytes moves every chunk after the art.
MAX_PL = 188416                  # ECX.PL fills 92 CD sectors (188416 bytes); verified: tools/p2check.py


def splice(pl, blob, grow):
    """Put blob (longer than the art region) at A5 and move the rest of the
    file up by grow bytes, fixing: the first chunk's length, each later
    resource chunk's absolute resource offset (chunk + $0E), and each later
    compressed resource's offset back to the bank section (its first long,
    relative to the resource)."""
    L = lambda b, o: int.from_bytes(b[o:o + 4], 'big')
    W = lambda b, o: int.from_bytes(b[o:o + 2], 'big')
    out = bytearray(pl[:A5]) + bytearray(blob) + bytearray(grow - (len(blob) - (REGION_END - A5))) + bytearray(pl[REGION_END:])
    assert len(out) == len(pl) + grow
    out[0:4] = (L(pl, 0) + grow).to_bytes(4, 'big')
    pos = L(out, 0)
    while pos + 8 <= len(out):
        n = L(out, pos)
        if n == 0:
            break
        if W(out, pos + 4) == 0:                         # resource chunk
            res = L(out, pos + 0x0E) + grow
            out[pos + 0x0E:pos + 0x12] = res.to_bytes(4, 'big')
            if W(out, pos + 0x0C) == 0x18:               # compressed: offset back to the banks
                rel = (L(out, res) - grow) & 0xFFFFFFFF
                out[res:res + 4] = rel.to_bytes(4, 'big')
        pos += n
    return bytes(out)


BLADE_ONLY_SHEETS = (0x44, 0x45)   # Blade's projectile and its blast (BLA.CO $31F6/$3914): no Scorpion move shows them


def strip_sheets(pl, sheets=BLADE_ONLY_SHEETS):
    """Drop the sheet-registration chunks for sheets, and the tile-source
    chunks they use, from the end of the file (they follow every sheet
    Scorpion uses, so no offset before them moves). Blade registers the same
    sheets from his own file when he is in the fight."""
    L = lambda o: int.from_bytes(pl[o:o + 4], 'big')
    W = lambda o: int.from_bytes(pl[o:o + 2], 'big')
    chunks, pos = [], 0
    while pos + 8 <= len(pl) and L(pos):
        chunks.append(pos)
        pos += L(pos)
    trailer = bytes(pl[pos:])
    drop_src = {W(c + 0x0C) for c in chunks if W(c + 4) == 4 and W(c + 0x0A) // 4 in sheets}
    drop = [c for c in chunks if (W(c + 4) == 4 and W(c + 0x0A) // 4 in sheets) or (W(c + 4) == 0 and W(c + 0x0A) // 4 in drop_src)]
    assert len(drop) == 2 * len(sheets) and drop == chunks[-len(drop):], 'Blade-only sheets are not the last chunks'
    return bytes(pl[:drop[0]]) + trailer


_UNPACKER = []


def check_bank(data, offs, frames):
    """Decode every frame of a bank with EC's own unpacker (tools/ecunpack.py)
    and compare: the encoder must be exact."""
    import ecunpack
    from inputs import ROOT
    if not _UNPACKER:
        _UNPACKER.append(ecunpack.Unpacker(open(os.path.join(ROOT, 'extracted', 'ec_us', 'SUB.BIN'), 'rb').read()))
    u = _UNPACKER[0]
    for j, (lo, oo) in enumerate(offs):
        res = bytearray((10).to_bytes(4, 'big') + bytes(2) + lo.to_bytes(2, 'big') + oo.to_bytes(2, 'big'))
        res += (6).to_bytes(2, 'big') + (6).to_bytes(4, 'big') + data
        u.load(bytes(res))
        t = u.frame(0, 0)
        got = [int.from_bytes(t[i:i + 2], 'big') for i in range(0, len(t), 2)]
        assert got == frames[j], f'art bank frame {j}: EC unpacks something else'


def build(pl, root):
    pl = bytearray(strip_sheets(pl) if CFG['strip'] else pl)
    W = lambda o: int.from_bytes(pl[o:o + 2], 'big')
    want = assignments(CFG['aliases'], CFG['exact'], CFG['extra'])
    exact_actions = {a for a, _ in CFG['extra']}

    # --- the distinct Scorpion poses needed. Every capture starts and ends in
    #     the stance, so for actions other than idle, stance poses are dropped.
    def crop_key(p):
        ys, xs = np.nonzero(p)
        return p[ys.min():ys.max() + 1, xs.min():xs.max() + 1].tobytes() if len(ys) else b''
    idle_keys = {crop_key(p) for p in load_action(root, 'idle')[0]}
    actions, chosen = {}, {}
    for key, (action, k, n) in want.items():
        if action == 'none':
            chosen[key] = None
            continue
        if action not in actions:
            poses_, anchors_, cram_ = load_action(root, action)
            # stance poses are dropped from other actions; groups addressed by
            # pose number keep the capture's numbering (the daze also sways
            # through stance-like poses)
            exact_group = action in exact_actions or (CFG['exact'] and action in ('dizzy', 'teleport_mk', 'jumpup_c', 'jumpup_a'))
            if action != 'idle' and not exact_group:
                keep = [i for i, p in enumerate(poses_) if crop_key(p) not in idle_keys] or list(range(len(poses_)))
                if action.startswith('hit_'):
                    # stance poses the idle capture missed (Raiden's stance cycle
                    # outlasts it): drop what showed before the hit landed
                    first = {}
                    for t, q in enumerate(load_order(root, action)):
                        first.setdefault(q, t)
                    keep = [i for i in keep if first.get(i, 0) >= HIT_LANDS] or keep
                poses_, anchors_ = poses_[keep], [anchors_[i] for i in keep]
            actions[action] = (poses_, anchors_, cram_)
            if action == 'spear':
                SPEAR_CLIPPED.clear()
                SPEAR_CLIPPED.update(spear_clipped(poses_, anchors_, cram_))
        poses, anchors, _ = actions[action]
        chosen[key] = (action, pick(poses, k, n, 'hit' if key in HIT_KEYS and action == 'hit_high' else action))
    # the same MK image picked by several actions (the stance that starts a
    # crouching move, a kick shared by two buttons...) is stored once
    canon = {}
    for v in sorted({v for v in chosen.values() if v}):
        poses, anchors, _ = actions[v[0]]
        canon.setdefault((crop_key(poses[v[1]]), tuple(anchors[v[1]])), v)
    for key, v in chosen.items():
        if v:
            poses, anchors, _ = actions[v[0]]
            chosen[key] = canon[(crop_key(poses[v[1]]), tuple(anchors[v[1]]))]
    distinct = sorted({v for v in chosen.values() if v})
    cut = {}
    for action, i in distinct:
        poses, anchors, cram = actions[action]
        cut[(action, i)] = pose_pieces(poses[i], anchors[i], cram, ahead=SPEAR_AHEAD if action == 'spear' else None)
    cut[None] = ([], [])

    # --- pack into banks (<= 30 KB each, own dictionary)
    order = [None] + distinct
    banks, placed, group = [], {}, []

    def flush(group):
        frames = [ecpl.words(cut[g][1]) for g in group]
        data, offs = ecpl2.encode_bank(frames)
        check_bank(data, offs, frames)
        b = len(banks)
        banks.append(data)
        for g, o in zip(group, offs):
            placed[g] = (b, o)

    est = 512
    for g in order:
        size = len(cut[g][1]) * 32 * 0.65 + 64
        if group and est + size > 30000:
            flush(group)
            group, est = [], 512
        group.append(g)
        est += size
    if group:
        flush(group)

    # --- write the bank section + banks
    nb = len(banks)
    head = 2 + 4 * nb
    sec = bytearray(head.to_bytes(2, 'big'))       # word0 -> (empty) shared sub-frame table
    at = head
    body = bytearray()
    for data in banks:
        if (at + len(body)) % 2:
            body.append(0)
        sec += (at + len(body)).to_bytes(4, 'big')
        body += data
    blob = sec + body
    room = REGION_END - A5
    grow = max(0, (len(blob) - room + 1) & ~1)
    if len(pl) + grow > MAX_PL:
        raise ValueError(f'Scorpion art is {len(blob)} bytes: BLA.PL would be {len(pl) + grow}, over {MAX_PL}')
    pl[A5:A5 + min(len(blob), room)] = blob[:room]
    if not grow:
        pl[A5 + len(blob):REGION_END] = bytes(room - len(blob))

    # --- frame records and piece lists
    report = {'poses': len(distinct), 'banks': nb, 'bytes': len(blob), 'room': room, 'tight': []}
    for sid, (res, sheet) in RESOURCES.items():
        nframes = W(sheet + 4)
        offsets = [W(sheet + 6 + 2 * i) for i in range(nframes)]
        uniq = sorted(set(offsets))
        assigned, seen = {}, set()
        for f in range(nframes):
            o = offsets[f]
            g = assigned.setdefault(o, chosen.get((sid, f)))   # frames sharing a record share a pose
            b, (lo, oo) = placed[g]
            r = res + 4 + 6 * f
            pl[r:r + 6] = bytes([b, 0]) + lo.to_bytes(2, 'big') + oo.to_bytes(2, 'big')
            if o in seen:
                continue
            seen.add(o)
            nxt = next((x for x in uniq if x > o), None)
            q = sheet + 6 + o
            end = sheet + 6 + nxt if nxt is not None else None
            q0 = q
            q += 2 + 4 * W(q)
            q += 2 + 2 * W(q)
            t = q
            while not W(t) & 0x8000:
                t += 6
            if end is None:
                end = t + 2
            pieces = cut[g][0]
            if g and g[0] == 'spear':
                spear_reach(pl, q0, (sid, f))       # the rope: Blade's reach, stretched
            elif g and g[0] in PROJECTILES:
                no_strike(pl, q0)                   # a bolt: its flying object hits (mkinputs.emit_proj)
            elif not os.environ.get('EK_NOFIT'):
                ext = extents(pieces)
                if (sid, f) in SWEEP_STRIKES and ext:
                    # the strike lands on the uppercut's highest pose (mkscripts), whose
                    # fist is above him: its box reaches as far as the fist swept on the way up
                    ext = (ext[0], max([ext[1]] + [extents(cut[h][0])[1] for h in cut
                                                   if h and h[0] == SWEEP_STRIKES[(sid, f)]
                                                   and extents(cut[h][0])]), *ext[2:])
                fit_boxes(pl, q0, extents_raw(pl[q:t]), ext, report)
            rec = ecpl.piece_record(pieces) + bytes(pl[t:t + 2])
            while q + len(rec) > end and pieces:
                pieces = pieces[:-1]                # drop the smallest-priority piece
                rec = ecpl.piece_record(pieces) + bytes(pl[t:t + 2])
                report['tight'].append((sid, f))
            pl[q:q + len(rec)] = rec
    report['grow'] = grow
    if grow:
        pl = splice(pl, blob, grow)
    report['room'] = room + grow
    return bytes(pl), report
