# SPDX-License-Identifier: MIT
"""Patches applied to the Eternal Champions disc, in order.

Each patch is a function taking (ec, sources) -> None:
    ec       Disc: the output disc being built (a copy; safe to modify)
    sources  {id: Disc}: every recognised input disc, read-only
Register it with @patch('name', 'what it does'). build.py --skip name disables one.
"""
PATCHES = []

# Scorpion is built from a copy of Blade's files (art, code, sounds) written
# into HOST's files; Blade's own stay stock once HOST is a slot of its own.
HOST = 'SEN'                      # the Senator: a hidden EC fighter (his special-casing: patches.senator_slot)
HOST_ID = 22
HOST_IDX = HOST_ID - 2
# versus portraits in GAME.DAT ($EA0 bytes): ids 2-18 from $23D30, 19+ from $33604
PORTRAIT = {i: (0x23D30 + i * 0xEA0 if i < 17 else 0x33604 + (i - 17) * 0xEA0) for i in range(25)}


def host(ext):
    return getattr(SPEC, 'files', {}).get(ext, f'{HOST}.{ext}')   # (Shang's slot: CHA.CO, but ECH.PL)


class Spec:
    """An MK fighter built from a copy of Blade's files in an EC host slot."""
    def __init__(self, **kw):
        self.__dict__.update(kw)


SCORPION = Spec(key='scorpion', name='SCORPION', host='SEN', host_id=22, mk_dir='mk_moves', ai='SEN.AI',
                win=(0xCB84, b'   SENATOR\0', b'  SCORPION\0'), sheet_base=0x85,
                aliases={}, exact=True, strip=True, blood=True, alt='p2')
# Raiden: Chin Wo's slot (CHW, id 19, sheets from $72). First version: Blade's
# moves and code with Raiden's MK poses - Blade's projectile is his lightning,
# Blade's dash his torpedo. Actions not captured for him borrow these:
RAIDEN = Spec(key='raiden', name='RAIDEN', host='CHW', host_id=19, mk_dir='mk_moves_raiden', ai='CHW.AI',
              win=(0xCB64, b'   CHIN WO\0', b'    RAIDEN\0'), sheet_base=0x72,
              aliases={'spear': 'lightning', 'teleport_mk': 'torpedo', 'lying': 'knockdown',
                       'jumpup_c': 'jump_c', 'jumpup_a': 'jump_a', 'fatality': 'torpedo',
                       'fatality_fire': 'lightning', 'fatality_skeleton': 'teleport', 'teleport': 'teleport'},
              # his torpedo is Blade's dash (frames 41:16, 41:17, 41:61, 41:62 with the hit,
              # 41:61, 41:16): MK's crouch, spring, dive and the head-first flight
              extra=[('torpedo', ['41:16=7', '41:17=8', '41:61=9', '41:62=10']),
                     ('teleport', __import__('mkinputs').rtele_plan('mk_moves_raiden')[1])]   # his MK teleport (move $31)
                    + __import__('mkinputs').cap_pins('raiden'),     # his electrocution (mkinputs.emit_gfatal)
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
# shadow kick / Sub-Zero's slide.
JOHNNY = Spec(key='johnny', name='JOHNNY CAGE', host='MON', host_id=18, mk_dir='mk_moves_johnny', ai='MONK.AI',
              win=(0xCB5A, b'    ZUNI\0', b' J. CAGE\0'), sheet_base=0xD9, src_ids=list(range(0x236, 0x242, 2)),
              aliases={'spear': 'greenbolt', 'teleport_mk': 'shadowkick', 'teleport': 'shadowkick',
                       'fatality': 'shadowkick',
                       'fatality_fire': 'greenbolt', 'fatality_skeleton': 'uppercut'},
              exact=False, strip=False, blood=True, alt='dim',
              # down + Z: MK1's split punch (tools/lib/mkmoves.py crouch_z 5 split, 7 punch, 8 back up)
              extra=[('crouch_z', ['42:05=5', '42:06=7', '42:07=8']),
                     ('shadowkick', ['41:16=1', '41:17=8', '41:30=8', '41:31=15',
                                     '41:32=22', '41:62=29', '41:34=34', '41:35=36', '41:61=36'])]
                    + __import__('mkinputs').jcf_pins(),     # his decapitation (mkinputs.emit_gfatal)
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
                        'lying': 'knockdown', 'fatality': 'iceblast',
                        'fatality_fire': 'iceblast', 'fatality_skeleton': 'uppercut'},
              exact=False, strip=False, blood=True, alt='p2',      # MK's Scorpion: the same sprites
              # blood as Raiden's: navy-black 6 joins black 12, cream 1 joins white 15
              # his slide on Blade's dash (41:17, 41:16, 41:61, 41:62 with the hit, 41:61, 41:16):
              # MK's drop / getting up (8) and the slide (9)
              extra=[('slide', ['41:16=8', '41:17=8', '41:61=8', '41:62=9'])]
                    + __import__('mkinputs').szf_pins(),     # his spine rip (mkinputs.emit_gfatal)
              colour_map={6: 12, 1: 15}, blood_moves={12: 6, 13: 1})
# Liu Kang, Kano, Sonya: the chicken's (CHI, id 12), the snake's (SNA, 13) and the
# owl's (OWL, 17) slots - EC's last gag animals. Sheets $E1-$EC and their own effect
# sheets (mkinputs.FX_SHEET), tile sources from the free even ids. Blood: EC's
# hit-spark colours 12 and 13 freed by merging near-identical colours of theirs.
LIUKANG = Spec(key='liukang', name='LIU KANG', host='CHI', host_id=12, mk_dir='mk_moves_liukang', ai='CHI.AI',
               win=(0xCB16, b'   CRISPY\0', b' LIU KANG\0'), sheet_base=0xE1, src_ids=[0x1C, 0x1E, 0x20, 0x22, 0x24, 0x26],
               aliases={'spear': 'fireball', 'teleport_mk': 'flyingkick', 'teleport': 'flyingkick',
                        'lying': 'knockdown', 'fatality': 'flyingkick',
                        'fatality_fire': 'fireball', 'fatality_skeleton': 'uppercut'},
               exact=False, strip=False, blood=True, alt='dim',
               extra=__import__('mkinputs').cap_pins('liukang')      # his uppercut fatality (mkinputs.emit_gfatal)
                     + [('flyingkick', __import__('mkinputs').flykick_plan('mk_moves_liukang')[1])],   # his flying kick
               # his black is there twice (6, 12): 6 joins 12; his grey 13 joins the dark grey 9
               colour_map={6: 12, 13: 9}, blood_moves={12: 6})
KANO = Spec(key='kano', name='KANO', host='SNA', host_id=13, mk_dir='mk_moves_kano', ai='SNA.AI',
            win=(0xCB20, b'   SLITHER\0', b'      KANO\0'), sheet_base=0xE5, src_ids=[0xE0, 0xE2, 0xFA, 0xFC, 0xFE, 0x100],
            aliases={'spear': 'knife', 'teleport_mk': 'cannonball', 'teleport': 'cannonball',
                     'fatality': 'cannonball',
                     'fatality_fire': 'knife', 'fatality_skeleton': 'uppercut'},
            exact=False, strip=False, blood=True, alt='dim',
            # his knife throw on Blade's cast ($34: these 20 frames in this order, 2 game frames
            # each; the knife object flies from 42:2E). Spread evenly they began on MK's block
            # poses (MK: Block held through the input) and skipped the throw; pinned: MK's crouch
            # (10), reach back (11, 12), overhead (13), slash (14, 15), release (17), follow-through
            extra=[('knife', ['40:60=9', '40:61=10', '40:62=10', '40:63=11', '42:28=12', '42:29=12',
                              '42:2a=13', '42:2b=14', '42:2c=14', '42:2d=15', '42:2e=17', '42:2f=18',
                              '42:30=20', '42:31=22', '40:5e=24', '40:5f=25', '42:32=26', '42:33=28',
                              '42:34=30', '42:35=32'])] +
                  __import__('mkinputs').cap_pins('kano'),     # his heart rip (mkinputs.emit_gfatal)
            # the paler of his two yellows (10) joins 9, the paler blue (2) joins 1
            colour_map={10: 9, 2: 1}, blood_moves={12: 10, 13: 2})
SONYA = Spec(key='sonya', name='SONYA', host='OWL', host_id=17, mk_dir='mk_moves_sonya', ai='OWL.AI',
             win=(0xCB50, b'   HOOTER\0', b'    SONYA\0'), sheet_base=0xE9, src_ids=[0x102, 0x104, 0x12C, 0x12E, 0x130, 0x16C],
             aliases={'spear': 'rings', 'teleport_mk': 'squarewave', 'teleport': 'squarewave',
                      'lying': 'knockdown', 'fatality': 'squarewave',
                      'fatality_fire': 'btn_x', 'fatality_skeleton': 'uppercut'},
             exact=False, strip=False, blood=True, alt='dim',   # (her rings: Blade's effect sheet, renumbered)
             # Blade's dash holds 41:61/62 while moving and hitting. Use MK's
             # airborne approach and outstretched punch, not the landing pose.
             # The dash's other steps rise and drop as MK's (SQUARE_STEPS): launch, tuck,
             # then after the flight her drop and landing crouch.
             extra=[('squarewave', ['41:61=12', '41:62=13', '41:30=10', '41:31=11', '41:32=17', '41:34=18']),
                    ('leggrab', __import__('mkinputs').leg_plan('mk_moves_sonya')[1])] +   # her leg grab (EC's throw)
                   __import__('mkinputs').cap_pins('sonya') + __import__('mkinputs').burn_pins(),   # her kiss of death
             # two of her greens are near alike twice (2 / 1, 6 / 5)
             colour_map={2: 1, 6: 5}, blood_moves={12: 2, 13: 6})
# Shang Tsung: the Contest's first boss, in the Eternal Champion's slot (CHA, id 11:
# GAME.CO's boss match; an ordinary fighter there hands straight on to the Dark
# Champion, docs/notes/2026-11.md). Built as the others (Blade's code, his MK moves from
# EMP.OBJ: tools/lib/mkshangmoves.py), but a boss: not on the select screen, no ending,
# no fatality. MK gave him no punches, kicks or jumps: those are his stance.
SHANG = Spec(key='shang', name='SHANG TSUNG', host='CHA', host_id=11, mk_dir='mk_moves_shang', ai='CHP.AI',
             portrait='mk_shang',              # (select and versus: mkportraits_disc.shang, his fighter art)
             win=(0xCB0A, b'   ETERNAL\0', b'     SHANG\0'), sheet_base=0xED, boss=True, files={'PL': 'ECH.PL'},
             aliases={'spear': 'skull', 'teleport_mk': 'idle', 'teleport': 'idle', 'fatality': 'idle',
                      'fatality_fire': 'idle', 'fatality_skeleton': 'idle',
                      'speared': 'hit_high'},      # (MK CD has no Scorpion vs Shang: his first hit pose)
             # his cast (move $34) is his own script (mkinputs.skull_plan): its poses pinned
             extra=[('skull', __import__('mkinputs').skull_plan('mk_moves_shang')[1]),
                    # his morph's blends (EMP 22-42: 3 per MK fighter) on frames no script or table uses
                    ('morph', [f'40:{0x38 + i:02x}={i}' for i in range(21)])],
             exact=False, strip=False, blood=True, alt='dim',
             # blood (EC's hit spark: colours 12/13 red): his darker grey 13 joins the olive 7,
             # the pale grey 1 joins white 15; his black (12) moves to 1
             colour_map={13: 7, 1: 15}, blood_moves={12: 1})
# Reptile: MK's secret fighter, fought on the Pit's bottom (MK CD: player 2 as Scorpion's
# sprites in his green, PAC.PRG $1BF10; tools/capture/mkreptileref.py). Never on the select screen.
# In the Eternal Champion's second form's slot (ECX, id 26: never loaded in the Contest).
# Built as Sub-Zero (MK's ninjas are one set of sprites): his freeze and slide; and, as MK's
# Reptile, Scorpion's spear (below).
REPTILE = Spec(key='reptile', name='REPTILE', host='ECX', host_id=26, mk_dir='mk_moves_subzero', ai='CHX.AI',
               portrait='mk_reptile',          # (his select and versus portrait: mkportraits_disc.reptile)
               win=(0xCBB0, b'   ETERNAL\0', b'   REPTILE\0'), sheet_base=0xF1, boss=True,
               palette_src='mk_reptile_1p:1', files={'SND': 'CHA.SND'},   # (the second form shares the first's bank)
               # his spear is Scorpion's (MK CD draws Reptile with Scorpion's sprites), on Blade's
               # $34 as Scorpion's; Sub-Zero's ice blast moves to $31 (mkinputs.ice_plan)
               aliases={k: v for k, v in SUBZERO.aliases.items() if k != 'spear'}, captures={'spear': 'mk_moves'},
               exact=False, strip=False, blood=True, alt='dim',
               extra=[('slide', ['41:16=8', '41:17=8', '41:61=8', '41:62=9']),
                      ('iceblast', __import__('mkinputs').ice_plan('mk_moves_subzero')[1])],
               colour_map={6: 12, 1: 15}, blood_moves={12: 6, 13: 1})
MK_SPECS = (SCORPION, RAIDEN, JOHNNY, SUBZERO, LIUKANG, KANO, SONYA, SHANG, REPTILE)
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
    specs = MK_SPECS
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
        co = open(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                               'extracted', 'ec_us', 'BLA.CO'), 'rb').read()
        import mkinputs
        spec.extra = list(getattr(spec, 'extra', [])) + mkscripts.build(co, spec.mk_dir)[1] \
            + [('throw_seq', mkinputs.throw_plan(spec.mk_dir)[1])] \
            + [('hit_seq', mkinputs.hit_plan(spec.mk_dir)[1])]   # MK's whole throw and hit reaction (mkinputs drives them)
        if spec is not SCORPION:                 # MK's walk loop (mkinputs drives it)
            import mkinputs
            spec.extra.append(('walk_fwd', mkinputs.walk_plan(spec.mk_dir)[2]))
        import mkinputs
        if spec.host_id in mkinputs.JUMP_FIGHTERS:        # MK's roll on forward / back jumps
            spec.extra.append(('jump_fwd', mkinputs.jump_plan(spec.mk_dir)[2]))
        if spec.host_id in mkinputs.KD_FIGHTERS:          # MK's knockdown (fall, bounce, getting up)
            spec.extra.append(('knockdown', mkinputs.kd_plan(spec.mk_dir)[2]))
        spec.extra.append(('kick_seq', mkinputs.kick_plan(spec.mk_dir)[1]))   # MK's reaction to a kick
        if spec is SCORPION:                     # MK's bare throw: the spear missed / blocked (emit_spear_miss)
            b = mkinputs.spear_bare_slot(spec.mk_dir)
            spec.extra.append(('spear_bare', [f'{b >> 8:02x}:{b & 0xFF:02x}={mkinputs.SPEAR_BARE_POSE}']))
        elif 'spear' in getattr(spec, 'captures', {}):   # Reptile: Scorpion's spear, so his bare throw too -
            used = {int(e.split('=')[0].replace(':', ''), 16) for _, es in spec.extra for e in es}   # on the
            spec.spear_bare = [f for f in mkinputs._free_slots(spec.mk_dir) if f not in used][-1]   # last free slot
            spec.captures = dict(spec.captures, spear_bare=spec.captures['spear'])
            b = spec.spear_bare
            spec.extra.append(('spear_bare', [f'{b >> 8:02x}:{b & 0xFF:02x}={mkinputs.SPEAR_BARE_POSE}']))
        if spec.host_id in mkinputs.KD_FIGHTERS and spec.mk_dir in mkinputs.SWEPT_DIRS:   # MK's fall when swept
            spec.extra.append(('swept', mkinputs.kd_plan(spec.mk_dir, 'swept')[2]))
        spec.scripts_art = True
    import mkinputs
    scorpion_full.CFG.update(extra_frames=len(mkinputs.extra_slots(spec.mk_dir)))   # (sheet $43 grows)
    scorpion_full.CFG.update(mk_dir=spec.mk_dir, aliases=spec.aliases, exact=spec.exact, strip=spec.strip,
                             extra=getattr(spec, 'extra', ()), colour_map=getattr(spec, 'colour_map', {}),
                             captures=getattr(spec, 'captures', {}),
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


SAVE_NAME = b'ETERNAL_CD_', b'ETERNALKOMB'   # (BRAM file names: 11 characters, A-Z 0-9 _)


@patch('save-file', "The game's own save in backup RAM (ETERNALKOMB), not EC's ETERNAL_CD_")
def save_file(ec, sources):
    """EC keeps its save (the select screen's unlock mask $1CC8(a6), $14A4(a6) and the options) in the
    Sega CD's backup RAM as ETERNAL_CD_, written by SUB.BIN $7608 and read back at boot by BACKUP.CO
    ($136: move.l (a1),$1CC8(a6)). On a console that has played EC, its save would load over this
    game's unlock mask: no MK fighters and no Blast on the select screen (seen on real hardware; the
    emulator's backup RAM never held an EC save). Under its own name the game starts from its own
    defaults, and EC's save is left alone. The name is in SUB.BIN ($765E, $766C) and BACKUP.CO
    ($18E, $19C)."""
    old, new = SAVE_NAME
    for name, offs in (('SUB.BIN', (0x765E - 0x6000, 0x766C - 0x6000)), ('BACKUP.CO', (0x18E, 0x19C))):
        for o in offs:
            ec.patch_file(name, o, new, expect=old)


@patch('title-logo', "The title screen's logo says ETERNAL KOMBAT (EC's own letters, rearranged; ectitle.py)")
def title_logo(ec, sources):
    import ectitle
    print(f'        {ectitle.apply(ec)} tiles of the title picture redrawn')


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
            for i in range(na):                      # Blade's ids -> the host's first na (a host with
                j = min(i, nb - 1)                   #  fewer - the chicken, the owl: 3 - shares its last)
                ea = oa + int.from_bytes(blade[oa + 14 + 4 * i:oa + 18 + 4 * i], 'big')
                eb = ob + int.from_bytes(hostsnd[ob + 14 + 4 * j:ob + 18 + 4 * j], 'big')
                ids[int.from_bytes(blade[ea:ea + 2], 'big')] = int.from_bytes(hostsnd[eb:eb + 2], 'big')
                b[ea:ea + 2] = hostsnd[eb:eb + 2]
    return bytes(b), ids


@patch('scorpion-full', "All of Blade's sprite art (sheets $40-$43) rebuilt as Scorpion's MK poses")
def scorpion_full(ec, sources):
    """Every Blade pose is replaced by the matching Scorpion pose (see
    tools/lib/scorpion_map.py), captured from MK by tools/lib/mkmoves.py. Blade's
    code, timing and hit boxes are unchanged. Same file size: fits both
    player slots."""
    import os
    from inputs import ROOT
    import scorpion_full
    if not os.path.isdir(os.path.join(ROOT, 'extracted', SPEC.mk_dir, 'idle')):
        raise SystemExit('missing MK poses: run  python3 tools/prepare.py')
    new, rep = scorpion_full.build(ec.read_file(host('PL')), ROOT)
    print(f'        {rep["poses"]} {SPEC.name.title()} poses in {rep["banks"]} banks, '
          f'{rep["bytes"]} of {rep["room"]} bytes; {len(set(rep["tight"]))} frame records repacked bigger')
    if rep.get('grow'):
        print(f'        BLA.PL grows by {rep["grow"]} bytes to {len(new)}')
    # always replace: the file may shrink (Blade's effect sheets are dropped)
    # and a patched-in-place file would keep its old tail, loaded for nothing
    ec.replace_file(host('PL'), new)


@patch('scorpion-ghost-art', "Scorpion's teleport leaves MK's frozen double: his stance as effect sheet $7C")
def scorpion_ghost_art(ec, sources):
    """MK leaves a frozen copy of his stance (idle pose 3) where he took off.
    A fighter frame can't be shown by a second object (EC unpacks one frame per
    fighter into his own VRAM area), so the pose goes into an effect sheet:
    Blade's $44 chunks, kept by scorpion_full, renumbered $7C, one frame, whose
    tiles PLYR.CO uploads once at the fight's start (scorpion-no-fx)."""
    import numpy as np
    import scorpion_full as sf, mkprojectile
    from inputs import ROOT
    pl = bytearray(ec.read_file(host('PL')))
    chunks = mkprojectile.chunks(pl)
    sheet, sheet_len = next((o, n) for o, n, t in chunks if t == 4 and int.from_bytes(pl[o+10:o+12], 'big') // 4 == 0x44)
    sid = int.from_bytes(pl[sheet+12:sheet+14], 'big')
    src, src_len = next((o, n) for o, n, t in chunks if t == 0 and int.from_bytes(pl[o+10:o+12], 'big') // 4 == sid)
    poses, anchors, cram = sf.load_action(ROOT, 'idle')
    full, (ax, ay) = sf.scale_pose(poses[3], anchors[3], cram)
    full = sf.remap_colours(full)
    yy, xx = np.nonzero(full)
    y0, y1, x0, x1 = int(yy.min()), int(yy.max())+1, int(xx.min()), int(xx.max())+1
    img = full[y0:y1, x0:x1]
    ox, oy = ax-x0, ay-sf.FOOT_DROP-y0
    tiles, pieces = mkprojectile.tiles_and_pieces(img, ox, oy, 0, skip_empty=True)
    record = mkprojectile.frame_record(img, ox, oy, pieces)
    assert len(tiles) <= (src_len - 20) // 32
    nfr = int.from_bytes(pl[sheet+20:sheet+22], 'big')
    assert 22 + 2*nfr + len(record) <= sheet_len
    pl[src+20:src+src_len] = b''.join(tiles).ljust(src_len-20, b'\0')
    pl[sheet+10:sheet+12] = (4*0x7C).to_bytes(2, 'big')
    pl[sheet+22:sheet+22+2*nfr] = (2*nfr).to_bytes(2, 'big') * nfr
    pl[sheet+22+2*nfr:sheet+sheet_len] = record.ljust(sheet_len-22-2*nfr, b'\0')
    ec.replace_file(host('PL'), bytes(pl))
    print(f'        ghost sheet $7C, {len(tiles)} tiles')


def tint_palette(tint, own, sparks=()):
    """An EC tint palette (32 bytes: Blade's, for his art's slots) for another fighter's palette
    (own: 16 Genesis colour words): each slot gets the tint colour nearest its brightness, his
    darkest to the tint's darkest and his lightest to its lightest, so he turns one even tint
    with his shading kept. Slot 0 (transparent) and the spark slots keep the tint's own; the
    tint's slot 15 (red in some: Blade's) isn't one of the shades."""
    tint = [int.from_bytes(tint[i:i + 2], 'big') for i in range(0, 32, 2)]
    lum = lambda v: 3 * ((v >> 1) & 7) + 6 * ((v >> 5) & 7) + ((v >> 9) & 7)
    special = {0, *sparks}
    shades = sorted({tint[i] for i in range(1, 15) if i not in (12, 13)}, key=lum)
    lo, hi = lum(shades[0]), lum(shades[-1])
    mine = [lum(own[i]) for i in range(16) if i not in special]
    mlo, mhi = min(mine), max(mine)
    out = []
    for i, v in enumerate(own):
        if i in special:
            out.append(tint[i])
            continue
        want = lo + (lum(v) - mlo) * (hi - lo) / max(1, mhi - mlo)
        out.append(min(shades, key=lambda s: (abs(lum(s) - want), lum(s))))
    return b''.join(v.to_bytes(2, 'big') for v in out)


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
    if getattr(SPEC, 'palette_src', None):   # (read from MK CD itself: PAC.PRG)
        import mkpalettes
        cram = moved(mkpalettes.palette(SPEC.palette_src))
    else:
        cram = moved(json.load(open(os.path.join(ROOT, 'extracted', SPEC.mk_dir, 'idle', 'cram.json'))))
    # Blade's palette: BLA.CO, 16 colour words (found by matching his live CRAM)
    co = ec.read_file(host('CO'))
    old = co[0x3DE0:0x3E00]
    words = [ecpl.genesis_colour(c) for c in cram]
    for i, v in BLOOD.items():
        words[i] = v
    new = b''.join(v.to_bytes(2, 'big') for v in words)
    ec.patch_file(host('CO'), 0x3DE0, new, expect=old)
    # Blade's six tint palettes before it ($3D20-$3DDF): EC fades a fighter caught by an effect
    # (Riptide's bubble: +$80) to one, slot by slot - PLYR's tint tasks ($1AC08, started at PLYR
    # $1AC40-$1AD2C) find them through the module header (+$18). Blade's suit his art's slots;
    # on MK art they came out in blotches (Kano red and blue in the bubble). Each is now
    # the fighter's own colours mapped by brightness onto that tint's colours (spark slots kept).
    old = co[0x3D20:0x3DE0]
    tints = b''.join(tint_palette(old[o:o + 32], words, sparks=tuple(BLOOD))
                     for o in range(0, 0xC0, 0x20))
    ec.patch_file(host('CO'), 0x3D20, tints, expect=old)
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
    """Scorpion's slot is HOST_ID's (the Senator's): his entries in each name table
    point at 'SCORPION'. Fixed-width win-message field: SUB.BIN $CB90.
    Pointer tables (by id - 2), each pointing into a NUL-separated list, so
    'SCORPION' is appended to the file and the entry moved to it:
     - HUD (health bar): SUB.BIN $5970 (loads at $6000)
     - versus screen: GAME.CO $DB1C (e.g. '\x04BLAST': first byte = centring; loads at $14000)
     - stats screen: STATS.CO $6B4 (loads at $34000)"""
    at, old, new = SPEC.win
    assert len(old) == len(new)
    # the health bar's and the win message's font has no hyphen (SUB-ZERO showed a stray tile
    # there): a space in both; the versus screen and the stats print it
    ec.patch_file('SUB.BIN', at, new.replace(b'-', b' '), expect=old)
    text = SPEC.name.encode('ascii')

    def repoint(name, base, table, text):
        b = ec.read_file(name)
        o = table + 4 * HOST_IDX
        at = (len(b) + 1) & ~1
        b = b + bytes(at - len(b)) + text
        b = b[:o] + (base + at).to_bytes(4, 'big') + b[o + 4:]
        ec.replace_file(name, b)
    repoint('SUB.BIN', 0x6000, 0x5970, text.replace(b'-', b' ') + b'\0')
    repoint('GAME.CO', 0x14000, 0xDB1C, b'\x01' + text + b'\0')
    repoint('STATS.CO', 0x34000, 0x6B4, text + b'\0')


@patch('scorpion-roster', "Scorpion's slot (the Senator's) is unlocked on the select screen and set up as Blade's")
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
# the fight hung after loading. Scorpion's move to the host's range (the
# Senator's sheets start at $85). The effect sheets $44/$45 (rope, sparks) keep their
# numbers: both files hold the same art there.
SHEET_SHIFT = 0x85 - 0x40
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
    ids = [sp.host_id for sp in MK_SPECS]   # any MK winner
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


PORTRAIT_W, PORTRAIT_H, PORTRAIT_FRAME = 72, 104, 2     # a versus portrait: 9x13 tiles, a 2-pixel frame


def portrait_indexed(dat, at):
    """A versus portrait's pixels (palette indices) from its tiles in GAME.DAT."""
    import numpy as np
    out = np.zeros((PORTRAIT_H, PORTRAIT_W), np.uint8)
    for t in range(PORTRAIT_W // 8 * PORTRAIT_H // 8):
        ty, tx = divmod(t, PORTRAIT_W // 8)
        raw = np.frombuffer(dat[at + 32 * t:at + 32 * t + 32], np.uint8).reshape(8, 4)
        out[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8:2] = raw >> 4
        out[ty * 8:ty * 8 + 8, tx * 8 + 1:tx * 8 + 8:2] = raw & 15
    return out


def portrait_frame_colours(dat, at):
    """The palette indices of a versus portrait's frame (and 0, transparent): kept as EC's."""
    import numpy as np
    old, F = portrait_indexed(dat, at), PORTRAIT_FRAME
    ring = np.ones(old.shape, bool)
    ring[F:-F, F:-F] = False
    return sorted(set(old[ring].tolist()) | {0})


@patch('scorpion-portrait', "Versus screen shows Scorpion's MK portrait instead of Blade's")
def scorpion_portrait(ec, sources):
    """EC's versus portrait: 9x13 tiles (72x104) stored row by row in
    BIODAT.BIN at $D4B8 (Blade) and again in GAME.DAT at $2A390 (the copy the
    versus screen loads), drawn with palette line 2 = the 16 colours at
    GAME.CO $E188 (also at $55E2). The gold frame is part of the portrait:
    the outer FRAME pixels and the palette entries they use are kept.
    Scorpion's portrait comes from MK's select screen (tools/lib/mkportrait.py ->
    extracted/mk_moves/portrait.png, 42x50), scaled to the inside of the
    frame and reduced to the remaining palette entries."""
    import os
    import numpy as np
    from PIL import Image
    from inputs import ROOT
    import ecpl
    src = os.path.join(ROOT, 'extracted', getattr(SPEC, 'portrait', SPEC.mk_dir), 'portrait.png')
    if not os.path.exists(src):
        raise SystemExit('missing MK portrait: run  python3 tools/prepare.py')
    # EC's versus portraits and their palettes are for ids 2-25 only: the palette pointers at GAME.CO $E048 (24
    # longs) then the palettes (+32 per id, from $E0A8: past id 25's is code), the tiles in GAME.DAT (past id 25's
    # portrait: other art). id 26 (Eternal's second form, Reptile's slot) never had one - writing it broke the game
    assert HOST_IDX <= 23, f'{SPEC.name}: EC has no versus portrait for id {HOST_ID}'
    W, H, FRAME = PORTRAIT_W, PORTRAIT_H, PORTRAIT_FRAME
    DAT_TILES, PALS = PORTRAIT[HOST_IDX], (0xE048 + 32 * (HOST_IDX + 3),)
    bio = ec.read_file('GAME.DAT')                          # the copy the versus screen loads
    old = portrait_indexed(bio, DAT_TILES)                 # the host's portrait, indexed
    keep = portrait_frame_colours(bio, DAT_TILES)
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
    im = Image.open(os.path.join(ROOT, 'extracted', getattr(SPEC, 'portrait', SPEC.mk_dir), 'portrait.png')).convert('RGB')
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


VOICE_RATE = 4800                 # Hz for Scorpion's MK lines (5200 before the spear's screams: the bank's room)
VOICE_LINES = [                   # (MK sample, Blade's sound id: the host's via SPEC.sound_ids, Hz) in clip order
    ('GETOHERE.SVX', 0x06D6, VOICE_RATE),     # (in id order: the driver loads a bank's clips as its table's
    ('MALEHURT.SVX', 0x06D7, VOICE_RATE),     #  entries name them, in order - entries pointing back at
    ('FINISHim.SVX', 0x06D9, VOICE_RATE),     #  earlier clips left the later ones out of sound RAM:
    ('GIRLHURT.SVX', 0x06DA, VOICE_RATE),     #  traced, the screams were never loaded)
    ('FINISHER.SVX', 0x06DB, VOICE_RATE),     # 'FINISH HER' (mkinputs picks it for a woman)
]                                             # MALEHURT / GIRLHURT: the spear's victim screams at the hit
VOICE_OF = {name: sid for name, sid, _ in VOICE_LINES}
BANK_ROOM = 17702                 # Blade's PCM chunk: Scorpion's bank stays this size or less
BLADE_SOUND_CALLS = (0x0F0E, 0x107E, 0x237E, 0x23A6, 0x272C,   # his $06D7/$06DA/$06DB plays: skipped
                     0x28A6)   # and $06D6 (GET OVER HERE now) at the projectile's launch: MK says it at the yank


# The punch / kick sounds every fighter shares: FIGHT.SND (sound RAM from 0, below the players' banks
# at $3F00; each clip on its own 256-byte page). PLYR.CO's attack records name three ids each: +8 the
# hit ($3EF, $3EC), +A the block ($3EB), +C the swing ($3EA, $3F0). MK's (tools/capture/mkmovesounds.py):
# SMACK1 on a hit, BLOCK1 on a block - EC's thuds sounded weak; FALL2 as a knocked-down
# or thrown fighter hits the floor ($3EE, PLYR's landing code $18A12: traced on an uppercut and a
# throw, never on a jump - MK's FALL2 exactly). Swings, specials and voices stay EC's (the swing
# also plays on punches: MK's punches grunt instead).
FIGHT_SOUNDS = {0x03EF: 'SMACK1.SVX', 0x03EC: 'SMACK1.SVX', 0x03EB: 'BLOCK1.SVX', 0x03EE: 'FALL2.SVX'}
FIGHT_PAGES = 0x3F00 // 256
# A clip takes (its bytes + n) / 256 pages, plus one, n between 6 and 27: measured in sound RAM (all nine:
# FALL2's 2046 bytes take 9 pages, FEETLAND's 1274 six, EC's 740 / 2020 / 3042 three / eight / twelve);
# counted with n = 27. Counted as bytes / 256 the bank looked 8 pages short of full: MALEJUMP's
# tail ($3900-$4060) went over player 1's bank at $3F00 (its first clip lost its end: the versus screens
# waited, a Contest froze). fight_pages / FIGHT_LEN.
FIGHT_NEW = {0x3F1: 'FEETLAND.SVX', 0x3F2: 'MALEJUMP.SVX'}   # new ids in FIGHT.SND (after EC's $3EA-$3F0):
#                                   id -> MK sample ($3F1: a jump's landing - mkinputs.FEET_SOUND; $3F2: an MK
#                                   punch's and jump's grunt - mk_punch_grunt, mkinputs.JUMP_GRUNT; Sonya's
#                                   GIRLJUMP is in her bank)
FIGHT_LEN = {'FEETLAND.SVX': 1250, 'MALEJUMP.SVX': 1762}   # samples kept: their quiet ends cut (FEETLAND's
#                                   last 26 at most 9/128, MALEJUMP's last 124 at most 8/128, faded) - 5 and 7
#                                   pages: 63 of 63
FIGHT_FADE = 32                   # samples faded out before a cut


def fight_pages(clip):
    """Sound RAM pages the driver gives a FIGHT.SND clip (its bytes, with the pad and $FF)."""
    return (len(clip) + 27) // 256 + 1
GRUNT = 0x3F2


def grunt_id(spec):
    """A fighter's grunt (his punches, his jumps): MALEJUMP in FIGHT.SND; Sonya's GIRLJUMP, her bank's
    voice id for it (GENERIC_VOICE: mk_voice gives Blade's voice ids, in the host's numbering, in order)."""
    if spec is not SONYA:
        return GRUNT
    lines = [n for n, _ in GENERIC_VOICE['sonya']]
    avail = [spec.sound_ids[b] for b in BLADE_VOICE_IDS if b in spec.sound_ids]
    return avail[lines.index('GIRLJUMP.SVX')]


# EC's effect objects: a pool of 35 ($A6 bytes each) after their free stack (-$35D2(a6) = $2CA2E: a word, 4 x
# how many are free, then the pointers), built by SUB $10504. The allocator (SUB $10844) pops one and clears it
# - with none free it left a0 on the free stack itself, carry set, and EC's ~80 spawns never look at the carry:
# each wrote its fields there - over the stack's pointers and the first object's link (the object loop then
# ran a wild task: Johnny's Contest froze at $102, PLYR's hit spark; its dust, $18D50, the same). Our blood
# and effects made a full pool possible (EC's own never filled it). Now 34 circulate and the first ($2CABC, the
# one the stack handed out first) is a scratch object, never listed: a spawn with none free gets it (carry still
# set) and writes there harmlessly. The objects stay where they were.
POOL_INIT, POOL_ALLOC = 0x10504, 0x10844          # the pool's setup; the allocator
POOL_CLEAR = 0x10850                              # its clear (bsr'd from $107F2 / $107FE too): a0 = the object
POOL_SCRATCH = 0x2CA2E + 2 + 4 * 35               # the first object: $2CABC


@patch('ec-object-pool', "A spawn with no free effect object gets a scratch one (EC wrote over its object list: a freeze)")
def ec_object_pool(ec, sources):
    import os
    from inputs import ROOT
    B = 0x6000
    # the setup: 35 built as before, then one fewer free - moveq and st make the subq's room
    init = bytes.fromhex('41EECA2E' '303C0023' '323C00A6' '4EB90000C62C' '7000' '2D40E16E' '2D40E172'
                         '3D7C7FFFE176' '1D7C00FFCA24' '4EB90000F434' '4E75')
    ec.patch_file('SUB.BIN', POOL_INIT - B,
                  bytes.fromhex('41EECA2E'           # lea -$35D2(a6),a0
                                '7023'               # moveq #35,d0
                                '323C00A6'           # move.w #$A6,d1
                                '4EB90000C62C'       # jsr $C62C          the stack, the objects after it
                                '596ECA2E'           # subq.w #4,-$35D2(a6)   34 free: the first is the scratch
                                '7000' '2D40E16E' '2D40E172' '3D7C7FFFE176'
                                '50EECA24'           # st -$35DC(a6)      (was move.b #$FF)
                                '4EB90000F434' '4E75'), expect=init)
    old = open(os.path.join(ROOT, 'extracted', 'ec_us', 'SUB.BIN'), 'rb').read()[POOL_ALLOC - B:0x10896 - B]
    assert old[:12] == bytes.fromhex('41EECA2E4EB90000C6426544') and old[-6:] == bytes.fromhex('44FC00004E75'), old.hex()
    scratch = (POOL_SCRATCH - 0x30000) & 0xFFFF
    code = bytes.fromhex('41EECA2E'          # lea -$35D2(a6),a0     the free stack
                         '4EB90000C642'      # jsr $C642             pop (carry: none)
                         '6516')             # bcs.s none
    assert POOL_ALLOC + len(code) == POOL_CLEAR
    code += bytes.fromhex('3F01'             # clear: move.w d1,-(sp)
                          '7252'             # moveq #82,d1          $A6 bytes: 83 words
                          '4258'             # clr.w (a0)+
                          '51C9FFFC'         # dbra d1,*-2
                          '90FC00A6'         # suba.w #$A6,a0
                          '321F'             # move.w (sp)+,d1
                          '44FC0000'         # move.w #0,ccr          (carry clear: an object)
                          '4E75')            # rts
    assert POOL_ALLOC + len(code) == 0x10866, hex(POOL_ALLOC + len(code))
    code += bytes.fromhex('41EE') + scratch.to_bytes(2, 'big')   # none: lea scratch(a6),a0
    code += bytes((0x61, (POOL_CLEAR - (POOL_ALLOC + len(code) + 2)) & 0xFF))   # bsr.s clear  (as a new one:
    code += bytes.fromhex('4868009C'         # pea $9C(a0)                                       no stale task link)
                          '215F0088'         # move.l (sp)+,$88(a0)  its 'task': its own tail ($9C-$A5) - a spawn
                                             #                        that sets a task there writes inside it
                          '003C0001'         # ori #1,ccr            carry: none free
                          '4E75')            # rts
    code += bytes.fromhex('4E71') * ((len(old) - len(code)) // 2)
    assert len(code) == len(old)
    ec.patch_file('SUB.BIN', POOL_ALLOC - B, code, expect=old)


DAZED_HIT = 0x1087A          # SUB.BIN: the bytes ec-object-pool leaves after its routine (nops after an rts)
BLOCK_TEST = 0x196D4         # PLYR.CO: the block decision's first test (btst #6,$F7(a3); bne.w $1971C)
HIT_PATH = 0x19750           # PLYR.CO: past the block decision: the hit lands


@patch('dazed-no-block', "A frozen or dazed fighter can't block: the hit lands (MK; a frozen CPU Dawson blocked an uppercut)")
def dazed_no_block(ec, sources):
    """A CPU Dawson frozen by Sub-Zero's ice blast blocked his uppercut (white sparks). Frozen - or
    dazed: FINISH HIM, the spear - a fighter is in EC's dizzy ($1F) with his move task parked, but
    EC's block decision (PLYR.CO $196D4) still ran: the CPU's guard roll ($1B4C(a6), the victim's
    $F7 bit 5 set) or a human's held 'away' blocked. Its first test becomes a call: a victim in
    $1F goes straight to the hit (the return address changed), else EC's own test, as before."""
    code = bytes.fromhex('0C2B001F00BF'    # cmpi.b #$1F,$BF(a3)   the victim dazed (any step flag above)?
                         '6608'            # bne.s ec
                         '2EBC') + HIT_PATH.to_bytes(4, 'big') + bytes.fromhex(   # move.l #hit,(sp)
                         '4E75'            # rts                   to the hit
                         '082B000600F7'    # ec: btst #6,$F7(a3)    (EC's test)
                         '4E75')           # rts
    ec.patch_file('SUB.BIN', DAZED_HIT - 0x6000, code, expect=bytes.fromhex('4E71') * (len(code) // 2))
    site = BLOCK_TEST - 0x14000 + 10                      # (PLYR.CO: its 10-byte header)
    old = bytes.fromhex('082B000600F7' '66000040')          # btst #6,$F7(a3); bne.w $1971C
    disp = 0x1971C - (BLOCK_TEST + 6 + 2)
    new = bytes.fromhex('4EB9') + DAZED_HIT.to_bytes(4, 'big') + bytes([0x66, disp]) + bytes.fromhex('4E71')
    ec.patch_file('PLYR.CO', site, new, expect=old)


@patch('mk-hit-sounds', "Punches and kicks land with MK's sounds (SMACK1; a block BLOCK1; a fall FALL2): EC's shared thuds replaced")
def mk_hit_sounds(ec, sources):
    snd = bytearray(ec.read_file('FIGHT.SND'))
    table, chunk = 0, int.from_bytes(snd[0:4], 'big')
    assert snd[4:6] == b'\x00\x1c' and snd[chunk + 4:chunk + 6] == b'\x00\x20'
    clen = int.from_bytes(snd[chunk:chunk + 4], 'big')
    clips, p, ln = [], chunk + 16, int.from_bytes(snd[chunk + 12:chunk + 16], 'big')
    while True:                                   # clip 0, then (length, clip) ...
        clips.append(bytes(snd[p:p + ln]))
        p += ln
        if p + 4 > chunk + clen:
            break
        ln = int.from_bytes(snd[p:p + 4], 'big')
        if not ln:                                # (zeros after the last clip)
            break
        p += 4
    entries = []                                  # (offset, id, clip)
    for i in range(int.from_bytes(snd[table + 0x0C:table + 0x0E], 'big')):
        e = table + int.from_bytes(snd[table + 0x0E + 4 * i:table + 0x12 + 4 * i], 'big')
        entries.append((e, int.from_bytes(snd[e:e + 2], 'big'), int.from_bytes(snd[e + 0x18:e + 0x1A], 'big')))
    # every entry its own clip, even two ids with one sample: the driver sets the end address (+$16,
    # where it keys the channel off) only for the entry that loads a clip - an entry naming an earlier
    # one keeps 0, and its channel loops sound RAM from 0 (FIGHT's first sound) until another sound
    # takes it (the hit sound kept playing over and over: $3EC shared $3EF's SMACK1)
    assert len({clip for _, _, clip in entries}) == len(entries), 'FIGHT.SND: EC entries share a clip'
    for e, sid, clip in entries:
        name = FIGHT_SOUNDS.get(sid)
        if not name:
            continue
        rate, body = mk_sample(name)
        pcm = to_rf5c164(body, rate, rate, len(body))
        clips[clip] = pcm + b'\x80' * ((len(pcm) + 1) & 1) + b'\xff'
        snd[e + 10:e + 12] = rate.to_bytes(2, 'big')
    new = []                                      # (id, clip index, rate): FIGHT_NEW's, appended
    for sid, name in sorted(FIGHT_NEW.items()):
        rate, body = mk_sample(name)
        if name in FIGHT_LEN:                     # (its quiet end cut, faded)
            n = FIGHT_LEN[name]
            assert n <= len(body)
            body = bytes((int.from_bytes(bytes([v]), 'big', signed=True) * min(FIGHT_FADE, n - i) // FIGHT_FADE)
                         & 0xFF for i, v in enumerate(body[:n]))
        pcm = to_rf5c164(body, rate, rate, len(body))
        clips.append(pcm + b'\x80' * ((len(pcm) + 1) & 1) + b'\xff')
        new.append((sid, len(clips) - 1, rate))
    pages = sum(fight_pages(c) for c in clips)
    assert pages <= FIGHT_PAGES, f'FIGHT.SND: {pages} pages, room {FIGHT_PAGES}'
    data = bytearray(clips[0])
    for c in clips[1:]:
        assert len(c) % 2 == 0 and c[-1] == 0xFF
        data += len(c).to_bytes(4, 'big') + c
    data += bytes(4)                              # (a zero length ends the clips, as in EC's file)
    tail = bytes(snd[chunk + clen:])
    snd[chunk:] = (16 + len(data)).to_bytes(4, 'big') + snd[chunk + 4:chunk + 12] \
        + len(clips[0]).to_bytes(4, 'big') + bytes(data) + tail
    if new:                                       # the table (chunk 0): an offset and an entry each
        n = int.from_bytes(snd[0x0C:0x0E], 'big')
        offs = [int.from_bytes(snd[0x0E + 4 * i:0x12 + 4 * i], 'big') for i in range(n)]
        ents = [bytes(snd[o:o + 0x1A]) for o in offs]
        for sid, clip, rate in new:
            e = bytearray(ents[0])
            e[0:2], e[10:12], e[0x18:0x1A] = sid.to_bytes(2, 'big'), rate.to_bytes(2, 'big'), clip.to_bytes(2, 'big')
            ents.append(bytes(e))
        head = 0x10 + 4 * len(ents)               # (every EC table: 2 bytes between the list and the entries)
        assert offs == [0x10 + 4 * n + 0x1A * i for i in range(n)], 'FIGHT.SND table not as EC packs it'
        tab = bytearray(snd[:0x0E]) + b''.join((head + 0x1A * i).to_bytes(4, 'big') for i in range(len(ents)))
        tab += snd[0x0E + 4 * n:0x10 + 4 * n] + b''.join(ents)
        tab[0:4] = len(tab).to_bytes(4, 'big')
        tab[0x0C:0x0E] = len(ents).to_bytes(2, 'big')
        snd = tab + snd[chunk:]
    ec.replace_file('FIGHT.SND', bytes(snd))
    print(f'        {", ".join(sorted(set(FIGHT_SOUNDS.values())))}: {pages} of {FIGHT_PAGES} pages')


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
    ids = dict((SPEC.sound_ids[sid], (k, hz)) for k, (_, sid, hz) in enumerate(VOICE_LINES))
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
                 'subzero': [('subzwep.SVX', 0x34), ('subslide.SVX', 0x35)] + _FINISH,  # ice blast, slide
                 'liukang': [('LUIKFLY.SVX', 0x35)] + _FINISH,  # flying kick yell (his slot has 3 voice ids)
                 'kano': [('knife1.SVX', 0x34), ('MALEJUMP.SVX', 0x35)] + _FINISH,     # knife, cannonball
                 'sonya': [('GIRLJUMP.SVX', 0x35)] + _FINISH,   # square-wave flight (her slot has 3 voice ids)
                 # his spear's lines (Scorpion's: MK CD's Reptile is fighter 4, Scorpion, for player 2) -
                 # played by rs_drive (mkinputs.RS_SOUNDS); his bank (CHA.SND, Shang's too) has 3 voice ids
                 'reptile': [('GETOHERE.SVX', 'yank'), ('MALEHURT.SVX', 'scream_m'), ('GIRLHURT.SVX', 'scream_f')]}
GENERIC_VOICE_RATE = 8000        # Hz at most; lower (VOICE_RATES) until his sounds fit the bank
VOICE_RATES = (8000, 7000, 6400, 6000, 5600, 5200, 4800)
BLADE_VOICE_IDS = (0x06D6, 0x06D7, 0x06D8, 0x06D9, 0x06DA, 0x06DB)


def mk_voice(ec, sources):
    """As scorpion_voice, for SPEC (the other MK fighters): his MK
    special-move sounds in his copy of Blade's bank; every other voice id
    plays silence; Blade's own plays of his voice ids are skipped."""
    lines = GENERIC_VOICE.get(SPEC.key, [])
    ids = SPEC.sound_ids
    snd = bytearray(ec.read_file(host('SND')))
    chunk, table = 0x16CA, 0x1624
    clen = int.from_bytes(snd[chunk:chunk + 4], 'big')
    assert snd[chunk + 4:chunk + 6] == b'\x00\x20' and chunk + clen == len(snd) - 4
    avail = [ids[b] for b in BLADE_VOICE_IDS if b in ids]   # (not every voice id has a host counterpart)
    assert len(lines) <= len(avail), f'{SPEC.name}: {len(lines)} sounds, {len(avail)} voice ids'
    mine = {avail[k]: k for k in range(len(lines))}
    order = []                                    # the table's entries: (entry, id)
    for i in range(int.from_bytes(snd[table + 0x0C:table + 0x0E], 'big')):
        e = table + int.from_bytes(snd[table + 0x0E + 4 * i:table + 0x12 + 4 * i], 'big')
        order.append((e, int.from_bytes(snd[e:e + 2], 'big')))
    assert set(mine) <= {sid for _, sid in order}, f'{SPEC.name}: a voice id not in his bank'
    for hz in VOICE_RATES:
        # a clip per entry, in the entries' order (the driver loads them so, and sets a channel's end
        # address only for the entry that loads a clip: entries sharing the silence kept 0 - played,
        # one would loop sound RAM from 0 until another sound took the channel); silence for the
        # ids he doesn't use
        clips, said = [], set()
        for _, sid in order:
            if sid in mine and sid not in said:   # (the driver plays an id's first entry: his bank's
                said.add(sid)                     #  table repeats its last id - those get silence)
                rate, body = mk_sample(lines[mine[sid]][0])
                pcm = to_rf5c164(body, rate, hz, int(len(body) * hz / rate))
                clips.append(pcm + b'\x80' * ((len(pcm) + 1) & 1) + b'\xff')
            else:
                clips.append(b'\x80' * 15 + b'\xff')
        data = bytearray(clips[0])
        for c in clips[1:]:
            data += len(c).to_bytes(4, 'big') + c
        if len(data) <= BANK_ROOM:
            break
    assert len(data) <= BANK_ROOM, f'{SPEC.name}: sounds need {len(data)} bytes, room {BANK_ROOM}'
    snd[chunk:] = (16 + len(data)).to_bytes(4, 'big') + snd[chunk + 4:chunk + 12] \
        + len(clips[0]).to_bytes(4, 'big') + bytes(data) + bytes(4)
    for k, (e, sid) in enumerate(order):
        snd[e + 0x18:e + 0x1A] = k.to_bytes(2, 'big')
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
    if SPEC.key == 'reptile':                     # Shang's code (CHA.CO) plays the same bank's ids: his
        co = bytearray(ec.read_file('CHA.CO'))    #  Blade plays would say Reptile's lines - skipped too
        for i in range(0, len(co) - 10, 2):
            if co[i:i + 2] == b'\x30\x3c' and int.from_bytes(co[i + 2:i + 4], 'big') in voice \
                    and co[i + 4:i + 10] == bytes.fromhex('4eb900006d58'):
                co[i:i + 2] = b'\x60\x08'
                n += 1
        ec.replace_file('CHA.CO', bytes(co))
    SPEC.voice = {move: avail[k] for k, (_, move) in enumerate(lines)}
    print(f'        {len(lines)} MK sounds at {hz} Hz, {len(data)} bytes; {n} of Blade\'s voice plays skipped')


@patch('scorpion-inputs', "Scorpion's specials use MK inputs (back, back + LP = spear); Blade's own specials removed")
def scorpion_inputs(ec, sources):
    """See tools/lib/mkinputs.py: a new 'two taps + button' move type in PLYR.CO's
    special-move recogniser, and Blade's move list replaced by Scorpion's."""
    import mkinputs
    # his voice lines' ids in his slot's numbering (scorpion_voice)
    ids = {name: SPEC.sound_ids[sid] for name, sid in VOICE_OF.items()}
    mkinputs.VOICE_ID, mkinputs.FINISH_VOICE, mkinputs.FINISH_VOICE_F, mkinputs.SCREAM_M, mkinputs.SCREAM_F = \
        (ids[n] for n in ('GETOHERE.SVX', 'FINISHim.SVX', 'FINISHER.SVX', 'MALEHURT.SVX', 'GIRLHURT.SVX'))
    sub = ec.read_file('SUB.BIN')
    at = (len(sub) + 1) & ~1
    add_rope(ec)                         # MK's spear: a rope of its own
    # his MK attack scripts go after his .PL's chunk chain (mkinputs.SCO_TAIL): room in his block
    pl = ec.read_file(host('PL'))
    end = pl_chain_end(pl)
    mkinputs.SCO_TAIL['off'] = (end + 4 + 1) & ~1
    plyr, bla, extra = mkinputs.build(ec.read_file('PLYR.CO'), mkinputs.spear_script(ec.read_file(host('CO'))),
                                      0x6000 + at)
    put_sub(ec, sub + bytes(at - len(sub)) + extra)
    tail = mkinputs.SCO_TAIL['data']
    from scorpion_full import MAX_PL
    off = mkinputs.SCO_TAIL['off']
    assert off + len(tail) <= MAX_PL, f'{host("PL")} + its tail over {MAX_PL} by {off + len(tail) - MAX_PL}'
    ec.replace_file(host('PL'), pl[:end + 4] + bytes(off - end - 4) + tail)
    print(f'        {len(tail)} bytes of his MK scripts after {host("PL")}\'s chunk chain (+${off:X})')
    for piece in (mkinputs.GEN_LOW, mkinputs.GEN_KD, mkinputs.GEN_ROOM):
        if piece.get('data'):
            print(f'        {len(piece["data"])} bytes in his module\'s room at ${piece["off"]:X}')
    print(f'        MK code block: {len(bla) - mkinputs.EXT_OFF} bytes at ${mkinputs.EXT_OFF:X}')
    ec.replace_file('PLYR.CO', plyr)
    ec.replace_file(host('CO'), bla)


CHAIN_START = 0x3FA0              # Blade's move scripts: PLYR $1A278 walks them into the move table


def mk_attack_scripts(ec, sources):
    """His basic attacks play MK's animation (tools/lib/mkscripts.py). A fighter's
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
DASH_TUNE = {'raiden': (7, 19), 'subzero': (6, 9), 'liukang': (7, 12), 'kano': (6, 12), 'sonya': (7, 12)}
# Sonya's square wave: the dash's steps (41:16 41:17 41:16 41:61 41:62 41:61 41:16) were
# standing, flying, standing - up and down in a frame. Her own frames for the rise and the
# drop (41:30-34: in no Blade script; patches.SONYA pins MK's poses 10, 11, 17, 18 to them).
SQUARE_STEPS = {1: (0x17, 0x30), 2: (0x16, 0x31), 5: (0x61, 0x32), 6: (0x16, 0x34)}


ROPE_CHUNKS = {22: (0xF6, 0x126), 26: (0xF7, 0x127)}   # thrower id -> his spear rope's sheet and tile
                                  # source (mkspear: ids no EC or MK file registers)


def add_rope(ec):
    """MK's spear rope (mkspear.py, mkinputs.emit_spear_rope): its raw tile source and sheet go at the
    end of his .PL's chunk chain (EC's loader registers them with the file)."""
    import mkspear, mkinputs, scorpion_full
    sheet, slot = ROPE_CHUNKS[HOST_ID]
    pl = ec.read_file(host('PL'))
    end = pl_chain_end(pl)
    makers, nt = mkspear.chunks(sheet, slot, scorpion_full.remap_colours)
    assert mkspear.max_tiles() == mkinputs.ROPE_TILES, mkspear.max_tiles()
    tiles = makers[('tiles', slot)](end)
    sh = makers[('sheet', sheet)](end + len(tiles))
    ec.replace_file(host('PL'), pl[:end] + tiles + sh + pl[end:])
    mkinputs.ROPE_SHEETS[HOST_ID] = (sheet, slot)
    print(f'        the spear\'s rope: sheet ${sheet:X}, {nt} tiles, {len(tiles) + len(sh)} bytes in {host("PL")}')


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
    mkinputs.RS_SOUNDS = dict(getattr(SPEC, 'voice', {})) if SPEC.key == 'reptile' else {}
    co = bytearray(mkinputs.recovery_still(ec.read_file(host('CO'))))   # his projectile's recovery: no drift
    if SPEC.key == 'reptile':
        add_rope(ec)                         # MK's spear: a rope of its own (before his tail is placed)
    if SPEC.key == 'reptile':                # his spear as Scorpion's (mkinputs.spear_script): only the
        for off, exp, new in mkinputs.SPEAR_SCRIPT_EDITS:      # rope's hit, on MK's timeline
            o = off - 0x21800
            assert co[o:o + 4].hex() == exp, hex(off)
            co[o:o + 4] = bytes.fromhex(new)
        mkinputs.spear_timeline(co)                         # MK's timeline (mk_fidelity_spec 6)
    if SPEC.key in ('raiden', 'reptile'):
        # Move $31 uses our teleport script (Reptile's: his ice blast) but still runs Blade's
        # move task. Skip its original projectile spawn and resume at the normal recovery.
        assert co[0x2534:0x2538] == bytes.fromhex('43fa15f0')
        assert co[0x2564:0x256a] == bytes.fromhex('4eb900006960')
        co[0x2534:0x2538] = bytes.fromhex('6000002e')  # bra.w $2564
    if SPEC.key == 'liukang':                # his flying kick: MK's timeline on the dash's 7 steps
        steps, _pins, speed = mkinputs.flykick_plan(SPEC.mk_dir)
        n = int.from_bytes(co[DASH_SCRIPT + 2:DASH_SCRIPT + 4], 'big') + 1
        assert len(steps) <= n == 7
        term = co[DASH_SCRIPT + 20 + 12 * n:DASH_SCRIPT + 32 + 12 * n]
        assert int.from_bytes(term[:2], 'big') < 0x100
        co[DASH_SCRIPT + 2:DASH_SCRIPT + 4] = (len(steps) - 1).to_bytes(2, 'big')
        co[DASH_SCRIPT + 20 + 12 * len(steps):DASH_SCRIPT + 32 + 12 * len(steps)] = term
        co[DASH_SCRIPT + 4:DASH_SCRIPT + 8] = (speed << 16).to_bytes(4, 'big')
        hit = co[DASH_SCRIPT + 20 + 12 * 4 + 10:DASH_SCRIPT + 20 + 12 * 5]     # Blade's 41:62 step's hit data
        assert co[DASH_SCRIPT + 20 + 12 * 4:DASH_SCRIPT + 20 + 12 * 4 + 2] == (0x4162 + (SHEET_SHIFT << 8)).to_bytes(2, 'big') \
            and hit != b'\0\0'                # (his module is renumbered by now: his sheets)
        for k, (f, t, fl, flies) in enumerate(steps):
            st = DASH_SCRIPT + 20 + 12 * k
            co[st:st + 12] = (f + (SHEET_SHIFT << 8)).to_bytes(2, 'big') + t.to_bytes(2, 'big') + bytes(4) + fl.to_bytes(2, 'big') \
                + (hit if flies else b'\0\0')
    elif SPEC.key in DASH_TUNE:              # Blade's dash as his MK flight (torpedo, slide)
        speed, ticks = DASH_TUNE[SPEC.key]
        assert int.from_bytes(co[DASH_SCRIPT + 4:DASH_SCRIPT + 8], 'big') == 0xA0000
        co[DASH_SCRIPT + 4:DASH_SCRIPT + 8] = (speed << 16).to_bytes(4, 'big')
        st = DASH_SCRIPT + 20 + 12 * 4               # its 41:62 step (the hit)
        assert co[st + 1] == 0x62 and int.from_bytes(co[st + 2:st + 4], 'big') == 6, co[st:st + 12].hex()
        co[st + 2:st + 4] = ticks.to_bytes(2, 'big')
    if SPEC.key == 'johnny':
        for k, (was, now) in {1: (0x17, 0x30), 2: (0x16, 0x31), 3: (0x61, 0x32),
                              5: (0x61, 0x34), 6: (0x16, 0x35)}.items():
            st = DASH_SCRIPT + 20 + 12 * k
            assert co[st + 1] == was
            co[st + 1] = now
    if SPEC.key == 'sonya':
        for k, (was, now) in SQUARE_STEPS.items():
            st = DASH_SCRIPT + 20 + 12 * k
            assert co[st + 1] == was, (k, co[st:st + 12].hex())
            co[st + 1] = now
    dz = mkinputs.daze_pad(SHEET_SHIFT)      # his MK daze, at the second victory room's end
    co = bytes(co[:mkinputs.DAZE_PAD]) + dz + bytes(co[mkinputs.DAZE_PAD + len(dz):])
    assert len(co) <= mkinputs.EXT_OFF, f'{host("CO")} reaches the block offset'
    mkinputs.GEN_TAIL.update(off=None, data=b'')
    if HOST_ID in mkinputs.TAIL_FIGHTERS:    # his scripts and fatality data after his .PL's chunk chain
        pl = ec.read_file(host('PL'))
        end = pl_chain_end(pl)
        mkinputs.GEN_TAIL['off'] = (end + 4 + 1) & ~1     # past the zero length that stops EC's loader
        from mkprojectile import chunks
        sh = next((o for o, ln, t in chunks(pl) if t == 4 and int.from_bytes(pl[o + 10:o + 12], 'big') // 4 == mkinputs.FX_SHEET.get(HOST_ID)), None)
        mkinputs.GEN_TAIL['fx_src'] = int.from_bytes(pl[sh + 12:sh + 14], 'big') // 2 if sh is not None else 0   # its tile source's id
        if sh is not None:                   # (its size: EC's upload copies all of it)
            sid = int.from_bytes(pl[sh + 12:sh + 14], 'big')
            mkinputs.GEN_TAIL['fx_size'] = next(ln for o, ln, t in chunks(pl)
                                                if t == 0 and int.from_bytes(pl[o + 10:o + 12], 'big') // 4 == sid) - 20
                                                                       # ($D448 / -$67D0; held heads only)
    mkinputs.MORPH['off'] = None
    if HOST_ID == mkinputs.SHANG_ID:         # his morph: room after his .PL's chunk chain for his module
        mpl = ec.read_file(host('PL'))       # while he is his opponent (mkinputs.emit_morph)
        mend = pl_chain_end(mpl)
        mkinputs.MORPH['off'] = (mend + 4 + 3) & ~3
    mkinputs.JUMP_GRUNT = grunt_id(SPEC)     # his jump's grunt (MALEJUMP; Sonya's GIRLJUMP in her bank)
    blk = mkinputs.generic_block(HOST_ID, SHEET_SHIFT, SPEC.mk_dir, getattr(SPEC, 'voice', {}))
    if mkinputs.MORPH['off'] is not None:
        from scorpion_full import MAX_PL
        import plsheet
        moff = mkinputs.MORPH['off']
        # his empty frame (mkinputs.MORPH_BLANK): its record no boxes, no points, no pieces
        mpl = bytearray(mpl)
        bs, bf = (mkinputs.MORPH_BLANK >> 8) - 0x40 + SPEC.sheet_base, mkinputs.MORPH_BLANK & 0xFF
        sh = next(sheet for sid, _res, sheet, _n in plsheet.sheets(bytes(mpl)) if sid == bs)
        offs = [int.from_bytes(mpl[sh + 6 + 2 * f:sh + 8 + 2 * f], 'big') for f in range(int.from_bytes(mpl[sh + 4:sh + 6], 'big'))]
        assert offs.count(offs[bf]) == 1, 'his blank frame shares its record'
        q = sh + 6 + offs[bf]
        mpl[q:q + 6] = bytes.fromhex('000000008000')
        mpl = bytes(mpl)
        assert not plsheet.pieces(mpl, sh, bf)
        assert moff + mkinputs.MORPH_SIZE <= MAX_PL, f'{host("PL")} + his saved module over {MAX_PL}'
        ec.replace_file(host('PL'), mpl[:mend + 4] + bytes(moff - mend - 4) + bytes(mkinputs.MORPH_SIZE))
        print(f'        {mkinputs.MORPH_SIZE} bytes for his saved module after {host("PL")}\'s chunk chain (+${moff:X})')
    if mkinputs.GEN_TAIL['data']:
        off, tail = mkinputs.GEN_TAIL['off'], mkinputs.GEN_TAIL['data']
        from scorpion_full import MAX_PL
        assert off + len(tail) <= MAX_PL, f'{host("PL")} + its tail over {MAX_PL} by {off + len(tail) - MAX_PL} (tail {len(tail)})'
        ec.replace_file(host('PL'), pl[:end + 4] + bytes(off - end - 4) + tail)
        print(f'        {len(tail)} bytes of scripts/fatality data after {host("PL")}\'s chunk chain (+${off:X})')
    lim = mkinputs.MORPH_MV                  # (the slot's last 32 bytes: Shang's morph vars and trampoline)
    assert mkinputs.EXT_OFF + len(blk) <= lim, f'{SPEC.key}: block of {len(blk)} bytes overflows the module slot by {mkinputs.EXT_OFF + len(blk) - lim}'
    for piece in (mkinputs.GEN_LOW, mkinputs.GEN_KD, mkinputs.GEN_ROOM):   # (code and tables in the rooms of Blade's pre-fight taunt and his
        if piece.get('data'):                           #  victory dances: mk_intro_stance, mk_victory_stance)
            o, d = piece['off'], piece['data']
            co = co[:o] + d + co[o + len(d):]
            print(f'        {len(d)} bytes in his module\'s room at ${o:X}')
    for o, d in mkinputs.GEN_DEAD.get('pieces', ()):   # (in bodies of Blade's scripts his block replaces)
        co = co[:o] + d + co[o + len(d):]
        print(f'        {len(d)} bytes in a dead script body of his module at ${o:X}')
    co = co + bytes(mkinputs.EXT_OFF - len(co)) + blk
    if HOST_ID == mkinputs.SHANG_ID:         # his morph vars at the slot's end: loaded as zeros
        co += bytes(mkinputs.MORPH_SIZE - len(co))
    ec.replace_file(host('CO'), co)
    print(f'        MK code block: {len(blk)} bytes at ${mkinputs.EXT_OFF:X}')


def mk_projectile(ec, sources):
    """His MK projectile's flying art (tools/lib/mkprojectile.py) in his effect
    sheet (Blade's $44, renumbered to his own mkinputs.FX_SHEET), for the
    object mkinputs.emit_proj flies across the screen."""
    import mkprojectile, scorpion_full
    import mkinputs
    fat = mkinputs.FATALS.get(HOST_ID, {})
    if fat.get('fxl'):                                  # Raiden: his fatality's lightning pieces (Sonya: her kiss)
        extra = [rec for *_, rec in fat['fxl']()]
    else:
        extra = [rec for _, rec in mkinputs.szf_heads()] \
            if fat.get('heads', True) and HOST_ID in mkinputs.FATALS else []   # (his fatality's heads)
    pl, (nf, ni) = mkprojectile.build(ec.read_file(host('PL')), SPEC.key, SPEC.mk_dir, scorpion_full.remap_colours, extra,
                                      live_extra=mkinputs.johnny_shadow_extra if SPEC.key == 'johnny' else None,
                                      shrink=bool(fat.get('fxl')) and not fat.get('kiss'))   # (Raiden: room for his pieces' tiles)
    if extra:
        print(f'        + {len(extra)} EC fighters\' severed heads (his fatality) from frame {nf + ni}')
    # his own sheet number (they're global: Blade's $44 in every one of them collided)
    fx = mkinputs.FX_SHEET[HOST_ID]
    pl = bytearray(pl)
    hit = [o for o, ln, t in mkprojectile.chunks(pl) if t == 4 and int.from_bytes(pl[o + 10:o + 12], 'big') == 4 * mkprojectile.SHEET]
    assert len(hit) == 1, hit
    pl[hit[0] + 10:hit[0] + 12] = (4 * fx).to_bytes(2, 'big')
    ec.replace_file(host('PL'), bytes(pl))
    old = mkprojectile.SHEET.to_bytes(2, 'big')
    for at in (0x58,                         # Blade's module init: load resources ($696C) $44, $45 (VRAM tiles)
               0x70):                        #  move.w #$44,$19C(a5): his projectile's sheet
        ec.patch_file(host('CO'), at, fx.to_bytes(2, 'big'), expect=old)
    ec.patch_file(host('CO'), mkinputs.PJ_DESC + 1, bytes([fx]), expect=bytes([mkprojectile.SHEET]))   # Blade's projectile descriptor
    print(f'        projectile: {nf} flight + {ni} impact frames in sheet ${fx:X}')


# Raiden, Johnny Cage, Sub-Zero, Liu Kang, Kano, Sonya: the same patches with
# their settings
for _spec, _slot in ((RAIDEN, "Chin Wo's"), (JOHNNY, "Zuni's"), (SUBZERO, "Yappy's"),
                     (LIUKANG, "Crispy's"), (KANO, "Slither's"), (SONYA, "Hooter's")):
    for _n, _fn in (('slot', scorpion_slot), ('full', scorpion_full), ('proj', mk_projectile), ('palette', scorpion_palette),
                    ('name', scorpion_name), ('roster', scorpion_roster), ('voice', mk_voice), ('mkcode', mk_code),
                    ('portrait', scorpion_portrait),
                    ('icon', scorpion_icon)):
        if _n == 'proj' and _spec.key not in __import__('mkprojectile').PROJ:
            continue                     # (a fighter with no MK projectile art)
        PATCHES.append((f'{_spec.key}-{_n}', f"{_spec.name.title()} ({_slot} slot): as scorpion-{_n}",
                        for_spec(_spec, _fn)))


def shang_roster(ec, sources):
    """As scorpion-roster, without the select screen (a boss): his object record
    is Blade's, Blade's checks of his own id are Shang's, his sheets his own."""
    sub = ec.read_file('SUB.BIN')
    tab = 0x11E8C - 0x6000
    rec = lambda fid: tab + int.from_bytes(sub[tab + 2 * fid:tab + 2 * fid + 2], 'big')
    ec.patch_file('SUB.BIN', rec(HOST_ID), sub[rec(9):rec(9) + 34])
    renumber_sheets(ec)
    import re
    co = bytearray(ec.read_file(host('CO')))
    n = 0
    for m in re.finditer(rb'\x0c[\x68-\x6f]\x00\x09\x00\x4c', bytes(co)):
        co[m.start() + 2:m.start() + 4] = HOST_ID.to_bytes(2, 'big')
        n += 1
    assert n == 5, f'expected 5 id checks in Blade\'s module, found {n}'
    ec.patch_file(host('CO'), 0, bytes(co))


SHANG_HUD_AT = 0xBA14              # SUB.BIN (RAM): 'ETERNAL\0CRISPY\0', both names no longer shown


def shang_name(ec, sources):
    """Health bar, versus screen, win messages and stats say SHANG TSUNG. SUB.BIN
    is full: the health bar's name goes over 'ETERNAL\0CRISPY\0' (Crispy's entry
    is Liu Kang's now, Eternal's Shang's)."""
    at, old, new = SPEC.win
    ec.patch_file('SUB.BIN', at, new, expect=old)
    name = SPEC.name.encode('ascii')
    sub = ec.read_file('SUB.BIN')
    o = SHANG_HUD_AT - 0x6000
    assert sub[o:o + 15] == b'ETERNAL\0CRISPY\0'
    ptrs = [int.from_bytes(sub[0x5970 + 4 * i:0x5974 + 4 * i], 'big') for i in range(25)]
    assert SHANG_HUD_AT + 8 not in ptrs, 'Crispy\'s name still in use'
    ec.patch_file('SUB.BIN', o, name + b'\0', expect=sub[o:o + len(name) + 1])
    ec.patch_file('SUB.BIN', 0x5970 + 4 * HOST_IDX, SHANG_HUD_AT.to_bytes(4, 'big'))

    def repoint(fname, base, table, text):
        b = ec.read_file(fname)
        at = (len(b) + 1) & ~1
        b = bytearray(b + bytes(at - len(b)) + text)
        b[table + 4 * HOST_IDX:table + 4 * HOST_IDX + 4] = (base + at).to_bytes(4, 'big')
        ec.replace_file(fname, bytes(b))
    # the versus screen: 'SHANG TSUNG' ran off the right edge as player 2 ('SHANG TSUN'): SHANG, centred as
    # EC's 'BLAST' (its first byte); the health bar, win message and stats keep the full name
    repoint('GAME.CO', 0x14000, 0xDB1C, b'\x04SHANG\0')
    repoint('STATS.CO', 0x34000, 0x6B4, name + b'\0')


SHANG_ARENA_CHECKS = (0x76C, 0x774, 0x1CFC)   # EC.BGI: cmpi.w #$B,<fighter id>(a6) (the boss's window pictures, the orb's target)


def shang_arena(ec, sources):
    """Eternal's arena draws its windows with the boss's pictures when a fighter
    is id 11, from tiles the Eternal Champion's art file put in VRAM: Shang's
    file has none (speckled windows). The arena treats him as any opponent."""
    for at in SHANG_ARENA_CHECKS:
        ec.patch_file('EC.BGI', at, bytes.fromhex('0c6e00ff'), expect=bytes.fromhex('0c6e000b'))

for _n, _fn in (('slot', scorpion_slot), ('full', scorpion_full), ('proj', mk_projectile), ('palette', scorpion_palette),
                ('name', shang_name), ('roster', shang_roster), ('mkcode', mk_code), ('arena', shang_arena),
                ('portrait', scorpion_portrait), ('icon', scorpion_icon)):
    PATCHES.append((f'shang-{_n}', f"Shang Tsung (the Eternal Champion's slot): as scorpion-{_n}",
                    for_spec(SHANG, _fn)))

REPTILE_HUD_AT = 0xBA90            # SUB.BIN (RAM): 'ETERNAL\0', the second form's own health-bar name


def reptile_name(ec, sources):
    """Health bar, versus screen, win messages and stats say REPTILE (MK CD's bar
    says SCORPION, its win message REPTILE). The health bar's name goes over the
    second form's own 'ETERNAL' (8 bytes, his alone)."""
    at, old, new = SPEC.win
    ec.patch_file('SUB.BIN', at, new, expect=old)
    name = SPEC.name.encode('ascii')
    sub = ec.read_file('SUB.BIN')
    ptrs = [int.from_bytes(sub[0x5970 + 4 * i:0x5974 + 4 * i], 'big') for i in range(25)]
    assert ptrs[HOST_IDX] == REPTILE_HUD_AT and ptrs.count(REPTILE_HUD_AT) == 1, [hex(p) for p in ptrs]
    o = REPTILE_HUD_AT - 0x6000
    ec.patch_file('SUB.BIN', o, name + b'\0', expect=b'ETERNAL\0')

    def repoint(fname, base, table, text):
        b = ec.read_file(fname)
        at = (len(b) + 1) & ~1
        b = bytearray(b + bytes(at - len(b)) + text)
        b[table + 4 * HOST_IDX:table + 4 * HOST_IDX + 4] = (base + at).to_bytes(4, 'big')
        ec.replace_file(fname, bytes(b))
    repoint('GAME.CO', 0x14000, 0xDB1C, b'\x00' + name + b'\0')
    repoint('STATS.CO', 0x34000, 0x6B4, name + b'\0')


VERSUS_MAP = 0xDF60      # GAME.CO: a versus portrait (d1 = id - 2): id 26 drawn as id 11, then its palette
VERSUS_MAP_OLD = bytes.fromhex('0c810000001866027209'      # cmpi.l #$18,d1; bne.s +2; moveq #9,d1
                               '6100006c')                 # bsr.w $DFD8 (the palette)
VERSUS_PAL = 0xDFE8      # GAME.CO: the palette loader's body (a0 = its palette), to its rts
VERSUS_PAL_OLD = bytes.fromhex(                            # by d0 (the side): palette line 0, 1, 2, else 3
    '0c40 0000 6612 2048 303c 0000 323c 000f 4eb9 0000 69fc 6040'
    '0c40 0001 6612 2048 303c 0010 323c 001f 4eb9 0000 69fc 6028'
    '0c40 0002 6612 2048 303c 0020 323c 002f 4eb9 0000 69fc 6010'
    '2048 303c 0030 323c 003f 4eb9 0000 69fc'
    '205f 381f 221f 4e75')


def reptile_portrait(ec, sources):
    """Reptile's versus portrait: Sub-Zero's with his blues turned green, as his select icon.
    EC has portraits for ids 2-25 only and draws id 26 (the Eternal Champion's second form) as
    id 11 (GAME.CO $DF60), Shang's now. Id 26 draws Sub-Zero's tiles instead, with a palette of
    its own: the palette loader's four copies by side (palette line 0-3) become one, and the
    palette goes in the bytes that frees."""
    import colorsys
    import mkinputs
    assert [n for n, _, _ in PATCHES].index('subzero-portrait') < [n for n, _, _ in PATCHES].index('reptile-portrait')
    sz = SUBZERO.host_id - 2
    g = ec.read_file('GAME.CO')
    src = g[0xE0A8 + 32 * sz:0xE0A8 + 32 * sz + 32]          # Sub-Zero's (subzero-portrait's) palette
    assert int.from_bytes(g[0xE048 + 4 * sz:0xE04C + 4 * sz], 'big') == 0x14000 + 0xE0A8 + 32 * sz
    keep = portrait_frame_colours(ec.read_file('GAME.DAT'), PORTRAIT[sz])
    pal = bytearray(src)
    for k in range(16):
        if k in keep:
            continue
        c = int.from_bytes(src[2 * k:2 * k + 2], 'big')
        r, gg, b = ((c >> 1 & 7) / 7, (c >> 5 & 7) / 7, (c >> 9 & 7) / 7)
        h, s, v = colorsys.rgb_to_hsv(r, gg, b)
        if 120 / 255 <= h <= 185 / 255 and s >= 60 / 255:     # mkportraits_disc.reptile's rule
            r, gg, b = colorsys.hsv_to_rgb(h - 70 / 255, s, v)
        pal[2 * k:2 * k + 2] = ((round(b * 7) << 9) | (round(gg * 7) << 5) | (round(r * 7) << 1)).to_bytes(2, 'big')
    assert pal != src, 'no blues in Sub-Zero\'s portrait palette'

    m = mkinputs.Asm(0x14000 + VERSUS_MAP)
    m.bccw(0x61, 'pal'); m.w(0x0C81); m.l(26 - 2)            # bsr.w (palette: id 26's own); cmpi.l #24,d1
    m.bcc(0x66, 'go'); m.w(0x7200 | sz)                      # bne.s; moveq #<Sub-Zero>,d1 (his tiles)
    m.label('go')
    m.labels['pal'] = 0xDFD8 - VERSUS_MAP
    code = m.build()
    assert len(code) == len(VERSUS_MAP_OLD)
    ec.patch_file('GAME.CO', VERSUS_MAP, code, expect=VERSUS_MAP_OLD)

    a = mkinputs.Asm(0x14000 + VERSUS_PAL)                            # (a0 = the table's palette, d1 = (id - 2) * 4)
    a.w(0x0C41, 4 * (26 - 2)); a.bcc(0x66, 'line')           # cmpi.w #96,d1; bne.s
    a.pcrel(0x41FA, 'reptile')                               # lea reptile(pc),a0
    a.label('line')
    a.w(0x0C40, 3); a.bcc(0x63, 'n')                         # cmpi.w #3,d0; bls.s   (else line 3, as EC)
    a.w(0x303C, 3)                                           # move.w #3,d0
    a.label('n')
    a.w(0xE948, 0x3200, 0x0641, 0x000F)                      # lsl.w #4,d0; move.w d0,d1; addi.w #15,d1
    a.w(0x4EB9); a.l(0x69FC)                                 # jsr $69FC (load colours d0-d1 from a0)
    a.w(0x205F, 0x381F, 0x221F, 0x4E75)                      # (as EC) movea.l (a7)+,a0; move.w (a7)+,d4; move.l (a7)+,d1; rts
    a.label('reptile')
    a.out += pal
    code = a.build()
    assert len(code) <= len(VERSUS_PAL_OLD)
    ec.patch_file('GAME.CO', VERSUS_PAL, code + bytes(len(VERSUS_PAL_OLD) - len(code)), expect=VERSUS_PAL_OLD)
    n = sum(pal[2 * k:2 * k + 2] != src[2 * k:2 * k + 2] for k in range(16))
    print(f"        portrait: Sub-Zero's tiles, {n} of his colours turned green")


for _n, _fn in (('slot', scorpion_slot), ('full', scorpion_full), ('proj', mk_projectile), ('palette', scorpion_palette),
                ('name', reptile_name), ('roster', shang_roster), ('voice', mk_voice), ('mkcode', mk_code),
                ('portrait', reptile_portrait), ('icon', scorpion_icon)):
    PATCHES.append((f'reptile-{_n}', f"Reptile (the Eternal Champion's second form's slot): as scorpion-{_n}",
                    for_spec(REPTILE, _fn)))

@patch('mk-own-graphics', "MK fighters load and free only their own projectile sheet (Blade's $45 freed a stage's graphic: Slash's bird, Dawson's stage drawn in stripes)")
def mk_own_graphics(ec, sources):
    """Blade's module lists his projectile sheets ($44, $45) for $696C at its +$1A entry, which runs at
    the start and again at a finisher's end. The MK fighters' $44 is their own sheet now (mk_projectile);
    $45 no MK .PL has, so the id meant whatever else was registered as $45 - on Slash's stage, its
    pterodactyl's art: freed at a knockout, the bird was drawn from the screen map (a striped block; any
    MK fighter, loser or winner; tools/dev/stageaudit.py). The list is one entry shorter, as Scorpion's
    (scorpion-ghost-art): its old end a nop."""
    for sp in MK_SPECS:
        name = sp.host + '.CO'
        co = ec.read_file(name)
        if sp is SCORPION:                                     # (his: scorpion-ghost-art)
            continue
        fx = co[0x58:0x5A]
        assert co[0x5A:0x5E] == bytes.fromhex('0045ffff') and co[0x70:0x72] == fx, (name, co[0x58:0x5E].hex())
        ec.patch_file(name, 0x5A, bytes.fromhex('ffff4e71'), expect=bytes.fromhex('0045ffff'))


# MK's walk (MK CD, the fighters' sprite boxes against a still opponent before the screen scrolls:
# Scorpion and Raiden ~1.47 px a frame away, Kano ~1.7; toward 1.875 - MK's world x 2,2,2,2,2,2,2,1).
# Ours was Blade's, 2 px a frame both ways: his walk scripts' header x speed (16.16, 2 units a px a
# frame; EC halves it walking away, PLYR $18126). Every MK module is a copy of Blade's; Shang glides.
WALK_SPEEDS = ((0x3FE4, 0x80000, 0x60000),      # walk away: 1.5 px a frame
               (0x4040, 0x40000, 0x3C000))      # walk toward: 1.875


@patch('mk-walk', "MK fighters walk at MK's pace: 1.875 px a frame toward, 1.5 away (EC's 2 both ways)")
def mk_walk(ec, sources):
    for sp in MK_SPECS:
        if sp is SHANG:                          # (his glide: mkinputs.GLIDE_SPEED)
            continue
        use(sp)
        try:
            for head, old, new in WALK_SPEEDS:
                ec.patch_file(host('CO'), head + 4, new.to_bytes(4, 'big'), expect=old.to_bytes(4, 'big'))
        finally:
            use(SCORPION)


GAME_HOME_STAGES = 0xC28             # GAME.CO: each slot's home stage (stage mode)


@patch('mk-pit-home', "Every MK fighter's home stage is MK's Pit (they had their EC hosts': Chin Wo's, Zuni's circus ...)")
def mk_pit_home(ec, sources):
    """GAME.CO's stage-by-slot table: the Pit for every MK fighter (Scorpion's and
    Sub-Zero's were already its stage, the Senator's); not Shang (his boss match's
    arena) nor Reptile (reptile-secret)."""
    g = ec.read_file('GAME.CO')
    for sp in MK_SPECS:
        if getattr(sp, 'boss', False):
            continue
        o = GAME_HOME_STAGES + 2 * (sp.host_id - 2)
        ec.patch_file('GAME.CO', o, PIT_MODE.to_bytes(2, 'big'), expect=g[o:o + 2])


REPTILE_SLOT = 26 - 2                # his ladder / select slot (id - 2)
GAME_MATCH_END = 0x149B6 - 0x14000   # GAME.CO: after a match, cmpi.w #7,$1438(a6) (the stats' counts)
PIT_CARD = 0xB2E5                     # SUB.BIN (RAM): the Pit's (the Senator's mode's) stage card
PIT_CARD_ENTRY = 0xB104               # its entry in the stage cards' table ($B0CC, by mode - $11)
PIT_CARD_TEXT = bytes([11, 16, 12]) + b'THE PIT\0' + bytes([15, 14]) + b'\0'   # (skip to line 2, x, y, text; x, y, text)
GAME_VERSUS = 0x14938 - 0x14000      # GAME.CO: the match loop's versus screen (42 bytes)
CONTEST_POOL = 0x148F2 - 0x14000     # GAME.CO: ori.l #mask,d0 (the Contest's opponents: a bit per slot)


@patch('reptile-secret', "Reptile's secret Contest match: a flawless fatality on the Pit brings him next (MK's)")
def reptile_secret(ec, sources):
    """MK CD (tools/capture/mkreptileref.py): won on the Pit with both rounds, a fatality
    and (MK) no hit taken, the next fight is Reptile's. Here: a Contest match
    ($1438 = 7) on the Pit (stage $AB2 = PIT_MODE), won 2-0 (player 2's rounds
    $1D28 = 0), finished with an MK fatality ($1CD4 = 3), player 1 at full health
    (104): his slot goes into the ladder ($1BBA, slot words to a -1) after the
    current match ($1C04: advanced after the win, $14C8C), once. GAME's
    match-end compare becomes a jsr to this (appended to GAME.CO), which ends
    with the compare it replaced. His own match: his home stage, the Pit."""
    import mkinputs
    game = ec.read_file('GAME.CO')
    at = (len(game) + 1) & ~1
    a = mkinputs.Asm(0x14000 + at)
    a.w(0x48E7, 0xC0C0)                  # movem.l d0-d1/a0-a1,-(sp)
    a.w(0x0C6E, 0x0007, 0x1438)          # cmpi.w #7,$1438(a6)     the Contest
    a.bcc(0x66, 'rs_out')
    a.w(0x0C6E, PIT_MODE, 0x0AB2)        # cmpi.w #pit,$AB2(a6)    on the Pit
    a.bcc(0x66, 'rs_out')
    a.w(0x0C6E, 0x0003, 0x1CD4)          # cmpi.w #3,$1CD4(a6)     an MK fatality
    a.bcc(0x66, 'rs_out')
    a.w(0x0C6E, 104, 0xE1FE)             # cmpi.w #104,-$1E02(a6)  player 1 untouched
    a.bcc(0x66, 'rs_out')
    a.w(0x4A6E, 0x1D28)                  # tst.w $1D28(a6)         no round lost
    a.bcc(0x66, 'rs_out')
    a.w(0x41EE, 0x1BBA)                  # lea $1BBA(a6),a0        the ladder
    a.w(0x302E, 0x1C04)                  # move.w $1C04(a6),d0     this match
    a.w(0xD040)                          # add.w d0,d0
    a.w(0x41F0, 0x0002)                  # lea 2(a0,d0.w),a0       the next
    a.w(0x0C50, REPTILE_SLOT)            # cmpi.w #slot,(a0)       (once)
    a.bcc(0x67, 'rs_out')
    a.w(0x2248)                          # movea.l a0,a1
    a.label('rs_end')
    a.w(0x4A59)                          # tst.w (a1)+             to past the -1
    a.bcc(0x6A, 'rs_end')
    a.w(0x5589)                          # subq.l #2,a1
    a.label('rs_mv')
    a.w(0x3351, 0x0002)                  # move.w (a1),2(a1)       the rest one on
    a.w(0xB3C8)                          # cmpa.l a0,a1
    a.bcc(0x67, 'rs_put')
    a.w(0x5589)                          # subq.l #2,a1
    a.bcc(0x60, 'rs_mv')
    a.label('rs_put')
    a.w(0x30BC, REPTILE_SLOT)            # move.w #slot,(a0)
    a.label('rs_out')
    a.w(0x4CDF, 0x0303)                  # movem.l (sp)+,d0-d1/a0-a1
    a.w(0x0C6E, 0x0007, 0x1438)          # cmpi.w #7,$1438(a6)     (the compare replaced)
    a.w(0x4E75)
    # MK goes straight into his fight: no versus screen. The match loop's versus block
    # (GAME $14938-$14961: mode 2, run, fade) becomes a call to the same block, skipped
    # when the next opponent is his slot
    vs = game[GAME_VERSUS:GAME_VERSUS + 42]
    assert vs == bytes.fromhex('08ee0000143b3d7c0016143670024eb900006c8c4eb900006ca4'
                               '3d7c00018002303c000a4eb900006c44'), vs.hex()
    # nor a stage card: the Pit's card ("WASHINGTON DC / 1995 A.D.", the Senator's: SUB
    # $B2E5, 29 bytes, its entry in the cards' table at $B104) becomes "THE PIT" and, after
    # it, an empty card (the routine runs as ever: its waits and fades - skipping it froze
    # the fight's start); before each match his slot's points the entry at the empty one
    a.label('rs_vs')
    a.out += vs[:12]                     # bset #0,$143B(a6) ; move.w #$16,$1436(a6)
    a.w(0x0C6E, REPTILE_SLOT, 0x142A)    # cmpi.w #slot,$142A(a6)   his match?
    a.bcc(0x67, 'rs_his')
    a.w(0x23FC); a.l(PIT_CARD); a.l(PIT_CARD_ENTRY)          # move.l #card,entry
    a.out += vs[12:]                     # the versus screen, run, faded
    a.w(0x4E75)
    a.label('rs_his')
    a.w(0x23FC); a.l(PIT_CARD + len(PIT_CARD_TEXT)); a.l(PIT_CARD_ENTRY)   # the empty card
    a.w(0x4E75)
    code = a.build()
    ec.replace_file('GAME.CO', game + bytes(at - len(game)) + code)
    ec.patch_file('GAME.CO', GAME_MATCH_END, bytes.fromhex('4eb9') + (0x14000 + at).to_bytes(4, 'big'),
                  expect=bytes.fromhex('0c6e00071438'))
    jump = bytes.fromhex('4eb9') + (0x14000 + at + a.labels['rs_vs']).to_bytes(4, 'big')
    jump += bytes.fromhex('6000') + (42 - len(jump) - 2).to_bytes(2, 'big')     # bra.w past the block
    ec.patch_file('GAME.CO', GAME_VERSUS, jump + bytes(42 - len(jump)), expect=vs)
    sub = ec.read_file('SUB.BIN')
    assert int.from_bytes(sub[PIT_CARD_ENTRY - 0x6000:PIT_CARD_ENTRY - 0x5FFC], 'big') == PIT_CARD
    old = b'\x11\x0d\x0cWASHINGTON DC\x00\x0f\x0e1995 A.D.\x00'
    cards = PIT_CARD_TEXT + bytes.fromhex('030000000000')        # (empty: both lines '')
    assert len(cards) <= len(old)
    ec.patch_file('SUB.BIN', PIT_CARD - 0x6000, cards + bytes(len(old) - len(cards)), expect=old)
    o = GAME_HOME_STAGES + 2 * REPTILE_SLOT
    ec.patch_file('GAME.CO', o, PIT_MODE.to_bytes(2, 'big'), expect=bytes.fromhex('0013'))
    # MK's Pit is one of the one-player game's stages; EC's Contest fights each match on the
    # opponent's home stage, and the Pit's owner (Scorpion, the Senator's slot 20) was never
    # an opponent: he joins the pool (GAME $148F2: ori.l #$482000,d0 - the opponents' mask,
    # a bit per slot; the player's own is left out)
    ec.patch_file('GAME.CO', CONTEST_POOL, bytes.fromhex('00800058') + bytes.fromhex('2000'),
                  expect=bytes.fromhex('008000482000'))
    print(f'        {len(code)} bytes at ${0x14000 + at:X} (GAME.CO)')


STATS_DRAW = 0xD2                    # STATS.CO: its task, set up, about to draw (cmpi.w #$F00,$A3C(a6))
STATS_END = 0x4FC                    # STATS.CO: its task's end (yield, the screen's flags, halt)
REPTILE_LINES = ((11, 10, b'YOU HAVE FOUND ME'), (9, 12, b'NOW PROVE YOURSELF !!'))   # (MK CD's, x y in 8 px)


@patch('reptile-found', "After the qualifying win, MK's words instead of the final statistics: YOU HAVE FOUND ME / NOW PROVE YOURSELF !!")
def reptile_found(ec, sources):
    """MK CD, after the win that brings Reptile (build/shots/reptile/mk_transition.png): "YOU HAVE
    FOUND ME / NOW PROVE YOURSELF !!", then his fight. Ours: EC's final statistics screen
    (STATS.CO, loaded at $34000 after the win scene) draws those two lines instead of the
    statistics when the match qualifies (reptile_secret's test, the same match) and ends as
    it ends. Its task's set-up runs as ever; at STATS_DRAW a jmp to this (appended)."""
    import mkinputs
    st = ec.read_file('STATS.CO')
    assert st[STATS_DRAW:STATS_DRAW + 6] == bytes.fromhex('0c6e0f000a3c')
    assert st[STATS_END:STATS_END + 6] == bytes.fromhex('4eb9000068d0')
    at = (len(st) + 1) & ~1
    a = mkinputs.Asm(0x34000 + at)
    for cmp in (('0c6e', 0x0007, 0x1438), ('0c6e', PIT_MODE, 0x0AB2), ('0c6e', 0x0003, 0x1CD4), ('0c6e', 104, 0xE1FE)):
        a.w(int(cmp[0], 16), cmp[1], cmp[2])
        a.bccw(0x66, 'sf_no')
    a.w(0x4A6E, 0x1D28)                  # tst.w $1D28(a6)      no round lost
    a.bccw(0x66, 'sf_no')
    for k, (x, y, _) in enumerate(REPTILE_LINES):
        a.w(0x3D7C, x, 0xB0E2)           # move.w #x,-$4F1E(a6)
        a.w(0x3D7C, y, 0xB0E4)           # move.w #y,-$4F1C(a6)
        a.jsr(0x6C6E)                    # (the text's place)
        a.pcrel(0x41FA, f'sf_t{k}')      # lea text(pc),a0
        a.jsr(0x6C7A)                    # (the text)
    a.w(0x4EF9); a.l(0x34000 + STATS_END)    # jmp end: as the statistics end
    a.label('sf_no')
    a.w(0x0C6E, 0x0F00, 0x0A3C)          # cmpi.w #$F00,$A3C(a6)  (the compare replaced)
    a.w(0x4EF9); a.l(0x34000 + STATS_DRAW + 6)
    for k, (_, _, text) in enumerate(REPTILE_LINES):
        a.label(f'sf_t{k}')
        a.out += text + b'\0'
        a.out += bytes(len(a.out) % 2)
    code = a.build()
    st = st + bytes(at - len(st)) + code
    st = st[:STATS_DRAW] + bytes.fromhex('4ef9') + (0x34000 + at).to_bytes(4, 'big') + st[STATS_DRAW + 6:]
    ec.replace_file('STATS.CO', st)
    print(f'        {len(code)} bytes at ${0x34000 + at:X} (STATS.CO)')


@patch('move-table-clear', "A fighter's move table is cleared before it is built: no entries left from the slot's last fighter")
def move_table_clear(ec, sources):
    """EC builds a fighter's move table (P1 $31646, P2 $31742: 63 entries) from his
    module's script list (PLYR $1A278) without clearing it, so moves the new
    fighter hasn't got keep the last one's pointers. The Contest's Dark Champion
    kept Shang's $2E/$31/$34/$35/$36, his AI took them for his own moves and ran
    one into the middle of his code: the sub CPU trapped (Johnny's ending run,
    once Shang's morph had changed the fight's timing). In the fighter set-up
    (PLYR $190C6 player 2, $190F4 player 1) the first colour upload ($12BBC: the
    same palette line $1A278 writes again right after) makes way for clearing it."""
    for at, table in ((0x190C6, 0x1742), (0x190F4, 0x1646)):
        old = bytes.fromhex('206d011e6100') + ec.read_file('PLYR.CO')[at - 0x14000 + 6:at - 0x14000 + 8] \
            + bytes.fromhex('41ee') + table.to_bytes(2, 'big') + bytes.fromhex('2b4800a62648')
        new = bytes.fromhex('41ee') + table.to_bytes(2, 'big') + bytes.fromhex('2b4800a62648') \
            + bytes.fromhex('703e429851c8fffc')        # moveq #62,d0 / clr.l (a0)+ / dbra d0,*-2
        assert len(new) == len(old) == 18
        ec.patch_file('PLYR.CO', at - 0x14000, new, expect=old)


THROW_SKIP = ('PLYR.CO', 'GAME.CO', 'STATS.CO', 'CINE.CO', 'CREDITS.CO', 'BACKUP.CO', 'ENDMSG.CO')


def throw_table(co):
    """(offset, entry size, [25 entry offsets]) of a fighter module's throw
    victim table: one entry per victim id 2-26 (relative to the table), each
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
            # (found by its first 23; the table runs to id 26: 25 entries, every module's
            #  checked - ids 25, 26 in step, 26 the second form's sheet $9F, never shared)
            e += [int.from_bytes(co[t + 4 * i:t + 4 * i + 4], 'big', signed=True) for i in (23, 24)]
            assert all(92 <= x <= 0x3000 and (x - e[0]) % g == 0 for x in e[23:]), hex(t)
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
    mk = [(sp.host_id, sp.sheet_base - 0x40, sp.host) for sp in MK_SPECS]
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


# Other per-victim pose tables in EC's specials (found by tools/dev/victimtables.py,
# a scan of every stock module for tables whose entry per victim id 2-24 holds
# frame words in that victim's sheets): (file, offset, bytes per victim, frame
# word offsets in the record).
VICTIM_POSES = (('XAV.CO', 0x39AE, 2, (0,)),           # Xavier's energy grab: the victim's pose
                ('XAV.CO', 0x39FA, 2, (0,)),           #  (and its second one)
                ('SLA.CO', 0x20C6, 2, (0,)),           # Slash
                ('JET.CO', 0x326A, 8, (0, 4)),         # Jetta: two poses (and their dx)
                ('TRI.VC', 0x746, 16, (0, 4, 8, 12)), # Trident's Vendetta: four victim poses
                ('MID.VC', 0xA1E, 66, tuple(range(0, 64, 8))),  # Midknight's Vendetta: eight steps
                ('BLA.VC', 0xB68, 4, (0, 2)),           # Blade's Vendetta: two poses
                                                      #  (frame, dx, dy, flags; $FFFF after)
                ('MID.OC', 0x52AA, 4, (0, 2)),         # Midknight's stage finisher: two poses
                ('BST.CO', 0x20A6, 10, (0, 6)))        # Blast's grab: two poses (his module is his own again)
# MK has no such grab: an MK victim shows a stunned hit pose instead of Blade's (the frames would show
# MK's thrown-through-the-air poses - Sonya in Xavier's snake: butt down, legs up)
VICTIM_POSE_FOR_MK = {('XAV.CO', 0x39AE): (0x4226,), ('XAV.CO', 0x39FA): (0x4224,)}   # MK's hit reaction (hit_plan)
# per-victim records through an offset table, like the throw tables:
# (file, offset, frame word offsets in a record; None = every 10-byte step's)
VICTIM_STEPS = (('MID.CO', 0x293C, None),               # Midknight: 10-byte steps
                ('SLA.CO', 0x2722, (0, 2)))             # Slash: two poses, dx, dy


@patch('mk-victim-poses', "EC's grabs and finishers show an MK victim in his own poses")
def mk_victim_poses(ec, sources):
    """As mk_throw_victims, for the other per-victim tables: the MK fighters'
    ids (their hosts') held the hosts' frames, which an MK .PL hasn't got
    (Xavier's energy grab on Raiden showed Chin Wo's frame 73:67: the fight
    crashed). Each gets the table's entry for Blade (whose poses they keep)
    moved to his own sheets. Entries shared with another fighter (MID.CO:
    Snake's is Trident's) get a copy at the module's end instead."""
    import math
    for name, t, size, frames in VICTIM_POSES:
        b = ec.read_file(name)
        blade = b[t + size * 7:t + size * 8]
        for sp in MK_SPECS:
            if sp.host_id > 24 and not all(0x9D <= b[t + size * (sp.host_id - 2) + w] <= 0xA8 for w in frames):
                continue                     # (no entry for id 26 - the Vendettas': none on an MK loser)
            ent = bytearray(blade)
            mine = VICTIM_POSE_FOR_MK.get((name, t))
            for j, w in enumerate(frames):
                assert 0x40 <= ent[w] <= 0x43, (name, hex(t), blade.hex())
                if mine:
                    ent[w:w + 2] = mine[j].to_bytes(2, 'big')
                ent[w] += sp.sheet_base - 0x40
            o = t + size * (sp.host_id - 2)
            ec.patch_file(name, o, bytes(ent), expect=b[o:o + size])
    for name, t, frames in VICTIM_STEPS:
        co = bytearray(ec.read_file(name))
        e = [int.from_bytes(co[t + 4 * i:t + 4 * i + 4], 'big', signed=True) for i in range(25)]
        u = sorted(set(e[:23]))
        size = 0
        for i in range(len(u) - 1):
            size = math.gcd(size, u[i + 1] - u[i])
        blade = co[t + e[7]:t + e[7] + size]
        for sp in MK_SPECS:
            if sp.host_id > 24:              # (id 26's entry: the second form's poses, checked)
                assert co[t + e[sp.host_id - 2]] == 0x9F, (name, hex(co[t + e[sp.host_id - 2]]))
            ent = bytearray(blade)
            for w in frames or range(0, size, 10):
                assert 0x40 <= ent[w] <= 0x43, (name, hex(t), blade.hex())
                ent[w] += sp.sheet_base - 0x40
            i = sp.host_id - 2
            if e.count(e[i]) > 1:                           # shared: a copy of its own at the end
                end = (len(co) + 1) & ~1
                co += bytes(end - len(co)) + bytes(ent)
                e[i] = end - t
                co[t + 4 * i:t + 4 * i + 4] = e[i].to_bytes(4, 'big', signed=True)
            else:
                co[t + e[i]:t + e[i] + size] = ent
        ec.replace_file(name, bytes(co))


BLA_VC_GRABS = 0x4DC          # BLA.VC: Blade's Vendetta grab, a bra.w per loser id - 2 (after jmp 2(pc,d0))
BLA_VC_SHARED = 0x638         #  the Senator's entry (Scorpion's slot): starts his case ($ABA) as a task (jsr $68B2)
BLA_VC_SHARED_CASE = 0xABA    #  his case: 34 bytes, the loser's frames: the MK fighters' now
BLA_VC_TABLE = 0xA76          #  Chin Wo's case (Raiden's slot, 34 bytes): the MK case's sheet table


@patch('mk-blade-vendetta', "Blade's Vendetta grabs an MK loser in his own pose (it ran data or a host's frames: hang)")
def mk_blade_vendetta(ec, sources):
    """Blade's Vendetta picks its grab by the loser's id: a jump table of
    bra.w (BLA.VC $4DC), each entry starting a case that writes the loser's
    frame word ($1490(a6) -> $1A; Shadow's: 35:88, 35:89; Blade's: 42:3D).
    Ids without a fighter of their own - the hidden animals' - point into data
    ($BC8: ILLEGAL): Liu Kang, Kano, Sonya, Johnny and Sub-Zero hung the game;
    Raiden ran Chin Wo's case (his frames: hang), Scorpion the Senator's (a
    wrong pose). The Senator's case becomes one for all seven: Blade's frame
    3D on sheet 2 of the loser's own, from a byte per id kept in Chin Wo's case
    (both slots are MK fighters'); their entries point at the Senator's."""
    vc = bytearray(ec.read_file('BLA.VC'))
    assert vc[BLA_VC_GRABS - 4:BLA_VC_GRABS - 2] == bytes.fromhex('4efb')      # jmp 2(pc,d0.w)
    assert vc[BLA_VC_SHARED_CASE:BLA_VC_SHARED_CASE + 8] == bytes.fromhex('206e1490317c880a')
    assert vc[BLA_VC_TABLE:BLA_VC_TABLE + 4] == bytes.fromhex('206e1490')
    assert vc[BLA_VC_SHARED:BLA_VC_SHARED + 4] == bytes.fromhex('c18841fa')     # exg d0,a0; lea case(pc),a0
    assert vc[BLA_VC_SHARED + 4:BLA_VC_SHARED + 6] == (BLA_VC_SHARED_CASE - BLA_VC_SHARED - 4).to_bytes(2, 'big')
    blade = 9
    t = BLA_VC_GRABS + 4 * (blade - 2)
    case = t + 2 + int.from_bytes(vc[t + 2:t + 4], 'big', signed=True)          # Blade's entry -> his case
    lea = case + 4 + int.from_bytes(vc[case + 4:case + 6], 'big', signed=True)
    assert vc[lea:lea + 6] == bytes.fromhex('206e1490317c') and vc[lea + 6] == 0x42
    frame = vc[lea + 7]                                                         # (his pose: 42:3D)
    sheet = bytearray(0x42 for _ in range(23))
    vspecs = [sp for sp in MK_SPECS if sp.host_id <= 24]   # (its table stops at id 24: Reptile's 26 has none)
    for sp in vspecs:
        sheet[sp.host_id - 2] = sp.sheet_base + 2
    tbl = BLA_VC_TABLE
    idx = BLA_VC_SHARED_CASE + 8                                                # move.b d8(pc,d0.w)
    code = (bytes.fromhex('206e1490')                         # movea.l $1490(a6),a0   the loser
            + bytes.fromhex('3028004c')                       # move.w $4C(a0),d0      his id
            + bytes.fromhex('103b00') + ((tbl - 2) - (idx + 2)).to_bytes(1, 'big', signed=True)   # move.b tbl-2(pc,d0.w),d0
            + bytes.fromhex('e148')                           # lsl.w #8,d0
            + bytes.fromhex('103c00') + bytes([frame])        # move.b #frame,d0
            + bytes.fromhex('3140001a')                       # move.w d0,$1A(a0)
            + bytes.fromhex('4ef900006a1a'))                  # jmp $6A1A              (as every case)
    assert len(code) == 28 and len(sheet) <= 34
    vc[BLA_VC_SHARED_CASE:BLA_VC_SHARED_CASE + 34] = code.ljust(34, b'\0')
    vc[BLA_VC_TABLE:BLA_VC_TABLE + 34] = bytes(sheet).ljust(34, b'\0')
    for sp in vspecs:
        e = BLA_VC_GRABS + 4 * (sp.host_id - 2)
        assert vc[e:e + 2] == bytes.fromhex('6000')
        vc[e + 2:e + 4] = (BLA_VC_SHARED - e - 2).to_bytes(2, 'big', signed=True)
    ec.replace_file('BLA.VC', bytes(vc))


SENATOR_CHECK = bytes.fromhex('0c6b0016004c')   # cmpi.w #22,$4C(a3): "the opponent is the Senator"
VERSUS_SENATOR = 0x21966 - 0x14000            # GAME.CO: cmpi.w #20,$142A(a6) - his portrait unmirrored
BLAST_IDX = 23 - 2                            # Blast: an EC fighter again (his slot was Scorpion's)


@patch('senator-slot', "Scorpion in the Senator's slot: nobody treats him as the Senator; Blast selectable again")
def senator_slot(ec, sources):
    """The Senator (id 22) is EC's special case in two places:
     - every fighter's throw: `cmpi.w #$16,$4C(a3)` (the opponent) picks
       another reaction move ($3B for $39) and grab record for him (BLA.CO
       $120C, $127C; two in each module, three in Raven's, one in Ramses'):
       never true now (the compare's id becomes $FF), in EC's modules and in
       the MK fighters' copies of Blade's (below their code block: their own
       code compares ids too);
     - the versus screen draws his portrait unmirrored (GAME.CO $21966):
       Scorpion's MK portrait is mirrored as everyone's.
    Blast's bit in the unlock mask is set (as scorpion-roster sets HOST's):
    he is selectable from the start."""
    import mkinputs
    n = 0
    for name in sorted(ec.files()):
        if not name.endswith('.CO') or name in ('PLYR.CO', 'GAME.CO', 'STATS.CO', 'CINE.CO', 'CREDITS.CO',
                                                 'BACKUP.CO', 'ENDMSG.CO', 'SEN.CO'):
            continue
        b = bytearray(ec.read_file(name))
        top = mkinputs.EXT_OFF if name in {sp.host + '.CO' for sp in MK_SPECS} else len(b)
        k = 0
        at = b.find(SENATOR_CHECK, 0, top)
        while at >= 0:
            if at % 2 == 0:
                b[at + 2:at + 4] = b'\x00\xff'
                k += 1
            at = b.find(SENATOR_CHECK, at + 2, top)
        if k:
            ec.patch_file(name, 0, bytes(b))
            n += k
    assert n >= 40, f'{n} Senator checks'
    ec.patch_file('GAME.CO', VERSUS_SENATOR, bytes.fromhex('0c6e00ff142a'), expect=bytes.fromhex('0c6e0014142a'))
    for o in (0xBC6C - 0x6000, 0xBC84 - 0x6000):
        sub = ec.read_file('SUB.BIN')
        assert sub[o:o + 2] == b'\x2d\x7c'
        v = int.from_bytes(sub[o + 2:o + 6], 'big')
        ec.patch_file('SUB.BIN', o + 2, (v | 1 << BLAST_IDX).to_bytes(4, 'big'))
    print(f'        {n} Senator checks off')


@patch('scorpion-no-fx', "Scorpion's module loads only his own effect sheet: the teleport's double ($7C)")
def scorpion_no_fx(ec, sources):
    """His .CO is Blade's module: its init loads resources $44, $45 (BLA.CO
    $52: jsr $696C + list) and sets $19C = $44, the effect sheet PLYR.CO gives
    VRAM at each fight's start ($1493A, $16FE0: none when 0). Scorpion's .PL
    once had neither sheet, so they were whatever another .PL registered last:
    in the one-player Contest, Blade (opponent) registered them in player 2's
    area, the later opponents' .PLs overwrote it, and at match 7 the fight
    start read a junk tile-slot index and hung. Now his .PL keeps Blade's $44
    chunks renumbered $7C (no other file registers $7C) holding the teleport's
    double (scorpion-ghost-art), and the module loads and uses only that."""
    # the list ($696C returns past its $FFFF) one entry shorter: its old end becomes a nop
    # (left as $FFFF it ran as a line-F instruction: a crash whenever $6D28, a finisher's
    # end, calls this init again through the module's +$1A entry)
    ec.patch_file(host('CO'), 0x58, bytes.fromhex('007cffff4e71'), expect=bytes.fromhex('00440045ffff'))
    ec.patch_file(host('CO'), 0x70, bytes.fromhex('007c'), expect=bytes.fromhex('0044'))


ENDING_TABLE = 0x1716             # CREDITS.CO: word offsets (from here) of the ending texts
# the hosts' entries (their slots' byte table at $13A6 picks them) and a name in each text
ENDING_OF = {'SEN': (25, b'Senator'), 'CHW': (17, b'Chin'), 'CHI': (19, b'Cri'), 'DOG': (20, b'Yappy'),
             'SNA': (21, b'Slither'), 'MON': (22, b'Zuni'), 'OWL': (23, b'Hoo')}


@patch('mk-endings', "Winning the Contest with an MK fighter shows his MK ending (MK CD's text, tools/lib/mkendings.py)")
def mk_endings(ec, sources):
    """CREDITS.CO's ending scroller shows the text the winner's slot picks:
    the hosts' (the Senator's, Chin Wo's, Zuni's, the animals'). Each host's record gets
    the MK fighter's ending from MK CD (RJC.PRG: his story page, then the
    column beside his picture), in EC's record format, in place (they're
    shorter)."""
    import os, mkendings
    from inputs import ROOT
    if not os.path.exists(os.path.join(ROOT, 'extracted', 'mk_us', 'RJC.PRG')):
        print('        (no MK CD extracted: EC\'s endings stay)')
        return
    texts = mkendings.endings()
    cr = ec.read_file('CREDITS.CO')
    offs = sorted({int.from_bytes(cr[ENDING_TABLE + 2 * i:ENDING_TABLE + 2 * i + 2], 'big') for i in range(27)})
    for sp in MK_SPECS:
        if getattr(sp, 'boss', False):       # (Shang: nobody plays him)
            continue
        entry, name = ENDING_OF[sp.host]
        at = int.from_bytes(cr[ENDING_TABLE + 2 * entry:ENDING_TABLE + 2 * entry + 2], 'big')
        room = next(o for o in offs if o > at) - at
        o = ENDING_TABLE + at
        assert name in cr[o:o + 80], (sp.host, cr[o:o + 80])
        rec = mkendings.record(texts[sp.key])
        assert len(rec) <= room, f'{sp.key}: ending {len(rec)} bytes, room {room}'
        ec.patch_file('CREDITS.CO', o, rec + bytes(room - len(rec)), expect=cr[o:o + room])


THROW_LIFT = 0.5                  # victim heights in the MK fighters' throws (x Blade's)
THROW_HOLD = 4                    # ticks (2 frames) the victim stays overhead (Blade's 7)
# px further the victim is left at the end (MK: Raiden's and Johnny's
# overhead tosses land him ~155 px behind, the roll throws ~110-120)
THROW_FAR = {'raiden': 35, 'johnny': 35}
# MK's own victim path for a thrower (measured: MK CD's Kano throwing Sub-Zero, docs/notes/2026-11.md
# "MK throws vs ours"): per EC step, the victim's place after it (px ahead of the thrower as he
# faced at the grab, px up) and its ticks (2 frames; mkinputs.THROW_TRACK_TICKS) - held, lifted,
# over his head, down behind him; released at the end, he falls where he is
THROW_TRACK = {'kano': [((30, 0), 6), ((22, 40), 3), ((0, 60), 2), ((-44, 95), 3), ((-101, 78), 4),
                        ((-150, 40), 3), ((-182, 0), 3)],
               # (tools/dev/throwcmp.py track, from MK CD's own throws on Sub-Zero)
               'scorpion': [((-4, 0), 10), ((-6, 14), 2), ((-49, 74), 2), ((-73, 24), 2), ((-89, 20), 2),
                            ((-110, 10), 2), ((-111, 0), 2)],
               'subzero': [((-4, 0), 10), ((-13, 14), 2), ((-49, 74), 2), ((-49, 74), 2), ((-83, 21), 2),
                           ((-99, 15), 2), ((-95, 0), 2)],
               'reptile': [((-4, 0), 10), ((-13, 14), 2), ((-49, 74), 2), ((-49, 74), 2), ((-83, 21), 2),
                           ((-99, 15), 2), ((-95, 0), 2)],      # (Sub-Zero's: MK's ninjas)
               'raiden': [((18, 0), 6), ((-6, 56), 3), ((-35, 92), 3), ((-61, 92), 3), ((-100, 39), 3),
                          ((-132, 25), 3), ((-138, 0), 3)],
               'johnny': [((36, 0), 3), ((9, 44), 3), ((-10, 92), 3), ((-52, 75), 3), ((-98, 45), 3),
                          ((-134, 28), 3), ((-141, 0), 3)],
               'liukang': [((20, 0), 6), ((7, 56), 3), ((-6, 92), 2), ((-35, 92), 3), ((-70, 39), 3),
                           ((-97, 28), 2), ((-108, 0), 3)],
               'sonya': [((6, 0), 10), ((-5, 12), 2), ((-38, 72), 2), ((-29, 72), 2), ((-58, 21), 2),
                         ((-79, 13), 2), ((-95, 0), 2)]}       # (released at the ground: EC's fall from
                                                                #  higher drifts down slowly, lying in the air)
THROW_GRAB_DX = 56                # px: the victim's furthest in front of him while grabbed (Blade's up to 117)


@patch('mk-throw-arc', "The MK fighters' throws lift the victim to MK's height, briefly (MK's roll throw)")
def mk_throw_arc(ec, sources):
    """Blade's throw holds the victim 156 px up (feet) for 14 frames; MK's
    roll throw takes him over ~74 px up, briefly (measured, build/states/mk_2p.state).
    Each victim record (throw_table: 10-byte steps, frame, dx, dy, flags,
    ticks) in the MK fighters' modules: lifts (negative dy) scaled by
    THROW_LIFT, the overhead step (3) held THROW_HOLD ticks. The release and
    the landing are mkinputs' (emit_throwfix)."""
    import mkinputs, throwsim
    bottom = throwsim.bottoms(ec.read_file, ec.files())     # (the victims' art, as built so far)
    for sp in MK_SPECS:
        name = sp.host + '.CO'
        co = bytearray(ec.read_file(name))
        t, size, e = throw_table(co)
        if sp.key in THROW_TRACK:                      # MK's own path: every victim's records rebuilt
            track = THROW_TRACK[sp.key][:-1] + [(THROW_TRACK[sp.key][-1][0], mkinputs.THROW_LAND_TICKS)]
            assert tuple(tk for _, tk in track) == mkinputs.THROW_TRACK_TICKS[sp.mk_dir]
            # no side swap mid-throw (EC's Blade turns round as he throws; MK's thrower
            # follows through facing forward and turns to his victim as it ends)
            for k in range(7):                         # (the swap on the last step: he turns as MK's does)
                o = mkinputs.THROW_LIST_AT + 4 * k + 2
                cw = int.from_bytes(co[o:o + 2], 'big') & ~0xC000
                swap = mkinputs.THROW_SHAPE[sp.mk_dir][1]
                co[o:o + 2] = (cw | (0x8000 if swap and k == 6 else 0)).to_bytes(2, 'big')
            # Blade's two pauses after the release: 42:11 in both (EC's second showed his stance
            # frame between the drive's calls) and as long as he holds his throw (throw_post)
            t1, t2 = mkinputs.throw_post(sp.mk_dir)
            assert co[0x1A6E] == co[0x1A82] == 0x70 and co[0x1A6B] == 0x11 and co[0x1A7F] == 0x01
            co[0x1A6F], co[0x1A83] = t1, t2
            co[0x1A79], co[0x1A7F] = co[0x1A65], 0x11
            for vid in range(2, 27):
                recs, tl = throwsim.lists(bytes(co), vid, mkinputs.THROW_LIST_AT)
                if (recs[5][3], recs[6][3]) == (0x1800, 0):    # (EC turns him upright on step 5: MK's
                    recs[5] = recs[5][:3] + (0,) + recs[5][4:]  #  comes down head first - upright on
                    recs[6] = recs[6][:3] + (0x1800,) + recs[6][4:]   # the last step, for his landing)
                for st, rec in enumerate(throwsim.solve(recs, tl, track, bottom)):
                    o = t + e[vid - 2] + 10 * st
                    co[o:o + 10] = b''.join(v.to_bytes(2, 'big', signed=k in (1, 2)) for k, v in enumerate(rec))
            e = []                                     # (none of the scaling below)
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
        for i, f in enumerate(mkinputs.throw_list(sp.mk_dir)):
            o = lst + 4 * i
            assert 0x40 <= co[o] - (sp.sheet_base - 0x40) <= 0x43, (name, hex(o))
            co[o:o + 2] = bytes([(f >> 8) + sp.sheet_base - 0x40, f & 0xFF])
        ec.patch_file(name, 0, bytes(co))


PIT_STAGE = 'SEN'                 # the Pit's files: the Senator's stage (his slot is Scorpion's): home of Scorpion
                                  # and Sub-Zero (Yappy's slot)
PIT_MODE = 0x1F                   # its stage mode: the Senator's (its init in SUB.BIN becomes the Pit's)
PIT_TEMPLATE, PIT_TEMPLATE_MODE = 'BST', 0x13   # built on Blast's stage (layers, bands, objects): its init,
                                  # patched as the Pit's, is moved (pit_init_move); Blast's own stays stock
PIT_OFFSET = (-32, 0)             # art shift (MK's plane starts 32 px left of the bridge's end)
PIT_FLOOR = 0xCE                  # fighters' floor line (EC's $D8 put them 10 px into the bridge)
PIT_XMAX = 500                    # camera's right limit: where MK's stops (its right statue at screen x ~230)
# The back layer's scroll bands (Blast's stage: plane B band objects by their
# y) re-laid as MK's Pit (measured: tools/lib/vdp.py hscroll over 4 s, camera
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
    """MK's Pit (tools/lib/mkstage.py) as EC's two layers, laid out as MK's planes
    (measured: tools/lib/vdp.py on build/states/mk_pit_raw.state):
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


# The Pit's fall (MK's Pit fatality, build/shots/mk_pit_fatality.mp4): the loser
# falls past the bridge, the stage cuts to the pit (layer 2: the whole of
# MK's pit, tools/lib/mkpitbottom.py) and the camera scrolls down to its floor
# (ecstage.pit_cut). World y = MK's plane y = map y + 88; world x = map x - 32.
# The camera keeps x PIT_CUT_CAM[0] (MK's last screen: map x 280-599), so the
# layer only holds that strip (and the bridge, whose tiles layer 1 has); the
# rest is black. Layer x = world x (the streamer doesn't wrap layer columns).
PIT_CUT_CAM = (248, 544)          # camera x, and y at the pit's floor (map y 456)
PIT_CUT_FLOOR = 734               # world y the loser lands on: the spikes (map y 646)
PIT_REPTILE_FLOOR = 757           # world y Reptile's fight stands on: MK CD's pit-bottom stage has their
                                  # feet at screen line ~217 of 224 (mkreptileref video), 23 px under the
                                  # spikes' line (ours stood at ~194); the camera as MK's (the wall matches)
PIT_CUT_LOSER = (448, 150)        # world x he drifts to (screen x 200); (screen y: unused)
PIT_MAP_Y = 88                    # world y of MK's map row 0
PIT_FULL_TO = 688                 # map rows the tall layer has at full width: all (the camera drifts over the
                                  # top ones; Reptile's fight pans along the bottom, as MK's: +59 tiles)


def pit_tall_layer():
    import os, numpy as np
    from PIL import Image
    from inputs import ROOT
    f = os.path.join(ROOT, 'extracted', 'mk_stages', 'pit_bottom', 'pit_full.png')
    if not os.path.exists(f):
        raise SystemExit('missing the pit: run  python3 tools/prepare.py')
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


@patch('pit-stage', "MK's Pit (bridge, statues, moon and clouds) as an EC stage: the MK fighters' home stage")
def pit_stage(ec, sources):
    """tools/lib/ecstage.py builds the stage's .BG/.BGI from MK's layers in place
    of PIT_STAGE's (the Senator's), on Blast's stage as the template: a copy
    of Blast's init (mode $13) gets:
     - the camera: the Pit is 848 px wide; right limit as MK's (PIT_XMAX),
       start centred;
     - the front layer down to the plane's bottom (y $D7 -> $FF); Blast's
       floor strip object (a narrower parallax layer) never on screen (y
       $4000): its layer holds the pit, scrolled to in the cut (pit_tall_layer);
     - the back layer's bottom band (plane B from y $C8) without its per-line
       scroll routine ($E332) and x mode 8: it slid apart from the rest.
    The layers are then cut to that init, and the init moves to the Pit's
    mode (pit_init_move): Blast's stays as it is."""
    import os, json
    from inputs import ROOT, require
    from disc import Disc
    import ecstage
    d = os.path.join(ROOT, 'extracted', 'mk_stages', 'pit')
    if not os.path.exists(os.path.join(d, 'plane_a.png')):
        raise SystemExit('missing the Pit: run  python3 tools/prepare.py')
    sub = ec.read_file('SUB.BIN')
    work = bytearray(sub)                         # (Blast's init, patched here as the Pit's, then moved)

    def put(off, new, expect):
        assert bytes(work[off:off + len(new)]) == expect, (hex(off), expect.hex())
        work[off:off + len(new)] = new
    inits = ecstage.stage_inits(sub)
    a = inits[PIT_TEMPLATE_MODE] - ecstage.SUB_BASE
    end = min(x for x in inits.values() if x > inits[PIT_TEMPLATE_MODE]) - ecstage.SUB_BASE
    for off, new, old in ecstage.camera_patch(sub, PIT_TEMPLATE, xmax=PIT_XMAX, start_x=PIT_XMAX // 2):
        put(off, new, old)
    n = m = 0
    bands = 0
    for k in range(a, end, 2):
        if sub[k:k + 6] != bytes.fromhex('4eb90000e062'):
            continue
        args = sub[k + 6:k + 16]
        y = int.from_bytes(args[4:6], 'big')
        if args[:2] == b'\x00\x02' and y in PIT_BANDS and args[8:10] != b'\x7f\xff':   # (not the layer itself)
            ny, nh, mode, speed = PIT_BANDS[y]
            put(k + 10, ny.to_bytes(2, 'big'), args[4:6])
            put(k + 14, nh.to_bytes(2, 'big'), args[8:10])
            nk = sub.find(bytes.fromhex('4eb9'), k + 16)
            for j in range(k + 16, nk, 2):
                if sub[j:j + 2] == b'\x11\x7c' and sub[j + 4:j + 6] == b'\x00\x36':
                    put(j + 2, mode.to_bytes(2, 'big'), sub[j + 2:j + 4])
                if sub[j:j + 2] == b'\x31\x7c' and sub[j + 4:j + 6] == b'\x00\x38':
                    put(j + 2, speed.to_bytes(2, 'big'), sub[j + 2:j + 4])
            bands += 1
            continue
        if args == bytes.fromhex('0000 0000 0000 7fff 00d7'.replace(' ', '')):
            put(k + 14, b'\x00\xff', b'\x00\xd7')
            n += 1
        elif args == bytes.fromhex('0000 0000 00d8 7fff 7f27'.replace(' ', '')):
            # Blast's floor strip: its object never on screen (y $4000); its
            # layer (2) holds the pit, which the front object streams in the cut
            put(k + 10, bytes.fromhex('40007fff7f0f'), bytes.fromhex('00d87fff7f27'))
            n += 1
        elif args[:2] == b'\x00\x02' and args[4:6] == b'\x00\xc8':
            for j in range(k + 16, k + 70, 2):
                if sub[j:j + 6] == bytes.fromhex('117c00080036'):
                    put(j + 2, b'\x00\x00', b'\x00\x08')
                if sub[j:j + 8] == bytes.fromhex('217c0000e3320064'):
                    put(j + 2, bytes(4), bytes.fromhex('0000e332'))
                    m += 1
    assert n >= 2 and m and bands == len(PIT_BANDS), ('Blast stage init not as expected', n, m, bands)
    # the floor line: MK's fighters stand up on the walkway, 10 px higher
    k = sub.find(bytes.fromhex('3d7c00d81496'), a, end)
    assert k > 0, 'no floor line in the init'
    put(k + 2, PIT_FLOOR.to_bytes(2, 'big'), b'\x00\xd8')
    front, back = pit_layers()
    cram = json.load(open(os.path.join(d, 'cram.json')))
    stock = Disc(require('ec_us').cue)
    tmpl = dict(sub=bytes(work), bg=stock.read_file(PIT_TEMPLATE + '.BG'),
                bgi=stock.read_file(PIT_TEMPLATE + '.BGI'))
    cut = ecstage.pit_cut(1, 2, *PIT_CUT_CAM, PIT_CUT_FLOOR, *PIT_CUT_LOSER, back=3, rfloor=PIT_REPTILE_FLOOR)
    bg, bgi, rep = ecstage.build(front, back, cram, stage=PIT_TEMPLATE, template=tmpl, offset=PIT_OFFSET,
                                 pit_fall=cut, layer_images={2: pit_tall_layer()},
                                 fixed_extra=ecstage.PIT_BLOOD,
                                 fade={'layers': [3], 'rows': {1: PIT_MAP_Y}},
                                 blank_tile_slots=(0, 1, 2, 3),      # Blast's stage sprites
                                 layer_prio={3: (0, 0, 4096, PIT_MAP_Y - 1)})   # clouds over the moon
    bgi = pit_init_move(ec, bytes(work), bgi)
    ec.replace_file(PIT_STAGE + '.BG', bg)
    ec.replace_file(PIT_STAGE + '.BGI', bgi)
    print(f'        Pit: {rep.get("tiles")} tiles, BG {len(bg)} bytes, BGI {len(bgi)} bytes (mode ${PIT_MODE:X})')


def pit_init_move(ec, work, bgi):
    """Blast's init as patched for the Pit (in work: a copy of SUB.BIN) runs
    as the Pit's mode's: SUB.BIN has no room for it (the Senator's init, whose
    place it takes, is 638 bytes; this one 842 and more once moved), so
    - the head (camera, the stage-file loads - the Pit's own files now -, the
      slot set-up) goes in place of PIT_MODE's init, then jumps to
    - the rest (the layer objects, the bands, the floor...), appended to the
      Pit's stage code (BGI, loaded at $34000 by the head, resident all fight).
    Moving it: its bsr.w into SUB.BIN become jsr.l, bra.w $6D8C a jmp.l; its
    one branch out of the head (bit 5 of $AB7: files already in, skip the
    loads) a beq.s over a jmp.l to the rest."""
    import capstone, ecstage
    md = capstone.Cs(capstone.CS_ARCH_M68K, capstone.CS_MODE_BIG_ENDIAN | capstone.CS_MODE_M68K_000)
    B = ecstage.SUB_BASE
    names = ecstage.file_list(work)
    fid = {n: names.index(n) for n in (PIT_TEMPLATE + '.BG', PIT_TEMPLATE + '.BGI', PIT_STAGE + '.BG', PIT_STAGE + '.BGI')}
    inits = ecstage.stage_inits(work)
    pc = inits[PIT_TEMPLATE_MODE]
    ins = []                                      # (address, bytes, mnemonic text)
    while True:
        i = next(md.disasm(work[pc - B:pc - B + 10], pc, 1))
        t = f'{i.mnemonic} {i.op_str}'
        n = i.size
        if t == 'jsr $e00e.l':
            n += 8
        elif t == 'jsr $e062.l':
            n += 10
        elif t == 'jsr $f4ba.l':
            k = pc + n
            while int.from_bytes(work[k - B:k - B + 2], 'big') != 0xFFFF:
                k += 2
            n = k + 2 - pc
        assert '(pc' not in i.op_str, t
        ins.append((pc, bytes(work[pc - B:pc - B + n]), t))
        if t == 'bra.w $6d8c':
            break
        pc += n
        assert pc - inits[PIT_TEMPLATE_MODE] < 0x600
    split = next(k for k, (_, _, t) in enumerate(ins) if t == 'jsr $c0fa.l') + 1     # head: through the slot set-up
    rest_at = (len(bgi) + 1) & ~1
    rest_org = ecstage.BGI_BASE + rest_at

    def move(part, internal):
        out = bytearray()
        for adr, raw, t in part:
            m = t.split()
            if m[0] == 'bsr.w':
                out += bytes.fromhex('4eb9') + int(m[1][1:], 16).to_bytes(4, 'big')
            elif t == 'bra.w $6d8c':
                out += bytes.fromhex('4ef900006d8c')
            elif m[0] == 'bne.w':                 # (the skip of the loads: to the rest's start)
                assert int(m[1][1:], 16) == ins[split][0], t
                out += bytes.fromhex('6706') + bytes.fromhex('4ef9') + rest_org.to_bytes(4, 'big')
            elif m[0][0] == 'b' and m[0][1:3] in ('ra', 'eq', 'ne', 'mi', 'pl', 'gt', 'lt', 'ge', 'le', 'cc', 'cs', 'hi', 'ls', 'sr'):
                raise AssertionError(f'branch in the moved init: {t}')
            elif t.startswith('move.w #$') and t.endswith(', d0') and int(t.split('#$')[1].split(',')[0], 16) in (
                    fid[PIT_TEMPLATE + '.BG'], fid[PIT_TEMPLATE + '.BGI']):
                old = int(t.split('#$')[1].split(',')[0], 16)
                new = fid[PIT_STAGE + '.BG'] if old == fid[PIT_TEMPLATE + '.BG'] else fid[PIT_STAGE + '.BGI']
                out += raw[:2] + new.to_bytes(2, 'big')
            else:
                out += raw
        return bytes(out)
    head = move(ins[:split], False) + bytes.fromhex('4ef9') + rest_org.to_bytes(4, 'big')
    rest = move(ins[split:], True)
    at = inits[PIT_MODE] - B
    room = min(x for x in inits.values() if x > inits[PIT_MODE]) - inits[PIT_MODE]
    assert len(head) <= room, f'the Pit init head: {len(head)} bytes, room {room}'
    ec.patch_file('SUB.BIN', at, head)
    bgi = bgi + bytes(rest_at - len(bgi)) + rest
    assert len(bgi) <= ecstage.BG_BASE - ecstage.BGI_BASE, f'the Pit BGI {len(bgi)} bytes runs into its BG'
    print(f'        its init: {len(head)} bytes in mode ${PIT_MODE:X}\'s place, {len(rest)} in its BGI (${rest_org:X})')
    return bgi


SHANG_IDS = (11, 26)                # the Eternal Champion's two forms: ECH.PL (CHA.CO), ECX.PL (ECX.CO)
SHANG_NAME = b'SHANG TSUNG'
SHANG_WIN = ((0xCB0A, b'   ETERNAL', b'     SHANG'), (0xCBB0, b'   ETERNAL', b'     SHANG'))
SHANG_FADES = (0x35F0, 0x360A, 0x3624, 0x363E)   # CHA.CO: his glow's fade steps (entries 1-13, $69FC)


# (not in the build: Shang's art on the Eternal Champion's code fights like EC's boss -
# his hops, his orbs, his colours squeezed into 9 - not like MK's Shang. Kept for
# its findings; Shang is his own fighter now (SHANG): docs/notes/2026-11.md, 'Shang Tsung'.)
def shang_tsung(ec, sources):
    """tools/lib/mkshang.py redraws both of the Eternal Champion's art files with
    Shang's MK poses (each pose: the Shang pose of its kind); his code, moves,
    AI and the arena's boss sequence are EC's. His colours: entries 1-8 and
    11 of every palette in his modules (player 2's line: his own, alternates,
    one per special, and the glow's fade steps).
    Names: the health bar, versus and stats tables (SUB $5970, GAME $DB1C,
    STATS $6B4, by id - 2: both forms) and the win message field."""
    import mkshang
    words = None
    for name in ('ECH.PL', 'ECX.PL'):
        data, words, rep = mkshang.build(name, ec.read_file(name))
        ec.replace_file(name, data)
        print(f'        {name}: {rep["poses"]} Shang poses, {rep["bytes"]} bytes of art, file {rep["size"]}')
    n = 0
    for name in ('CHA.CO', 'ECX.CO'):
        b = bytearray(ec.read_file(name))
        starts = [o + 2 for o in range(0, len(b) - 32, 2)          # every palette: entries 9, 10 = blood
                  if b[o + 18:o + 22] == bytes.fromhex('000e00ee')
                  and all(not int.from_bytes(b[o + 2 * i:o + 2 * i + 2], 'big') & 0xF111 for i in range(16))]
        if name == 'CHA.CO':
            starts += SHANG_FADES
        for at in starts:                             # at: entry 1
            for k, w in zip(mkshang.OWN, words):
                b[at + 2 * (k - 1):at + 2 * k] = w.to_bytes(2, 'big')
        n += len(starts)
        ec.patch_file(name, 0, bytes(b))
    assert n == 34, ('Eternal\'s palettes', n)
    print(f'        his colours set in {n} palettes')
    for at, old, text in SHANG_WIN:
        ec.patch_file('SUB.BIN', at, text, expect=old)

    def repoint(name, base, table, text):
        b = ec.read_file(name)
        at = (len(b) + 1) & ~1
        b = bytearray(b + bytes(at - len(b)) + text)
        for fid in SHANG_IDS:
            o = table + 4 * (fid - 2)
            b[o:o + 4] = (base + at).to_bytes(4, 'big')
        ec.replace_file(name, bytes(b))
    # SUB.BIN is full: the HUD's name goes over 'ETERNAL\0CRISPY\0' (Crispy's
    # entry is Liu Kang's, moved by his name patch)
    sub = ec.read_file('SUB.BIN')
    at = 0xBA14 - 0x6000
    assert sub[at:at + 15] == b'ETERNAL\0CRISPY\0'
    ptrs = [int.from_bytes(sub[0x5970 + 4 * i:0x5974 + 4 * i], 'big') for i in range(25)]
    assert 0xBA1C not in ptrs, 'Crispy\'s name still in use'
    ec.patch_file('SUB.BIN', at, SHANG_NAME + b'\0', expect=sub[at:at + len(SHANG_NAME) + 1])
    for fid in SHANG_IDS:
        ec.patch_file('SUB.BIN', 0x5970 + 4 * (fid - 2), (0xBA14).to_bytes(4, 'big'))
    repoint('GAME.CO', 0x14000, 0xDB1C, b'\x00' + SHANG_NAME + b'\0')
    repoint('STATS.CO', 0x34000, 0x6B4, SHANG_NAME + b'\0')


LAIR_STAGE, LAIR_MODE = 'EC', 0x12  # Goro's Lair in place of the Eternal Champion's arena (only his fight uses it;
                                  # the Dark Champion's is DEC, mode $11)
LAIR_INIT = 0x791A                # its init in SUB.BIN (stock)
LAIR_XMAX, LAIR_START_X = 480, 160   # camera: MK's right limit and start (measured: tools/lib/vdp.py hscroll)
LAIR_BACK_SPEED = 0x300           # the arches (plane B) scroll 3/4 of the camera, as MK's ...
LAIR_BACK_SHIFT = 40              # ... 40 px ahead (MK's plane B x = 40 + 3/4 camera x)


# (not in the build: replacing EC.BGI loses the arena's code, which stages the
# boss fight - the spirit show between Shang's two forms never ran and the
# fight stood still; docs/notes/2026-11.md. To return as art over the kept code.)
def lair_stage(ec, sources):
    """tools/lib/mklair_disc.py decodes MK's Lair (BACKGD6.BIN) into MK's planes;
    tools/lib/ecstage.py builds EC.BG/EC.BGI from them on the arena's own init
    (mode $12, kept in SUB.BIN): its one front layer takes plane A (800 px of
    wall, 1024 of floor); its five back bands take plane B, all scrolling
    3/4 of the camera (the stock bands barely move: EC's arena sky) at x
    mode 4 (x = (camera - origin) * speed / 1024, SUB $E4CE). Camera limit
    and start as MK's. The arena's stage objects (its BGI's) go: the
    generated BGI keeps their descriptors, empty."""
    import os, json
    import numpy as np
    from PIL import Image
    from inputs import ROOT, require
    from disc import Disc
    import ecstage
    d = os.path.join(ROOT, 'extracted', 'mk_stages', 'lair')
    if not os.path.exists(os.path.join(d, 'plane_a.png')):
        raise SystemExit('missing the Lair: run  .venv/bin/python tools/prepare.py')
    sub = ec.read_file('SUB.BIN')
    assert ecstage.stage_inits(sub)[LAIR_MODE] == LAIR_INIT
    a = LAIR_INIT - ecstage.SUB_BASE
    # (ecstage.camera_patch walks every mode's init: the Pit's moved one stops it)
    assert sub[a:a + 6] == bytes.fromhex('4eb90000e00e')
    ec.patch_file('SUB.BIN', a + 10, LAIR_XMAX.to_bytes(2, 'big'), expect=b'\x02\x80')
    k = sub.find(bytes.fromhex('3d7c0144b070'), a, a + 0x300)        # move.w #$144,-$4F90(a6): start x
    assert k > 0
    ec.patch_file('SUB.BIN', k + 2, LAIR_START_X.to_bytes(2, 'big'), expect=b'\x01\x44')
    n = 0
    for k in range(a, a + 0x200, 2):              # the back bands: move.b #4,$36(a0); move.w #speed,$38(a0)
        if sub[k:k + 6] == bytes.fromhex('117c00040036') and sub[k + 6:k + 8] == b'\x31\x7c' \
                and sub[k + 10:k + 12] == b'\x00\x38':
            ec.patch_file('SUB.BIN', k + 8, LAIR_BACK_SPEED.to_bytes(2, 'big'), expect=sub[k + 8:k + 10])
            n += 1
    assert n == 5, ('the arena init: back bands', n)
    front = np.array(Image.open(os.path.join(d, 'plane_a.png')))
    back = np.array(Image.open(os.path.join(d, 'plane_b.png')))[:, LAIR_BACK_SHIFT:]
    cram = json.load(open(os.path.join(d, 'cram.json')))
    stock = Disc(require('ec_us').cue)
    tmpl = dict(sub=stock.read_file('SUB.BIN'), bg=stock.read_file(LAIR_STAGE + '.BG'),   # (its layer objects: stock)
                bgi=stock.read_file(LAIR_STAGE + '.BGI'))
    bg, bgi, rep = ecstage.build(front, back, cram, stage=LAIR_STAGE, template=tmpl)
    ec.replace_file(LAIR_STAGE + '.BG', bg)
    ec.replace_file(LAIR_STAGE + '.BGI', bgi)
    print(f'        Lair: {rep.get("tiles")} tiles, BG {len(bg)} bytes, BGI {len(bgi)} bytes (mode ${LAIR_MODE:X})')


@patch('no-cinekill-mk', "No EC Cinekill, stage Sudden Death or Vendetta on an MK loser: they'd show the slot owner's EC body")
def no_cinekill_mk(ec, sources):
    """EC's finishers that show the loser in EC art never pick an MK loser:
    each would draw the slot's EC owner (the Senator's body for Scorpion, ...).
    - Cinekill (video): PLYR.CO $14AA2 (a5 = the victim) `cmpi.w #$18,$76(a5);
      bgt.s no` is its first check (victim at most 24 health).
    - Stage Sudden Death (the Chicago Theater's usher, ...: they load the
      loser's Z<xx>.BIN death art by slot): PLYR.CO $1784C `cmpi.w #$14,$76(a5);
      bgt.w no` (victim at most 20 health) - docs/notes/2026-11.md. Only MK victims
      without death art of their own (mk-death-art) are skipped.
    Both compares become jsrs to routines appended to SUB.BIN that return
    'greater' for an MK victim (SUB's mkrow: his row's id byte is non-zero).
    Stage Overkills (the drive-by) draw the loser's own frames: kept.
    - Vendettas (some load Z<xx>.BIN too): PLYR.CO $15F1B, a byte per loser
      (id - 2), 0 = none on him (EC's gag animals and bosses): 0 for the MK
      fighters' slots."""
    import mkinputs
    sub = ec.read_file('SUB.BIN')
    at = (len(sub) + 1) & ~1
    org = 0x6000 + at
    code = bytearray()

    def bsr_w(target):
        return bytes.fromhex('6100') + ((target - (org + len(code) + 2)) & 0xFFFF).to_bytes(2, 'big')
    # ck: bsr.s mkv ; bne.s gt ; the displaced compare ; rts
    code += bytes.fromhex('6100' '6600' '0c6d00180076' '4e75')   # (branch offsets set below)
    gt = len(code)
    code += bytes.fromhex('44fc0000' '4e75')            # gt: move #0,ccr ('greater': none) ; rts
    mkv = len(code)
    code += bytes.fromhex('48e78080')                    # mkv: movem.l d0/a0,-(sp)
    code += bytes.fromhex('302d004c')                    # move.w $4C(a5),d0
    code += bsr_w(mkinputs.SUB_AT['mkrow'])              # bsr mkrow           a0 = his row
    code += bytes.fromhex('4a10')                        # tst.b (a0)          non-zero: an MK fighter
    code += bytes.fromhex('4cdf0101')                    # movem.l (sp)+,d0/a0 (flags kept)
    code += bytes.fromhex('4e75')
    code[1] = (mkv - 2) & 0xFF                           # bsr.s mkv
    code[3] = (gt - 4) & 0xFF                            # bne.s gt
    assert org + len(code) <= 0x14000, f'SUB.BIN reaches PLYR.CO by {org + len(code) - 0x14000} bytes'
    put_sub(ec, sub + bytes(at - len(sub)) + bytes(code))
    ec.patch_file('PLYR.CO', mkinputs.CINEKILL_SITE - 0x14000,
                  bytes.fromhex('4eb9') + org.to_bytes(4, 'big'), expect=bytes.fromhex('0c6d00180076'))
    # sd: the stage Sudden Death skips only MK victims WITHOUT death art of
    # their own (mk-death-art). In PLYR.CO's gap (SUB.BIN is full):
    # [cmpi.w #id,$4C(a5) ; beq.s gt]... ; cmpi.w #$14,$76(a5) ; rts ; gt: move #0,ccr ; rts
    import mkdeath
    no_art = [i for i in mkinputs.MK_IDS if i not in mkdeath.art_ids()]
    plyr = ec.read_file('PLYR.CO')
    sd_at = (len(plyr) + 1) & ~1
    sd_org = 0x14000 + sd_at
    sd = bytearray()
    for k, fid in enumerate(no_art):
        sd += bytes.fromhex('0c6d') + fid.to_bytes(2, 'big') + bytes.fromhex('004c')
        sd += bytes([0x67, 8 * (len(no_art) - 1 - k) + 8])          # beq.s gt (8 bytes per id, then 8 to gt)
    sd += bytes.fromhex('0c6d00140076' '4e75' '44fc0000' '4e75')
    assert sd_org + len(sd) <= mkinputs.GAP_END, f'PLYR.CO gap overflows by {sd_org + len(sd) - mkinputs.GAP_END}'
    ec.replace_file('PLYR.CO', plyr + bytes(sd_at - len(plyr)) + bytes(sd))
    ec.patch_file('PLYR.CO', SUDDEN_SITE - 0x14000,
                  bytes.fromhex('4eb9') + sd_org.to_bytes(4, 'big'), expect=bytes.fromhex('0c6d00140076'))
    for fid in mkinputs.MK_IDS:
        ec.patch_file('PLYR.CO', VENDETTA_OK - 0x14000 + fid - 2, b'\0')


@patch('mk-death-art', "EC's death art for the MK fighters (stage Sudden Deaths, Vendettas) redrawn from MK: "
                       "headless body, head, lying (tools/lib/mkdeath.py)")
def mk_death_art(ec, sources):
    """EC's stage Sudden Deaths and some Vendettas load the loser's Z<xx>.BIN
    by slot (a table of file ids by loser id - 2 in each of 18 files; the
    Senator's stage code, the Pit's now, had none). Scorpion's and Raiden's slots load their EC
    owners' (ZSN, ZCH): rebuilt with their MK art. Johnny's and Sub-Zero's
    load files shared with Exodus / Raiden: their entries are pointed at files
    of their own (mkdeath.FILES), and the theater usher's per-victim offsets
    (LAR.OC) and Larcen's Vendetta's (LAR.VC) for all of these (Scorpion's
    too) are Blast's: their art is laid out on his file's frames (ZBS)."""
    import mkdeath
    try:
        for who, (tmpl, name, _) in mkdeath.FILES.items():
            data, _ = mkdeath.build(who)
            ec.replace_file(name, data)
            print(f'        {who}: {name}, {len(data)} bytes')
    finally:
        use(SCORPION)
    first = bytes.fromhex('00ec00ed00ee00ef00f000f100f200f300f4')
    own = {mkdeath.spec_of(w).host_id: mkdeath.FILE_IDS[out]           # (fighters whose slot's own Z file
           for w, (tmpl, out, _) in mkdeath.FILES.items() if out != tmpl + '.BIN'}   #  isn't theirs: repointed)
    n = 0
    for name in sorted(ec.files()):
        if not name.endswith(('.BGI', '.OC', '.VC')) or name == 'EC.BGI':
            continue                  # (EC.BGI's match is a window's tile map, $35072: not a death table)
        b = ec.read_file(name)
        at = b.find(first)
        if at < 0:
            continue
        for fid, file_id in own.items():
            o = at + 2 * (fid - 2)
            ec.patch_file(name, o, file_id.to_bytes(2, 'big'), expect=b[o:o + 2])
        n += 1
    assert n == 17, f'{n} per-victim death file tables (EC has 18: the Pit\'s stage code has none, Blast\'s is back)'
    for name, at, size in (('LAR.OC', 0x1058, 10), ('LAR.VC', 0x2EE, 1)):
        b = ec.read_file(name)
        src = b[at + size * (DEATH_LAYOUT_ID - 2):at + size * (DEATH_LAYOUT_ID - 1)]
        for fid in own:
            ec.patch_file(name, at + size * (fid - 2), src)


TRI_SPIN = 0x1A34            # TRI.OC (Trident's stage Sudden Death): per loser (id - 2) a word offset from here to
TRI_LAST = 0x1B82            #  his frames (frame, ticks pairs to $FFFF, looped) / to his last frame
BLADE_ID = 9


@patch('mk-trident-sudden', "Trident's stage Sudden Death plays on MK losers (it froze: their slots had no frames)")
def mk_trident_sudden(ec, sources):
    """Trident's stage Sudden Death plays a loop of the loser's own frames (TRI.OC: offsets by id - 2 at
    TRI_SPIN, his last frame at TRI_LAST). EC's animals, Eternal and his second form (the MK fighters'
    slots but Scorpion's and Raiden's) never lost there: their offsets are 0, the loop ran through the
    table itself, found no end and the game stood still (tools/dev/stageaudit.py). Scorpion's and Raiden's
    are the Senator's and Chin Wo's frames, not theirs. Every MK fighter's art is Blade's layout on his own
    sheets (MK_SHEET_BASE): each gets Blade's entry (his dazed wobble, 41:25 41:26, then 42:26) on them.
    The tables have entries for ids 2-25 only; id 26's word is the first of Shadow's data, moved away."""
    import mkinputs
    b = bytearray(ec.read_file('TRI.OC'))
    W = lambda o: int.from_bytes(b[o:o + 2], 'big')
    def blade(table):
        return table + W(table + 2 * (BLADE_ID - 2))
    seq, n = blade(TRI_SPIN), 0
    while W(seq + 2 * n) != 0xFFFF:
        n += 2
    seq = [W(seq + 2 * k) for k in range(n)]
    last = W(blade(TRI_LAST))
    assert seq[0::2] == [0x4125, 0x4126] and last == 0x4226, (seq, hex(last))
    at = (len(b) + 1) & ~1
    b += bytes(at - len(b))
    # each table has entries for ids 2-25: the word for 26 (Reptile's slot) is the first word of the data
    # after it (Shadow's) - moved to the end, so that word can be his offset
    for table, ends in ((TRI_SPIN, True), (TRI_LAST, False)):
        n = min(W(table + 2 * i) for i in range(24) if W(table + 2 * i)) // 2
        assert n == 24, (hex(table), n)
        first = next(i for i in range(24) if W(table + 2 * i) == 2 * n)   # whose data starts there
        o, data = table + 2 * n, b''
        while True:
            data += b[o:o + 2]
            o += 2
            if not ends or data[-2:] == b'\xff\xff':
                break
        b[table + 2 * first:table + 2 * first + 2] = (len(b) - table).to_bytes(2, 'big')
        b += data
    for fid, base in sorted(mkinputs.MK_SHEET_BASE.items()):
        own = lambda f: (base + (f >> 8) - 0x40) << 8 | f & 0xFF
        frames = b''.join(own(f).to_bytes(2, 'big') + t.to_bytes(2, 'big') for f, t in zip(seq[0::2], seq[1::2]))
        b[TRI_SPIN + 2 * (fid - 2):TRI_SPIN + 2 * (fid - 1)] = (len(b) - TRI_SPIN).to_bytes(2, 'big')
        b += frames + b'\xff\xff'
        b[TRI_LAST + 2 * (fid - 2):TRI_LAST + 2 * (fid - 1)] = (len(b) - TRI_LAST).to_bytes(2, 'big')
        b += own(last).to_bytes(2, 'big')
    assert len(b) - TRI_SPIN < 0x8000
    ec.replace_file('TRI.OC', bytes(b))


DEATH_LAYOUT_ID = 23          # Blast: the MK death files are laid out as his ZBS.BIN (mkdeath.FILES)
SUDDEN_SITE = 0x1784C         # PLYR.CO: the stage Sudden Death's health check
VENDETTA_OK = 0x15F1B         # PLYR.CO: a byte per loser (id - 2): Vendettas allowed on him


@patch('pit-no-shadows', "No fighter shadows on the Pit (MK draws none on the bridge)")
def pit_no_shadows(ec, sources):
    """SUB.BIN spawns each fighter's shadow (object $1D) at $B44A / $B4E2,
    except on stage mode $18: `cmpi.w #$18,$AB2(a6); beq.s skip` just before
    ($B442 / $B4DA). The compare becomes a jsr (same 6 bytes) to a routine
    appended to SUB.BIN that sets Z for the Pit's mode (PIT_MODE) too."""
    sub = ec.read_file('SUB.BIN')
    at = (len(sub) + 1) & ~1
    code = bytes.fromhex('0c6e00180ab2'      # cmpi.w #$18,$AB2(a6)
                         '6706'              # beq.s done
                         f'0c6e00{PIT_MODE:02x}0ab2'      # cmpi.w #mode,$AB2(a6)  the Pit
                         '4e75')             # done: rts (Z = no shadow)
    assert 0x6000 + at + len(code) <= 0x14000, f'SUB.BIN reaches PLYR.CO by {0x6000 + at + len(code) - 0x14000}'
    put_sub(ec, sub + bytes(at - len(sub)) + code)
    for site in (0xB442, 0xB4DA):
        ec.patch_file('SUB.BIN', site - 0x6000, bytes.fromhex('4eb9') + (0x6000 + at).to_bytes(4, 'big'),
                      expect=bytes.fromhex('0c6e00180ab2'))


@patch('mk-stages', "MK CD's Courtyard, Palace Gates, Warrior Shrine, Throne Room and Goro's Lair as EC stages (with MK's music); "
                   "a fight with an MK fighter is on one of MK's six stages at random (tools/lib/mkstages.py)")
def mk_stages(ec, sources):
    import mkstages
    mkstages.patch(ec, sources)


@patch('cd-ai-stack', "Keep the disc transfer from overwriting the interrupt stack during large AI loads")
def cd_ai_stack(ec, sources):
    """EC loads AI at $40800, rounding the disc read up to whole sectors.

    A final sector at $43000 reaches $437FF, where a nested BIOS interrupt
    can be using the loader's stack. Keep the level-4 interrupt masked until that sector
    has been transferred. The existing loader already waits for the same bit
    after the BIOS call; do so before restoring interrupts instead. Preserve
    the BIOS status flags, including carry on an error.
    """
    from mkinputs import Asm

    sub = ec.read_file('SUB.BIN')
    at = (len(sub) + 1) & ~1
    a = Asm(0x6000 + at)
    a.w(0xB5FC); a.l(0x43000)                # cmpa.l #$43000,a2: sector destination
    a.bcc(0x66, 'normal')
    a.w(0x40E7, 0x007C, 0x0700)            # save SR; raise interrupt mask
    a.w(0x303C, 0x008B, 0x4EB8, 0x5F22)   # BIOS CDC read
    a.w(0x40E7)                             # save BIOS status, including carry
    a.bcc(0x65, 'restore')                  # error: return it to the loader
    a.label('wait')
    a.w(0x0838, 0x0007, 0x8004)            # CDC end-of-transfer bit (EDT)
    a.bcc(0x67, 'wait')
    a.label('restore')
    a.w(0x46EF, 0x0002, 0x44DF, 0x548F, 0x4E75)  # restore SR, BIOS CCR, stack; rts
    a.label('normal')
    a.w(0x303C, 0x008B, 0x4EF8, 0x5F22)   # original call, tail-jumped
    code = a.build()
    put_sub(ec, sub + bytes(at - len(sub)) + code)
    ec.patch_file('SUB.BIN', 0x6220 - 0x6000,
                  bytes.fromhex('4eb9') + (0x6000 + at).to_bytes(4, 'big') + bytes.fromhex('4e71'),
                  expect=bytes.fromhex('303c008b4eb85f22'))


JUMP_SCRIPT = 0x44A4               # Blade's move 8 (the jump): header +8 = vy (16.16), -22 in BLA.CO


@patch('mk-jump-height', "MK fighters' straight-up jumps as high as MK's (EC's rose 121 px for every fighter: MK's 81-105; the head left the screen)")
def mk_jump_height(ec, sources):
    """Each MK fighter's own copy of Blade's jump script launches at his MK straight-up
    height (mkinputs.JUMP_VY_UP) and falls as slowly as MK's, as long in the air (mkinputs.jump_up_launch:
    header +8 the launch speed, +12 gravity); forward/back jumps get MK's - higher - from the roll, with
    EC's gravity back."""
    import mkinputs
    for sp in MK_SPECS:
        if sp.host_id not in mkinputs.JUMP_VY_UP:
            continue
        name = sp.host + '.CO'
        co = ec.read_file(name)
        o = JUMP_SCRIPT
        assert co[o:o + 2] == bytes.fromhex('0020') and co[o + 8:o + 12] == bytes.fromhex('ffea0000'), (name, co[o:o + 12].hex())
        assert co[o + 12:o + 16] == round(mkinputs.EC_GRAVITY * 0x10000).to_bytes(4, 'big')
        v, g = mkinputs.jump_up_launch(sp.host_id)
        ec.patch_file(name, o + 8, (-round(v * 0x10000) & 0xFFFFFFFF).to_bytes(4, 'big') + round(g * 0x10000).to_bytes(4, 'big'),
                      expect=bytes.fromhex('ffea000000020000'))


INTRO_CODE = (0x10C, 0x34A)          # Blade's pre-fight taunt in his module (BLA.CO; ecdis.py): reached only
                                     #  from $FA (the first round's start); $34A on is its ending (kept)
INTRO_TICKS = 110                    # its sleeps (2 frames a tick), after the optional 15 at the start
def stance_loop(lo, end, sheet, ticks, first_sleep=True):
    """Code at lo: his stance for ticks ticks (2 frames a tick) - frame sheet:00, no drawing offset ($9A),
    [Blade's optional first sleep: 15 if $7B bit 0 is clear], poses of 5 ticks cycling 00 01 02 01 (his
    standing stance's frames, about MK's pace; the remainder a sleep on the last), then bra.w end.
    EC's sleep keeps neither registers nor the stack: the count is a word in the code (each player's slot
    holds its own copy of the module)."""
    import mkinputs
    n, r = divmod(ticks, 5)
    a = mkinputs.Asm(lo)
    a.labels['end'] = end - lo
    a.w(0x1B7C, sheet, 0x001A)           # move.b #sheet,$1A(a5)
    a.w(0x426D, 0x009A)                  # clr.w $9A(a5)       no drawing offset
    if first_sleep:
        a.w(0x082D, 0x0000, 0x007B)      # btst #0,$7B(a5)
        a.bcc(0x67, 'go')                # beq.s
        a.w(0x700F)                      # moveq #15,d0
        a.jsr(0x68D6)                    # jsr sleep
        a.label('go')
    a.pcrel(0x41FA, 'cnt')               # lea cnt(pc),a0
    a.w(0x30BC, n - 1)                   # move.w #n-1,(a0)
    a.label('loop')
    a.pcrel(0x41FA, 'cnt')               # lea cnt(pc),a0
    a.w(0x3010)                          # move.w (a0),d0
    a.w(0x0240, 0x0003)                  # andi.w #3,d0
    a.w(0x1B7B); at = len(a.out); a.w(0x0000, 0x001B)    # move.b tbl(pc,d0.w),$1B(a5)
    a.w(0x7005)                          # moveq #5,d0
    a.jsr(0x68D6)                        # jsr sleep
    a.pcrel(0x41FA, 'cnt')               # lea cnt(pc),a0
    a.w(0x5350)                          # subq.w #1,(a0)
    a.bcc(0x6A, 'loop')                  # bpl.s loop
    if r:
        a.w(0x7000 | r)                  # moveq #r,d0         (the remainder, on the last pose)
        a.jsr(0x68D6)                    # jsr sleep
    a.bccw(0x60, 'end')                  # bra.w end
    a.label('tbl')
    a.w(0x0001, 0x0201)                  # 00 01 02 01
    a.label('cnt')
    a.w(0)
    code = bytearray(a.build())
    disp = a.labels['tbl'] - at
    assert 0 < disp < 128
    code[at + 1] = disp                  # brief extension word: d0.w index, 8-bit displacement from it
    return bytes(code)


def intro_stance_code(sheet):
    """MK's stance for the taunt's time (EC starts the round's clock when both fighters' intros end - with no
    intro it ran during BEGIN CONTEST), then the taunt's own ending at $34A. The rest of the range is free
    (mkinputs.LOW_OFF)."""
    import mkinputs
    lo, hi = INTRO_CODE
    code = stance_loop(lo, hi, sheet, INTRO_TICKS)
    assert lo + len(code) <= mkinputs.LOW_OFF, hex(lo + len(code))
    return code


@patch('mk-intro-stance', "MK fighters stand in MK's stance before the fight (Blade's pre-fight taunt showed whatever MK poses "
                          "share its frame slots - punches, kicks, the knife - in a flicker)")
def mk_intro_stance(ec, sources):
    """Each MK fighter's copy of Blade's taunt becomes intro_stance_code (its room after it: mkinputs.LOW_OFF)."""
    import os
    from inputs import ROOT
    blade = open(os.path.join(ROOT, 'extracted', 'ec_us', 'BLA.CO'), 'rb').read()
    lo, hi = INTRO_CODE
    assert blade[0xFA:0xFC] == bytes.fromhex('6710') and blade[lo:lo + 4] == bytes.fromhex('1b7c0043'), 'BLA.CO taunt'
    assert blade[hi:hi + 6] == bytes.fromhex('4eb900006a30'), 'BLA.CO taunt end'
    for sp in MK_SPECS:
        name = sp.host + '.CO'
        co = ec.read_file(name)
        assert co[lo:lo + 3] == bytes.fromhex('1b7c00') and co[hi:hi + 6] == blade[hi:hi + 6], name
        ec.patch_file(name, lo, intro_stance_code(sp.sheet_base))


BLOCK_READS = (0x404, 0x176E, 0x18B4)   # BLA.CO: move.w $1626(a6),d0 - EC's attack request (3: Z) read by his
                                        #  air task, standing loop and walk loop (then flags tested, $18B8 $408)
CROUCH_SITE = 0x18F8                    # BLA.CO: his crouch going down: bclr #7,$BE(a5) / bne.b $1906 (crouched)
CROUCH_ATTACK = 0x19AA                  #  ... and his crouched loop's attack start (d1 = the request)
CROUCH_OFF = __import__('mkinputs').JUMP_LOW_END   # in the module's low room, after mkinputs' jump drive
CROUCH_HUMAN = 0x19B0                   #  ... where a human's request becomes its move (addi.w #$D,d1; the CPU's skip it)
CROUCH_IDLE = 0x199E                    #  ... and the loop's 'no request' (bset #7,$BE(a5); end of frame)
CROUCH_READ = 0x1998                    # BLA.CO: his crouched loop's move.w $1626(a6),d1 (then bne)


def block_button_code(org):
    """zf (called in place of each BLOCK_READS read, every frame he stands or walks): the attack request with
    Z (3: Blade's overhead punch, whose script shows his throw frames - a throw with nobody there) turned
    into none. (MK's Block itself - 'away' in his pad while Z is held and the opponent attacks - is
    mkinputs.emit_zblock now, at the start of his input task: here, after EC had read the pad, it never
    blocked.) d0 = request, flags."""
    import mkinputs
    a = mkinputs.Asm(org)
    a.label('zf')
    a.w(0x302E, 0x1626)                  # move.w $1626(a6),d0
    a.w(0x0C40, 0x0003)                  # cmpi.w #3,d0        Z
    a.bcc(0x66, 'z_t')
    a.w(0x7000)                          # moveq #0,d0
    a.label('z_t')
    a.w(0x4A40)                          # tst.w d0
    a.w(0x4E75)                          # rts
    out = a.build()
    assert len(out) <= mkinputs.ZF_SIZE
    return out


STAND_ATTACK = 0x1794                   # BLA.CO: his standing attack's start (move.w d0,$BE(a5): d0 the move as
                                        #  it is - the 'close' moves, $1F + request, are added before it)


HUMAN_SITE = 0x1784                     # BLA.CO: jsr $6ADE (d4 = how far the opponent is, for the 'close' moves): a
                                        #  human's request from his stand or walk loop, d0, just before it starts -
                                        #  the CPU's skip it ($177E: tst.w $12A(a5) / bne $1794)
CLOSE = 0x6ADE                          # sys: that distance
CLOSE_THROW = 0x6AE4                    # sys: the same, $7F if the opponent can't be thrown now (d0 kept)
THROW_START = 0x17138                   # PLYR: a throw's start, past its read of the held direction ($17112, sys $6AFE:
                                        #  away held throws behind - $A4(a5) 1)
SPECIAL_GO = 0x2206                     # BLA.CO: his special moves' start (d0 = the move)
THROW_GO = 0x19F2                       # BLA.CO: his throw, from its 'gosub' of that start (a0) on
CTRL_OFF, CTRL_END = __import__('mkinputs').CTRL_ROOM


def controls_code(org):
    """MK CD's inputs for a human's MK fighter, in mkinputs.CTRL_ROOM of his module. Every routine here is
    called from code only a human's fighter runs, so the CPU's fighter runs what it ran before, instruction
    for instruction (a fight's course turns on the sub CPU's timing: docs/notes/2026-11.md).
    h (in place of HUMAN_SITE's jsr; d0 = his request, any of d1-d4/a0/a3 free; ends in that jsr's routine):
      - up close the high kick (B, 5) is MK CD's throw, whatever direction is held: EC's own test for its
        throw (his walk loop's, $17E0-$17FE: within 8, neither fighter busy) without the direction, then
        EC's throw with 'behind' chosen ($A4 1: MK's throws all go over);
      - MK's back + high kick is the roundhouse and back + low kick the sweep. Holding away, B (5) becomes
        C (6); A (4) starts the sweep (move $13) as a standing attack, at STAND_ATTACK (the loop's return
        address dropped). Started that way its first frames still give way to a special (Sub-Zero's slide:
        back + A + B, a frame or two apart), which EC's crouched attacks don't.
    jat (Johnny's: in place of CROUCH_HUMAN's addi.w #$D,d1 - a human's crouched request, d1, becoming its
    move): MK CD's split punch is down + high kick, so B (5) becomes EC's Z (3: move $10, his split punch),
    and Z itself is no attack (MK's Block, as the others': to the crouched loop's 'no request', $199E).
    org: module offset."""
    import mkinputs
    a = mkinputs.Asm(org)
    a.labels.update(attack=STAND_ATTACK - org, throw=THROW_GO - org, idle=CROUCH_IDLE - org)
    a.label('h')
    a.w(0x0C40, 0x0005)                  # cmpi.w #5,d0        B: the throw, the roundhouse
    a.bcc(0x66, 'h_a')
    a.jsr(CLOSE_THROW)                   # d4 = the distance
    a.w(0x0C44, 0x0008)                  # cmpi.w #8,d4
    a.bcc(0x6E, 'h_b')                   # bgt
    a.w(0x7206)                          # moveq #6,d1
    a.w(0xC22D, 0x011B)                  # and.b $11B(a5),d1   (EC's two flags)
    a.bcc(0x66, 'h_b')
    a.w(0x588F)                          # addq.l #4,sp        (the loop's return address)
    a.w(0x3B7C, 0x0001, 0x00A4)          # move.w #1,$A4(a5)   behind him
    a.w(0x207C); a.l(THROW_START)        # movea.l #start,a0
    a.bccw(0x60, 'throw')                # bra.w $19F2
    a.label('h_b')
    a.bcc(0x61, 'away')
    a.bcc(0x67, 'h_x')
    a.w(0x7006)                          # moveq #6,d0
    a.bcc(0x60, 'h_x')
    a.label('h_a')
    a.w(0x0C40, 0x0004)                  # cmpi.w #4,d0        A: the sweep
    a.bcc(0x66, 'h_x')
    a.bcc(0x61, 'away')
    a.bcc(0x67, 'h_x')
    a.w(0x7013)                          # moveq #$13,d0
    a.w(0x588F)                          # addq.l #4,sp
    a.bccw(0x60, 'attack')               # bra.w $1794
    a.label('h_x')
    a.jmp(CLOSE)                         # jmp $6ADE           (the replaced call)
    a.label('away')                      # Z clear: he holds away (d1 used)
    a.w(0x7202)                          # moveq #2,d1         left = away ...
    a.w(0x082D, 0x0003, 0x0020)          # btst #3,$20(a5)     facing left?
    a.bcc(0x67, 'aw_t')
    a.w(0x7203)                          # moveq #3,d1         ... or right
    a.label('aw_t')
    a.w(0x032E, 0x1629)                  # btst d1,$1629(a6)
    a.w(0x4E75)                          # rts
    a.label('jat')
    a.w(0x0C41, 0x0003)                  # cmpi.w #3,d1        Z: nothing
    a.bcc(0x67, 'j_no')
    a.w(0x0C41, 0x0005)                  # cmpi.w #5,d1        B: the split punch
    a.bcc(0x66, 'j_a')
    a.w(0x7203)                          # moveq #3,d1
    a.label('j_a')
    a.w(0x0641, 0x000D)                  # addi.w #$D,d1       (the replaced instruction)
    a.w(0x4E75)                          # rts
    a.label('j_no')
    a.w(0x588F)                          # addq.l #4,sp
    a.bccw(0x60, 'idle')                 # bra.w $199E
    return a.build(), a.labels


def rings_code(org):
    """At mkinputs.RINGS_AT of Sonya's module, called from her zblock's human-only part (a1 = her, a0 free): her
    energy rings out of the high punch that begins their input (MK CD: high punch, back, a punch - the jab
    shows, then the rings). EC queues the recognised rings while her punch (move 2; up close $21) plays and
    drops them before it ends: her move task is sent to Blade's special dispatcher with them at once (as
    Kano's queued knife, mkinputs r_generic's g_kstart)."""
    import mkinputs
    a = mkinputs.Asm(org)
    a.labels.update(special=SPECIAL_GO - org)
    a.w(0x0C69, 0x0002, 0x00BE)          # cmpi.w #2,$BE(a1)   her high punch ...
    a.bcc(0x67, 'rg_q')
    a.w(0x0C69, 0x0021, 0x00BE)          # cmpi.w #$21,$BE(a1) ... or the close one
    a.bcc(0x66, 'rg_x')
    a.label('rg_q')
    a.w(0x0829, 0x0003, 0x011A)          # btst #3,$11A(a1)    the recogniser has queued a special:
    a.bcc(0x67, 'rg_x')
    a.w(0x2069, 0x0184)                  # movea.l $184(a1),a0 her input task's queue
    a.w(0x0C68, 0x0034, 0x0042)          # cmpi.w #$34,$42(a0) the rings
    a.bcc(0x66, 'rg_x')
    a.w(0x2069, 0x0088)                  # movea.l $88(a1),a0  her move task
    a.w(0x2050)                          # movea.l (a0),a0
    a.pcrel(0x487A, 'rg_s')              # pea rg_s(pc)
    a.w(0x215F, 0x0004)                  # move.l (sp)+,4(a0)  resumes there
    a.w(0x4268, 0x0008)                  # clr.w 8(a0)         at once
    a.label('rg_x')
    a.w(0x4E75)                          # rts
    a.label('rg_s')                      # (her move task: a5 = her)
    a.w(0x7034)                          # moveq #$34,d0
    a.bccw(0x60, 'special')              # bra.w $2206
    return a.build()


def crouch_code(org):
    """MK's crouching attacks at once (EC dropped a press made with down - its standing attack - or while he
    goes down: only a crouched fighter's press counted, 6 frames on). zfw (his stand and walk loops' read, for
    zf): a request made with down held is kept (crq) and none returned, so EC starts his crouch; c_down (in
    place of the crouch-down step's end test): the kept request, or a press now with down still held, starts
    the crouched attack (EC's own path, $19AA: request + $D)."""
    import mkinputs
    a = mkinputs.Asm(org)
    a.labels['zf'] = mkinputs.LOW_OFF - org
    a.labels['attack'] = CROUCH_ATTACK - org
    a.labels['crouched'] = 0x1906 - org
    a.label('zfw')
    a.bccw(0x61, 'zf')                   # bsr zf              d0 = request (Z: none)
    a.w(0x2F08)                          # move.l a0,-(sp)
    a.pcrel(0x41FA, 'crq')               # lea crq(pc),a0
    a.w(0x4250)                          # clr.w (a0)
    a.w(0x4A40)                          # tst.w d0
    a.bcc(0x67, 'w_x')
    a.w(0x082E, 0x0001, 0x1629)          # btst #1,$1629(a6)   down with it?
    a.bcc(0x67, 'w_x')
    a.w(0x3080)                          # move.w d0,(a0)      kept for the crouch
    a.w(0x7000)                          # moveq #0,d0
    a.label('w_x')
    a.w(0x205F)                          # movea.l (sp)+,a0    (flags kept)
    a.w(0x4A40)                          # tst.w d0
    a.w(0x4E75)                          # rts
    a.label('c_down')
    a.w(0x2F08)                          # move.l a0,-(sp)
    a.pcrel(0x41FA, 'crq')               # lea crq(pc),a0
    a.w(0x3210)                          # move.w (a0),d1
    a.w(0x4250)                          # clr.w (a0)
    a.w(0x205F)                          # movea.l (sp)+,a0
    a.w(0x4A41)                          # tst.w d1
    a.bcc(0x66, 'c_go')
    a.bccw(0x61, 'zf')                   # bsr zf              a press while he goes down (Z: none)
    a.w(0x3200)                          # move.w d0,d1
    a.bcc(0x67, 'c_no')
    a.w(0x082E, 0x0001, 0x1629)          # btst #1,$1629(a6)   down still held
    a.bcc(0x67, 'c_no')
    a.label('c_go')
    a.w(0x42AD, 0x005E)                  # clr.l $5E(a5)       (as his crouched start, $190C)
    a.w(0x42AD, 0x0062)                  # clr.l $62(a5)
    a.bccw(0x60, 'attack')               # bra.w $19AA
    a.label('c_no')
    a.w(0x08AD, 0x0007, 0x00BE)          # bclr #7,$BE(a5)     (the replaced test)
    a.bccw(0x66, 'crouched')             # bne.w $1906
    a.jmp(0x68CA)                        # jmp end_frame
    a.label('crq')
    a.w(0)
    a.label('cz')                        # his crouched loop's read: Z is MK's Block there too (crouching:
    a.bccw(0x61, 'zf')                   #  EC's crouch block, down + away, fed while the opponent attacks)
    a.w(0x3200)                          # move.w d0,d1        (flags: the bne after it)
    a.w(0x4E75)                          # rts
    return a.build(), a.labels


VICTORY = ((0x87C, 0xB1A, 153), (0xB40, 0xD38, 125))   # BLA.CO: Blade's two victory dances (the winner's
                                     #  branch at $800 picks one: sys $6918 & 1) - frames between sleeps (153 /
                                     #  125 ticks, then their endings: $B1A; $D38, a task loop - $12(a4) = 4,
                                     #  sys $68DC marks it, $68E2 at $D66 repeats it: two poses 7 ticks each,
                                     #  then 15 more - kept, its poses his stance's), a palette glow and two
                                     #  effects; MK's winner stands in his stance (MK CD)
VICTORY_LOOP_FRAMES = ((0xD44, 0x34, 0), (0xD52, 0x32, 1))   # that task loop's move.b #frame,$1B(a5): frame, his


@patch('mk-victory-stance', "MK fighters stand in their stance when they win a round (MK CD: KANO WINS, FLAWLESS VICTORY - "
                            "his stance; Blade's victory dances showed punches, kicks, the knife)")
def mk_victory_stance(ec, sources):
    """Each dance becomes stance_loop for its time; the rest of its range is free (mkinputs.VROOM)."""
    import mkinputs, os
    from inputs import ROOT
    blade = open(os.path.join(ROOT, 'extracted', 'ec_us', 'BLA.CO'), 'rb').read()
    for (lo, end, ticks), (room, _) in zip(VICTORY, mkinputs.VROOM):
        assert blade[lo:lo + 4] == bytes.fromhex('1b7c0041') and blade[end:end + 6] in (
            bytes.fromhex('4eb900006a82'), bytes.fromhex('397c00040012')), hex(lo)
    for at, was, now in VICTORY_LOOP_FRAMES:
        assert blade[at:at + 6] == bytes.fromhex('1b7c00%02x001b' % was), hex(at)
    for sp in MK_SPECS:
        name = sp.host + '.CO'
        for (lo, end, ticks), (room, _) in zip(VICTORY, mkinputs.VROOM):
            code = stance_loop(lo, end, sp.sheet_base, ticks, first_sleep=False)
            assert lo + len(code) <= room, (hex(lo + len(code)), hex(room))
            ec.patch_file(name, lo, code)
        for at, was, now in VICTORY_LOOP_FRAMES:
            ec.patch_file(name, at + 3, bytes([now]), expect=bytes([was]))


@patch('mk-block-button', "MK fighters' Z is MK's Block: no more Blade's overhead punch (his throw frames: a throw with nobody "
                          "there); held while the opponent attacks it blocks")
def mk_block_button(ec, sources):
    import mkinputs, os
    from inputs import ROOT
    blade = open(os.path.join(ROOT, 'extracted', 'ec_us', 'BLA.CO'), 'rb').read()
    org = mkinputs.LOW_OFF
    code = block_button_code(org)
    assert org + len(code) <= mkinputs.JUMP_LOW_OFF
    for sp in MK_SPECS:
        name = sp.host + '.CO'
        co = ec.read_file(name)
        ec.patch_file(name, org, code)
        cr, lab = crouch_code(CROUCH_OFF)
        assert CROUCH_OFF + len(cr) <= mkinputs.LOW_END
        sheet = lambda i: blade[i - 3:i] == b'\x1b\x7c\x00' and blade[i + 1:i + 3] == b'\x00\x1a'   # (the dead
        assert all(co[i] == blade[i] or sheet(i)                    #  taunt's move.b #sheet,$1A: renumbered)
                   for i in range(CROUCH_OFF, CROUCH_OFF + len(cr))), f'{name}: low room taken'
        ec.patch_file(name, CROUCH_OFF, cr)
        if sp.host_id == mkinputs.SONYA_ID:
            rg = rings_code(mkinputs.RINGS_AT)
            assert mkinputs.RINGS_AT + len(rg) <= mkinputs.JUMP_LOW_OFF
            assert all(co[i] == blade[i] or sheet(i)
                       for i in range(mkinputs.RINGS_AT, mkinputs.RINGS_AT + len(rg))), f'{name}: low room taken'
            ec.patch_file(name, mkinputs.RINGS_AT, rg)
        if sp is not SHANG:              # (his scripts are Blade's own: CTRL_ROOM is live in his module - the CPU's)
            ctl, clab = controls_code(CTRL_OFF)
            assert CTRL_OFF + len(ctl) <= CTRL_END, f'controls_code over its room by {CTRL_OFF + len(ctl) - CTRL_END}'
            assert co[CTRL_OFF - 4:CTRL_OFF] == blade[CTRL_OFF - 4:CTRL_OFF], f'{name}: CTRL_ROOM is not that script'
            ec.patch_file(name, CTRL_OFF, ctl)
            to = CTRL_OFF + clab['h']
            ec.patch_file(name, HUMAN_SITE, bytes.fromhex('6100') + (to - (HUMAN_SITE + 2)).to_bytes(2, 'big', signed=True)
                          + bytes.fromhex('4e71'), expect=bytes.fromhex('4eb900006ade'))
            if sp.host_id == mkinputs.JOHNNY_ID:
                to = CTRL_OFF + clab['jat']
                ec.patch_file(name, CROUCH_HUMAN, bytes.fromhex('6100') + (to - (CROUCH_HUMAN + 2)).to_bytes(2, 'big', signed=True),
                              expect=bytes.fromhex('0641000d'))
        for at in BLOCK_READS:
            to = org if at == 0x404 else CROUCH_OFF + lab['zfw']   # (the air: zf; stand, walk: zfw)
            ec.patch_file(name, at, bytes.fromhex('6100') + (to - (at + 2)).to_bytes(2, 'big', signed=True),
                          expect=bytes.fromhex('302e1626'))
        if sp.host_id != mkinputs.JOHNNY_ID:     # (Johnny's crouched loop reads EC's way: move $10, EC's down + Z, is his
                                                 #  split punch - the CPU's still; a human's Z is dropped by jat)
            to = CROUCH_OFF + lab['cz']
            ec.patch_file(name, CROUCH_READ, bytes.fromhex('6100') + (to - (CROUCH_READ + 2)).to_bytes(2, 'big', signed=True),
                          expect=bytes.fromhex('322e1626'))
        to = CROUCH_OFF + lab['c_down']
        ec.patch_file(name, CROUCH_SITE, bytes.fromhex('6000') + (to - (CROUCH_SITE + 2)).to_bytes(2, 'big', signed=True)
                      + bytes.fromhex('4e714e71'), expect=bytes.fromhex('08ad000700be6606'))


AIR_MOVING = {0x26: 0x455C, 0x27: 0x45D8, 0x29: 0x46B8, 0x2A: 0x4710, 0x2B: 0x478C}   # (not $28: Z, mk_air_block)
AIR_UP_PUNCH = {0x14: 0x4524, 0x15: 0x4594}   # Blade's straight-up X / Y (MK holds the punch to the ground; its
                                             #  straight-up kick goes out, back and falls: EC's kicks as they are)
AIR_Z = {0x16: 0x461C, 0x28: 0x4660}  # Blade's jump Z (straight up, moving): PLYR starts them ($1861E: request + $13 /
                                     #  + $25) - PLYR's gap has no room to filter Z there
                                     # Blade's forward/back jump attacks (BLA.CO script heads: move x4 first)
AIR_HOLD = 0x60                      # ticks: longer than any fall - the landing ends the move


@patch('mk-air-block', "MK fighters' Z in the air is nothing, as MK's Block (Blade's jump Z showed a hit-reaction pose)")
def mk_air_block(ec, sources):
    """Each of Blade's jump-Z scripts in an MK fighter's module: every step his straight-up jump's peak frame
    (41:02: MK's pose, mkinputs.jump_up_plan), a tick, no hit - over in a moment, back in his jump (move 8;
    the roll goes on where it was)."""
    import os
    from inputs import ROOT
    blade = open(os.path.join(ROOT, 'extracted', 'ec_us', 'BLA.CO'), 'rb').read()
    W = lambda b, o: int.from_bytes(b[o:o + 2], 'big')
    for mid, head in AIR_Z.items():
        assert W(blade, head) == 4 * mid, (hex(mid), hex(W(blade, head)))
    for sp in MK_SPECS:
        name = sp.host + '.CO'
        co = bytearray(ec.read_file(name))
        for mid, head in AIR_Z.items():
            o = head + 20
            while W(co, o) >= 0x100:
                assert co[o] - sp.sheet_base in (0, 1, 2, 3), (name, hex(o))
                co[o:o + 12] = (0x4102 - 0x4000 + (sp.sheet_base << 8)).to_bytes(2, 'big') + (1).to_bytes(2, 'big') \
                    + co[o + 4:o + 10] + b'\0\0'
                o += 12
            ec.patch_file(name, head, bytes(co[head:o]))


@patch('mk-air-hold', "MK fighters hold a forward/back jump attack and a straight-up punch until they land, as MK (Blade's ended in "
                      "mid-air and dropped back to the jump pose)")
def mk_air_hold(ec, sources):
    """The strike step (hit data) of each of Blade's moving-jump attacks holds AIR_HOLD ticks: MK shows the
    attack's pose to the ground (Sonya's jump kick: pose 15 for 32 frames, then the landing). And the
    straight-up punches (AIR_UP_PUNCH): MK CD's Kano holds his straight-up punch from the press to the
    landing; Blade's took it back and fell in the jump pose (~6 frames)."""
    import os
    from inputs import ROOT
    blade = open(os.path.join(ROOT, 'extracted', 'ec_us', 'BLA.CO'), 'rb').read()
    W = lambda b, o: int.from_bytes(b[o:o + 2], 'big')
    sites = []
    for mid, head in {**AIR_MOVING, **AIR_UP_PUNCH}.items():
        assert W(blade, head) == 4 * mid, (hex(mid), hex(W(blade, head)))
        o = head + 20
        while W(blade, o) >= 0x100 and W(blade, o + 10) == 0:
            o += 12
        assert W(blade, o) >= 0x100, hex(mid)
        sites.append(o + 2)                  # the strike step's ticks
    for sp in MK_SPECS:
        name = sp.host + '.CO'
        co = ec.read_file(name)
        for at in sites:
            assert 0 < W(co, at) < AIR_HOLD, (name, hex(at))
            ec.patch_file(name, at, AIR_HOLD.to_bytes(2, 'big'))


ATTACK_RECORDS = 0x1A2CC           # PLYR: EC's attack records, 16 bytes, by hit data's low byte n (1 = the first)
BLOCK_RECORDS = 0x1A75C            # PLYR: the same n's blocked hit (its pushback, +A the block sound: $198A4)
RECORD_COUNT = 73                  # (the attack records end where the blocked ones start)
RECORD_SWING = 0x0C                # a record's swing sound (also +8 the hit, +A the block)


@patch('mk-punch-grunt', "MK fighters grunt as they punch, as MK (MALEJUMP; Sonya GIRLJUMP): EC's whoosh "
                         "stays on kicks, the uppercut and EC's fighters")
def mk_punch_grunt(ec, sources):
    """mkscripts.GRUNT_RECORDS: the MK punches' hit data names copies of Blade's records 1 / 2 (attack
    and blocked) with the grunt as the swing. Their n: of the 73, none an EC fighter's, finisher's or
    Vendetta's script names (every script chain after its palette, all modules: 19 20 22 24 25 27 47 49
    51 52 71 72 free) and no code sets (move.w #n,$102 / $78: 0-6, 21, 23, 28, 29, 31, 33, 34, 36, 38,
    40, 45, 48). (80-83 would be past the 73 - the blocked table's 7-10, EC's own blocks - and a
    blocked punch read past its end: Contests froze or stalled.) Sonya's GIRLJUMP: grunt_id."""
    import mkscripts
    girl = grunt_id(SONYA)
    plyr = ec.read_file('PLYR.CO')
    rec = lambda table, n: table - 0x14000 + 16 * (n - 1)
    for src, copies in mkscripts.GRUNT_RECORDS.items():
        for to, sound in zip(copies, (GRUNT, girl)):
            assert 0 < to <= RECORD_COUNT and to not in mkscripts.GRUNT_RECORDS, to
            for table in (ATTACK_RECORDS, BLOCK_RECORDS):
                r = bytearray(plyr[rec(table, src):rec(table, src) + 16])
                if table == ATTACK_RECORDS:
                    r[RECORD_SWING:RECORD_SWING + 2] = sound.to_bytes(2, 'big')
                old = plyr[rec(table, to):rec(table, to) + 16]
                ec.patch_file('PLYR.CO', rec(table, to), bytes(r), expect=old)
    print(f'        records {sorted(c for cs in mkscripts.GRUNT_RECORDS.values() for c in cs)}: '
          f'grunt ${GRUNT:X}, Sonya ${girl:X}')


SELECT_BLINK = ((0xCEEE, 0xE000, 0xA000), (0xCF24, 0xA000, 0xE000),   # GAME.CO: the OPTIONS / EXIT blink tasks
                (0xCF70, 0xE000, 0xA000), (0xCFA6, 0xA000, 0xE000))   #  ($20EE2, $20F6E): their two attributes


@patch('select-menu-highlight', "OPTIONS / EXIT under the select grid light up as soon as the cursor reaches them "
                                "(EC's blink began with 20 frames of the unlit text: it looked as if nothing was chosen)")
def select_menu_highlight(ec, sources):
    """Each blink task draws the text green ($E000), sleeps 20, yellow ($A000), sleeps 20: after the
    menu's own 10-frame pause the first yellow came ~28 frames after the press (the original two-row
    screen does the same). The two attributes swapped: yellow first. Every way out redraws it green."""
    for at, old, new in SELECT_BLINK:
        ec.patch_file('GAME.CO', at, new.to_bytes(2, 'big'), expect=old.to_bytes(2, 'big'))


@patch('throw-finish', "A throw that would win the match leaves the loser on FINISH HIM, as a hit does (every fighter module)")
def throw_finish(ec, sources):
    """A thrown fighter takes the throw's damage in his own module's landing code (mkinputs.THROW_DAMAGE):
    left on 0 or less, it set his health to 0 - the round over, with no FINISH HIM (a throw on the last
    sliver of health skipped it). Its move.w
    #0,$76(a5) calls mkinputs' throwko stub: the hits' after-damage path (clamp, then finish) with the
    thrown fighter as the victim, so an MK winner's deciding throw leaves him on 1, dazed. Its 10 bytes
    (that move, bra.w on) become exg a3,a5; jsr throwko; bra.s on (throwko swaps them back)."""
    import re, mkinputs
    if mkinputs.THROWKO['at'] is None:
        return
    pat = re.compile(re.escape(mkinputs.THROW_DAMAGE) + rb'\x6e.' + re.escape(mkinputs.THROW_ZERO) + rb'\x60\x00(..)', re.S)
    n = 0
    for name in sorted(f for f in ec.files() if f.endswith('.CO')):
        co = ec.read_file(name)
        found = list(pat.finditer(co))
        if not found:
            continue
        assert len(found) == 1, (name, len(found))
        at = found[0].end() - len(mkinputs.THROW_ZERO) - 4          # move.w #0,$76(a5); bra.w on
        on = at + 8 + int.from_bytes(found[0].group(1), 'big', signed=True)
        d8 = on - (at + 10)
        assert -128 <= d8 <= 127 and d8, (name, d8)
        new = bytes.fromhex('C74D4EB9') + mkinputs.THROWKO['at'].to_bytes(4, 'big') + bytes([0x60, d8 & 0xFF])
        ec.patch_file(name, at, new, expect=co[at:at + 10])
        n += 1
    assert n >= 24, f'throw landing found in {n} modules'
    print(f'        {n} fighter modules\' throw landing: FINISH HIM')


@patch('fatality-music', "MK's CD cues: FINISH HIM's track 9; at the fatality track 13 then 10 with MK's flame and scream (disc times)")
def fatality_music(ec, sources):
    """cdaudio.add_mk_jingle appended MK's cues (cdaudio.mk_jingle: FINISH HIM's
    track 9, the fatality music with each fatality's sounds, the Pit's falls) to
    the end of the last track. Their absolute times (LBA + 150 frames of
    lead-in, BCD MMSSFF00 as MSCPLAYT takes it) go after the 'EKMU' tag in
    each MK fighter's code block. Must be the last patch: it needs the data
    track's final size (build.py --32x writes them again after the 32X steps,
    which grow it: cd_times)."""
    cd_times(ec, sources)


def cd_times(ec, sources, first=True):
    """Write the disc times of the cues (fatality_music) for ec's layout as it is. first: in place of
    their zero placeholders; else over the times already there (build.py --32x, after the 32X steps moved the
    audio tracks 40 sectors on)."""
    import os, cdaudio, mkinputs
    from disc import RAW
    if 'mk_us' not in sources:
        return
    parts = cdaudio.mk_jingle(sources['mk_us'].cue)
    appended = sum(cdaudio.jingle_gap(i) + len(p) // RAW for i, p in enumerate(parts)) + cdaudio.JINGLE_TAIL
    lba, seen = 0, set()
    for t in ec.tracks:
        if t.file in seen:
            continue
        seen.add(t.file)
        size = ec.data.index01 + ec.data.length if t.file == ec.data.file else os.path.getsize(t.file) // RAW
        if t.number == cdaudio.JINGLE_TRACK:
            lba += size - appended
            break
        lba += size
    bcd = lambda v: (v // 10) << 4 | v % 10
    times = b''
    for i, p in enumerate(parts):
        lba += cdaudio.jingle_gap(i)
        a = lba + 150
        times += (bcd(a // 4500) << 24 | bcd(a // 75 % 60) << 16 | bcd(a % 75) << 8).to_bytes(4, 'big')
        lba += len(p) // RAW
    blk = times[:12] + times[4 * 13:4 * 19]       # f_time (9), f_time_m / _f (fire), f_time_sz / _jc / _rd / _lk / _sn / _kn
    for sp in MK_SPECS:     # every MK fighter's block plays it
        co = ec.read_file(sp.host + '.CO')
        i = co.index(mkinputs.MUSIC_TAG.to_bytes(4, 'big'))
        ec.patch_file(sp.host + '.CO', i + 4, blk, expect=bytes(len(blk)) if first else None)
    # the Pit's fall (a man's, a woman's): in its stage code, after its tag
    import ecstage
    bgi = ec.read_file(PIT_STAGE + '.BGI')
    j = bgi.find(ecstage.PIT_SOUND_TAG.to_bytes(4, 'big'))
    if j >= 0:
        pit = times[12:4 * 13] + times[4 * 19:4 * 25]     # the falls, the 4 first MK winners, Liu Kang / Kano / Sonya
        ec.patch_file(PIT_STAGE + '.BGI', j + 4, pit, expect=bytes(len(pit)) if first else None)

