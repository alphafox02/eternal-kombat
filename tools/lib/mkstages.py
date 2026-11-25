# SPDX-License-Identifier: MIT
"""MK CD's other stages - the Courtyard, Palace Gates, Warrior Shrine, Throne Room and Goro's Lair -
as EC stages, and which stage a fight is on.

MK CD's 2-player battles go round its six stages in order (tools/capture/mkstagestates.py): the
Courtyard (MK track 4), the Palace Gates (6), the Warrior Shrine (3), the Pit (4), the Throne Room
(7), Goro's Lair (3). The Pit is its own EC stage (patches.pit_stage, mode $1F); the other five
share one stage mode, Chin Wo's ($16, his JET.BG / JET.BGI: since his slot is Raiden's, nobody's
home - nothing else reaches it):
  - JET.BG and JET.BGI become packs: each stage's .BG (.BGI) in turn, each from a sector start;
  - mode $16's init (SUB.BIN, in its own place) becomes a dispatcher: for the stage picked
    (VAR) it sets the camera limits, the stage card (the cards' table, $B0CC by mode) and the
    music track (SUB $AC12 by stage), points EC's file table (PRG $12E9E, 8 bytes a file: sector,
    sectors) at that stage's parts of the packs, loads them (as every init: not when a round
    restarts, $AB7 bit 5), and jumps to the rest of the stage's init, in its own .BGI;
  - that rest (body_code) is generated: one layer object per scroll band MK's camera has
    (data/mk_stages/<stage>.json, measured: each band at MK's rate, its art MK's plane rows
    unwrapped from where MK's camera starts), the floor line, the camera's start, the palette.

Which stage (pick_code: GAME starts every fight with jmp $6C98, d0 = the stage mode it chose;
that entry jumps here first):
  - the bosses' arenas (modes $11, $12) stay;
  - two EC fighters: EC's choice, except an MK stage (the Pit: an MK fighter's slot's home, from
    the Duel's RANDOM background) - then EC's own random stage (the Tournament's list);
  - an MK fighter on either side: one of MK's six at random (never the last one again), except
    a Duel whose BACKGROUND SETTING names a stage (that stage) or is PLAYER 2 with an EC player 2
    (his home), and Reptile's secret Contest match (the Pit, as MK's). The game is told by the
    fight start that called (its return address in $143C).
"""
import json, os
import numpy as np
from PIL import Image

STAGES = (   # MK CD's 2-player order: (key, card, MK track)
    ('courtyard', 'COURTYARD', 4),
    ('gates', 'PALACE GATES', 6),
    ('shrine', 'WARRIOR SHRINE', 3),
    ('pit', 'THE PIT', 4),
    ('throne', 'THRONE ROOM', 7),
    ('lair', "GORO'S LAIR", 3),
)
PACKED = tuple(k for k, _, _ in STAGES if k != 'pit')
MODE = 0x16                       # Chin Wo's stage mode: the packed stages'
HOST = 'JET'                      # its files (JET.BG / .BGI) and template
HOST_FILES = (0x25, 0x26)         # their file ids (BG, BGI)
FILE_TABLE = 0x12E9E              # PRG RAM: EC's file table, 8 bytes a file id (sector, sectors)
CARDS = 0xB0CC                    # SUB.BIN: the stage cards' table (a long per mode - $11)
MUSIC_IDS, MUSIC_TRACKS = 0xABEC, 0xAC12   # SUB.BIN: stage modes ($FFFF-ended), their CD tracks
PICK_ENTRY = 0x6C98               # SUB.BIN: GAME's fight start (jmp $7134)
FIGHT_START = 0x7134
VSCROLL = 16                      # MK's camera y on every stage (VSRAM; measured)
# MK's fighters' lowest pixel on screen, standing (tools/capture/mkstagecamera.py battles; a
# fight's start): the floor line goes where ours stand the same
MK_FEET = {'courtyard': 214, 'gates': 217, 'shrine': 213, 'throne': 202, 'lair': 212}
MAX_LAYERS = 7                    # Chin Wo's BG's layer ids ($44-$4A): ids are numbered across stages


def _json(key):
    from inputs import ROOT
    return json.load(open(os.path.join(ROOT, 'data', 'mk_stages', f'{key}.json')))


def art(key):
    """MK's planes A and B (RGBA, 1024 x 256), its CRAM (64) and the planes' high-priority cells."""
    from inputs import ROOT
    d = os.path.join(ROOT, 'extracted', 'mk_stages', key)
    if not os.path.exists(os.path.join(d, 'plane_a.png')):
        raise SystemExit(f'missing MK\'s {key}: run  .venv/bin/python tools/prepare.py')
    a = np.array(Image.open(os.path.join(d, 'plane_a.png')).convert('RGBA'))
    b = np.array(Image.open(os.path.join(d, 'plane_b.png')).convert('RGBA'))
    b[:8 * _json(key)['hud_rows']] = 0                     # (MK's HUD rows: the Lair's decoder keeps them)
    cram = json.load(open(os.path.join(d, 'cram.json')))
    m = _json(key)
    prio = {p: (np.array(m['planes'][p]) >> 15) & 1 for p in 'AB'}
    return {'A': a, 'B': b}, cram, prio


def bands(key):
    """MK's scroll bands per plane, merged and with their art: dicts plane, y (world row), h, rate,
    art (RGBA strip, row 0 = y; column 0 = what the band shows at the camera's left stop), prio
    (its cells' priority). Bands that show nothing are left out."""
    m = _json(key)
    cam = m['camera']
    lo, hi = cam['camera']
    span = hi - lo
    planes, _, prio = art(key)
    out = []
    for p in 'AB':
        img = planes[p]
        pix_prio = np.kron(prio[p], np.ones((8, 8), np.uint8))
        for b in cam['plane_' + p.lower()]:
            l0, l1 = b['lines']
            y0, y1 = l0 + VSCROLL, l1 + VSCROLL + 1
            start = (-b['scroll_at_left']) % img.shape[1]
            width = int(np.ceil(b['rate'] * span)) + 320 + 32
            cols = (start + np.arange(width)) % img.shape[1]
            strip = img[y0:y1][:, cols]
            if not strip[:, :, 3].any():
                continue
            out.append(dict(plane=p, y=y0, h=y1 - y0, rate=b['rate'], art=strip,
                            pprio=pix_prio[y0:y1][:, cols], parts=[(p, y0, y1, start, width)]))
    # contiguous bands of one plane at one rate: one layer
    merged = []
    for b in out:
        last = merged[-1] if merged else None
        if last and last['plane'] == b['plane'] and last['rate'] == b['rate'] and last['y'] + last['h'] == b['y']:
            w = max(last['art'].shape[1], b['art'].shape[1])
            pad = lambda a: np.pad(a, ((0, 0), (0, w - a.shape[1])) + ((0, 0),) * (a.ndim - 2))
            last['art'] = np.concatenate([pad(last['art']), pad(b['art'])])
            last['pprio'] = np.concatenate([pad(last['pprio']), pad(b['pprio'])])
            last['h'] += b['h']
            last['parts'] = last['parts'] + b['parts']
        else:
            merged.append(dict(b))
    # too many: the two neighbours (one plane) whose rates are closest share one (their mean)
    while len(merged) > MAX_LAYERS:
        pairs = [(abs(merged[i]['rate'] - merged[i + 1]['rate']), i) for i in range(len(merged) - 1)
                 if merged[i]['plane'] == merged[i + 1]['plane'] and merged[i]['y'] + merged[i]['h'] == merged[i + 1]['y']]
        _, i = min(pairs)
        a, b = merged[i], merged[i + 1]
        rate = round((a['rate'] * a['h'] + b['rate'] * b['h']) / (a['h'] + b['h']), 3)
        w = max(a['art'].shape[1], b['art'].shape[1])
        pad = lambda x: np.pad(x, ((0, 0), (0, w - x.shape[1])) + ((0, 0),) * (x.ndim - 2))
        merged[i:i + 2] = [dict(plane=a['plane'], y=a['y'], h=a['h'] + b['h'], rate=rate,
                                art=np.concatenate([pad(a['art']), pad(b['art'])]),
                                pprio=np.concatenate([pad(a['pprio']), pad(b['pprio'])]),
                                parts=a['parts'] + b['parts'])]
    for b in merged:
        # a cell is high priority when most of its drawn pixels are (the art's cells needn't fall
        # on MK's: a band's unwrapped start is any pixel)
        h8, w8 = (b['h'] + 7) // 8, (b['art'].shape[1] + 7) // 8
        drawn = np.zeros((h8 * 8, w8 * 8), bool)
        hp = np.zeros((h8 * 8, w8 * 8), bool)
        drawn[:b['h'], :b['art'].shape[1]] = b['art'][:, :, 3] > 0
        hp[:b['h'], :b['art'].shape[1]] = (b['pprio'] > 0) & (b['art'][:, :, 3] > 0)
        b['cell_prio'] = (hp.reshape(h8, 8, w8, 8).sum((1, 3)) * 2 > drawn.reshape(h8, 8, w8, 8).sum((1, 3))).astype(np.uint8)
    return merged, (lo, hi)


def layer_art(planes, b):
    """A layer's art cut from planes (A, B: RGBA) as bands() cut it: its parts, each MK plane rows
    unwrapped from the camera's left stop, one under another."""
    arts = []
    for p, y0, y1, start, width in b['parts']:
        img = planes[p]
        arts.append(img[y0:y1][:, (start + np.arange(width)) % img.shape[1]])
    w = max(x.shape[1] for x in arts)
    return np.concatenate([np.pad(x, ((0, 0), (0, w - x.shape[1]), (0, 0))) for x in arts])


def state_planes(key, a=None, planes=None, cram=None):
    """Per animation element, MK's planes (A, B: RGBA) with it in each of its states."""
    from inputs import ROOT
    if a is None:
        path = os.path.join(ROOT, 'extracted', 'mk_stages', key, 'anim.json')
        if not os.path.exists(path):
            return []
        a = json.load(open(path))
        planes, cram, _ = art(key)
    rgb = np.array([((v & 7) * 36, ((v >> 3) & 7) * 36, ((v >> 6) & 7) * 36) for v in cram], np.uint8)
    base = _json(key)['tile_base']

    def paint(pl, p, y, x, word, px):
        t = np.array(px, np.uint8).reshape(8, 8)
        if word & 0x800:
            t = t[:, ::-1]
        if word & 0x1000:
            t = t[::-1]
        cell = pl[p][y * 8:y * 8 + 8, x * 8:x * 8 + 8]
        cell[:, :, :3] = rgb[((word >> 13) & 3) * 16 + t]
        cell[:, :, 3] = (t > 0) * 255
    out = []
    for e in a['elements']:
        states = []
        for st in e['states']:
            pl = {p: planes[p].copy() for p in 'AB'}
            if e['kind'] == 'cells':
                for (y, x), (word, px) in zip(e['cells'], st):
                    paint(pl, e['plane'], y, x, word, px)
            else:
                for p, y, x, word in e['shows']:
                    paint(pl, p, y, x, word, st[e['tiles'].index((word & 0x7FF) - base)])
            states.append(pl)
        out.append(states)
    return out


def animation(key, layers):
    """MK's animation (extracted/mk_stages/<stage>/anim.json) in our layers: per element, its runs
    (MK's own sequence: state, frames) and, per layer, its cells (those whose art changes between
    its states) with their art in every state (RGBA 8 x 8)."""
    from inputs import ROOT
    path = os.path.join(ROOT, 'extracted', 'mk_stages', key, 'anim.json')
    if not os.path.exists(path):
        return []
    a = json.load(open(path))
    planes, cram, _ = art(key)
    out = []
    for e, states in zip(a['elements'], state_planes(key, a, planes, cram)):
        cells = {}
        for k, b in enumerate(layers):
            arts = [layer_art(pl, b) for pl in states]
            h8, w8 = arts[0].shape[0] // 8, arts[0].shape[1] // 8
            for cy in range(h8):
                for cx in range(w8):
                    cs = [x[cy * 8:cy * 8 + 8, cx * 8:cx * 8 + 8] for x in arts]
                    if any(not np.array_equal(cs[0], c_) for c_ in cs[1:]):
                        cells[(k, cy, cx)] = cs
        out.append(dict(runs=loop(e['runs']), cells=cells, nstates=len(states)))
    return out


ANIM_LOOP = 900                   # frames of MK's recorded animation looped (room: the Gates' torches' sequence)


def loop(runs):
    """MK's sequence (state, frames) up to ANIM_LOOP frames, its last run cut there."""
    out, t = [], 0
    for st, n in runs:
        if t >= ANIM_LOOP:
            break
        out.append([st, min(n, ANIM_LOOP - t)])
        t += n
    return out


def init_info(key, layers, cam, template_sub):
    """ecstage.build's view of the stage's init (as parse_init gives): its layer objects, the one
    descriptor it spawns (the BGI's palette task), the palette table whose HUD and shadow colours
    are kept (the host's)."""
    import ecstage
    host = ecstage.parse_init(template_sub, MODE)
    first = ecstage.parse_bg(_host_file('BG'))['bg']['first_id']
    objs = []
    for k, b in enumerate(layers):
        last = not any(o['plane'] == b['plane'] and o['y'] > b['y'] for o in layers)
        # x mode 4 moves a layer by (camera - x3c) * speed / 1024 on top of the camera's own
        # movement (measured: speed 0 follows the camera): MK's rate r is speed (r - 1) * 1024.
        # The camera's y stays 0 (MK's never moves): an object's rows are screen lines on both
        # planes (with the camera's y at 16, plane B's VSRAM stayed 0 while its bands' lines
        # were taken 16 up - each band scrolled 16 lines of the next one's art)
        y = b['y'] - VSCROLL
        objs.append(dict(plane=b['plane'], x=0, y=y, ext_x=0x7FFF,
                         ext_y=(0x7F00 | (0xFF - y)) if last else b['h'] - 1,
                         id=first + k, flags=0x1E, xmode=4, xspeed=int(round((b['rate'] - 1) * 1024)), ymode=0, x3c=0))
    lo, hi = cam
    return dict(mode=MODE, init=host['init'], files=host['files'], objects=objs, descriptors=host['descriptors'][:1],
                bgi_refs=host['bgi_refs'][:1], sheets=host['sheets'], palette=host['palette'],
                camera=(0, 0, hi - lo, 0), bg_file=host['bg_file'], bgi_file=host['bgi_file'])


_HOST = {}


def _host_file(ext):
    if ext not in _HOST:
        from disc import Disc
        from inputs import require
        d = Disc(require('ec_us').cue)
        _HOST.update(BG=d.read_file(HOST + '.BG'), BGI=d.read_file(HOST + '.BGI'), SUB=d.read_file('SUB.BIN'))
        d.close()
    return _HOST[ext]


def body_code(org, info, floor, start_x, pal_hw, template_sub):
    """The init's rest (after the files are in), at org in the stage's BGI: the layer objects, the
    host's sheet lists and its first descriptor's spawn (the palette task), the floor line, the
    camera's start, the palette, then EC's usual end (as the host's: $B708, $105E8, $B3E4, $AB76,
    $702E, $ABA2, $BDA4) and jmp $6D8C."""
    import mkinputs, stageinit, ecstage
    a = mkinputs.Asm(org)
    for o in info['objects']:
        a.jsr(0xE062)
        a.w({'A': 0, 'B': 2}[o['plane']], o['x'] & 0xFFFF, o['y'], o['ext_x'], o['ext_y'])
        a.w(0x317C, o['flags'], 0x005E)                     # move.w #flags,$5E(a0)
        a.w(0x317C, o['id'], 0x0058)                        # move.w #id,$58(a0)
        a.w(0x117C, o['xmode'], 0x0036)                     # move.b #xmode,$36(a0)
        a.w(0x317C, o['xspeed'] & 0xFFFF, 0x0038)           # move.w #speed,$38(a0)
        a.w(0x317C, o['x3c'] & 0xFFFF, 0x003C)              # move.w #x3c,$3C(a0)
    a.jsr(0xE046)
    # the host's sprite sheet lists (its stage objects' art: the descriptor's object needs its sheet)
    sub = template_sub
    sp = stageinit.split(sub, info['init'], 0x88FC)
    pc = sp['body']
    cs = stageinit._cs()
    while pc < sp['end']:
        i, n = stageinit._one(cs, sub, pc)
        if i.mnemonic == 'jsr' and stageinit._target(i) == stageinit.LIST_CALL:
            a.out += sub[pc - 0x6000:pc - 0x6000 + n]
        pc += n
    a.w(0x303C, 2); a.jsr(0xC0FA)                           # wait 2
    a.jsr(0xB708)
    for d in info['descriptors']:                           # (the palette task's; the animation's)
        a.w(0x303C, d['d0']); a.w(0x323C, d['x']); a.w(0x343C, d['y'])
        a.w(0x227C); a.l(d['addr'] or 0)                    # movea.l #descriptor,a1
        a.jsr(0x1064A)
    a.w(0x303C, 0x20); a.w(0x323C, 0); a.w(0x343C, 0); a.jsr(0x105E8)
    a.w(0x303C, 1); a.jsr(0xC0FA)                           # wait 1
    a.w(0x3D7C, floor, 0x1496)                              # move.w #floor,$1496(a6)
    a.w(0x3D7C, start_x, 0xB070)                            # the camera's start x, y
    a.w(0x3D7C, 0, 0xB074)
    a.w(0x426E, 0x1A1E)                                     # clr.w $1A1E(a6)
    a.jsr(0xB3E4)
    a.w(0x303C, 3); a.jsr(0xC0FA)                           # wait 3
    a.jsr(0xAB76)
    a.w(0x303C, 0); a.w(0x323C, 0x1F)
    a.w(0x207C)
    pal_at = len(a.out)
    a.l(0)                                                  # movea.l #pal,a0 (below)
    a.jsr(0x12C3C)
    a.jsr(0x702E)
    a.jsr(0xABA2)
    a.jsr(0xBDA4)
    a.w(0x426E, 0x146C)                                     # clr.w $146C(a6)
    a.jmp(0x6D8C)
    code = bytearray(a.build())
    code[pal_at:pal_at + 4] = (org + len(code)).to_bytes(4, 'big')
    code += b''.join(w.to_bytes(2, 'big') for w in pal_hw)
    return bytes(code)


def build_stage(key, template_sub):
    """(BG bytes, BGI bytes with its init's rest appended, record for the dispatcher, report)."""
    import ecstage
    layers, cam = bands(key)
    info = init_info(key, layers, cam, template_sub)
    planes, cram, _ = art(key)
    tmpl = dict(sub=template_sub, bg=_host_file('BG'), bgi=_host_file('BGI'))
    P = ecstage.parse_bg(tmpl['bg'])
    keep = P['bg']['tile_slot']
    sprite_slots = tuple(sorted({W(tmpl['bg'], o + 0xA) // 8 for o, n, t in P['chunks'] if t == 0} - {keep}))
    lids = {o['id']: k for k, o in enumerate(info['objects'])}
    anim = animation(key, layers)
    # an animated cell's tile: shared by the cells with the same art in every state (the Courtyard's
    # monks repeat 12 tiles along the row), each element's together
    own, keyof = {}, {}
    for e, el in enumerate(anim):
        for (k, cy, cx), cs in el['cells'].items():
            sig = (e, b''.join(c_.tobytes() for c_ in cs))
            keyof.setdefault(sig, (e, len([1 for s_ in keyof if s_[0] == e])))
            own.setdefault(info['objects'][k]['id'], {})[(cy, cx)] = keyof[sig]
    extra = [np.concatenate([c_ for c_ in cs], 1) for el in anim for cs in el['cells'].values()]
    kw = dict(stage=HOST, template=tmpl, init=info,
              layer_images={lid: layers[k]['art'] for lid, k in lids.items()},
              cell_prio={lid: layers[k]['cell_prio'] for lid, k in lids.items()},
              backdrop=32, blank_tile_slots=sprite_slots, own_cells=own or None,
              fit_extra=[np.concatenate(extra[i:i + 64], 1) for i in range(0, len(extra), 64)])
    bg, bgi, rep = ecstage.build(planes['A'], planes['B'], cram, **kw)
    if anim:
        # every animated cell keeps one palette line in all its states: the line that draws them best
        lines = {}
        for e, el in enumerate(anim):
            for (k, cy, cx), cs in el['cells'].items():
                lid = info['objects'][k]['id']
                if lid not in lines:
                    lines[lid] = -np.ones(rep['cells'][lid].shape, int)
                lines[lid][cy, cx] = ecstage.best_line(cs, rep['line_rgb'])
        kw['cell_lines'] = lines
    # MK's text: its sheet in place of the host's sheet 2 (its tiles in RAM, at the BG's start), in
    # the stage's own reds - or MK's red put in the palette where it has none near
    red = MK_TEXT_RGB[2][15]
    near = min(sum((a - b) ** 2 for a, b in zip(red, rep['line_rgb'][0][k])) ** 0.5 for k in range(2, 16))
    if near > TEXT_RED_NEAR:
        kw['fixed_extra'] = {TEXT_RED: red}
        bg, bgi, rep = ecstage.build(planes['A'], planes['B'], cram, **kw)
    where = {}
    kw['replace_chunks'] = text_chunks(rep['line_rgb'], where)
    kw['blank_tile_slots'] = tuple(x for x in kw['blank_tile_slots'] if x != TEXT_SOURCE)
    line_rgb = rep['line_rgb']
    bg, bgi, rep = ecstage.build(planes['A'], planes['B'], cram, **kw)
    assert rep['line_rgb'] == line_rgb, 'the palette moved between passes'
    lo, hi = cam
    start = (hi - lo) // 2
    floor = MK_FEET[key] + FLOOR_TO_FEET
    at = (len(bgi) + 1) & ~1
    org = ecstage.BGI_BASE + at
    pal_hw = [int(x, 16) for x in rep['pal_hw']]
    # the stage's tasks, each an object of its own (the host's first descriptor, its code ours):
    # MK's animation (if any) and MK's text; the setup spawns them (placeholders first: same size)
    tasks = (['anim'] if anim else []) + ['text']
    host_desc = info['descriptors'][0]
    spawn = lambda addrs: dict(info, descriptors=[host_desc] + [dict(host_desc, addr=a_) for a_ in addrs])
    body = body_code(org, spawn([None] * len(tasks)), floor, start, pal_hw, template_sub)
    bgi = bgi + bytes(at - len(bgi)) + body
    d0 = host_desc['addr'] - ecstage.BGI_BASE
    template_desc = bytes(bgi[d0:d0 + 0x22])

    def desc(code_at):
        d = bytearray(template_desc)
        d[0x1E:0x22] = code_at.to_bytes(4, 'big')
        return bytes(d)
    addrs = []
    for t in tasks:
        at = (len(bgi) + 1) & ~1
        bgi = bgi + bytes(at - len(bgi))
        desc_at = ecstage.BGI_BASE + at
        if t == 'anim':
            code = anim_code(desc_at + 0x22, anim, rep, info)
            bgi += desc(desc_at + 0x22) + code
        else:
            code, _ = text_code(desc_at + 0x22, 0, where)             # (its size: the letters' descriptor after)
            letter_at = desc_at + 0x22 + len(code)
            code, letter_code = text_code(desc_at + 0x22, letter_at, where)
            bgi += desc(desc_at + 0x22) + code + desc(letter_code)
        addrs.append(desc_at)
    body2 = body_code(org, spawn(addrs), floor, start, pal_hw, template_sub)
    assert len(body2) == len(body)
    bgi = bgi[:org - ecstage.BGI_BASE] + body2 + bgi[org - ecstage.BGI_BASE + len(body2):]
    task = dict(elements=len(anim), text_frames=where['frames'], text_tiles=where['tiles'])
    assert len(bg) <= BG_MAX, f'{key}: BG {len(bg)} bytes reaches the CD loader\'s stack ($43000)'
    assert len(bgi) <= ecstage.BG_BASE - ecstage.BGI_BASE, f'{key}: BGI {len(bgi)} bytes runs into its BG'
    return bg, bgi, dict(camera=info['camera'], entry=org, slot=P['bg']['slot']), \
        dict(rep, layers=[(b['plane'], b['y'], b['h'], b['rate']) for b in layers], anim=task)


STAGE_VRAM_TILE = 708             # VRAM tile of the stages' tile slot (9, Chin Wo's): tile n is at 708 + n (measured)
ANIM_REC = 18                     # an element's record: timer, run, runs, runs table, states, VRAM address, bytes


def anim_code(org, anim, rep, info):
    """The animation task at org: every tick (a sleep: 2 frames) each element's timer counts down 2; at 0
    or below its next run
    (MK's sequence, looped) begins and that run's state's tiles are queued for VRAM ($CE1A: source,
    VRAM address, bytes). An element's tiles are consecutive (build's own_cells), each state's
    pixels one block. Starts each element on its last run so that the first frame puts run 0's
    state in (a round restarting finds the tiles as the last round left them)."""
    import mkinputs, ecstage
    line_rgb = rep['line_rgb']
    elems = []
    for e, el in enumerate(anim):
        tiles = sorted({t for key, t in rep['own_tiles'].items() if key[0] == e})
        assert tiles == list(range(tiles[0], tiles[0] + len(tiles))), 'an element\'s tiles apart'
        # each state's pixels, tile by tile (a tile: its key's cells' art in that state)
        blocks = []
        for s_ in range(el['nstates']):
            data = bytearray(32 * len(tiles))
            for (k, cy, cx), cs in el['cells'].items():
                lid = info['objects'][k]['id']
                word = int(rep['cells'][lid][cy, cx])
                t = (word & 0x7FF) - tiles[0]
                px = ecstage.quantize_cell(cs[s_], line_rgb[(word >> 13) & 3])
                data[32 * t:32 * t + 32] = ecstage.encode_tiles([px])
            blocks.append(bytes(data))
        elems.append(dict(dest=(STAGE_VRAM_TILE + tiles[0]) * 32, size=32 * len(tiles), blocks=blocks, runs=el['runs']))
    a = mkinputs.Asm(org)
    a.w(0x08ED, 0x0006, 0x002A)                           # bset #6,$2A(a5)       its sprite hidden
    a.w(0x3B7C, 0x7000, 0x004E, 0x3B7C, 0x7000, 0x0052)   # x, y = $7000
    a.pcrel(0x45FA, 'elems')                              # lea elems(pc),a2      each starts at its last run
    a.w(0x7E00 | (len(elems) - 1))                        # moveq #n-1,d7
    a.label('init')
    a.w(0x34BC, 1)                                        # move.w #1,(a2)        timer
    a.w(0x356A, 4, 2)                                     # move.w 4(a2),2(a2)    run = runs
    a.w(0x536A, 2)                                        # subq.w #1,2(a2)       - 1
    a.w(0x45EA, ANIM_REC)                                 # lea REC(a2),a2
    a.dbra(7, 'init')
    a.label('loop')
    a.pcrel(0x45FA, 'elems')                              # lea elems(pc),a2
    a.w(0x7E00 | (len(elems) - 1))                        # moveq #n-1,d7
    a.label('el')
    a.w(0x5552)                                           # subq.w #2,(a2)        (a sleep is 2 frames)
    a.bccw(0x6E, 'next')                                  # bgt.w next
    a.w(0x302A, 2)                                        # move.w 2(a2),d0       the next run
    a.w(0x5240)                                           # addq.w #1,d0
    a.w(0xB06A, 4)                                        # cmp.w 4(a2),d0
    a.bcc(0x6D, 'nowrap')                                 # blt.s
    a.w(0x7000)                                           # moveq #0,d0
    a.label('nowrap')
    a.w(0x3540, 2)                                        # move.w d0,2(a2)
    a.w(0xE548)                                           # lsl.w #2,d0
    a.w(0x226A, 6)                                        # movea.l 6(a2),a1      runs table
    a.w(0x3231, 0x0002)                                   # move.w 2(a1,d0.w),d1    its frames,
    a.w(0xD352)                                           # add.w d1,(a2)           after what's left
    a.w(0x3231, 0x0000)                                   # move.w 0(a1,d0.w),d1    its state
    a.w(0xC2EA, 16)                                       # mulu.w 16(a2),d1      x bytes
    a.w(0x202A, 10)                                       # move.l 10(a2),d0      states
    a.w(0xD081)                                           # add.l d1,d0           its pixels
    a.w(0x322A, 14)                                       # move.w 14(a2),d1      VRAM
    a.w(0x342A, 16)                                       # move.w 16(a2),d2      bytes
    a.jsr(0xCE1A)
    a.label('next')
    a.w(0x45EA, ANIM_REC)                                 # lea REC(a2),a2
    a.dbra(7, 'el')
    a.w(0x7001); a.jsr(0x68D6)                            # moveq #1,d0 ; jsr sleep
    a.bccw(0x60, 'loop')
    a.label('elems')
    fix = []
    for el in elems:
        a.w(0, 0, len(el['runs']))
        fix.append((len(a.out), 'runs')); a.l(0)
        fix.append((len(a.out), 'states')); a.l(0)
        a.w(el['dest'], el['size'])
    code = bytearray(a.build())
    for k, el in enumerate(elems):
        if len(code) & 1:
            code += b'\0'
        runs_at = org + len(code)
        code += b''.join(st.to_bytes(2, 'big') + n.to_bytes(2, 'big') for st, n in el['runs'])
        states_at = org + len(code)
        code += b''.join(el['blocks'])
        o = fix[2 * k][0]
        code[o:o + 4] = runs_at.to_bytes(4, 'big')
        o = fix[2 * k + 1][0]
        code[o:o + 4] = states_at.to_bytes(4, 'big')
    return bytes(code)


FLOOR_TO_FEET = -6                # $1496 = MK's feet line + this (ours stand 6 px below $1496, the camera's y at 0: measured)


def W(d, o):
    return int.from_bytes(d[o:o + 2], 'big')


def card(text):
    """A stage card: the name on line 1 (centred), line 2 empty (MK's stages have no year)."""
    t = text.encode('latin-1')
    return bytes([3 + len(t) + 1, (40 - len(t)) // 2, 12]) + t + b'\0' + bytes([15, 14]) + b'\0'


# ---------------------------------------------------------------- SUB.BIN: the dispatcher and the pick
REC = 36                          # a packed stage's record: camera (4 words), BG sector, sectors, BGI
                                  # sector, sectors, entry (its init's rest), card, track, BG slot
MK_TRACK_EC = {4: 13, 3: 20, 6: 21, 7: 22}   # MK CD track -> ours (13: the Pit's, cdaudio.STAGE_MUSIC;
                                  # 20-22: cdaudio.STAGE_TRACKS)
SHADOW_SITES = (0xB442, 0xB4DA)   # SUB.BIN: each fighter's shadow (patches.pit_no_shadows' jsr)
EC_RANDOM = 0x18A98 - 0x14000     # GAME.CO: the Tournament's random stage list (a word per pick, 0 = none)
# Which game a fight is in: each of GAME's fight starts puts its own return address in $143C(a6)
# just before jmp $6C98 (lea ret(pc),a0; move.l a0,$143C(a6)). ($1438 is no game: 7 one player,
# 2 two, in the Contest, the Duel and the Tournament alike.)
CONTEST_RET, DUEL_RET, TOURNAMENT_RET = 0x149B6, 0x14DA6, 0x18A52
FIGHT_CALL = bytes.fromhex('41fa000c2d48143c4ef900006c98')   # (the 14 bytes before each return)


def sub_code(org, recs, cards, mk_slots, reptile_slot, pit_mode, ec_stages):
    """The code and data in mode $16's init's place (org): init16 (the dispatcher), pick, shadow.
    recs: per packed stage, dict camera, bg (sector, sectors), bgi (..), entry, track, slot."""
    import mkinputs
    a = mkinputs.Asm(org)
    lab = lambda n: org + a.labels[n]
    # init16: the dispatcher
    a.label('init16')
    a.pcrel(0x43FA, 'recs')                               # lea recs(pc),a1
    a.w(0x7000)                                           # moveq #0,d0
    a.pcrel(0x103A, 'var')                                # move.b var(pc),d0
    a.w(0xC0FC, REC)                                      # mulu.w #REC,d0
    a.w(0xD2C0)                                           # adda.w d0,a1
    fix = []                                              # (offset of a long, label): absolute addresses
    a.w(0x23C9); fix.append((len(a.out), 'cur')); a.l(0)  # move.l a1,cur
    a.w(0x23D1); fix.append((len(a.out), 'cam')); a.l(0)  # move.l (a1),cam      camera: x min, y min
    a.w(0x23E9, 4); fix.append((len(a.out), 'cam+4')); a.l(0)   # move.l 4(a1),cam+4   x max, y max
    a.w(0x23E9, 28); a.l(CARDS + 4 * (MODE - 0x11))      # move.l 28(a1),card entry
    a.w(0x33E9, 32); a.l(MUSIC_TRACKS + 2 * MUSIC_INDEX)  # move.w 32(a1),its track
    for k, fid in enumerate(HOST_FILES):                  # EC's file table: the packs' parts
        a.w(0x23E9, 8 + 8 * k); a.l(FILE_TABLE + 8 * fid)
        a.w(0x23E9, 12 + 8 * k); a.l(FILE_TABLE + 8 * fid + 4)
    a.jsr(0xE00E)
    a.label('cam')
    a.w(0, 0, 0, 0)
    a.jsr(0xAC38)
    a.w(0x082E, 5, 0x0AB7)                                # btst #5,$AB7(a6)   a round restarting:
    a.bccw(0x66, 'go')                                    # bne.w go           the files are in
    for fid, dest in zip(HOST_FILES, (0x37000, 0x34000)):
        a.w(0x303C, fid)                                  # move.w #file,d0
        a.w(0x2D7C); a.l(dest); a.w(0x9190)               # move.l #dest,-$6E70(a6)
        a.jsr(0x65C8)
        a.w(0x42AE, 0x9190)                               # clr.l -$6E70(a6)
    a.w(0x2279); fix.append((len(a.out), 'cur')); a.l(0)  # movea.l cur,a1
    a.w(0x3029, 34); a.jsr(0xDEF8)                        # move.w 34(a1),d0 ; jsr slot set-up
    a.w(0x303C, 0x0A); a.jsr(0xC0FA)                      # wait 10
    a.label('go')
    a.w(0x2279); fix.append((len(a.out), 'cur')); a.l(0)  # movea.l cur,a1
    a.w(0x2069, 24)                                       # movea.l 24(a1),a0
    a.w(0x4ED0)                                           # jmp (a0)
    # pick: GAME's fight start (d0 = its stage mode), then on to the fight
    a.label('pick')
    a.w(0x48E7, 0x70C0)                                   # movem.l d1-d3/a0-a1,-(sp)
    a.w(0x3600)                                           # move.w d0,d3
    a.w(0x0C43, 0x13)                                     # cmpi.w #$13,d3     the bosses' arenas
    a.bccw(0x6D, 'out')                                   # blt.w out
    a.w(0x7400)                                           # moveq #0,d2        d2: 1 = player 1 MK's, 2 = player 2
    a.w(0x223C); a.l(sum(1 << s for s in mk_slots))       # move.l #mk slots,d1
    a.w(0x302E, 0x1428)                                   # move.w $1428(a6),d0
    a.w(0x0101)                                           # btst d0,d1
    a.bcc(0x67, 'p1ec'); a.w(0x5242); a.label('p1ec')     # beq.s ; addq.w #1,d2
    a.w(0x302E, 0x142A)                                   # move.w $142A(a6),d0
    a.w(0x0101)                                           # btst d0,d1
    a.bcc(0x67, 'p2ec'); a.w(0x5442); a.label('p2ec')     # beq.s ; addq.w #2,d2
    a.w(0x4A42)                                           # tst.w d2
    a.bcc(0x66, 'mk')                                     # bne.s mk
    a.w(0x0C43, pit_mode); a.bcc(0x67, 'ecrand')          # two EC fighters on an MK stage:
    a.w(0x0C43, MODE); a.bccw(0x66, 'out')                #  EC's own random stage instead
    a.label('ecrand')
    a.w(0x7200, 0x7400 | (len(ec_stages) - 1))            # moveq #0,d1 ; moveq #n-1,d2
    a.jsr(0x6C68)                                         # random d1..d2 -> d0
    a.pcrel(0x41FA, 'eclist')                             # lea eclist(pc),a0
    a.w(0xD040, 0x3630, 0x0000)                           # add.w d0,d0 ; move.w (a0,d0.w),d3
    a.bccw(0x60, 'out')
    a.label('mk')
    a.w(0x0CAE); a.l(DUEL_RET); a.w(0x143C)               # cmpi.l #duel,$143C(a6)   a Duel:
    a.bcc(0x66, 'notduel')
    a.w(0x102E, 0x1CFC)                                   # move.b $1CFC(a6),d0   BACKGROUND SETTING
    a.bcc(0x67, 'mkrand')                                 # beq.s mkrand          RANDOM
    a.w(0x0C00, 14)                                       # cmpi.b #14,d0
    a.bccw(0x6D, 'out')                                   # blt.w out             a stage by name
    a.w(0x0802, 1)                                        # btst #1,d2            PLAYER 2: his home,
    a.bccw(0x67, 'out')                                   # beq.w out             unless he's MK's
    a.bcc(0x60, 'mkrand')
    a.label('notduel')
    a.w(0x0CAE); a.l(CONTEST_RET); a.w(0x143C)            # cmpi.l #contest,$143C(a6)   the Contest:
    a.bcc(0x66, 'mkrand')
    a.w(0x0C6E, reptile_slot, 0x142A)                     # cmpi.w #slot,$142A(a6) Reptile's match:
    a.bccw(0x67, 'out')                                   # beq.w out             the Pit (MK's)
    a.label('mkrand')
    a.w(0x7200, 0x7400 | (len(STAGES) - 1))               # moveq #0,d1 ; moveq #5,d2
    a.jsr(0x6C68)
    a.pcrel(0xB03A, 'last')                               # cmp.b last(pc),d0    never the last again
    a.bcc(0x67, 'mkrand')
    a.w(0x13C0); fix.append((len(a.out), 'last')); a.l(0)   # move.b d0,last
    a.pcrel(0x41FA, 'mkmode')                             # lea mkmode(pc),a0
    a.w(0xD040, 0x3630, 0x0000)                           # add.w d0,d0 ; move.w (a0,d0.w),d3
    a.w(0xE248)                                           # lsr.w #1,d0
    a.pcrel(0x41FA, 'mkvar')                              # lea mkvar(pc),a0
    a.w(0x1230, 0x0000)                                   # move.b (a0,d0.w),d1
    a.w(0x13C1); fix.append((len(a.out), 'var')); a.l(0)    # move.b d1,var
    a.label('out')
    a.w(0x3003)                                           # move.w d3,d0
    a.w(0x4CDF, 0x030E)                                   # movem.l (sp)+,d1-d3/a0-a1
    a.jmp(FIGHT_START)
    # shadow: Z (no shadow) on stage $18 (EC's own rule), the Pit and the packed stages
    a.label('shadow')
    a.w(0x0C6E, 0x18, 0x0AB2); a.bcc(0x67, 'sh_done')
    a.w(0x0C6E, pit_mode, 0x0AB2); a.bcc(0x67, 'sh_done')
    a.w(0x0C6E, MODE, 0x0AB2)
    a.label('sh_done')
    a.w(0x4E75)
    # data
    a.label('var'); a.out += b'\0'
    a.label('last'); a.out += b'\xff'
    a.label('cur'); a.l(0)
    a.label('mkmode')
    for k, _, _ in STAGES:
        a.w(pit_mode if k == 'pit' else MODE)
    a.label('mkvar')
    for k, _, _ in STAGES:
        a.out += bytes([PACKED.index(k) if k in PACKED else 0])
    if len(a.out) & 1:
        a.out += b'\0'
    a.label('eclist')
    a.w(*ec_stages)
    a.label('cards')
    card_at = {}
    for k, text in cards.items():
        card_at[k] = len(a.out)
        a.out += card(text)
    if len(a.out) & 1:
        a.out += b'\0'
    a.label('recs')
    for k in PACKED:
        r = recs[k]
        a.w(*r['camera'])
        a.l(r['bg'][0]); a.l(r['bg'][1]); a.l(r['bgi'][0]); a.l(r['bgi'][1])
        a.l(r['entry']); a.l(org + card_at[k]); a.w(r['track']); a.w(r['slot'])
    out = bytearray(a.build())
    for at, name in fix:
        base, _, plus = name.partition('+')
        out[at:at + 4] = (org + a.labels[base] + int(plus or 0)).to_bytes(4, 'big')
    return bytes(out), {n: org + o for n, o in a.labels.items()}


MUSIC_INDEX = None                # mode $16's place in SUB's stage music list (patch() finds it)


def patch(ec, found):
    """The packs, the dispatcher in mode $16's init's place, the pick, the shadows' rule."""
    global MUSIC_INDEX
    import ecstage, patches
    sub = ec.read_file('SUB.BIN')
    stock = _host_file('SUB')
    ids = [W(sub, MUSIC_IDS - 0x6000 + 2 * i) for i in range(18)]
    MUSIC_INDEX = ids.index(MODE)
    inits = ecstage.stage_inits(sub)
    org = inits[MODE]
    room = min(x for x in inits.values() if x > org) - org
    assert sub[org - 0x6000:org - 0x6000 + 6] == stock[org - 0x6000:org - 0x6000 + 6], 'mode $16\'s init changed'
    # each packed stage
    built = {}
    for key in PACKED:
        bg, bgi, rec, rep = build_stage(key, stock)
        built[key] = (bg, bgi, rec)
        print(f'        {key}: {rep["tiles"]} tiles, BG {len(bg)}, BGI {len(bgi)} bytes; layers '
              + ', '.join(f'{p}{y}+{h}x{r}' for p, y, h, r in rep['layers']))
    recs = {}
    for ext, part in (('BG', 0), ('BGI', 1)):
        pack, where = bytearray(), {}
        for key in PACKED:
            data = built[key][part]
            where[key] = (len(pack) // 2048, (len(data) + 2047) // 2048)
            pack += data + bytes(-len(data) % 2048)
        lba = ec.replace_file(f'{HOST}.{ext}', bytes(pack))
        for key in PACKED:
            recs.setdefault(key, dict(built[key][2]))[ext.lower()] = (lba + where[key][0], where[key][1])
    cards = {k: c for k, c, _ in STAGES if k in PACKED}
    for k, _, t in STAGES:
        if k in recs:
            recs[k]['track'] = MK_TRACK_EC[t]
    game = ec.read_file('GAME.CO')
    for ret in (CONTEST_RET, DUEL_RET, TOURNAMENT_RET):
        o = ret - 0x14000 - len(FIGHT_CALL)
        assert game[o:o + len(FIGHT_CALL)] == FIGHT_CALL, f'GAME.CO: no fight start returning to ${ret:X}'
    ec_stages = sorted({W(game, EC_RANDOM + 2 * i) for i in range(25)} - {0})
    mk_slots = [sp.host_id - 2 for sp in patches.MK_SPECS]
    code, labels = sub_code(org, recs, cards, mk_slots, patches.REPTILE_SLOT, patches.PIT_MODE, ec_stages)
    assert len(code) <= room, f'the dispatcher: {len(code)} bytes, room {room}'
    ec.patch_file('SUB.BIN', org - 0x6000, code + bytes(room - len(code)))
    ec.patch_file('SUB.BIN', PICK_ENTRY - 0x6000, bytes.fromhex('4ef9') + labels['pick'].to_bytes(4, 'big'),
                  expect=bytes.fromhex('4ef9') + FIGHT_START.to_bytes(4, 'big'))
    sub = ec.read_file('SUB.BIN')
    for site in SHADOW_SITES:
        old = sub[site - 0x6000:site - 0x6000 + 6]
        assert old[:2] == b'\x4e\xb9', f'${site:X}: not pit-no-shadows\' jsr'
        ec.patch_file('SUB.BIN', site - 0x6000, bytes.fromhex('4eb9') + labels['shadow'].to_bytes(4, 'big'), expect=old)
    print(f'        dispatcher and pick: {len(code)} of {room} bytes at ${org:X} (mode ${MODE:X}\'s init)')


# ---------------------------------------------------------------- MK's FIGHT! and FINISH HIM / FINISH HER
TEXT_EVENTS = ('fight', 'finish_him', 'finish_her')
TEXT_RED = (0, 15)                # a stage whose colours have no red near MK's text gets it here (the Lair)
TEXT_RED_NEAR = 60                # (distance of the nearest)
TEXT_STEP = 8                     # a letter's sizes: MK's, to the nearest 8 px (MK shows ~5 per letter as it grows; room)
BG_MAX = 0x43000 - 0x37000        # a stage's .BG may reach $43000: the CD loader's stack is there as it loads
                                  # (patches.cd_ai_stack)
TEXT_SLOTS = 9                    # letter objects (FINISH HIM / HER: 9 letters; FIGHT!: 6)
TEXT_SHEET, TEXT_SOURCE = 2, 2    # the host's sheet 2 and its tile source 2 (unused by the MK stages), ours
FIGHT_FLAG = 0x28001              # PRG RAM: bit 6 set when EC's BEGIN CONTEST ends (-$7FFF(a6)): the fight begins
DAZED = 0x1F                      # a fighter's move when dazed (FINISH HIM's loser, on 1 health)
P1, P2 = 0x2E188, 0x2E330
MK_TEXT_RGB = {2: {12: (0, 0, 0), 13: (108, 36, 36), 15: (252, 0, 0)},      # MK's line 2: the red text
               1: {12: (0, 0, 0), 13: (36, 36, 36), 15: (216, 216, 216)}}   # line 1: its grey flash


def text_art(line_rgb):
    """MK's text for a stage whose palette is line_rgb: the sheet's frames - each letter at each size
    MK shows it (data/mk_text.json; drawn from PAC.PRG's letters, mktext.scale), red, and grey at
    full size - their tiles, and each event's timeline: per tick (2 frames, MK's even frames), per
    letter (in the word's order), [frame or None, x, y] on screen."""
    import sys as _s
    from inputs import ROOT
    _s.path.insert(0, os.path.join(ROOT, 'tools', 'capture'))
    import mktext
    pac = open(os.path.join(ROOT, 'extracted', 'mk_us', 'PAC.PRG'), 'rb').read()
    letters = mktext.pac_letters(pac)
    data = json.load(open(os.path.join(ROOT, 'data', 'mk_text.json')))
    # the stage's own colours nearest MK's (line 0, 2-15: never the HUD's - line 1, 10-15 - which EC
    # changes at FINISH HIM, nor the fighters' shadow, line 0 colour 1)
    maps = {}
    for pal, want in MK_TEXT_RGB.items():
        m = {}
        for idx, c in want.items():
            d = [sum((a - b) ** 2 for a, b in zip(c, line_rgb[0][k])) for k in range(2, 16)]
            m[idx] = int(np.argmin(d)) + 2
        maps[pal] = (0, m)
    frames, index, tiles, tile_at = [], {}, [], {}

    def frame(name, s, pal):
        pal = 2                                           # (red throughout: MK's grey flash at full size would
                                                          #  take 11 x 16 more tiles than the BG has room for)
        s = min(32, max(TEXT_STEP, int(round(s / TEXT_STEP)) * TEXT_STEP))   # (MK's sizes to the nearest step: room)
        key = (name, s, pal)
        if key not in index:
            img = mktext.scale(letters[name], s)
            li, m = maps[pal]
            out = np.zeros_like(img)
            for idx, k in m.items():
                out[img == idx] = k
            # one piece: the tiles of the letter's bounding box (MK grows it from the top-left)
            ys, xs = np.nonzero(out)
            y0, y1 = int(ys.min()) // 8, int(ys.max()) // 8 + 1
            x0, x1 = int(xs.min()) // 8, int(xs.max()) // 8 + 1
            block = [out[cy * 8:cy * 8 + 8, cx * 8:cx * 8 + 8] for cx in range(x0, x1) for cy in range(y0, y1)]
            b = b''.join(t.tobytes() for t in block)
            if b not in tile_at:
                tile_at[b] = len(tiles)
                tiles.extend(block)
            index[key] = len(frames)
            frames.append([(x1 - x0, y1 - y0, 0x8000 | (li << 13) | tile_at[b], 8 * x0, 8 * y0)])
        return index[key]
    timelines = {}
    for ev in TEXT_EVENTS:
        ticks = []
        for fr in data[ev][::2]:
            ticks.append([[frame(r[0], r[3], r[4]), r[1], r[2]] for r in sorted(fr, key=lambda r: r[1])])
        timelines[ev] = ticks
    return tiles, frames, timelines


def text_chunks(line_rgb, where):
    """The sheet (TEXT_SHEET) and tile source (TEXT_SOURCE) chunks for ecstage.build's replace_chunks,
    each event's timeline after the sheet's frames; where gets their RAM addresses (the BG at $37000):
    {event: address}. A timeline: a word, its ticks; a word, its letters; per tick per letter:
    frame (byte), y (byte), x (word)."""
    import ecstage
    tiles, frames, timelines = text_art(line_rgb)
    makers = ecstage.raw_sheet(TEXT_SHEET, TEXT_SOURCE, tiles, frames)
    sheet = makers[('sheet', TEXT_SHEET)]

    def sheet_and_timelines(at):
        c = bytearray(sheet(at))
        for ev in TEXT_EVENTS:
            if len(c) & 1:
                c += b'\0'
            where[ev] = ecstage.BG_BASE + at + len(c)
            c += len(timelines[ev]).to_bytes(2, 'big') + len(timelines[ev][0]).to_bytes(2, 'big')
            for tick in timelines[ev]:
                for f, x, y in tick:
                    c += bytes([0xFF if f is None else f, y & 0xFF]) + (x & 0xFFFF).to_bytes(2, 'big')
        c[0:4] = len(c).to_bytes(4, 'big')
        return bytes(c)
    makers[('sheet', TEXT_SHEET)] = sheet_and_timelines
    where['frames'] = len(frames)
    where['tiles'] = len(tiles)
    return makers


def text_code(org, letter_desc, where):
    """The text director at org (an object's code). A task's registers don't last a sleep (EC's
    tasks keep their state in memory; a4 is the task's own block): each tick (a sleep, 2 frames) it
    starts afresh from its variables. Idle: on the fight's start (FIGHT_FLAG's bit 6 rising, once)
    it starts FIGHT!'s timeline; when a fighter is dazed on 1 health (FINISH HIM's loser, once)
    FINISH HIM's or FINISH HER's (FEMALE_MASK: his id $4C). Starting: as many letter objects as
    the word has (letter_desc: sheet TEXT_SHEET; their code: a VRAM block of 16 tiles, idle).
    Playing: per tick each letter gets its frame ($1B), x = camera + x, y; at the end they're
    removed ($82 bit 2, as the stages' own objects go)."""
    import mkinputs
    from mkinputs import FEMALE_MASK
    a = mkinputs.Asm(org)
    fix = []                                              # (offset of a long, label)

    def var(name):                                        # an absolute long: a variable's address
        fix.append((len(a.out), name))
        a.l(0)
    a.w(0x08ED, 0x0006, 0x002A)                           # bset #6,$2A(a5)       itself hidden
    a.w(0x3B7C, 0x7000, 0x004E, 0x3B7C, 0x7000, 0x0052)
    a.w(0x1039); a.l(FIGHT_FLAG)                          # move.b flag,d0
    a.w(0x0200, 0x0040)                                   # andi.b #$40,d0
    a.w(0x13C0); var('prev')                              # move.b d0,prev
    a.w(0x4279); var('left')                              # clr.w left            (not playing)
    a.label('wait')
    a.w(0x7001); a.jsr(0x68D6)                            # sleep
    a.w(0x4A79); var('left')                              # tst.w left
    a.bccw(0x66, 'tick')                                  # bne.w tick            playing
    a.pcrel(0x103A, 'fdone')                              # move.b fdone(pc),d0
    a.bcc(0x66, 'nofight')
    a.w(0x1039); a.l(FIGHT_FLAG)                          # move.b flag,d0
    a.w(0x0200, 0x0040)                                   # andi.b #$40,d0
    a.pcrel(0x123A, 'prev')                               # move.b prev(pc),d1
    a.w(0x13C0); var('prev')                              # move.b d0,prev
    a.w(0x4A00)                                           # tst.b d0
    a.bcc(0x67, 'nofight')
    a.w(0x4A01)                                           # tst.b d1              rising?
    a.bcc(0x66, 'nofight')
    a.w(0x13FC, 1); var('fdone')                          # move.b #1,fdone
    a.w(0x207C); a.l(where['fight'])                      # movea.l #fight,a0
    a.bccw(0x60, 'start')
    a.label('nofight')
    a.pcrel(0x103A, 'kdone')                              # move.b kdone(pc),d0
    a.bccw(0x66, 'wait')
    for P in (P1, P2):
        a.w(0x3039); a.l(P + 0xBE)                        # move.w move,d0
        a.w(0x0240, 0x7FFF)                               # andi.w #$7FFF,d0
        a.w(0x0C40, DAZED)                                # cmpi.w #dazed,d0
        a.bccw(0x66, f'n{P:x}')
        a.w(0x0C79, 1); a.l(P + 0x76)                     # cmpi.w #1,health
        a.bccw(0x6E, f'n{P:x}')                           # bgt.w
        a.w(0x13FC, 1); var('kdone')                      # move.b #1,kdone
        a.w(0x3239); a.l(P + 0x4C)                        # move.w id,d1
        a.w(0x203C); a.l(FEMALE_MASK)                     # move.l #women,d0
        a.w(0x0300)                                       # btst d1,d0
        a.w(0x207C); a.l(where['finish_him'])             # movea.l #him,a0      (movea: flags kept)
        a.bccw(0x67, 'start')
        a.w(0x207C); a.l(where['finish_her'])             # movea.l #her,a0
        a.bccw(0x60, 'start')
        a.label(f'n{P:x}')
    a.bccw(0x60, 'wait')
    # start: a0 = the timeline: its ticks and letters, the letters spawned
    a.label('start')
    a.w(0x33D8); var('left')                              # move.w (a0)+,left     ticks
    a.w(0x33D8); var('count')                             # move.w (a0)+,count    letters
    a.w(0x23C8); var('ptr')                               # move.l a0,ptr
    a.w(0x4279); var('k')                                 # clr.w k
    a.label('spawn')
    a.w(0x303C, 0x0388, 0x323C, 0x7000, 0x343C, 0x7000)   # d0 type, d1 x, d2 y (off screen)
    a.w(0x227C); var('letter')                            # movea.l #letter,a1
    a.jsr(0x1064A)                                        # (a0: the object; carry: none free)
    a.w(0x55C4)                                           # scs d4
    a.w(0x3239); var('k')                                 # move.w k,d1
    a.w(0xE549)                                           # lsl.w #2,d1
    a.pcrel(0x43FA, 'objs')                               # lea objs(pc),a1
    a.w(0x4A04)                                           # tst.b d4
    a.bcc(0x67, 'got')
    a.w(0x91C8)                                           # suba.l a0,a0          (none: that letter left out)
    a.label('got')
    a.w(0x2388, 0x1000)                                   # move.l a0,(a1,d1.w)
    a.w(0x5279); var('k')                                 # addq.w #1,k
    a.w(0x3039); var('k')                                 # move.w k,d0
    a.w(0xB079); var('count')                             # cmp.w count,d0
    a.bcc(0x6D, 'spawn')                                  # blt.s spawn
    a.bccw(0x60, 'wait')
    # tick: each letter's frame and place, from ptr; then on (or the end)
    a.label('tick')
    a.w(0x2079); var('ptr')                               # movea.l ptr,a0
    a.pcrel(0x43FA, 'objs')                               # lea objs(pc),a1
    a.w(0x3E39); var('count')                             # move.w count,d7
    a.w(0x5347)                                           # subq.w #1,d7
    a.label('each')
    a.w(0x2459)                                           # movea.l (a1)+,a2      the object
    a.w(0x1018)                                           # move.b (a0)+,d0       frame
    a.w(0x7200, 0x1218)                                   # moveq #0,d1 ; move.b (a0)+,d1   y
    a.w(0x3418)                                           # move.w (a0)+,d2       x
    a.w(0xB5FC); a.l(0)                                   # cmpa.l #0,a2
    a.bcc(0x67, 'skip')
    a.w(0x1540, 0x001B)                                   # move.b d0,$1B(a2)     its frame
    a.w(0xD46E, 0xB070)                                   # add.w -$4F90(a6),d2   + camera
    a.w(0x3542, 0x004E)                                   # move.w d2,$4E(a2)
    a.w(0x3541, 0x0052)                                   # move.w d1,$52(a2)
    a.label('skip')
    a.dbra(7, 'each')
    a.w(0x23C8); var('ptr')                               # move.l a0,ptr
    a.w(0x5379); var('left')                              # subq.w #1,left
    a.bccw(0x66, 'wait')
    # the end: the letters removed
    a.pcrel(0x43FA, 'objs')
    a.w(0x3E39); var('count')
    a.w(0x5347)
    a.label('gone')
    a.w(0x2459)                                           # movea.l (a1)+,a2
    a.w(0xB5FC); a.l(0)
    a.bcc(0x67, 'none')
    a.w(0x357C, 0x7000, 0x004E)                           # move.w #$7000,$4E(a2)
    a.w(0x08EA, 0x0002, 0x0082)                           # bset #2,$82(a2)       EC removes it
    a.label('none')
    a.w(0x42A9, 0xFFFC)                                   # clr.l -4(a1)
    a.dbra(7, 'gone')
    a.bccw(0x60, 'wait')
    for name, size in (('prev', 1), ('fdone', 1), ('kdone', 1)):
        a.label(name); a.out += bytes(size)
    if len(a.out) & 1:
        a.out += b'\0'
    for name in ('left', 'count', 'k'):
        a.label(name); a.out += bytes(2)
    a.label('ptr'); a.out += bytes(4)
    a.label('objs'); a.out += bytes(4 * TEXT_SLOTS)
    a.label('letter_code')
    a.w(0x303C, 0x0200); a.jsr(0x6942)
    a.w(0x3B7C, 0x7000, 0x004E)
    a.label('idle')
    a.w(0x7001); a.jsr(0x68D6)
    a.bcc(0x60, 'idle')
    code = bytearray(a.build())
    lab = lambda n: org + a.labels[n]
    for at, name in fix:
        code[at:at + 4] = (letter_desc if name == 'letter' else lab(name)).to_bytes(4, 'big')
    return bytes(code), lab('letter_code')
