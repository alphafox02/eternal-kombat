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
                            pprio=pix_prio[y0:y1][:, cols]))
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
                                pprio=np.concatenate([pad(a['pprio']), pad(b['pprio'])]))]
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
    d = info['descriptors'][0]
    a.w(0x303C, d['d0']); a.w(0x323C, d['x']); a.w(0x343C, d['y'])
    a.w(0x227C); a.l(d['addr'])                             # movea.l #descriptor,a1
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
    bg, bgi, rep = ecstage.build(planes['A'], planes['B'], cram, stage=HOST, template=tmpl, init=info,
                                 layer_images={lid: layers[k]['art'] for lid, k in lids.items()},
                                 cell_prio={lid: layers[k]['cell_prio'] for lid, k in lids.items()},
                                 backdrop=32, blank_tile_slots=sprite_slots)
    lo, hi = cam
    m = _json(key)
    start = (hi - lo) // 2
    floor = MK_FEET[key] + FLOOR_TO_FEET
    at = (len(bgi) + 1) & ~1
    org = ecstage.BGI_BASE + at
    pal_hw = [int(x, 16) for x in rep['pal_hw']]
    body = body_code(org, info, floor, start, pal_hw, template_sub)
    bgi = bgi + bytes(at - len(bgi)) + body
    assert len(bgi) <= ecstage.BG_BASE - ecstage.BGI_BASE, f'{key}: BGI {len(bgi)} bytes runs into its BG'
    return bg, bgi, dict(camera=info['camera'], entry=org, slot=P['bg']['slot']), \
        dict(rep, layers=[(b['plane'], b['y'], b['h'], b['rate']) for b in layers])


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
