"""Patches applied to the Eternal Champions disc, in order.

Each patch is a function taking (ec, sources) -> None:
    ec       Disc: the output disc being built (a copy; safe to modify)
    sources  {id: Disc}: every recognised input disc, read-only
Register it with @patch('name', 'what it does'). build.py --skip name disables one.
"""
PATCHES = []

# Scorpion is built from a copy of Blade's files (art, code, sounds) written
# into HOST's files; Blade's own stay stock once HOST is a slot of its own.
HOST = 'BST'                      # Blast: a hidden EC fighter, almost never special-cased
HOST_ID = 23
HOST_IDX = HOST_ID - 2
# versus portraits in GAME.DAT ($EA0 bytes): ids 2-18 from $23D30, 19+ from $33604
PORTRAIT = {i: (0x23D30 + i * 0xEA0 if i < 17 else 0x33604 + (i - 17) * 0xEA0) for i in range(25)}


def host(ext):
    return f'{HOST}.{ext}'


class Spec:
    """An MK fighter built from a copy of Blade's files in an EC host slot."""
    def __init__(self, **kw):
        self.__dict__.update(kw)


SCORPION = Spec(key='scorpion', name='SCORPION', host='BST', host_id=23, mk_dir='mk_moves', ai='BST.AI',
                win=(0xCB90, b'    BLAST\0', b' SCORPION\0'), sheet_base=0x8D,
                aliases={}, exact=True, strip=True, blood=True, alt='p2')
# Raiden: Chin Wo's slot (CHW, id 19, sheets from $72). First version: Blade's
# moves and code with Raiden's MK poses - Blade's projectile is his lightning,
# Blade's dash his torpedo. Actions not captured for him borrow these:
RAIDEN = Spec(key='raiden', name='RAIDEN', host='CHW', host_id=19, mk_dir='mk_moves_raiden', ai='CHW.AI',
              win=(0xCB64, b'   CHIN WO\0', b'    RAIDEN\0'), sheet_base=0x72,
              aliases={'spear': 'lightning', 'teleport_mk': 'torpedo', 'dizzy': 'hit_high', 'lying': 'knockdown',
                       'jumpup_c': 'jump_c', 'jumpup_a': 'jump_a', 'fatality': 'torpedo',
                       'fatality_fire': 'lightning', 'fatality_skeleton': 'teleport', 'teleport': 'teleport'},
              # his torpedo is Blade's dash (frames 41:16, 41:17, 41:61, 41:62 with the hit,
              # 41:61, 41:16): MK's crouch, spring, dive and the head-first flight
              extra=[('torpedo', ['41:16=7', '41:17=8', '41:61=9', '41:62=10']),
                     ('teleport', __import__('mkinputs').rtele_plan('mk_moves_raiden')[1])],   # his MK teleport (move $31)
              exact=False, strip=False, blood=True, alt='dim',
              # blood: EC's hit spark is the attacker's colours 12/13 made red. His
              # black (12) and grey (13) move to 10 and 6, freed by merging the
              # hat's palest gold into the next (10 -> 9) and 6 into 5
              colour_map={10: 9, 6: 5}, blood_moves={12: 10, 13: 6})
# Johnny Cage: Zuni's slot (MON, id 18); Sub-Zero: Yappy's (DOG, id 20).
# Neither is special-cased by any EC module. Their own sheet and tile-source
# numbers are too few for Blade's art (2 and 5), so they get numbers no EC
# file registers: sheets $D9-$FF (a gap below the animal transformations'
# $100+) and tile sources $236-$256 (the end of the 300-entry table at RAM
# $D448; every other id up to $234 is some file's).
# First versions like Raiden's: Blade's moves with their MK poses - Blade's
# projectile is Johnny's green bolt / Sub-Zero's ice blast, his dash Johnny's
# shadow kick (Sub-Zero's slide is not captured yet: his sweep stands in).
JOHNNY = Spec(key='johnny', name='JOHNNY CAGE', host='MON', host_id=18, mk_dir='mk_moves_johnny', ai='MONK.AI',
              win=(0xCB5A, b'    ZUNI\0', b' J. CAGE\0'), sheet_base=0xD9, src_ids=list(range(0x236, 0x242, 2)),
              aliases={'spear': 'greenbolt', 'teleport_mk': 'shadowkick', 'teleport': 'shadowkick',
                       'dizzy': 'hit_high', 'lying': 'knockdown', 'fatality': 'shadowkick',
                       'fatality_fire': 'greenbolt', 'fatality_skeleton': 'uppercut'},
              exact=False, strip=False, blood=True, alt='dim',
              # down + Z: MK1's split punch (tools/mkmoves.py crouch_z 5 split, 7 punch, 8 back up)
              extra=[('crouch_z', ['42:05=5', '42:06=7', '42:07=8'])],
              # his home stage (Zuni's circus) animates entries 3, 4, 7, 8, 9 of his
              # palette line: keep off them. His MK palette has black three times
              # (5, 6, 12): 3 and 4 move to 5 and 6, 9 (= 3 but for red's last
              # bit) joins 3, 8 and 7 go to their nearest (13 grey, 12 black)
              # blood (EC's hit spark colours 12/13 red): his grey (13, and 8
              # that joined it) merges into the dark brown 2 and light grey 14
              # into white - barely visible - and his black moves to 14
              colour_map={5: 12, 6: 12, 3: 5, 4: 6, 9: 5, 8: 2, 7: 12, 13: 2, 14: 15}, palette_set={5: 3, 6: 4},
              blood_moves={12: 14})
SUBZERO = Spec(key='subzero', name='SUB-ZERO', host='DOG', host_id=20, mk_dir='mk_moves_subzero', ai='DOG.AI',
               win=(0xCB70, b'    YAPPY\0', b' SUB-ZERO\0'), sheet_base=0xDD, src_ids=list(range(0x242, 0x24E, 2)),
               aliases={'spear': 'iceblast', 'teleport_mk': 'slide', 'teleport': 'slide',
                        'dizzy': 'hit_high', 'lying': 'knockdown', 'fatality': 'iceblast',
                        'fatality_fire': 'iceblast', 'fatality_skeleton': 'uppercut'},
              exact=False, strip=False, blood=True, alt='p2',      # MK's Scorpion: the same sprites
              # blood as Raiden's: navy-black 6 joins black 12, cream 1 joins white 15
              # his slide on Blade's dash (41:17, 41:16, 41:61, 41:62 with the hit, 41:61, 41:16):
              # MK's drop / getting up (8) and the slide (9)
              extra=[('slide', ['41:16=8', '41:17=8', '41:61=8', '41:62=9'])]
                    + __import__('mkinputs').szf_pins(),     # his spine rip (mkinputs.emit_gfatal)
              colour_map={6: 12, 1: 15}, blood_moves={12: 6, 13: 1})
SPEC = SCORPION


SUB_CEILING = 0x14000             # SUB.BIN loads at $6000; PLYR.CO at $14000


def put_sub(ec, sub):
    """SUB.BIN with code appended: it must end below PLYR.CO."""
    end = 0x6000 + len(sub)
    if end > SUB_CEILING:
        raise ValueError(f'SUB.BIN would run {end - SUB_CEILING} bytes into PLYR.CO (ends ${end:X})')
    ec.replace_file('SUB.BIN', sub)


def _check_mk_tables():
    import mkinputs
    specs = (SCORPION, RAIDEN, JOHNNY, SUBZERO)
    assert mkinputs.MK_SHEET_BASE == {sp.host_id: sp.sheet_base for sp in specs}, 'mkinputs.MK_SHEET_BASE'
    assert set(mkinputs.BLOOD_IDS) == {sp.host_id for sp in specs if sp.blood}, 'mkinputs.BLOOD_IDS'
    assert tuple(mkinputs.MK_IDS) == tuple(sp.host_id for sp in specs), 'mkinputs.MK_IDS'


_check_mk_tables()


def use(spec):
    """Point the fighter patches (host(), HOST_ID, the art builder) at spec."""
    global SPEC, HOST, HOST_ID, HOST_IDX, SHEET_SHIFT
    import scorpion_full
    SPEC, HOST, HOST_ID = spec, spec.host, spec.host_id
    HOST_IDX = HOST_ID - 2
    SHEET_SHIFT = spec.sheet_base - 0x40
    if not getattr(spec, 'scripts_art', False):
        import os, mkscripts                 # his attacks' MK poses on their own frame slots
        co = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               'extracted', 'ec_us', 'BLA.CO'), 'rb').read()
        import mkinputs
        spec.extra = list(getattr(spec, 'extra', [])) + mkscripts.build(co, spec.mk_dir)[1] \
            + [('throw_seq', mkinputs.throw_plan(spec.mk_dir)[1])] \
            + [('hit_seq', mkinputs.hit_plan(spec.mk_dir)[1])]   # MK's whole throw and hit reaction (mkinputs drives them)
        if spec is not SCORPION:                 # MK's walk loop (mkinputs drives it)
            import mkinputs
            spec.extra.append(('walk_fwd', mkinputs.walk_plan(spec.mk_dir)[2]))
        spec.scripts_art = True
    scorpion_full.CFG.update(mk_dir=spec.mk_dir, aliases=spec.aliases, exact=spec.exact, strip=spec.strip,
                             extra=getattr(spec, 'extra', ()), colour_map=getattr(spec, 'colour_map', {}),
                             colour_moves=getattr(spec, 'blood_moves', scorpion_full.COLOUR_MOVES) if spec.blood else {})


def _start():
    use(SCORPION)                            # the scorpion-* patches run with his settings


def for_spec(spec, fn):
    def run(ec, sources):
        use(spec)
        try:
            fn(ec, sources)
        finally:
            use(SCORPION)
    return run


def patch(name, doc):
    def deco(fn):
        PATCHES.append((name, doc, fn))
        return fn
    return deco


def text_field(old, new):
    """Same-width replacement for a space-padded text field."""
    if len(new) > len(old):
        raise ValueError(f'{new!r} is longer than the {len(old)}-byte field {old!r}')
    return old.encode('ascii'), new.ljust(len(old)).encode('ascii')


@patch('title-text', 'Backup-RAM warning screen names the game "Eternal Kombat"')
def title_text(ec, sources):
    # BACKUP.CO holds the warning as fixed-width, space-padded, NUL-separated lines
    old, new = text_field('  Eternal Champions: Challenge from     ',
                          '  Eternal Kombat: Challenge from')
    ec.patch_file('BACKUP.CO', 0x312, new, expect=old)


HOST_PL_ORIG = {}                 # host -> its own original .PL (its sheet numbering)


@patch('scorpion-slot', "Scorpion gets a fighter slot of his own: Blade's files copied into HOST's")
def scorpion_slot(ec, sources):
    """Scorpion starts as Blade (art, code, sounds, CPU behaviour): copy
    BLA.PL/CO/SND and BLAD.AI over HOST's files. Every later Scorpion patch
    edits HOST's copies, so Blade himself stays stock."""
    if HOST == 'BLA':
        return
    if SPEC is SCORPION:
        _start()
    HOST_PL_ORIG[HOST] = ec.read_file(host('PL'))          # its numbering, for renumber_sheets
    for ext in ('PL', 'CO'):
        ec.replace_file(host(ext), ec.read_file(f'BLA.{ext}'))
    snd, ids = host_sound(ec.read_file('BLA.SND'), ec.read_file(host('SND')))
    ec.replace_file(host('SND'), snd)
    SPEC.sound_ids = ids                     # Blade's sound ids -> the host's (mk_voice, mk_code)
    ec.replace_file(SPEC.ai, ec.read_file('BLAD.AI'))
    # Blade's code plays his sound ids: the host's now
    co = bytearray(ec.read_file(host('CO')))
    for i in range(0, len(co) - 4, 2):
        if co[i:i + 2] == b'\x30\x3c' and int.from_bytes(co[i + 2:i + 4], 'big') in ids:
            co[i + 2:i + 4] = ids[int.from_bytes(co[i + 2:i + 4], 'big')].to_bytes(2, 'big')
    ec.patch_file(host('CO'), 0, bytes(co))


def snd_chunks(b):
    o, out = 0, []
    while o + 6 <= len(b):
        ln = int.from_bytes(b[o:o + 4], 'big')
        if ln == 0:
            break
        out.append((o, int.from_bytes(b[o + 4:o + 6], 'big')))
        o += ln
    return out


def host_sound(blade, hostsnd):
    """Blade's sound bank for the host's slot: a .SND's tables (type $1C) and
    PCM chunks (type $20) carry the fighter's sample-slot numbers (+10) and
    its tables his sound ids; with Blade's, the fight loader crashed. Slots
    become the host's; Blade's ids map to the host's in order. Returns
    (bank, {Blade id: host id})."""
    b = bytearray(blade)
    ca, cb = snd_chunks(blade), snd_chunks(hostsnd)
    assert [t for _, t in ca] == [t for _, t in cb], 'different .SND layouts'
    ids = {}
    for (oa, t), (ob, _) in zip(ca, cb):
        b[oa + 10:oa + 12] = hostsnd[ob + 10:ob + 12]
        if t == 0x1C:
            na, nb = (int.from_bytes(x[o + 12:o + 14], 'big') for x, o in ((blade, oa), (hostsnd, ob)))
            assert na <= nb, f'the host has fewer sound ids ({nb}) than Blade ({na})'
            for i in range(na):                      # Blade's ids -> the host's first na
                ea = oa + int.from_bytes(blade[oa + 14 + 4 * i:oa + 18 + 4 * i], 'big')
                eb = ob + int.from_bytes(hostsnd[ob + 14 + 4 * i:ob + 18 + 4 * i], 'big')
                ids[int.from_bytes(blade[ea:ea + 2], 'big')] = int.from_bytes(hostsnd[eb:eb + 2], 'big')
                b[ea:ea + 2] = hostsnd[eb:eb + 2]
    return bytes(b), ids


@patch('scorpion-full', "All of Blade's sprite art (sheets $40-$43) rebuilt as Scorpion's MK poses")
def scorpion_full(ec, sources):
    """Every Blade pose is replaced by the matching Scorpion pose (see
    tools/scorpion_map.py), captured from MK by tools/mkmoves.py. Blade's
    code, timing and hit boxes are unchanged. Same file size: fits both
    player slots."""
    import os
    from inputs import ROOT
    import scorpion_full
    if not os.path.isdir(os.path.join(ROOT, 'extracted', SPEC.mk_dir, 'idle')):
        raise SystemExit(f'missing MK poses: run  .venv/bin/python tools/mkmoves.py --fighter={SPEC.key}')
    new, rep = scorpion_full.build(ec.read_file(host('PL')), ROOT)
    print(f'        {rep["poses"]} {SPEC.name.title()} poses in {rep["banks"]} banks, '
          f'{rep["bytes"]} of {rep["room"]} bytes; {len(set(rep["tight"]))} frames trimmed to fit')
    if rep.get('grow'):
        print(f'        BLA.PL grows by {rep["grow"]} bytes to {len(new)}')
    # always replace: the file may shrink (Blade's effect sheets are dropped)
    # and a patched-in-place file would keep its old tail, loaded for nothing
    ec.replace_file(host('PL'), new)


@patch('scorpion-palette', "Scorpion's MK palette replaces Blade's")
def scorpion_palette(ec, sources):
    import os
    import ecpl
    from inputs import ROOT
    import json
    import scorpion_full
    BLOOD = {12: 0x00A, 13: 0x00E}        # Genesis BGR: dark red, red (EC's spark colours 12/13)

    def moved(c):
        c = list(c)
        for dst, src in getattr(SPEC, 'palette_set', {}).items():
            c[dst] = c[src]
        for a, b in getattr(SPEC, 'blood_moves', scorpion_full.COLOUR_MOVES).items():
            c[b] = c[a]
        return c
    if not SPEC.blood:
        BLOOD = {}

        def moved(c):
            c = list(c)
            for dst, src in getattr(SPEC, 'palette_set', {}).items():
                c[dst] = c[src]
            return c
    cram = moved(json.load(open(os.path.join(ROOT, 'extracted', SPEC.mk_dir, 'idle', 'cram.json'))))
    # Blade's palette: BLA.CO, 16 colour words (found by matching his live CRAM)
    co = ec.read_file(host('CO'))
    old = co[0x3DE0:0x3E00]
    words = [ecpl.genesis_colour(c) for c in cram]
    for i, v in BLOOD.items():
        words[i] = v
    new = b''.join(v.to_bytes(2, 'big') for v in words)
    ec.patch_file(host('CO'), 0x3DE0, new, expect=old)
    # Blade's alternate palette (mirror matches) follows at $3E00. MK1's
    # Sub-Zero is Scorpion's sprites with another palette, so the mirror
    # match becomes Scorpion vs Sub-Zero.
    if SPEC.alt == 'p2':                      # the capture's player 2 wears the same sprites
        alt = moved(json.load(open(os.path.join(ROOT, 'extracted', SPEC.mk_dir, 'idle', 'cram_p2.json'))))
    else:                                     # a darker version of his own colours
        alt = [((c & 7) * 5 // 7) | (((c >> 3) & 7) * 5 // 7) << 3 | (((c >> 6) & 7) * 5 // 7) << 6 for c in cram]
    old = co[0x3E00:0x3E20]
    words = [ecpl.genesis_colour(c) for c in alt]
    for i, v in BLOOD.items():
        words[i] = v
    new = b''.join(v.to_bytes(2, 'big') for v in words)
    ec.patch_file(host('CO'), 0x3E00, new, expect=old)


@patch('scorpion-name', 'Health bar, versus screen, win messages and stats say SCORPION')
def scorpion_name(ec, sources):
    """Scorpion's slot is HOST_ID's (Blast's): his entries in each name table
    point at 'SCORPION'. Fixed-width win-message field: SUB.BIN $CB90.
    Pointer tables (by id - 2), each pointing into a NUL-separated list, so
    'SCORPION' is appended to the file and the entry moved to it:
     - HUD (health bar): SUB.BIN $5970 (loads at $6000)
     - versus screen: GAME.CO $DB1C ('\x04BLAST': first byte = centring; loads at $14000)
     - stats screen: STATS.CO $6B4 (loads at $34000)"""
    at, old, new = SPEC.win
    assert len(old) == len(new)
    ec.patch_file('SUB.BIN', at, new, expect=old)
    text = SPEC.name.encode('ascii')

    def repoint(name, base, table, text):
        b = ec.read_file(name)
        o = table + 4 * HOST_IDX
        at = (len(b) + 1) & ~1
        b = b + bytes(at - len(b)) + text
        b = b[:o] + (base + at).to_bytes(4, 'big') + b[o + 4:]
        ec.replace_file(name, b)
    repoint('SUB.BIN', 0x6000, 0x5970, text + b'\0')
    repoint('GAME.CO', 0x14000, 0xDB1C, b'\x01' + text + b'\0')
    repoint('STATS.CO', 0x34000, 0x6B4, text + b'\0')


@patch('scorpion-roster', "Scorpion's slot (Blast's) is unlocked on the select screen and set up as Blade's")
def scorpion_roster(ec, sources):
    """- The select grid shows a fighter when its bit (id - 2) is set in the
       unlock mask $1CC8(a6), initialised by two move.l #$004831FF at SUB.BIN
       $BC6C/$BC84 (one to $1CC8, one to $14A4): set HOST_IDX's.
     - The object descriptor (SUB.BIN $11E8C, word offsets by id, 34 bytes:
       first sprite sheet, module entry point, ...) is Blade's, since his
       art and code are Blade's.
     - Inside Scorpion's copy of Blade's module, Blade's checks of his own id
       (cmpi.w #9,$4C(an): mirror match) are for Scorpion's id."""
    if HOST == 'BLA':
        return
    for o in (0xBC6C - 0x6000, 0xBC84 - 0x6000):        # RAM $BC6C/$BC84
        sub = ec.read_file('SUB.BIN')
        assert sub[o:o + 2] == b'\x2d\x7c'
        v = int.from_bytes(sub[o + 2:o + 6], 'big')
        ec.patch_file('SUB.BIN', o + 2, (v | 1 << HOST_IDX).to_bytes(4, 'big'))
    sub = ec.read_file('SUB.BIN')
    tab = 0x11E8C - 0x6000
    rec = lambda fid: tab + int.from_bytes(sub[tab + 2 * fid:tab + 2 * fid + 2], 'big')
    ec.patch_file('SUB.BIN', rec(HOST_ID), sub[rec(9):rec(9) + 34])
    renumber_sheets(ec)
    co = bytearray(ec.read_file(host('CO')))
    import re
    n = 0
    for m in re.finditer(rb'\x0c[\x68-\x6f]\x00\x09\x00\x4c', bytes(co)):
        co[m.start() + 2:m.start() + 4] = HOST_ID.to_bytes(2, 'big')
        n += 1
    assert n == 5, f'expected 5 id checks in Blade\'s module, found {n}'
    ec.patch_file(host('CO'), 0, bytes(co))


# Blade's four art sheets ($40-$43, rebuilt as Scorpion's) are registered by
# number in one global table; in Scorpion vs Blade both files claimed them and
# the fight hung after loading. Scorpion's move to the host's range (Blast's
# sheets start at $8D). The effect sheets $44/$45 (rope, sparks) keep their
# numbers: both files hold the same art there.
SHEET_SHIFT = 0x8D - 0x40
ART_SHEETS = range(0x40, 0x44)
# frame words in Blade's module (BLA.CO offsets) outside the 12-byte animation
# steps, checked by hand: frame lists and other records, embedded effect
# descriptors, two move.w #frame
CO_FRAME_WORDS = (0x1B1C, 0x1B20, 0x1B24, 0x3F88, 0x450C, 0x49F4, 0x4A2C, 0x4A58, 0x4AEC, 0x5020,
                  0x1D1A, 0x1D24, 0x1D2E, 0x1D38, 0x1D42, 0x1D4C, 0x1D56,
                  0x2BD8, 0x2F0E, 0x2F18, 0x341A, 0x3B2A, 0x30B8, 0x30F0,
                  0x41D0, 0x41F0, 0x46AC, 0x46CC, 0x4A9C, 0x4AB6, 0x4B2C, 0x4C70, 0x5198)


def module_frame_words(co):
    """Offsets of frame words (sheet $40-$43) in Blade's module: animation
    steps (12 bytes, frame at +4 followed by a small word, in runs) plus
    CO_FRAME_WORDS."""
    W = lambda o: int.from_bytes(co[o:o + 2], 'big')
    cand = {o for o in range(0, len(co) - 3, 2) if co[o] in ART_SHEETS and co[o + 1] < 0x70}
    out = {o for o in cand if (o + 12 in cand or o - 12 in cand) and W(o + 2) <= 0x10}
    for o in CO_FRAME_WORDS:
        assert co[o] in ART_SHEETS, hex(o)
        out.add(o)
    return sorted(out)


def renumber_sheets(ec):
    import re
    co = bytearray(ec.read_file(host('CO')))
    words = module_frame_words(co)
    for o in words:
        co[o] += SHEET_SHIFT
    n = 0                                    # move.b #sheet,$1A(an): the sheet byte alone
    for m in re.finditer(rb'[\x11\x13\x15\x17\x19\x1b\x1d]\x7c\x00[\x40-\x43]\x00\x1a', bytes(co)):
        co[m.start() + 3] += SHEET_SHIFT
        n += 1
    ec.patch_file(host('CO'), 0, bytes(co))
    # The .PL's tile sources (chunk type 0: +10 = source id * 4) are numbered
    # per fighter too (Blade $8A-$94, Blast $124-...), and each sheet (type 4:
    # +10 = sheet * 4, +12 = its tile source id) points at one: Blade's ids
    # in both files also hung Scorpion vs Blade. They become the host's, in
    # order.
    pl = bytearray(ec.read_file(host('PL')))
    own = HOST_PL_ORIG[HOST]
    def chunks(b):
        o, out = 0, []
        while o + 12 <= len(b):
            ln = int.from_bytes(b[o:o + 4], 'big')
            if ln == 0:
                break
            out.append((o, int.from_bytes(b[o + 4:o + 6], 'big')))
            o += ln
        return out
    src = [int.from_bytes(pl[o + 10:o + 12], 'big') // 4 for o, t in chunks(pl) if t == 0]
    dst = getattr(SPEC, 'src_ids', None) or [int.from_bytes(own[o + 10:o + 12], 'big') // 4 for o, t in chunks(own) if t == 0]
    assert len(dst) >= len(src), (src, dst)
    remap = dict(zip(src, dst))
    k = 0
    for o, t in chunks(pl):
        if t == 0:
            pl[o + 10:o + 12] = (4 * remap[int.from_bytes(pl[o + 10:o + 12], 'big') // 4]).to_bytes(2, 'big')
        elif t == 4:
            v = int.from_bytes(pl[o + 10:o + 12], 'big')
            if v // 4 in ART_SHEETS:
                pl[o + 10:o + 12] = (v + 4 * SHEET_SHIFT).to_bytes(2, 'big')
                k += 1
            ts = int.from_bytes(pl[o + 12:o + 14], 'big')
            pl[o + 12:o + 14] = remap[ts].to_bytes(2, 'big')
    assert k == 4, k
    ec.patch_file(host('PL'), 0, bytes(pl))
    sub = ec.read_file('SUB.BIN')
    tab = 0x11E8C - 0x6000
    rec = tab + int.from_bytes(sub[tab + 2 * HOST_ID:tab + 2 * HOST_ID + 2], 'big')
    assert sub[rec] == 0 and sub[rec + 1] in ART_SHEETS        # first word: his first sheet ($0040)
    ec.patch_file('SUB.BIN', rec + 1, bytes([sub[rec + 1] + SHEET_SHIFT]))
    print(f'        sheets: {len(words)} frame words, {n} sheet bytes, {k} registrations moved by +${SHEET_SHIFT:X}')


@patch('scorpion-fatality-stats', 'Stats screen says "Finishing Move: Fatality" after Scorpion\'s fatality')
def scorpion_fatality_stats(ec, sources):
    """STATS.CO picks the finishing-move text from a 5-entry table at $65A
    indexed by $1CD4(a6) (0 None, 1 Overkill, 2 Sudden Death, 3 Vendetta,
    4 Cinekill; record = x, y, text). The fatality ends the round as type 3
    (GAME.CO scores by that index, so no new type). Both `lea $3465A(pc),a2`
    become `bsr` to a helper appended to the file: if the finish is type 3 and
    the winner (the opponent of the loser at $1490(a6)) is an MK fighter, use
    a copy of the table whose entry 3 says 'Fatality'."""
    BASE, TAB, SITES = 0x34000, 0x65A, (0x498, 0x4D0)
    st = ec.read_file('STATS.CO')
    for s in SITES:
        assert st[s:s + 2] == b'\x45\xFA' and s + 2 + int.from_bytes(st[s + 2:s + 4], 'big', signed=True) == TAB, hex(s)
    rec = st[0x698:0x6A4]
    assert rec == b'\x00\x07\x00\x17Vendetta', rec
    at = (len(st) + 1) & ~1
    st = st + bytes(at - len(st))
    helper = at
    code = bytearray()
    w = lambda *v: code.extend(b''.join(x.to_bytes(2, 'big') for x in v))
    def pcrel(target):                      # displacement word for an opcode at helper + len(code) - 2
        return (target - (helper + len(code))) & 0xFFFF
    ids = [sp.host_id for sp in (SCORPION, RAIDEN, JOHNNY, SUBZERO)]   # any MK winner
    w(0x45FA); w(pcrel(TAB))                # lea table(pc),a2
    w(0x0C6E, 0x0003, 0x1CD4)               # cmpi.w #3,$1CD4(a6)
    bne_out = len(code); w(0x6600)          # bne.s out (filled below)
    w(0x206E, 0x1490)                       # movea.l $1490(a6),a0   loser
    w(0x2068, 0x008C)                       # movea.l $8C(a0),a0     winner
    beqs = []
    for i in ids:
        w(0x0C68, i, 0x004C)                # cmpi.w #id,$4C(a0)
        beqs.append(len(code)); w(0x6700)   # beq.s yes
    bra_out = len(code); w(0x6000)          # bra.s out
    yes = len(code)
    fix = len(code)
    w(0x45FA, 0)                            # lea alt(pc),a2
    out = len(code)
    w(0x4E75)                               # out: rts
    for at_, to in [(bne_out, out), (bra_out, out)] + [(b, yes) for b in beqs]:
        code[at_ + 1] = (to - (at_ + 2)) & 0xFF
    alt = helper + len(code)
    code[fix + 2:fix + 4] = ((alt - (helper + fix + 2)) & 0xFFFF).to_bytes(2, 'big')
    fat = alt + 20
    ents = [int.from_bytes(st[TAB + 4 * i:TAB + 4 * i + 4], 'big') for i in range(5)]
    ents[3] = BASE + fat
    for e in ents:
        code.extend(e.to_bytes(4, 'big'))
    code.extend(b'\x00\x07\x00\x17Fatality\0\0')
    st = st + bytes(code)
    for s in SITES:                         # lea -> bsr.w helper (same 4 bytes)
        st = st[:s] + b'\x61\x00' + ((helper - (s + 2)) & 0xFFFF).to_bytes(2, 'big') + st[s + 4:]
    ec.replace_file('STATS.CO', st)


@patch('scorpion-portrait', "Versus screen shows Scorpion's MK portrait instead of Blade's")
def scorpion_portrait(ec, sources):
    """EC's versus portrait: 9x13 tiles (72x104) stored row by row in
    BIODAT.BIN at $D4B8 (Blade) and again in GAME.DAT at $2A390 (the copy the
    versus screen loads), drawn with palette line 2 = the 16 colours at
    GAME.CO $E188 (also at $55E2). The gold frame is part of the portrait:
    the outer FRAME pixels and the palette entries they use are kept.
    Scorpion's portrait comes from MK's select screen (tools/mkportrait.py ->
    extracted/mk_moves/portrait.png, 42x50), scaled to the inside of the
    frame and reduced to the remaining palette entries."""
    import os
    import numpy as np
    from PIL import Image
    from inputs import ROOT
    import ecpl
    src = os.path.join(ROOT, 'extracted', SPEC.mk_dir, 'portrait.png')
    if not os.path.exists(src):
        raise SystemExit(f'missing MK portrait: run  .venv/bin/python tools/mkportrait.py --fighter {SPEC.key}')
    W, H, FRAME = 72, 104, 2
    TILES, DAT_TILES, PALS = None, PORTRAIT[HOST_IDX], (0xE048 + 32 * (HOST_IDX + 3),)
    bio = ec.read_file('GAME.DAT')                          # the copy the versus screen loads
    TILES = DAT_TILES
    old = np.zeros((H, W), np.uint8)                       # the host's portrait, indexed
    for t in range(117):
        ty, tx = divmod(t, 9)
        raw = bio[TILES + 32 * t:TILES + 32 * t + 32]
        for r in range(8):
            for c in range(4):
                v = raw[r * 4 + c]
                old[ty * 8 + r, tx * 8 + 2 * c] = v >> 4
                old[ty * 8 + r, tx * 8 + 2 * c + 1] = v & 15
    ring = np.ones((H, W), bool)
    ring[FRAME:H - FRAME, FRAME:W - FRAME] = False
    keep = sorted(set(old[ring].tolist()) | {0})           # frame colours (+ transparent)
    free = [k for k in range(16) if k not in keep]
    iw, ih = W - 2 * FRAME, H - 2 * FRAME
    im = Image.open(src).convert('RGB')
    w = round(im.width * ih / im.height)
    im = im.resize((w, ih), Image.LANCZOS)
    x0 = (w - iw) // 2
    im = im.crop((x0, 0, x0 + iw, ih))
    q = im.quantize(colors=len(free), method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    qi = np.asarray(q, np.uint8)
    new = old.copy()
    new[FRAME:H - FRAME, FRAME:W - FRAME] = np.array(free, np.uint8)[qi]
    pal = q.getpalette()
    co = ec.read_file('GAME.CO')
    for P in PALS:
        words = bytearray(co[P:P + 32])
        for j, k in enumerate(free):
            r, g, b = pal[3 * j:3 * j + 3]
            words[2 * k:2 * k + 2] = ((round(b / 255 * 7) << 9) | (round(g / 255 * 7) << 5)
                                      | (round(r / 255 * 7) << 1)).to_bytes(2, 'big')
        ec.patch_file('GAME.CO', P, bytes(words))
    tiles = b''
    for ty in range(H // 8):
        for tx in range(W // 8):
            tiles += b''.join(ecpl.tiles_of(new, tx, ty, 1, 1))
    ec.patch_file('GAME.DAT', DAT_TILES, tiles)
    print(f'        portrait: frame keeps colours {keep}, {SPEC.name.title()} gets {len(free)}')


@patch('scorpion-icon', "Select screen shows Scorpion's MK portrait in his slot")
def scorpion_icon(ec, sources):
    """Select-screen icon: 4x6 tiles (32x48) row by row in GAME.DAT at $1FAC8,
    drawn with the select screen's palette line 2, which all icons share, so
    Scorpion's MK portrait is mapped to the nearest of those colours."""
    import os
    import numpy as np
    from PIL import Image
    from inputs import ROOT
    import ecpl
    LINE2 = [0x0422, 0x0200, 0x0220, 0x0422, 0x0444, 0x0A20, 0x0468, 0x0460,
             0x020E, 0x064A, 0x046C, 0x048C, 0x02A0, 0x08CA, 0x02CE, 0x0EC6]
    rgb = np.array([[(c >> 1 & 7) * 36, (c >> 5 & 7) * 36, (c >> 9 & 7) * 36] for c in LINE2], float)
    W, H, AT = 32, 48, 0x1FAC8 + 0x300 * (HOST_IDX - 7)   # GAME.DAT: one $300-byte icon per id - 2 (Blade's at $1FAC8)
    im = Image.open(os.path.join(ROOT, 'extracted', SPEC.mk_dir, 'portrait.png')).convert('RGB')
    w = round(im.width * H / im.height)
    im = im.resize((w, H), Image.LANCZOS)
    x0 = (w - W) // 2
    a = np.asarray(im.crop((x0, 0, x0 + W, H)), float)
    d = ((a[:, :, None, :] - rgb[None, None, 1:, :]) ** 2).sum(-1)
    idx = (d.argmin(-1) + 1).astype(np.uint8)
    tiles = b''
    for ty in range(H // 8):
        for tx in range(W // 8):
            tiles += b''.join(ecpl.tiles_of(idx, tx, ty, 1, 1))
    ec.patch_file('GAME.DAT', AT, tiles)


def mk_sample(name):
    """(rate, signed 8-bit samples) of a named sample in MK's 8SVX sound files."""
    import glob, os
    from inputs import ROOT
    for f in sorted(glob.glob(os.path.join(ROOT, 'extracted', 'mk_us', 'SFX*.BIN'))):
        d = open(f, 'rb').read()
        p = 0
        while p < len(d) - 12:
            if d[p:p + 4] != b'FORM':
                p += 2
                continue
            ln = int.from_bytes(d[p + 4:p + 8], 'big')
            form, q, nm, rate, body = d[p:p + 8 + ln], 12, '', 0, b''
            while q < len(form) - 8:
                cid, cl = form[q:q + 4], int.from_bytes(form[q + 4:q + 8], 'big')
                if cid == b'NAME':
                    nm = form[q + 8:q + 8 + cl].split(b'\0')[0].decode('latin-1')
                elif cid == b'VHDR':
                    rate = int.from_bytes(form[q + 20:q + 22], 'big')
                elif cid == b'BODY':
                    body = form[q + 8:q + 8 + cl]
                q += 8 + cl + (cl & 1)
            if nm.upper() == name.upper():
                return rate, body
            p += 8 + ln + (ln & 1)
    raise KeyError(name)


def mk_form(file, which):
    """(rate, signed 8-bit samples) of an 8SVX sample in one MK sound file,
    by NAME or by index (some have no name)."""
    import os
    from inputs import ROOT
    d = open(os.path.join(ROOT, 'extracted', 'mk_us', file), 'rb').read()
    p, k = 0, 0
    while p < len(d) - 12:
        if d[p:p + 4] != b'FORM':
            p += 2
            continue
        ln = int.from_bytes(d[p + 4:p + 8], 'big')
        form, q, nm, rate, body = d[p:p + 8 + ln], 12, '', 0, b''
        while q < len(form) - 8:
            cid, cl = form[q:q + 4], int.from_bytes(form[q + 4:q + 8], 'big')
            if cid == b'NAME':
                nm = form[q + 8:q + 8 + cl].split(b'\0')[0].decode('latin-1')
            elif cid == b'VHDR':
                rate = int.from_bytes(form[q + 20:q + 22], 'big')
            elif cid == b'BODY':
                body = form[q + 8:q + 8 + cl]
            q += 8 + cl + (cl & 1)
        if which == k or (isinstance(which, str) and nm.upper() == which.upper()):
            return rate, body
        p += 8 + ln + (ln & 1)
        k += 1
    raise KeyError((file, which))


def to_rf5c164(body, rate_in, rate_out, length):
    """Signed 8-bit PCM -> Sega CD PCM (RF5C164 sign-magnitude, $FF reserved),
    resampled and trimmed/padded with silence to exactly length bytes."""
    import numpy as np
    s = np.frombuffer(body, dtype=np.int8).astype(float)
    n = int(len(s) * rate_out / rate_in)
    t = np.linspace(0, len(s) - 1, n)
    r = np.interp(t, np.arange(len(s)), s)
    out = bytearray()
    for v in r[:length]:
        v = int(round(v))
        out.append(0x80 | min(v, 126) if v >= 0 else min(-v, 127))
    return bytes(out.ljust(length, b'\x80'))


VOICE_RATE = 5200                 # Hz for Scorpion's MK lines
VOICE_LINES = [                   # (MK sample, sound id, Hz) in clip order
    ('GETOHERE.SVX', 0x05E6, VOICE_RATE),     # Blade's $06D6 in the host's numbering (Blast)
    ('FINISHim.SVX', 0x05EC, VOICE_RATE),     # Blade's $06D9, unused by his code
    ('FINISHER.SVX', 0x05EE, VOICE_RATE),     # Blade's $06DB: 'FINISH HER' (mkinputs picks it for a woman)
]
BANK_ROOM = 17702                 # Blade's PCM chunk: Scorpion's bank stays this size or less
BLADE_SOUND_CALLS = (0x0F0E, 0x107E, 0x237E, 0x23A6, 0x272C)   # his $06D7/$06DA/$06DB plays: skipped


@patch('scorpion-voice', 'Scorpion\'s MK sounds: "GET OVER HERE!", "FINISH HIM" / "FINISH HER", the flame roar')
def scorpion_voice(ec, sources):
    """Sounds are played with jsr $6D58, d0 = sound id. BLA.SND's second
    sound table (chunk at $1624, entries of $1A bytes: id word, ..., rate word
    in Hz at +10, clip word at +$18) maps ids $06D6-$06DB to clips of the PCM
    chunk at $16CA. The chunk (+10 sample slot, +12 clip 0's length) holds
    clip 0, then for every further clip a 4-byte length and its bytes (as
    in every EC .SND: e.g. BLA had 00 00 16 E4 at clip 0's end). Lengths
    include the closing $FF. The driver copies each clip to its own page of
    sound RAM and stops a channel at its clip's end. Here: GET OVER HERE,
    FINISH HIM, FINISH HER, a short silence (for the ids left over)."""
    snd = bytearray(ec.read_file(host('SND')))
    chunk, table = 0x16CA, 0x1624
    clen = int.from_bytes(snd[chunk:chunk + 4], 'big')
    assert snd[chunk + 4:chunk + 6] == b'\x00\x20' and int.from_bytes(snd[chunk + 12:chunk + 16], 'big') == 0x1488
    clips = []
    for name, _, hz in VOICE_LINES:
        rate, body = mk_sample(name)
        pcm = to_rf5c164(body, rate, hz, int(len(body) * hz / rate))
        clips.append(pcm + b'\x80' * ((len(pcm) + 1) & 1) + b'\xff')    # even length with the $FF
    clips.append(b'\x80' * 15 + b'\xff')
    assert all(len(c) % 2 == 0 for c in clips), 'clip lengths must be even (the driver reads the next length as a long)'
    data = bytearray(clips[0])
    for c in clips[1:]:
        data += len(c).to_bytes(4, 'big') + c
    # the driver reads clips until the chunk ends: the chunk must end right after the last
    if len(data) & 1:
        data += b'\0'
    assert len(data) <= BANK_ROOM, f'voice lines need {len(data)} bytes, room {BANK_ROOM}'
    assert chunk + clen == len(snd) - 4, 'the PCM chunk is the last one'
    snd[chunk:] = (16 + len(data)).to_bytes(4, 'big') + snd[chunk + 4:chunk + 12] \
        + len(clips[0]).to_bytes(4, 'big') + bytes(data) + bytes(4)
    ids = dict((sid, (k, hz)) for k, (_, sid, hz) in enumerate(VOICE_LINES))
    for i in range(5):
        e = table + int.from_bytes(snd[table + 0x0E + 4 * i:table + 0x12 + 4 * i], 'big')
        sid = int.from_bytes(snd[e:e + 2], 'big')
        clip, hz = ids.get(sid, (len(VOICE_LINES), VOICE_RATE))
        snd[e + 0x18:e + 0x1A] = clip.to_bytes(2, 'big')
        snd[e + 10:e + 12] = hz.to_bytes(2, 'big')
    ec.replace_file(host('SND'), bytes(snd))
    for o in BLADE_SOUND_CALLS:                       # move.w #id,d0; jsr $6D58 -> bra.s past it
        cur = ec.read_file(host('CO'))[o:o + 10]
        assert cur[:2] == b'\x30\x3c' and cur[4:] == bytes.fromhex('4eb900006d58'), hex(o)
        ec.patch_file(host('CO'), o, b'\x60\x08')


# The other MK fighters' special-move sounds (MK's own samples), started by
# their block when the move starts (mkinputs.generic_block 'sounds'): on
# Blade's voice ids $06D6.. in order (his own plays of them are skipped)
_FINISH = [('FINISHim.SVX', 'finish'), ('FINISHER.SVX', 'finish_f')]   # MK: 'FINISH HIM' / 'FINISH HER'
GENERIC_VOICE = {'raiden': [('RAIDDive.SVX', 0x35), ('spark2.SVX', 0x34)] + _FINISH,    # torpedo yell, lightning
                 'johnny': [('jctrails.SVX', 0x35), ('FIRING2.SVX', 0x34)] + _FINISH,   # shadow kick, green bolt
                 'subzero': [('subzwep.SVX', 0x34), ('subslide.SVX', 0x35)] + _FINISH}  # ice blast, slide
GENERIC_VOICE_RATE = 8000        # Hz at most; lower (VOICE_RATES) until his sounds fit the bank
VOICE_RATES = (8000, 7000, 6400, 6000, 5600, 5200, 4800)
BLADE_VOICE_IDS = (0x06D6, 0x06D7, 0x06D8, 0x06D9, 0x06DA, 0x06DB)


def mk_voice(ec, sources):
    """As scorpion_voice, for SPEC (Raiden, Johnny, Sub-Zero): his MK
    special-move sounds in his copy of Blade's bank; every other voice id
    plays silence; Blade's own plays of his voice ids are skipped."""
    lines = GENERIC_VOICE.get(SPEC.key, [])
    ids = SPEC.sound_ids
    snd = bytearray(ec.read_file(host('SND')))
    chunk, table = 0x16CA, 0x1624
    clen = int.from_bytes(snd[chunk:chunk + 4], 'big')
    assert snd[chunk + 4:chunk + 6] == b'\x00\x20' and chunk + clen == len(snd) - 4
    for hz in VOICE_RATES:
        clips = []
        for name, _ in lines:
            rate, body = mk_sample(name)
            pcm = to_rf5c164(body, rate, hz, int(len(body) * hz / rate))
            clips.append(pcm + b'\x80' * ((len(pcm) + 1) & 1) + b'\xff')
        clips.append(b'\x80' * 15 + b'\xff')
        data = bytearray(clips[0])
        for c in clips[1:]:
            data += len(c).to_bytes(4, 'big') + c
        if len(data) <= BANK_ROOM:
            break
    assert len(data) <= BANK_ROOM, f'{SPEC.name}: sounds need {len(data)} bytes, room {BANK_ROOM}'
    snd[chunk:] = (16 + len(data)).to_bytes(4, 'big') + snd[chunk + 4:chunk + 12] \
        + len(clips[0]).to_bytes(4, 'big') + bytes(data) + bytes(4)
    avail = [ids[b] for b in BLADE_VOICE_IDS if b in ids]   # (not every voice id has a host counterpart)
    assert len(lines) <= len(avail), f'{SPEC.name}: {len(lines)} sounds, {len(avail)} voice ids'
    mine = {avail[k]: k for k in range(len(lines))}
    for i in range(int.from_bytes(snd[table + 0x0C:table + 0x0E], 'big')):
        e = table + int.from_bytes(snd[table + 0x0E + 4 * i:table + 0x12 + 4 * i], 'big')
        sid = int.from_bytes(snd[e:e + 2], 'big')
        snd[e + 0x18:e + 0x1A] = mine.get(sid, len(lines)).to_bytes(2, 'big')
        snd[e + 10:e + 12] = hz.to_bytes(2, 'big')
    ec.replace_file(host('SND'), bytes(snd))
    co = bytearray(ec.read_file(host('CO')))
    voice = {ids[b] for b in BLADE_VOICE_IDS if b in ids}
    n = 0
    for i in range(0, len(co) - 10, 2):           # move.w #id,d0; jsr $6D58 -> bra.s past it
        if co[i:i + 2] == b'\x30\x3c' and int.from_bytes(co[i + 2:i + 4], 'big') in voice \
                and co[i + 4:i + 10] == bytes.fromhex('4eb900006d58'):
            co[i:i + 2] = b'\x60\x08'
            n += 1
    ec.replace_file(host('CO'), bytes(co))
    SPEC.voice = {move: avail[k] for k, (_, move) in enumerate(lines)}
    print(f'        {len(lines)} MK sounds at {hz} Hz, {len(data)} bytes; {n} of Blade\'s voice plays skipped')


@patch('scorpion-inputs', "Scorpion's specials use MK inputs (back, back + LP = spear); Blade's own specials removed")
def scorpion_inputs(ec, sources):
    """See tools/mkinputs.py: a new 'two taps + button' move type in PLYR.CO's
    special-move recogniser, and Blade's move list replaced by Scorpion's."""
    import mkinputs
    sub = ec.read_file('SUB.BIN')
    at = (len(sub) + 1) & ~1
    plyr, bla, extra = mkinputs.build(ec.read_file('PLYR.CO'), mkinputs.spear_script(ec.read_file(host('CO'))),
                                      0x6000 + at)
    put_sub(ec, sub + bytes(at - len(sub)) + extra)
    ec.replace_file('PLYR.CO', plyr)
    ec.replace_file(host('CO'), bla)


CHAIN_START = 0x3FA0              # Blade's move scripts: PLYR $1A278 walks them into the move table


def mk_attack_scripts(ec, sources):
    """His basic attacks play MK's animation (tools/mkscripts.py). A fighter's
    move table is built at fight start by walking the chain of move scripts
    in his module (PLYR $1A278: header word 0 = table slot, word 1 = steps;
    a negative word ends it; a later script with the same slot wins): the
    MK scripts go at the chain's end, before its terminator. Before
    scorpion-roster: the sheet renumbering then covers their frames too."""
    import mkscripts
    from inputs import ROOT
    import os
    blade = open(os.path.join(ROOT, 'extracted', 'ec_us', 'BLA.CO'), 'rb').read()
    scripts, _ = mkscripts.build(blade, SPEC.mk_dir)
    co = bytearray(ec.read_file(host('CO')))
    W = lambda o: int.from_bytes(co[o:o + 2], 'big', signed=True)
    o = CHAIN_START
    while W(o) >= 0:
        o += 20 + 12 * (W(o + 2) + 1)
    end = bytes(co[o:o + 2])
    body = b''
    for mid, sc in sorted(scripts.items()):
        n = int.from_bytes(sc[2:4], 'big') + 1
        body += sc[:20 + 12 * n]            # without the trailing word (in the chain, the next header)
    co[o:o + 2] = body + end
    ec.replace_file(host('CO'), bytes(co))
    print(f'        {len(scripts)} MK attack scripts appended at ${o:X} ({len(body)} bytes)')


# Blade's dash (move $35, BLA.CO $4F74: header speed 10 px/frame, its 41:62
# step 6 ticks: ~13 frames, ~130 px) as the MK fighters' flights: (px/frame,
# ticks of 2 frames). MK (measured): Raiden's torpedo flies ~38 frames head
# first across the screen; Sub-Zero's slide covers ~100 px
DASH_SCRIPT = 0x4F74
DASH_TUNE = {'raiden': (7, 19), 'subzero': (6, 9)}


def pl_chain_end(pl):
    """Offset of a .PL's terminating zero chunk length."""
    o = 0
    while int.from_bytes(pl[o:o + 4], 'big'):
        o += int.from_bytes(pl[o:o + 4], 'big')
    return o


def mk_code(ec, sources):
    """The fighter's MK code block (mkinputs.generic_block: his MK attack
    animations, toward + Y throws behind, MK's walk cycle) at EXT_OFF in his
    module, where the PLYR stubs find it (mkinputs._block)."""
    import mkinputs
    co = bytearray(mkinputs.recovery_still(ec.read_file(host('CO'))))   # his projectile's recovery: no drift
    if SPEC.key in DASH_TUNE:                # Blade's dash as his MK flight (torpedo, slide)
        speed, ticks = DASH_TUNE[SPEC.key]
        assert int.from_bytes(co[DASH_SCRIPT + 4:DASH_SCRIPT + 8], 'big') == 0xA0000
        co[DASH_SCRIPT + 4:DASH_SCRIPT + 8] = (speed << 16).to_bytes(4, 'big')
        st = DASH_SCRIPT + 20 + 12 * 4               # its 41:62 step (the hit)
        assert co[st + 1] == 0x62 and int.from_bytes(co[st + 2:st + 4], 'big') == 6, co[st:st + 12].hex()
        co[st + 2:st + 4] = ticks.to_bytes(2, 'big')
    co = bytes(co)
    assert len(co) <= mkinputs.EXT_OFF, f'{host("CO")} reaches the block offset'
    mkinputs.GEN_TAIL.update(off=None, data=b'')
    if HOST_ID in mkinputs.TAIL_FIGHTERS:    # his scripts and fatality data after his .PL's chunk chain
        pl = ec.read_file(host('PL'))
        end = pl_chain_end(pl)
        mkinputs.GEN_TAIL['off'] = (end + 4 + 1) & ~1     # past the zero length that stops EC's loader
        import mkprojectile
        from mkprojectile import chunks
        sh = next(o for o, ln, t in chunks(pl) if t == 4 and int.from_bytes(pl[o + 10:o + 12], 'big') // 4 == mkprojectile.SHEET)
        mkinputs.GEN_TAIL['fx_src'] = int.from_bytes(pl[sh + 12:sh + 14], 'big') // 2   # its tile source's id ($D448 / -$67D0)
    blk = mkinputs.generic_block(HOST_ID, SHEET_SHIFT, SPEC.mk_dir, getattr(SPEC, 'voice', {}))
    if mkinputs.GEN_TAIL['data']:
        off, tail = mkinputs.GEN_TAIL['off'], mkinputs.GEN_TAIL['data']
        from scorpion_full import MAX_PL
        assert off + len(tail) <= MAX_PL, f'{host("PL")} + its tail over {MAX_PL}'
        ec.replace_file(host('PL'), pl[:end + 4] + bytes(off - end - 4) + tail)
        print(f'        {len(tail)} bytes of scripts/fatality data after {host("PL")}\'s chunk chain (+${off:X})')
    assert mkinputs.EXT_OFF + len(blk) <= 0x6800, 'block overflows the module slot'
    ec.replace_file(host('CO'), co + bytes(mkinputs.EXT_OFF - len(co)) + blk)
    print(f'        MK code block: {len(blk)} bytes at ${mkinputs.EXT_OFF:X}')


def mk_projectile(ec, sources):
    """His MK projectile's flying art (tools/mkprojectile.py) in his effect
    sheet $45, for the object mkinputs.emit_proj flies across the screen."""
    import mkprojectile, scorpion_full
    import mkinputs
    extra = [rec for _, rec in mkinputs.szf_heads()] if HOST_ID == mkinputs.SUBZERO_ID else []
    pl, (nf, ni) = mkprojectile.build(ec.read_file(host('PL')), SPEC.key, SPEC.mk_dir, scorpion_full.remap_colours, extra)
    if extra:
        print(f'        + {len(extra)} EC fighters\' severed heads (his fatality) from frame {nf + ni}')
    ec.replace_file(host('PL'), pl)
    print(f'        projectile: {nf} flight + {ni} impact frames in sheet ${mkprojectile.SHEET:X}')


# Raiden, Johnny Cage, Sub-Zero: the same patches with their settings (no MK
# specials, voice or fatality yet)
for _spec, _slot in ((RAIDEN, "Chin Wo's"), (JOHNNY, "Zuni's"), (SUBZERO, "Yappy's")):
    for _n, _fn in (('slot', scorpion_slot), ('full', scorpion_full), ('proj', mk_projectile), ('palette', scorpion_palette),
                    ('name', scorpion_name), ('roster', scorpion_roster), ('voice', mk_voice), ('mkcode', mk_code),
                    ('portrait', scorpion_portrait),
                    ('icon', scorpion_icon)):
        PATCHES.append((f'{_spec.key}-{_n}', f"{_spec.name.title()} ({_slot} slot): as scorpion-{_n}",
                        for_spec(_spec, _fn)))


THROW_SKIP = ('PLYR.CO', 'GAME.CO', 'STATS.CO', 'CINE.CO', 'CREDITS.CO', 'BACKUP.CO', 'ENDMSG.CO')


def throw_table(co):
    """(offset, entry size, [23 entry offsets]) of a fighter module's throw
    victim table: one entry per victim id 2-24 (relative to the table), each
    the victim's poses during the throw as 10-byte records (frame word in
    the VICTIM's sheets first). Found by shape; checked by the victims'
    sheets (every one of the 23 modules that throw matches)."""
    import math
    for t in range(0, len(co) - 92, 2):
        e = [int.from_bytes(co[t + 4 * i:t + 4 * i + 4], 'big', signed=True) for i in range(23)]
        if min(e) < 92 or max(e) > 0x3000:
            continue
        u = sorted(set(e))
        if len(u) < 15:
            continue
        g = 0
        for i in range(len(u) - 1):
            g = math.gcd(g, u[i + 1] - u[i])
        if g >= 16 and (u[-1] - u[0]) // g <= 30:
            return t, g, e
    return None


@patch('mk-throw-victims', "Every fighter's throw shows an MK victim in his own (Blade-numbered) poses")
def mk_throw_victims(ec, sources):
    """Each attacker's throw table has an entry per victim with the victim's
    frame words; the MK fighters' ids (their hosts') hold the hosts' poses.
    They get the attacker's entry for Blade (whose frames they use) moved to
    their own sheets. In the MK fighters' own modules (copies of Blade's) the
    sheet renumbering also moved the Blade entry: put back."""
    import os
    from inputs import ROOT
    mk = [(sp.host_id, sp.sheet_base - 0x40, sp.host) for sp in (SCORPION, RAIDEN, JOHNNY, SUBZERO)]
    hosts = {h for _, _, h in mk}
    blade = open(os.path.join(ROOT, 'extracted', 'ec_us', 'BLA.CO'), 'rb').read()
    n = 0
    for name in sorted(ec.files()):
        if not name.endswith('.CO') or name in THROW_SKIP:
            continue
        mine = name[:-3] in hosts
        orig = blade if mine else ec.read_file(name)
        found = throw_table(orig)
        if not found:
            continue
        t, size, e = found
        b9 = bytes(orig[t + e[7]:t + e[7] + size])
        co = bytearray(ec.read_file(name))
        if mine:
            co[t + e[7]:t + e[7] + size] = b9
        for fid, shift, _ in mk:
            ent = bytearray(b9)
            for w in range(0, size - 1, 2):
                if 0x40 <= ent[w] <= 0x43:
                    ent[w] += shift
            co[t + e[fid - 2]:t + e[fid - 2] + size] = ent
        ec.patch_file(name, 0, bytes(co))
        n += 1
    print(f'        {n} fighters\' throw tables')


THROW_LIFT = 0.5                  # victim heights in the MK fighters' throws (x Blade's)
THROW_HOLD = 4                    # ticks (2 frames) the victim stays overhead (Blade's 7)
# px further the victim is left at the end (MK: Raiden's and Johnny's
# overhead tosses land him ~155 px behind, the roll throws ~110-120)
THROW_FAR = {'raiden': 35, 'johnny': 35}
THROW_GRAB_DX = 56                # px: the victim's furthest in front of him while grabbed (Blade's up to 117)


@patch('mk-throw-arc', "The MK fighters' throws lift the victim to MK's height, briefly (MK's roll throw)")
def mk_throw_arc(ec, sources):
    """Blade's throw holds the victim 156 px up (feet) for 14 frames; MK's
    roll throw takes him over ~74 px up, briefly (measured, states/mk_2p.state).
    Each victim record (throw_table: 10-byte steps, frame, dx, dy, flags,
    ticks) in the MK fighters' modules: lifts (negative dy) scaled by
    THROW_LIFT, the overhead step (3) held THROW_HOLD ticks. The release and
    the landing are mkinputs' (emit_throwfix)."""
    import mkinputs
    for sp in (SCORPION, RAIDEN, JOHNNY, SUBZERO):
        name = sp.host + '.CO'
        co = bytearray(ec.read_file(name))
        t, size, e = throw_table(co)
        for eo in sorted(set(e)):
            for st in range(size // 10):
                o = t + eo + 10 * st
                dy = int.from_bytes(co[o + 4:o + 6], 'big', signed=True)
                if dy < 0:
                    co[o + 4:o + 6] = round(dy * THROW_LIFT).to_bytes(2, 'big', signed=True)
                if st == 3:
                    co[o + 8:o + 10] = min(int.from_bytes(co[o + 8:o + 10], 'big'), THROW_HOLD).to_bytes(2, 'big')
                if st == size // 10 - 1 and THROW_FAR.get(sp.key):   # the last step: tossers' victims land further
                    dx = int.from_bytes(co[o + 2:o + 4], 'big', signed=True)
                    co[o + 2:o + 4] = (dx + THROW_FAR[sp.key]).to_bytes(2, 'big', signed=True)
                if st == 0:                            # grabbed at MK's arm's length, not Blade's blade's:
                    dx = int.from_bytes(co[o + 2:o + 4], 'big', signed=True)
                    cut = max(0, dx - THROW_GRAB_DX)   # (steps move her relative to the last: the cut
                    if cut:                            #  goes onto step 1, so the rest of the path is kept)
                        co[o + 2:o + 4] = (dx - cut).to_bytes(2, 'big', signed=True)
                        dx1 = int.from_bytes(co[o + 12:o + 14], 'big', signed=True)
                        co[o + 12:o + 14] = (dx1 + cut).to_bytes(2, 'big', signed=True)
        # the thrower list (mkinputs.THROW_LIST): each frame loaded at one moment
        lst = mkinputs.THROW_LIST_AT
        for i, f in enumerate(mkinputs.THROW_LIST):
            o = lst + 4 * i
            assert 0x40 <= co[o] - (sp.sheet_base - 0x40) <= 0x43, (name, hex(o))
            co[o:o + 2] = bytes([(f >> 8) + sp.sheet_base - 0x40, f & 0xFF])
        ec.patch_file(name, 0, bytes(co))


PIT_STAGE = 'BST'                 # Blast's stage (his slot is Scorpion's): Scorpion's home stage
PIT_OFFSET = (-32, 0)             # art shift (MK's plane starts 32 px left of the bridge's end)
PIT_FLOOR = 0xCE                  # fighters' floor line (EC's $D8 put them 10 px into the bridge)
PIT_XMAX = 500                    # camera's right limit: where MK's stops (its right statue at screen x ~230)
# The back layer's scroll bands (Blast's stage: plane B band objects by their
# y) re-laid as MK's Pit (measured: tools/vdp.py hscroll over 4 s, camera
# still): lines 0-31 and 128+ still, the clouds in three bands drifting
# 0.69, 0.51 and 0.43 px a frame. MK's plane B is scrolled 16 down (VSRAM
# $10): the bands are its plane rows 48-87, 88-127, 128-143, which the art
# (MK's plane B) shares. (Screen line + 8 cut the clouds' bottoms off into
# slivers drifting at the next band's speed.) y -> (new y, height - 1, x mode, speed):
# x mode $14 drifts by speed/1024 px a frame, 0 is locked to the camera.
PIT_BANDS = {0x00: (0x00, 0x2F, 0x00, 0x0000), 0x20: (0x30, 0x27, 0x14, 0xFD40),
             0x38: (0x58, 0x27, 0x14, 0xFDF6), 0x70: (0x80, 0x0F, 0x14, 0xFE48),
             0x80: (0x90, 0x1F, 0x00, 0x0000), 0xB0: (0xB0, 0x07, 0x00, 0x0000),
             0xB8: (0xB8, 0x07, 0x00, 0x0000), 0xC0: (0xC0, 0x07, 0x00, 0x0000)}


def pit_layers():
    """MK's Pit (tools/mkstage.py) as EC's two layers, laid out as MK's planes
    (measured: tools/vdp.py on states/mk_pit_raw.state):
      front (plane A): the night sky and the moon in the top PIT_MAP_Y rows
          (low priority), then the bridge, statues and pillars;
      back (plane B): the clouds. Its top PIT_MAP_Y rows (MK's plane B rows
          0-10) are high priority (build layer_prio, patches.pit_stage): the
          clouds drift in front of the moon, as in MK. EC's fighters' sprites
          are high priority too, so they stay in front of the clouds."""
    import os, numpy as np
    from PIL import Image
    from inputs import ROOT
    d = os.path.join(ROOT, 'extracted', 'mk_stages', 'pit')
    a = np.array(Image.open(os.path.join(d, 'plane_a.png')))
    b = np.array(Image.open(os.path.join(d, 'plane_b.png'))).copy()
    b[:32, :, 3] = 0                          # MK's HUD lives in plane B's top rows
    T = PIT_MAP_Y
    m = b[:, :, 3] > 0
    back = np.zeros_like(a)
    back[m] = b[m]                            # the clouds (above T: only them, the rest clear)
    sky_a = a[20, 600, :3]
    moon = (a[:T, :, 3] > 0) & np.any(a[:T, :, :3] != sky_a, axis=2)
    moon[:, 400:] = False                     # (the right pillar's top reaches these rows)
    # MK's backdrop colour (the night blue) shows wherever both its planes
    # are empty - below the bridge; EC's is black: the back layer is filled there
    sky = b[100, 8, :3] if b[100, 8, 3] else np.array([0, 0, 108], np.uint8)
    low = back[T:]
    empty = low[:, :, 3] == 0
    low[empty, :3] = sky
    low[empty, 3] = 255
    # the front's sky band: the night blue (opaque, as MK's plane A), the
    # pillars' tops, and the moon. MK scrolls the moon's lines apart from the
    # bridge (it stays put on screen); EC's front layer scrolls as one: the
    # moon is placed where MK shows it when a fight starts (screen x ~85:
    # pit_mk_vs_ours), for this stage's start camera (PIT_XMAX // 2, art
    # shifted by PIT_OFFSET)
    front = a.copy()
    top = front[:T]
    top[moon, :3] = sky_a
    clear = top[:, :, 3] == 0
    top[clear, :3] = sky_a
    top[:, :, 3] = 255
    ys, xs = np.nonzero(moon)
    dx = 85 + PIT_XMAX // 2 - PIT_OFFSET[0] - xs.min()
    front[ys, xs + dx] = a[ys, xs]
    # MK's sky repeats every 512 px: one period is the whole back layer, so
    # it fits the 64-cell plane and its bands can drift without streaming
    back = back[:, :512]
    # build() shifts both layers by PIT_OFFSET (cropping): give it one period
    # more of the repeating sky, so 512 full pixels remain
    back = np.concatenate([back, back], axis=1)[:, :512 - PIT_OFFSET[0]]
    return front, back


# The Pit's fall (MK's Pit fatality, shots/mk_pit_fatality.mp4): the loser
# falls past the bridge, the stage cuts to the pit (layer 2: the whole of
# MK's pit, tools/mkpitbottom.py) and the camera scrolls down to its floor
# (ecstage.pit_cut). World y = MK's plane y = map y + 88; world x = map x - 32.
# The camera keeps x PIT_CUT_CAM[0] (MK's last screen: map x 280-599), so the
# layer only holds that strip (and the bridge, whose tiles layer 1 has); the
# rest is black. Layer x = world x (the streamer doesn't wrap layer columns).
PIT_CUT_CAM = (248, 544)          # camera x, and y at the pit's floor (map y 456)
PIT_CUT_FLOOR = 734               # world y the loser lands on: the spikes (map y 646)
PIT_CUT_LOSER = (448, 150)        # world x he drifts to (screen x 200); (screen y: unused)
PIT_MAP_Y = 88                    # world y of MK's map row 0
PIT_FULL_TO = 480                 # map rows the tall layer has at full width (the camera drifts over them; 779 tiles, Raven's stage has 775)


def pit_tall_layer():
    import os, numpy as np
    from PIL import Image
    from inputs import ROOT
    f = os.path.join(ROOT, 'extracted', 'mk_stages', 'pit_bottom', 'pit_full.png')
    if not os.path.exists(f):
        raise SystemExit('missing the pit: run  .venv/bin/python tools/mkpitbottom.py')
    pit = np.array(Image.open(f).convert('RGBA'))
    sky = pit[2, 400, :3].copy()                      # the file palette's navy (MK fades it to black)
    pit[np.all(pit[:, :, :3] == sky, axis=2) | (pit[:, :, 3] == 0)] = (0, 0, 0, 255)
    h = (PIT_MAP_Y + pit.shape[0] + 31) // 32 * 32
    dx = -PIT_OFFSET[0]
    x0, x1 = PIT_CUT_CAM[0], PIT_CUT_CAM[0] + 320       # the strip the camera ends on
    w = pit.shape[1] - dx
    out = np.zeros((h, (w + 31) // 32 * 32, 4), np.uint8)
    out[:, :, 3] = 255
    # full width down to PIT_FULL_TO (the camera drifts to the strip while
    # the bridge and the pillars' tops are on screen), the strip below
    out[PIT_MAP_Y:PIT_MAP_Y + PIT_FULL_TO, :w] = pit[:PIT_FULL_TO, dx:]
    out[PIT_MAP_Y + PIT_FULL_TO:PIT_MAP_Y + pit.shape[0], x0:x1] = pit[PIT_FULL_TO:, x0 + dx:x1 + dx]
    return out


@patch('pit-stage', "MK's Pit (bridge, statues, moon and clouds) as an EC stage: Scorpion's home stage")
def pit_stage(ec, sources):
    """tools/ecstage.py builds the stage's .BG/.BGI from MK's layers in place
    of PIT_STAGE's (Blast's). Its init in SUB.BIN (mode $13) gets:
     - the camera: the Pit is 848 px wide; right limit as MK's (PIT_XMAX),
       start centred;
     - the front layer down to the plane's bottom (y $D7 -> $FF); Blast's
       floor strip object (a narrower parallax layer) never on screen (y
       $4000): its layer holds the pit, scrolled to in the cut (pit_tall_layer);
     - the back layer's bottom band (plane B from y $C8) without its per-line
       scroll routine ($E332) and x mode 8: it slid apart from the rest.
    The layers are then cut to that init."""
    import os, json
    from inputs import ROOT, require
    from disc import Disc
    import ecstage
    d = os.path.join(ROOT, 'extracted', 'mk_stages', 'pit')
    if not os.path.exists(os.path.join(d, 'plane_a.png')):
        raise SystemExit('missing the Pit: run  .venv/bin/python tools/mkstage.py')
    sub = ec.read_file('SUB.BIN')
    inits = ecstage.stage_inits(sub)
    a = inits[0x13] - ecstage.SUB_BASE
    end = min(x for x in inits.values() if x > inits[0x13]) - ecstage.SUB_BASE
    for off, new, old in ecstage.camera_patch(sub, PIT_STAGE, xmax=PIT_XMAX, start_x=PIT_XMAX // 2):
        ec.patch_file('SUB.BIN', off, new, expect=old)
    n = m = 0
    bands = 0
    for k in range(a, end, 2):
        if sub[k:k + 6] != bytes.fromhex('4eb90000e062'):
            continue
        args = sub[k + 6:k + 16]
        y = int.from_bytes(args[4:6], 'big')
        if args[:2] == b'\x00\x02' and y in PIT_BANDS and args[8:10] != b'\x7f\xff':   # (not the layer itself)
            ny, nh, mode, speed = PIT_BANDS[y]
            ec.patch_file('SUB.BIN', k + 10, ny.to_bytes(2, 'big'), expect=args[4:6])
            ec.patch_file('SUB.BIN', k + 14, nh.to_bytes(2, 'big'), expect=args[8:10])
            nk = sub.find(bytes.fromhex('4eb9'), k + 16)
            for j in range(k + 16, nk, 2):
                if sub[j:j + 2] == b'\x11\x7c' and sub[j + 4:j + 6] == b'\x00\x36':
                    ec.patch_file('SUB.BIN', j + 2, mode.to_bytes(2, 'big'), expect=sub[j + 2:j + 4])
                if sub[j:j + 2] == b'\x31\x7c' and sub[j + 4:j + 6] == b'\x00\x38':
                    ec.patch_file('SUB.BIN', j + 2, speed.to_bytes(2, 'big'), expect=sub[j + 2:j + 4])
            bands += 1
            continue
        if args == bytes.fromhex('0000 0000 0000 7fff 00d7'.replace(' ', '')):
            ec.patch_file('SUB.BIN', k + 14, b'\x00\xff', expect=b'\x00\xd7')
            n += 1
        elif args == bytes.fromhex('0000 0000 00d8 7fff 7f27'.replace(' ', '')):
            # Blast's floor strip: its object never on screen (y $4000); its
            # layer (2) holds the pit, which the front object streams in the cut
            ec.patch_file('SUB.BIN', k + 10, bytes.fromhex('40007fff7f0f'), expect=bytes.fromhex('00d87fff7f27'))
            n += 1
        elif args[:2] == b'\x00\x02' and args[4:6] == b'\x00\xc8':
            for j in range(k + 16, k + 70, 2):
                if sub[j:j + 6] == bytes.fromhex('117c00080036'):
                    ec.patch_file('SUB.BIN', j + 2, b'\x00\x00', expect=b'\x00\x08')
                if sub[j:j + 8] == bytes.fromhex('217c0000e3320064'):
                    ec.patch_file('SUB.BIN', j + 2, bytes(4), expect=bytes.fromhex('0000e332'))
                    m += 1
    assert n >= 2 and m and bands == len(PIT_BANDS), ('Blast stage init not as expected', n, m, bands)
    # the floor line: MK's fighters stand up on the walkway, 10 px higher
    k = sub.find(bytes.fromhex('3d7c00d81496'), a, end)
    assert k > 0, 'no floor line in the init'
    ec.patch_file('SUB.BIN', k + 2, PIT_FLOOR.to_bytes(2, 'big'), expect=b'\x00\xd8')
    front, back = pit_layers()
    cram = json.load(open(os.path.join(d, 'cram.json')))
    stock = Disc(require('ec_us').cue)
    tmpl = dict(sub=ec.read_file('SUB.BIN'), bg=stock.read_file(PIT_STAGE + '.BG'),
                bgi=stock.read_file(PIT_STAGE + '.BGI'))
    cut = ecstage.pit_cut(1, 2, *PIT_CUT_CAM, PIT_CUT_FLOOR, *PIT_CUT_LOSER, back=3)
    bg, bgi, rep = ecstage.build(front, back, cram, stage=PIT_STAGE, template=tmpl, offset=PIT_OFFSET,
                                 pit_fall=cut, layer_images={2: pit_tall_layer()},
                                 fixed_extra=ecstage.PIT_BLOOD,
                                 fade={'layers': [3], 'rows': {1: PIT_MAP_Y}},
                                 blank_tile_slots=(0, 1, 2, 3),      # Blast's stage sprites
                                 layer_prio={3: (0, 0, 4096, PIT_MAP_Y - 1)})   # clouds over the moon
    ec.replace_file(PIT_STAGE + '.BG', bg)
    ec.replace_file(PIT_STAGE + '.BGI', bgi)
    print(f'        Pit: {rep.get("tiles")} tiles, BG {len(bg)} bytes, BGI {len(bgi)} bytes')


@patch('no-cinekill-mk', "No EC Cinekill (finisher video) on an MK fighter: its video has none of them in it")
def no_cinekill_mk(ec, sources):
    """PLYR.CO $14AA2 (a5 = the victim): `cmpi.w #$18,$76(a5); bgt.s no` is
    the Cinekill's first check (victim at most 24 health), then DECKL.VC plays
    the video. The compare becomes a jsr to a routine appended to SUB.BIN that
    returns 'greater' for an MK victim (mkinputs.MK_IDS)."""
    import mkinputs
    sub = ec.read_file('SUB.BIN')
    at = (len(sub) + 1) & ~1
    ids = mkinputs.MK_IDS
    code = b''
    for k, f in enumerate(ids):                     # cmpi.w #id,$4C(a5) ; beq.s mk
        code += bytes.fromhex('0c6d') + f.to_bytes(2, 'big') + bytes.fromhex('004c')
        code += bytes([0x67, 8 * (len(ids) - k)])
    code += bytes.fromhex('0c6d00180076' '4e75')    # the displaced compare ; rts
    code += bytes.fromhex('44fc0000' '4e75')        # mk: move #0,ccr ('greater': no Cinekill) ; rts
    assert 0x6000 + at + len(code) <= 0x14000, 'SUB.BIN reaches PLYR.CO'
    put_sub(ec, sub + bytes(at - len(sub)) + code)
    ec.patch_file('PLYR.CO', mkinputs.CINEKILL_SITE - 0x14000,
                  bytes.fromhex('4eb9') + (0x6000 + at).to_bytes(4, 'big'), expect=bytes.fromhex('0c6d00180076'))


@patch('pit-no-shadows', "No fighter shadows on the Pit (MK draws none on the bridge)")
def pit_no_shadows(ec, sources):
    """SUB.BIN spawns each fighter's shadow (object $1D) at $B44A / $B4E2,
    except on stage mode $18: `cmpi.w #$18,$AB2(a6); beq.s skip` just before
    ($B442 / $B4DA). The compare becomes a jsr (same 6 bytes) to a routine
    appended to SUB.BIN that sets Z for the Pit's mode ($13) too."""
    sub = ec.read_file('SUB.BIN')
    at = (len(sub) + 1) & ~1
    code = bytes.fromhex('0c6e00180ab2'      # cmpi.w #$18,$AB2(a6)
                         '6706'              # beq.s done
                         '0c6e00130ab2'      # cmpi.w #$13,$AB2(a6)  the Pit
                         '4e75')             # done: rts (Z = no shadow)
    assert 0x6000 + at + len(code) <= 0x14000, 'SUB.BIN reaches PLYR.CO'
    put_sub(ec, sub + bytes(at - len(sub)) + code)
    for site in (0xB442, 0xB4DA):
        ec.patch_file('SUB.BIN', site - 0x6000, bytes.fromhex('4eb9') + (0x6000 + at).to_bytes(4, 'big'),
                      expect=bytes.fromhex('0c6e00180ab2'))


@patch('fatality-music', "MK's CD cues: FINISH HIM's track 9; at the fatality track 13 then 10 with MK's flame and scream (disc times)")
def fatality_music(ec, sources):
    """build.add_mk_jingle appended MK's fatality music and two mixes (flame +
    a man's / a woman's scream) to the end of the last track. Their absolute
    times (LBA + 150 frames of lead-in, BCD MMSSFF00 as MSCPLAYT takes it) go
    after the 'EKMU' tag in BLA.CO's extension block. Must be the last
    patch: it needs the data track's final size."""
    import os, build, mkinputs
    from disc import RAW
    if 'mk_us' not in sources:
        return
    parts = build.mk_jingle(sources['mk_us'].cue)
    appended = sum(build.JINGLE_GAP + len(p) // RAW for p in parts)
    lba, seen = 0, set()
    for t in ec.tracks:
        if t.file in seen:
            continue
        seen.add(t.file)
        size = ec.data.index01 + ec.data.length if t.file == ec.data.file else os.path.getsize(t.file) // RAW
        if t.number == build.JINGLE_TRACK:
            lba += size - appended
            break
        lba += size
    bcd = lambda v: (v // 10) << 4 | v % 10
    times = b''
    for p in parts:
        lba += build.JINGLE_GAP
        a = lba + 150
        times += (bcd(a // 4500) << 24 | bcd(a // 75 % 60) << 16 | bcd(a % 75) << 8).to_bytes(4, 'big')
        lba += len(p) // RAW
    for sp in (SCORPION, RAIDEN, JOHNNY, SUBZERO):     # every MK fighter's block plays it
        co = ec.read_file(sp.host + '.CO')
        i = co.index(mkinputs.MUSIC_TAG.to_bytes(4, 'big'))
        ec.patch_file(sp.host + '.CO', i + 4, times[:12], expect=bytes(12))
    # the Pit's fall (a man's, a woman's): in its stage code, after its tag
    import ecstage
    bgi = ec.read_file(PIT_STAGE + '.BGI')
    j = bgi.find(ecstage.PIT_SOUND_TAG.to_bytes(4, 'big'))
    if j >= 0:
        ec.patch_file(PIT_STAGE + '.BGI', j + 4, times[12:], expect=bytes(len(times) - 12))
