#!/usr/bin/env python3
"""Eternal Champions CD stages: read, render and build NAME.BG / NAME.BGI.

Format (docs/re_notes.md, "Stages"):
  .BG  chunk chain like .PL (long length, word type, long 0, ...), 4 zero
       bytes at the end. Type 0 = tile source (+A slot*8, +C kind 4 = raw,
       +E long file offset of data, +12 word size, data from +14). Type 4 =
       sprite sheet (+A sheet*4). Type 8 = the background: +A slot*4,
       +C first layer id, +E tile slot, +16 word VRAM bytes, +1C $FFFF,
       +1E layer ids ($FFFF-terminated, renumbered by the loader from +C),
       then one record per layer (word 4 = raw, long file offset, word size).
  layer = +0 width-1 (blocks), +2 height-1, +4 default block, +6 0,
          +8 long offset of the block table, +C long offset of each block row;
          rows = width words (block numbers, bit 15 ignored by the streamer);
          block = 4x4 cell words, row-major (prio/pal/vflip/hflip/tile,
          tile relative to the stage's tile block in VRAM).
  .BGI 68000 module at $34000 (header 00000000 0018 0000 0000). The engine
       has no fixed entry: the stage's init routine in SUB.BIN spawns objects
       whose 34-byte descriptors live in the BGI, and the BGI code sets the
       Overkill check $14FA(a6) (called at +0 and +2, carry set = trigger).

  Stage modes: $AB2(a6) = $11..$22 picks a stage; SUB.BIN $6862 + 2*mode is
  a word offset (from $6862) to that stage's init, which loads BG/BGI, calls
  $DEF8(slot), creates the layer objects ($E062 + inline plane/x/y/w/h), sets
  camera limits ($E00E inline), floor $1496, start camera, the 32-colour
  palette (lines 0-1, table in SUB.BIN, $12C3C), and spawns the BGI objects.
  GAME.CO $C28 (loaded at $14000): word per fighter idx -> stage mode.

  Palette budget for the art: line 0 colours 2-15 (0 = backdrop, 1 = fighter
  shadow), line 1 colours 1-9 (10-15 = HUD). build() keeps the replaced
  stage's shadow and HUD colours and fits the rest.

    ecstage.py info STAGE                         # init + BG summary (SHA, MID, ...)
    ecstage.py render STAGE OUTDIR                # every layer + both planes as PNG
    ecstage.py build STAGE A.png B.png cram.json OUTDIR [--dx N --dy N]
"""
import argparse, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

SUB_BASE, BGI_BASE, BG_BASE = 0x6000, 0x34000, 0x37000
MODE_TABLE = 0x6862          # SUB.BIN: word offsets from $6862, indexed by $AB2(a6)
STAGE_MODES = range(0x11, 0x23)
API = dict(e00e=0xE00E, e062=0xE062, f4ba=0xF4BA, load=0x65C8, def8=0xDEF8,
           spawn=0x1064A, spawn2=0x105E8, pal=0x12C3C)


def W(d, o):
    return int.from_bytes(d[o:o + 2], 'big')


def L(d, o):
    return int.from_bytes(d[o:o + 4], 'big')


def S(d, o):
    return int.from_bytes(d[o:o + 2], 'big', signed=True)


# --------------------------------------------------------------- .BG reading
def chunks(data):
    o = 0
    while o + 6 <= len(data):
        n = L(data, o)
        if n == 0:
            break
        yield o, n, W(data, o + 4)
        o += n


def parse_bg(data):
    out = dict(tiles={}, sheets={}, bg=None, chunks=list(chunks(data)))
    for o, n, t in out['chunks']:
        if t == 0:
            size = W(data, o + 0x12)
            out['tiles'][W(data, o + 0xA) // 8] = dict(off=o, kind=W(data, o + 0xC), size=size,
                                                       data=data[o + 0x14:o + 0x14 + size])
        elif t == 4:
            out['sheets'][W(data, o + 0xA) // 4] = o
        elif t == 8:
            bg = dict(off=o, slot=W(data, o + 0xA) // 4, first_id=W(data, o + 0xC),
                      tile_slot=W(data, o + 0xE), vram_bytes=W(data, o + 0x16))
            k = o + 0x1E
            n_ids = 0
            while W(data, k) != 0xFFFF:
                n_ids += 1
                k += 2
            k += 2
            bg['layers'] = []
            for j in range(n_ids):
                bg['layers'].append(dict(id=bg['first_id'] + j, type=W(data, k),
                                         off=L(data, k + 2), size=W(data, k + 6)))
                k += 8
            out['bg'] = bg
    return out


def read_layer(data, rec):
    a = rec['off']
    if rec['type'] != 4:
        raise NotImplementedError(f"layer {rec['id']:#x}: packed type {rec['type']}")
    w, h = W(data, a) + 1, W(data, a + 2) + 1
    boff = L(data, a + 8)
    grid = np.array([[W(data, L(data, a + 0xC + 4 * r) + 2 * c) for c in range(w)] for r in range(h)],
                    np.uint16)
    nblk = int((grid & 0x7FF).max()) + 1
    blocks = np.array([[W(data, boff + 32 * b + 2 * k) for k in range(16)] for b in range(nblk)],
                      np.uint16).reshape(nblk, 4, 4)
    return dict(id=rec['id'], w=w, h=h, default=W(data, a + 4), grid=grid, blocks=blocks)


def layer_cells(lay):
    """(h*4, w*4) cell words, tile numbers relative to the stage's tile block."""
    g = lay['grid'] & 0x7FF
    return lay['blocks'][g].transpose(0, 2, 1, 3).reshape(lay['h'] * 4, lay['w'] * 4)


def decode_tiles(raw):
    a = np.frombuffer(raw[:len(raw) // 32 * 32], np.uint8).reshape(-1, 8, 4)
    t = np.empty((a.shape[0], 8, 8), np.uint8)
    t[:, :, 0::2] = a >> 4
    t[:, :, 1::2] = a & 15
    return t


def encode_tiles(tiles):
    t = np.asarray(tiles, np.uint8)
    return ((t[:, :, 0::2] << 4) | t[:, :, 1::2]).astype(np.uint8).tobytes()


def hw_to_rgb(word):
    """Genesis CRAM word as the game stores it ($0BGR, 3 bits each, bits 1-3)."""
    return ((word >> 1) & 7) * 36, ((word >> 5) & 7) * 36, ((word >> 9) & 7) * 36


def packed_to_hw(v):
    """vdp.py's 9-bit BBBGGGRRR -> $0BGR."""
    return ((v >> 6 & 7) << 9) | ((v >> 3 & 7) << 5) | ((v & 7) << 1)


def render_cells(cells, tiles, pal_rgb):
    """RGBA image of a cell map: pal_rgb = 64 (r,g,b) (lines 0-3); colour 0 transparent."""
    h, w = cells.shape
    out = np.zeros((h * 8, w * 8, 4), np.uint8)
    pal = np.array(pal_rgb, np.uint8).reshape(4, 16, 3)
    for cy in range(h):
        for cx in range(w):
            e = int(cells[cy, cx])
            t = tiles[e & 0x7FF] if (e & 0x7FF) < len(tiles) else np.zeros((8, 8), np.uint8)
            if e & 0x800:
                t = t[:, ::-1]
            if e & 0x1000:
                t = t[::-1]
            px = out[cy * 8:cy * 8 + 8, cx * 8:cx * 8 + 8]
            px[:, :, :3] = pal[(e >> 13) & 3][t]
            px[:, :, 3] = np.where(t > 0, 255, 0)
    return out


# --------------------------------------------------------------- SUB.BIN: stage init
def stage_inits(sub):
    """{mode ($AB2 value): init address} for the 18 stage modes."""
    return {m: (MODE_TABLE + W(sub, MODE_TABLE - SUB_BASE + 2 * m)) & 0xFFFF for m in STAGE_MODES}


def parse_init(sub, mode):
    """What a stage's init routine in SUB.BIN sets up (measured from the code)."""
    import capstone
    cs = capstone.Cs(capstone.CS_ARCH_M68K, capstone.CS_MODE_M68K_000)
    mem = sub
    base = SUB_BASE
    pc = stage_inits(sub)[mode]
    info = dict(mode=mode, init=pc, files={}, objects=[], descriptors=[], bgi_refs=[], sheets=[])
    last = {}
    cur = None
    while True:
        i = next(cs.disasm(mem[pc - base:pc - base + 10], pc, 1))
        s = f'{i.mnemonic} {i.op_str}'
        nxt = pc + i.size
        args = lambda n: [W(mem, nxt - base + 2 * k) for k in range(n)]
        if s == f'jsr ${API["e00e"]:x}.l':
            info['camera'] = tuple(args(4))      # x min, y min, x max, y max (-$4FA8..-$4FA2)
            nxt += 8
        elif s == f'jsr ${API["e062"]:x}.l':
            a = args(5)
            cur = dict(plane='AB'[a[0] // 2] if a[0] in (0, 2) else a[0], x=S(bytes(a[1].to_bytes(2, 'big')), 0),
                       y=a[2], ext_x=a[3], ext_y=a[4], id=0, flags=0x1E, xmode=0, xspeed=0, ymode=0)
            info['objects'].append(cur)
            nxt += 10
        elif s == f'jsr ${API["f4ba"]:x}.l':
            k = nxt - base
            lst = []
            while W(mem, k) != 0xFFFF:
                lst.append(W(mem, k))
                k += 2
            info['sheets'].append(lst)
            nxt = k + 2 + base
        elif s.startswith('move.w #') and s.endswith(', d0'):
            last['d0'] = int(i.op_str.split(',')[0][2:], 16)
        elif s.startswith('move.w #') and s.endswith(', d1'):
            last['d1'] = int(i.op_str.split(',')[0][2:], 16)
        elif s.startswith('move.w #') and s.endswith(', d2'):
            last['d2'] = int(i.op_str.split(',')[0][2:], 16)
        elif s.startswith('move.l #') and '-$6e70(a6)' in s:
            last['dest'] = int(i.op_str.split(',')[0][2:], 16)
        elif s == f'jsr ${API["load"]:x}.l':
            info['files'][last.get('dest')] = last.get('d0')
        elif s == f'jsr ${API["def8"]:x}.l':
            info['slot'] = last.get('d0')
        elif s.startswith('movea.l #') and s.endswith(', a1'):
            last['a1'] = int(i.op_str.split(',')[0][2:], 16)
        elif s.startswith('movea.l #') and s.endswith(', a0'):
            last['a0'] = int(i.op_str.split(',')[0][2:], 16)
        elif s in (f'jsr ${API["spawn"]:x}.l',):
            a1 = last.get('a1')
            info['descriptors'].append(dict(addr=a1, d0=last.get('d0'), x=last.get('d1'), y=last.get('d2')))
            if a1 and BGI_BASE <= a1 < BG_BASE:
                info['bgi_refs'].append(('descriptor', a1))
        elif s == 'jsr $e046.l':
            cur = None
        elif s == f'jsr ${API["pal"]:x}.l':
            info['palette'] = dict(addr=last.get('a0'), first=last.get('d0'), last=last.get('d1'))
        elif cur is not None and '(a0)' in s and s.startswith('move'):
            src, dst = i.op_str.split(', ')
            if src.startswith('#$'):
                v = int(src[2:], 16)
                off = int(dst.split('(')[0][1:], 16)
                key = {0x58: 'id', 0x5E: 'flags', 0x36: 'xmode', 0x37: 'ymode', 0x38: 'xspeed',
                       0x3A: 'x3a', 0x3C: 'x3c', 0x4A: 'yspeed', 0x60: 'rowmask', 0x64: 'linefunc'}.get(off, f'f{off:02x}')
                cur[key] = v
                if key == 'linefunc' and BGI_BASE <= v < BG_BASE:
                    info['bgi_refs'].append(('linefunc', v))
        elif 'b070' in s and s.startswith('move.w #'):
            info.setdefault('cam0', {})['x'] = int(i.op_str.split(',')[0][2:], 16)
        elif 'b074' in s and s.startswith('move.w #'):
            info.setdefault('cam0', {})['y'] = int(i.op_str.split(',')[0][2:], 16)
        elif '$1496(a6)' in s and s.startswith('move.w #'):
            info['floor'] = int(i.op_str.split(',')[0][2:], 16)
        if s.startswith(('bra.w $6d8c', 'jmp $6d8c')) or pc - info['init'] > 0x600:
            break
        pc = nxt
    info['bg_file'] = info['files'].get(BG_BASE)
    info['bgi_file'] = info['files'].get(BGI_BASE)
    return info


def file_list(sub):
    i = sub.find(b'\x0aMISC.BIN;1')
    names = []
    while i < len(sub):
        n = sub[i]
        s = sub[i + 1:i + 1 + n]
        if n == 0 or not s.endswith(b';1'):
            break
        names.append(s[:-2].decode())
        i += 1 + n
        i += i & 1
    return names


# --------------------------------------------------------------- building
def _cells_from_rgba(img, line_rgb):
    """Map an RGBA image (H, W multiples of 8) to cells: returns (line, idx tiles)."""
    h, w = img.shape[0] // 8, img.shape[1] // 8
    rgb = img[:, :, :3].astype(int)
    op = img[:, :, 3] > 0
    lines = np.zeros((h, w), np.uint8)
    idx = np.zeros((h, w, 8, 8), np.uint8)
    pals = [np.array(p[1:], int) for p in line_rgb]           # colours 1-15 of each line
    for cy in range(h):
        for cx in range(w):
            m = op[cy * 8:cy * 8 + 8, cx * 8:cx * 8 + 8]
            if not m.any():
                continue
            px = rgb[cy * 8:cy * 8 + 8, cx * 8:cx * 8 + 8][m]
            best = None
            for li, p in enumerate(pals):
                d = ((px[:, None, :] - p[None, :, :]) ** 2).sum(2)
                err = d.min(1).sum()
                if best is None or err < best[0]:
                    best = (err, li, d.argmin(1))
            _, li, near = best
            t = np.zeros((8, 8), np.uint8)
            t[m] = near + 1
            lines[cy, cx] = li
            idx[cy, cx] = t
    return lines, idx


def choose_lines(images, cram):
    """Pick the two source palette lines (of cram's 4) that cover the most cells exactly.
    Returns [line_rgb x2] (16 colours each) and their 9-bit packed words."""
    rgb = [((v & 7) * 36, ((v >> 3) & 7) * 36, ((v >> 6) & 7) * 36) for v in cram]
    sets = [set(rgb[l * 16 + 1:l * 16 + 16]) for l in range(4)]
    need = []
    for img in images:
        h, w = img.shape[0] // 8, img.shape[1] // 8
        for cy in range(h):
            for cx in range(w):
                c = img[cy * 8:cy * 8 + 8, cx * 8:cx * 8 + 8]
                m = c[:, :, 3] > 0
                if m.any():
                    need.append({tuple(int(x) for x in p) for p in c[:, :, :3][m]})
    best = None
    for a in range(4):
        for b in range(4):
            if a >= b:
                continue
            score = sum(1 for n in need if n <= sets[a] or n <= sets[b])
            if best is None or score > best[0]:
                best = (score, a, b)
    _, a, b = best
    return [a, b], best[0], len(need)


def _rgb9(v):
    return ((v & 7) * 36, ((v >> 3) & 7) * 36, ((v >> 6) & 7) * 36)


def _snap(c):
    """RGB -> nearest Genesis colour (vdp.py scale: 0, 36, ... 252)."""
    return tuple(int(min(7, max(0, round(x / 36)))) * 36 for x in c)


def rgb_to_hw(c):
    r, g, b = (int(round(x / 36)) for x in c)
    return (b << 9) | (g << 5) | (r << 1)


def fit_palettes(images, cram, fixed, iters=8):
    """Two 16-colour lines for the stage art. fixed = {(line, index): (r,g,b)}:
    slots the game owns (line 0 colour 1 = fighter shadow, line 1 colours
    10-15 = HUD); art may use them but they don't move. Colour 0 of each
    line is transparent. Starts from the two source cram lines that cover
    the most cells exactly, then alternates cell -> line assignment and a
    weighted k-means of each line's free slots."""
    cells = []
    for img in images:
        h, w = img.shape[0] // 8, img.shape[1] // 8
        for cy in range(h):
            for cx in range(w):
                c = img[cy * 8:cy * 8 + 8, cx * 8:cx * 8 + 8]
                m = c[:, :, 3] > 0
                if m.any():
                    cols, cnt = np.unique(c[:, :, :3][m].reshape(-1, 3), axis=0, return_counts=True)
                    cells.append((cols.astype(float), cnt.astype(float)))
    chosen, exact, n = choose_lines(images, cram)
    free = [[i for i in range(1, 16) if (l, i) not in fixed] for l in (0, 1)]
    pal = []
    for l, src in enumerate(chosen):
        line = [None] * 16
        line[0] = (0, 0, 0)
        for (fl, i), c in fixed.items():
            if fl == l:
                line[i] = tuple(c)
        # most used source colours first into the free slots
        srcc = [_rgb9(cram[src * 16 + i]) for i in range(1, 16)]
        use = {c: 0 for c in srcc}
        for cols, cnt in cells:
            for c, k in zip(map(tuple, cols.astype(int)), cnt):
                if c in use:
                    use[c] += k
        cand = [c for c in sorted(use, key=lambda c: -use[c]) if c not in line]
        for i in free[l]:
            line[i] = cand.pop(0) if cand else (0, 0, 0)
        pal.append(line)

    def cell_err(cols, cnt, line):
        p = np.array(line[1:], float)
        d = ((cols[:, None, :] - p[None, :, :]) ** 2).sum(2)
        return (d.min(1) * cnt).sum(), d.argmin(1) + 1

    for _ in range(iters):
        groups = [[], []]
        for cols, cnt in cells:
            e = [cell_err(cols, cnt, pal[l])[0] for l in (0, 1)]
            groups[int(e[1] < e[0])].append((cols, cnt))
        changed = False
        for l in (0, 1):
            if not groups[l]:
                continue
            X = np.concatenate([g[0] for g in groups[l]])
            Wt = np.concatenate([g[1] for g in groups[l]])
            for _k in range(4):
                P = np.array(pal[l][1:], float)
                lab = ((X[:, None, :] - P[None, :, :]) ** 2).sum(2).argmin(1) + 1
                for i in free[l]:
                    m = lab == i
                    if m.any():
                        c = _snap((X[m] * Wt[m, None]).sum(0) / Wt[m].sum())
                        if c != pal[l][i] and c not in pal[l]:
                            pal[l][i] = c
                            changed = True
            # an unused free slot takes the worst-served colour
            P = np.array(pal[l][1:], float)
            d = ((X[:, None, :] - P[None, :, :]) ** 2).sum(2)
            lab = d.argmin(1) + 1
            for i in free[l]:
                if not (lab == i).any():
                    j = int((d.min(1) * Wt).argmax())
                    c = tuple(int(x) for x in X[j])
                    if c not in pal[l]:
                        pal[l][i] = c
                        changed = True
                        P = np.array(pal[l][1:], float)
                        d = ((X[:, None, :] - P[None, :, :]) ** 2).sum(2)
                        lab = d.argmin(1) + 1
        if not changed:
            break
    err = sum(min(cell_err(c, k, pal[0])[0], cell_err(c, k, pal[1])[0]) for c, k in cells)
    npx = sum(k.sum() for _, k in cells)
    return pal, dict(source_lines=chosen, exact_cells=f'{exact}/{n}', rms=float(np.sqrt(err / max(npx, 1))))


def _dedupe_tiles(idx_cells, lines, tiles, lookup):
    """Cell words for one image; tiles/lookup shared across layers (tile 0 = blank)."""
    h, w = lines.shape
    out = np.zeros((h, w), np.uint16)
    for cy in range(h):
        for cx in range(w):
            t = idx_cells[cy, cx]
            if not t.any():
                continue                                    # tile 0, line 0
            word = None
            for flip, v in ((0, t), (0x800, t[:, ::-1]), (0x1000, t[::-1]), (0x1800, t[::-1, ::-1])):
                k = v.tobytes()
                if k in lookup:
                    word = lookup[k] | flip
                    break
            if word is None:
                lookup[t.tobytes()] = len(tiles)
                word = len(tiles)
                tiles.append(t.copy())
            out[cy, cx] = word | (int(lines[cy, cx]) << 13)
    return out


def _layer_bytes(cells, file_off):
    """Raw layer record for a cell map (rows/cols multiples of 4) at file offset file_off."""
    h, w = cells.shape[0] // 4, cells.shape[1] // 4
    blocks = [bytes(32)]                                    # block 0: empty
    index = {blocks[0]: 0}
    grid = np.zeros((h, w), np.uint16)
    for r in range(h):
        for c in range(w):
            b = cells[r * 4:r * 4 + 4, c * 4:c * 4 + 4].astype('>u2').tobytes()
            if b not in index:
                index[b] = len(blocks)
                blocks.append(b)
            grid[r, c] = index[b]
    if len(blocks) > 2048:
        raise ValueError(f'{len(blocks)} blocks in one layer (max 2048)')
    head = 0xC + 4 * h
    rows_off = file_off + head
    blocks_off = rows_off + h * w * 2
    out = bytearray()
    out += (w - 1).to_bytes(2, 'big') + (h - 1).to_bytes(2, 'big') + (0).to_bytes(2, 'big') + bytes(2)
    out += blocks_off.to_bytes(4, 'big')
    for r in range(h):
        out += (rows_off + r * w * 2).to_bytes(4, 'big')
    out += grid.astype('>u2').tobytes()
    out += b''.join(blocks)
    return bytes(out), len(blocks)


def _pad(img, h, w):
    out = np.zeros((h, w, 4), np.uint8)
    out[:min(h, img.shape[0]), :min(w, img.shape[1])] = img[:h, :w]
    return out


def _asm(items, org):
    """Tiny assembler: items are hex strings, ('label', name), or
    ('pc16', name) = d16(pc) displacement to name (pc = the extension word),
    ('br16', name) = 16-bit branch displacement (from the opcode + 2),
    ('abs32', name) = absolute address of name."""
    labels, pos = {}, 0
    for it in items:
        if isinstance(it, str):
            pos += len(bytes.fromhex(it))
        elif it[0] == 'label':
            labels[it[1]] = pos
        else:
            pos += 4 if it[0] == 'abs32' else 2
    out = bytearray()
    for it in items:
        if isinstance(it, str):
            out += bytes.fromhex(it)
        elif it[0] == 'label':
            continue
        elif it[0] in ('pc16', 'br16'):
            out += (labels[it[1]] - len(out)).to_bytes(2, 'big', signed=True)
        elif it[0] == 'abs32':
            out += (org + labels[it[1]]).to_bytes(4, 'big')
    return bytes(out), labels


# The Pit's fall (pit_fall): a fighter knocked out in the deciding round and
# launched high (an uppercut) does not land on the bridge: as he comes back
# down past it the floor line ($1496) drops below the screen. Without a cut,
# once he is out of sight the floor is put back and he "lands" there, below
# the screen; the round ends as usual.
# With a cut (pit_cut(), MK's Pit fatality: shots/mk_pit_fatality.mp4): as he
# falls past the bridge the stage fades out; in the dark the front layer
# object (layer id `src`) is pointed at the tall pit layer (`dst`) with row
# streaming on (flag $5F bit 2: EC's streamer does rows too, $E924, wrapping
# at the plane's 32 rows; no EC stage uses it) and redrawn; the camera is put
# on rails (its limits, -$4FA8..-$4FA2, pinned each frame: the streamer clamps
# the camera into them) at x `cx`; the winner is put off the screen (screen
# clamp off: $AB6 bit 2) and kept there; the loser is put on screen at `x`,
# `sy` px below the camera's top; the floor line becomes the pit's (`floor`).
# Fade in, then the camera goes down PIT_SCROLL px a frame to `cy` while he
# falls slower (MK's victim rises on the screen), and he drops onto the spikes.
# Round wins: $31D26 (P1), $31D28 (P2). Layer objects: list at -$5A6E(a6), id
# at $58, flags $5E/$5F, band height $E.
PIT_SOUND_TAG = 0x454B5046        # 'EKPF': the Pit fall soundtrack's disc times follow (patches.fatality_music)
PIT_FALL_FRAMES = 300             # its length (build.PIT_FALL_SECONDS)
PIT_MK_WINNERS = (23, 19, 18, 20)  # Scorpion, Raiden, Johnny Cage, Sub-Zero ($4C): build.PIT_WINS' order
PIT_FULL_HEALTH = 104             # EC's full health ($76): a flawless round
PIT_WINS_FRAMES, PIT_FLAWLESS_FRAMES = 150, 240   # the announcer parts' lengths
PIT_FEMALE = (2, 10, 21)          # Shadow, Jetta, Raven ($4C; as mkinputs.FEMALE)
PIT_SKY_FADE = {1: 1, 4: 2, 7: 3}   # counter -> the sky's colours halved (MK: 3 steps)
PIT_CUT_SWAP = 9                  # the scroll starts no sooner (the sky is dark) ...
PIT_BACK_DOWN = 40                # ... and once he has fallen back to the bridge's floor - this
PIT_SCROLL = 8                    # px a frame (MK's)
PIT_PAN = 16                      # px a frame the camera drifts to the pit's strip ...
PIT_PAN_FROM = 208                # ... once it is this far down (the bridge and the winner off the top)
PIT_LAUNCH = 16                   # px above the floor: he's been launched (his x is locked from here)
PIT_RIDE_Y = 110                  # screen y (his feet) he rides at while the camera goes down
PIT_FALL_MAX = 10                 # px a frame cap on his fall while the camera goes down (he falls ~3/4 of it: he rises slowly on the screen, as in MK)
PIT_BLOOD_FRAMES, PIT_BLOOD_EVERY, PIT_BLOOD_N = 96, 2, 3   # MK: blood ~100 frames after the landing
PIT_BLOOD_MAX, PIT_BLOOD_LIFE, PIT_BLOOD_UP = 6, 20, 12
PIT_BLOOD_SHEET, PIT_BLOOD_FRAME = 0x1B, 7     # EC's spark: a drop in colours 12/13
PIT_EFFECT = 0x24                 # plain effect object (the hit spark's)
EFFECT_SPAWN = 0x6954             # d0 type, d1 x, d2 y -> a0 (carry set: none free)
PIT_BLOOD = {(0, 12): (180, 0, 0), (0, 13): (252, 0, 0)}   # stage palette slots kept for the blood
POS_X = (0x36, 0x3A, 0x4E, 0x56, 0xB2, 0xBA)   # a fighter's x, every copy (y: +2)
POS_Y = (0x38, 0x3C, 0x52, 0x58, 0xB6, 0xBC)


def pit_cut(src, dst, cx, cy, floor, x, sy, back=0):
    return dict(src=src, dst=dst, cx=cx, cy=cy, floor=floor, x=x, sy=sy, back=back)


def pit_fall_code(cut=None):
    h = lambda v: f'{v & 0xFFFF:04x}'
    items = [
        ('label', 'watch_init'),
        '41fa', ('pc16', 'fvars'), '30ae1496',          # lea fvars(pc),a0 ; move.w $1496(a6),(a0)   the floor
        ('label', 'watch'),
        '45fa', ('pc16', 'fvars'),                      # lea fvars(pc),a2
        '47f90002e188', '7e00', '6100', ('br16', 'one'),   # P1
        '47f90002e330', '7e01', '6100', ('br16', 'one'),   # P2
    ] + (['6100', ('br16', 'pf_tick')] if cut else []) + [
        '7001', '4eb9000068d6',                         # sleep 1
        '6000', ('br16', 'watch'),
        ('label', 'one'),                               # a3 = fighter, d7 = 0/1, a2 = fvars
        '10327002',                                     # move.b 2(a2,d7.w),d0   state
        '0c000003', '6600', ('br16', 'f_s0'),
        '4a6b0076', '6f00', ('br16', 'f_hold'),         # done: a new round (health back)?
        '42327002', '4e75',                             # state 0
        ('label', 'f_s0'),
        '4a00', '6600', ('br16', 'f_s1'),
        '4a6b0076', '6e00', ('br16', 'f_ret'),          # knocked out ...
        '322b00be', '02417fff', '0c41001c', '6600', ('br16', 'f_ret'),   # ... and down ($1C) ...
        '3207', '0a410001', 'd241', '41f900031d26', '4a701000', '6700', ('br16', 'f_ret'),  # ... deciding round
        '322b0052', '3412', '0442' + h(PIT_LAUNCH), 'b242', '6c00', ('br16', 'f_ret'),   # ... launched
        '15bc00017002', '42ab005e',                     # (straight up, as MK's: no vx)
    ] + (['356b004e0010', '6100', ('br16', 'pf_play')] if cut else []) + [   # (x locked; MK's fall soundtrack)
        '4e75',
        ('label', 'f_s1'),
        '0c000001', '6600', ('br16', 'f_s2'),
        '42ab005e',                                     # clr.l $5E(a3): up and down, not off the side
    ] + (['08ee00010ab6', '6100', ('br16', 'xhold')] if cut else []) + [
        '4aab0062', '6f00', ('br16', 'f_ret'),          # coming down ...
    ] + ([] if cut else [
        '322b0052', '3412', '04420018', 'b242', '6d00', ('br16', 'f_ret'),   # ... past the bridge
    ]) + [
        '3d7c01f01496', '426a0004', '15bc00027002', '4e75',   # the floor drops away
        ('label', 'f_s2'),
    ]
    if cut is None:
        items += [
            '526a0004', '0c6a005a0004', '6c00', ('br16', 'f_fin'),
            '0c6b01300052', '6d00', ('br16', 'f_ret'),      # below the screen?
            ('label', 'f_fin'),
            '3d521496', '15bc00037002',                     # floor back (he lands below the screen)
            ('label', 'f_ret'),
            ('label', 'f_hold'),
            '4e75',
            ('label', 'fvars'), '0000000000000000',
        ]
        return items
    cx = cut['cx']
    mask = cut.get('fade_mask', 0xFFFFFFC0)
    items += [
        '0c000002', '6600', ('br16', 'f_s4'),
        '08ee00010ab6', '6100', ('br16', 'xhold'),      # MK's camera stays put; he goes straight up and down
        '526a0004', '302a0004',                         # addq.w #1,4(a2) ; move.w 4(a2),d0
    ]
    for t, k in sorted(PIT_SKY_FADE.items()):          # the sky goes dark
        items += ['0c40' + h(t), '6600', ('br16', f'f_n{t}'), f'74{k:02x}', '6100', ('br16', 'fade'),
                  '4e75', ('label', f'f_n{t}')]
    items += [
        # the scroll starts once the sky is dark and he is back down past the bridge
        '0c40' + h(PIT_CUT_SWAP), '6500', ('br16', 'f_ret'),
        '322b0052', '3412', '0442' + h(PIT_BACK_DOWN), 'b242', '6d00', ('br16', 'f_ret'),
        '48e73f3e',                                     # movem.l d2-d7/a2-a6,-(sp)
        '41eea592',                                     # lea -$5A6E(a6),a0   layer objects
        ('label', 'f_find'),
        '2010', '6700', ('br16', 'f_cam'),              # move.l (a0),d0 ; beq
        '2040',                                         # movea.l d0,a0
        # the back layer (its priority clouds would show over the pit as the
        # plane wraps): redrawn, all 32 rows ($5E bit 0), from the pit layer,
        # which plane A's pit covers
        '0c68' + h(cut.get('back', 0)) + '0058', '6600', ('br16', 'f_front'),
        '317c' + h(cut['dst']) + '0058', '00280001005e',
        '217cc000c0000016', '217c3fff3fff001a', '217cc000c000001e',
        '6000', ('br16', 'f_find'),
        ('label', 'f_front'),
        '0c68' + h(cut['src']) + '0058', '6600', ('br16', 'f_find'),
        '317c' + h(cut['dst']) + '0058',                # move.w #dst,$58(a0)
        '0028' + '0004' + '005f',                       # ori.b #4,$5F(a0)   rows streamed too
        '317c7fff000e',                                 # move.w #$7FFF,$E(a0)   the whole height
        '217cc000c0000016', '217c3fff3fff001a', '217cc000c000001e',   # redraw it all
        '6000', ('br16', 'f_find'),
        ('label', 'f_cam'),
        '356eb0740006', '356eb0700008',                 # camera y, x: where they are
        '3d7c' + h(cut['floor']) + '1496',              # the floor line: the pit's
        '277c' + h(PIT_FALL_MAX) + '0000' + '0062',     # falling about as fast as the camera goes down
        '15bc00047002',                                 # state 4: the camera goes down
        '6100', ('br16', 'rails'),
        '4cdf7cfc',                                     # movem.l (sp)+,d2-d7/a2-a6
        ('label', 'f_ret'),
        '4e75',
        # state 4: the camera goes down to cy, PIT_SCROLL a frame
        ('label', 'f_s4'),
        '0c000004', '6600', ('br16', 'f_ret'),
        '6100', ('br16', 'rails'), '6100', ('br16', 'vycap'), '6100', ('br16', 'nobounce'),
        '6100', ('br16', 'xhold'),
        # EC caps his fall below the camera's speed: he is kept from rising past PIT_RIDE_Y
        '322a0006', '0641' + h(PIT_RIDE_Y), 'b26b0052', '6f00', ('br16', 'f_ride'),
        ] + [f'3741{o:04x}' for o in POS_Y] + [
        ('label', 'f_ride'),
        '066a' + h(PIT_SCROLL) + '0006',                # addi.w #8,6(a2)
        '0c6a' + h(cut['cy']) + '0006', '6d00', ('br16', 'f_ret'),
        '357c' + h(cut['cy']) + '0006', '15bc00037002',   # there: state 3
        '42ab005e', '4e75',                             # (no more drifting)
        # after the scroll, until the next match: the camera stays; blood from
        # the spikes for PIT_BLOOD_FRAMES once he lies on them
        ('label', 'f_hold'),
        '6100', ('br16', 'vycap'), '6100', ('br16', 'rails'), '6100', ('br16', 'nobounce'),
        '4a2a000e', '6600', ('br16', 'f_down'), '6100', ('br16', 'xhold'),   # still falling: x held
        ('label', 'f_down'),
        '4a2a000e', '6700', ('br16', 'f_ret'),          # landed?
        '0c6a' + h(PIT_BLOOD_FRAMES) + '000a', '6c00', ('br16', 'f_ret'),
        '526a000a', '302a000a', '0240' + h(PIT_BLOOD_EVERY - 1), '6600', ('br16', 'f_ret'),
        '48e73f3e', '6100', ('br16', 'spray'), '4cdf7cfc', '4e75',
        # PLYR's knockdown ($17B60) replays its script once after the landing
        # (a bounce): the moment it starts, he is put back on the floor and the
        # replay ended (steps used up, $C2 = $C4; this step's ticks, task +$26, 1)
        # his x: locked (16(a2)) from the launch till he lands; the knockdown
        # script's own steps would carry him off the side of the screen
        ('label', 'xhold'),
        '302a0010',
        ] + [f'3740{o:04x}' for o in POS_X] + [
        '4e75',
        ('label', 'nobounce'),
        '302b0052', 'b06e1496', '6d00', ('br16', 'nb_air'),
        '4a2a000e', '6600', ('br16', 'f_ret'), '157c0001000e',   # landed: 14(a2) = 1
        '356b001a001a', '4e75',                         # (his landing frame, 26(a2))
        ('label', 'nb_air'),
        '0c2a0001000e', '6600', ('br16', 'f_ret'),      # landed once and in the air: the bounce
        '0c6b001c00be', '6600', ('br16', 'f_ret'),
        '322e1496',
        ] + [f'3741{o:04x}' for o in POS_Y] + [
        '42ab0062', '376b00c400c2',
        '376a001a001a',                                 # the landing frame, not the replay's first (a standing hit pose)
        '206b0088', '2050', '317c00010026',             # movea.l $88(a3),a0 ; movea.l (a0),a0 ; ticks 1
        '157c0002000e', '4e75',                         # done: 14(a2) = 2
        ('label', 'rails'),                             # camera at (8(a2) -> cx, 6(a2)) via its limits
        '322a0008',                                     # d1 = camx before
        '0c6a' + h(PIT_PAN_FROM) + '0006', '6d00', ('br16', 'r_set'),   # x held while the bridge is on screen
        '302a0008', '0440' + h(cx), '6700', ('br16', 'r_set'),   # d0 = camx - cx
        '6d00', ('br16', 'r_lo'),
        '0c40' + h(PIT_PAN), '6f00', ('br16', 'r_snap'), '046a' + h(PIT_PAN) + '0008', '6000', ('br16', 'r_set'),
        ('label', 'r_lo'),
        '0c40' + h(-PIT_PAN), '6c00', ('br16', 'r_snap'), '066a' + h(PIT_PAN) + '0008', '6000', ('br16', 'r_set'),
        ('label', 'r_snap'),
        '357c' + h(cx) + '0008',
        ('label', 'r_set'),
        '302a0008', '9041', 'd16a0010',                 # the loser (his locked x) moves with the camera's drift
        ('label', 'r_lim'),
        '3d6a0008b058', '3d6a0008b05c', '3d6a0008b070',
        '3d6a0006b05a', '3d6a0006b05e', '3d6a0006b074',
        '08ee00010ab6', '08ee00020ab6',                 # camera held, no screen clamp (the winner stays on the bridge)
        '4e75',
        ('label', 'vycap'),                             # he falls no faster than PIT_FALL_MAX
        '0c6b' + h(PIT_FALL_MAX) + '0062', '6f00', ('br16', 'f_ret'),
        '277c' + h(PIT_FALL_MAX) + '0000' + '0062', '4e75',
        # spray: PIT_BLOOD_N drops from where he lies (stage palette line 0,
        # whose colours 12/13 are blood: the drop's), at most PIT_BLOOD_MAX alive
        ('label', 'spray'),
        f'76{PIT_BLOOD_N - 1:02x}',                       # moveq #n-1,d3
        ('label', 'sp_l'),
        '45fa', ('pc16', 'fvars'),
        '0c6a' + h(PIT_BLOOD_MAX) + '000c', '6c00', ('br16', 'sp_x'),
        '322b004e', '342b0052', '0442' + h(PIT_BLOOD_UP),   # d1 = x, d2 = y - up
        '48e71030', '303c' + h(PIT_EFFECT), '4eb9' + f'{EFFECT_SPAWN:08x}', '4cdf0c08',
        '6500', ('br16', 'sp_x'),                       # bcs: no free object (movem keeps the flags)
        '117c' + h(PIT_BLOOD_SHEET) + '001a', '117c' + h(PIT_BLOOD_FRAME) + '001b',
        '317c2000001e', '317c20000020',                 # sprite line 0 (((attr >> 13) & 3) ^ 1)
        '302a000a', 'd043', '02400003', '5240',         # vx = +-(1 + (t + d3) & 3)
        '0803' + '0000', '6700', ('br16', 'sp_r'), '4440',
        ('label', 'sp_r'),
        '31400060',
        '7000', '3003', '0640' + h(4), '4440', '31400062',   # vy = -(4 + d3)
        '317c' + h(PIT_BLOOD_LIFE) + '0064',
        '526a000c',                                     # alive + 1
        '22680088', '487a', ('pc16', 'drop'), '235f0004', '42690008',   # its task: drop
        '51cb', ('br16', 'sp_l'),
        ('label', 'sp_x'),
        '4e75',
        ('label', 'drop'),                              # a5 = the drop
        '302d0060', 'd16d004e', '302d0062', 'd16d0052', '526d0062',   # x += vx; y += vy; vy += 1
        '536d0064', '6700', ('br16', 'dr_gone'),
        '7001', '4eb9000068d6', '6000', ('br16', 'drop'),
        ('label', 'dr_gone'),
        '41fa', ('pc16', 'fvars'), '5368000c',          # alive - 1
        '08ed00020082', '4ef900006a1a',                 # bset #2,$82(a5): removed; halt
        # fade: palette lines 0-1, each colour in the mask (bit 31 = colour 0)
        # halved d2 times, via set_palette
        ('label', 'fade'),
        '48e73f3e',
        '41fa', ('pc16', 'pal'), '43fa', ('pc16', 'ptmp'), '701f',
        '283c' + f'{mask:08x}',                         # move.l #mask,d4
        ('label', 'fd_l'),
        '3218', 'e38c', '6400', ('br16', 'fd_k'),       # move.w (a0)+,d1 ; lsl.l #1,d4 ; bcc: kept
        '3602', '6000', ('br16', 'fd_c'),
        ('label', 'fd_h'),
        'e2490241' + '0666',                            # lsr.w #1,d1 ; andi.w #$666,d1
        ('label', 'fd_c'),
        '51cb', ('br16', 'fd_h'),
        ('label', 'fd_k'),
        '32c1', '51c8', ('br16', 'fd_l'),
        '41fa', ('pc16', 'ptmp'), '7000', '721f', '4eb9000069fc',   # set_palette
        '4cdf7cfc', '4e75',
        # MK's Pit fall soundtrack (build.mk_jingle parts 3/4, a man's / a
        # woman's), by disc time (BIOS MSCPLAYT), as mkinputs' f_music
        ('label', 'pf_play'),
        '48e7fffe', '41fa', ('pc16', 'pf_m'), '302b004c',
        ] + sum([['0c40' + h(f), '6700', ('br16', 'pf_f')] for f in PIT_FEMALE], []) + [
        '6000', ('br16', 'pf_go'),
        ('label', 'pf_f'), '41fa', ('pc16', 'pf_w'),
        ('label', 'pf_go'),
        '4a90', '6700', ('br16', 'pf_out'),             # (no time: no sound)
        '7014', '4eb900006288',                         # MSCPLAYT
        '303c0085', '223c000002b3', '4eb900005f22',     # FDRSET: volume as EC sets it
        '357c' + h(PIT_FALL_FRAMES) + '0012',           # then the announcer, or stopped (the disc plays on)
        ('label', 'pf_out'),
        '256b008c0016', '422a0014', '422a0015',         # the winner (22(a2)); phase 0; flawless? (21(a2))
        '206b008c', '0c68' + h(PIT_FULL_HEALTH) + '0076', '6600', ('br16', 'pf_nfl'), '157c00010015',
        ('label', 'pf_nfl'),
        '4cdf7fff', '4e75',
        # once a frame: when the fall's soundtrack is over, MK's announcer for
        # an MK winner ("<NAME> WINS", "FLAWLESS VICTORY" if he has all his
        # health); then (or else) the disc is stopped (BIOS MSCSTOP)
        ('label', 'pf_tick'),
        '4a6a0012', '6700', ('br16', 'f_ret'), '536a0012', '6600', ('br16', 'f_ret'),
        '48e7fffe',
        '4a2a0014', '6600', ('br16', 'pt_stop'), '157c00010014',
        '206a0016', '3028004c', '43fa', ('pc16', 'pf_wins'),
        ] + sum([['0c40' + h(fid), '6700', ('br16', f'pt_{k}')] for k, fid in enumerate(PIT_MK_WINNERS)], []) + [
        '6000', ('br16', 'pt_stop'),
        ] + sum([[('label', f'pt_{k}'), '43e9' + h(8 * k), '6000', ('br16', 'pt_go')] for k in range(len(PIT_MK_WINNERS))], []) + [
        ('label', 'pt_go'),
        '357c' + h(PIT_WINS_FRAMES) + '0012',
        '4a2a0015', '6700', ('br16', 'pt_play'),        # (all his health when the loser was launched)
        '5889', '357c' + h(PIT_FLAWLESS_FRAMES) + '0012',   # addq.l #4,a1: the flawless one
        ('label', 'pt_play'),
        '2049', '4a90', '6700', ('br16', 'pt_stop'),
        '7014', '4eb900006288', '303c0085', '223c000002b3', '4eb900005f22',
        '6000', ('br16', 'pt_out'),
        ('label', 'pt_stop'),
        '7002', '4eb900006288',
        ('label', 'pt_out'),
        '4cdf7fff', '4e75',
        f'{PIT_SOUND_TAG:08x}', ('label', 'pf_m'), '00000000', ('label', 'pf_w'), '00000000',
        ('label', 'pf_wins'), '00000000' * (2 * len(PIT_MK_WINNERS)),   # (build.PIT_WINS: plain, flawless)
        ('label', 'fvars'), '00' * 28,
        ('label', 'ptmp'), '00' * 64,
    ]
    return items


PIT_FALL = pit_fall_code()


def _m68k_bgi(template_bgi, descriptors, palette_hw, settle=300, pit_fall=False):
    """Minimal BGI for a stage whose init (SUB.BIN) is kept:
      $3400A  Overkill check, both entries (+0, +2) return carry clear;
      each descriptor the init spawns: the template's 34 bytes, code pointer
              replaced by `task`;
      task    sets $14FA(a6), hides its object (x, y = $7000), then for
              `settle` frames re-applies the stage palette (lines 0-1) to
              $1502(a6) and set_palette whenever the init's own palette load
              (SUB.BIN table, $12C3C/$702E) has overwritten it; then halts."""
    hi = max(d - BGI_BASE for d in descriptors) + 0x22 if descriptors else 0x12
    code_off = (max(hi, 0x12) + 1) & ~1
    out = bytearray(code_off)
    out[0:10] = bytes.fromhex('00000000001800000000')
    out[0x0A:0x12] = bytes.fromhex('4e71' '44fc0000' '4e75')          # +0: nop; +2: ccr = 0; rts
    org = BGI_BASE + code_off
    code, lab = _asm([
        ('label', 'task'),
        '2d7c0003400a14fa',                  # move.l #$3400A,$14FA(a6)
        '08ed0006002a',                      # bset #6,$2A(a5)
        '3b7c7000004e', '3b7c70000052',      # move.w #$7000,$4E(a5) / $52(a5)
        '33fc' + f'{settle:04x}', ('abs32', 'count'),   # move.w #settle,count
        ('label', 'loop'),
        '41fa', ('pc16', 'pal'),             # lea pal(pc),a0
        '43ee1502',                          # lea $1502(a6),a1
        '700f',                              # moveq #15,d0
        ('label', 'cmp'),
        'b388',                              # cmpm.l (a0)+,(a1)+
        '56c8fffc',                          # dbne d0,cmp
        '6700', ('br16', 'same'),            # beq.w same
        '41fa', ('pc16', 'pal'),             # lea pal(pc),a0
        '43ee1502', '700f',                  # lea $1502(a6),a1 ; moveq #15,d0
        '22d8', '51c8fffc',                  # copy: move.l (a0)+,(a1)+ ; dbra d0,copy
        '41fa', ('pc16', 'pal'),             # lea pal(pc),a0
        '7000', '721f',                      # moveq #0,d0 ; moveq #31,d1
        '4eb9000069fc',                      # jsr set_palette
        ('label', 'same'),
        '7001', '4eb9000068d6',              # moveq #1,d0 ; jsr sleep
        '5379', ('abs32', 'count'),          # subq.w #1,count
        '6600', ('br16', 'loop'),            # bne.w loop
    ] + (['6000', ('br16', 'watch_init')] + pit_fall_code(pit_fall if isinstance(pit_fall, dict) else None)
         if pit_fall else ['4ef900006a1a']) + [   # watch / jmp halt
        ('label', 'count'), '0000',
        ('label', 'pal'), ''.join(f'{w:04x}' for w in palette_hw),
    ], org)
    # br16 displacements are relative to the opcode word + 2 = position of the extension word
    for d in descriptors:
        o = d - BGI_BASE
        desc = bytearray(template_bgi[o:o + 0x22])
        desc[0x1E:0x22] = (org + lab['task']).to_bytes(4, 'big')
        out[o:o + 0x22] = desc
    return bytes(out + code)


def build(plane_a_rgba, plane_b_rgba, cram, stage='SHA', template=None, offset=(0, 0), pit_fall=False,
          backdrop=0, layer_images=None, layer_prio=None, fixed_extra=None, fade=None,
          blank_tile_slots=()):
    """Build NAME.BG and NAME.BGI for `stage` (whose init in SUB.BIN stays as is)
    from a front (plane A) and back (plane B) RGBA image in world pixels and a
    64-word cram (vdp.py packing). layer_images {layer id: RGBA in world
    pixels} gives a layer's art outright (row 0 = its object's y) instead of
    cutting it from the plane image. layer_prio {layer id: (x0, y0, x1, y1)}
    sets the priority bit on that layer's cells in the pixel box (drawn over
    the fighters). fixed_extra {(line, index): rgb} reserves more palette
    slots. fade {'layers': [ids], 'rows': {id: y}}: the colours only those
    layers (and those layers' rows above y) use - the sky - become
    pit_fall's fade_mask (bit 31 = colour 0). blank_tile_slots: the
    template's tile chunks (by slot) cut to one blank tile (the replaced
    stage's own sprite art, unused: file size and VRAM). Returns (bg_bytes,
    bgi_bytes, report)."""
    layer_images = {k: np.asarray(v, np.uint8) for k, v in (layer_images or {}).items()}
    if template is None:
        template = load_template(stage)
    sub, tbg, tbgi = template['sub'], template['bg'], template['bgi']
    names = file_list(sub)
    mode = [m for m in STAGE_MODES if names[parse_init(sub, m)['bg_file'] or 0] == stage + '.BG'][0]
    init = parse_init(sub, mode)
    bad = [r for r in init['bgi_refs'] if r[0] != 'descriptor']
    if bad:
        raise NotImplementedError(f'{stage}: init points into the BGI for {bad}')
    P = parse_bg(tbg)
    hdr = P['bg']
    ids = sorted({o['id'] for o in init['objects'] if o['id']})
    if ids and (ids[0] < hdr['first_id'] or ids[-1] >= hdr['first_id'] + len(hdr['layers'])):
        raise ValueError(f'{stage}: init uses layer ids {ids}, BG has {hdr["first_id"]}+{len(hdr["layers"])}')

    imgs = {'A': np.asarray(plane_a_rgba, np.uint8), 'B': np.asarray(plane_b_rgba, np.uint8)}
    dx, dy = offset
    for k in imgs:                                         # world = image shifted by offset
        im = imgs[k]
        w = np.zeros((im.shape[0] + dy, im.shape[1] + dx, 4), np.uint8)
        w[max(dy, 0):, max(dx, 0):] = im[max(-dy, 0):, max(-dx, 0):]
        imgs[k] = w
    # the game's own colours: line 0 colour 1 (shadow) and line 1 colours 10-15 (HUD),
    # from the replaced stage's palette table in SUB.BIN
    tpal = [W(sub, init['palette']['addr'] - SUB_BASE + 2 * i) for i in range(32)]
    fixed = {(0, 1): hw_to_rgb(tpal[1])}
    fixed.update({(1, i): hw_to_rgb(tpal[16 + i]) for i in range(10, 16)})
    fixed.update(fixed_extra or {})
    line_rgb, pinfo = fit_palettes(list(imgs.values()) + list(layer_images.values()), cram, fixed)
    pal_hw = [rgb_to_hw(c) for line in line_rgb for c in line]
    pal_hw[0] = packed_to_hw(cram[backdrop])
    pal_hw[16] = tpal[16]

    # one layer per id the init streams, cut from its plane image at the object's origin
    tiles, lookup = [np.zeros((8, 8), np.uint8)], {bytes(64): 0}
    layer_cells_by_id = {}
    used = {'sky': {0}, 'kept': set()}             # colour 0 of line 0: the backdrop
    for lid in range(hdr['first_id'], hdr['first_id'] + len(hdr['layers'])):
        objs = [o for o in init['objects'] if o['id'] == lid]
        if not objs:
            layer_cells_by_id[lid] = np.zeros((4, 4), np.uint16)
            continue
        o = objs[0]
        if lid in layer_images:
            crop = layer_images[lid]
        else:
            src = imgs[o['plane']]
            y0 = o['y']
            y1 = src.shape[0] if o['ext_y'] >= 0x4000 else min(src.shape[0], y0 + o['ext_y'] + 1)
            x0 = max(o['x'], 0)
            crop = src[y0:y1, x0:]
        hh = max(32, (crop.shape[0] + 31) // 32 * 32)
        ww = max(32, (crop.shape[1] + 31) // 32 * 32)
        crop = _pad(crop, hh, ww)
        lines, idx = _cells_from_rgba(crop, line_rgb)
        if fade:
            split = fade.get('rows', {}).get(lid, 0) // 8
            for cy in range(lines.shape[0]):
                key = 'sky' if lid in fade['layers'] or cy < split else 'kept'
                for cx in range(lines.shape[1]):
                    for c in np.unique(idx[cy, cx]):
                        if c:
                            used[key].add(int(lines[cy, cx]) * 16 + int(c))
        layer_cells_by_id[lid] = _dedupe_tiles(idx, lines, tiles, lookup)
        if lid in (layer_prio or {}):
            x0, y0, x1, y1 = layer_prio[lid]
            layer_cells_by_id[lid][y0 // 8:(y1 + 7) // 8, x0 // 8:(x1 + 7) // 8] |= 0x8000
    if len(tiles) > 2047:
        raise ValueError(f'{len(tiles)} tiles (max 2047 in one tile chunk)')
    tile_bytes = encode_tiles(tiles)

    # assemble: template chunks (shared art, stage sprites) minus its map and map tiles
    out = bytearray()
    for o, n, t in P['chunks']:
        if t == 8 or (t == 0 and W(tbg, o + 0xA) // 8 == hdr['tile_slot']):
            continue
        if t == 0 and W(tbg, o + 0xA) // 8 in blank_tile_slots:
            c0 = len(out)
            out += (0x14 + 32).to_bytes(4, 'big') + tbg[o + 4:o + 0xE]
            out += (c0 + 0x14).to_bytes(4, 'big') + (32).to_bytes(2, 'big') + bytes(32)
            continue
        out += tbg[o:o + n]
    c8 = len(out)
    nl = len(hdr['layers'])
    head = 0x1E + 2 * nl + 2 + 8 * nl
    body = bytearray()
    recs = []
    nblocks = {}
    for j in range(nl):
        lid = hdr['first_id'] + j
        off = c8 + head + len(body)
        lb, nb = _layer_bytes(layer_cells_by_id[lid], off)
        nblocks[lid] = nb
        recs.append((4, off, len(lb)))
        body += lb
        if len(body) & 1:
            body += b'\0'
    ch = bytearray()
    ch += (head + len(body)).to_bytes(4, 'big') + (8).to_bytes(2, 'big') + bytes(4)
    ch += (hdr['slot'] * 4).to_bytes(2, 'big') + hdr['first_id'].to_bytes(2, 'big')
    ch += hdr['tile_slot'].to_bytes(2, 'big') + bytes(6) + len(tile_bytes).to_bytes(2, 'big')
    ch += bytes(2) + hdr['tile_slot'].to_bytes(2, 'big') + b'\xff\xff'
    for j in range(nl):
        ch += (hdr['first_id'] + j).to_bytes(2, 'big')
    ch += b'\xff\xff'
    for t, off, size in recs:
        ch += t.to_bytes(2, 'big') + off.to_bytes(4, 'big') + size.to_bytes(2, 'big')
    assert len(ch) == head
    out += ch + body
    t0 = len(out)
    out += (0x14 + len(tile_bytes)).to_bytes(4, 'big') + bytes(2) + bytes(4)
    out += (hdr['tile_slot'] * 8).to_bytes(2, 'big') + (4).to_bytes(2, 'big')
    out += (t0 + 0x14).to_bytes(4, 'big') + len(tile_bytes).to_bytes(2, 'big') + tile_bytes
    out += bytes(4)
    descs = [d['addr'] for d in init['descriptors'] if d['addr'] and BGI_BASE <= d['addr'] < BG_BASE]
    if fade and isinstance(pit_fall, dict):
        sky = used['sky'] - used['kept'] - {16 + i for i in range(10, 16)} - {l * 16 + i for l, i in fixed_extra or {}}
        pit_fall = dict(pit_fall, fade_mask=sum(1 << (31 - c) for c in sky))
    bgi = _m68k_bgi(tbgi, descs, pal_hw, pit_fall=pit_fall)
    report = dict(mode=mode, tiles=len(tiles), tile_bytes=len(tile_bytes), bg_bytes=len(out),
                  map_end=BG_BASE + t0, blocks=nblocks, palette=pinfo, pal_hw=[f'{w:03x}' for w in pal_hw],
                  bgi_bytes=len(bgi), objects=init['objects'], camera=init.get('camera'))
    if BG_BASE + t0 > 0x40800:
        raise ValueError('map data runs past $40800 (the AI loads there)')
    return bytes(out), bgi, report


def camera_patch(sub, stage, xmax=None, start_x=None):
    """SUB.BIN patches for a stage's camera: [(file offset, new bytes, expected bytes)].
    xmax = right camera limit (art width - 320); start_x = camera x at round start."""
    names = file_list(sub)
    mode = [m for m in STAGE_MODES if names[parse_init(sub, m)['bg_file'] or 0] == stage + '.BG'][0]
    a = stage_inits(sub)[mode] - SUB_BASE
    assert W(sub, a) == 0x4EB9 and L(sub, a + 2) == API['e00e']
    out = []
    if xmax is not None:
        out.append((a + 10, xmax.to_bytes(2, 'big'), sub[a + 10:a + 12]))
    if start_x is not None:                        # move.w #x,-$4F90(a6) = 3D7C xxxx B070
        k = sub.find(b'\x3d\x7c', a)
        while k >= 0 and k - a < 0x600 and sub[k + 4:k + 6] != b'\xb0\x70':
            k = sub.find(b'\x3d\x7c', k + 2)
        if k >= 0 and k - a < 0x600:
            out.append((k + 2, start_x.to_bytes(2, 'big'), sub[k + 2:k + 4]))
    return out


def load_template(stage):
    from inputs import require
    from disc import Disc
    d = Disc(require('ec_us').cue)
    return dict(sub=d.read_file('SUB.BIN'), bg=d.read_file(stage + '.BG'), bgi=d.read_file(stage + '.BGI'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['info', 'render', 'build'])
    ap.add_argument('stage')
    ap.add_argument('args', nargs='*')
    ap.add_argument('--dx', type=int, default=0)
    ap.add_argument('--dy', type=int, default=0)
    a = ap.parse_args()
    t = load_template(a.stage)
    if a.cmd == 'build':
        import json
        from PIL import Image
        pa, pb, cj, out = a.args
        bg, bgi, rep = build(np.array(Image.open(pa).convert('RGBA')), np.array(Image.open(pb).convert('RGBA')),
                             json.load(open(cj)), stage=a.stage, template=t, offset=(a.dx, a.dy))
        os.makedirs(out, exist_ok=True)
        open(os.path.join(out, a.stage + '.BG'), 'wb').write(bg)
        open(os.path.join(out, a.stage + '.BGI'), 'wb').write(bgi)
        print({k: v for k, v in rep.items() if k != 'objects'})
        return
    a.out = a.args[0] if a.args else None
    sub = t['sub']
    names = file_list(sub)
    mode = [m for m in STAGE_MODES if names[parse_init(sub, m)['bg_file'] or 0] == a.stage + '.BG'][0]
    init = parse_init(sub, mode)
    P = parse_bg(t['bg'])
    if a.cmd == 'info':
        print(f"{a.stage}: mode ${mode:02X}, init ${init['init']:X}, BG slot {init.get('slot')}, camera {init.get('camera')}")
        for o in init['objects']:
            print('  object', {k: (hex(v) if isinstance(v, int) else v) for k, v in o.items()})
        print('  descriptors', init['descriptors'], 'bgi refs', init['bgi_refs'], 'palette', init.get('palette'))
        print('  BG', {k: v for k, v in P['bg'].items() if k != 'layers'})
        for r in P['bg']['layers']:
            lay = read_layer(t['bg'], r)
            print(f"    layer {r['id']:#04x}: {lay['w']}x{lay['h']} blocks, {len(lay['blocks'])} blocks")
        return
    from PIL import Image
    os.makedirs(a.out, exist_ok=True)
    pal = [hw_to_rgb(W(sub, init['palette']['addr'] - SUB_BASE + 2 * i)) for i in range(32)] + [(0, 0, 0)] * 32
    tiles = decode_tiles(P['tiles'][P['bg']['tile_slot']]['data'])
    for r in P['bg']['layers']:
        lay = read_layer(t['bg'], r)
        img = render_cells(layer_cells(lay), tiles, pal)
        Image.fromarray(img, 'RGBA').save(os.path.join(a.out, f'{a.stage}_layer_{r["id"]:02x}.png'))
    # the planes as the init lays them out (each object's band, scroll offset 0)
    for plane in 'AB':
        canvas = np.zeros((256, 1024 + 256, 4), np.uint8)
        for o in init['objects']:
            if o['plane'] != plane or not o['id']:
                continue
            lay = read_layer(t['bg'], [r for r in P['bg']['layers'] if r['id'] == o['id']][0])
            img = render_cells(layer_cells(lay), tiles, pal)
            y1 = 256 if o['ext_y'] >= 0x4000 else min(256, o['y'] + o['ext_y'] + 1)
            hh = max(0, min(img.shape[0], y1 - o['y']))
            ww = min(img.shape[1], canvas.shape[1])
            canvas[o['y']:o['y'] + hh, :ww] = img[:hh, :ww]
        Image.fromarray(canvas, 'RGBA').save(os.path.join(a.out, f'{a.stage}_plane_{plane}.png'))
    print('wrote', a.out)


if __name__ == '__main__':
    main()
