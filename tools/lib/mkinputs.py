#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Scorpion's MK behaviour in Eternal Champions: inputs, spear, voice, CPU.

Code layout
-----------
New code lives in an extension block appended to Scorpion's own module,
BLA.CO (EXT_OFF, tagged with MAGIC). A fighter module loads into slot 1
($1B000, player 1) or slot 2 ($21800, player 2) - both in a mirror match - so
small stubs in the shared PLYR.CO (in its free tail $1AE72-$1B000) find the
block by its tag and call routines by offset. With no Scorpion in the fight
the stubs find nothing and just run the instructions they displaced.

Special moves
-------------
EC recognises special moves in PLYR.CO. Per fighter a handler (table $153A0,
indexed by fighter id $4C - 2; Blade = 9 -> $15604) loads a pointer list of
entries that the loop at $15A62 runs every frame:

    entry: word level   (skipped while level > the fighter's $148, inner strength)
           word slot    (byte offset of its progress word in the table at a3)
           word type    (x4 into the jump table at $15A82)
           args...

Types: $00 charge back, forward+button; $04 charge down, up+button; $08 hold
button; $0C QCF+button; $10 QCB+button; $14 half circle; $18 button combo;
$1C forward+button; $20 hold buttons; $24 direction sequence (finishers).
On success d6 = move id and $15AB0 starts it (Blade's projectile = $34).
MK1 uses taps: back, back + LP is the spear. New type $28 "two direction
taps + button" (args dir1, dir2, button mask, move; directions relative to
facing: 4 back, 8 forward, 2 down, 1 up; buttons X $400 Y $200 Z $100 A $40
B $10 C $20). Blade's list ($164AC) becomes MK_MOVES + his finisher entry.

Spear, measured against MK (tools: MK disc, mk_2p.state, back,back+A)
---------------------------------------------------------------------
MK: the spear sticks ~35 frames (victim shakes, bleeds), the yank takes ~16
frames at ~6.4 px/frame, he lands ~42 px in front, dazed ~80 frames.
Here: the spear's hit stays as Blade's (3 damage, reaction $1B - stagger);
repeat contacts while he's reeling do nothing; while Scorpion holds the rope
(frames 42:2E-42:31, ~30 frames) the victim's knock-back is cancelled; on
Scorpion's pull-back frames he's dragged PULL_SPEED px/frame to PULL_GAP
px and dazed (EC's dizzy move $1F). The hit sound becomes MK's voice.

    mkinputs.py      -> the PLYR.CO stubs and Scorpion's extension block, disassembled
                        (from extracted/ec_us; needs capstone)
"""
import math
import os, struct

BASE = 0x14000
END = 0x1AE72                 # PLYR.CO's last byte + 1
GAP_END = 0x1B000
SLOTS = (0x1B000, 0x21800)    # fighter module slots (player 1, player 2)
EXT_OFF = 0x5200              # extension block's offset inside BLA.CO
VROOM = ((0x8C8, 0xB1A), (0xB88, 0xD38))   # room in every MK module after the victory stance loops
                                           #  (patches.mk_victory_stance): Blade's victory dances
LOW_OFF, LOW_END = 0x158, 0x34A  # room in every MK module: Blade's pre-fight taunt (patches.intro_stance_code)
MAGIC = 0x454B5343            # 'EKSC'

HOOK_AT = 0x15A7C             # move.w (a0)+,d0 ; jmp $15A82(pc,d0.w)
HOOK_ORIG = bytes.fromhex('30184efb0002')
BLADE_LIST = 0x164AC
BLADE_FINISHER = 0x16560      # type $24 entry: keep, so EC's finisher input still works
NEXT, SUCCESS = 0x15AAA, 0x15AB0
TYPE = 0x28

BACK, FWD, DOWN, UP = 4, 8, 2, 1
RAIDEN_ID = 19
RTELE_MOVE = 0x31             # Blade's move $31: Raiden's teleport (its original spawn is skipped)
CHORD = 0x4000                # in a move's button word: all these buttons held (not one pressed)
DIR3 = 0x8000                 # in a move's button word: a third tap (DIR3 | direction), not a button
TAP4 = 8                      # ... and a fourth after it: DIR3 | third | fourth << TAP4
BTN1 = 0x8000                 # in a move's first word: a button press (BTN1 | buttons, any of them), not a tap
LP, HP, LK, HK = 0x400, 0x200, 0x40, 0x10   # EC X, Y, A, B as mapped in scorpion_map
BLOCK = 0x100                 # EC Z: MK's Block
PUNCH = LP | HP               # either punch: MK CD's specials and fatalities that name one take both (measured, docs/notes/2026-11.md)

# (dir1, dir2, button, EC move id): Scorpion's MK1 specials
MK_MOVES = [
    (BACK, BACK, PUNCH, 0x34),   # spear: back, back + a punch (Blade's projectile move)
    (DOWN, BACK, PUNCH, 0x35),   # teleport punch: down, back + a punch
]

SPEAR_MOVE = 0x34
# MK's spear pulls only on a hit: missed (or blocked) Scorpion holds the bare throw (MK: no rope, arm out,
# then his stance): emit_spear_miss, the bare throw on its own slot (spear_bare_slot)
SCORPION_ID = 22              # his fighter id: the Senator's slot (patches.HOST); Blade (9) stays EC's
SCORPION_ID_FIXED = SCORPION_ID   # (SCORPION_ID is reassigned while a generic block is assembled)
HANDLERS = 0x153A0            # PLYR.CO special-move handler table, longs by id - 2
HIT_FIRST, HIT_LAST = 0x1A, 0x1D   # hit-reaction states ($1B standing, $1D airborne, ...)
STAGGER = 0x1B
DIZZY = 0x1F                  # EC's dizzy move
VENDETTA_MOVE = 0x3C          # EC's Vendetta move id (every fighter's type $24 entry)
DIZZY_CODE = 0x17C9A          # its start in PLYR.CO (bsr; start anim; move.w #$1F,$BE(a5) ...)
SHEET_SHIFT = 0x45            # Scorpion's art sheets $40-$43 live at $85-$88 (patches.renumber_sheets)


def fr(frame):
    """One of Scorpion's frames (sheet:frame as Blade numbers it) as the game sees it."""
    return frame + (SHEET_SHIFT << 8) if 0x40 <= frame >> 8 <= 0x43 else frame


HOLD_FRAMES = (fr(0x422E), fr(0x4231))  # Scorpion's frames while the rope is stuck in the victim
PULL_GAP = 56                 # px between them when the yank ends (MK ~42 between its narrower sprites; EC bodies overlap below ~55)
KNOCKDOWN = 0x1C
UPPERCUT_FRAMES = (fr(0x4202), fr(0x4204))   # Scorpion's uppercut frames (down + Y)
LAUNCH_VY = 282               # x16 px per call (calls every other frame): peak ~150 px after ~17 calls
LAUNCH_G = 17                 # x16 px per call per call
LAUNCH_DX = 3                 # px per call backwards (~100 px over the flight; MK ~86)
LAUNCH_AT = 0x19870           # fighter hit path after the reaction: move.w $1444(a6),d1 ; move.w $1446(a6),d2
LAUNCH_ORIG = bytes.fromhex('322e1444342e1446')
DAZE_CALLS = 40               # MK daze ~80 frames; the input task runs every other frame
PULL_SPEED = 14               # px per call; the input task runs every other frame -> ~7 px/frame (MK: ~6.4; 6 was too slow for the yank from the spear's full reach to end inside EC's hit stun after the longer hold)
VOICE_ID = None               # his bank's clip 0 = GETOHERE (set by patches.scorpion_inputs: his slot's ids)
FINISH_VOICE = None           # clip 1 = FINISHim
FINISH_VOICE_F = None         # clip 2 = FINISHER: MK says 'FINISH HER' to a woman
SCREAM_M = SCREAM_F = None     # the spear's victim: MALEHURT / GIRLHURT (patches.VOICE_LINES)
FEMALE = (2, 10, 14, 21, 17)  # Shadow, Jetta, Riptide, Raven, Sonya (the owl's slot) (fighter ids, $4C)
FEMALE_MASK = sum(1 << f for f in FEMALE)   # (ids 2-26: one long, bit = id)
SHANG_ID = 11                 # Shang Tsung: the Eternal Champion's slot (patches.SHANG)
SHANG_AIR = 16                # px his opponent's feet are above his: in the air (r_ai)
SHANG_RANGE = 150             # px: closer than this the CPU's Shang stands his ground (MK: ~120 at the start)
P1_AT, P2_AT = 0x2E188, 0x2E330   # the fighters' structures
JOHNNY_ID = 18                # Johnny Cage's slot (Zuni's, patches.JOHNNY host_id)
MK_IDS = (22, 19, 18, 20, 12, 13, 17, 11, 26)   # Scorpion, Raiden, Johnny Cage, Sub-Zero, Liu Kang, Kano, Sonya, Shang Tsung, Reptile ($4C)
REPTILE_ID = 26              # Reptile: the Eternal Champion's second form's slot (patches.REPTILE)
MK_DIR_OF = {26: 'mk_moves_subzero'}   # (Reptile's captures: Sub-Zero's - his spear Scorpion's)
LIUKANG_ID, KANO_ID, SONYA_ID = 12, 13, 17   # the chicken's, the snake's and the owl's slots (CHI, SNA, OWL)
# Shang's morph into his opponent (an MK fighter: his code and art are already in
# memory - MK CD's morph loads from the CD and freezes ~2.5 s). emit_morph /
# emit_morph_subs. The opponent's module is copied into Shang's slot (as a mirror
# match loads it), Shang's own saved in a tail of his .PL (patches.mk_code).
MORPH_MV = 0x67E0             # module offset: Shang's morph vars (16 bytes; CHA.CO is padded to the slot's end)
MORPH_TRAMP = 0x67F0          # module offset: in a morphed copy, a jmp back to Shang's saved controller
MORPH_SIZE = 0x6800           # a module slot
MORPH = {'off': None}         # his .PL's tail offset (patches.mk_code)
MORPH_HOLD = 5                # calls (2 frames) per blend frame
MORPH_DUR = 150               # calls morphed (MK: ~280 frames as Raiden), then back once he stands still
MORPH_CALM = 5                # calls standing, no projectile, before he changes back
MORPH_COOL = 200              # calls after changing back before another morph (after another volley)
MORPH_COOL_ABORT = 60         # calls after a blend he was hit out of
MORPH_LOW = 24                # neither fighter's health below this when he starts
MORPH_FRAME = 0x4038          # his blend frames: 40:38.. (3 per opponent, mkshangmoves 'morph': EMP 22-42)
MORPH_HOLD_MARK = 0xA55A      # at MORPH_MV in a just-morphed copy: r_ai gives him no input (a move
                              # started then would show over the blank in the old colours); his first call clears it
MORPH_BLANK = 0x404D          # an empty frame (patches.mk_code): shown as he swaps. A frame set in $1A reaches
                              # the screen two frames later, new colours one frame later: he goes blank a call
                              # before his colours change, so no frame shows art in the other fighter's colours
MORPH_BLEND = {}              # fighter id -> his 3 blends' place in 'morph' (filled below: MK's EMP order)
# their first art sheet (patches Spec.sheet_base; Blade's $40): his frame
# 42:xx is (base + 2) << 8 | xx
MK_SHEET_BASE = {22: 0x85, 19: 0x72, 18: 0xD9, 20: 0xDD, 12: 0xE1, 13: 0xE5, 17: 0xE9, 11: 0xED, 26: 0xF1}
# MK fighters whose palette has red in the spark colours 12/13 (patches
# Spec.blood): their hits and hurts bleed in their own palette line
BLOOD_IDS = (22, 19, 18, 20, 12, 13, 17, 11, 26)
CINEKILL_SITE = 0x14AA2       # PLYR: cmpi.w #$18,$76(a5); bgt: the Cinekill check (victim at most 24 health)
SPLIT_STRIKE = 2              # his split punch's strike step (0-based; BLA.CO $43B4)
SPLIT_MOVE = 0x10             # EC's down + Z (Blade's script): Johnny's split punch (a human's: down + B, patches.controls_code)

DRAG_SITES = ((0x1504E, 0x188E), (0x15210, 0x186E))   # input tasks P2, P1: lea x(a6),a3 ; tst.w $12A(a1)
AI_SITES = (0x15120, 0x152E0)  # move.w $1D20(a6),$1634(a6): CPU's chosen special (P1, P2)
AI_ORIG = bytes.fromhex('3d6e1d201634')
HIT_SOUND_SITES = ((0x19816, False), (0x19E74, True))   # move.w 8(a1),$1640(a6): fighter / projectile hit
HIT_SOUND_ORIG = bytes.fromhex('3d6900081640')
BLADE_SPECIALS = (0x2C, 0x36)
BLADE_SPECIALS_ALSO = (0x3C, 0x64)   # (BLA.CO $2252/$225A: his other specials, outside the range)
KEEP = {m for *_, m in MK_MOVES}


class Asm:
    """Tiny label-aware assembler: raw words plus short branches."""
    def __init__(self, org):
        self.org, self.out, self.labels, self.fix = org, bytearray(), {}, []

    def w(self, *words):
        for x in words:
            self.out += struct.pack('>H', x & 0xFFFF)

    def l(self, x):
        self.out += struct.pack('>I', x)

    def label(self, name):
        self.labels[name] = len(self.out)

    def bcc(self, op, name):             # op = high byte (0x60 bra, 0x66 bne, 0x67 beq, 0x6D blt, ...)
        self.fix.append((len(self.out), name))
        self.w(op << 8)

    def pcrel(self, opword, name):
        """opword with a (d16,PC) source; displacement fixed up to label name."""
        self.w(opword)
        self.fix16 = getattr(self, 'fix16', [])
        self.fix16.append((len(self.out), name))
        self.w(0)

    def bccw(self, op, name):            # 16-bit displacement branch
        self.w(op << 8)
        self.fix16 = getattr(self, 'fix16', [])
        self.fix16.append((len(self.out), name))
        self.w(0)

    def dbra(self, reg, name):
        self.w(0x51C8 | reg)
        self.fix16 = getattr(self, 'fix16', [])
        self.fix16.append((len(self.out), name))
        self.w(0)

    def wdiff(self, name, base):
        """A data word: label name - label base (fixed in build)."""
        self.fixd = getattr(self, 'fixd', [])
        self.fixd.append((len(self.out), name, base))
        self.w(0)

    def bsr_back(self, name):
        """bsr to an already-placed label: 2 bytes when in reach, else 4."""
        disp = self.labels[name] - (len(self.out) + 2)
        if -128 <= disp <= 127 and disp != 0:
            self.w(0x6100 | (disp & 0xFF))
        else:
            self.w(0x6100, disp & 0xFFFF)

    def jmp(self, addr):
        self.w(0x4EF9)
        self.l(addr)

    def jsr(self, addr):
        self.w(0x4EB9)
        self.l(addr)

    def build(self):
        for at, name, base in getattr(self, 'fixd', []):
            self.out[at:at + 2] = struct.pack('>h', self.labels[name] - self.labels[base])
        for at, name in getattr(self, 'fix16', []):
            disp = self.labels[name] - at          # PC = address of the extension word
            assert -32768 <= disp <= 32767
            self.out[at:at + 2] = struct.pack('>h', disp)
        for at, name in self.fix:
            disp = self.labels[name] - (at + 2)
            assert -128 <= disp <= 127 and disp != 0, (name, disp)
            self.out[at + 1] = disp & 0xFF
        return bytes(self.out)


# ---------------------------------------------------------------- extension routines (BLA.CO)
# Position-independent: only short branches internally, absolute jumps only
# into PLYR.CO / the engine.

def r_taps(a):
    """Type $28 recogniser. a0 = args (dir1, dir2, button, move: dir1 a tap or BTN1 | buttons;
    button a press of any of its buttons, CHORD | buttons all held, DIR3 | a third tap
    (| a fourth << TAP4), or 0), d1 = slot,
    a3 = progress table, a1 = fighter. Progress: high byte step, low byte
    frames since the last step. Exits to NEXT or SUCCESS (d6 = move).
    The first block found runs it for both fighters' lists (stubs' dispatch),
    so every block's copy is the same; EC's recogniser returns before it for
    the CPU's fighter (PLYR $159D0), so only a human's presses come here."""
    a.w(0x3029, 0x0162)                  # move.w $162(a1),d0   new presses
    a.w(0x0240, 0x000F)                  # andi.w #$F,d0        directions only
    a.w(0x0829, 0x0003, 0x0020)          # btst #3,$20(a1)      facing left?
    a.bcc(0x67, 't_nf')
    a.w(0x3C00)                          # move.w d0,d6
    a.w(0x0246, 0x000C)                  # andi.w #$C,d6
    a.bcc(0x67, 't_nf')
    a.w(0x0A40, 0x000C)                  # eori.w #$C,d0        swap left/right
    a.label('t_nf')
    a.w(0x4A33, 0x1000)                  # tst.b (a3,d1.w)      step
    a.bcc(0x66, 't_s1')
    a.w(0x3C10)                          # move.w (a0),d6       the first: a button (BTN1 | buttons) ...
    a.bcc(0x6A, 't_p0')                  # bpl
    a.w(0xCC69, 0x0162)                  # and.w $162(a1),d6    ... pressed? (new presses have no bit 15)
    a.bcc(0x66, 't_st')
    a.label('t_p0')
    a.w(0xB050)                          # cmp.w (a0),d0        ... or a tap
    a.bcc(0x66, 't_next')
    a.label('t_st')
    a.w(0x37BC, 0x0100, 0x1000)          # move.w #$0100,(a3,d1.w)
    a.bcc(0x60, 't_next')
    a.label('t_s1')
    a.w(0x0C33, 0x0001, 0x1000)          # cmpi.b #1,(a3,d1.w)
    a.bcc(0x66, 't_s2')
    a.w(0x4A68, 0x0002)                  # tst.w 2(a0)          no second tap: on to the buttons
    a.bcc(0x67, 't_2')
    a.w(0xB068, 0x0002)                  # cmp.w 2(a0),d0       second tap
    a.bcc(0x66, 't_tick')
    a.label('t_2')
    a.w(0x37BC, 0x0200, 0x1000)          # move.w #$0200,(a3,d1.w)  (button may come with it)
    a.label('t_s2')
    a.w(0x3C28, 0x0004)                  # move.w 4(a0),d6      the button ...
    a.bcc(0x6B, 't_d3')                  # bmi: ... a third tap (DIR3 | direction)
    a.bcc(0x67, 't_ok')                  # beq: ... none (two taps are the move)
    a.w(0x0806, 0x000E)                  # btst #14,d6          ... a chord (CHORD | buttons, all held)
    a.bcc(0x66, 't_ch')
    a.w(0xCC69, 0x0162)                  # and.w $162(a1),d6    button pressed?
    a.bcc(0x67, 't_tick')
    a.bcc(0x60, 't_ok')
    a.label('t_tick')                    # (here, in the middle: in every short branch's reach)
    a.w(0x5233, 0x1001)                  # addq.b #1,1(a3,d1.w)
    a.w(0x0C33, 0x000C, 0x1001)          # cmpi.b #12,1(a3,d1.w)  12-frame window per step
    a.bcc(0x6D, 't_next')
    a.w(0x4273, 0x1000)                  # clr.w (a3,d1.w)
    a.label('t_next')
    a.jmp(NEXT)
    a.label('t_ch')
    a.w(0x0246, 0x0FF0)                  # andi.w #$FF0,d6      the buttons
    a.w(0x3F06)                          # move.w d6,-(sp)
    a.w(0xCC6E, 0x0A3A)                  # and.w $A3A(a6),d6    held (player 1's pad ...
    a.w(0xB3FC); a.l(0x2E188)            # cmpa.l #P1,a1
    a.bcc(0x67, 't_cp')
    a.w(0x3C17)                          # move.w (sp),d6
    a.w(0xCC6E, 0x0A3C)                  # and.w $A3C(a6),d6    ... or player 2's)
    a.label('t_cp')
    a.w(0xBC5F)                          # cmp.w (sp)+,d6       all of them?
    a.bcc(0x66, 't_tick')
    a.label('t_d3')
    a.w(0x0C33, 0x0003, 0x1000)          # cmpi.b #3,(a3,d1.w)  the third tap done: the fourth's turn
    a.bcc(0x66, 't_d3a')
    a.w(0xE04E)                          # lsr.w #8,d6
    a.label('t_d3a')
    a.w(0x0246, 0x000F)                  # andi.w #$F,d6
    a.w(0xBC40)                          # cmp.w d0,d6          (d0: this frame's taps, facing-relative)
    a.bcc(0x66, 't_tick')
    a.w(0x1C28, 0x0004)                  # move.b 4(a0),d6      a third tap with a fourth after it ($8n: TAP4)?
    a.w(0xDC06)                          # add.b d6,d6
    a.bcc(0x64, 't_ok')                  # bcc: a chord, not a tap
    a.bcc(0x67, 't_ok')                  # beq: no fourth
    a.w(0x0C33, 0x0003, 0x1000)          # cmpi.b #3,(a3,d1.w)  that was the fourth
    a.bcc(0x67, 't_ok')
    a.w(0x37BC, 0x0300, 0x1000)          # move.w #$0300,(a3,d1.w)
    a.bcc(0x60, 't_next')
    a.label('t_ok')
    a.w(0x3C28, 0x0006)                  # move.w 6(a0),d6      move id
    a.w(0x4273, 0x1000)                  # clr.w (a3,d1.w)
    a.jmp(SUCCESS)


def r_ai(a, keep=None):
    """d0 = CPU's chosen special; returns d0 filtered: for every MK fighter any of
    Blade's specials other than his own MK ones become 0 (no special). (Blade's
    others need art his copy doesn't have: a CPU Johnny / Sub-Zero / Liu Kang
    picking Blade's $33 hung the game.) The same routine in every MK block: the
    first block found answers, whoever the CPU plays. Uses d0."""
    table = [(SCORPION_ID_FIXED, sorted(KEEP))] + [(fid, sorted({m for *_, m in mv}))
                                                  for fid, mv in sorted(GENERIC_MOVES.items()) if fid != SCORPION_ID_FIXED]
    # Shang Tsung (MK's CPU Shang: stands at range, throws skull volleys, backs off from a
    # jump-in; tools/lib/mkshangref.py): no jump or crouch; while his opponent is in the air he
    # backs away and doesn't throw; on the ground no away (EC's block: MK gave him none)
    # and toward only from beyond SHANG_RANGE; any special the CPU wants is his volley;
    # his punches and kicks are dropped (MK gave him none).
    # (a6 = the game's base; $1628 the pad's directions: 1 up, 2 down, 4 left, 8 right;
    # $1626 the attack button)
    # Shang's morph (emit_morph): still while he blends (his phase, the first byte at his
    # slot's MORPH_MV), and as he swaps (MORPH_HOLD_MARK there in the morphed copy)
    a.w(0x2F08)                          # move.l a0,-(sp)
    a.w(0x41F9); a.l(SLOTS[1] + MORPH_MV)   # lea slot2+mv,a0
    a.w(0xB3FC); a.l(P1_AT)              # cmpa.l #P1,a1
    a.bcc(0x66, 'ai_mv')
    a.w(0x41F9); a.l(SLOTS[0] + MORPH_MV)
    a.label('ai_mv')
    a.w(0x0C50, MORPH_HOLD_MARK)         # cmpi.w #mark,(a0)
    a.bcc(0x67, 'ai_hd')
    a.w(0x0C69, SHANG_ID, 0x004C)        # cmpi.w #id,$4C(a1)
    a.bcc(0x66, 'ai_n0')
    a.w(0x4A10)                          # tst.b (a0)
    a.bcc(0x67, 'ai_n0')
    a.label('ai_hd')
    a.w(0x205F)                          # movea.l (sp)+,a0
    a.w(0x426E, 0x1628)                  # clr.w $1628(a6)      he stands still
    a.w(0x426E, 0x1626)                  # clr.w $1626(a6)
    a.w(0x7000)                          # moveq #0,d0
    a.w(0x4E75)
    a.label('ai_n0')
    a.w(0x205F)                          # movea.l (sp)+,a0
    a.w(0x0C69, SHANG_ID, 0x004C)        # cmpi.w #id,$4C(a1)
    a.bccw(0x66, 'ai_ns')
    a.w(0x48E7, 0x7080)                  # movem.l d1-d3/a0,-(sp)
    a.w(0x026E, 0xFFFC, 0x1628)          # andi.w #~(up|down),$1628(a6)
    a.w(0x41F9); a.l(P1_AT)              # lea P1,a0            his opponent
    a.w(0xB3C8)                          # cmpa.l a0,a1
    a.bcc(0x66, 'ai_op')
    a.w(0x41F9); a.l(P2_AT)              # lea P2,a0
    a.label('ai_op')
    a.w(0x3229, 0x004E)                  # move.w $4E(a1),d1
    a.w(0x9268, 0x004E)                  # sub.w $4E(a0),d1     his x less the opponent's
    a.w(0x7408)                          # moveq #right,d2      away: right...
    a.w(0x4A41)                          # tst.w d1
    a.bcc(0x6E, 'ai_ab')                 # bgt
    a.w(0x7404)                          # moveq #left,d2       ...or left
    a.w(0x4441)                          # neg.w d1             d1 = how far apart
    a.label('ai_ab')
    a.w(0x3629, 0x0052)                  # move.w $52(a1),d3    his feet
    a.w(0x9668, 0x0052)                  # sub.w $52(a0),d3     less the opponent's
    a.w(0x0C43, SHANG_AIR)               # cmpi.w #air,d3
    a.bcc(0x6D, 'ai_gr')                 # blt: on the ground
    a.w(0x026E, 0xFFF3, 0x1628)          # andi.w #~(left|right),$1628(a6)   in the air:
    a.w(0x856E, 0x1628)                  # or.w d2,$1628(a6)    he backs off
    a.w(0x7000)                          # moveq #0,d0          (no volley)
    a.bcc(0x60, 'ai_nb')
    a.label('ai_gr')
    a.w(0x4642)                          # not.w d2
    a.w(0xC56E, 0x1628)                  # and.w d2,$1628(a6)   no away (EC's block)
    a.w(0x0C41, SHANG_RANGE)             # cmpi.w #range,d1
    a.bcc(0x6E, 'ai_far')                # bgt: he may come closer
    a.w(0x026E, 0xFFF3, 0x1628)          # andi.w #~(left|right),$1628(a6)   in range: he stands
    a.label('ai_far')
    a.w(0x4A40)                          # tst.w d0             a special?
    a.bcc(0x67, 'ai_nb')
    a.w(0x7034)                          # moveq #$34,d0        his volley
    a.label('ai_nb')
    a.w(0x426E, 0x1626)                  # clr.w $1626(a6)      no punch or kick
    a.w(0x4CDF, 0x010E)                  # movem.l (sp)+,d1-d3/a0
    a.w(0x4E75)
    a.label('ai_ns')
    for m in BLADE_SPECIALS_ALSO:        # Blade's dispatcher ($2206) has these too: a CPU Sonya chose $64
        a.w(0x0C40, m)                   #  (his charge-up: its effect wrecked both fighters' records and the
        a.bcc(0x67, 'ai_0')              #  emulator crashed) - none
    # (a table walked by a loop: compares per fighter outgrew Sonya's block)
    a.w(0x0C40, BLADE_SPECIALS[0])       # cmpi.w #first,d0
    a.bcc(0x6D, 'ai_r')                  # blt: not one of Blade's specials
    a.w(0x0C40, BLADE_SPECIALS[1])       # cmpi.w #last,d0
    a.bcc(0x6E, 'ai_r')                  # bgt
    a.w(0x48E7, 0x6080)                  # movem.l d1-d2/a0,-(sp)
    a.pcrel(0x41FA, 'ai_t')              # lea table(pc),a0
    a.label('ai_l')                      # a group: its specials, 0, its fighters' ids, 0
    a.w(0x2408)                          # move.l a0,d2        (its specials)
    a.w(0x4A50)                          # tst.w (a0)          none: the table's end -
    a.bcc(0x67, 'ai_d')                  #  not an MK fighter, as chosen
    a.label('ai_s')
    a.w(0x4A58)                          # tst.w (a0)+         past the specials
    a.bcc(0x66, 'ai_s')
    a.label('ai_i')
    a.w(0x3218)                          # move.w (a0)+,d1     a fighter's id
    a.bcc(0x67, 'ai_l')                  # (none left: the next group)
    a.w(0xB269, 0x004C)                  # cmp.w $4C(a1),d1
    a.bcc(0x66, 'ai_i')
    a.w(0x2042)                          # movea.l d2,a0       his group's specials
    a.label('ai_f')
    a.w(0x3218)                          # move.w (a0)+,d1     one of his own
    a.bcc(0x67, 'ai_z')                  # beq: none left
    a.w(0xB240)                          # cmp.w d0,d1
    a.bcc(0x67, 'ai_d')
    a.bcc(0x60, 'ai_f')
    a.label('ai_z')
    a.w(0x7000)                          # moveq #0,d0         (none)
    a.label('ai_d')
    # a special he has no move for (no entry in his move table) is none: the Contest's
    # Dark Champion, after Shang (no fighter 26 between: his AI isn't his own), chose
    # $35 and ran an empty entry (he vanished) or Shang's leftover one (a trap)
    a.w(0x2069, 0x00A6)                  # movea.l $A6(a1),a0  his move table
    a.w(0x3200)                          # move.w d0,d1
    a.w(0xD241)                          # add.w d1,d1
    a.w(0xD241)
    a.w(0x4AB0, 0x1000)                  # tst.l 0(a0,d1.w)
    a.bcc(0x66, 'ai_d2')
    a.w(0x7000)                          # moveq #0,d0
    a.label('ai_d2')
    a.w(0x4CDF, 0x0106)                  # movem.l (sp)+,d1-d2/a0
    a.label('ai_r')
    a.w(0x4E75)                          # rts
    a.label('ai_0')
    a.w(0x7000)                          # moveq #0,d0
    a.w(0x4E75)
    a.label('ai_t')                      # groups: specials, 0, ids, 0; ...; 0
    groups = {}                          # (fighters with the same specials share theirs: the
    for fid, keep in table:              #  table outgrew Sonya's block with Reptile's)
        groups.setdefault(tuple(keep), []).append(fid)
    for keep, fids in groups.items():
        assert keep and all(keep) and all(fids)
        a.w(*keep, 0, *fids, 0)
    a.w(0)


def emit_flight(a, done):
    """One call of the uppercut flight: a1 = the flying fighter, a2 = vars
    (+14 him, +18 vy x16, +20 ground y, +22 dx). Uses d0; ends at done."""
    a.w(0x42A9, 0x00C6)                  # clr.l $C6(a1)        EC's own x/y velocity off
    a.w(0x42A9, 0x00CA)                  # clr.l $CA(a1)
    a.w(0x302A, 0x0012)                  # move.w 18(a2),d0
    a.w(0xE840)                          # asr.w #4,d0
    a.w(0x9169, 0x00B6)                  # sub.w d0,$B6(a1)     up by vy
    a.w(0x9169, 0x0052)                  # sub.w d0,$52(a1)
    a.w(0x046A, LAUNCH_G, 0x0012)        # subi.w #G,18(a2)     gravity
    a.w(0x302A, 0x0016)                  # move.w 22(a2),d0
    a.w(0xD169, 0x00B2)                  # add.w d0,$B2(a1)     drift back
    a.w(0xD169, 0x004E)                  # add.w d0,$4E(a1)
    a.w(0x3029, 0x00B6)                  # move.w $B6(a1),d0
    a.w(0xB06A, 0x0014)                  # cmp.w 20(a2),d0
    a.bccw(0x6D, done)                   # blt: still in the air
    a.w(0x336A, 0x0014, 0x00B6)          # move.w 20(a2),$B6(a1)   landed
    a.w(0x336A, 0x0014, 0x0052)          # move.w 20(a2),$52(a1)
    a.w(0x42AA, 0x000E)                  # clr.l 14(a2)


def emit_finish_daze(a, pfx, voice_m, voice_f):
    """FINISH HIM, for the fighter in a1 (a2 = vars: +52 the loser, +56 grace
    calls left, +58 voice pending, +60 calls before he gives out): if a1 is
    the loser, his daze (re)started, the countdowns, the voice and MK's music.
    Ends at label pfx + 'nf'."""
    # FINISH HIM (vars+52 victim, +56 grace calls left, +58 voice pending)
    a.w(0xB3EA, 0x0034)                  # cmpa.l 52(a2),a1
    a.bccw(0x66, f'{pfx}nf')
    a.w(0x0C69, 0x0001, 0x0076)          # cmpi.w #1,$76(a1)   health refilled - a new round (his object is
    a.bcc(0x6E, f'{pfx}fo')              # bgt                  rebuilt at the same address): over. Else it
    a.w(0x4A69, 0x0076)                  # tst.w $76(a1)        dazed him again at the round's start and EC's
    a.bcc(0x6E, f'{pfx}fa')              # bgt                  start sync waited for him for good (Contest)
    a.label(f'{pfx}fo')                  # hit to 0 in the window: an ordinary KO
    a.w(0x42AA, 0x0034)                  # clr.l 52(a2)
    a.bccw(0x60, f'{pfx}nf')
    a.label(f'{pfx}fa')
    a.w(0x4A6A, 0x0038)                  # tst.w 56(a2)        grace countdown
    a.bcc(0x67, f'{pfx}fg')
    a.w(0x536A, 0x0038)                  # subq.w #1,56(a2)
    a.label(f'{pfx}fg')
    a.w(0x4A6A, 0x003C)                  # tst.w 60(a2)        MK: unfinished, he gives out
    a.bcc(0x67, f'{pfx}fx')
    a.w(0x536A, 0x003C)                  # subq.w #1,60(a2)
    a.bcc(0x66, f'{pfx}fx')
    a.w(0x206E, CLOCK_OBJ)               # movea.l $15CA(a6),a0  the round clock's object
    a.w(0x317C, 0x0001, CLOCK_TIME)      # move.w #1,$A4(a0)   its next tick is time-up: EC gives the round
    a.label(f'{pfx}fx')                      # (and so the match) to the one with health left
    # (re)start the daze whenever he's back to neutral: EC parks his move
    # task during a hit reaction and restores its own resume address after
    a.w(0x4A69, 0x00BE)                  # tst.w $BE(a1)
    a.bccw(0x66, f'{pfx}nf')
    a.w(0x2069, 0x0088)                  # movea.l $88(a1),a0
    a.w(0x2050)                          # movea.l (a0),a0     move task -> EC's dizzy
    a.w(0x217C); a.l(DIZZY_CODE); a.w(0x0004)
    a.w(0x4268, 0x0008)                  # clr.w 8(a0)
    a.w(0x4269, 0x0118)                  # clr.w $118(a1)      no pending reaction
    a.w(0x42A9, 0x00C6)                  # clr.l $C6(a1)       no knock-back
    a.w(0x4A6A, 0x003A)                  # tst.w 58(a2)
    a.bccw(0x67, f'{pfx}nf')
    a.w(0x426A, 0x003A)                  # clr.w 58(a2)
    a.w(0x48E7, 0x7FFE)                  # movem.l d1-d7/a0-a6,-(sp)
    a.w(0x363C, voice_m)            # move.w #voice,d3    'FINISH HIM' ...
    a.w(0x3229, 0x004C)                  # move.w $4C(a1),d1
    a.w(0x203C); a.l(FEMALE_MASK)        # move.l #women,d0
    a.w(0x0300)                          # btst d1,d0          a woman?
    a.bcc(0x67, f'{pfx}m')
    a.w(0x363C, voice_f)                 # ... 'FINISH HER'
    a.label(f'{pfx}m')
    a.pcrel(0x41FA, 'f_time')            # lea f_time(pc),a0   MK: the round music gives way to
    a.bccw(0x61, 'f_music')              # bsr.w f_music       the fatality track (2 s of silence first)
    a.w(0x3003)                          # move.w d3,d0
    a.jsr(0x6D58)
    a.w(0x4CDF, 0x7FFE)                  # movem.l (sp)+,d1-d7/a0-a6
    # a hit after the grace is an ordinary KO, the fatality the other way out;
    # left alone he gives out after FINISH_CALLS (the round clock runs out)
    a.label(f'{pfx}nf')


SPEAR_PULL_FRAMES = (0x405E, 0x405F, 0x4232, 0x4233, 0x4234, 0x4235)   # Blade's $34 after the rope's hold


def emit_spear_phase(a, pfx):
    """d0 = the spear thrower's frame: falls through to {pfx}pull only on the pull frames
    (SPEAR_PULL_FRAMES: after the rope's hold, 42:2E-42:31 - which goes to {pfx}out, as
    every other frame does). The throw's wind-up (40:60-40:63, 42:28-42:2D) used to count
    as 'before the hold: pull': a fighter knocked down then was 'reeling' and was dazed
    lying (a hang: EC's landing code looped in his task)."""
    for f in SPEAR_PULL_FRAMES:
        a.w(0x0C40, fr(f))               # cmpi.w #frame,d0
        a.bcc(0x67, f'{pfx}pull')        # beq: a pull frame
    a.bccw(0x60, f'{pfx}out')


SPEAR_STEPS = 0x26614 - 0x21800   # BLA.CO: the spear script's steps after the strike (the rope's hold,
SPEAR_NSTEPS = 17                 #  the yank: 42:30 x2, 42:30 42:31 42:30 40:5E 40:5F 42:32-35...)


def emit_spear_miss(a, p, bare=None):
    """a1 = Scorpion (uses d0/a0). Once per throw, while the rope's hold (42:30)
    shows: his opponent neither reeling ($1A-$1D) nor dazed - the spear missed or was blocked: MK
    pulls nothing (EC pulled a rope with no spear on it), it holds the bare throw. The steps after
    the strike (his module's script, by player slot) are saved and rewritten to the bare throw
    (spear_bare_slot), standing still; restored when the move ends. (Decided once: r_drag runs every
    other frame, the yank's steps change every frame.)"""
    a.w(0x48E7, 0x2030)                  # movem.l d2/a2-a3,-(sp)
    a.pcrel(0x45FA, p + 'v')             # lea vars(pc),a2     (per player: flag word, saved steps)
    a.w(0x267C); a.l(SLOTS[0] + SPEAR_STEPS)   # movea.l #slot1 steps,a3
    a.w(0xB3FC); a.l(0x2E188)            # cmpa.l #P1,a1
    a.bcc(0x67, p + 'p')
    a.w(0x45EA, 2 + 6 * SPEAR_NSTEPS)    # lea size(a2),a2
    a.w(0x267C); a.l(SLOTS[1] + SPEAR_STEPS)   # movea.l #slot2 steps,a3
    a.label(p + 'p')
    a.w(0x3029, 0x00BE)                  # move.w $BE(a1),d0
    a.w(0x0240, 0x7FFF)                  # andi.w #$7FFF,d0
    a.w(0x0C40, SPEAR_MOVE)              # cmpi.w #$34,d0
    a.bcc(0x66, p + 'o')                 # not throwing: restore
    a.w(0x4A12)                          # tst.b (a2)          decided this throw
    a.bcc(0x66, p + 'x')
    a.w(0x0C69, fr(0x4230), 0x001A)      # cmpi.w #42:30,$1A(a1)  (the rope's hold)
    a.bcc(0x66, p + 'x')
    a.w(0x2069, 0x008C)                  # movea.l $8C(a1),a0  his opponent
    a.w(0x3028, 0x00BE)                  # move.w $BE(a0),d0
    a.w(0x0240, 0x7FFF)                  # andi.w #$7FFF,d0
    a.w(0x0C40, DIZZY)                   # cmpi.w #$1F,d0
    a.bcc(0x67, p + 'h')
    a.w(0x0440, 0x001A)                  # subi.w #$1A,d0
    a.w(0x0C40, 0x0003)                  # cmpi.w #3,d0
    a.bcc(0x63, p + 'h')                 # bls: reeling - a hit
    a.w(0x14BC, 0x0002)                  # move.b #2,(a2)      missed: steps rewritten
    a.w(0x548A)                          # addq.l #2,a2
    a.w(0x7400 | (SPEAR_NSTEPS - 1))     # moveq #16,d2
    a.label(p + 'm')
    a.w(0x34EB, 0x0004)                  # move.w 4(a3),(a2)+
    a.w(0x24EB, 0x0008)                  # move.l 8(a3),(a2)+
    bare = bare or spear_bare_slot()
    a.w(0x377C, fr(bare), 0x0004)        # move.w #bare,4(a3)
    a.w(0x42AB, 0x0008)                  # clr.l 8(a3)          (no slide)
    a.w(0x47EB, 0x000C)                  # lea 12(a3),a3
    a.dbra(2, p + 'm')
    a.w(0x337C, fr(bare), 0x001A)        # move.w #bare,$1A(a1)  (the hold showing now)
    a.bcc(0x60, p + 'x')
    a.label(p + 'h')
    a.w(0x14BC, 0x0001)                  # move.b #1,(a2)      a hit: as it is
    a.bcc(0x60, p + 'x')
    a.label(p + 'o')
    a.w(0x1012)                          # move.b (a2),d0
    a.bcc(0x67, p + 'x')
    a.w(0x4212)                          # clr.b (a2)
    a.w(0x5500)                          # subq.b #2,d0
    a.bcc(0x66, p + 'x')
    a.w(0x548A)                          # addq.l #2,a2
    a.w(0x7400 | (SPEAR_NSTEPS - 1))     # moveq #16,d2
    a.label(p + 'r')
    a.w(0x375A, 0x0004)                  # move.w (a2)+,4(a3)
    a.w(0x275A, 0x0008)                  # move.l (a2)+,8(a3)
    a.w(0x47EB, 0x000C)                  # lea 12(a3),a3
    a.dbra(2, p + 'r')
    a.label(p + 'x')
    a.w(0x4CDF, 0x0C04)                  # movem.l (sp)+,d2/a2-a3
    a.bccw(0x60, p + 'z')
    a.label(p + 'v')
    a.out += bytes(2 * (2 + 6 * SPEAR_NSTEPS))
    a.label(p + 'z')


def r_drag(a):
    """Every frame, a1 = a fighter (input task, human or CPU). Uses d0/a0
    (saved by the stub) and saves d1/a2.
    - While he is idle, remember where his main task resumes (per player),
      so a daze can be ended by sending him back there.
    - Daze countdown: when it runs out, end the daze that way.
    - If his opponent is Scorpion in the spear move and he is reeling:
      cancel his knock-back; while Scorpion still holds the rope
      (HOLD_FRAMES) leave him stuck; then drag him PULL_SPEED px per call to
      PULL_GAP px and daze him (EC's dizzy routine) for DAZE_CALLS calls."""
    a.w(0x48E7, 0x4020)                  # movem.l d1/a2,-(sp)
    a.pcrel(0x45FA, 'vars')              # lea vars(pc),a2
    a.w(0x7200)                          # moveq #0,d1          player 0 ...
    a.w(0xB3FC); a.l(0x2E188)            # cmpa.l #P1,a1
    a.bcc(0x67, 'd_p')
    a.w(0x7204)                          # moveq #4,d1          ... or 1 (x4)
    a.label('d_p')
    a.bccw(0x61, 'fatal')                # bsr.w fatal          (MK fatality: input + timeline)
    a.w(0x4A40)                          # tst.w d0
    a.bccw(0x66, 'd_out')                # in a fatality: nothing else for him
    emit_finish_daze(a, 'd_', FINISH_VOICE, FINISH_VOICE_F)
    # a stage Overkill shoots / crushes him without a fighter hit (no blood
    # from the hit path): bleed whenever he reaches his hit frame while a
    # finisher ($1CD4) runs
    a.w(0x0C69, SCORPION_ID, 0x004C)     # cmpi.w #id,$4C(a1)
    a.bccw(0x66, 'd_nob')
    if SCORPION_ID in KD_FIGHTERS:       # MK's knockdown between EC's frame changes (low_kd)
        a.w(0x2F0D)                      # move.l a5,-(sp)
        a.w(0x2A49)                      # movea.l a1,a5
        a.bccw(0x61, 'g_kd')
        a.w(0x2A5F)                      # movea.l (sp)+,a5
    a.w(0x3029, 0x001A)                  # move.w $1A(a1),d0
    a.w(0x4A6E, 0x1CD4)                  # tst.w $1CD4(a6)
    a.bcc(0x67, 'd_obs')
    a.w(0xB06A, 0x0040)                  # cmp.w 64(a2),d0
    a.bcc(0x67, 'd_obs')
    a.w(0x0C40, fr(0x4224))              # cmpi.w #hit frame,d0
    a.bcc(0x66, 'd_obs')
    a.w(0x48E7, 0x0014)                  # movem.l a3/a5,-(sp)
    a.w(0x2649)                          # movea.l a1,a3       he bleeds ...
    a.w(0x2A69, 0x008C)                  # movea.l $8C(a1),a5  ... away from the other side
    a.jsr(SUB_AT['blood_body'])
    a.w(0x4CDF, 0x2800)                  # movem.l (sp)+,a3/a5
    a.w(0x3029, 0x001A)                  # move.w $1A(a1),d0
    a.label('d_obs')
    a.w(0x3540, 0x0040)                  # move.w d0,64(a2)
    a.label('d_nob')
    r_swept(a)
    # dazed (EC's dizzy, state $1F): MK's wobble at MK's timing (DAZE_SEQ)
    # walking (state 8 forward, 4 back): MK's 9-pose walk cycle at MK's
    # timing, forward or reversed (WALK_SEQ; EC's own cycle has 6 frames)
    a.w(0x0C69, SCORPION_ID, 0x004C)     # cmpi.w #id,$4C(a1)
    a.bccw(0x66, 'd_nod')
    emit_spear_miss(a, 'sm_')
    emit_zblock(a)
    a.bccw(0x61, 'zblock')               # bsr zblock          Z: MK's Block
    # his basic attacks play MK's animation (tools/lib/mkscripts.py): his move
    # table ($A6, longs by move id) points at our scripts
    a.w(0x2069, 0x00A6)                  # movea.l $A6(a1),a0
    # (a loop over (4 * id, offset) words: smaller than a pea / move.l pair each)
    a.w(0x48E7, 0x4018)                  # movem.l d1/a3-a4,-(sp)
    a.pcrel(0x47FA, 'mstab')             # lea mstab(pc),a3
    if SCO_TAIL['off'] is not None:      # his scripts in his .PL's tail
        a.w(0x2F08)                      # move.l a0,-(sp)
        a.bccw(0x61, 'sco_tail')         # bsr sco_tail        a0 = the tail
        a.w(0x2848)                      # movea.l a0,a4
        a.w(0x205F)                      # movea.l (sp)+,a0
    else:
        a.w(0x284B)                      # movea.l a3,a4
    a.label('ms_l')
    a.w(0x301B)                          # move.w (a3)+,d0     4 * move id
    a.bcc(0x6B, 'ms_d')                  # bmi: done
    a.w(0x321B)                          # move.w (a3)+,d1     its script - mstab
    a.w(0x4874, 0x1000)                  # pea 0(a4,d1.w)
    a.w(0x219F, 0x0000)                  # move.l (sp)+,0(a0,d0.w)
    a.bcc(0x60, 'ms_l')
    a.label('ms_d')
    a.w(0x4CDF, 0x1802)                  # movem.l (sp)+,d1/a3-a4
    a.w(0x2F0A)                          # move.l a2,-(sp)
    a.bccw(0x61, 'g_reg')                # bsr g_reg            his specials' list and handler (r_gmoves)
    a.w(0x245F)                          # movea.l (sp)+,a2
    emit_vendetta_ok(a, SCORPION_ID, 'sd_')
    r_teleport(a)
    emit_throwcall(a)                    # his throw's victim lands like MK's
    emit_hitdrive(a, THROW_CALLS['mk_moves'], 'd_tw', 'd_nod', True, THROW_MOVE, False)   # MK's throw animation
    emit_hitdrive(a, kick_plan('mk_moves')[0], 'd_ht', 'd_nod', True, room=True,
                  calls_b=HIT_CALLS['mk_moves'])   # MK's reactions: a kick's ($1A), a punch's ($1B)
    # an EC finisher (Vendetta, Overkill...) owns the loser's frames: it loads
    # over his .PL, so a frame of his picked now would unpack garbage (hang)
    a.w(0x4A6E, 0x1CD4)                  # tst.w $1CD4(a6)
    a.bccw(0x66, 'd_nod')
    a.w(0x2069, 0x008C)                  # movea.l $8C(a1),a0  (a Vendetta loads before it sets
    a.w(0x0C28, VENDETTA_MOVE, 0x00BF)   # cmpi.b #$3C,$BF(a0)  $1CD4: his opponent in its move;
                                         #  the low byte: bit 15 flags a step's end)
    a.bccw(0x67, 'd_nod')
    # held by an EC grab ($100 bit 1: a throw, the Dark Champion's drain): the
    # grabber moves him, so no new walk/daze pose - a new pose puts him back at
    # $B6 (SUB $11754), and the drain's lift to $52 >= $150 never ended (lock)
    a.w(0x0829, 0x0001, 0x0101)          # btst #1,$101(a1)
    a.bccw(0x66, 'd_nod')
    a.w(0x3029, 0x00BE)                  # move.w $BE(a1),d0
    a.w(0x0240, 0x7FFF)                  # andi.w #$7FFF,d0
    a.w(0x0C40, DIZZY)                   # cmpi.w #$1F,d0
    a.bccw(0x67, 'd_daze')
    a.w(0x426A, 0x0042)                  # clr.w 66(a2)
    a.w(0x0C40, WALK_FWD)                # cmpi.w #8,d0
    a.bcc(0x67, 'd_wst')
    a.w(0x0C40, WALK_BACK)               # cmpi.w #4,d0
    a.bcc(0x66, 'd_nwk')
    # state 4 is also EC's hold-back and his parked state after the fatality:
    # only drive the walk while a walk frame shows (EC's 40:16-40:1B or ours)
    a.label('d_wst')
    a.w(0x0C29, fr(0x4000) >> 8, 0x001A)  # cmpi.b #sheet,$1A(a1)
    a.bcc(0x66, 'd_nwk')
    a.w(0x1029, 0x001B)                  # move.b $1B(a1),d0
    a.w(0x0C00, 0x0016)                  # cmpi.b #$16,d0
    a.bcc(0x65, 'd_nwk')                 # blo
    a.w(0x0C00, 0x001B)                  # cmpi.b #$1B,d0
    a.bcc(0x63, 'd_wok')                 # bls: EC's walk frame
    a.w(0x0C00, WALK_FRAMES[0] & 0xFF)   # cmpi.b #$64,d0
    a.bcc(0x65, 'd_nwk')
    a.w(0x0C00, WALK_FRAMES[-1] & 0xFF)  # cmpi.b #$6C,d0
    a.bcc(0x63, 'd_wok')                 # bls: ours
    a.label('d_nwk')
    a.w(0x4272, 0x1054)                  # clr.w 84(a2,d1.w)  (per player)
    a.bccw(0x60, 'd_nod')
    a.label('d_wok')
    # EC's own walk step just started (its frame 40:16-40:1B is showing):
    # sync to it - the step's 2nd call is entry 3*step+1 of our table.
    # Direction: state 8 (bit 3 of $BF) forward, else back (step = 5 - frame)
    a.w(0x7000)                          # moveq #0,d0
    a.w(0x1029, 0x001B)                  # move.b $1B(a1),d0
    a.w(0x0440, 0x0016)                  # subi.w #$16,d0
    a.bcc(0x6D, 'd_wcnt')                # blt: not one of EC's frames
    a.w(0x0C40, 0x0005)                  # cmpi.w #5,d0
    a.bcc(0x6E, 'd_wcnt')                # bgt
    a.bccw(0x61, 'wdir')                 # bsr wdir           (toward?)
    a.bcc(0x66, 'd_wfs')
    a.w(0x4440)                          # neg.w d0
    a.w(0x5A40)                          # addq.w #5,d0
    a.label('d_wfs')
    a.w(0x3040)                          # movea.w d0,a0
    a.w(0xD040)                          # add.w d0,d0
    a.w(0xD048)                          # add.w a0,d0          3*step
    a.w(0x5240)                          # addq.w #1,d0
    a.w(0x3580, 0x1054)                  # move.w d0,84(a2,d1.w)
    a.bcc(0x60, 'd_wki')
    a.label('d_wcnt')
    a.w(0x5272, 0x1054)                  # addq.w #1,84(a2,d1.w)
    a.w(0x3032, 0x1054)                  # move.w 84(a2,d1.w),d0
    a.w(0x0C40, len(WALK_SEQ))           # cmpi.w #len,d0
    a.bcc(0x65, 'd_wki')                 # blo
    a.w(0x7000)                          # moveq #0,d0
    a.w(0x3580, 0x1054)                  # move.w d0,84(a2,d1.w)
    a.label('d_wki')
    a.pcrel(0x41FA, 'walkf')             # lea walkf(pc),a0
    a.bccw(0x61, 'wdir')                 # bsr wdir           (toward?)
    a.bcc(0x66, 'd_wset')
    a.pcrel(0x41FA, 'walkb')             # lea walkb(pc),a0
    a.label('d_wset')
    assert len({fr(f) >> 8 for f in WALK_FRAMES}) == 1
    a.w(0x137C, fr(WALK_FRAMES[0]) >> 8, 0x001A)   # move.b #sheet,$1A(a1)   (tables: frame bytes)
    a.w(0x1370, 0x0000, 0x001B)          # move.b (a0,d0.w),$1B(a1)
    a.bccw(0x60, 'd_nod')
    a.label('walkf')
    a.out += bytes(fr(WALK_FRAMES[k]) & 0xFF for k in WALK_SEQ)
    a.label('walkb')
    a.out += bytes(fr(WALK_FRAMES[k]) & 0xFF for k in WALK_SEQ_BACK)
    assert len(a.out) % 2 == 0
    emit_wdir(a, 'wdir')
    a.label('d_daze')
    a.w(0x526A, 0x0042)                  # addq.w #1,66(a2)
    a.w(0x302A, 0x0042)                  # move.w 66(a2),d0
    a.w(0x0C40, len(DAZE_SEQ))           # cmpi.w #len,d0
    a.bcc(0x65, 'd_dzi')                 # blo
    a.w(0x7000)                          # moveq #0,d0
    a.w(0x3540, 0x0042)                  # move.w d0,66(a2)
    a.label('d_dzi')
    a.pcrel(0x41FA, 'dazet')             # lea dazet(pc),a0
    assert len({fr(f) >> 8 for f in DAZE_FRAMES}) == 1
    a.w(0x137C, fr(DAZE_FRAMES[0]) >> 8, 0x001A)   # move.b #sheet,$1A(a1)
    a.w(0x1370, 0x0000, 0x001B)          # move.b (a0,d0.w),$1B(a1)
    a.bccw(0x60, 'd_nod')
    a.label('dazet')
    a.out += bytes(fr(DAZE_FRAMES[k]) & 0xFF for k in DAZE_SEQ)
    if len(a.out) % 2:
        a.out += b'\0'
    a.label('d_nod')
    a.w(0x2069, 0x0088)                  # movea.l $88(a1),a0   his task chain ...
    a.w(0x2050)                          # movea.l (a0),a0      ... 2nd task = his moves
    a.w(0x4A69, 0x00BE)                  # tst.w $BE(a1)        idle?
    a.bcc(0x66, 'd_ni')
    a.w(0x25A8, 0x0004, 0x1000)          # move.l 4(a0),(a2,d1.w)   idle resume address
    a.label('d_ni')
    # daze countdown (vars+8 = victim, vars+12 = calls left)
    a.w(0xB3EA, 0x0008)                  # cmpa.l 8(a2),a1
    a.bcc(0x66, 'd_nd')
    a.w(0x536A, 0x000C)                  # subq.w #1,12(a2)
    a.bcc(0x66, 'd_nd')
    a.w(0x42AA, 0x0008)                  # clr.l 8(a2)          daze over:
    a.w(0x0C69, DIZZY, 0x00BE)           # cmpi.w #$1F,$BE(a1)  (still dizzy, not hit out of it)
    a.bcc(0x66, 'd_nd')
    a.w(0x2172, 0x1000, 0x0004)          # move.l (a2,d1.w),4(a0)  back to standing
    a.w(0x4268, 0x0008)                  # clr.w 8(a0)
    a.w(0x4269, 0x00BE)                  # clr.w $BE(a1)
    # the cleanup EC's own dizzy exit does (BLA.CO $22850): without it he
    # stays flagged as "being hit" - the CPU never acts and he can't be hit
    a.w(0x08A9, 0x0003, 0x0101)          # bclr #3,$101(a1)
    a.w(0x08A9, 0x0007, 0x011A)          # bclr #7,$11A(a1)
    a.w(0x08A9, 0x0005, 0x00F7)          # bclr #5,$F7(a1)
    a.w(0x2069, 0x008C)                  # movea.l $8C(a1),a0   opponent
    a.w(0x0268, 0xBEF9, 0x011A)          # andi.w #$BEF9,$11A(a0)
    a.label('d_nd')
    # uppercut flight (vars+14 = flying fighter, +18 vy x16, +20 ground y, +22 dx)
    a.w(0xB3EA, 0x000E)                  # cmpa.l 14(a2),a1
    a.bcc(0x66, 'd_nl')
    emit_flight(a, 'd_nl')
    a.label('d_nl')
    # spear
    a.w(0x2069, 0x008C)                  # movea.l $8C(a1),a0  opponent
    a.w(0x0C68, SCORPION_ID, 0x004C)     # cmpi.w #9,$4C(a0)
    a.bccw(0x66, 'd_out')
    a.w(0x0C68, SPEAR_MOVE, 0x00BE)      # cmpi.w #$34,$BE(a0)
    a.bccw(0x66, 'd_out')
    a.w(0x4A69, 0x0076)                  # tst.w $76(a1)       knocked out by it (in the air: EC's
    a.bccw(0x67, 'd_out')                #  knockdown) - EC's KO, not our pull and daze: the round never ended
    a.w(0x3029, 0x00BE)                  # move.w $BE(a1),d0
    a.w(0x0440, HIT_FIRST)               # subi.w #first,d0
    a.w(0x0C40, HIT_LAST - HIT_FIRST)    # cmpi.w #n,d0
    a.bccw(0x62, 'd_out')                 # bhi: not reeling
    a.w(0xB3EA, 96)                      # cmpa.l 96(a2),a1     speared in the air (r_hit):
    a.bccw(0x67, 'd_out')                #  EC's knockdown, not ours
    a.w(0x42A9, 0x00C6)                  # clr.l $C6(a1)        no knock-back
    a.w(0x3028, 0x001A)                  # move.w $1A(a0),d0    Scorpion's frame: only after the rope's hit
    emit_spear_phase(a, 'd_')
    a.label('d_pull')
    a.w(0xB3EA, 92)                      # cmpa.l 92(a2),a1     the yank's line said?
    a.bcc(0x67, 'd_said')
    a.w(0x2549, 92)                      # move.l a1,92(a2)
    a.w(0x48E7, 0xFFFE)                  # movem.l d0-d7/a0-a6,-(sp)
    a.w(0x303C, VOICE_ID)                # move.w #GETOHERE,d0  (MK: as he yanks)
    a.jsr(0x6D58)
    a.w(0x4CDF, 0x7FFF)                  # movem.l (sp)+,d0-d7/a0-a6
    a.label('d_said')
    a.w(0x3368, 0x00B6, 0x00B6)          # move.w $B6(a0),$B6(a1)  dragged along the floor
    a.w(0x3368, 0x00B6, 0x0052)          # move.w $B6(a0),$52(a1)  (speared mid-jump: no floating)
    a.w(0x3029, 0x00B2)                  # move.w $B2(a1),d0
    a.w(0x9068, 0x00B2)                  # sub.w $B2(a0),d0    gap (victim - Scorpion)
    a.bcc(0x6A, 'd_right')               # bpl
    a.w(0x4440)                          # neg.w d0
    a.w(0x0C40, PULL_GAP)
    a.bcc(0x6F, 'd_near')                # ble
    a.w(0x0669, PULL_SPEED, 0x00B2)      # addi.w #SPEED,$B2(a1)
    a.w(0x0669, PULL_SPEED, 0x004E)      # addi.w #SPEED,$4E(a1)
    a.bccw(0x60, 'd_out')
    a.label('d_right')
    a.w(0x0C40, PULL_GAP)
    a.bcc(0x6F, 'd_near')
    a.w(0x0469, PULL_SPEED, 0x00B2)      # subi.w #SPEED,$B2(a1)
    a.w(0x0469, PULL_SPEED, 0x004E)      # subi.w #SPEED,$4E(a1)
    a.bccw(0x60, 'd_out')
    a.label('d_near')
    # yanked in: daze him - his main task resumes in EC's dizzy routine
    a.w(0x2069, 0x0088)                  # movea.l $88(a1),a0
    a.w(0x2050)                          # movea.l (a0),a0      move task
    a.w(0x217C); a.l(DIZZY_CODE); a.w(0x0004)   # move.l #dizzy,4(a0)
    a.w(0x4268, 0x0008)                  # clr.w 8(a0)
    a.w(0x2549, 0x0008)                  # move.l a1,8(a2)     dazed fighter
    a.w(0x357C, DAZE_CALLS, 0x000C)      # move.w #calls,12(a2)
    a.label('d_out')
    a.w(0x4CDF, 0x0402)                  # movem.l (sp)+,d1/a2
    a.w(0x4E75)                          # rts
    a.label('vars')   # +0 idle PC P1, +4 idle PC P2, +8 dazed fighter, +12 calls left,
    a.l(0); a.l(0); a.l(0); a.w(0)       # +14 flying fighter, +18 vy x16, +20 ground y, +22 dx
    a.l(0); a.w(0); a.w(0); a.w(0)
    # +24 fatality on, +26 step, +28 calls in step, +30 Scorpion, +34 victim, +38 victim's frame,
    # +40/+42 Up taps (P1/P2), +44/+46 tap window, +48/+50 last pad word
    a.w(0); a.w(0); a.w(0); a.l(0); a.l(0); a.w(0)
    a.w(0); a.w(0); a.w(0); a.w(0); a.w(0); a.w(0)
    # +52 FINISH HIM victim, +56 grace calls left, +58 FINISH HIM voice still to play,
    # +60 calls left before he gives out, +62 blood drops alive, +64 his last frame,
    # +66 dazed count, +68 walk count, +70 teleport direction, +72 its last step,
    # +74 camera held, +76 teleport taken over, +78 where he lands, +81 his double stands (bit 0 P1, 1 P2),
    # +84/+88 walk count (P1/P2: a mirror match walks two Scorpions), +92 the spear's victim told GET OVER HERE,
    # +96 the spear's victim speared in the air (no pull, no daze: EC's knockdown)
    a.l(0); a.w(0); a.w(0); a.w(0); a.w(0); a.w(0); a.w(0); a.w(0)
    a.w(0); a.w(0); a.w(0); a.w(0); a.w(0); a.w(0); a.l(0); a.l(0)
    a.l(0); a.l(0)
    a.w(0)            # (to 100 bytes: +92's long ran 2 bytes past the 94 there were - over the first
                      #  word of the code after, r_hit_f's; +96's then hung the Contest: traced)
    assert len(a.out) - a.labels['vars'] == 100, len(a.out) - a.labels['vars']


BLOOD_SHEET, BLOOD_FRAME, BLOOD_N, BLOOD_LIFE = 0x1B, 7, 6, 22
BLOOD_MAX = 6                 # drops alive at once: EC's hit code waits for a free effect object (a fighter froze mid-reaction)
BLOOD_CHEST = 75              # px above the feet: where the spear's blood comes from
EFFECT_SPAWN = 0x6954         # d0 type, d1 x, d2 y -> a0 object (carry set: none free - patches.ec_object_pool)
PLAIN_EFFECT = 0x24           # the hit spark: a drawn, scheduled effect we take over


def emit_mkrow(a):
    """mkrow: d0 = a fighter id -> a0 = his row of mktab (id.b, bleeds.b,
    his frame 42:02.w), or the zero row if he isn't an MK fighter. Uses a0."""
    a.label('mkrow')
    a.pcrel(0x41FA, 'mktab')             # lea mktab(pc),a0
    a.label('mr_l')
    a.w(0x4A10)                          # tst.b (a0)
    a.bcc(0x67, 'mr_x')
    a.w(0xB010)                          # cmp.b (a0),d0
    a.bcc(0x67, 'mr_x')
    a.w(0x5888)                          # addq.l #4,a0
    a.bcc(0x60, 'mr_l')
    a.label('mr_x')
    a.w(0x4E75)
    a.label('mktab')
    for fid in MK_IDS:
        assert 0 < fid < 0x100
        a.w(fid << 8 | (1 if fid in BLOOD_IDS else 0))
        a.w((MK_SHEET_BASE[fid] + 2) << 8 | 0x02)
    a.w(0); a.w(0)


SUB_AT = {}                   # shared routines in SUB.BIN (build): blood, blood_body, mkrow -> address


def r_blood(a, cnt='vars', off=62):
    """Spawn BLOOD_N droplets at the hit point ($1444/$1446): plain effect
    objects drawing sheet BLOOD_SHEET (Scorpion's art) that run 'droplet'.
    Per droplet: $60 vx, $62 vy, $64 frames left (effect objects are only
    $A6 bytes: fields past that belong to the next object)."""
    a.label('blood')                     # at the hit point
    a.w(0x48E7, 0xFCC0)                  # movem.l d0-d5/a0-a1,-(sp)
    a.w(0x322E, 0x1444)                  # move.w $1444(a6),d1
    a.w(0x342E, 0x1446)                  # move.w $1446(a6),d2
    a.bcc(0x60, 'b_go')
    a.label('blood_body')                # at the victim's chest (spear: no hit point)
    a.w(0x48E7, 0xFCC0)                  # movem.l d0-d5/a0-a1,-(sp)
    a.w(0x322B, 0x004E)                  # move.w $4E(a3),d1
    a.w(0x342B, 0x0052)                  # move.w $52(a3),d2
    a.w(0x0442, BLOOD_CHEST)             # subi.w #chest,d2
    a.label('b_go')
    # red: drawn with Scorpion's palette line, whose colours 12/13 (the
    # spark's) are blood (patches.scorpion_palette). Scorpion: attacker,
    # victim, or the owner of the projectile.
    a.w(0x78FF)                          # moveq #-1,d4        (SUB.BIN's room: 2 bytes less than move.w)
    # (the attacker, then the victim: the victim's line wins when both bleed)
    a.w(0x302D, 0x004C)                  # move.w $4C(a5),d0
    a.bccw(0x61, 'mkrow')                # bsr mkrow
    a.w(0x4A28, 0x0001)                  # tst.b 1(a0)          bleeds?
    a.bcc(0x67, 'b_v')
    a.w(0x382D, 0x007A)                  # move.w $7A(a5),d4
    a.label('b_v')
    a.w(0x302B, 0x004C)                  # move.w $4C(a3),d0
    a.bccw(0x61, 'mkrow')
    a.w(0x4A28, 0x0001)                  # tst.b 1(a0)
    a.bcc(0x67, 'b_o')
    a.w(0x382B, 0x007A)                  # move.w $7A(a3),d4
    a.label('b_o')
    a.w(0x4A44)                          # tst.w d4
    a.bcc(0x6A, 'b_s')                   # bpl: found
    a.w(0x226D, 0x008C)                  # movea.l $8C(a5),a1  projectile's owner
    a.w(0x3029, 0x004C)                  # move.w $4C(a1),d0
    a.bccw(0x61, 'mkrow')
    a.w(0x4A28, 0x0001)                  # tst.b 1(a0)
    a.bcc(0x67, 'b_s')
    a.w(0x3829, 0x007A)                  # move.w $7A(a1),d4
    a.label('b_s')
    a.w(0x4A44)                          # tst.w d4
    a.bccw(0x6B, 'b_done')               # bmi: nobody here bleeds (no droplets in other colours)
    # spray away from the attacker (a5)
    a.w(0x7A01)                          # moveq #1,d5
    a.w(0x302B, 0x004E)                  # move.w $4E(a3),d0
    a.w(0xB06D, 0x004E)                  # cmp.w $4E(a5),d0
    a.bcc(0x6C, 'b_dir')                 # bge: victim to the right
    a.w(0x7AFF)                          # moveq #-1,d5
    a.label('b_dir')
    a.w(0x7600 | (BLOOD_N - 1))          # moveq #n-1,d3
    a.label('b_loop')
    a.pcrel(0x41FA, cnt)                 # lea cnt(pc),a0
    a.w(0x0C68, BLOOD_MAX, off)          # cmpi.w #max,off(a0)  drops alive: EC's own effects
    a.bccw(0x6C, 'b_done')               # bge                 must always find a free object
    a.w(0x48E7, 0x6000)                  # movem.l d1-d2,-(sp)
    a.w(0x303C, PLAIN_EFFECT)            # move.w #$24,d0
    a.jsr(EFFECT_SPAWN)
    a.w(0x4CDF, 0x0006)                  # movem.l (sp)+,d1-d2
    a.bcc(0x65, 'b_done')                # bcs: no free object
    a.w(0x117C, BLOOD_SHEET, 0x001A)     # move.b #sheet,$1A(a0)
    a.w(0x117C, BLOOD_FRAME, 0x001B)     # move.b #frame,$1B(a0)
    a.w(0x4A44)                          # tst.w d4
    a.bcc(0x6B, 'b_np')                  # bmi: no Scorpion here
    # an effect's sprite line is ((attr >> 13) & 3) ^ 1, attr at $1E/$20
    # (probed); a fighter's is ($7A & 3) ^ 1: so attr = ($7A & 3) << 13
    a.w(0x3004)                          # move.w d4,d0
    a.w(0x0240, 0x0003)                  # andi.w #3,d0
    a.w(0xE148)                          # lsl.w #8,d0
    a.w(0xEB48)                          # lsl.w #5,d0
    a.w(0x3140, 0x001E)                  # move.w d0,$1E(a0)
    a.w(0x3140, 0x0020)                  # move.w d0,$20(a0)
    a.label('b_np')
    a.w(0x7000)                          # moveq #0,d0
    a.w(0x3003)                          # move.w d3,d0        vx = dir * (1 + d3 % 5)
    a.w(0x80FC, 0x0005)                  # divu.w #5,d0
    a.w(0x4840)                          # swap d0             remainder
    a.w(0x5240)                          # addq.w #1,d0
    a.w(0xC1C5)                          # muls.w d5,d0
    a.w(0x3140, 0x0060)                  # move.w d0,$60(a0)
    a.w(0x3003)                          # move.w d3,d0        vy = -(3 + d3 / 2)
    a.w(0xE248)                          # lsr.w #1,d0
    a.w(0x5640)                          # addq.w #3,d0
    a.w(0x4440)                          # neg.w d0
    a.w(0x3140, 0x0062)                  # move.w d0,$62(a0)
    a.w(0x317C, BLOOD_LIFE, 0x0064)      # move.w #life,$64(a0)
    a.pcrel(0x43FA, cnt)                 # lea cnt(pc),a1
    a.w(0x5269, off)                     # addq.w #1,off(a1)
    a.w(0x2268, 0x0088)                  # movea.l $88(a0),a1   its task
    a.pcrel(0x487A, 'droplet')           # pea droplet(pc)
    a.w(0x235F, 0x0004)                  # move.l (sp)+,4(a1)
    a.w(0x4269, 0x0008)                  # clr.w 8(a1)
    a.dbra(3, 'b_loop')
    a.label('b_done')
    a.w(0x4CDF, 0x033F)                  # movem.l (sp)+,d0-d5/a0-a1
    a.w(0x4E75)
    # droplet task (a5 = the droplet, a4 = this task's block)
    a.label('droplet')
    # (EC can take a droplet's object back for an effect of its own - a flurry of hits: the drop went
    # on moving, and at its end removing, an object no longer its own; a Contest froze, the task list
    # wrecked: still ours only while the object's task is this one)
    a.w(0xB9ED, 0x0088)                  # cmpa.l $88(a5),a4
    a.bcc(0x66, 'dr_lost')               # bne: not ours any more
    a.w(0x302D, 0x0060)                  # move.w $60(a5),d0
    a.w(0xD16D, 0x004E)                  # add.w d0,$4E(a5)
    a.w(0x302D, 0x0062)                  # move.w $62(a5),d0
    a.w(0xD16D, 0x0052)                  # add.w d0,$52(a5)
    a.w(0x526D, 0x0062)                  # addq.w #1,$62(a5)   gravity
    a.w(0x536D, 0x0064)                  # subq.w #1,$64(a5)
    a.bcc(0x67, 'dr_gone')
    a.w(0x7001)                          # moveq #1,d0
    a.jsr(0x68D6)                        # sleep 1 frame
    a.bcc(0x60, 'droplet')
    a.label('dr_gone')
    a.w(0x08ED, 0x0002, 0x0082)          # bset #2,$82(a5)     remove
    a.label('dr_lost')
    a.pcrel(0x41FA, cnt)                 # lea cnt(pc),a0
    a.w(0x5368, off)                     # subq.w #1,off(a0)
    a.jmp(0x6A1A)                        # halt
    emit_mkrow(a)


MUSIC_TAG = 0x454B4D55        # 'EKMU': the fatality music's disc time follows (patches.fatality_music)
FINISH_CALLS = 125            # MK: an unfinished loser collapses 250 frames after FINISH HIM (r_drag: every other frame)
ROUND_CLOCK = -0x2AE6         # (unused: a fixed address, but the clock lives in an object that moves)
CLOCK_OBJ, CLOCK_TIME = 0x15CA, 0xA4   # ($15CA(a6)) + $A4: the round time, BCD (found by its count-down
                                       # in three fights: $2D1DC, $2D282, $2D282)
FINISH_GRACE = 30             # calls (~1 s) after FINISH HIM in which hits can't take his last point
FINISH_TABLE = 0x15F16        # EC's wins-needed bytes by $1CFE (its own finisher check, PLYR.CO $15EC6)
CLAMP_SITES = (0x1985A, 0x19D26, 0x19EFA)   # tst.w $76(a3); bpl.s; clr.w $76(a3): after damage (fighter, projectile hits)
CLAMP_ORIG = bytes.fromhex('4a6b00766a04426b0076')
# a fighter module's throw landing (each .CO: its victim code, a5 = the thrown fighter): the damage
# taken, then 0 when he's left on 0 or less - that move and the bra.w after it become exg a3,a5; jsr
# THROWKO['at']; bra.s (patches.throw_finish)
THROW_DAMAGE = bytes.fromhex('302d0116426d0116d16d0190916d0076')   # move.w $116(a5),d0; clr.w $116(a5);
                                                                   # add.w d0,$190(a5); sub.w d0,$76(a5)
THROW_ZERO = bytes.fromhex('3b7c00000076')                         # (after a bgt.s) move.w #0,$76(a5)
THROWKO = {'at': None}
DARK_CHAMPION = 25            # fighter id (the Contest's last opponent)
KO_SITE = 0x19FAE             # sub.w d6,d4; move.w d4,$76(a3); bgt.s: projectile damage, straight to the KO when <= 0
KO_ORIG = bytes.fromhex('984637440076')
FAT_GAP = 90                  # px: MK does it from half a screen
FAT_PAUSE = 100               # frames on the bones before the round ends (MK ~2 s, moveq max 127)
GK_HOLD = 2                   # more FAT_PAUSEs (200 frames each: the task sleeps in calls) after a fatality: MK's announcer
BLOCK_BIT, UP_BIT = 8, 0      # pad word: Z = MK Block ($100), Up = 1
THROW_BIT = 9                 # pad word: Y ($200) (A $40, B $10, C $20, X $400, Start $80; dirs 1/2/4/8)
# (calls, Scorpion frame (0 = keep), victim mode (0 own/frozen, 1 Scorpion art +
# Scorpion's colours, 2 his own frame in black), victim frame); calls ~2 frames
FATALITY_BLADE = [
    (10, 0x4152, 0, 0), (14, 0x4153, 0, 0), (14, 0x4155, 0, 0), (10, 0x4156, 0, 0),   # mask off, skull
    (6, 0x4157, 0, 0),                                                                 # leans in
    (6, 0x4159, 1, 0x415A), (8, 0x4159, 1, 0x415B), (8, 0x4159, 1, 0x415B),           # fire: burst, column
    (10, 0x4155, 2, 0),                                                                # charred
    (6, 0x4155, 1, 0x415C), (6, 0x4155, 1, 0x415E),                                   # ash
    (10, 0x4155, 1, 0x4140), (8, 0x4155, 1, 0x4141), (8, 0x4155, 1, 0x4143),          # skeleton falls
    (40, 0x4155, 1, 0x4145),                                                           # bones
]
FATALITY = [(n, fr(f), m, fr(v) if v else 0) for n, f, m, v in FATALITY_BLADE]


TELE_MOVE = 0x35              # Blade's dash (down, back + HP): Scorpion's teleport punch
CAMERA_X = 0x2B070            # PRG-RAM word: the screen's left edge in stage x (320 wide)
# MK's teleport (tools/lib/mkmoves.py teleport; poses cleaned into teleport_mk):
# crouch, spring, a tucked leap back and up, out through his own screen edge
# head first; then in at the opposite edge fist first, landing just inside
# it - the punch lands only on someone near that edge. Our own animation
# script (EC plays the frames, no flashes); r_tele moves him.
# the punch's hit ($102: damage, attack type - Blade's punches are types
# 1/2, his uppercuts $40/$41, the dash $1C). The dash's $0C1C knocked the
# victim down and across the screen; MK's teleport punch (measured,
# build/states/mk_2p.state) staggers him ~70 px back on his feet, with blood, for
# 19 of 119 health (16%: 17 of EC's 104): the high punch's type
TELE_HIT = 0x1101
TELE_STEPS = [                # (frame, ticks of 2 frames, F6, $102)
    (0x4116, 3, 0x0002, 0),   # 1 crouch
    (0x4117, 1, 0x0002, 0),   # 2 spring
    (0x4130, 2, 0x0002, 0),   # 3 tucked leap
    (0x4131, 1, 0x0002, 0),   # 4 stretching out
    (0x4132, 8, 0x0002, 0),   # 5 flying out head first: EC stops him at the screen edge,
                              #   the pose is drawn behind him, so he leaves the screen
    (0x4162, 5, 0x0402, TELE_HIT),   # 6 in at the far edge, punching (Blade's dash frame: if
                              #   someone is there, the contact is the hit and ends the move)
    (0x4134, 6, 0x0000, 0),   # 7 landed at the edge
]
T_TUCK, T_FLY, T_PUNCH, T_LAND = 3, 5, 6, 7
# MK leaves a frozen copy of his stance (idle pose 3) where he took off, from
# the leap until he lands: an effect object showing GHOST_FRAME. Not a fighter
# frame (EC unpacks one per fighter, into his own VRAM area: a second object
# showing one draws stripes) but effect sheet $7C, uploaded whole at the
# fight's start (patches.scorpion_ghost_art, scorpion-no-fx)
GHOST_FRAME = 0x7C00
GHOST_ON = True

CAM_HOLD = 1                  # $AB6 bit 1: EC's camera stops following (PLYR $14D88)
TELE_OUT = 16                 # px per call flying out (outruns the camera; EC stops him at the edge)
TELE_EDGE = 238               # incoming pose extends 80 px from its anchor; keep it on screen


def _mk_scripts():
    import mkscripts
    from inputs import ROOT
    co = open(os.path.join(ROOT, 'extracted', 'ec_us', 'BLA.CO'), 'rb').read()
    return mkscripts.build(co)[0]


MK_SCRIPTS = _mk_scripts()


def r_teleport(a):
    """Scorpion in his teleport (EC move $35), a1 = him, a2 = vars, d1 kept.
    vars +70 direction away from the opponent (-1/1), +72 last step, +74 camera
    held, +76 taken, +78 landing x."""
    a.w(0x3029, 0x00BE)                  # move.w $BE(a1),d0
    a.w(0x0240, 0x7FFF)                  # andi.w #$7FFF,d0
    a.w(0x0C40, TELE_MOVE)               # cmpi.w #$35,d0
    a.bccw(0x67, 'tp_on')
    a.w(0x3009)                          # move.w a1,d0
    a.w(0x0240, 0x0020)                  # andi.w #$20,d0
    a.w(0xEA48)                          # lsr.w #5,d0         player 0/1 ($2E188/$2E330)
    a.w(0x01AA, 0x0051)                  # bclr d0,81(a2)      his double goes (each player his bit: a mirror match)
    # the rest of vars +72-78 is one teleport's: in a mirror match, while the
    # other Scorpion teleports, leave it (and the camera) to him
    # (only one in OUR teleport script: the Dark Champion copies fighters, Scorpion's
    #  id and move $35 included, and skipping for him left the final fight unwinnable)
    a.w(0x2069, 0x008C)                  # movea.l $8C(a1),a0  his opponent
    a.w(0x2028, 0x00AE)                  # move.l $AE(a0),d0   his script position
    a.pcrel(0x41FA, 'tscript')           # lea tscript(pc),a0
    a.w(0x9088)                          # sub.l a0,d0
    a.w(0x0C80); a.l(12 * (len(TELE_STEPS) + 2))   # cmpi.l #len,d0
    a.bccw(0x65, 'tp_out')               # blo: in our teleport (unsigned: before it is huge)
    a.label('tp_own')
    a.w(0x426A, 0x004C)                  # clr.w 76(a2)        not teleporting
    a.w(0x4A6A, 0x004A)                  # tst.w 74(a2)        camera held by us?
    a.bccw(0x67, 'tp_out')
    a.w(0x426A, 0x004A)                  # clr.w 74(a2)
    a.w(0x08AE, CAM_HOLD, 0x0AB6)        # bclr #1,$AB6(a6)    camera follows again
    a.bccw(0x60, 'tp_out')
    a.label('tp_on')
    a.w(0x48E7, 0x3010)                  # movem.l d2-d3/a3,-(sp)
    a.pcrel(0x41FA, 'tscript')           # lea tscript(pc),a0
    a.w(0x2429, 0x00AE)                  # move.l $AE(a1),d2   script position
    a.w(0x9488)                          # sub.l a0,d2
    a.bccw(0x6B, 'tp_ec')                 # bmi: EC's own script
    a.w(0x0C82); a.l(12 * (len(TELE_STEPS) + 2))   # cmpi.l #len,d2
    a.bccw(0x64, 'tp_ec')                 # bhs
    a.w(0x84FC, 0x000C)                  # divu.w #12,d2       step
    a.w(0x362A, 0x0048)                  # move.w 72(a2),d3    last step
    a.w(0x3542, 0x0048)                  # move.w d2,72(a2)
    # the double: in place as he leaps, gone as he lands
    a.w(0x0C42, T_TUCK)                  # cmpi.w #tuck,d2
    a.bccw(0x66, 'tp_g1')
    a.w(0xB642)                          # cmp.w d2,d3         first call of the leap?
    a.bccw(0x67, 'tp_g1')
    if GHOST_ON:
        a.bccw(0x61, 'ghost_new')        # bsr.w ghost_new
    a.label('tp_g1')
    a.w(0x0C42, T_LAND)                  # cmpi.w #land,d2
    a.bccw(0x66, 'tp_g2')
    a.w(0x3009)                          # move.w a1,d0
    a.w(0x0240, 0x0020)                  # andi.w #$20,d0
    a.w(0xEA48)                          # lsr.w #5,d0         player 0/1 ($2E188/$2E330)
    a.w(0x01AA, 0x0051)                  # bclr d0,81(a2)      the double goes
    a.label('tp_g2')
    # d0 = T, where he lands: the far edge's side of the screen
    a.w(0x3039); a.l(CAMERA_X)           # move.w CAMERA_X,d0
    a.w(0x4A6A, 0x0046)                  # tst.w 70(a2)        away = left?
    a.bccw(0x6B, 'tp_tl')
    a.w(0x0640, 320 - TELE_EDGE)         # inset from the left (away right)
    a.bccw(0x60, 'tp_tt')
    a.label('tp_tl')
    a.w(0x0640, TELE_EDGE)               # inset from the right
    a.label('tp_tt')
    a.w(0x0C42, T_FLY)                   # cmpi.w #fly,d2
    a.bccw(0x66, 'tp_nf')
    a.w(0x302A, 0x0046)                  # move.w 70(a2),d0
    a.w(0xC1FC, TELE_OUT)                # muls.w #out,d0
    a.w(0xD069, 0x004E)                  # add.w $4E(a1),d0
    a.bccw(0x60, 'tp_setx')
    a.label('tp_nf')
    a.w(0x0C42, T_PUNCH)                 # cmpi.w #punch,d2    punching in, landed:
    a.bccw(0x6D, 'tp_done')              # blt                 at the far edge (T)
    a.bccw(0x66, 'tp_kept')              # bne: landed
    a.w(0xB642)                          # cmp.w d2,d3         first call coming in:
    a.bccw(0x67, 'tp_kept')
    a.w(0x3540, 0x004E)                  # move.w d0,78(a2)    where he lands (the camera may move after a hit)
    # he faces her as he comes in (else EC turns him round, ending the move):
    # the poses coming in are stored mirrored (teleport_mk 5, 6)
    a.w(0x0A69, 0x0800, 0x0100)          # eori.w #$800,$100(a1)
    a.w(0x0A69, 0x0800, 0x0020)          # eori.w #$800,$20(a1)
    a.bccw(0x60, 'tp_setx')
    a.label('tp_kept')
    a.w(0x302A, 0x004E)                  # move.w 78(a2),d0
    a.bccw(0x60, 'tp_done')
    a.label('tp_setx')
    a.w(0x3340, 0x004E)                  # move.w d0,$4E(a1)
    a.w(0x3340, 0x00B2)                  # move.w d0,$B2(a1)
    a.bccw(0x60, 'tp_done')
    # EC's own dash script: take it over once per move
    a.label('tp_ec')
    a.w(0x4A6A, 0x004C)                  # tst.w 76(a2)
    a.bccw(0x66, 'tp_done')                # EC took it back (a hit, the end)
    a.w(0x357C, 0x0001, 0x004C)          # move.w #1,76(a2)
    a.w(0x08EE, CAM_HOLD, 0x0AB6)        # bset #1,$AB6(a6)    camera holds still (MK's does)
    a.w(0x357C, 0x0001, 0x004A)          # move.w #1,74(a2)
    a.w(0x2669, 0x008C)                  # movea.l $8C(a1),a3  opponent
    a.w(0x76FF)                          # moveq #-1,d3        away = left ...
    a.w(0x302B, 0x004E)                  # move.w $4E(a3),d0
    a.w(0xB069, 0x004E)                  # cmp.w $4E(a1),d0
    a.bccw(0x6E, 'tp_d')                   # bgt: he is to our right
    a.w(0x7601)                          # moveq #1,d3         ... or right
    a.label('tp_d')
    a.w(0x3543, 0x0046)                  # move.w d3,70(a2)
    a.w(0x2348, 0x00AE)                  # move.l a0,$AE(a1)   next step: ours
    # EC ends a move after $C4 steps ($C2 counts them, PLYR $182CE): ours
    a.w(0x337C, len(TELE_STEPS), 0x00C4)  # move.w #steps,$C4(a1)
    a.w(0x4269, 0x00C2)                  # clr.w $C2(a1)
    a.w(0x42A9, 0x005E)                  # clr.l $5E(a1)       no dash speed
    a.w(0x42A9, 0x00C6)                  # clr.l $C6(a1)
    a.w(0x357C, 0xFFFF, 0x0048)          # move.w #-1,72(a2)
    a.label('tp_done')
    a.w(0x4CDF, 0x080C)                  # movem.l (sp)+,d2-d3/a3
    a.bccw(0x60, 'tp_out')
    if GHOST_ON:                         # (off: not assembled)
        # spawn the double: an effect object at his feet, his palette line and facing
        a.label('ghost_new')
        a.w(0x48E7, 0xF0C0)                  # movem.l d0-d3/a0-a1,-(sp)
        a.w(0x3229, 0x004E)                  # move.w $4E(a1),d1
        a.w(0x3429, 0x0052)                  # move.w $52(a1),d2
        a.w(0x2F09)                          # move.l a1,-(sp)
        a.w(0x303C, SCORPION_ID)             # move.w #id,d0       his own descriptor (a spark's has no room)
        a.jsr(EFFECT_SPAWN)
        a.w(0x225F)                          # movea.l (sp)+,a1
        a.bccw(0x65, 'gh_out')               # bcs: no free object
        a.w(0x317C, GHOST_FRAME, 0x001A)     # move.w #$7C00,$1A(a0)  (sheet $7C frame 0)
        a.w(0x3169, 0x001E, 0x001E)          # move.w $1E(a1),$1E(a0)  his palette line
        a.w(0x3169, 0x0020, 0x0020)          # move.w $20(a1),$20(a0)  his facing
        a.w(0x3009)                          # move.w a1,d0
        a.w(0x0240, 0x0020)                  # andi.w #$20,d0
        a.w(0xEA48)                          # lsr.w #5,d0         player 0/1 ($2E188/$2E330)
        a.w(0x01EA, 0x0051)                  # bset d0,81(a2)      his double stands
        a.w(0x2068, 0x0088)                  # movea.l $88(a0),a0  its task
        a.pcrel(0x43FA, 'ghost')             # lea ghost(pc),a1    (player 1's double)
        a.w(0x4A40)                          # tst.w d0
        a.bcc(0x67, 'gh_p1')
        a.pcrel(0x43FA, 'ghost2')            # lea ghost2(pc),a1   (player 2's)
        a.label('gh_p1')
        a.w(0x2149, 0x0004)                  # move.l a1,4(a0)
        a.w(0x4268, 0x0008)                  # clr.w 8(a0)
        a.label('gh_out')
        a.w(0x4CDF, 0x030F)                  # movem.l (sp)+,d0-d3/a0-a1
        a.w(0x4E75)
        # the double's task (a5 = it): stand until he lands (his bit of vars+81)
        for k, at in ((0, 'ghost'), (1, 'ghost2')):
            a.label(at)
            a.pcrel(0x41FA, 'vars')          # lea vars(pc),a0
            a.w(0x0828, k, 0x0051)           # btst #k,81(a0)
            a.bccw(0x67, 'gh_gone')
            a.w(0x7001)                      # moveq #1,d0
            a.jsr(0x68D6)                    # sleep 1 frame
            a.bccw(0x60, at)
        a.label('gh_gone')
        a.w(0x08ED, 0x0002, 0x0082)          # bset #2,$82(a5)     remove
        a.jmp(0x6A1A)
    a.label('tscript')                   # step 0: never played (EC moves on before reading)
    a.w(fr(0x4116), 1, 0, 0, 0, 0)
    for f, n, f6, x in TELE_STEPS:
        a.w(fr(f), n, 0, 0, f6, x)
    a.w(0x00D8, 0x0006, 0x0008, 0x0000, 0xFFF8, 0x0000)   # Blade's dash ending
    a.w(0, 0, 0, 0, 0, 0)
    a.label('mstab')                     # (4 * move id, his script - base) words, then -1
    if SCO_TAIL['off'] is not None:      # base: his .PL's tail (SCO_TAIL, patches.scorpion_inputs)
        for mid in sorted(MK_SCRIPTS):
            a.w(4 * mid, SCO_TAIL['offs'][mid])
        a.w(0xFFFF)
    else:                                # base: mstab
        for mid in sorted(MK_SCRIPTS):
            a.w(4 * mid)
            a.wdiff(f'ms_{mid}', 'mstab')
        a.w(0xFFFF)
        for mid, sc in sorted(MK_SCRIPTS.items()):   # header, steps (frames in his numbering), terminator
            a.label(f'ms_{mid}')
            a.out += script_bytes(sc)
    a.label('tp_out')


# Straight-up jump attacks: EC plays the same frames whether Scorpion jumps
# straight up or forward; MK's straight-up kick and punch are near-upright
# poses of their own (tools/lib/mkmoves.py jumpup_*). A hook on EC's step loader
# (FRAME_SITES) swaps the frame as it loads while his horizontal speed is 0.
# PLYR's step loaders: movea.l $AE(a5),a0 ; move.w (a0),$1A(a5) (the main
# script), and $E2 (the attack script a jump attack runs alongside it)
FRAME_SITES = ((0x18174, 0xAE), (0x183F8, 0xAE), (0x1846A, 0xAE), (0x186D8, 0xE2),
               (0x188EE, 0xAE), (0x18B8C, 0xAE))
JUMP_UP = [                   # EC frame (both jumps) -> straight-up pose (scorpion_map jumpup_*)
    (0x4106, 0x4137),         # A (low kick): the kick out
    (0x4003, 0x4136),         # B / C: knee up ...
    (0x4303, 0x4137),         #   ... the kick out
    (0x4107, 0x4138),         # X (low punch): wind up ...
    (0x4108, 0x4139),         #   ... punch
    (0x4208, 0x4138),         # Y (high punch)
    (0x4209, 0x4139),
    (0x420A, 0x4139),
    (0x420B, 0x4138),
]


def r_jumpup(a):
    """From the step-loader stub, a5 = a fighter, $1A just loaded; d0/a0 free."""
    a.w(0x0C6D, SCORPION_ID, 0x004C)     # cmpi.w #id,$4C(a5)  (this block's fighter)
    a.bcc(0x66, 'ju_out')
    if SCORPION_ID in JUMP_FIGHTERS:
        a.bccw(0x61, 'g_jump')           # bsr g_jump          MK's roll (forward / back jumps)
    if SCORPION_ID in KD_FIGHTERS:
        a.bccw(0x61, 'g_kd')             # bsr g_kd            MK's knockdown
    if 'g_ht_cnt' in a.labels or 'd_ht_cnt' in a.labels:   # (its hit drive's tables in the victory room)
        a.bccw(0x61, 'g_hfix')           # bsr g_hfix          MK's hit pose over EC's, as EC loads it
    emit_airland(a)
    a.bccw(0x61, 'airland')              # bsr airland         a jump attack lands in the crouch
    emit_zpose(a)
    a.bccw(0x61, 'zpose')                # bsr zpose           Z held: MK's block pose
    a.w(0x4A6D, 0x005E)                  # tst.w $5E(a5)       moving sideways: a forward/back jump
    a.bcc(0x66, 'ju_out')
    a.w(0x302D, 0x001A)                  # move.w $1A(a5),d0
    a.pcrel(0x41FA, 'ju_tab')            # lea ju_tab(pc),a0
    a.label('ju_lp')
    a.w(0x4A50)                          # tst.w (a0)
    a.bcc(0x67, 'ju_out')
    a.w(0xB058)                          # cmp.w (a0)+,d0
    a.bcc(0x67, 'ju_hit')
    a.w(0x5488)                          # addq.l #2,a0
    a.bcc(0x60, 'ju_lp')
    a.label('ju_hit')
    a.w(0x3B50, 0x001A)                  # move.w (a0),$1A(a5)
    a.label('ju_out')
    a.w(0x4E75)                          # rts
    a.label('ju_tab')
    for f, t in JUMP_UP:
        a.w(fr(f), fr(t))
    a.w(0)


SWEEP_FRAMES = (0x430D, 0x430F)   # Scorpion's sweep (down + C; scorpion_map 'sweep': 43:0E, 43:0F, 43:0D)
KNOCKDOWN = 0x1C              # EC's knockdown: launched at vy -10, vx 5 (16.16 px per tick)
SWEPT_VY = -0x18000           # MK's sweep: feet taken out, falling where they stand (EC has no trip:
                              # every EC sweep is this launch, 69 px up and ~140 px back)


def r_swept(a):
    """Any fighter (a1) just knocked down by Scorpion's sweep: MK drops the
    victim on his back where he stands - barely off the ground, an eighth of the push."""
    a.w(0x3029, 0x00BE)                  # move.w $BE(a1),d0
    a.w(0x0240, 0x7FFF)                  # andi.w #$7FFF,d0
    a.w(0x0C40, KNOCKDOWN)               # cmpi.w #$1C,d0
    a.bccw(0x66, 'sw_out')
    a.w(0x2069, 0x008C)                  # movea.l $8C(a1),a0  the attacker
    a.w(0x0C68, SCORPION_ID, 0x004C)     # cmpi.w #id,$4C(a0)
    a.bccw(0x66, 'sw_out')
    a.w(0x0C28, fr(0x4300) >> 8, 0x001A)  # cmpi.b #sheet,$1A(a0)
    a.bccw(0x66, 'sw_out')
    a.w(0x1028, 0x001B)                  # move.b $1B(a0),d0
    a.w(0x0C00, SWEEP_FRAMES[0] & 0xFF)  # cmpi.b #$0D,d0
    a.bccw(0x65, 'sw_out')               # blo
    a.w(0x0C00, SWEEP_FRAMES[1] & 0xFF)  # cmpi.b #$0F,d0
    a.bccw(0x62, 'sw_out')               # bhi
    a.w(0x0CA9); a.l(-0x90000 & 0xFFFFFFFF); a.w(0x0062)   # cmpi.l #-9.0,$62(a1)
    a.bccw(0x6E, 'sw_out')               # bgt: already tamed (or falling)
    a.w(0x237C); a.l(SWEPT_VY & 0xFFFFFFFF); a.w(0x0062)   # move.l #vy,$62(a1)
    a.w(0x237C); a.l(SWEPT_VY & 0xFFFFFFFF); a.w(0x00CA)   # move.l #vy,$CA(a1)
    a.w(0x2029, 0x005E)                  # move.l $5E(a1),d0
    a.w(0xE680)                          # asr.l #3,d0         an eighth of the push
    a.w(0x2340, 0x005E)                  # move.l d0,$5E(a1)
    a.w(0x2340, 0x00C6)                  # move.l d0,$C6(a1)
    # EC launched her a tick or two before this ran: back down near the floor
    a.w(0x302E, 0x1496)                  # move.w $1496(a6),d0 the floor's y
    a.w(0x5940)                          # subq.w #4,d0
    a.w(0x3340, 0x0052)                  # move.w d0,$52(a1)
    a.w(0x3340, 0x00B6)                  # move.w d0,$B6(a1)
    a.label('sw_out')


SWEEP_MOVE = 0x13             # EC's move id for down + C (the MK fighters' sweep: mkscripts)


def r_swept_by(a):
    """As r_swept, from the attacker's side (a1 = this block's fighter, any MK
    fighter but Scorpion: a generic block runs for its own fighter only, and an
    EC victim has no block): while he sweeps (move SWEEP_MOVE), a victim just
    launched into EC's knockdown (69 px up, ~140 px back: MK's sweep flung
    EC fighters backwards) drops on his back where he stands, as
    MK's sweep. Uses d0/a0."""
    a.w(0x3029, 0x00BE)                  # move.w $BE(a1),d0
    a.w(0x0240, 0x7FFF)                  # andi.w #$7FFF,d0
    a.w(0x0C40, SWEEP_MOVE)              # cmpi.w #$13,d0
    a.bcc(0x66, 'sb_out')
    a.w(0x2069, 0x008C)                  # movea.l $8C(a1),a0  his victim
    a.w(0x3028, 0x00BE)                  # move.w $BE(a0),d0
    a.w(0x0240, 0x7FFF)                  # andi.w #$7FFF,d0
    a.w(0x0C40, KNOCKDOWN)               # cmpi.w #$1C,d0
    a.bcc(0x66, 'sb_out')
    a.w(0x0CA8); a.l(-0x40000 & 0xFFFFFFFF); a.w(0x0062)   # cmpi.l #-4.0,$62(a0)
    a.bcc(0x6E, 'sb_out')               # bgt: already tamed (or falling)
    a.w(0x217C); a.l(SWEPT_VY & 0xFFFFFFFF); a.w(0x0062)   # move.l #vy,$62(a0)
    a.w(0x217C); a.l(SWEPT_VY & 0xFFFFFFFF); a.w(0x00CA)   # move.l #vy,$CA(a0)
    a.w(0x2028, 0x005E)                  # move.l $5E(a0),d0
    a.w(0xE680)                          # asr.l #3,d0         an eighth of the push
    a.w(0x2140, 0x005E)                  # move.l d0,$5E(a0)
    a.w(0x2140, 0x00C6)                  # move.l d0,$C6(a0)
    a.w(0x302E, 0x1496)                  # move.w $1496(a6),d0 the floor's y
    a.w(0x5940)                          # subq.w #4,d0        (launched a tick or two ago)
    a.w(0x3140, 0x0052)                  # move.w d0,$52(a0)
    a.w(0x3140, 0x00B6)                  # move.w d0,$B6(a0)
    a.label('sb_out')


def emit_music(a):
    """f_music (a0 = a disc time: MK's music from the end of EC's last track)
    and the times patches.fatality_music fills in after the 'EKMU' tag."""
    # MK's fatality music (MK CD track 13, appended to EC's last track:
    # cdaudio.add_mk_jingle), started by disc time; patches.fatality_music
    # writes the time after the build has its final layout
    a.label('f_music')                   # a0 = disc time (BCD MMSSFF00)
    a.w(0x48E7, 0xFFFE)                  # movem.l d0-d7/a0-a6,-(sp)
    a.w(0x4A90)                          # tst.l (a0)          (no time: no music)
    a.bcc(0x67, 'fm_out')
    a.w(0x7014)                          # moveq #$14,d0       BIOS MSCPLAYT
    a.jsr(0x6288)                        # (EC's BIOS call + wait)
    a.w(0x303C, 0x0085)                  # move.w #$85,d0      FDRSET: volume as EC sets it
    a.w(0x223C); a.l(0x2B3)              # move.l #$2B3,d1
    a.jsr(0x5F22)
    a.label('fm_out')
    a.w(0x4CDF, 0x7FFF)                  # movem.l (sp)+,d0-d7/a0-a6
    a.w(0x4E75)
    a.l(MUSIC_TAG)
    a.label('f_time')
    a.l(0)                               # BCD MMSSFF00: MK's fatality track
    a.label('f_time_m')
    a.l(0)                               # its music + flame + a man's scream
    a.label('f_time_f')
    a.l(0)                               # ... + a woman's
    a.label('f_time_sz')
    a.l(0)                               # Sub-Zero's spine rip: 13 then 10 with MK's rip sounds
    a.label('f_time_jc')
    a.l(0)                               # Johnny Cage's decapitation: 13 then 10 with its sounds
    a.label('f_time_rd')
    a.l(0)                               # Raiden's electrocution: 13 then 10 with its sounds
    a.label('f_time_lk')
    a.l(0)                               # Liu Kang's uppercut: 13 then 10 with its sounds
    a.label('f_time_sn')
    a.l(0)                               # Sonya's kiss: 13 then 10 with its sounds
    a.label('f_time_kn')
    a.l(0)                               # Kano's heart rip: 13 then 10 with its sounds


def r_fatal(a):
    """MK fatality. Called from r_drag for each fighter (a1, d1 = player x4,
    a2 = vars); returns d0 != 0 if this fighter is taken over by it.
    Trigger (Scorpion, not running): hold Z (MK Block) and tap Up twice - Up is
    removed from his pad word while Z is held so he doesn't jump - with the
    opponent dazed ($BE $1F) at FAT_HP or less. Then both fighters' move tasks
    are parked, the victim placed FAT_GAP px away, and the FATALITY timeline
    plays (frames on both; the victim's palette line becomes Scorpion's for
    fire and skeleton, black for the charred step). At the end the victim's
    health is 0 and Scorpion returns to standing."""
    a.label('fatal')
    a.w(0x48E7, 0x3018)                  # movem.l d2-d3/a3-a4,-(sp)
    a.w(0x4A6A, 0x0018)                  # tst.w 24(a2)        running?
    a.bcc(0x67, 'f_idle')
    a.w(0xB3EA, 0x0022)                  # cmpa.l 34(a2),a1    the victim:
    a.bcc(0x67, 'f_busy')
    a.w(0xB3EA, 0x001E)                  # cmpa.l 30(a2),a1    Scorpion:
    a.bccw(0x66, 'f_out0')
    # his pad reads nothing while it plays (held Z = back would walk him)
    a.w(0x3001)                          # move.w d1,d0        player x4
    a.w(0xE248)                          # lsr.w #1,d0         x2
    a.w(0x41EE, 0x0A3A)                  # lea $A3A(a6),a0     pads
    a.w(0x4270, 0x0000)                  # clr.w (a0,d0.w)
    a.bccw(0x61, 'f_step')               # bsr.w f_step
    a.label('f_busy')
    a.w(0x7001)                          # moveq #1,d0
    a.bccw(0x60, 'f_out')
    a.label('f_idle')
    a.w(0x0C69, SCORPION_ID, 0x004C)     # cmpi.w #9,$4C(a1)
    a.bccw(0x66, 'f_out0')
    a.w(0x47EE, 0x0A3A)                  # lea $A3A(a6),a3     P1 pad ...
    a.w(0x4A41)                          # tst.w d1
    a.bcc(0x67, 'f_pad')
    a.w(0x47EE, 0x0A3C)                  # lea $A3C(a6),a3     ... P2 pad
    a.label('f_pad')
    a.w(0x3401)                          # move.w d1,d2
    a.w(0xE24A)                          # lsr.w #1,d2         0 / 2
    a.w(0x3613)                          # move.w (a3),d3      pad word
    # MK's throw (toward + the button) sends the victim behind him; EC's
    # (close + Y) does that with back held: toward + Y reads as back + Y
    a.w(0x0803, THROW_BIT)               # btst #9,d3          Y held?
    a.bccw(0x67, 'f_nthr')
    a.w(0x0829, 0x0003, 0x0020)          # btst #3,$20(a1)     facing left?
    a.bcc(0x66, 'f_thl')
    a.w(0x0803, 0x0003)                  # btst #3,d3          right = toward
    a.bccw(0x67, 'f_nthr')
    a.w(0x0883, 0x0003)                  # bclr #3,d3
    a.w(0x08C3, 0x0002)                  # bset #2,d3          left = back
    a.bcc(0x60, 'f_thw')
    a.label('f_thl')
    a.w(0x0803, 0x0002)                  # btst #2,d3          left = toward
    a.bccw(0x67, 'f_nthr')
    a.w(0x0883, 0x0002)                  # bclr #2,d3
    a.w(0x08C3, 0x0003)                  # bset #3,d3          right = back
    a.label('f_thw')
    a.w(0x3683)                          # move.w d3,(a3)
    a.label('f_nthr')
    a.w(0x0803, BLOCK_BIT)               # btst #8,d3          Block held?
    a.bcc(0x67, 'f_noz')
    # this runs every other frame (at times every third) and EC shows a quick tap in
    # the pad word for a frame or two: Up in the frame before counts too (EC's reader
    # keeps that pad, $A42 / $A44 = 8(a3)) - a 3-frame tap was lost at 1 timing in 7.
    # (No room for more code: Up goes to bit 15 by a rotate, the saved word's sign)
    assert UP_BIT == 0
    a.w(0x302B, 0x0008)                  # move.w 8(a3),d0     the pad a frame ago
    a.w(0x8043)                          # or.w d3,d0          and now
    a.w(0xE258)                          # ror.w #1,d0         Up -> bit 15
    a.bcc(0x6A, 'f_noup')                # bpl                 Up now ...
    a.w(0x4A72, 0x2030)                  # tst.w 48(a2,d2.w)
    a.bcc(0x6B, 'f_noup')                # bmi                 ... and not before
    a.w(0x5272, 0x2028)                  # addq.w #1,40(a2,d2.w)   one more tap
    a.w(0x35BC, 0x0014, 0x202C)          # move.w #20,44(a2,d2.w)  window
    a.label('f_noup')
    a.w(0x3580, 0x2030)                  # move.w d0,48(a2,d2.w)   (Up in its sign)
    # Z is MK's Block button: EC never sees Z or Up, it sees "back" (= block)
    # MK's Block stands still: no Z, Up, left or right reach EC. EC blocks by
    # holding back, so back is fed only while the opponent attacks ($F6 bit 5
    # clears from the first frame of an attack or jump, measured). Holding back stays EC's walk-
    # back-and-block for everyone.
    a.w(0x0253, 0xFFF2)                  # andi.w #$FFF2,(a3)  no Up, left, right (Z stays: zf keeps it from
                                         #  starting Blade's punch, as for the others; zblock / zpose see it - MK's block pose)
    a.w(0x2869, 0x008C)                  # movea.l $8C(a1),a4  opponent
    a.w(0x082C, 0x0005, 0x00F7)          # btst #5,$F7(a4)     not attacking ($F6 bit 5 clears as an attack starts):
    a.bccw(0x66, 'f_noz2')               # bne                 just stand
    a.w(0x0C6C, DIZZY, 0x00BE)           # cmpi.w #$1F,$BE(a4) dazed (EC's daze is a move: bit 5 clear) -
    a.bccw(0x67, 'f_noz2')               # beq                 FINISH HIM: just stand
    a.w(0x0829, 0x0003, 0x0020)          # btst #3,$20(a1)     facing left?
    a.bcc(0x66, 'f_bl')
    a.w(0x0053, 0x0004)                  # ori.w #4,(a3)       back = left
    a.bcc(0x60, 'f_noz2')
    a.label('f_bl')
    a.w(0x0053, 0x0008)                  # ori.w #8,(a3)       back = right
    a.label('f_noz2')
    a.bcc(0x60, 'f_win')
    a.label('f_noz')
    a.w(0x3583, 0x2030)                  # move.w d3,48(a2,d2.w)
    a.w(0x4272, 0x2028)                  # clr.w 40(a2,d2.w)
    a.label('f_win')
    a.w(0x4A72, 0x202C)                  # tst.w 44(a2,d2.w)
    a.bcc(0x67, 'f_chk')
    a.w(0x5372, 0x202C)                  # subq.w #1,44(a2,d2.w)
    a.bcc(0x66, 'f_chk')
    a.w(0x4272, 0x2028)                  # clr.w 40(a2,d2.w)   window over
    a.label('f_chk')
    a.w(0x0C72, 0x0002, 0x2028)          # cmpi.w #2,40(a2,d2.w)
    a.bccw(0x6D, 'f_out0')               # blt
    a.w(0x4272, 0x2028)                  # clr.w 40(a2,d2.w)
    a.w(0x2669, 0x008C)                  # movea.l $8C(a1),a3  opponent
    a.w(0x302B, 0x00BE)                  # move.w $BE(a3),d0
    a.w(0x0240, 0x7FFF)                  # andi.w #$7FFF,d0    (bit 15: a daze step ending - it flips
    a.w(0x0C40, DIZZY)                   # cmpi.w #$1F,d0       every few frames: the input was lost then)
    a.bccw(0x66, 'f_out0')
    a.w(0xB7EA, 0x0034)                  # cmpa.l 52(a2),a3    only in the FINISH HIM window
    a.bccw(0x66, 'f_out0')
    a.w(0x42AA, 0x0034)                  # clr.l 52(a2)
    # start
    a.w(0x357C, 0x0001, 0x0018)          # move.w #1,24(a2)
    a.w(0x426A, 0x001A)                  # clr.w 26(a2)
    a.w(0x426A, 0x001C)                  # clr.w 28(a2)
    a.w(0x2549, 0x001E)                  # move.l a1,30(a2)
    a.w(0x254B, 0x0022)                  # move.l a3,34(a2)
    a.w(0x356B, 0x001A, 0x0026)          # move.w $1A(a3),38(a2)
    a.w(0x42AA, 0x0008)                  # clr.l 8(a2)         no daze timer
    # stop his animation script too ($AE = current step's frame word): EC's walk cycle
    # (held Z = back) would otherwise play out over the first steps
    a.pcrel(0x41FA, 'f_hold')            # lea f_hold(pc),a0
    a.w(0x5888)                          # addq.l #4,a0        ($AE points at a step's frame word)
    a.w(0x2348, 0x00AE)                  # move.l a0,$AE(a1)
    a.pcrel(0x49FA, 'park')              # lea park(pc),a4
    for obj in (0x2069, 0x206B):         # movea.l $88(a1|a3),a0
        a.w(obj, 0x0088)
        a.w(0x2050)                      # movea.l (a0),a0     move task
        a.w(0x214C, 0x0004)              # move.l a4,4(a0)
        a.w(0x4268, 0x0008)              # clr.w 8(a0)
    a.w(0x3029, 0x00B2)                  # move.w $B2(a1),d0
    a.w(0x362B, 0x00B2)                  # move.w $B2(a3),d3
    a.w(0xB640)                          # cmp.w d0,d3
    a.bcc(0x6C, 'f_right')               # bge
    a.w(0x0440, FAT_GAP)                 # subi.w #gap,d0
    a.bcc(0x60, 'f_setx')
    a.label('f_right')
    a.w(0x0640, FAT_GAP)                 # addi.w #gap,d0
    a.label('f_setx')
    a.w(0x3740, 0x00B2)                  # move.w d0,$B2(a3)
    a.w(0x3740, 0x004E)                  # move.w d0,$4E(a3)
    a.w(0x3769, 0x00B6, 0x00B6)          # move.w $B6(a1),$B6(a3)
    a.w(0x3769, 0x00B6, 0x0052)          # move.w $B6(a1),$52(a3)
    a.w(0x42AB, 0x00C6)                  # clr.l $C6(a3)
    a.w(0x42A9, 0x00C6)                  # clr.l $C6(a1)
    a.w(0x426B, 0x015E)                  # clr.w $15E(a3)      EC's daze loop ended (as the generic
                                         #  fatality: else EC's stepper puts her script back to her daze)
    a.bccw(0x61, 'f_dark')               # bsr.w f_dark        MK: the stage goes dark
    # the music again, now with MK's flame and scream mixed in where the fire hits
    a.pcrel(0x41FA, 'f_time_m')          # lea f_time_m(pc),a0 a man's scream ...
    a.w(0x302B, 0x004C)                  # move.w $4C(a3),d0
    for fid in FEMALE:
        a.w(0x0C40, fid)                 # cmpi.w #id,d0
        a.bcc(0x66, f'f_w{fid}')
        a.pcrel(0x41FA, 'f_time_f')      # ... or a woman's
        a.label(f'f_w{fid}')
    a.bccw(0x61, 'f_music')
    a.w(0x7001)                          # moveq #1,d0
    a.bcc(0x60, 'f_out')
    a.label('f_out0')
    a.w(0x7000)                          # moveq #0,d0
    a.label('f_out')
    a.w(0x4CDF, 0x180C)                  # movem.l (sp)+,d2-d3/a3-a4
    a.w(0x4E75)
    # halve the colours of the palette lines neither fighter uses (the stage)
    a.label('f_dark')
    a.w(0x7400)                          # moveq #0,d2         line
    a.label('fd_line')
    a.w(0x3029, 0x007A)                  # move.w $7A(a1),d0
    a.w(0x0240, 0x0003)                  # andi.w #3,d0
    a.w(0x0A40, 0x0001)                  # eori.w #1,d0        Scorpion's line
    a.w(0xB042)                          # cmp.w d2,d0
    a.bcc(0x67, 'fd_next')
    a.w(0x302B, 0x007A)                  # move.w $7A(a3),d0
    a.w(0x0240, 0x0003)
    a.w(0x0A40, 0x0001)                  # victim's line
    a.w(0xB042)
    a.bcc(0x67, 'fd_next')
    a.w(0x49EE, 0x96AA)                  # lea -$6956(a6),a4   palette buffer
    a.w(0x3002)                          # move.w d2,d0
    a.w(0xEB48)                          # lsl.w #5,d0
    a.w(0xD8C0)                          # adda.w d0,a4
    a.w(0x700F)                          # moveq #15,d0
    a.label('fd_col')
    a.w(0x3614)                          # move.w (a4),d3
    a.w(0xE24B)                          # lsr.w #1,d3
    a.w(0x0243, 0x0EEE)                  # andi.w #$0EEE,d3    each of B, G, R halved
    a.w(0x38C3)                          # move.w d3,(a4)+
    a.dbra(0, 'fd_col')
    a.label('fd_next')
    a.w(0x5242)                          # addq.w #1,d2
    a.w(0x0C42, 0x0004)                  # cmpi.w #4,d2
    a.bcc(0x6D, 'fd_line')               # blt
    a.w(0x3D7C, 0xFFFF, 0x982C)          # move.w #$FFFF,-$67D4(a6)  palette changed
    a.w(0x4E75)
    emit_music(a)
    # two animation-script steps that hold the fatality's first frame ~9 min
    a.label('f_hold')
    for _ in range(2):
        a.w(0x0000, 0x0000, fr(FATALITY_BLADE[0][1]), 0x7FFF, 0x0000, 0x0000)
    # a parked task: do nothing, every frame
    a.label('park')
    a.w(0x7001)                          # moveq #1,d0
    a.jsr(0x68D6)
    a.bcc(0x60, 'park')
    # one timeline call (a1 = Scorpion)
    a.label('f_step')
    a.w(0x206A, 0x0022)                  # movea.l 34(a2),a0   her daze loop kept ended (as gk_step)
    a.w(0x4268, 0x015E)                  # clr.w $15E(a0)
    # no move of hers starts while it plays: a CPU loser's request ($BE bit 15, with $100
    # bit 0) made EC start her own move - her own frames, from a .PL her death art replaced
    a.w(0x0828, 0x0007, 0x00BE)          # btst #7,$BE(a0)
    a.bcc(0x67, 'f_nrq')
    a.w(0x4268, 0x00BE)                  # clr.w $BE(a0)
    a.w(0x08A8, 0x0000, 0x0101)          # bclr #0,$101(a0)
    a.label('f_nrq')
    a.pcrel(0x49FA, 'fattab')            # lea fattab(pc),a4
    a.w(0x342A, 0x001A)                  # move.w 26(a2),d2
    a.w(0xE74A)                          # lsl.w #3,d2
    a.w(0xD8C2)                          # adda.w d2,a4
    a.w(0x4A54)                          # tst.w (a4)
    a.bccw(0x67, 'f_end')
    a.w(0x526A, 0x001C)                  # addq.w #1,28(a2)
    a.w(0x362A, 0x001C)                  # move.w 28(a2),d3
    a.w(0xB654)                          # cmp.w (a4),d3
    a.bcc(0x6D, 'f_apply')               # blt
    a.w(0x426A, 0x001C)                  # clr.w 28(a2)
    a.w(0x526A, 0x001A)                  # addq.w #1,26(a2)
    a.w(0x504C)                          # addq.w #8,a4
    a.w(0x4A54)                          # tst.w (a4)
    a.bccw(0x67, 'f_end')
    a.label('f_apply')
    a.w(0x7400)                          # moveq #0,d2         d2: his pose changes now
    a.w(0x362C, 0x0002)                  # move.w 2(a4),d3
    a.bcc(0x67, 'f_nos')
    a.w(0xB669, 0x001A)                  # cmp.w $1A(a1),d3
    a.bcc(0x67, 'f_same')
    a.w(0x7401)                          # moveq #1,d2
    a.label('f_same')
    a.w(0x3343, 0x001A)                  # move.w d3,$1A(a1)   Scorpion's frame
    a.label('f_nos')
    a.w(0x266A, 0x0022)                  # movea.l 34(a2),a3   victim
    a.w(0x362C, 0x0004)                  # move.w 4(a4),d3     mode
    a.bcc(0x67, 'f_ret')
    a.w(0x0C43, 0x0002)                  # cmpi.w #2,d3
    a.bcc(0x67, 'f_char')
    # Scorpion player 2: a player-1 victim's poses are unpacked by the main CPU
    # ($2A bit 8: SUB $1178E), which can't reach player 2's art in PRG RAM
    # (garbled, or a hang): unpacked here instead, as player 2's own are
    # Both unpacked by the sub CPU then: its unpacker keeps one job in progress
    # (-$3F6E(a6)), so the victim's new pose waits a call when Scorpion's
    # changes on this one (else the two jobs garble each other)
    a.w(0xB3FC); a.l(0x2E330)            # cmpa.l #P2,a1
    a.bcc(0x66, 'f_p1v')
    a.w(0x4A42)                          # tst.w d2
    a.bcc(0x66, 'f_ret')
    a.w(0x08AB, 0x0000, 0x002A)          # bclr #0,$2A(a3)     (bit 8 of the word)
    a.label('f_p1v')
    a.w(0x376C, 0x0006, 0x001A)          # move.w 6(a4),$1A(a3)
    # in Scorpion's colours: her sprites take his palette line ($20 bits 13-14),
    # which shows on the same frame as the pose (copying his colours into her
    # line showed a frame early: her own pose flashed in his colours)
    a.w(0x3629, 0x0020)                  # move.w $20(a1),d3
    a.w(0x0243, 0x6000)                  # andi.w #$6000,d3    his line
    a.label('f_line')
    a.w(0x026B, 0x9FFF, 0x0020)          # andi.w #$9FFF,$20(a3)
    a.w(0x876B, 0x0020)                  # or.w d3,$20(a3)
    a.label('f_ret')
    a.w(0x4E75)
    a.label('f_char')
    a.w(0xB3FC); a.l(0x2E330)            # cmpa.l #P2,a1       a player-1 victim's own pose:
    a.bcc(0x66, 'f_chp1')                #  the main CPU's again (bit 8 back)
    a.w(0x08EB, 0x0000, 0x002A)          # bset #0,$2A(a3)
    a.label('f_chp1')
    a.w(0x376A, 0x0026, 0x001A)          # move.w 38(a2),$1A(a3)   his own pose ...
    a.w(0x362B, 0x007A)                  # move.w $7A(a3),d3   ... on his own line again
    a.w(0x0243, 0x0003)                  # andi.w #3,d3
    a.w(0x0A43, 0x0001)                  # eori.w #1,d3        (sprite line = $7A&3 ^ 1)
    a.w(0xE65B)                          # ror.w #3,d3         -> bits 13-14
    a.bccw(0x61, 'f_line')
    a.w(0x7401)                          # moveq #1,d2         ... in black
    a.bccw(0x60, 'f_pal2')
    a.label('f_end')
    a.w(0x426A, 0x0018)                  # clr.w 24(a2)
    a.w(0x266A, 0x0022)                  # movea.l 34(a2),a3
    a.w(0x426B, 0x0076)                  # clr.w $76(a3)       no health left
    a.w(0x2069, 0x0088)                  # movea.l $88(a1),a0
    a.w(0x2050)                          # movea.l (a0),a0
    a.pcrel(0x47FA, 'f_kill')            # lea f_kill(pc),a3
    a.w(0x214B, 0x0004)                  # move.l a3,4(a0)     Scorpion's move task -> f_kill
    a.w(0x4268, 0x0008)                  # clr.w 8(a0)
    a.w(0x4E75)
    # Scorpion's move task, as EC's own finishers do it (Blade's Vendetta,
    # BLA.CO $1D2D2 + BLA.VC): music cue 3, then $6D28 = PLYR.CO $19472,
    # which parks both fighters, zeroes the victim and records him at
    # $1490(a6). It hides the victim; we keep the bones on screen. Then, like
    # BLA.VC: round-end type $1CD4 = 3 (finisher), and after a pause on the
    # bones, $AB7 bits 0+1 make SUB.BIN's fight runner ($BDDA) leave the round.
    a.label('f_kill')
    a.jsr(0x6D28)
    a.w(0x266D, 0x008C)                  # movea.l $8C(a5),a3
    a.w(0x08EB, 0x0007, 0x0082)          # bset #7,$82(a3)     victim stays drawn
    a.w(0x3D7C, 0x0003, 0x1CD4)          # move.w #3,$1CD4(a6) round won by a finisher
    for _ in range(1 + GK_HOLD):         # (held while MK's announcer speaks, as the others)
        a.w(0x7000 | FAT_PAUSE)          # moveq #pause,d0
        a.jsr(0x68D6)                    # sleep
    a.w(0x08EE, 0x0000, 0x0AB7)          # bset #0,$AB7(a6)
    a.w(0x08EE, 0x0001, 0x0AB7)          # bset #1,$AB7(a6)    round over
    a.bccw(0x60, 'park')
    # victim's palette line <- Scorpion's (d2 = 0) or black (d2 = 1)
    a.label('f_pal')
    a.w(0x7400)                          # moveq #0,d2
    a.label('f_pal2')
    a.w(0x3629, 0x007A)                  # move.w $7A(a1),d3   Scorpion's line ...
    a.w(0x0243, 0x0003)                  # andi.w #3,d3
    a.w(0x0A43, 0x0001)                  # eori.w #1,d3        (sprite line = $7A&3 ^ 1)
    a.w(0xEB4B)                          # lsl.w #5,d3
    a.w(0x41EE, 0x96AA)                  # lea -$6956(a6),a0   palette buffer
    a.w(0xD0C3)                          # adda.w d3,a0
    a.w(0x362B, 0x007A)                  # move.w $7A(a3),d3   victim's line
    a.w(0x0243, 0x0003)                  # andi.w #3,d3
    a.w(0x0A43, 0x0001)                  # eori.w #1,d3
    a.w(0xEB4B)                          # lsl.w #5,d3
    a.w(0x49EE, 0x96AA)                  # lea -$6956(a6),a4
    a.w(0xD8C3)                          # adda.w d3,a4
    a.w(0x700F)                          # moveq #15,d0
    a.label('f_pl')
    a.w(0x4A42)                          # tst.w d2
    a.bcc(0x66, 'f_blk')
    a.w(0x38D8)                          # move.w (a0)+,(a4)+
    a.bcc(0x60, 'f_pn')
    a.label('f_blk')
    a.w(0x425C)                          # clr.w (a4)+
    a.label('f_pn')
    a.dbra(0, 'f_pl')
    a.w(0x3D7C, 0xFFFF, 0x982C)          # move.w #$FFFF,-$67D4(a6)  palette changed
    a.w(0x4E75)
    a.label('fattab')
    for row in FATALITY:
        a.w(*row)
    a.w(0, 0, 0, 0)


def r_finish(a, full=True):
    """After a hit's damage (a3 = victim, health already clamped at 0).
    MK rule: the blow that would win Scorpion the match (EC's own test, as
    its finishers use it) leaves the loser on 1 health; r_drag dazes him and
    runs the FINISH HIM window. A blow inside the window is an ordinary KO.
    full=False (a generic fighter's block, one per slot): in a mirror match
    the winner's own slot's block takes it (its vars are the ones his r_drag
    and fatality input read)."""
    a.label('finish')
    a.w(0x4A6B, 0x0076)                  # tst.w $76(a3)
    a.bccw(0x6E, 'fi_out')               # bgt: still alive
    a.pcrel(0x41FA, 'vars')              # lea vars(pc),a0
    a.w(0xB7E8, 0x0034)                  # cmpa.l 52(a0),a3    in the window:
    a.bcc(0x66, 'fi_new')
    a.w(0x4A68, 0x0038)                  # tst.w 56(a0)        grace over: this blow KOs ...
    if SCORPION_ID in FATALS:            # ... unless his fatality input is one step from done (its last
        a.bcc(0x66, 'fi_keep')           #  press - forward / back + the button - can start EC's own attack
        a.w(0x0C68, len(FATALS[SCORPION_ID]['taps']) - 1, 0x0028)   # cmpi.w #2,40(a0)   before his code sees it)
        a.bccw(0x6D, 'fi_out')           # blt: an ordinary KO
        a.w(0x226B, 0x008C)              # movea.l $8C(a3),a1  the winner's pad:
        a.w(0x302E, 0x0A3A)              # move.w $A3A(a6),d0
        a.w(0xB3FC); a.l(0x2E188)        # cmpa.l #P1,a1
        a.bcc(0x67, 'fi_p1')
        a.w(0x302E, 0x0A3C)              # move.w $A3C(a6),d0
        a.label('fi_p1')
        a.w(0x0800, 0x0001)              # btst #1,d0          down held (a crouching attack, the uppercut):
        a.bccw(0x66, 'fi_out')           #  an ordinary blow (it KOs; on the Pit it throws her in)
        a.w(0x0240, 0x000C)              # andi.w #$C,d0       no left / right: not the fatality's press
        a.bccw(0x67, 'fi_out')
        a.label('fi_keep')
    else:
        a.bccw(0x67, 'fi_out')
    a.w(0x377C, 0x0001, 0x0076)          # move.w #1,$76(a3)   the rest of the winning blow doesn't count
    a.bccw(0x60, 'fi_out')
    a.label('fi_new')
    a.w(0x4AA8, 0x0034)                  # tst.l 52(a0)        (someone else's window)
    a.bccw(0x66, 'fi_out')
    a.w(0x4A68, 0x0018)                  # tst.w 24(a0)        fatality running
    a.bccw(0x66, 'fi_out')
    a.w(0x226B, 0x008C)                  # movea.l $8C(a3),a1  winner
    a.w(0x0C69, SCORPION_ID, 0x004C)     # cmpi.w #9,$4C(a1)
    a.bccw(0x66, 'fi_fwd')               # not this block's fighter: his own block's FINISH HIM
    if not full:                         # a mirror match: the stubs call player 1's block,
        a.w(0x2009)                      # move.l a1,d0         a player-2 winner's is the other
        a.bccw(0x61, 'mine')             # bsr mine
        a.bccw(0x66, 'fi_fwd')           # bne: the other slot's block (same fighter)
    a.w(0x302E, 0x1D26)                  # move.w $1D26(a6),d0  (EC: PLYR.CO $15EC6)
    a.w(0x082B, 0x0000, 0x007B)          # btst #0,$7B(a3)
    a.bcc(0x66, 'fi_w')
    a.w(0x302E, 0x1D28)                  # move.w $1D28(a6),d0
    a.label('fi_w')
    a.w(0x5240)                          # addq.w #1,d0
    a.w(0x122E, 0x1CFE)                  # move.b $1CFE(a6),d1
    a.w(0x4881)                          # ext.w d1
    a.w(0x43F9); a.l(FINISH_TABLE)       # lea table,a1
    a.w(0xB031, 0x1000)                  # cmp.b (a1,d1.w),d0
    a.bccw(0x6D, 'fi_out')               # blt: not the deciding round
    a.w(0x377C, 0x0001, 0x0076)          # move.w #1,$76(a3)
    a.w(0x214B, 0x0034)                  # move.l a3,52(a0)
    a.w(0x317C, FINISH_GRACE, 0x0038)    # move.w #grace,56(a0)
    a.w(0x317C, FINISH_CALLS, 0x003C)    # move.w #calls,60(a0)
    a.w(0x317C, 0x0001, 0x003A)          # move.w #1,58(a0)
    a.label('fi_out')
    a.w(0x4E75)
    # MK vs MK: this hook is fight-wide, so only one block hears it (the full
    # one, or player 1's); the winner's own block decides his FINISH HIM
    a.label('fi_fwd')
    a.bccw(0x61, 'oth')                  # bsr oth             a0 = the other slot's block
    a.bcc(0x66, 'fi_out')
    a.w(0x3029, 0x004C)                  # move.w $4C(a1),d0
    a.w(0xB068, 0x0004)                  # cmp.w 4(a0),d0      the winner's?
    a.bcc(0x66, 'fi_out')
    a.w(0x4EE8, RAW + 4 * ENTRIES.index('finish'))   # jmp raw finish(a0)


def r_launch(a):
    """Fighter hit path, after the reaction is set (a5 attacker, a3 victim).
    Scorpion's uppercut (MK: down + high punch) launches the victim like MK:
    knock-down reaction, and r_drag flies him along MK's arc (peak ~150 px,
    ~68 frames, ~90 px back). Uses d0/a0 (saved by the stub).
    Every hit also sprays blood (r_blood)."""
    a.jsr(SUB_AT['blood'])               # jsr blood (SUB.BIN)
    # MK has no white hit sparks: EC spawns its spark at $1444/$1446 right
    # after this hook; with an MK fighter in the hit it goes off-screen
    a.w(0x302D, 0x004C)                  # move.w $4C(a5),d0
    a.jsr(SUB_AT['mkrow'])               # jsr mkrow (SUB.BIN)
    a.w(0x4A10)                          # tst.b (a0)
    a.bcc(0x66, 'l_nospark')
    a.w(0x302B, 0x004C)                  # move.w $4C(a3),d0
    a.jsr(SUB_AT['mkrow'])
    a.w(0x4A10)                          # tst.b (a0)
    a.bcc(0x67, 'l_spark')
    a.label('l_nospark')
    a.w(0x3D7C, 0xFE00, 0x1444)          # move.w #-512,$1444(a6)
    a.label('l_spark')
    # an MK fighter's uppercut: his own 42:02-42:04 (the strike 42:03)
    a.w(0x302D, 0x004C)                  # move.w $4C(a5),d0
    a.jsr(SUB_AT['mkrow'])
    a.w(0x302D, 0x001A)                  # move.w $1A(a5),d0    his frame
    a.w(0x9068, 0x0002)                  # sub.w 2(a0),d0       - his 42:02 (0: not MK, never <= 2)
    a.w(0x0C40, (0x4009 - 0x4202) & 0xFFFF)   # cmpi.w #(40:09 - 42:02),d0: down + X's strike,
    a.bcc(0x67, 'l_up')                  # beq                 the other crouching punch (MK CD: also the uppercut)
    a.w(0x0C40, 0x0002)                  # cmpi.w #2,d0
    a.bccw(0x62, 'l_out')                # bhi
    a.label('l_up')
    a.w(0x377C, KNOCKDOWN, 0x0118)       # move.w #$1C,$118(a3)
    a.pcrel(0x41FA, 'vars')              # lea vars(pc),a0
    a.w(0x214B, 0x000E)                  # move.l a3,14(a0)
    a.w(0x317C, LAUNCH_VY, 0x0012)       # move.w #vy,18(a0)
    a.w(0x316D, 0x00B6, 0x0014)          # move.w $B6(a5),20(a0)   ground = Scorpion's feet (victim may be mid-jump)
    a.w(0x302B, 0x00B2)                  # move.w $B2(a3),d0
    a.w(0x906D, 0x00B2)                  # sub.w $B2(a5),d0
    a.bcc(0x6A, 'l_r')                   # bpl
    a.w(0x317C, -LAUNCH_DX, 0x0016)      # move.w #-dx,22(a0)
    a.bcc(0x60, 'l_out')
    a.label('l_r')
    a.w(0x317C, LAUNCH_DX, 0x0016)       # move.w #dx,22(a0)
    a.label('l_out')
    a.w(0x4E75)


def r_hit_f(a):
    """r_hit_f: the fighter's own hit - r_hit's body (after r_hit_p's entry) with d2 = 0."""
    a.w(0x2F02)                          # move.l d2,-(sp)
    a.w(0x7400)                          # moveq #0,d2         (his own hit)
    a.bccw(0x60, 'h_common')


def r_hit(a):
    """Hit routine (after the displaced sound-id copy), entry r_hit_p: d2 = 1, the rope object's hit
    (r_hit_f: d2 = 0, the fighter's own - one body for both, the block's room). a5 = attacker (the
    fighter, or the rope object, owner at $8C), a3 = victim. First contact of Scorpion's spear: the
    hit sound is his voice (and the victim staggers instead of the rope's own reaction). Repeat
    contacts while the victim is reeling: no damage, reaction or sound. Uses a0 (saved by the stub);
    keeps d2."""
    a.w(0x2F02)                          # move.l d2,-(sp)
    a.w(0x7401)                          # moveq #1,d2         (the rope's)
    a.label('h_common')
    a.w(0x204D)                          # movea.l a5,a0
    a.w(0x0C68, SCORPION_ID, 0x004C)     # cmpi.w #9,$4C(a0)
    a.bcc(0x67, 'h_chk')
    a.w(0x206D, 0x008C)                  # movea.l $8C(a5),a0  owner
    a.label('h_chk')
    a.w(0x0C68, SPEAR_MOVE, 0x00BE)      # cmpi.w #$34,$BE(a0)
    a.bccw(0x66, 'h_out')
    a.w(0x0C68, SCORPION_ID, 0x004C)     # cmpi.w #9,$4C(a0)
    a.bccw(0x66, 'h_out')
    # the spear's one strike step shows 42:2F (its hold is on 42:30 now): that contact is the hit,
    # though EC has set his reaction already ($1B) by the time this runs (traced: no scream played)
    a.w(0x0C68, fr(0x422F), 0x001A)      # cmpi.w #42:2F,$1A(a0)
    a.bcc(0x67, 'h_first')
    a.w(0x0C6B, HIT_FIRST, 0x00BE)       # cmpi.w #$1A,$BE(a3)
    a.bcc(0x6D, 'h_first')               # blt
    a.w(0x0C6B, HIT_LAST, 0x00BE)        # cmpi.w #$1D,$BE(a3)
    a.bcc(0x6E, 'h_first')               # bgt
    a.w(0x4A02)                          # tst.b d2
    a.bcc(0x67, 'h_rf')
    a.w(0x422D, 0x0078)                  # clr.b $78(a5)        damage 0 (the rope)
    a.w(0x426D, 0x00A4)                  # clr.w $A4(a5)        no new reaction
    a.bcc(0x60, 'h_rx')
    a.label('h_rf')
    a.w(0x422D, 0x0102)                  # clr.b $102(a5)       (his own)
    a.label('h_rx')
    a.w(0x426E, 0x1640)                  # clr.w $1640(a6)      no sound
    a.bcc(0x60, 'h_out')
    a.label('h_first')
    # MK: the victim screams at the hit (a man's or a woman's); GET OVER HERE comes with the yank (r_drag)
    a.w(0x48E7, 0xC000)                  # movem.l d0-d1,-(sp)
    a.w(0x3D7C, SCREAM_M, 0x1640)        # move.w #MALEHURT,$1640(a6)
    a.w(0x322B, 0x004C)                  # move.w $4C(a3),d1    the victim
    a.w(0x203C); a.l(FEMALE_MASK)        # move.l #women,d0
    a.w(0x0300)                          # btst d1,d0
    a.bcc(0x67, 'h_man')
    a.w(0x3D7C, SCREAM_F, 0x1640)        # move.w #GIRLHURT,$1640(a6)
    a.label('h_man')
    a.pcrel(0x41FA, 'vars')              # lea vars(pc),a0
    a.w(0x42A8, 92)                      # clr.l 92(a0)         the yank's line still to say
    # speared in the air: EC's knockdown takes him (r_drag neither holds, pulls nor dazes him: dazed
    # mid-fall, EC's landing code looped in his task, its thud flooding the sound queue - a hang)
    a.w(0x42A8, 96)                      # clr.l 96(a0)
    a.w(0x302B, 0x0052)                  # move.w $52(a3),d0    his y
    a.w(0x5840)                          # addq.w #4,d0
    a.w(0xB06E, 0x1496)                  # cmp.w $1496(a6),d0   the floor
    a.bcc(0x6C, 'h_gnd')                 # bge: on it
    a.w(0x214B, 96)                      # move.l a3,96(a0)     in the air
    a.label('h_gnd')
    a.w(0x4CDF, 0x0003)                  # movem.l (sp)+,d0-d1
    a.w(0x4A02)                          # tst.b d2
    a.bcc(0x67, 'h_out')
    a.w(0x3B7C, STAGGER, 0x00A4)         # move.w #$1B,$A4(a5)  (the rope's hit)
    a.jsr(SUB_AT['blood_body'])          # jsr blood_body       MK: the spear draws blood
    a.label('h_out')
    a.w(0x241F)                          # move.l (sp)+,d2
    a.w(0x4E75)                          # rts


ENTRIES = ('taps', 'ai', 'drag', 'hit_f', 'hit_p', 'launch', 'finish', 'jumpup')
PER_FIGHTER = {'drag': 1, 'jumpup': 5}          # entry -> the fighter's register (a1 / a5)
HEAD = 8                                        # MAGIC, fighter id, full flag
RAW = HEAD + 4 * len(ENTRIES)                   # the raw routines' table


def _block(a, full, fid, raws):
    """Every MK fighter's module carries a block at EXT_OFF (the PLYR stubs
    find the first one by MAGIC, player 1's slot first):
      +0 MAGIC, +4 fighter id, +6 full (Scorpion's: spear, FINISH HIM, blood,
      fatality - fight-wide, by fighter id); +8 entries (bra.w), one per
      ENTRIES name, called by the stubs; RAW: the same, straight to this
      block's routines.
    An entry runs the right block(s): for per-fighter hooks (walk, throw,
    jump attacks) the block of the fighter's own slot, plus a full block
    anywhere (its routines act on its fighter and his victims); for the
    fight-wide hooks, the full block. Two full blocks of one fighter (a
    mirror match): only the first, as before."""
    a.label('base')
    a.l(MAGIC)
    a.w(fid)
    a.w(1 if full else 0)
    for n in ENTRIES:
        a.bccw(0x60, f'w_{n}')
    for n in ENTRIES:
        a.bccw(0x60, f'r_{n}' if n in raws else 'r_null')
    a.label('r_null')
    a.w(0x4E75)
    # oth: a0 = the other slot's block, Z set if there is one
    a.label('oth')
    a.pcrel(0x41FA, 'base')              # lea base(pc),a0
    a.w(0xB1FC); a.l(SLOTS[0] + EXT_OFF)  # cmpa.l #slot0,a0
    a.bcc(0x66, 'oth1')
    a.w(0x41F9); a.l(SLOTS[1] + EXT_OFF)  # lea slot1,a0
    a.bcc(0x60, 'oth2')
    a.label('oth1')
    a.w(0x41F9); a.l(SLOTS[0] + EXT_OFF)  # lea slot0,a0
    a.label('oth2')
    a.w(0x0C90); a.l(MAGIC)              # cmpi.l #MAGIC,(a0)
    a.w(0x4E75)
    # mine: Z set if the fighter in d0 is this block's slot's (P1 <-> slot 0)
    a.label('mine')
    a.w(0x2F08)                          # move.l a0,-(sp)
    a.pcrel(0x41FA, 'base')              # lea base(pc),a0
    a.w(0xB1FC); a.l(SLOTS[0] + EXT_OFF)  # cmpa.l #slot0,a0
    a.w(0x205F)                          # movea.l (sp)+,a0   (flags kept)
    a.bcc(0x66, 'mine1')
    a.w(0xB0BC); a.l(0x2E188)            # cmp.l #P1,d0
    a.w(0x4E75)
    a.label('mine1')
    a.w(0xB0BC); a.l(0x2E330)            # cmp.l #P2,d0
    a.w(0x4E75)
    for i, n in enumerate(ENTRIES):
        a.label(f'w_{n}')
        if n in PER_FIGHTER:
            reg = PER_FIGHTER[n]
            a.w(0x48E7, 0xFFFE)          # movem.l d0-d7/a0-a6,-(sp)
            if not full:
                a.w(0x2008 | reg)        # move.l a1/a5,d0
                a.bccw(0x61, 'mine')     # bsr mine
                a.bccw(0x66, f'wo_{n}')  # not mine: skip own
            a.bccw(0x61, f'r_{n}' if n in raws else 'r_null')
            a.w(0x4CD7, 0x7FFF)          # movem.l (sp),d0-d7/a0-a6   (back, kept on the stack)
            a.label(f'wo_{n}')
            a.bccw(0x61, 'oth')
            a.bccw(0x66, f'wd_{n}')      # no other block
            a.w(0x4A68, 0x0006)          # tst.w 6(a0)         other full?
            a.bcc(0x67, f'wn_{n}')
            if full:
                a.w(0x3028, 0x0004)      # move.w 4(a0),d0     a mirror of a full block: skip
                a.w(0xB07C, fid)         # cmp.w #fid,d0
                a.bccw(0x67, f'wd_{n}')
            a.bcc(0x60, f'wc_{n}')
            a.label(f'wn_{n}')
            a.w(0x2008 | reg)            # move.l a1/a5,d0     other generic: only its own fighter
            a.w(0x2F08)                  # move.l a0,-(sp)
            a.bccw(0x61, 'mine')
            a.w(0x205F)                  # movea.l (sp)+,a0
            a.bccw(0x67, f'wd_{n}')      # mine, so not his
            a.label(f'wc_{n}')
            a.w(0x41E8, RAW + 4 * i)     # lea raw(a0),a0
            a.w(0x2F08)                  # move.l a0,-(sp)     target
            a.pcrel(0x487A, f'wr_{n}')   # pea wr(pc)          return here
            a.w(0x2F2F, 0x0004)          # move.l 4(sp),-(sp)  target again (for the rts)
            a.w(0x4CEF, 0x7FFF, 0x000C)  # movem.l 12(sp),d0-d7/a0-a6
            a.w(0x4E75)                  # rts -> the other block, back to wr
            a.label(f'wr_{n}')
            a.w(0x588F)                  # addq.l #4,sp
            a.label(f'wd_{n}')
            a.w(0x4CDF, 0x7FFF)          # movem.l (sp)+,d0-d7/a0-a6
            a.w(0x4E75)
        elif full or n == 'ai':          # (the CPU filter: every block has the whole table)
            a.bccw(0x60, f'r_{n}' if n in raws else 'r_null')
        else:
            # a fight-wide hook in a generic block: the other slot's full block does it
            a.w(0x598F)                  # subq.l #4,sp        a slot for the target
            a.w(0x2F08)                  # move.l a0,-(sp)     [a0][slot]
            a.bccw(0x61, 'oth')
            a.bccw(0x66, f'gn_{n}')
            a.w(0x4A68, 0x0006)          # tst.w 6(a0)
            a.bccw(0x67, f'gn_{n}')
            a.w(0x41E8, RAW + 4 * i)     # lea raw(a0),a0
            a.w(0x2F48, 0x0004)          # move.l a0,4(sp)     slot = target
            a.w(0x205F)                  # movea.l (sp)+,a0
            a.w(0x4E75)                  # rts -> target
            a.label(f'gn_{n}')
            a.w(0x205F)                  # movea.l (sp)+,a0
            a.w(0x588F)                  # addq.l #4,sp
            if n in raws:                # (launch: blood and the uppercut for any MK fighter)
                a.bccw(0x60, f'r_{n}')
            elif n == 'taps':
                a.jmp(NEXT)              # (the dispatch stub's own way out)
            else:
                a.w(0x4E75)


def ext_block():
    """Scorpion's block: (bytes, {entry: offset})."""
    SCO_TAIL.update(offs={}, data=b'')
    if SCO_TAIL['off'] is not None:
        tail = bytearray()
        for mid, sc in sorted(MK_SCRIPTS.items()):
            SCO_TAIL['offs'][mid] = len(tail)
            tail += script_bytes(sc)
            tail += bytes(len(tail) % 2)
        SCO_TAIL['data'] = bytes(tail)
    a = Asm(0)
    raws = {}
    GEN_LOW.clear()
    low_jump(a, MK_DIR_BY_ID[SCORPION_ID])  # MK's jumps (r_jumpup): in his module's low room
    GEN_KD.clear()
    GEN_ROOM.clear()
    GEN_DEAD.clear()
    if SCORPION_ID in KD_FIGHTERS:
        low_kd(a, MK_DIR_BY_ID[SCORPION_ID])   # MK's knockdown (r_jumpup, r_drag): in a victory room
    _block(a, True, SCORPION_ID, ('taps', 'ai', 'drag', 'hit_f', 'hit_p', 'launch', 'finish', 'jumpup'))
    for name, fn in (('taps', r_taps), ('ai', r_ai), ('drag', r_drag),
                     ('hit_f', r_hit_f),
                     ('hit_p', r_hit),          # (one body for both: d2 says which)
                     ('launch', r_launch), ('fatal', r_fatal),
                     ('finish', r_finish), ('jumpup', r_jumpup),
                     ('gmoves', lambda a: r_gmoves(a, SCORPION_ID))):  # his specials' list and handler (was in SUB.BIN)
        while len(a.out) % 2:
            a.out += b'\0'
        if name in ENTRIES:
            a.label(f'r_{name}')
        _at = len(a.out)
        fn(a)
        if os.environ.get('EK_SIZES'):
            print(f'        {name}: {len(a.out) - _at} bytes')
    while len(a.out) % 2:
        a.out += b'\0'
    if 'd_ht_cnt' in a.labels:
        emit_hitfix(a, 'd_ht', per_player=True)
    if SCO_TAIL['off'] is not None:
        while len(a.out) % 2:
            a.out += b'\0'
        emit_pl_tail(a, SCO_TAIL['off'], 'sco_tail')
    flush_late(a)
    return a.build(), {n: HEAD + 4 * i for i, n in enumerate(ENTRIES)}


SCO_TAIL = {'off': None, 'offs': {}, 'data': b''}   # Scorpion's .PL tail ('off' set by patches.scorpion_inputs)


def walk_cycle(mk_dir):
    """[(capture pose, frames)] of one loop of MK's forward walk."""
    from inputs import ROOT
    o = [int(x) for x in open(os.path.join(ROOT, 'extracted', mk_dir, 'walk_fwd', 'order.txt')).read().split()]
    runs = []
    for k in o:
        if runs and runs[-1][0] == k:
            runs[-1][1] += 1
        else:
            runs.append([k, 1])
    ks = [r[0] for r in runs]
    for p in range(4, 12):
        for i in range(len(ks) - p - 2):
            rest = ks[i + p:i + 2 * p]
            if len(rest) >= min(p, 3) and ks[i:i + len(rest)] == rest and len(set(ks[i:i + p])) == p:
                return [tuple(r) for r in runs[i:i + p]]
    raise ValueError(f'no walk loop in {mk_dir}')


HIT_EC = (0x4201, 0x4226, 0x4224)   # EC's hit frames, loaded at its calls 0, 3 and 6 (scorpion_map 'hit_high')
HIT_EC_AT = (0, 3, 6)


def _free_slots(mk_dir, skip=()):
    """Free frame slots (Blade numbering) after the attack scripts' (mkscripts
    takes them from the front of its list: these come from the end), less skip."""
    import mkscripts
    from inputs import ROOT
    co = open(os.path.join(ROOT, 'extracted', 'ec_us', 'BLA.CO'), 'rb').read()
    used = {int(e.split('=')[0].replace(':', ''), 16) for _, es in mkscripts.build(co, mk_dir)[1] for e in es}
    out = [sid << 8 | f for sid, f in reversed(mkscripts.free_slots())
           if (sid << 8 | f) not in used and (sid << 8 | f) not in skip]
    return out + [f for f in extra_slots(mk_dir) if f not in skip]   # (last: Blade's are used first)


EXTRA_FRAMES = 24                  # frames appended to sheet $43 per MK fighter (scorpion_full.grow_sheet)
EXTRA_FRAMES_OF = {}               # (Raiden's .PL had no room: Blade's blast sheet, $45, now stripped)
BLADE_43_FRAMES = 18               # Blade's count on sheet $43


def extra_slots(mk_dir):
    """The appended frames' slots (Blade numbering: 43:12 on)."""
    return [0x4300 | f for f in range(BLADE_43_FRAMES, BLADE_43_FRAMES + EXTRA_FRAMES_OF.get(mk_dir, EXTRA_FRAMES))]


# EC's throw (move $0D): the thrower list (BLA.CO $1B10, 7 steps, 4 bytes:
# frame, flags) loads its frames at 0, 6, 12, 16, 24, 28, 32 frames (victim
# record ticks 3 3 2 THROW_HOLD 2 2 2); the victim is released ~36 frames
# in; then Blade's module shows 42:11 (BLA.CO $1A62, ~46) and his stance.
# Blade's list reuses 42:0F and 42:10 late, which flashed early poses over
# MK's: in the MK fighters' modules the list is rewritten (patches.mk_throw_arc)
# so each frame is loaded at one moment only.
THROW_LIST_AT = 0x1B10       # BLA.CO offset of the thrower list
THROW_LIST = (0x4210, 0x420F, 0x420E, 0x420D, 0x420D, 0x420D, 0x420D)
THROW_LIST_TIMES = (0, 6, 12, 16, 24, 28, 32)   # frames: when EC loads each entry
THROW_LAST_AT = 0x1A62       # BLA.CO: move.b #$42,$1A(a5); move.b #$11,$1B(a5) (its last frame, ...
THROW_LAST_TIME = 46         # ... ~46 frames in)
THROW_EC = ((0x4210, 0), (0x420F, 6), (0x420E, 12), (0x420D, 16), (0x4211, 46))
THROW_MOVE = 0x0D
THROW_PEAK_AT, THROW_RELEASE, THROW_END = 16, 36, 52   # frames
# A thrower whose victim follows MK's own path (patches.THROW_TRACK: the victim
# records rebuilt, so EC's step times move): his times, from the track's ticks
# (2 frames each) - the list's load times, his peak (the lift's end), the
# release (the steps' end), the end of his animation, EC's last frame (42:11).
# per thrower: (ticks per step, he turns by the side swap on the last step, else as he stands
# at MK's turn: frame from the input; tools/dev/throwcmp.py track)
THROW_SHAPE = {'mk_moves_kano': ((6, 3, 2, 3, 4, 3, 3), True, 44),
               'mk_moves_johnny': ((3, 3, 3, 3, 3, 3, 3), True, 40),
               'mk_moves': ((10, 2, 2, 2, 2, 2, 2), False, 70),               # Scorpion
               'mk_moves_subzero': ((10, 2, 2, 2, 2, 2, 2), False, 68),
               'mk_moves_raiden': ((6, 3, 3, 3, 3, 3, 3), False, 61),
               'mk_moves_liukang': ((6, 3, 2, 3, 3, 2, 3), False, 60),
               'mk_moves_sonya': ((10, 2, 2, 2, 2, 2, 2), False, 87)}   # (her block had no room for it
#  until her leg grab's tables moved to a room: tools/dev/throwcmp.py track sonya)
THROW_LAND_TICKS = 1          # the last step (on the floor): released a tick after he lands - EC's
                              # knockdown takes ~7 frames more to lie him down (MK's lies ~2-4 after
                              # landing); held to MK's landing, he lay ~8 frames late
THROW_TRACK_TICKS = {d: v[0][:-1] + (THROW_LAND_TICKS,) for d, v in THROW_SHAPE.items()}
THROW_EC_START = 6            # frames from the throw's input to EC's first step
THROW_TURN_EARLY = 6          # frames: his stance is set this much before the swap turns him (a frame
                              # set in $1A shows 2 frames later, and his drive started ~6 before EC's
                              # steps): else his last throw pose showed turned the wrong way


def throw_times(mk_dir):
    """(list times, peak, release, end, last) for a thrower (frames)."""
    ticks = THROW_TRACK_TICKS.get(mk_dir)
    if not ticks:
        return THROW_LIST_TIMES, THROW_PEAK_AT, THROW_RELEASE, THROW_END, THROW_LAST_TIME
    times = tuple(2 * sum(ticks[:k]) for k in range(len(ticks)))
    release = 2 * sum(ticks)
    _, swap, turn = THROW_SHAPE[mk_dir]
    end = release + 16 if swap else max(release + 16, turn + 8)
    return times, times[2], release, end, release + 2


def throw_post(mk_dir):
    """Ticks of Blade's two pauses after the release (BLA.CO $1A6E, $1A82: 3, 3): a thrower
    who turns as he stands holds his throw till MK's turn (EC turns him then, as he stands)."""
    shape = THROW_SHAPE.get(mk_dir)
    if not shape or shape[1]:
        return 3, 3
    ticks, turn = THROW_TRACK_TICKS[mk_dir], shape[2]
    left = max(2, round((turn - THROW_EC_START - 2 * sum(ticks) - 5) / 2))
    return left // 2, left - left // 2


def throw_plan(mk_dir):
    """(calls, art pins) for MK's thrower animation (mkmoves throw) fitted to
    EC's choreography: MK's poses up to his peak (the longest-held: on his
    back in the roll throws, arms up in the tosses) squeezed into the
    THROW_PEAK_AT frames before EC lifts the victim overhead; the peak held
    till the release; then MK's poses after it at MK's timing till
    THROW_END. One frame word per call (2 frames)."""
    import mkscripts
    P, order = mkscripts._load('throw', mk_dir)
    skip = set()
    for other in ('idle', 'walk_fwd'):
        Q, _ = mkscripts._load(other, mk_dir)
        skip |= {mkscripts._key(p) for p in Q}
    runs = []
    for k in order:
        if runs and runs[-1][0] == k:
            runs[-1][1] += 1
        else:
            runs.append([k, 1])
    times, peak_at, release, end, last = throw_times(mk_dir)
    if mk_dir in THROW_TRACK_TICKS:
        # his victim follows MK's path at MK's timing: so does he - MK's throw poses as
        # MK plays them, up to his stance (MK turns him round then: his stance drawn
        # facing the other way), spread over the steps up to the last one (the swap:
        # he turns), then his own stance
        import numpy as np
        mirrored = set()
        for other in ('idle', 'walk_fwd'):
            Q, _ = mkscripts._load(other, mk_dir)
            mirrored |= {mkscripts._key(np.ascontiguousarray(q[:, ::-1])) for q in Q}
        act = []
        for k, m in runs:
            if mkscripts._key(P[k]) in skip or mkscripts._key(P[k]) in mirrored:
                if act:
                    break
                continue
            act.append([k, m])
        stance = next(k for k, m in runs if mkscripts._key(P[k]) in skip)   # (his stance, drawn facing forward)
        n = sum(m for _, m in act)
        frames = []
        swap, turn = THROW_SHAPE[mk_dir][1:]
        upto = times[-1] - THROW_TURN_EARLY if swap else turn - 2   # (to the swap, or to his turn
        for k, m in act:                              #  as he stands; plan frames from the throw's start)
            frames += [k] * max(1, round(m * upto / n))
        frames = (frames[:upto] + [stance] * end)[:end]   # then he stands, facing his victim
        return _throw_calls_pins(mk_dir, frames, times, last)
    act = [r for r in runs if mkscripts._key(P[r[0]]) not in skip]
    first_end = next((i for i, r in enumerate(act) if i and r[0] == act[0][0]), len(act))
    act = act[:first_end]
    peak = max(range(len(act)), key=lambda i: act[i][1])
    pre, post = act[:peak], act[peak + 1:]
    frames = []
    n = sum(r[1] for r in pre) or 1
    for k, m in pre:                                  # squeezed to his peak
        frames += [k] * max(1, round(m * peak_at / n))
    frames = (frames + [act[peak][0]] * peak_at)[:peak_at]
    frames += [act[peak][0]] * (release - peak_at)
    for k, m in post:
        frames += [k] * m
    frames = (frames + [frames[-1]] * end)[:end]
    return _throw_calls_pins(mk_dir, frames, times, last)


def throw_list(mk_dir):
    """The thrower list's frames (one per step, loaded by EC at the step's time) for a
    thrower: Blade's (THROW_LIST, each pinned to the pose due when it loads), or for a
    thrower with an MK track the frame his animation shows at each step's time (EC's
    load and the drive then agree: no other pose flashes between the drive's calls)."""
    if mk_dir not in THROW_TRACK_TICKS:
        return THROW_LIST
    calls = throw_plan(mk_dir)[0]
    return tuple(calls[min(t // 2, len(calls) - 1)] for t in throw_times(mk_dir)[0])


def _throw_calls_pins(mk_dir, frames, times, last):
    """throw_plan's (calls, pins) from a pose per frame."""
    end = len(frames)
    calls = [frames[2 * c] for c in range(end // 2)]
    slot = {}
    ec_frames = tuple(zip(THROW_LIST[:4], times[:4])) + ((0x4211, last),)
    for f, t in ec_frames:                            # EC's own frames: the pose due when EC loads each
        slot.setdefault(calls[t // 2], f)
    hit_slots = set(hit_plan(mk_dir)[0])
    free = _free_slots(mk_dir, hit_slots)
    for k in calls:
        if k not in slot:
            slot[k] = free.pop(0)
    pins, seen = [], set()
    for f, t in ec_frames:
        if f not in seen:
            seen.add(f)
            pins.append(f'{f >> 8:02x}:{f & 0xFF:02x}={calls[t // 2]}')
    pins += [f'{f >> 8:02x}:{f & 0xFF:02x}={k}' for k, f in slot.items() if f not in seen]
    return tuple(slot[k] for k in calls), pins


# Sonya's leg grab (MK CD: down + LP + LK, close; Block held too is the same): MK's capture (mkmoves
# 'leggrab') bends (16), hands down (17), kicks up (18) into a handstand (19), holds
# the arch that clamps and flings the victim (20, the longest), and comes back
# 19, 21, 18, 17, 16 to her stance. It is EC's throw (move $0D: the victim lifted
# by THROW_PEAK_AT, released behind at THROW_RELEASE) with these poses: the way up
# squeezed into the lift, the arch held to the release, the way back in what's left.
# The input: her block (emit_leggrab_pad) turns those buttons into back + Y.
LEG_BUTTONS = 0x0442          # pad: X (LP) $400 + A (LK) $40 + down 2 (measured: MK CD needs no Block)
LEG_CLEARS = LEG_BUTTONS | 0x0100   # and Z (Block) $100, if held too: cleared with them
LEG_KEEP = 8                  # calls a leg grab flag lives outside the throw (vars+64/65)


def leg_plan(mk_dir):
    """(calls, art pins) for the leg grab on EC's throw (LEG_BUTTONS): one
    frame word per call, its poses on free slots of their own."""
    import mkscripts
    P, order = mkscripts._load('leggrab', mk_dir)
    skip = set()
    for other in ('idle', 'walk_fwd'):
        Q, _ = mkscripts._load(other, mk_dir)
        skip |= {mkscripts._key(p) for p in Q}
    runs = []
    for k in order:
        if mkscripts._key(P[k]) in skip:
            continue
        if runs and runs[-1][0] == k:
            runs[-1][1] += 1
        else:
            runs.append([k, 1])
    peak = max(range(len(runs)), key=lambda i: runs[i][1])
    pre, post = runs[:peak], runs[peak + 1:]
    def fit(rs, n):
        tot = sum(m for _, m in rs) or 1
        out = []
        for k, m in rs:
            out += [k] * max(2, round(m * n / tot))
        return (out + [out[-1]] * n)[:n]
    frames = fit(pre, THROW_PEAK_AT) + [runs[peak][0]] * (THROW_RELEASE - THROW_PEAK_AT) \
        + fit(post, THROW_END - THROW_RELEASE)
    calls = [frames[2 * c] for c in range(THROW_END // 2)]
    taken = set(hit_plan(mk_dir)[0]) | set(throw_plan(mk_dir)[0])
    free = _free_slots(mk_dir, taken)
    slot = {}
    for k in calls:
        if k not in slot:
            slot[k] = free.pop(0)
    return tuple(slot[k] for k in calls), [f'{f >> 8:02x}:{f & 0xFF:02x}={k}' for k, f in slot.items()]


def emit_leggrab_pad(a):
    """(a1 = Sonya, a0 = her pad word, d0 = it) Her leg grab's buttons, all held,
    read as back + Y: EC's throw (behind) when she's close, its flag set for
    LEG_KEEP calls (vars+64 player 1, +65 player 2). Uses d0/a2."""
    a.w(0x2F01)                          # move.l d1,-(sp)
    a.w(0x3200)                          # move.w d0,d1
    a.w(0x0241, LEG_BUTTONS)             # andi.w #buttons,d1
    a.w(0x0C41, LEG_BUTTONS)             # cmpi.w #buttons,d1
    a.bcc(0x66, 'lp_no')
    a.w(0x0240, (~(LEG_CLEARS | 0xF)) & 0xFFFF)    # andi.w: no directions, no X/A/Z
    a.w(0x0040, 1 << THROW_BIT)          # ori.w #Y,d0
    a.w(0x0829, 0x0003, 0x0020)          # btst #3,$20(a1)     facing left?
    a.bcc(0x66, 'lp_l')
    a.w(0x0040, 0x0004)                  # ori.w #left,d0      (back)
    a.bcc(0x60, 'lp_w')
    a.label('lp_l')
    a.w(0x0040, 0x0008)                  # ori.w #right,d0
    a.label('lp_w')
    a.w(0x3080)                          # move.w d0,(a0)
    a.pcrel(0x45FA, 'vars')              # lea vars(pc),a2
    a.w(0xB3FC); a.l(0x2E188)            # cmpa.l #P1,a1
    a.bcc(0x67, 'lp_p1')
    a.w(0x528A)                          # addq.l #1,a2
    a.label('lp_p1')
    a.w(0x157C, LEG_KEEP, 0x0040)        # move.b #keep,64(a2)
    a.label('lp_no')
    a.w(0x221F)                          # move.l (sp)+,d1


def emit_leggrab_drive(a, leg):
    """(a1 = Sonya) While her leg grab flag lives, her module's thrower list
    (THROW_LIST_AT, loaded by EC at THROW_LIST_TIMES) and its last frame (42:11,
    BLA.CO $1A62) hold the leg grab's poses due then (else EC's own loads show
    the throw's poses between this drive's calls); in EC's throw its poses
    (leg_plan) are driven, branching to g_out. Without the flag the list is the
    throw's again. Outside the throw the flag runs down and the drive's counter
    is reset. Uses d0/a0/a2."""
    lst = [fr(leg[t // 2]) for t in THROW_LIST_TIMES]
    last = fr(leg[THROW_LAST_TIME // 2])
    a.pcrel(0x45FA, 'vars')              # lea vars(pc),a2
    a.w(0x41F9); a.l(0x1B000 + THROW_LIST_AT)   # lea list (player 1's module),a0
    a.w(0xB3FC); a.l(0x2E188)            # cmpa.l #P1,a1
    a.bcc(0x67, 'ld_p1')
    a.w(0x528A)                          # addq.l #1,a2
    a.w(0x41F9); a.l(0x21800 + THROW_LIST_AT)   # lea list (player 2's module),a0
    a.label('ld_p1')
    a.w(0x4A2A, 0x0040)                  # tst.b 64(a2)
    a.bccw(0x66, 'ld_on')
    for k, f in enumerate(THROW_LIST):   # the throw's own
        a.w(0x317C, fr(f), 4 * k)        # move.w #frame,4k(a0)
    a.w(0x117C, fr(0x4211) >> 8, (THROW_LAST_AT + 3 - THROW_LIST_AT) & 0xFFFF)   # move.b #sheet,..(a0)
    a.w(0x117C, 0x11, (THROW_LAST_AT + 9 - THROW_LIST_AT) & 0xFFFF)              # move.b #frame,..(a0)
    a.bccw(0x60, 'ld_off')
    a.label('ld_on')
    for k, f in enumerate(lst):
        a.w(0x317C, f, 4 * k)
    a.w(0x117C, last >> 8, (THROW_LAST_AT + 3 - THROW_LIST_AT) & 0xFFFF)
    a.w(0x117C, last & 0xFF, (THROW_LAST_AT + 9 - THROW_LIST_AT) & 0xFFFF)
    a.w(0x3029, 0x00BE)                  # move.w $BE(a1),d0
    a.w(0x0240, 0x7FFF)                  # andi.w #$7FFF,d0
    a.w(0x0C40, THROW_MOVE)              # cmpi.w #$0D,d0
    a.bcc(0x67, 'ld_in')
    a.w(0x532A, 0x0040)                  # subq.b #1,64(a2)
    a.bccw(0x60, 'ld_off')
    a.label('ld_in')
    a.w(0x157C, LEG_KEEP, 0x0040)        # move.b #keep,64(a2)   (alive while she throws)
    emit_hitdrive(a, leg, 'g_lg', 'g_out', False, THROW_MOVE, False, room=True)   # (its tables in a room:
                                         #  her block's room for her MK throw)
    a.label('ld_off')
    a.pcrel(0x41FA, 'g_lg_cnt')          # lea cnt(pc),a0      next time from its start
    a.w(0x30BC, 0xFFFF)                  # move.w #-1,(a0)


# Raiden's MK teleport (down, up; measured on mk_raiden_2p): he crouches,
# turns into a white silhouette that sinks while another rises ~40 px
# behind his opponent, and he's back in colour there, facing him, ~33
# frames in. One sprite can't be in both places: crouch, the silhouette
# where he stood, then (RTELE_AT) he is moved behind his opponent and
# turned, the silhouette there, then his colours. (capture pose, ticks of 2 frames)
RTELE_STEPS = [(3, 2), (4, 2), (5, 2), (6, 3), (6, 3), (14, 3), (15, 3)]
RTELE_AT = 4                  # the step at which he is over there
RTELE_BEHIND = 41             # px past his opponent (MK: Raiden's centre 41 px past Sub-Zero's)


def rtele_plan(mk_dir):
    """(script bytes in Blade's numbering, art pins) for Raiden's teleport
    on move $31 (header as Blade's $31: table slot $C4, steps - 1)."""
    from inputs import ROOT
    taken = set(hit_plan(mk_dir)[0]) | set(throw_plan(mk_dir)[0])
    free = _free_slots(mk_dir, taken)
    slot = {}
    for k, _ in RTELE_STEPS:
        if k not in slot:
            slot[k] = free.pop(0)
    co = open(os.path.join(ROOT, 'extracted', 'ec_us', 'BLA.CO'), 'rb').read()
    head = 0x4D24
    hdr = bytearray(co[head:head + 20])
    hdr[2:4] = (len(RTELE_STEPS) - 1).to_bytes(2, 'big')
    steps = b''.join(struct.pack('>HHHHHH', slot[k], n, 0, 0, 0, 0) for k, n in RTELE_STEPS)
    term = bytes(co[head + 20 + 12 * 5:head + 20 + 12 * 6])        # Blade's: $00D0 ...
    assert int.from_bytes(term[:2], 'big') < 0x100
    pins = [f'{f >> 8:02x}:{f & 0xFF:02x}={k}' for k, f in slot.items()]
    return bytes(hdr) + steps + term, pins


ICE_MOVE = RTELE_MOVE          # Reptile's ice blast: Blade's $31 with our script (his $34 is the spear)
RS_SOUNDS = {}                 # Reptile's spear lines: 'yank', 'scream_m', 'scream_f' -> his bank's ids
                               #  (patches.mk_voice, GENERIC_VOICE['reptile'])
RS_EVERY = 100                 # calls standing (every other frame: ~3.3 s) before the CPU's Reptile throws
                               #  one himself: with his AI's own, ~MK's ~4.5 a minute (mk_fidelity_spec 1)
RS_REACH = 125                 # px apart: the spear's reach (scorpion_full.SPEAR_REACH and his body)
ICE_LONG = (12,)               # Blade's $34 steps that last 2 ticks on screen (42:30's rope hit: 4 frames)


def ice_plan(mk_dir):
    """(script bytes in Blade's numbering, art pins, release frame) for Reptile's ice blast
    on move ICE_MOVE: Blade's $34 timeline (41 steps, a tick each - 2 frames) as it shows
    the ice blast on his projectile frames now (scorpion_full.pick: the 'spear' group's
    20 frames spread over the capture's poses), each of those frames on a free slot with
    the same pose; the recovery's walk frames (40:64-40:6D) as they are; no step moves him
    (recovery_still: no drift). The ball leaves on 42:2E's pose (PJ_RELEASE)."""
    import numpy as np, scorpion_map, scorpion_full as sf
    from inputs import ROOT
    group = [int(e.split('=')[0].replace(':', ''), 16)
             for e in next(fr for act, fr in scorpion_map.MEASURED if act == 'spear')]
    p = len(np.load(os.path.join(ROOT, 'extracted', mk_dir, 'iceblast', 'indexed.npy')))
    n, cap = len(group), min(p, sf.CAP.get('iceblast', sf.DEFAULT_CAP))
    pose = lambda k: round(round(k * (cap - 1) / (n - 1)) * (p - 1) / (cap - 1))
    taken = set(hit_plan(mk_dir)[0]) | set(throw_plan(mk_dir)[0])
    free = _free_slots(mk_dir, taken)
    co = open(os.path.join(ROOT, 'extracted', 'ec_us', 'BLA.CO'), 'rb').read()
    W = lambda o: int.from_bytes(co[o:o + 2], 'big')
    head = 0x4D74                        # Blade's $34 (table slot $D0, 41 steps)
    assert W(head) == 0xD0 and W(head + 2) == 40
    slot, steps = {}, b''
    for i in range(41):
        f = W(head + 20 + 12 * i)
        if f in group:
            k = pose(group.index(f))
            if k not in slot:
                slot[k] = free.pop(0)
            f = slot[k]
        if 0x4064 <= f <= 0x406D:        # (the recovery: his stance, not MK's walk - recovery_still)
            f = 0x4000 | STANCE_CYCLE[(i - 29) % 4]
        steps += struct.pack('>HHHHHH', f, 2 if i in ICE_LONG else 1, 0, 0, 0, 0)
    r31 = 0x4D24                         # Blade's $31 header (table slot $C4), its terminator
    hdr = bytearray(co[r31:r31 + 20])
    hdr[2:4] = (41 - 1).to_bytes(2, 'big')
    term = bytes(co[r31 + 20 + 12 * 5:r31 + 20 + 12 * 6])
    assert W(r31) == 0xC4 and int.from_bytes(term[:2], 'big') < 0x100
    pins = [f'{f >> 8:02x}:{f & 0xFF:02x}={k}' for k, f in slot.items()]
    release = slot[pose(group.index(PJ_RELEASE))]
    return bytes(hdr) + steps + term, pins, release


DASH_MOVE = 0x35                       # Blade's dash: the move his flying kick plays
FLYKICK_SPEED = 15                     # px a tick (the dash header's speed is per tick of 2 frames): MK CD's
                                       #  flying kick flies 7.5 px a frame (measured: $7BE34, 146 px in 19 frames,
                                       #  level, ~10 px up) until it connects. Was 5 (2.5 px a frame: slow motion)


def flykick_plan(mk_dir):
    """Liu Kang's flying kick on Blade's dash ($35, 7 steps): MK's timeline (the capture's order.txt,
    his first pose off the stance to the stance again: 7 poses) - the wind-up (moving, as MK), the kick (the
    held pose: on 41:62, Blade's strike, its hit box and hit data) flying for as long as MK holds it,
    the landing. -> ([(frame, ticks, flags, flies)], pins, px a tick for the flight). The flight ends
    when the kick connects (emit_flykick_stop)."""
    import numpy as np, scorpion_full as sf
    from inputs import ROOT
    d = os.path.join(ROOT, 'extracted', mk_dir, 'flyingkick')
    order = [int(v) for v in open(os.path.join(d, 'order.txt')).read().split()]
    lead = sf.stance_lead(np.load(os.path.join(d, 'indexed.npy'), mmap_mode='r'))
    t0 = next(i for i, k in enumerate(order) if k >= lead)
    t1 = next(i for i in range(t0, len(order)) if order[i] < lead)
    seq = []
    for k in order[t0:t1]:
        if seq and seq[-1][0] == k:
            seq[-1][1] += 1
        else:
            seq.append([k, 1])
    assert len(seq) <= 7 and len({k for k, _ in seq}) == len(seq), seq   # (the dash has 7 steps)
    # on the floor before the leap: only the last pose (the crouch). The capture held forward
    # for the input, so its first poses off the stance are his walk; MK leaps after one pose
    P = np.load(os.path.join(d, 'indexed.npy'), mmap_mode='r')
    feet = lambda k: int(np.nonzero(P[k].any(1))[0].max())
    air = next(i for i, (k, _) in enumerate(seq) if feet(k) < feet(order[0]) - 8)
    seq = seq[max(0, air - 1):]
    strike = max(seq, key=lambda kn: kn[1])[0]
    taken = set(hit_plan(mk_dir)[0]) | set(throw_plan(mk_dir)[0])
    own = [0x4116, 0x4117, 0x4161]
    free = _free_slots(mk_dir, taken | set(own) | {0x4162})
    slot = {strike: 0x4162}
    for k, _ in seq:
        if k not in slot:
            slot[k] = own.pop(0) if own else free.pop(0)
    # the wind-up as MK plays it live (tools/lib/mkmoves.py's script on MK CD: off
    # the ground 4-5 frames after HK, the kick held ~9-10 frames after it, travelling from the
    # start ~7 px a frame): a tick a pose, all but the first on the move (flag $0400, the header's
    # speed - Blade's 41:61 step's way). The capture's order.txt holds it 15 frames, starting 24
    # after HK - not MK's timing (its state wasn't fighting yet): his kick stood 12 frames in place
    # (slow to get going)
    steps, cum, done, before = [], 0, 0, True
    for k, frames in seq:
        cum += frames
        ticks = max(1, round(cum / 2) - done)
        done += ticks
        if k == strike:
            before = False
            steps.append((slot[k], ticks, 0x0402, True))
        elif before:
            steps.append((slot[k], 1, 0x0402 if steps else 0x0002, False))
        else:
            steps.append((slot[k], ticks, 0, False))
    pins = [f'{f >> 8:02x}:{f & 0xFF:02x}={k}' for k, f in slot.items()]
    return steps, pins, FLYKICK_SPEED


FLYKICK_BACK = 6                       # px a tick: after it connects MK's kick floats back (measured on MK CD:
                                       #  ~56 px in 25 frames, then still) ...
FLYKICK_AFTER = 16                     # ticks: ... held in the air 38 frames from the contact, then the landing


def emit_flykick_stop(a):
    """(a1 = Liu Kang) MK's flying kick flies until it connects, then floats back: in his flight step
    (the dash $35 showing 41:62), once its hit is spent ($F7 bit 1 cleared: hit or blocked) his
    velocity turns to FLYKICK_BACK px a tick backwards ($C6, the travel the step's $0400 flag applies,
    and $5E, this tick's: EC slows it to a stop) and the step is held FLYKICK_AFTER ticks more (his
    task's tick counter, as the knockdown drive's), then the landing step. Once: then he's going
    backwards. Without it he flew on at 7.5 px a frame, carrying the victim. Uses d0/a0."""
    a.w(0x3029, 0x00BE)                  # move.w $BE(a1),d0
    a.w(0x0240, 0x7FFF)                  # andi.w #$7FFF,d0
    a.w(0x0C40, DASH_MOVE)               # cmpi.w #$35,d0
    a.bcc(0x66, 'g_fkn')
    a.w(0x0C69, fr(0x4162), 0x001A)      # cmpi.w #41:62,$1A(a1)   the flight
    a.bcc(0x66, 'g_fkn')
    a.w(0x0829, 0x0001, 0x00F7)          # btst #1,$F7(a1)     its hit not yet spent
    a.bcc(0x66, 'g_fkn')
    a.w(0x2029, 0x00C6)                  # move.l $C6(a1),d0   his velocity, on the screen (EC sets its own
    a.w(0x0829, 0x0003, 0x0020)          # btst #3,$20(a1)      at some hits: a jumping victim's +7)
    a.bcc(0x66, 'g_fkl')                 # facing left?
    a.w(0x4A80)                          # tst.l d0             facing right: going left already
    a.bcc(0x6B, 'g_fkn')
    a.w(0x203C); a.l((-FLYKICK_BACK << 16) & 0xFFFFFFFF)   # move.l #-back,d0
    a.bcc(0x60, 'g_fks')
    a.label('g_fkl')
    a.w(0x4A80)                          # tst.l d0             facing left: going right already
    a.bcc(0x6E, 'g_fkn')
    a.w(0x203C); a.l(FLYKICK_BACK << 16)   # move.l #back,d0
    a.label('g_fks')
    a.w(0x2340, 0x00C6)                  # move.l d0,$C6(a1)
    a.w(0x2340, 0x005E)                  # move.l d0,$5E(a1)
    a.w(0x2069, 0x0088)                  # movea.l $88(a1),a0
    a.w(0x2050)                          # movea.l (a0),a0
    a.w(0x317C, FLYKICK_AFTER, 0x0026)   # move.w #ticks,$26(a0)
    a.label('g_fkn')


JUMP_POSES_CAP = {'mk_moves_raiden': 5}   # (Raiden, CHW.PL: 3.6 KB of room since sheet $45 went - his roll 5 poses,
KD_FLOOR_N = {('mk_moves_kano', 'knockdown'): 1}   # floor poses (no .PL room for more: Kano's lying, 23, is
                              # EC's landing art too - every slot showed it before, and he lay flat)
KD_POSES_CAP = {'mk_moves_raiden': 8, 'mk_moves': 4}     # (Raiden: his knockdown 8 (JUMP_POSES_CAP); all of the roll's, the
                              #  knockdown's and the kick reaction hit_high's poses were 5 KB over)
JUMP_MAX_POSES = 10            # roll poses a fighter's jump may take (free slots and .PL room)
JUMP_IN_TAIL = (20, 18)        # fighters whose roll tables go in their .PL's tail (Sub-Zero, Johnny: block room)
JUMP_TAIL = {}                 # 'off': the tables' offset in the tail being built (generic_block)
# MK's jump heights (the captures' feet at the peak, x1.08): EC's jump (Blade's move 8) launches at
# vy -22 for every direction (121 px). Straight up: each fighter's own script header (patches
# mk_jump_height); forward/back: the roll sets these when it starts (px per tick, 16.16 in $CA)
JUMP_VY_UP = {22: 21.0, 19: 20.0, 18: 19.7, 20: 21.3, 12: 20.8, 13: 18.7, 17: 20.5, 26: 21.3}
JUMP_VY_FWD = {22: 22.3, 19: 22.3, 18: 21.0, 20: 22.45, 12: 22.45, 13: 21.35, 17: 21.1, 26: 22.45}
# (set on the roll's first call, ~20 px after the takeoff: v = sqrt((MK's rise x1.08 - 21) / 0.25),
#  EC's rise being 0.25 v^2 - measured: Kano 135 / Sub-Zero 147 px wanted)
# MK's straight-up jump is as long in the air as its forward one (data/mk_meta jump_up: frames more than
# 12 px off the floor - Kano 43, Scorpion 41, Sub-Zero 42, Liu Kang 41, Sonya 40, Johnny 40, Raiden 42),
# lower: its gravity is lower. Ours took EC's gravity (2 px a tick per tick) at MK's height: Kano 33 frames.
JUMP_UP_AIR = {22: 41, 19: 42, 18: 40, 20: 42, 12: 41, 13: 43, 17: 40, 26: 42}
EC_GRAVITY = 2.0               # Blade's jump script header +12 ($CE once launched), px per tick per tick


def jump_up_launch(fid):
    """(launch speed, gravity), px per tick, of his straight-up jump: MK's height (JUMP_VY_UP, at EC's
    gravity) and MK's frames above 12 px (2 a tick)."""
    h = JUMP_VY_UP[fid] ** 2 / (2 * EC_GRAVITY)
    t = JUMP_UP_AIR[fid] / 2
    g = 8 * (h - 12) / t ** 2
    return math.sqrt(2 * g * h), g


JUMP_CALLS = 22                # EC's airborne frames (41:00-41:04: 12+12+10+8+2 = 44) in calls
JUMP_FIGHTERS = (KANO_ID, JOHNNY_ID, LIUKANG_ID, 26, 20, 22, RAIDEN_ID, SONYA_ID)
JUMP_LOW = JUMP_FIGHTERS          # the drive (code and tables) in each module's low room (JUMP_LOW_OFF), not his block
FEET_SOUND = 0x3F1                # MK's FEETLAND as a jump lands (emit_jump_drive; patches.FIGHT_NEW: its clip)
JUMP_GRUNT = 0x3F2                # MK's MALEJUMP as he leaves the floor (every jump: tools/capture/mkmovesounds.py jump_up
#                                   6 frames after the press, jump_* 3): patches.GRUNT; Sonya's GIRLJUMP set by
#                                   patches.mk_code (patches.grunt_id)
JUMP_LOW_OFF = 0x1A8              # (after patches.block_button_code's zf at LOW_OFF)
JUMP_LOW_END = 0x2E0              # (then patches.crouch_code: 104 bytes, to $348 of LOW_END's $34A - its spare
#                                   moved here for the jump's grunt)
GEN_LOW = {}                      # generic_block -> {'off', 'data'}: written into his module by patches
GEN_KD = {}                       # (the same for his knockdown drive: low_kd)
ZF_SIZE = 16                      # bytes of zf (patches.block_button_code) at LOW_OFF (the rest, to JUMP_LOW_OFF: free but
#                                   in Sonya's, RINGS_AT - it was room_put's third room)
GEN_ROOM = {}                     # (and tables in the second victory room: room_put)
GEN_DEAD = {}                     # room_put's third room (generic_block): {'free': [(start, end)], 'pieces': [(off, data)]} -
#   the bodies of Blade's move scripts (BLA.CO's chain from patches.CHAIN_START) for the slots his block
#   installs its own scripts in every frame (generic_block: 'move.l script,4*id(a0)'): PLYR $1A278 reads
#   a chain script's first two words (its slot and step count) to build the move table, and the block's
#   scripts replace those entries, so the rest of each is never read (2026-11-22: a fighter's running
#   script, $AE, never in them over 24,000 frames of random fights; deadscriptcheck.py)
CTRL_ROOM = (0x47C8, 0x485C)      # the body of Blade's close punch script (move $20), dead in every MK module but Shang's
#                                   (GEN_DEAD; Scorpion's too): kept for patches.controls_code, the same place in each
MK_DIR_BY_ID = {22: 'mk_moves', KANO_ID: 'mk_moves_kano', JOHNNY_ID: 'mk_moves_johnny', LIUKANG_ID: 'mk_moves_liukang',
                SONYA_ID: 'mk_moves_sonya', 20: 'mk_moves_subzero', 19: 'mk_moves_raiden', 26: 'mk_moves_subzero'}


def _jump_air(mk_dir, action):
    """(poses, airborne timeline of pose indices at 60 fps) of a jump capture: the frames
    whose feet (the pose's anchor: anchors.json) are above the ground line of his first
    (standing) pose - the recordings start in his stance and end standing again, and
    their stance poses are numbered anew after the landing (Johnny's 10-14, Scorpion's
    14-17), so neither the numbers nor the shape alone tell them."""
    import json
    import numpy as np
    from inputs import ROOT
    d = os.path.join(ROOT, 'extracted', mk_dir, action)
    poses = np.load(os.path.join(d, 'indexed.npy'))
    order = [int(v) for v in open(os.path.join(d, 'order.txt')).read().split()]
    anc = json.load(open(os.path.join(d, 'anchors.json')))
    ground = anc[0][1]
    air = [i for i, k in enumerate(order) if anc[k][1] < ground - 3]
    return poses, order[air[0]:air[-1] + 1]


def jump_plan(mk_dir):
    """MK's forward / back jump, a roll (mk_fidelity_spec 0a; EC has one upright jump
    for every direction): (forward frames per call, back frames per call, art pins).
    The forward capture's airborne poses (at most JUMP_MAX_POSES, spread over its order)
    go on free slots; a call (every other frame) shows the timeline's pose then. The back
    jump shows the back capture's timeline through the same poses (mostly the same
    images: each back pose as the forward pose with the same crop; one with none holds
    the last)."""
    import numpy as np
    pf, tf = _jump_air(mk_dir, 'jump_fwd')
    pb, tb = _jump_air(mk_dir, 'jump_back')
    used = sorted(set(tf))
    taken = set(hit_plan(mk_dir)[0]) | set(throw_plan(mk_dir)[0])
    for fn, d in ((rtele_plan, 'mk_moves_raiden'), (ice_plan, 'mk_moves_subzero'), (leg_plan, 'mk_moves_sonya'),
                  (flykick_plan, 'mk_moves_liukang')):
        if mk_dir == d:
            taken |= {int(e.split('=')[0].replace(':', ''), 16) for e in fn(mk_dir)[1]}
    free = _free_slots(mk_dir, taken)
    n = min(JUMP_MAX_POSES, len(free), JUMP_POSES_CAP.get(mk_dir, 99))   # (Raiden: few slots, a full .PL)
    keep = used if len(used) <= n else [used[round(i * (len(used) - 1) / (n - 1))] for i in range(n)]
    near = lambda k: min(keep, key=lambda q: abs(q - k))
    def crop(q):
        ys, xs = np.nonzero(q)
        return q[ys.min():ys.max() + 1, xs.min():xs.max() + 1].tobytes() if len(ys) else b''
    crops = {crop(pf[k]): k for k in used}
    slot = {}
    for k in keep:
        slot[k] = free.pop(0)
    fit = lambda t: [t[min(len(t) - 1, round(i * len(t) / JUMP_CALLS))] for i in range(JUMP_CALLS)]
    fwd = [slot[near(k)] for k in fit(tf)]           # (MK's airtime onto EC's: 22 calls)
    back, last = [], keep[0]
    for k in fit(tb):                                # the back capture's own pose numbers differ:
        q = crops.get(crop(pb[k]))                   # its poses by image (identical crops); one with
        last = near(q) if q is not None else last    # none in the forward set holds the last
        back.append(slot[last])
    pins = [f'{f >> 8:02x}:{f & 0xFF:02x}={k}' for k, f in slot.items()]
    return fwd, back, pins


def jump_up_plan(mk_dir):
    """MK's straight-up jump (frames per call): the jump_up capture's airborne timeline on
    EC's own jump frames 41:00-41:04, each MK pose on the frame that holds it (scorpion_map
    'jump_up', spread as scorpion_full.pick) - MK shows 2-3 poses in the air (Sub-Zero 6, 7, 6);
    EC's fixed steps (12, 12, 10, 8, 2 frames) put his landing poses high in the air, the tall
    one past the top of the screen (his head disappeared)."""
    import scorpion_map, scorpion_full as sf
    poses, tl = _jump_air(mk_dir, 'jump_up')
    want = scorpion_map.assignments({}, False, ())
    on = {}
    for f in range(5):
        action, k, n = want[(0x41, f)]
        assert action == 'jump_up', (mk_dir, f, action)
        on.setdefault(sf.pick(poses, k, n, 'jump_up'), 0x4100 | f)
    near = lambda k: on[min(on, key=lambda q: abs(q - k))]
    fit = [tl[min(len(tl) - 1, round(i * len(tl) / JUMP_CALLS))] for i in range(JUMP_CALLS)]
    return [near(k) for k in fit]


KD_FIGHTERS = (KANO_ID, JOHNNY_ID, LIUKANG_ID, 26, 20, SONYA_ID, 22, RAIDEN_ID)   # MK's knockdown driven
KD_LOW = KD_FIGHTERS                # their drives (and tables) in the first victory room (VROOM, low_kd)
KD_AIR_POSES, KD_FLOOR_POSES = 8, 5   # slots it may take
KD_KNOCKDOWN_POSES = (2, 3)   # the knockdown's (air, floor): its slots drew one picture till scorpion_full.pick took
                              # the pins as poses - all 13 different were 7 KB over Scorpion's .PL, 8 still 3 KB, 6 1 KB;
                              # the air's include EC's flight pose (42:18: its art is there already); the sweep's as above
KD_STATE = 0x1C                # EC's knockdown
KD_TAIL = {}                   # 'off', 'n': its tables in the .PL tail being built (generic_block)


KD_FLAT = {}                    # (mk_dir, action) -> the floor table's first call on the flat pose: a fighter out of
                                #  the round (no health, or a finisher on: $1CD4) stays there - he got up in MK's
                                #  poses while EC held him down (seen: Sub-Zero knocked down by Trident didn't lie
                                #  flat, and the stage's vines came up round him); kd_plan sets it, emit_kd_drive


def kd_plan(mk_dir, action='knockdown'):
    """MK's knockdown (or, action='swept', his fall when swept: SWEPT_DIRS) (mk_fidelity_spec 0g; EC shows one pose, 42:18, for the whole flight):
    (air frames per call, floor frames per call, art pins). The capture's poses past his
    stance: in the air (feet - anchors.json - above the ground: the flight, the bounce) and,
    after the last airborne frame, on the floor (landing, getting up), each spread over at most
    KD_AIR_POSES / KD_FLOOR_POSES free slots, a call (2 frames) per entry at MK's speed."""
    import json
    import numpy as np, scorpion_full as sf
    from inputs import ROOT
    d = os.path.join(ROOT, 'extracted', mk_dir, action)
    poses = np.load(os.path.join(d, 'indexed.npy'))
    order = [int(v) for v in open(os.path.join(d, 'order.txt')).read().split()]
    anc = json.load(open(os.path.join(d, 'anchors.json')))
    lead = sf.stance_lead(poses)
    ground = anc[0][1]
    air = [i for i, k in enumerate(order) if k >= lead and anc[k][1] < ground - 20]
    a0, a1 = air[0], air[-1] + 1
    t1 = next((i for i in range(a1, len(order)) if order[i] < lead), len(order))
    tl_air, tl_floor = order[a0:a1], order[a1:t1]
    def keep(tl, n):
        used = sorted(set(tl))
        if n == 1:
            return used[:1]
        return used if len(used) <= n else [used[round(i * (len(used) - 1) / (n - 1))] for i in range(n)]
    taken = set(hit_plan(mk_dir)[0]) | set(throw_plan(mk_dir)[0])
    for fn, dd in ((rtele_plan, 'mk_moves_raiden'), (ice_plan, 'mk_moves_subzero'), (leg_plan, 'mk_moves_sonya'),
                   (flykick_plan, 'mk_moves_liukang')):
        if mk_dir == dd:
            taken |= {int(e.split('=')[0].replace(':', ''), 16) for e in fn(mk_dir)[1]}
    if MK_DIR_BY_ID.get(KANO_ID) and any(MK_DIR_BY_ID[f] == mk_dir for f in JUMP_FIGHTERS):
        taken |= {int(e.split('=')[0].replace(':', ''), 16) for e in jump_plan(mk_dir)[2]}
    if action == 'swept':                # (after every other plan: the knockdown's, the kick's)
        taken |= {int(e.split('=')[0].replace(':', ''), 16) for e in kd_plan(mk_dir)[2] + kick_plan(mk_dir)[1]}
    free = _free_slots(mk_dir, taken)
    n_air, n_floor = KD_KNOCKDOWN_POSES if action == 'knockdown' else (KD_AIR_POSES, KD_FLOOR_POSES)
    n = min(n_air + n_floor, len(free), KD_POSES_CAP.get(mk_dir, 99))   # (fewer slots or room: the same share)
    na = max(2, round(n * n_air / (n_air + n_floor)))
    ka, kf = keep(tl_air, na), keep(tl_floor, KD_FLOOR_N.get((mk_dir, action), max(2, n - na)))
    # lying: the floor's flattest pose always (spread evenly the floor's 5 had passed it over on all but Kano:
    # Sub-Zero landed half up - MK's 27 - and got up, never flat, 28: knocked down, never lying down).
    # It takes the nearest kept pose's place (a tie: the earlier, the half-up landing)
    if action == 'knockdown':            # (EC's own flight frame, 42:18, has this pose's art already: shared)
        fl = sf.knockdown_pose(poses, 0, 2)
        if fl not in ka and fl in tl_air:
            ka[min(range(len(ka)), key=lambda i: (abs(ka[i] - fl), ka[i]))] = fl
            ka = sorted(set(ka))
    def flatness(k):
        ys, xs = np.nonzero(poses[k])
        return (xs.max() - xs.min()) / (ys.max() - ys.min() + 1)
    flat = max(sorted(set(tl_floor)), key=flatness)
    if flat not in kf:
        kf[min(range(len(kf)), key=lambda i: (abs(kf[i] - flat), kf[i]))] = flat
        kf = sorted(set(kf))
    if len(kf) == 1:                     # (just the flat pose: no room for his getting up - EC's own after it)
        kf = [flat]
    slot = {}
    for k in ka + kf:
        if k not in slot:
            slot[k] = free.pop(0)
    near = lambda ks, k: min(ks, key=lambda q: abs(q - k))
    air_seq = [slot[near(ka, k)] for k in tl_air[::2]]
    floor_seq = [slot[near(kf, k)] for k in tl_floor[::2]]
    KD_FLAT[(mk_dir, action)] = floor_seq.index(slot[flat]) if slot[flat] in floor_seq else len(floor_seq) - 1
    pins = [f'{f >> 8:02x}:{f & 0xFF:02x}={k}' for k, f in slot.items()]
    return air_seq, floor_seq, pins


def hit_plan(mk_dir):
    """(calls, art pins) for MK's hit reaction (tools/lib/mkmoves.py hit_high):
    the poses from the first reaction pose (first shown after the hit lands,
    scorpion_full.HIT_LANDS) until the stance is back, at MK's timing, one
    frame word per r_drag call (every other frame). EC's own hit frames are
    pinned to the pose due when EC loads them; the others go on free frame
    slots (from the end of mkscripts' list: its attack scripts take the front)."""
    import mkscripts, scorpion_full
    P, order = mkscripts._load('hit_high', mk_dir)
    I, _ = mkscripts._load('idle', mk_dir)
    stance = {mkscripts._key(p) for p in I}
    first = {}
    for t, k in enumerate(order):
        first.setdefault(k, t)
    react = {k for k in first if first[k] >= scorpion_full.HIT_LANDS and mkscripts._key(P[k]) not in stance}
    t0 = next(t for t, k in enumerate(order) if k in react)
    t1 = next((t for t in range(t0, len(order)) if order[t] not in react), len(order))
    frames = order[t0:t1]
    calls = [frames[min(2 * c, len(frames) - 1)] for c in range((len(frames) + 1) // 2)]
    calls += [calls[-1]] * max(0, HIT_EC_AT[-1] + 1 - len(calls))
    slot = {}
    for f, c in zip(HIT_EC, HIT_EC_AT):
        slot.setdefault(calls[c], f)
    free = _free_slots(mk_dir)
    for k in calls:
        if k not in slot:
            slot[k] = free.pop(0)
    pins = [f'{f >> 8:02x}:{f & 0xFF:02x}={k}' for f, k in zip(HIT_EC, (calls[c] for c in HIT_EC_AT))]
    pins += [f'{f >> 8:02x}:{f & 0xFF:02x}={k}' for k, f in slot.items() if f not in HIT_EC]
    return tuple(slot[k] for k in calls), pins


KICK_DIRS = ('mk_moves', 'mk_moves_kano', 'mk_moves_johnny', 'mk_moves_liukang', 'mk_moves_subzero',
             'mk_moves_sonya')   # (their hit_kick captures: data/mk_recipes; Raiden: no .PL room yet)


def kick_plan(mk_dir):
    """(calls, art pins) for MK's reaction to a kick (hit_kick; EC puts a kicked fighter in $1A, a
    punched one in $1B - the hit drive picks): as hit_plan, from the first reaction pose to the stance,
    one frame word per call. A pose that is one of hit_plan's images keeps its slot; the others take
    free slots after every other plan's (the appended frames, extra_slots). Too few: hit_plan's own."""
    import mkscripts, scorpion_full
    if mk_dir not in KICK_DIRS:          # (Shang: the CPU's boss, his captures made otherwise - no recipe)
        return hit_plan(mk_dir)[0], []
    P, order = mkscripts._load('hit_kick', mk_dir)
    I, _ = mkscripts._load('idle', mk_dir)
    H, _ = mkscripts._load('hit_high', mk_dir)
    stance = {mkscripts._key(p) for p in I}
    first = {}
    for t, k in enumerate(order):
        first.setdefault(k, t)
    react = {k for k in first if first[k] >= scorpion_full.HIT_LANDS and mkscripts._key(P[k]) not in stance}
    t0 = next(t for t, k in enumerate(order) if k in react)
    t1 = next((t for t in range(t0, len(order)) if order[t] not in react), len(order))
    frames = order[t0:t1]
    # the standing part only: MK's captured kick knocked him down - doubled over, then off his feet and
    # flat - but EC's kicked fighter stays up (played whole, Sub-Zero sprawled on the floor and
    # hunched mid-stagger). Up to the first pose off the ground or lying, then
    # those poses back the other way: he straightens up again
    import numpy as np
    def feet_shape(k):
        ys, xs = np.nonzero(P[k])
        return (int(ys.max()), int(xs.max() - xs.min()), int(ys.max() - ys.min()) + 1) if len(ys) else None
    floor = max(int(np.nonzero(q)[0].max()) for q in I if q.any())   # his stance's feet (the idle capture: Kano's
                                                                      #  kick capture has no stance poses)
    def standing(k):
        f = feet_shape(k)
        return f is not None and f[0] >= floor - 14 and f[1] < 1.5 * f[2]   # (doubled over: up to 12 px)
    cut = next((i for i, k in enumerate(frames) if not standing(k)), len(frames))
    if 0 < cut < len(frames):
        down = frames[:cut]
        frames = down + [k for k in reversed(list(dict.fromkeys(down))[:-1]) for _ in range(down.count(k))]
    calls = [frames[min(2 * c, len(frames) - 1)] for c in range((len(frames) + 1) // 2)]
    hcalls, hpins = hit_plan(mk_dir)
    hslot = {}                                          # hit_high's images: their slots
    for e in hpins:
        f, k = e.split('=')
        hslot.setdefault(mkscripts._key(H[int(k)]), int(f.replace(':', ''), 16))
    taken = set(hcalls) | set(throw_plan(mk_dir)[0])
    for fn, dd in ((rtele_plan, 'mk_moves_raiden'), (ice_plan, 'mk_moves_subzero'), (leg_plan, 'mk_moves_sonya'),
                   (flykick_plan, 'mk_moves_liukang')):
        if mk_dir == dd:
            taken |= {int(e.split('=')[0].replace(':', ''), 16) for e in fn(mk_dir)[1]}
    if any(MK_DIR_BY_ID[f] == mk_dir for f in JUMP_FIGHTERS):
        taken |= {int(e.split('=')[0].replace(':', ''), 16) for e in jump_plan(mk_dir)[2]}
    if any(MK_DIR_BY_ID.get(f) == mk_dir for f in KD_FIGHTERS):
        taken |= {int(e.split('=')[0].replace(':', ''), 16) for e in kd_plan(mk_dir)[2]}
    free = _free_slots(mk_dir, taken)
    slot, need = {}, [k for k in dict.fromkeys(calls) if mkscripts._key(P[k]) not in hslot]
    if len(need) > len(free):
        return hcalls, []
    for k in dict.fromkeys(calls):
        slot[k] = hslot.get(mkscripts._key(P[k])) or free.pop(0)
    pins = [f'{slot[k] >> 8:02x}:{slot[k] & 0xFF:02x}={k}' for k in need]
    return tuple(slot[k] for k in calls), pins


SPEAR_BARE_POSE = 6                 # the spear capture's arm-out throw before the rope shows (MK's miss / block hold)


def spear_bare_slot(mk_dir='mk_moves'):
    """The frame slot (Blade numbering) for MK's bare throw (SPEAR_BARE_POSE): the last free slot
    after every plan's pins (the others take theirs from the front)."""
    pins = []
    for fn in (lambda d: throw_plan(d)[1], lambda d: hit_plan(d)[1], lambda d: kick_plan(d)[1]):
        pins += fn(mk_dir)
    if any(MK_DIR_BY_ID.get(f) == mk_dir for f in JUMP_FIGHTERS):
        pins += jump_plan(mk_dir)[2]
    if any(MK_DIR_BY_ID.get(f) == mk_dir for f in KD_FIGHTERS):
        pins += kd_plan(mk_dir)[2]
        if mk_dir in SWEPT_DIRS:
            pins += kd_plan(mk_dir, 'swept')[2]
    taken = {int(e.split('=')[0].replace(':', ''), 16) for e in pins} | set(hit_plan(mk_dir)[0]) \
        | set(throw_plan(mk_dir)[0]) | set(kick_plan(mk_dir)[0])
    return _free_slots(mk_dir, taken)[-1]


def walk_plan(mk_dir):
    """(forward calls, back calls, art pins) for a fighter's MK walk: 9
    poses on 40:64-40:6C, MK's timing over EC's 36-frame cycle, EC's own
    walk frames 40:16-40:1B pinned to the pose due when each step starts.
    A glide (Shang Tsung: one held pose each way, no step loop) comes as
    walk_fwd/glide.json: 40:64 and 40:65 hold the poses, 40:66.. the poses
    he steps into them with (glide_frames; his scripts show them, no drive)."""
    glide = glide_frames(mk_dir)
    if glide:
        f, b = glide['fwd'], glide['back']
        pins = [f'40:64={f}', f'40:65={b}'] + [f'40:{0x16 + j:02x}={f}' for j in range(6)]
        pins += [f'40:{fr & 0xFF:02x}={k}' for side in ('fwd_start', 'back_start') for fr, k, _ in glide[side]]
        return (0,) * 18, (1,) * 18, pins
    cyc = walk_cycle(mk_dir)[:len(WALK_FRAMES)]
    frames = [i for i, (k, n) in enumerate(cyc) for _ in range(n)]
    frames = (frames + [frames[-1]] * 36)[:36]
    fwd = tuple(frames[2 * t] for t in range(18))
    back = tuple(frames[(30 - 2 * t) % 36] for t in range(18))
    pins = [f'40:{0x64 + i:02x}={k}' for i, (k, _) in enumerate(cyc)]
    pins += [f'40:{0x16 + j:02x}={cyc[frames[6 * j]][0]}' for j in range(6)]
    return fwd, back, pins


HIT_STATE = 0x1A              # EC's hit reaction (standing)


class _HitCalls(dict):
    def __missing__(self, mk_dir):
        self[mk_dir] = hit_plan(mk_dir)[0]
        return self[mk_dir]


HIT_CALLS = _HitCalls()


class _ThrowCalls(dict):
    def __missing__(self, mk_dir):
        self[mk_dir] = throw_plan(mk_dir)[0]
        return self[mk_dir]


THROW_CALLS = _ThrowCalls()


def flush_late(a):
    """room_put's last resort (every room full): its items after all of the block's code."""
    for label, data, subs in getattr(a, 'late', []):
        while len(a.out) % 2:
            a.out += b'\0'
        a.label(label)
        for k, v in subs.items():
            a.labels[k] = a.labels[label] + v
        a.out += data
    a.late = []


def room_put(a, label, data, subs=None):  # (up to DAZE_PAD: the room's end is daze_pad's)
    """Data (or position-free code) for block a in the second victory room (GEN_ROOM, written by
    patches mk_code), else after the knockdown drive in the first (GEN_KD): label points at it (the
    block reaches it PC-relative)."""
    if 'data' not in GEN_ROOM:
        GEN_ROOM.update(off=VROOM[1][0], data=bytearray())
    assert len(data) % 2 == 0
    if GEN_ROOM['off'] + len(GEN_ROOM['data']) + len(data) <= DAZE_PAD:
        at = GEN_ROOM['off'] + len(GEN_ROOM['data'])
        GEN_ROOM['data'] += data
    else:                                # full: the first victory room, after his knockdown drive (low_kd)
        if 'data' not in GEN_KD:
            GEN_KD.update(off=VROOM[0][0], data=b'')
        kd = bytearray(GEN_KD['data'])
        kd += bytes(len(kd) % 2)
        at = GEN_KD['off'] + len(kd)
        kd += data
        if GEN_KD['off'] + len(kd) <= VROOM[0][1]:
            GEN_KD['data'] = bytes(kd)
        else:                            # both victory rooms full: a dead script body of Blade's (GEN_DEAD) ...
            at = dead_put(data)
            if at is None:               # ... else after the block's code (flush_late)
                a.late = getattr(a, 'late', []) + [(label, data, subs or {})]
                return
    a.labels[label] = at - EXT_OFF
    for k, v in (subs or {}).items():
        a.labels[k] = at - EXT_OFF + v


def dead_put(data):
    """data at the first place in GEN_DEAD's free bodies it fits (even), or None."""
    for k, (start, end) in enumerate(GEN_DEAD.get('free', ())):
        at = (start + 1) & ~1
        if at + len(data) <= end:
            GEN_DEAD['free'][k] = (at + len(data), end)
            GEN_DEAD['pieces'].append((at, bytes(data)))
            return at
    return None


def dead_bodies(co, slots):
    """[(start, end)]: module offsets of the bodies (all but the first 4 bytes) of the chain's scripts
    whose slot is in slots."""
    import patches
    W = lambda o: int.from_bytes(co[o:o + 2], 'big', signed=True)
    o, out = patches.CHAIN_START, []
    while W(o) >= 0:
        n = 20 + 12 * (W(o + 2) + 1)
        if W(o) in slots:
            out.append((o + 4, o + n))
        o += n
    return out


EC_PUNCHES = ((0x01, 0x03), (0x0E, 0x10), (0x20, 0x22))   # EC's move ids: X/Y/Z, crouching, close


def emit_ispunch(a):
    """'ispunch' (a1 = the hit fighter) / 'ispunch5' (a5): Z set when his reaction should be MK's punch
    reaction - EC's state $1B, or $1A from an EC attacker's punch (EC puts every hit of its own fighters
    in $1A: an MK fighter doubled over at a jab - MK snaps the head back). Keeps d0/a0. In the second
    victory room (room_put): the block's two choices of table call it, 2 bytes shorter than the compare."""
    if 'ispunch' in a.labels or any(l == 'ispunch5' for l, _, _ in getattr(a, 'late', [])):
        return
    r = Asm(0)
    r.label('ispunch5')
    r.w(0x2F09)                          # move.l a1,-(sp)
    r.w(0x224D)                          # movea.l a5,a1
    r.bcc(0x61, 'ispunch')               # bsr.s ispunch
    r.w(0x225F)                          # movea.l (sp)+,a1    (flags kept)
    r.w(0x4E75)                          # rts
    r.label('ispunch')                   # (d0 = the reaction's step x2: 0 = the hit's first call)
    r.w(0x0C29, HIT_STATE + 1, 0x00BF)   # cmpi.b #$1B,$BF(a1)
    r.bcc(0x67, 'ip_r')                  # beq: punched (Z)
    r.w(0x2F08)                          # move.l a0,-(sp)
    r.w(0x3F00)                          # move.w d0,-(sp)
    r.pcrel(0x41FA, 'ip_f')              # lea flags(pc),a0    (per player: 0 = a punch)
    r.w(0xB3FC); r.l(0x2E188)            # cmpa.l #P1,a1
    r.bcc(0x67, 'ip_1')
    r.w(0x5288)                          # addq.l #1,a0
    r.label('ip_1')
    r.w(0x4A40)                          # tst.w d0
    r.bcc(0x66, 'ip_u')                  # not the hit's first call: as decided then
    r.w(0x2F08)                          # move.l a0,-(sp)
    r.w(0x2069, 0x008C)                  # movea.l $8C(a1),a0  his attacker
    r.w(0x7000)                          # moveq #0,d0
    r.w(0x1028, 0x00BF)                  # move.b $BF(a0),d0   its move
    base = 0
    for lo, hi in EC_PUNCHES:
        r.w(0x0440, lo - base)           # subi.w #(lo - previous lo),d0
        r.w(0x0C40, hi - lo)             # cmpi.w #n,d0
        r.bcc(0x63, 'ip_p')              # bls: one of EC's punches
        base = lo
    r.w(0x205F)                          # movea.l (sp)+,a0
    r.w(0x50D0)                          # st (a0)             a kick
    r.bcc(0x60, 'ip_u')
    r.label('ip_p')
    r.w(0x205F)                          # movea.l (sp)+,a0
    r.w(0x4210)                          # clr.b (a0)          a punch
    r.label('ip_u')
    r.w(0x301F)                          # move.w (sp)+,d0
    r.w(0x4A10)                          # tst.b (a0)          Z: a punch
    r.w(0x205F)                          # movea.l (sp)+,a0    (flags kept)
    r.label('ip_r')
    r.w(0x4E75)                          # rts
    r.label('ip_f')
    r.w(0xFFFF)                          # P1, P2: a kick until decided
    code = r.build()
    room_put(a, 'ispunch5', code, {'ispunch': r.labels['ispunch']})


BLOCK_POSE = 0x4236                 # EC's block frame (state 7): MK's block pose in MK fighters' art
AIR_ATTACKS = (0x26, 0x2B)          # Blade's moving jump attacks (patches.AIR_MOVING; $28 Z: nothing for MK)
AIR_UP_PUNCH = (0x14, 0x15)         # his straight-up X / Y: held to the landing too (patches.AIR_UP_PUNCH)


def emit_airland(a):
    """'airland' (from r_jumpup, the step loader: a5 = him, $1A just loaded; d0 free): in a forward / back
    jump attack or a straight-up punch (both held to the landing: patches.mk_air_hold), the landing's
    41:03 / 41:04 (MK's straight-jump poses, mapped 'jump_up') load as the
    landing crouch, 40:06 - they flashed 2 frames between the held attack and the crouch (inputaudit:
    'jump_up:2' after every jump attack). In the air EC's hold (PLYR $1874E) puts the attack back over
    it. In the second victory room (room_put)."""
    if 'airland' in a.labels or any(l == 'airland' for l, _, _ in getattr(a, 'late', [])):
        return
    r = Asm(0)
    r.w(0x302D, 0x00BE)                  # move.w $BE(a5),d0
    r.w(0x0240, 0x7FFF)                  # andi.w #$7FFF,d0
    for m in AIR_UP_PUNCH:
        r.w(0x0C40, m)                   # cmpi.w #$14 / #$15,d0   a straight-up punch (held too)
        r.bcc(0x67, 'al_f')
    r.w(0x0440, AIR_ATTACKS[0])          # subi.w #$26,d0
    r.w(0x0C40, AIR_ATTACKS[1] - AIR_ATTACKS[0])   # cmpi.w #5,d0
    r.bcc(0x62, 'al_x')                  # bhi: not a jump attack
    r.label('al_f')
    r.w(0x302D, 0x001A)                  # move.w $1A(a5),d0
    r.w(0x0C40, fr(0x4103))              # cmpi.w #41:03,d0
    r.bcc(0x67, 'al_s')
    r.w(0x0C40, fr(0x4104))              # cmpi.w #41:04,d0
    r.bcc(0x66, 'al_x')
    r.label('al_s')
    r.w(0x3B7C, fr(0x4006), 0x001A)      # move.w #40:06,$1A(a5)  the landing crouch
    r.label('al_x')
    r.w(0x4E75)                          # rts
    room_put(a, 'airland', r.build())


RINGS_AT = LOW_OFF + ZF_SIZE          # in Sonya's module: patches.rings_code (the low room after zf, 64 bytes)


def emit_zblock(a):
    """'zblock' (a1 = an MK fighter, from his drive at the start of his input task - before it reads his
    pad, PLYR $15228; uses nothing): MK's Block. A human player holding Z while the opponent attacks
    (his $F7 bit 5 clears from an attack's first frame; not dazed) gets 'away' in his pad: EC blocks
    by holding away. (zf did this at the stand loop's request read - after the pad was read, so EC
    never saw it held: Z didn't block, traced.) In the second victory room (room_put)."""
    if 'zblock' in a.labels or any(l == 'zblock' for l, _, _ in getattr(a, 'late', [])):
        return
    r = Asm(0)
    r.w(0x4A69, 0x012A)                  # tst.w $12A(a1)      the CPU's: its own input
    r.bcc(0x66, 'zb_x')
    r.w(0x48E7, 0x40A0)                  # movem.l d1/a0/a2,-(sp)
    if SCORPION_ID == SONYA_ID:          # (a human's Sonya: her rings out of her high punch, patches.rings_code)
        r.w(0x2069, 0x018C)              # movea.l $18C(a1),a0 her module's code start (+$A)
        r.w(0x4EA8, RINGS_AT - 10)       # jsr rings - $A(a0)
    r.w(0x41EE, 0x0A3A)                  # lea $A3A(a6),a0     his pad (player 1's ...
    r.w(0xB3FC); r.l(0x2E188)            # cmpa.l #P1,a1
    r.bcc(0x67, 'zb_p')
    r.w(0x5488)                          # addq.l #2,a0        ... or player 2's)
    r.label('zb_p')
    r.w(0x0810, 0x0000)                  # btst #0,(a0)        Z held?
    r.bcc(0x67, 'zb_r')
    r.w(0x3229, 0x00BE)                  # move.w $BE(a1),d1   standing or EC's walk back to the block:
    r.w(0x0241, 0x7FFF)                  # andi.w #$7FFF,d1     MK's block pose at once (EC walked him
    r.bcc(0x67, 'zb_bp')                 #  back 8 frames in walk poses first; with no attack, nothing)
    r.w(0x0C41, 0x0004)                  # cmpi.w #4,d1
    r.bcc(0x66, 'zb_np')
    r.label('zb_bp')
    r.w(0x337C, fr(BLOCK_POSE), 0x001A)  # move.w #42:36,$1A(a1)
    r.label('zb_np')
    r.w(0x2469, 0x008C)                  # movea.l $8C(a1),a2  his opponent
    r.w(0x082A, 0x0005, 0x00F7)          # btst #5,$F7(a2)     attacking?
    r.bcc(0x66, 'zb_r')
    r.w(0x0C6A, DIZZY, 0x00BE)           # cmpi.w #$1F,$BE(a2) (dazed: no)
    r.bcc(0x67, 'zb_r')
    r.w(0x7208)                          # moveq #8,d1         away = right ...
    r.w(0x0829, 0x0003, 0x0020)          # btst #3,$20(a1)     facing left?
    r.bcc(0x66, 'zb_a')
    r.w(0x7204)                          # moveq #4,d1         ... or left
    r.label('zb_a')
    r.w(0x8350)                          # or.w d1,(a0)
    r.label('zb_r')
    r.w(0x4CDF, 0x0502)                  # movem.l (sp)+,d1/a0/a2
    r.label('zb_x')
    r.w(0x4E75)                          # rts
    room_put(a, 'zblock', r.build())


def emit_zpose(a):
    """'zpose' (from r_jumpup, the step loader: a5 = him, $1A just loaded; d0/a0 free): MK's Block pose - a
    human holding Z, standing or walked back by EC to block: the step's stance or walk pose loads as the
    block pose (42:36), so EC's animation doesn't show between zblock's calls. In a room (room_put)."""
    if 'zpose' in a.labels or any(l == 'zpose' for l, _, _ in getattr(a, 'late', [])):
        return
    r = Asm(0)
    r.w(0x4A6D, 0x012A)                  # tst.w $12A(a5)      the CPU's
    r.bcc(0x66, 'zp_x')
    r.w(0x41EE, 0x0A3A)                  # lea $A3A(a6),a0     his pad
    r.w(0xBBFC); r.l(0x2E188)            # cmpa.l #P1,a5
    r.bcc(0x67, 'zp_p')
    r.w(0x5488)                          # addq.l #2,a0
    r.label('zp_p')
    r.w(0x0810, 0x0000)                  # btst #0,(a0)        Z held?
    r.bcc(0x67, 'zp_x')
    r.w(0x302D, 0x00BE)                  # move.w $BE(a5),d0
    r.w(0x0240, 0x7FFF)                  # andi.w #$7FFF,d0
    r.bcc(0x67, 'zp_bp')
    r.w(0x0C40, 0x0004)                  # cmpi.w #4,d0
    r.bcc(0x66, 'zp_x')
    r.label('zp_bp')
    r.w(0x3B7C, fr(BLOCK_POSE), 0x001A)  # move.w #42:36,$1A(a5)
    r.label('zp_x')
    r.w(0x4E75)                          # rts
    room_put(a, 'zpose', r.build())


def emit_hitfix(a, pfx='g_ht', per_player=False):
    """g_hfix (from r_jumpup, the step loader: a5 = him, EC has just put its own hit frame in $1A;
    d0/a0 free): while he is in a hit state ($1A, $1B), the hit drive's current MK pose (its first
    before the drive's first call) goes straight back over EC's - EC's hit frames (pinned to punch poses) showed
    for 2 frames whenever a step loaded, between the drive's calls (every other frame)."""
    a.label('g_hfix')
    a.w(0x302D, 0x00BE)                  # move.w $BE(a5),d0
    a.w(0x0240, 0x7FFF)                  # andi.w #$7FFF,d0
    a.w(0x0440, HIT_STATE)               # subi.w #$1A,d0
    a.w(0x0C40, 0x0001)                  # cmpi.w #1,d0
    a.bcc(0x62, 'hf_x')                  # bhi: not hit
    a.pcrel(0x41FA, f'{pfx}_cnt')        # lea cnt(pc),a0
    if per_player:                       # (Scorpion's block drives either side: P2's count at +4)
        a.w(0xBBFC); a.l(0x2E188)        # cmpa.l #P1,a5
        a.bcc(0x67, 'hf_p1')
        a.w(0x5888)                      # addq.l #4,a0
        a.label('hf_p1')
    a.w(0x3010)                          # move.w (a0),d0
    a.bcc(0x6A, 'hf_s')                  # bpl: started
    a.w(0x7000)                          # moveq #0,d0         not yet (it runs every other frame):
    a.label('hf_s')                      #  its first pose now - EC's hit frame showed 2 frames first
    a.w(0xD040)                          # add.w d0,d0
    a.pcrel(0x41FA, f'{pfx}_tab')        # lea tab(pc),a0
    if f'{pfx}_tabb' in a.labels:
        emit_ispunch(a)
        a.bccw(0x61, 'ispunch5')         # bsr.w ispunch5      (punched: his punch reaction)
        a.bcc(0x66, 'hf_k')
        a.pcrel(0x41FA, f'{pfx}_tabb')
        a.label('hf_k')
    a.w(0x3B70, 0x0000, 0x001A)          # move.w (a0,d0.w),$1A(a5)
    a.label('hf_x')
    a.w(0x4E75)                          # rts


def emit_hitdrive(a, calls, pfx, done, per_player, state=None, script=True, room=False, calls_b=None):
    """MK's hit reaction at MK's timing (hit_plan): a1 = the fighter. While
    he is in EC's hit state, one entry of calls per call, restarted when EC
    starts a hit (his counter is -1 outside the state, or EC's script is
    back at its first step after it moved on); the last pose holds. Then
    branches to done. Outside the state it falls through. per_player: d1 =
    the player (0/4) picks the counter (Scorpion's block drives either side
    in a mirror match). Uses d0/a0."""
    a.pcrel(0x41FA, f'{pfx}_cnt')        # lea cnt(pc),a0
    if per_player:
        a.w(0xD0C1)                      # adda.w d1,a0
    a.w(0x3029, 0x00BE)                  # move.w $BE(a1),d0
    a.w(0x0240, 0x7FFF)                  # andi.w #$7FFF,d0
    a.w(0x0C40, HIT_STATE if state is None else state)   # cmpi.w #state,d0
    a.bcc(0x67, f'{pfx}_in')
    if state is None:                    # EC's other standing hit ($1B: punches - it held two frames
        a.w(0x0C40, HIT_STATE + 1)       #  ~40 frames; kicks are $1A): MK's reaction there too
        a.bcc(0x67, f'{pfx}_in')
    a.w(0x30BC, 0xFFFF)                  # move.w #-1,(a0)
    a.bccw(0x60, f'{pfx}_no')
    a.label(f'{pfx}_in')
    if not script:                       # (the throw: EC back in his stance 40:00-40:02 ends it)
        a.w(0x0C29, fr(0x4000) >> 8, 0x001A)   # cmpi.b #sheet,$1A(a1)
        a.bcc(0x66, f'{pfx}_ns')
        a.w(0x0C29, 0x0002, 0x001B)      # cmpi.b #2,$1B(a1)
        a.bccw(0x63, f'{pfx}_no')        # bls
        a.label(f'{pfx}_ns')
    a.w(0x4A50)                          # tst.w (a0)
    a.bcc(0x6B, f'{pfx}_rst')            # bmi: just hit
    if script:                           # (a hit: EC's script restarting is a new hit)
        a.w(0x2029, 0x00AE)              # move.l $AE(a1),d0
        a.w(0xB0A9, 0x00AA)              # cmp.l $AA(a1),d0
        a.bcc(0x66, f'{pfx}_inc')        # EC past its first step
        a.w(0x0C50, HIT_EC_AT[1])        # cmpi.w #3,(a0)
        a.bcc(0x64, f'{pfx}_rst')        # bhs: back at the first step: hit again
    a.label(f'{pfx}_inc')
    a.w(0x5250)                          # addq.w #1,(a0)
    if calls_b is not None:              # (both tables as long: the last pose held)
        n = max(len(calls), len(calls_b))
        calls = tuple(calls) + (calls[-1],) * (n - len(calls))
        calls_b = tuple(calls_b) + (calls_b[-1],) * (n - len(calls_b))
    a.w(0x0C50, len(calls) - 1)          # cmpi.w #last,(a0)
    a.bcc(0x63, f'{pfx}_set')            # bls
    a.w(0x30BC, len(calls) - 1)          # move.w #last,(a0)
    a.bcc(0x60, f'{pfx}_set')
    a.label(f'{pfx}_rst')
    a.w(0x4250)                          # clr.w (a0)
    a.label(f'{pfx}_set')
    a.w(0x3010)                          # move.w (a0),d0
    a.w(0xD040)                          # add.w d0,d0
    a.pcrel(0x41FA, f'{pfx}_tab')        # lea tab(pc),a0
    if calls_b is not None:              # (punched - $1B, or an EC fighter's punch - his punch reaction;
        emit_ispunch(a)                  #  kicked, $1A, the kick's)
        a.bccw(0x61, 'ispunch')          # bsr.w ispunch
        a.bcc(0x66, f'{pfx}_k')
        a.pcrel(0x41FA, f'{pfx}_tabb')   # lea tab_b(pc),a0
        a.label(f'{pfx}_k')
    a.w(0x3370, 0x0000, 0x001A)          # move.w (a0,d0.w),$1A(a1)
    a.bccw(0x60, done)
    tab = b''.join(fr(f).to_bytes(2, 'big') for f in calls)
    cnt = bytes.fromhex('ffff0000ffff0000')   # (P1 at +0, P2 at +4)
    tab_b = b''.join(fr(f).to_bytes(2, 'big') for f in calls_b) if calls_b is not None else None
    if room:                             # (the tables and counts in the second victory room: block room)
        room_put(a, f'{pfx}_tab', tab)
        if tab_b is not None:
            room_put(a, f'{pfx}_tabb', tab_b)
        room_put(a, f'{pfx}_cnt', cnt)
    else:
        a.label(f'{pfx}_tab')
        a.out += tab
        if tab_b is not None:
            a.label(f'{pfx}_tabb')
            a.out += tab_b
        a.label(f'{pfx}_cnt')
        a.out += cnt
    a.label(f'{pfx}_no')


THROWN = 0x37                 # EC's victim state while being thrown
THROW_DROP = 3                # px/frame down as she is released (emit_throwfix)
# speed across (px/frame x256) of the victim's fall after the release, by
# thrower (measured on the MK disc: Scorpion's and Sub-Zero's roll throws
# land him ~110 px behind - where EC's choreography leaves him - Raiden's
# and Johnny's overhead tosses ~155 px: +35 px over EC's ~28-frame arc)
THROW_PUSH = {22: 0, 20: 0, 19: 0, 18: 0, 12: 0, 13: 0, 17: 0, 11: 0, 26: 0}   # (the distance is the throw records' now: patches.THROW_FAR)
FLOOR_Y = 0x1496              # (a6): the fighters' floor line
POS_Y = (0x38, 0x3C, 0x52, 0x58, 0xB6, 0xBC)   # a fighter's y, every copy (ecstage.POS_Y)


def emit_rtele(a):
    """Raiden's teleport (a1 = him): when his move $31 script reaches step
    RTELE_AT, he is put RTELE_BEHIND px past his opponent and turned round.
    Uses d0/d1/a0/a2."""
    a.pcrel(0x45FA, 'rt_flag')           # lea flag(pc),a2
    a.w(0x3029, 0x00BE)                  # move.w $BE(a1),d0
    a.w(0x0240, 0x7FFF)                  # andi.w #$7FFF,d0
    a.w(0x0C40, RTELE_MOVE)              # cmpi.w #$31,d0
    a.bcc(0x67, 'rt_in')
    a.w(0x4252)                          # clr.w (a2)
    a.bccw(0x60, 'rt_x')
    a.label('rt_in')
    a.w(0x4A52)                          # tst.w (a2)           done this time
    a.bccw(0x66, 'rt_x')
    if SCRIPT_TAIL:                      # his scripts in his .PL's tail (generic_block)
        a.bccw(0x61, 'pl_tail')          # bsr pl_tail         a0 = the tail
        a.w(0xD0FC, SCRIPT_TAIL[RTELE_MOVE])   # adda.w #script,a0
    else:
        a.pcrel(0x41FA, f'gs_{RTELE_MOVE}')    # lea script(pc),a0
    a.w(0x41E8, 20 + 12 * RTELE_AT)      # lea step(a0),a0
    a.w(0xB1E9, 0x00AE)                  # cmpa.l $AE(a1),a0
    a.bccw(0x66, 'rt_x')
    a.w(0x34BC, 0x0001)                  # move.w #1,(a2)
    a.w(0x2069, 0x008C)                  # movea.l $8C(a1),a0   his opponent
    a.w(0x3028, 0x004E)                  # move.w $4E(a0),d0
    a.w(0x3229, 0x004E)                  # move.w $4E(a1),d1
    a.w(0xB240)                          # cmp.w d0,d1
    a.bcc(0x6D, 'rt_r')                  # blt: he is on the left: over to the right
    a.w(0x0440, RTELE_BEHIND)            # subi.w #px,d0
    a.bcc(0x60, 'rt_set')
    a.label('rt_r')
    a.w(0x0640, RTELE_BEHIND)            # addi.w #px,d0
    a.label('rt_set')
    for o in (0x36, 0x3A, 0x4E, 0x56, 0xB2, 0xBA):   # every copy of his x
        a.w(0x3340, o)                   # move.w d0,o(a1)
    a.w(0x0869, 0x0003, 0x0020)          # bchg #3,$20(a1)      facing him
    a.w(0x0869, 0x0003, 0x0100)          # bchg #3,$100(a1)
    a.bcc(0x60, 'rt_x')
    a.label('rt_flag')
    a.w(0)
    a.label('rt_x')


SUBZERO_ID = 20
# Shang's blends in MK's EMP order (22-24 Johnny, 25-27 Kano, 28-30 Raiden, 31-33 Liu Kang,
# 34-36 Scorpion, 37-39 Sub-Zero, 40-42 Sonya; 43-45, Goro, unused)
MORPH_BLEND.update({fid: k for k, fid in enumerate((JOHNNY_ID, KANO_ID, RAIDEN_ID, LIUKANG_ID,
                                                    SCORPION_ID_FIXED, SUBZERO_ID, SONYA_ID))})
# each MK fighter's own effect sheet (his projectile, Sub-Zero's held heads):
# sheet numbers are global, so Blade's $44 in all of them collided (MK vs MK:
# the head Sub-Zero holds drew as his opponent's bolt; Blade's gauntlet vs them)
FX_SHEET = {RAIDEN_ID: 0x76, JOHNNY_ID: 0x77, SUBZERO_ID: 0x78, LIUKANG_ID: 0x79, KANO_ID: 0x7A, SONYA_ID: 0x7B,
            SHANG_ID: 0xAC, REPTILE_ID: 0xF5}   # (Shang, Reptile: sheet ids no EC file uses)


def fx_sheet():
    """The effect sheet of the fighter being built (SCORPION_ID's context)."""
    import mkprojectile
    return FX_SHEET.get(SCORPION_ID, mkprojectile.SHEET)
FZ_GRACE = 8                  # calls after the freeze starts in which a hit doesn't break it (the ice ball's own)
FZ_CALLS = 96                 # calls (2 frames): MK's freeze holds him 192 frames (measured, mk_subzero_2p)
PAL_BUF, PAL_DIRTY = -0x6956, -0x67D4   # (a6): EC's palette copy (64 words) and its upload flag (SUB $CF12)


def _freeze_tint():
    """Genesis colour words by R+G+B (0-21): MK's frozen look (measured:
    blue up, green a little, red down; e.g. (7,7,6) -> (5,7,7))."""
    out = []
    for t in range(22):
        lum = t / 3
        r, g, b = max(0, round(lum - 2)), min(7, round(lum + 0.5)), min(7, round(lum + 2.5))
        out.append(b << 9 | g << 5 | r << 1)
    return out


def emit_freeze(a):
    """Sub-Zero's ice blast freezes like MK's (a1 = him): when it hits, his
    opponent's move task is parked in a loop that holds him dazed ($1F, so
    his input starts nothing) with his pose as it was, his colours turn icy,
    and he shakes 2 px every other call, for FZ_CALLS calls; then he is sent
    back to standing (his idle resume address, recorded while he stands, as
    r_drag's daze end) and his colours come back. A hit breaks it (EC's
    reaction takes over his task). Uses d0-d3/a0/a2-a5."""
    a.pcrel(0x45FA, 'fz_v')              # lea vars(pc),a2  +0 calls, +2 done this blast, +4 him, +8 his idle PC,
    a.w(0x2669, 0x008C)                  # movea.l $8C(a1),a3   +12 his x, +14 shake, +16 his 15 colours
    a.w(0x4A6B, 0x00BE)                  # tst.w $BE(a3)        standing: where his task resumes
    a.bcc(0x66, 'fz_ni')
    a.w(0x206B, 0x0088)                  # movea.l $88(a3),a0
    a.w(0x2050)                          # movea.l (a0),a0
    a.w(0x2568, 0x0004, 0x0008)          # move.l 4(a0),8(a2)
    a.label('fz_ni')
    a.w(0x4A52)                          # tst.w (a2)
    a.bccw(0x66, 'fz_run')
    a.pcrel(0x41FA, 'pj_v')              # lea pj_v(pc),a0      his ice ball hit (emit_proj)?
    a.w(0x4A68, 0x0002)                  # tst.w 2(a0)
    a.bccw(0x67, 'fz_x')
    a.w(0x4268, 0x0002)                  # clr.w 2(a0)          (MK: frozen at once, no hit reaction)
    a.w(0x4AAA, 0x0008)                  # tst.l 8(a2)          (never seen standing: leave him)
    a.bccw(0x67, 'fz_x')
    a.w(0x302B, 0x00BE)                  # move.w $BE(a3),d0    blocked it (EC's block, standing 7 or
    a.w(0x0240, 0x7FFF)                  # andi.w #$7FFF,d0      crouching $C: EC calls the hit back for a
    a.w(0x0C40, 0x0007)                  # cmpi.w #7,d0          blocked shot too): as MK, no freeze
    a.bccw(0x67, 'fz_x')
    a.w(0x0C40, 0x000C)                  # cmpi.w #$C,d0
    a.bccw(0x67, 'fz_x')
    a.w(0x357C, 0x0001, 0x0002)          # move.w #1,2(a2)
    a.w(0x34BC, FZ_CALLS)                # move.w #calls,(a2)
    a.w(0x254B, 0x0004)                  # move.l a3,4(a2)
    a.w(0x356B, 0x004E, 0x000C)          # move.w $4E(a3),12(a2)
    a.w(0x356B, 0x001A, 0x002E)          # move.w $1A(a3),46(a2)   his pose, held
    a.w(0x426A, 0x000E)                  # clr.w 14(a2)
    a.w(0x206B, 0x0088)                  # movea.l $88(a3),a0
    a.w(0x2050)                          # movea.l (a0),a0
    a.pcrel(0x487A, 'fz_park')           # pea park(pc)
    a.w(0x215F, 0x0004)                  # move.l (sp)+,4(a0)
    a.w(0x4268, 0x0008)                  # clr.w 8(a0)
    for o in (0x5E, 0x62, 0xC6, 0xCA):
        a.w(0x42AB, o)                   # clr.l o(a3)          no speed
    a.bccw(0x61, 'fz_line')              # bsr: a0 = his colours
    a.w(0x5488)                          # addq.l #2,a0         (colour 0: the backdrop)
    a.w(0x49EA, 0x0010)                  # lea 16(a2),a4
    a.pcrel(0x4BFA, 'fz_tab')            # lea tab(pc),a5
    a.w(0x760E)                          # moveq #14,d3
    a.label('fz_tl')
    a.w(0x3010)                          # move.w (a0),d0
    a.w(0x38C0)                          # move.w d0,(a4)+      kept
    a.w(0x3200)                          # move.w d0,d1
    a.w(0xE249)                          # lsr.w #1,d1
    a.w(0x0241, 0x0007)                  # andi.w #7,d1         R
    a.w(0x3400)                          # move.w d0,d2
    a.w(0xEA4A)                          # lsr.w #5,d2
    a.w(0x0242, 0x0007)                  # andi.w #7,d2         G
    a.w(0xD242)                          # add.w d2,d1
    a.w(0xE048)                          # lsr.w #8,d0
    a.w(0xE248)                          # lsr.w #1,d0
    a.w(0x0240, 0x0007)                  # andi.w #7,d0         B
    a.w(0xD240)                          # add.w d0,d1
    a.w(0xD241)                          # add.w d1,d1
    a.w(0x30F5, 0x1000)                  # move.w (a5,d1.w),(a0)+   icy
    a.dbra(3, 'fz_tl')
    a.w(0x3D7C, 0xFFFF, PAL_DIRTY & 0xFFFF)   # move.w #-1,dirty(a6)
    a.bccw(0x60, 'fz_x')
    a.label('fz_run')
    a.w(0x266A, 0x0004)                  # movea.l 4(a2),a3
    a.w(0x302B, 0x00BE)                  # move.w $BE(a3),d0
    a.w(0x0240, 0x7FFF)
    a.w(0x0C52, FZ_CALLS - FZ_GRACE)     # cmpi.w #calls-grace,(a2)  just frozen: EC's own reaction
    a.bcc(0x62, 'fz_gr')                 # bhi                        to the ice ball's hit is overruled
    a.w(0x0440, HIT_FIRST)               # subi.w #$1A,d0
    a.w(0x0C40, HIT_LAST - HIT_FIRST)
    a.bccw(0x63, 'fz_col')               # bls: hit out of it (EC's reaction has him)
    a.label('fz_gr')
    # EC's own end of the reaction he was in (its stun clock) tries to stand
    # him up: kept parked
    a.w(0x0C6B, DIZZY, 0x00BE)           # cmpi.w #$1F,$BE(a3)
    a.bcc(0x67, 'fz_pk')
    a.w(0x206B, 0x0088)                  # movea.l $88(a3),a0
    a.w(0x2050)                          # movea.l (a0),a0
    a.pcrel(0x487A, 'fz_park')           # pea park(pc)
    a.w(0x215F, 0x0004)                  # move.l (sp)+,4(a0)
    a.w(0x4268, 0x0008)                  # clr.w 8(a0)
    a.w(0x377C, DIZZY, 0x00BE)           # move.w #$1F,$BE(a3)
    a.label('fz_pk')
    a.w(0x376A, 0x002E, 0x001A)          # move.w 46(a2),$1A(a3)   frozen in it
    for o in (0x5E, 0x62, 0xC6, 0xCA):
        a.w(0x42AB, o)                   # clr.l o(a3)          no drift
    a.w(0x5352)                          # subq.w #1,(a2)
    a.bcc(0x67, 'fz_end')
    a.w(0x086A, 0x0000, 0x000F)          # bchg #0,15(a2)       shake
    a.w(0x302A, 0x000C)                  # move.w 12(a2),d0
    a.w(0x082A, 0x0000, 0x000F)          # btst #0,15(a2)
    a.bcc(0x67, 'fz_sx')
    a.w(0x5440)                          # addq.w #2,d0
    a.label('fz_sx')
    for o in POS_X_ALL:
        a.w(0x3740, o)                   # move.w d0,o(a3)
    a.bccw(0x60, 'fz_x')
    a.label('fz_end')                    # thawed: back to standing (as r_drag's daze end)
    a.w(0x206B, 0x0088)                  # movea.l $88(a3),a0
    a.w(0x2050)                          # movea.l (a0),a0
    a.w(0x216A, 0x0008, 0x0004)          # move.l 8(a2),4(a0)
    a.w(0x4268, 0x0008)                  # clr.w 8(a0)
    a.w(0x426B, 0x00BE)                  # clr.w $BE(a3)
    a.w(0x08AB, 0x0003, 0x0101)          # bclr #3,$101(a3)
    a.w(0x08AB, 0x0007, 0x011A)          # bclr #7,$11A(a3)
    a.w(0x08AB, 0x0005, 0x00F7)          # bclr #5,$F7(a3)
    a.w(0x0269, 0xBEF9, 0x011A)          # andi.w #$BEF9,$11A(a1)
    a.w(0x302A, 0x000C)                  # move.w 12(a2),d0
    for o in POS_X_ALL:
        a.w(0x3740, o)                   # move.w d0,o(a3)
    a.label('fz_col')                    # his colours back
    a.w(0x4252)                          # clr.w (a2)
    a.bccw(0x61, 'fz_line')
    a.w(0x5488)                          # addq.l #2,a0
    a.w(0x49EA, 0x0010)                  # lea 16(a2),a4
    a.w(0x760E)                          # moveq #14,d3
    a.label('fz_rl')
    a.w(0x30DC)                          # move.w (a4)+,(a0)+
    a.dbra(3, 'fz_rl')
    a.w(0x3D7C, 0xFFFF, PAL_DIRTY & 0xFFFF)
    a.bccw(0x60, 'fz_x')
    a.label('fz_line')                   # a0 = his palette line in EC's copy (a3 = him)
    a.w(0x302B, 0x007A)                  # move.w $7A(a3),d0
    a.w(0x0240, 0x0003)                  # andi.w #3,d0
    a.w(0x0A40, 0x0001)                  # eori.w #1,d0         (a fighter's line: ($7A & 3) ^ 1)
    a.w(0xEB48)                          # lsl.w #5,d0
    a.w(0x41EE, PAL_BUF & 0xFFFF)        # lea buf(a6),a0
    a.w(0xD0C0)                          # adda.w d0,a0
    a.w(0x4E75)
    a.label('fz_park')                   # his move task while frozen (a5 = him)
    a.w(0x3B7C, DIZZY, 0x00BE)           # move.w #$1F,$BE(a5)
    a.label('fz_pl')
    a.w(0x7001)                          # moveq #1,d0
    a.jsr(0x68D6)                        # sleep a frame
    a.bcc(0x60, 'fz_pl')
    a.label('fz_tab')
    for v in _freeze_tint():
        a.w(v)
    a.label('fz_v')
    a.out += bytes(16 + 30 + 2)          # (+46: his pose)
    a.label('fz_x')


POS_X_ALL = (0x36, 0x3A, 0x4E, 0x56, 0xB2, 0xBA)   # a fighter's x, every copy


# MK projectiles (tools/lib/mkprojectile.py: the art in his effect sheet $45):
# an object spawned as Blade's (type $1F40, his descriptor with our sheet),
# registered as his projectile ($6A38: EC's own projectile hit check and
# reaction), flown at MK's speed (measured ~6 px/frame) from his cast's
# release frame (42:2E, Blade's projectile strike frame)
PJ_TYPE = 0x1F40              # Blade's own projectile object type
PJ_DESC = 0x3B26              # BLA.CO: his descriptor for it (word 0 = sheet)
PJ_RELEASE = 0x422E
PJ_SPEED, PJ_LIFE, PJ_AHEAD, PJ_UP = 6, 35, 70, 75   # px/frame, task runs (every other frame), px in front, px above his feet
PJ_FIGHTERS = {19: 'raiden', 18: 'johnny', 20: 'subzero', 12: 'liukang', 13: 'kano', 17: 'sonya', 26: 'reptile'}
# $78: damage byte, hit level byte (EC's table at PLYR $1A2CC; Blade's and
# Xavier's projectiles use level 2, damage 0). MK: the bolts take ~10% of the
# bar (10 of EC's 104); the ice ball does no damage, it freezes (emit_freeze)
PJ_DAMAGE = {'raiden': 10, 'johnny': 10, 'subzero': 0, 'liukang': 10, 'kano': 10, 'sonya': 10, 'reptile': 0}
PJ_LEVEL = 2
PJ_REACT = {'raiden': HIT_FIRST, 'johnny': HIT_FIRST, 'subzero': 0, 'liukang': HIT_FIRST, 'kano': HIT_FIRST, 'sonya': HIT_FIRST, 'reptile': 0}   # $A4: MK's frozen victim has no hit reaction


def emit_proj(a, key):
    """In r_generic (a1 = him): when his cast ($34) shows its release frame,
    his MK projectile flies. Its hit (EC's) sets pj_v+2 (emit_freeze)."""
    import mkprojectile
    from inputs import ROOT
    nfl = len(mkprojectile.PROJ[key][1])
    co = open(os.path.join(ROOT, 'extracted', 'ec_us', 'BLA.CO'), 'rb').read()
    desc = bytearray(co[PJ_DESC:PJ_DESC + 34])
    assert desc[0:2] == b'\x00\x44', desc.hex()
    desc[0:4] = bytes((0, fx_sheet(), 0, 0))
    a.pcrel(0x45FA, 'pj_v')              # lea vars(pc),a2     +0 fired this cast, +2 hit
    a.w(0x3029, 0x00BE)                  # move.w $BE(a1),d0
    a.w(0x0240, 0x7FFF)
    ice = SCORPION_ID == REPTILE_ID      # (Reptile: the ice blast is ICE_MOVE; $34 his spear)
    a.w(0x0C40, ICE_MOVE if ice else 0x0034)   # cmpi.w #$34,d0      his cast
    a.bcc(0x67, 'pj_in')
    a.w(0x4252)                          # clr.w (a2)
    a.bccw(0x60, 'pj_x')
    a.label('pj_in')
    a.w(0x4A52)                          # tst.w (a2)
    a.bccw(0x66, 'pj_x')
    a.w(0x0C69, fr(ice_plan(MK_DIR_OF[REPTILE_ID])[2] if ice else PJ_RELEASE), 0x001A)  # cmpi.w #release,$1A(a1)
    a.bccw(0x66, 'pj_x')
    a.w(0x34BC, 0x0001)                  # move.w #1,(a2)
    a.w(0x48E7, 0xFFFE)                  # movem.l d0-d7/a0-a6,-(sp)
    a.w(0x2A49)                          # movea.l a1,a5        (the spawn takes its owner in a5)
    a.pcrel(0x43FA, 'pj_desc')           # lea desc(pc),a1
    a.w(0x303C, PJ_TYPE)                 # move.w #type,d0
    a.w(0x7600)                          # moveq #0,d3
    a.jsr(0x6BBA)
    a.bccw(0x65, 'pj_none')              # bcs: no object free
    a.pcrel(0x43FA, 'pj_task')           # lea task(pc),a1
    a.w(0x2468, 0x0088)                  # movea.l $88(a0),a2
    a.w(0x2549, 0x0004)                  # move.l a1,4(a2)
    a.pcrel(0x43FA, 'pj_hit')            # lea hit(pc),a1
    a.w(0x2149, 0x0084)                  # move.l a1,$84(a0)
    a.w(0x317C, fx_sheet() << 8, 0x001A)   # move.w #sheet:00,$1A(a0)
    a.w(0x323C, PJ_AHEAD)                # move.w #ahead,d1
    a.w(0x343C, 2 * PJ_SPEED)            # move.w #2*speed,d2   (its task runs every other frame)
    a.w(0x082D, 0x0003, 0x0020)          # btst #3,$20(a5)      facing left?
    a.bcc(0x67, 'pj_rt')
    a.w(0x4441)                          # neg.w d1
    a.w(0x4442)                          # neg.w d2
    a.label('pj_rt')
    a.pcrel(0x47FA, 'pj_v')              # lea vars(pc),a3
    a.w(0x3742, 0x0006)                  # move.w d2,6(a3)      its step
    a.w(0x302D, 0x004E)                  # move.w $4E(a5),d0
    a.w(0xD041)                          # add.w d1,d0
    a.w(0x3140, 0x004E)                  # move.w d0,$4E(a0)
    a.w(0x302D, 0x0052)                  # move.w $52(a5),d0
    a.w(0x0440, PJ_UP)                   # subi.w #up,d0
    a.w(0x3140, 0x0052)                  # move.w d0,$52(a0)
    a.label('pj_none')
    a.w(0x4CDF, 0x7FFF)                  # movem.l (sp)+,d0-d7/a0-a6
    a.bccw(0x60, 'pj_x')
    # its task (a5 = it)
    a.label('pj_task')
    a.jsr(0x6A38)                        # his projectile now (a0 = him)
    a.w(0x2B48, 0x0090)                  # move.l a0,$90(a5)
    a.w(0x3B7C, PJ_DAMAGE[key] << 8 | PJ_LEVEL, 0x0078)   # move.w #dmg:level,$78(a5)
    a.w(0x3B7C, PJ_REACT[key], 0x00A4)   # move.w #reaction,$A4(a5)
    a.pcrel(0x41FA, 'pj_v')              # lea vars(pc),a0      (EC applies no speed to it: moved here)
    a.w(0x317C, PJ_LIFE, 0x0004)         # move.w #life,4(a0)   (EC's object fields stay EC's)
    a.label('pj_l')
    a.pcrel(0x41FA, 'pj_v')              # lea vars(pc),a0
    a.w(0x3028, 0x0006)                  # move.w 6(a0),d0
    a.w(0xD16D, 0x004E)                  # add.w d0,$4E(a5)
    if nfl > 1:
        a.w(0x3028, 0x0004)              # move.w 4(a0),d0
        a.w(0xE448)                      # lsr.w #2,d0          a frame every 4
        a.w(0x0240, 0x0001)              # andi.w #1,d0
        a.w(0x1B40, 0x001B)              # move.b d0,$1B(a5)
    a.w(0x5368, 0x0004)                  # subq.w #1,4(a0)
    a.bcc(0x67, 'pj_gone')
    a.jsr(0x68D0)                        # yield
    a.bcc(0x60, 'pj_l')
    a.label('pj_gone')
    a.w(0x08ED, 0x0002, 0x0082)          # bset #2,$82(a5)      gone
    a.w(0x206D, 0x0090)                  # movea.l $90(a5),a0
    a.w(0x42A8, 0x0122)                  # clr.l $122(a0)       he may throw again
    a.jmp(0x6A1A)
    # EC's hit callback (a5 = it): it hit
    a.label('pj_hit')
    a.pcrel(0x41FA, 'pj_v')              # lea vars(pc),a0
    a.w(0x317C, 0x0001, 0x0002)          # move.w #1,2(a0)      (Sub-Zero's freeze)
    a.w(0x08ED, 0x0002, 0x0082)          # bset #2,$82(a5)
    a.w(0x206D, 0x0090)                  # movea.l $90(a5),a0
    a.w(0x42A8, 0x0122)                  # clr.l $122(a0)
    a.w(0x4E75)
    a.label('pj_desc')
    a.out += bytes(desc)
    a.label('pj_v')
    a.w(0); a.w(0); a.w(0); a.w(0)       # +0 fired this cast, +2 it hit, +4 runs left, +6 its step
    a.label('pj_x')


# Shang Tsung's skull volley (MK: tools/lib/mkshangref.py). His cast (move $34) is his
# own script: 7, 8, 9, 10 at MK's timing, then 11 (arm out, on Blade's release frame
# 42:2E) held while three skulls go, ~40 frames apart. Each skull is an object at his
# feet showing MK's frames from there (mkprojectile 'shang': 13, 16 growing in his
# hand, 17 flying, 56, 57 its burst where it hits). Times in calls (every other frame).
SKULL_STEPS = [(0x4060, 1, 7), (0x4061, 1, 8), (0x4062, 3, 9), (0x4063, 2, 10), (0x422E, 65, 11)]   # (frame, ticks, EMP)
SKULL_HEAD = 0x4D74           # BLA.CO: Blade's move $34 script (41 steps)
SKULL_AT = (5, 25, 45)        # calls after 11 first shows: each skull appears (MK: 10, 51, 91 frames)
SKULL_FORM = (4, 9)           # its calls on 13, then on 16 (MK: 12-16 over ~17 frames), then it flies
SKULL_FLY = 28                # calls of flight at most (off the screen)
SKULL_STEP = 13               # px a call (MK: ~6.5 px a frame)
SKULL_BURST = (1, 5)          # calls on 56, then on 57
SKULL_DX, SKULL_DY = 0, 0     # its origin from his ($4E, $52): MK's frames are placed from his feet
SKULL_DAMAGE = 10
SKULL_LEVEL = 7               # EC's hit level (PLYR $1A2CC): the victim staggers ~26 frames, as MK's
                              # (Blade's level 2: ~40-70, so the next skull, 40 frames on, knocked down)


# walk back / forward: (BLA.CO script, his held pose, the side in glide.json)
GLIDE_MOVES = {0xA: (0x3FE4, 0x4065, 'back'), 0xB: (0x4040, 0x4064, 'fwd')}
# The header's x speed (16.16, 2 units a px a frame). MK's world x ($7BE26 in its
# PRG-RAM) moves 1.875 px a frame toward (2,2,2,2,2,2,2,1) and ~3.4 away (frame 6,
# 41 px in 12 frames). EC halves a walk's speed against the way he faces
# (PLYR $18126): away is 2 x 3.375.
GLIDE_SPEED = {0xA: 0xD8000, 0xB: 0x3C000}
GLIDE_HOLD = 0x1000           # ticks on the held pose (~2 min: the walk ends when he lets go)
# Step flag $0020 (EC: "may block"): a fighter on such a step holding away from an
# attack within 192 px is put into his block (PLYR $19960), which stopped Shang's
# glide away from a jump-in and let the kick reach him. MK blocks with a button,
# not by walking away: his held away pose goes without it. (The first step keeps
# it: EC reads the walk's direction from it, $18126. Without it on that step he
# can't be thrown, and the CPU's block choice, $1972C, isn't asked.)
GLIDE_NO_BLOCK = 0x0020


def glide_frames(mk_dir):
    """walk_fwd/glide.json with frames for the start poses: {'fwd', 'back': pose,
    'fwd_start', 'back_start': [(frame, pose, MK's game frames)]} - 40:66 on; or None."""
    from inputs import ROOT
    import json
    path = os.path.join(ROOT, 'extracted', mk_dir, 'walk_fwd', 'glide.json')
    if not os.path.exists(path):
        return None
    g = json.load(open(path))
    fr = iter(range(0x4066, 0x406D))
    for side in ('fwd_start', 'back_start'):
        g[side] = [(next(fr), k, n) for k, n in g[side]]
    return g


def glide_scripts(mk_dir):
    """Shang's walks (moves $A back, $B forward), as MK's glide: the poses he
    steps into it with (walk_plan's 40:66..) at MK's timing, then his held glide
    pose (40:65 away, 40:64 toward) for one long step, at MK's speeds. Blade's
    walk scripts give the rest of the header and step words. One long step and
    no loop: EC restarts a walk from its first step whenever its last one ends
    (PLYR $182F4), which would show the start poses again every cycle. The held
    away pose isn't a block (GLIDE_NO_BLOCK)."""
    from inputs import ROOT
    co = open(os.path.join(ROOT, 'extracted', 'ec_us', 'BLA.CO'), 'rb').read()
    W = lambda o: int.from_bytes(co[o:o + 2], 'big')
    g = glide_frames(mk_dir)
    out = {}
    for mid, (head, frame, side) in GLIDE_MOVES.items():
        assert W(head) == 4 * mid, hex(W(head))
        n = W(head + 2) + 1
        step = co[head + 20:head + 32]
        assert 0x4016 <= W(head + 20) <= 0x401B and W(head + 28) == 0x0420
        term = co[head + 20 + 12 * n:head + 32 + 12 * n]
        assert W(head + 20 + 12 * n) < 0x100
        steps = [(f, max(1, round(k / 2))) for f, _, k in g[side + '_start']] + [(frame, GLIDE_HOLD)]
        hdr = bytearray(co[head:head + 20])
        hdr[2:4] = (len(steps) - 1).to_bytes(2, 'big')
        hdr[4:8] = GLIDE_SPEED[mid].to_bytes(4, 'big')
        body = b''
        for f, t in steps:
            flags = W(head + 28)
            if side == 'back' and t == GLIDE_HOLD:
                flags &= ~GLIDE_NO_BLOCK
            body += struct.pack('>HHHHH', f, t, 0, 0, flags) + step[10:]
        out[mid] = bytes(hdr) + body + term
    return out


def skull_plan(mk_dir):
    """(move $34 script in Blade's numbering, art pins: his cast poses on its frames)."""
    from inputs import ROOT
    co = open(os.path.join(ROOT, 'extracted', 'ec_us', 'BLA.CO'), 'rb').read()
    W = lambda o: int.from_bytes(co[o:o + 2], 'big')
    n = W(SKULL_HEAD + 2) + 1
    term = bytes(co[SKULL_HEAD + 20 + 12 * n:SKULL_HEAD + 32 + 12 * n])
    assert W(SKULL_HEAD + 20 + 12 * n) < 0x100 and W(SKULL_HEAD + 20 + 12 * (n - 1)) >= 0x100
    hdr = bytearray(co[SKULL_HEAD:SKULL_HEAD + 20])
    hdr[2:4] = (len(SKULL_STEPS) - 1).to_bytes(2, 'big')
    steps = b''.join(struct.pack('>HHHHHH', f, t, 0, 0, 0x0002, 0) for f, t, _ in SKULL_STEPS)
    import json
    emp = json.load(open(os.path.join(ROOT, 'extracted', mk_dir, 'skull', 'emp.json')))
    pins = [f'{f >> 8:02x}:{f & 0xFF:02x}={emp.index(k)}' for f, _, k in SKULL_STEPS]
    return bytes(hdr) + steps + term, pins


def _lea_mod(a, reg, off):
    """lea off(pc),An for an offset in this module (the block sits at EXT_OFF)."""
    disp = off - (EXT_OFF + len(a.out) + 2)
    assert -0x8000 <= disp < 0x8000
    a.w(0x41FA | (reg << 9), disp & 0xFFFF)


def emit_morph(a):
    """At the top of Shang's r_drag (a1 = him; every other frame): his morph
    into his opponent. Vars at MORPH_MV: +0 phase (0 Shang, 1 blending in,
    2 morphed - only in the saved copy's vars -, 3 blending out), +1 a volley
    seen (phase 0) / calls standing still (phase 2), +2 calls in this phase,
    +4 his first blend frame, +6 cooldown, +8 the saved copy (his .PL's
    tail), +12 (saved copy's) the morphed copy's own drag routine.
    Phase 0: after a volley, standing, no skull out, both fighters at
    MORPH_LOW or more and an MK opponent: blend in. Phases 1 and 3 show his
    three blends (MORPH_HOLD calls each), holding his stance step; r_ai keeps
    the CPU still. A hit ends phase 1. At its end (mo_swap, at the top of the
    hook: nothing of this module is returned to) the module is saved and the
    swap goes on in the saved copy (mo_sw2)."""
    _lea_mod(a, 2, MORPH_MV)              # lea mv(pc),a2
    a.w(0x3029, 0x00BE)                   # move.w $BE(a1),d0
    a.w(0x0240, 0x7FFF)                   # andi.w #$7FFF,d0
    a.w(0x1212)                           # move.b (a2),d1      phase
    a.bccw(0x66, 'mo_ph')
    a.w(0x0C40, 0x0034)                   # cmpi.w #$34,d0      his volley
    a.bcc(0x66, 'mo_nv')
    a.w(0x50EA, 0x0001)                   # st 1(a2)
    a.label('mo_nv')
    a.w(0x4A6A, 0x0006)                   # tst.w 6(a2)         cooldown
    a.bcc(0x67, 'mo_c0')
    a.w(0x536A, 0x0006)                   # subq.w #1,6(a2)
    a.bccw(0x60, 'mo_cont')
    a.label('mo_c0')
    a.w(0x4A2A, 0x0001)                   # tst.b 1(a2)         a volley since the last?
    a.bccw(0x67, 'mo_cont')
    a.w(0x4A40)                           # tst.w d0            standing
    a.bccw(0x66, 'mo_cont')
    a.w(0x4AA9, 0x0122)                   # tst.l $122(a1)      no skull flying
    a.bccw(0x66, 'mo_cont')
    a.pcrel(0x41FA, 'sk_s')               # lea slots(pc),a0    none forming or bursting
    a.w(0x7200 | (len(SKULL_AT) - 1))     # moveq #2,d1
    a.label('mo_sl')
    a.w(0x4A90)                           # tst.l (a0)
    a.bccw(0x66, 'mo_cont')
    a.w(0x41E8, 12)                       # lea 12(a0),a0
    a.dbra(1, 'mo_sl')
    a.w(0x0C69, MORPH_LOW, 0x0076)        # cmpi.w #low,$76(a1)
    a.bccw(0x6D, 'mo_cont')               # blt
    a.w(0x2669, 0x008C)                   # movea.l $8C(a1),a3  his opponent
    a.w(0x0C6B, MORPH_LOW, 0x0076)        # cmpi.w #low,$76(a3)
    a.bccw(0x6D, 'mo_cont')
    a.w(0x322B, 0x004C)                   # move.w $4C(a3),d1
    a.pcrel(0x41FA, 'mo_tab')             # lea table(pc),a0
    a.label('mo_tl')
    a.w(0x3418)                           # move.w (a0)+,d2
    a.bccw(0x6B, 'mo_cont')               # bmi: not an MK fighter
    a.w(0x3618)                           # move.w (a0)+,d3
    a.w(0xB441)                           # cmp.w d1,d2
    a.bcc(0x66, 'mo_tl')
    a.w(0x3543, 0x0004)                   # move.w d3,4(a2)     his first blend
    a.w(0x14BC, 0x0001)                   # move.b #1,(a2)      blending in
    a.w(0x426A, 0x0002)                   # clr.w 2(a2)
    a.w(0x422A, 0x0001)                   # clr.b 1(a2)
    a.bccw(0x60, 'mo_cont')
    a.label('mo_ph')
    a.w(0x5301)                           # subq.b #1,d1
    a.bcc(0x67, 'mo_in')
    a.w(0x5501)                           # subq.b #2,d1
    a.bcc(0x67, 'mo_out')
    a.w(0x4212)                           # clr.b (a2)          (2: only in the saved copy)
    a.bccw(0x60, 'mo_cont')
    a.label('mo_in')
    a.w(0x4A40)                           # tst.w d0            still standing?
    a.bcc(0x67, 'mo_in1')
    a.w(0x4212)                           # clr.b (a2)          hit out of it
    a.w(0x357C, MORPH_COOL_ABORT, 0x0006) # move.w #cool,6(a2)
    a.bccw(0x60, 'mo_cont')
    a.label('mo_in1')
    a.w(0x526A, 0x0002)                   # addq.w #1,2(a2)
    a.w(0x302A, 0x0002)                   # move.w 2(a2),d0
    a.w(0x0C40, 3 * MORPH_HOLD)           # cmpi.w #3*hold,d0
    a.bcc(0x63, 'mo_sh1')                 # bls: a blend
    a.w(0x0C40, 3 * MORPH_HOLD + 1)
    a.bccw(0x62, 'mo_swap')               # bhi: blank on screen now - swap
    a.w(0x337C, fr(MORPH_BLANK), 0x001A)  # move.w #blank,$1A(a1)   (blank a call before his colours change)
    a.bccw(0x61, 'mo_hold')
    a.w(0x4E75)
    a.label('mo_sh1')
    a.bccw(0x61, 'mo_show')
    a.w(0x4E75)                           # rts
    a.label('mo_out')
    a.w(0x526A, 0x0002)                   # addq.w #1,2(a2)
    a.w(0x302A, 0x0002)                   # move.w 2(a2),d0
    a.w(0x0C40, 3 * MORPH_HOLD)
    a.bcc(0x62, 'mo_od')                  # bhi: done
    a.w(0x4440)                           # neg.w d0
    a.w(0x0640, 3 * MORPH_HOLD + 1)       # addi.w #3*hold+1,d0  (backwards)
    a.bccw(0x61, 'mo_show')
    a.w(0x4E75)
    a.label('mo_od')
    a.w(0x4212)                           # clr.b (a2)          Shang again
    a.w(0x357C, MORPH_COOL, 0x0006)       # move.w #cool,6(a2)
    a.bccw(0x60, 'mo_cont')
    a.label('mo_swap')
    a.bccw(0x61, 'mo_slots')              # a3 his slot, a4 the other
    a.bccw(0x61, 'mo_idx')                # d7 his step in his script
    a.bccw(0x61, 'mo_pl')                 # a0 = his .PL's tail
    a.w(0x2548, 0x0008)                   # move.l a0,8(a2)     (before the copy: it keeps it)
    a.w(0x2A4B)                           # movea.l a3,a5
    a.w(0x323C, MORPH_SIZE // 4 - 1)      # move.w #n,d1
    a.label('mo_c1')
    a.w(0x20DD)                           # move.l (a5)+,(a0)+  his module saved
    a.dbra(1, 'mo_c1')
    a.w(0x206A, 0x0008)                   # movea.l 8(a2),a0
    a.w(0xD0FC, EXT_OFF)                  # adda.w #EXT_OFF,a0
    a.w(0xD0FC); a.wdiff('mo_sw2', 'base')   # adda.w #mo_sw2,a0
    a.w(0x4ED0)                           # jmp (a0)            on in the saved copy
    a.label('mo_cont')


def emit_morph_subs(a):
    """emit_morph's swap (mo_sw2, in the saved copy), the morphed copy's drag
    hook (mo_m, by the trampoline at MORPH_TRAMP) and its way back, helpers."""
    drag_at = EXT_OFF + RAW + 4 * ENTRIES.index('drag')
    # --- mo_sw2: in the saved copy. a3 his slot, a4 the other, d7 his step
    a.label('mo_sw2')
    _lea_mod(a, 2, MORPH_MV)              # lea mv(pc),a2       the saved copy's vars
    a.w(0x14BC, 0x0002)                   # move.b #2,(a2)      morphed
    a.w(0x426A, 0x0002)                   # clr.w 2(a2)
    a.w(0x422A, 0x0001)                   # clr.b 1(a2)
    a.w(0x204C)                           # movea.l a4,a0       the opponent's module ...
    a.w(0x2A4B)                           # movea.l a3,a5       ... into his slot (as a mirror match has it)
    a.w(0x323C, MORPH_SIZE // 4 - 1)
    a.label('mo_c2')
    a.w(0x2AD8)                           # move.l (a0)+,(a5)+
    a.dbra(1, 'mo_c2')
    a.w(0x41EB, drag_at)                  # lea drag(a3),a0     the copy's drag entry (bra.w)
    a.w(0x0C50, 0x6000)                   # cmpi.w #$6000,(a0)
    a.bcc(0x66, 'mo_nt')
    a.w(0x3028, 0x0002)                   # move.w 2(a0),d0
    a.w(0x48C0)                           # ext.l d0
    a.w(0x4BF0, 0x0802)                   # lea 2(a0,d0.l),a5   its routine
    a.w(0x254D, 0x000C)                   # move.l a5,12(a2)
    a.w(0x317C, (MORPH_TRAMP - (drag_at + 2)) & 0xFFFF, 0x0002)   # bra.w the trampoline
    a.w(0x41EB, MORPH_TRAMP)              # lea tramp(a3),a0
    a.w(0x30FC, 0x4EF9)                   # move.w #jmp.l,(a0)+
    a.w(0x2A6A, 0x0008)                   # movea.l 8(a2),a5
    a.w(0xDAFC, EXT_OFF)                  # adda.w #EXT_OFF,a5
    a.w(0xDAFC); a.wdiff('mo_m', 'base')  # adda.w #mo_m,a5
    a.w(0x208D)                           # move.l a5,(a0)
    # a full block (Scorpion's) twice is a mirror match: the dispatcher skips the
    # second (its routines act on both fighters from the first). Generic, the copy
    # is called for him alone - and goes on to nothing: player 1's did his part
    a.w(0x4A6B, EXT_OFF + 6)              # tst.w full(a3)
    a.bcc(0x67, 'mo_nt')
    a.w(0x426B, EXT_OFF + 6)              # clr.w full(a3)
    a.w(0x42AA, 0x000C)                   # clr.l 12(a2)
    a.label('mo_nt')
    a.w(0x2A69, 0x008C)                   # movea.l $8C(a1),a5
    a.w(0x336D, 0x004C, 0x004C)           # move.w $4C(a5),$4C(a1)   he is his opponent's fighter
    a.bccw(0x61, 'mo_fit')
    a.w(0x337C, fr(MORPH_BLANK), 0x001A)  # move.w #blank,$1A(a1)
    a.w(0x377C, MORPH_HOLD_MARK, MORPH_MV)   # move.w #mark,mv(a3)   the CPU gives him no input
    a.bccw(0x61, 'mo_hold')
    a.w(0x4E75)                           # rts (to the hook's caller)
    # --- mo_m: the morphed copy's drag entry (trampoline), in the saved copy
    a.label('mo_m')
    a.w(0x598F)                           # subq.l #4,sp        (the routine to go on to)
    a.w(0x48E7, 0xFFFE)                   # movem.l d0-d7/a0-a6,-(sp)
    _lea_mod(a, 2, MORPH_MV)              # lea mv(pc),a2
    a.w(0x526A, 0x0002)                   # addq.w #1,2(a2)
    a.w(0x0C6A, 0x0001, 0x0002)           # cmpi.w #1,2(a2)     his first call morphed:
    a.bcc(0x66, 'mo_f1')
    a.bccw(0x61, 'mo_slots')
    a.w(0x426B, MORPH_MV)                 # clr.w mv(a3)        input again
    a.w(0x2069, 0x00AE)                   # movea.l $AE(a1),a0  his step's frame (his colours are on now)
    a.w(0x3010)                           # move.w (a0),d0
    a.w(0x0C40, 0x0100)
    a.bcc(0x65, 'mo_f1')
    a.w(0x3340, 0x001A)                   # move.w d0,$1A(a1)
    a.label('mo_f1')
    a.w(0x2669, 0x008C)                   # movea.l $8C(a1),a3
    a.w(0x4A69, 0x0076)                   # tst.w $76(a1)
    a.bccw(0x6F, 'mo_ko')                 # ble: knocked out
    a.w(0x4A6B, 0x0076)                   # tst.w $76(a3)
    a.bccw(0x6F, 'mo_ko')
    a.w(0x0C6A, MORPH_DUR, 0x0002)        # cmpi.w #dur,2(a2)
    a.bcc(0x65, 'mo_st')                  # bcs: not yet
    a.w(0x3029, 0x00BE)
    a.w(0x0240, 0x7FFF)
    a.bcc(0x66, 'mo_nc')                  # busy
    a.w(0x4AA9, 0x0122)                   # tst.l $122(a1)      his projectile out
    a.bcc(0x66, 'mo_nc')
    a.w(0x522A, 0x0001)                   # addq.b #1,1(a2)
    a.w(0x0C2A, MORPH_CALM, 0x0001)       # cmpi.b #calm,1(a2)
    a.bcc(0x65, 'mo_st')
    a.bcc(0x62, 'mo_b3')                  # bhi: blank on screen now - back
    a.w(0x337C, fr(MORPH_BLANK), 0x001A)  # move.w #blank,$1A(a1)   (a call before his colours change)
    a.bccw(0x61, 'mo_hold')
    a.bccw(0x61, 'mo_slots')
    a.w(0x377C, MORPH_HOLD_MARK, MORPH_MV)   # move.w #mark,mv(a3)   no input: no move over the blank
    a.bccw(0x60, 'mo_bx')                 # (not the copy's own routine this call)
    a.label('mo_b3')
    a.w(0x7C03)                           # moveq #3,d6         back, blending out
    a.bcc(0x60, 'mo_bk')
    a.label('mo_nc')
    a.w(0x422A, 0x0001)                   # clr.b 1(a2)
    a.bccw(0x61, 'mo_slots')
    a.w(0x426B, MORPH_MV)                 # clr.w mv(a3)        (a blank he was hit out of: input again)
    a.label('mo_st')
    a.w(0x202A, 0x000C)                   # move.l 12(a2),d0
    a.bcc(0x67, 'mo_bx')                  # none (a full block's copy)
    a.w(0x2F40, 0x003C)                   # move.l d0,60(sp)
    a.w(0x4CDF, 0x7FFF)                   # movem.l (sp)+,d0-d7/a0-a6
    a.w(0x4E75)                           # rts: on to the copy's own routine
    a.label('mo_ko')
    a.w(0x7C00)                           # moveq #0,d6         a knockout: Shang at once
    a.label('mo_bk')
    a.bccw(0x61, 'mo_slots')
    a.bccw(0x61, 'mo_idx')
    _lea_mod(a, 0, 0)                     # lea module(pc),a0   (the saved copy)
    a.w(0x2A4B)                           # movea.l a3,a5
    a.w(0x323C, MORPH_SIZE // 4 - 1)
    a.label('mo_c3')
    a.w(0x2AD8)                           # move.l (a0)+,(a5)+
    a.dbra(1, 'mo_c3')
    a.w(0x337C, SHANG_ID, 0x004C)         # move.w #id,$4C(a1)
    a.bccw(0x61, 'mo_fit')
    a.w(0x41EB, MORPH_MV)                 # lea mv(a3),a0       the restored module's vars
    a.w(0x1086)                           # move.b d6,(a0)
    a.w(0x4268, 0x0002)                   # clr.w 2(a0)
    a.w(0x4228, 0x0001)                   # clr.b 1(a0)
    a.w(0x317C, MORPH_COOL, 0x0006)       # move.w #cool,6(a0)
    a.w(0x4A06)                           # tst.b d6
    a.bcc(0x67, 'mo_bx')
    a.w(0x337C, fr(MORPH_BLANK), 0x001A)  # move.w #blank,$1A(a1)   (his blends from his next call)
    a.bccw(0x61, 'mo_hold')               # (his stance step held: not shown under it)
    a.label('mo_bx')
    a.w(0x4CDF, 0x7FFF)
    a.w(0x588F)                           # addq.l #4,sp
    a.w(0x4E75)
    # --- mo_show: d0 = 1..3*hold: his blend (d0 - 1) / hold; mo_hold: his step held
    a.label('mo_show')
    a.w(0x5340)                           # subq.w #1,d0
    a.w(0x48C0)                           # ext.l d0
    a.w(0x80FC, MORPH_HOLD)               # divu.w #hold,d0
    a.w(0xD06A, 0x0004)                   # add.w 4(a2),d0
    a.w(0x3340, 0x001A)                   # move.w d0,$1A(a1)
    a.label('mo_hold')
    a.w(0x2069, 0x0088)                   # movea.l $88(a1),a0  move task
    a.w(0x2050)                           # movea.l (a0),a0     its TCB
    a.w(0x317C, 0x0004, 0x0026)           # move.w #4,$26(a0)   his step's ticks: held
    a.w(0x4E75)
    # --- mo_slots: a3 = his module slot, a4 = the other
    a.label('mo_slots')
    a.w(0x47F9); a.l(SLOTS[1])            # lea slot2,a3
    a.w(0x49F9); a.l(SLOTS[0])            # lea slot1,a4
    a.w(0xB3FC); a.l(P2_AT)               # cmpa.l #P2,a1
    a.bcc(0x67, 'mo_sl2')
    a.w(0xC74C)                           # exg a3,a4
    a.label('mo_sl2')
    a.w(0x4E75)
    # --- mo_idx: d7 = his step in his current script ($AE - $AA) / 12, -1 if not in his module
    a.label('mo_idx')
    a.w(0x7EFF)                           # moveq #-1,d7
    a.w(0x2029, 0x00AA)                   # move.l $AA(a1),d0
    a.w(0x908B)                           # sub.l a3,d0
    a.bcc(0x65, 'mo_ix')                  # bcs
    a.w(0x0C80); a.l(MORPH_SIZE)          # cmpi.l #size,d0
    a.bcc(0x64, 'mo_ix')                  # bcc
    a.w(0x2029, 0x00AE)                   # move.l $AE(a1),d0
    a.w(0x90A9, 0x00AA)                   # sub.l $AA(a1),d0
    a.bcc(0x6B, 'mo_ix')                  # bmi
    a.w(0x80FC, 12)                       # divu.w #12,d0
    a.w(0x7E00)                           # moveq #0,d7
    a.w(0x3E00)                           # move.w d0,d7
    a.label('mo_ix')
    a.w(0x4E75)
    # --- mo_fit: the module in his slot is now his: EC's own set-up (PLYR $190C6):
    #     colours ($12BBC: the alternate set when both are one fighter; into the
    #     palette buffer, sent to the screen at once below), move table ($1A278,
    #     cleared first); then the same move's script in it, the same step (d7)
    a.label('mo_fit')
    a.w(0x48E7, 0xFFFE)                   # movem.l d0-d7/a0-a6,-(sp)
    a.w(0x2C7C); a.l(0x30000)             # movea.l #$30000,a6
    a.w(0x2A49)                           # movea.l a1,a5
    a.w(0x266D, 0x00A6)                   # movea.l $A6(a5),a3
    a.w(0x7200 | 62)                      # moveq #62,d1
    a.label('mo_tc')
    a.w(0x429B)                           # clr.l (a3)+
    a.dbra(1, 'mo_tc')
    a.w(0x206D, 0x011E)                   # movea.l $11E(a5),a0
    a.jsr(0x12BBC)
    a.w(0x266D, 0x00A6)                   # movea.l $A6(a5),a3
    a.w(0x206D, 0x011E)                   # movea.l $11E(a5),a0
    a.jsr(0x1A278)
    # his colours to the screen at once: EC's palette tasks ($D09A) take the target
    # (-$6956(a6)) to the output (-$69D6, sent to CRAM) through a fade by levels
    # (-$68D6, per colour) - over ~20 frames from a $702E. His line (P2 $20-$2F,
    # P1 $30-$3F, as $12BBC wrote them at $1502(a6)) into target and output, its
    # levels 0, and the whole-palette send (-$67D4) raised
    a.w(0x7040)                           # moveq #$40,d0       player 2's line ...
    a.w(0x082D, 0x0000, 0x007B)           # btst #0,$7B(a5)
    a.bcc(0x66, 'mo_p2')
    a.w(0x7060)                           # moveq #$60,d0       ... or player 1's
    a.label('mo_p2')
    a.w(0x41EE, 0x1502)                   # lea $1502(a6),a0
    a.w(0xD0C0)                           # adda.w d0,a0
    a.w(0x45EE, 0x96AA)                   # lea -$6956(a6),a2
    a.w(0xD4C0)
    a.w(0x47EE, 0x962A)                   # lea -$69D6(a6),a3
    a.w(0xD6C0)
    a.w(0x49EE, 0x972A)                   # lea -$68D6(a6),a4
    a.w(0xD8C0)
    a.w(0x720F)                           # moveq #15,d1
    a.label('mo_pc')
    a.w(0x34D0)                           # move.w (a0),(a2)+
    a.w(0x36D8)                           # move.w (a0)+,(a3)+
    a.w(0x425C)                           # clr.w (a4)+
    a.dbra(1, 'mo_pc')
    a.w(0x3D7C, 0xFFFF, 0x982C)           # move.w #-1,-$67D4(a6)
    a.w(0x3D7C, 0xFFFF, 0x982E)           # move.w #-1,-$67D2(a6)  the output sent this frame (with his new art)
    a.w(0x4CDF, 0x7FFF)                   # movem.l (sp)+,d0-d7/a0-a6
    a.w(0x4A87)                           # tst.l d7
    a.bcc(0x6B, 'mo_fx')                  # bmi
    a.w(0x3029, 0x00BE)
    a.w(0x0240, 0x7FFF)
    a.w(0x0C40, 63)                       # cmpi.w #63,d0
    a.bcc(0x64, 'mo_fx')                  # bcc: not a move
    a.w(0x2069, 0x00A6)                   # movea.l $A6(a1),a0
    a.w(0xD040)                           # add.w d0,d0
    a.w(0xD040)
    a.w(0x2070, 0x0000)                   # movea.l 0(a0,d0.w),a0   its header
    a.w(0x2208)                           # move.l a0,d1
    a.bcc(0x67, 'mo_fx')
    a.w(0x3228, 0x0002)                   # move.w 2(a0),d1     steps - 1
    a.w(0xBE41)                           # cmp.w d1,d7
    a.bcc(0x6F, 'mo_fk')                  # ble
    a.w(0x3E01)                           # move.w d1,d7
    a.label('mo_fk')
    a.w(0x41E8, 20)                       # lea 20(a0),a0       its steps
    a.w(0x2348, 0x00AA)                   # move.l a0,$AA(a1)
    a.w(0x3007)                           # move.w d7,d0
    a.w(0xC0FC, 12)                       # mulu.w #12,d0
    a.w(0xD1C0)                           # adda.l d0,a0
    a.w(0x2348, 0x00AE)                   # move.l a0,$AE(a1)
    a.w(0x3341, 0x00C4)                   # move.w d1,$C4(a1)
    a.w(0x3347, 0x00C2)                   # move.w d7,$C2(a1)
    a.w(0x3010)                           # move.w (a0),d0      the step's frame (not an opcode)
    a.w(0x0C40, 0x0100)
    a.bcc(0x65, 'mo_fx')
    a.w(0x3340, 0x001A)                   # move.w d0,$1A(a1)
    a.label('mo_fx')
    a.w(0x4E75)
    a.label('mo_tab')                     # opponent id, his first blend frame
    for fid, k in MORPH_BLEND.items():
        a.w(fid)
        a.w(fr(MORPH_FRAME + 3 * k))
    a.w(0xFFFF)


def emit_skull(a):
    """In r_generic (a1 = him): his volley. vars: +0 calls since 11 first showed
    (0: not yet), +2 skulls thrown, then a slot per skull (object.l, calls.w,
    bursting.w, step.w, 0.w)."""
    from inputs import ROOT
    co = open(os.path.join(ROOT, 'extracted', 'ec_us', 'BLA.CO'), 'rb').read()
    desc = bytearray(co[PJ_DESC:PJ_DESC + 34])
    assert desc[0:2] == b'\x00\x44', desc.hex()
    desc[0:4] = bytes((0, fx_sheet(), 0, 0))
    a.pcrel(0x45FA, 'sk_v')              # lea vars(pc),a2
    a.w(0x3029, 0x00BE)                  # move.w $BE(a1),d0
    a.w(0x0240, 0x7FFF)
    a.w(0x0C40, 0x0034)                  # cmpi.w #$34,d0      his cast
    a.bcc(0x67, 'sk_in')
    a.w(0x4292)                          # clr.l (a2)           (calls, thrown)
    a.bccw(0x60, 'sk_x')
    a.label('sk_in')
    a.w(0x4A52)                          # tst.w (a2)
    a.bcc(0x66, 'sk_cnt')
    a.w(0x0C69, fr(0x422E), 0x001A)      # cmpi.w #release,$1A(a1)
    a.bccw(0x66, 'sk_x')
    a.pcrel(0x47FA, 'sk_s')              # lea slots(pc),a3     a new volley: no slots
    a.w(0x7000 | (3 * len(SKULL_AT) - 1))   # moveq #8,d0
    a.label('sk_clr')
    a.w(0x429B)                          # clr.l (a3)+
    a.dbra(0, 'sk_clr')
    a.label('sk_cnt')
    a.w(0x5252)                          # addq.w #1,(a2)
    a.w(0x322A, 0x0002)                  # move.w 2(a2),d1     thrown
    a.w(0x0C41, len(SKULL_AT))           # cmpi.w #3,d1
    a.bccw(0x64, 'sk_x')                 # bcc: all thrown
    a.w(0x3601)                          # move.w d1,d3
    a.w(0xD241)                          # add.w d1,d1
    a.pcrel(0x47FA, 'sk_at')             # lea at(pc),a3
    a.w(0x3433, 0x1000)                  # move.w 0(a3,d1.w),d2
    a.w(0xB452)                          # cmp.w (a2),d2
    a.bccw(0x66, 'sk_x')
    a.w(0x526A, 0x0002)                  # addq.w #1,2(a2)
    a.w(0x48E7, 0xFFFE)                  # movem.l d0-d7/a0-a6,-(sp)
    a.w(0x2A49)                          # movea.l a1,a5        (the spawn takes its owner in a5)
    a.pcrel(0x43FA, 'sk_desc')           # lea desc(pc),a1
    a.w(0x303C, PJ_TYPE)                 # move.w #type,d0
    a.w(0x7600)                          # moveq #0,d3
    a.jsr(0x6BBA)
    a.bccw(0x65, 'sk_none')              # bcs: no object free
    a.pcrel(0x47FA, 'sk_v')              # lea vars(pc),a3
    a.w(0x382B, 0x0002)                  # move.w 2(a3),d4      thrown (this one included)
    a.w(0x5344)                          # subq.w #1,d4
    a.w(0xC8FC, 12)                      # mulu.w #12,d4        its slot
    a.pcrel(0x47FA, 'sk_s')              # lea slots(pc),a3
    a.w(0xD6C4)                          # adda.w d4,a3
    a.w(0x2688)                          # move.l a0,(a3)
    a.w(0x42AB, 0x0004)                  # clr.l 4(a3)          calls, bursting
    a.pcrel(0x43FA, 'sk_task')           # lea task(pc),a1
    a.w(0x2468, 0x0088)                  # movea.l $88(a0),a2
    a.w(0x2549, 0x0004)                  # move.l a1,4(a2)
    a.pcrel(0x43FA, 'sk_hit')            # lea hit(pc),a1
    a.w(0x2149, 0x0084)                  # move.l a1,$84(a0)
    a.w(0x317C, fx_sheet() << 8, 0x001A)   # move.w #sheet:00,$1A(a0)
    a.w(0x323C, SKULL_DX)                # move.w #dx,d1
    a.w(0x343C, SKULL_STEP)              # move.w #step,d2
    a.w(0x082D, 0x0003, 0x0020)          # btst #3,$20(a5)      facing left?
    a.bcc(0x67, 'sk_rt')
    a.w(0x4441)                          # neg.w d1
    a.w(0x4442)                          # neg.w d2
    a.label('sk_rt')
    a.w(0x3742, 0x0008)                  # move.w d2,8(a3)      its step
    a.w(0x302D, 0x004E)                  # move.w $4E(a5),d0
    a.w(0xD041)                          # add.w d1,d0
    a.w(0x3140, 0x004E)                  # move.w d0,$4E(a0)
    a.w(0x302D, 0x0052)                  # move.w $52(a5),d0
    a.w(0x0440, SKULL_DY & 0xFFFF)       # subi.w #dy,d0
    a.w(0x3140, 0x0052)                  # move.w d0,$52(a0)
    a.label('sk_none')
    a.w(0x4CDF, 0x7FFF)                  # movem.l (sp)+,d0-d7/a0-a6
    a.bccw(0x60, 'sk_x')
    # sk_find (a5 = a skull): a0 = its slot, Z clear; Z set: none (gone from the table)
    a.label('sk_find')
    a.pcrel(0x41FA, 'sk_s')              # lea slots(pc),a0
    a.w(0x7200 | (len(SKULL_AT) - 1))    # moveq #2,d1
    a.label('sk_fl')
    a.w(0xBBD0)                          # cmpa.l (a0),a5
    a.bcc(0x67, 'sk_ff')
    a.w(0x41E8, 12)                      # lea 12(a0),a0
    a.dbra(1, 'sk_fl')
    a.w(0x7000)                          # moveq #0,d0          Z set: none
    a.w(0x4E75)
    a.label('sk_ff')
    a.w(0x7001)                          # moveq #1,d0          Z clear
    a.w(0x4E75)
    # its task (a5 = it)
    a.label('sk_task')
    # EC's hit engine tests one projectile of his ($122): a skull takes it when it flies,
    # so one still in the air keeps its hit. $6A38 also gives it his palette bits.
    a.w(0x206D, 0x008C)                  # movea.l $8C(a5),a0   him (the spawn's owner)
    a.w(0x2F28, 0x0122)                  # move.l $122(a0),-(sp)
    a.jsr(0x6A38)                        # registered (a0 = him)
    a.w(0x2B48, 0x0090)                  # move.l a0,$90(a5)
    a.w(0x215F, 0x0122)                  # move.l (sp)+,$122(a0)   (not yet)
    a.w(0x3B7C, SKULL_DAMAGE << 8 | SKULL_LEVEL, 0x0078)   # move.w #dmg:level,$78(a5)
    a.w(0x3B7C, HIT_FIRST, 0x00A4)       # move.w #reaction,$A4(a5)
    a.label('sk_l')
    a.bcc(0x61, 'sk_find')               # bsr sk_find
    a.bccw(0x67, 'sk_gone')
    a.w(0x5268, 0x0004)                  # addq.w #1,4(a0)
    a.w(0x3028, 0x0004)                  # move.w 4(a0),d0
    a.w(0x4A68, 0x0006)                  # tst.w 6(a0)          bursting?
    a.bccw(0x66, 'sk_burst')
    a.w(0x0C40, SKULL_FORM[1])           # cmpi.w #form,d0
    a.bcc(0x6E, 'sk_fly')                # bgt: it flies
    # growing in his hand: gone if he stops casting (hit)
    a.w(0x226D, 0x0090)                  # movea.l $90(a5),a1   him
    a.w(0x3229, 0x00BE)                  # move.w $BE(a1),d1
    a.w(0x0241, 0x7FFF)
    a.w(0x0C41, 0x0034)                  # cmpi.w #$34,d1
    a.bccw(0x66, 'sk_gone')
    a.w(0x7200)                          # moveq #0,d1          frame 0 (13)
    a.w(0x0C40, SKULL_FORM[0])           # cmpi.w #form0,d0
    a.bcc(0x6F, 'sk_f0')                 # ble
    a.w(0x7201)                          # moveq #1,d1          frame 1 (16)
    a.label('sk_f0')
    a.w(0x1B41, 0x001B)                  # move.b d1,$1B(a5)
    a.bccw(0x60, 'sk_y')
    a.label('sk_fly')
    a.w(0x0C40, SKULL_FORM[1] + 1)       # cmpi.w #first flying call,d0
    a.bcc(0x66, 'sk_fl2')
    a.w(0x226D, 0x0090)                  # movea.l $90(a5),a1
    a.w(0x234D, 0x0122)                  # move.l a5,$122(a1)   his live projectile now
    a.label('sk_fl2')
    a.w(0x1B7C, 0x0002, 0x001B)          # move.b #2,$1B(a5)    (17)
    a.w(0x3228, 0x0008)                  # move.w 8(a0),d1      its step
    a.w(0xD36D, 0x004E)                  # add.w d1,$4E(a5)
    a.w(0x0C40, SKULL_FORM[1] + SKULL_FLY)   # cmpi.w #end,d0
    a.bccw(0x6E, 'sk_gone')              # bgt: off the screen
    a.bccw(0x60, 'sk_y')
    a.label('sk_burst')                  # (d0 = calls since it hit)
    a.w(0x7203)                          # moveq #3,d1          (56)
    a.w(0x0C40, SKULL_BURST[0])          # cmpi.w #b0,d0
    a.bcc(0x6F, 'sk_b0')                 # ble
    a.w(0x7204)                          # moveq #4,d1          (57)
    a.label('sk_b0')
    a.w(0x1B41, 0x001B)                  # move.b d1,$1B(a5)
    a.w(0x0C40, SKULL_BURST[1])          # cmpi.w #b1,d0
    a.bccw(0x6E, 'sk_gone')              # bgt: done
    a.label('sk_y')
    a.jsr(0x68D0)                        # yield
    a.bccw(0x60, 'sk_l')
    a.label('sk_gone')
    a.bccw(0x61, 'sk_find')              # bsr sk_find
    a.bcc(0x67, 'sk_g2')
    a.w(0x4290)                          # clr.l (a0)           its slot free
    a.label('sk_g2')
    a.w(0x08ED, 0x0002, 0x0082)          # bset #2,$82(a5)      gone
    a.w(0x206D, 0x0090)                  # movea.l $90(a5),a0
    a.w(0xBBE8, 0x0122)                  # cmpa.l $122(a0),a5   his projectile?
    a.bcc(0x66, 'sk_g3')
    a.w(0x42A8, 0x0122)                  # clr.l $122(a0)       he may throw again
    a.label('sk_g3')
    a.jmp(0x6A1A)
    # EC's hit callback (a5 = it): it hit - MK's burst where it is, no more hits (no box)
    a.label('sk_hit')
    a.w(0x48E7, 0xC0C0)                  # movem.l d0-d1/a0-a1,-(sp)
    a.w(0x226D, 0x0090)                  # movea.l $90(a5),a1
    a.w(0xBBE9, 0x0122)                  # cmpa.l $122(a1),a5
    a.bcc(0x66, 'sk_h0')
    a.w(0x42A9, 0x0122)                  # clr.l $122(a1)       no more hits from it
    a.label('sk_h0')
    a.bccw(0x61, 'sk_find')              # bsr sk_find
    a.bcc(0x67, 'sk_h1')
    a.w(0x4A68, 0x0006)                  # tst.w 6(a0)
    a.bcc(0x66, 'sk_h2')                 # already bursting
    a.w(0x317C, 0x0001, 0x0006)          # move.w #1,6(a0)      bursting
    a.w(0x4268, 0x0004)                  # clr.w 4(a0)          its calls from now
    a.w(0x1B7C, 0x0003, 0x001B)          # move.b #3,$1B(a5)    (56: no box)
    a.bcc(0x60, 'sk_h2')
    a.label('sk_h1')
    a.w(0x08ED, 0x0002, 0x0082)          # bset #2,$82(a5)      (not ours: gone)
    a.label('sk_h2')
    a.w(0x4CDF, 0x0303)                  # movem.l (sp)+,d0-d1/a0-a1
    a.w(0x4E75)
    a.label('sk_at')
    a.w(*SKULL_AT)
    a.label('sk_desc')
    a.out += bytes(desc)
    a.label('sk_v')
    a.w(0, 0)                            # +0 calls since 11 showed, +2 thrown
    a.label('sk_s')
    a.out += bytes(12 * len(SKULL_AT))   # slots: object.l, calls.w, bursting.w, step.w, 0.w
    a.label('sk_x')


PROJ_TEST = None              # experiment (off): (sheet, frame) - his lightning spawns an object showing it


def emit_proj_test(a):
    """Experiment (a1 = him): an object of his own descriptor (id), showing
    an effect-sheet frame, flown forward 6 px a frame for 40 frames."""
    a.label('g_proj')
    a.w(0x48E7, 0xFFFE)                  # movem.l d0-d7/a0-a6,-(sp)
    a.w(0x303C, SCORPION_ID)             # move.w #id,d0
    a.w(0x3229, 0x004E)                  # move.w $4E(a1),d1
    a.w(0x3429, 0x0052)                  # move.w $52(a1),d2
    a.w(0x0442, 70)                      # subi.w #70,d2
    a.w(0x2F09)                          # move.l a1,-(sp)
    a.jsr(EFFECT_SPAWN)
    a.w(0x225F)                          # movea.l (sp)+,a1
    a.bccw(0x65, 'pj_out')
    a.w(0x317C, PROJ_TEST[0] << 8 | PROJ_TEST[1], 0x001A)   # move.w #frame,$1A(a0)
    a.w(0x3029, 0x007A)                  # move.w $7A(a1),d0    attr: his line, his facing
    a.w(0x0240, 0x0003)
    a.w(0xE148)
    a.w(0xEB48)
    a.w(0x3229, 0x0020)                  # move.w $20(a1),d1
    a.w(0x0241, 0x0800)
    a.w(0x8041)                          # or.w d1,d0
    a.w(0x3140, 0x001E)
    a.w(0x3140, 0x0020)
    a.w(0x317C, 0x0006, 0x0060)          # move.w #6,$60(a0)    vx
    a.w(0x0829, 0x0003, 0x0020)          # btst #3,$20(a1)      facing left?
    a.bcc(0x67, 'pj_r')
    a.w(0x4468, 0x0060)                  # neg.w $60(a0)
    a.label('pj_r')
    a.w(0x317C, 40, 0x0064)              # move.w #40,$64(a0)   frames
    a.w(0x2268, 0x0088)                  # movea.l $88(a0),a1   its task
    a.pcrel(0x487A, 'pj_task')
    a.w(0x235F, 0x0004)                  # move.l (sp)+,4(a1)
    a.w(0x4269, 0x0008)                  # clr.w 8(a1)
    a.label('pj_out')
    a.w(0x4CDF, 0x7FFF)                  # movem.l (sp)+,d0-d7/a0-a6
    a.w(0x4E75)
    a.label('pj_task')                   # a5 = the object
    a.w(0x302D, 0x0060)                  # move.w $60(a5),d0
    a.w(0xD16D, 0x004E)                  # add.w d0,$4E(a5)
    a.w(0x536D, 0x0064)                  # subq.w #1,$64(a5)
    a.bcc(0x67, 'pj_gone')
    a.w(0x7001)                          # moveq #1,d0
    a.jsr(0x68D6)
    a.bcc(0x60, 'pj_task')
    a.label('pj_gone')
    a.w(0x08ED, 0x0002, 0x0082)          # bset #2,$82(a5)
    a.jmp(0x6A1A)


# Sub-Zero's MK fatality (the spine rip; tools/lib/mkfatality_subzero.py): in his
# FINISH HIM window, forward, down, forward + high punch (EC Y) up close. His
# poses on 41:52-41:59; the loser's (MK's headless body as a dark figure,
# fatality_corpse) on 41:40-41:45 and 41:5A/5B, drawn with his palette
# (mode 1, as Scorpion's skeleton). MK's timeline sampled every 6 frames
# from his grab (capture frame 144), its pause before shortened to SZF_PAUSE.
SZF_HIS = [1, 3, 5, 7, 10, 15, 23, 27]                 # his capture poses kept
SZF_HIS_SLOTS = [0x4152 + k for k in range(8)]
SZF_VIC = [8, 10, 12, 15, 17, 21, 26, 32]              # the loser's (corpse) poses kept
SZF_VIC_SLOTS = [0x4140, 0x4141, 0x4142, 0x4143, 0x4144, 0x4145, 0x415A, 0x415B]
SZF_MUSIC_LAG = 1.37          # s: the music asked for (after her death art's read) -> heard (the
                              #  drive seeks to the disc's end: measured in build/shots/subzero_moves.mp4)
SZF_RIP_IN_MUSIC = 1.33       # s: MK's rip (her first headless frame) into its fatality music
SZF_FROM, SZF_TO, SZF_STEP = 144, 420, 6                 # capture frames (his stance before 144)
SZF_PAUSE = round(((SZF_MUSIC_LAG + SZF_RIP_IN_MUSIC) * 60 - (170 - SZF_FROM)) / 2)   # calls (2 frames)
SZF_GAP = 26                  # px between them when he grabs (MK: 24 between the captured centres, x1.08)
SZF_TAPS = (FWD, DOWN, FWD)   # then a punch (EC X or Y)


def szf_zframe(p):
    """MK victim capture pose -> EC death-sheet frame (Z<xx>.BIN sheet 2:
    0-2 blown back (not used), 3-5 headless stagger, 6 knees, 7 falling, 8-11 lying)."""
    if p < 20:                          # (EC's frames 0-2 are the shotgun blast: the body thrown
        return 3 + max(0, p - 10) * 3 // 10   #  back, bent the other way - it read as her turning round)
    if p < 26:
        return 5
    if p < 30:
        return 6
    if p < 32:
        return 7
    return 8


SZF_ZFLIP = False             # EC's death art drawn the other way round from her own frames?
SZF_SETTLE = 2                # timeline steps per EC lying frame (8 -> 11: flat)
# her neck on EC's death frames (median over the fighters' Z sheet 2: the top of
# the headless body, from her feet, art facing right): where the blood spurts
SZF_NECK = [(-16, -78), (-18, -84), (-13, -86), (-6, -86), (-3, -81), (8, -77),
            (9, -58), (41, -43), (50, -21), (48, -19), (48, -19), (48, -19)]
SZF_BLEED = 12                # death frames that bleed: all (lying: it runs out onto the floor)
SZF_FLOW = 2                  # calls (2 frames each) between spurts: a power of 2


def szf_table():
    """[(calls, his frame, victim mode, 0)] in Blade's numbering; victim mode
    = EC death frame + 1 (0: she keeps her own frame)."""
    from inputs import ROOT
    d = os.path.join(ROOT, 'extracted', 'mk_moves_subzero')
    his = [int(v) for v in open(os.path.join(d, 'fatality', 'order.txt')).read().split()]
    vic = [int(v) for v in open(os.path.join(d, 'fatality_victim', 'order.txt')).read().split()]
    near = lambda k, keep: min(keep, key=lambda q: (abs(q - k), q))
    rows = [(SZF_PAUSE, 0, 0, 0)]                       # dark stage, she sways: his stance kept
    down = 0
    for t in range(SZF_FROM, SZF_TO, SZF_STEP):
        h = SZF_HIS_SLOTS[SZF_HIS.index(near(his[t], SZF_HIS))]
        z = szf_zframe(vic[t])
        if vic[t] >= 32:                                # MK's body is down: EC's settles flat (8 -> 11)
            z = min(11, 8 + down // SZF_SETTLE)
            down += 1
        k = SZF_HIS_SLOTS.index(h)
        row = (SZF_STEP // 2, h, 0 if vic[t] < 8 else 1 + z, k + 1 if SZF_HOFF()[k] != (0, 0) else 0)
        if rows and rows[-1][1:] == row[1:]:
            rows[-1] = (rows[-1][0] + row[0],) + row[1:]
        else:
            rows.append(row)
    return rows


# EC's own death art for the loser (docs/notes/2026-11.md "EC's own headless deaths"):
# Z<xx>.BIN file id $EC + n, its sheet 2 = $112 + n (n >= 10: one less, ZEC has
# no sheet 2). Victim idx (id - 2) -> n + 1; 0 = none (the MK fighters' hosts,
# the gag animals, the bosses: their Z art is someone else's or missing).
SZF_Z = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8, 12: 10, 13: 11,
         14: 12, 19: 14, 20: 15, 22: 17}
SZF_ZFILE = 0xEC
SZF_HEAD_FRAME = 6            # Z sheet 1 ($100 + n): the loser's own severed head, upright
SZF_HEAD_BASE = 2             # his effect sheet's frame of head 0 (after the ice ball's 1 + 1: mkprojectile.PROJ)
fr_fx = lambda k: (fx_sheet() << 8) | k   # his effect sheet's frame k
SZF_HEAD_UP = 0               # px: the MK head blob's centre to its bottom (EC's head frame sits on its bottom)


def szf_head_offsets():
    """[(dx, dy)] per held slot (SZF_HIS order): where MK's capture shows the
    head he holds, from his feet (EK scale); (0, 0) = no head shown yet."""
    import json
    from inputs import ROOT
    import numpy as np
    d = os.path.join(ROOT, 'extracted', 'mk_moves_subzero')
    anc = json.load(open(os.path.join(d, 'fatality', 'anchors.json')))
    vic = np.load(os.path.join(d, 'fatality_victim', 'rgb.npy'))
    oh = [int(v) for v in open(os.path.join(d, 'fatality', 'order.txt')).read().split()]
    ov = [int(v) for v in open(os.path.join(d, 'fatality_victim', 'order.txt')).read().split()]
    out = []
    for p in SZF_HIS:
        blobs = []
        for t in (t for t, h in enumerate(oh) if h == p):
            m = vic[ov[t]].any(-1).copy()
            m[112:, :] = False                       # (mkfatality_subzero HEAD_Y / HEAD_X:
            m[:, 192:] = False                       #  the head's corner of the capture)
            if m.any():
                ys, xs = np.nonzero(m)
                blobs.append((xs.mean(), ys.mean()))
        if not blobs:
            out.append((0, 0))
            continue
        cx, cy = blobs[0]
        out.append((round((cx - anc[p][0]) * 1.08), round((cy + SZF_HEAD_UP - anc[p][1]) * 1.08)))
    return out
TAIL_FIGHTERS = (SUBZERO_ID, JOHNNY_ID, RAIDEN_ID, LIUKANG_ID, SONYA_ID, KANO_ID, REPTILE_ID)   # (+ FATALS: their fatality data)


def szf_tail():
    return fat_tail(SUBZERO_ID)


def fat_tail(fid):
    """His fatality's data, appended to his .PL after its chunk chain (loaded
    with it, never parsed): the timeline rows (calls, his frame, her death
    frame + 1, head position + 1), a zero row, the victim table (szf_ztab:
    3 bytes per loser) and the head positions (dx, dy from his feet, his way
    round). -> (data, {'ztab': offset, 'hoff': offset})."""
    F = FATALS[fid]
    rows = [(n, fr(h) if h else 0, m, v) for n, h, m, v in F['table']()]
    out = b''.join(struct.pack('>4H', *r) for r in rows) + bytes(8)
    offs = {'ztab': len(out)}
    out += b''.join(bytes(e) for e in szf_ztab())
    out += bytes(len(out) % 2)
    offs['hoff'] = len(out)
    for dx, dy in F['hoff']():
        out += struct.pack('>2h', dx, dy)
    return out, offs


def szf_ztab():
    """Per loser id - 2 (25): (head + 1 (0 = no death art), file id, sheet 2 - $100, sheet 1 - $100).
    EC fighters: Z<xx>.BIN n ($EC + n; sheet 2 $112 + n, one less from n = 10:
    ZEC has none), head n. MK fighters: their death art (tools/lib/mkdeath.py), heads
    after EC's."""
    import mkdeath
    out = []
    for i in range(25):
        n = SZF_Z.get(i)
        out.append((n + 1, 0xEC + n, (0x112 + n - (n >= 10)) & 0xFF, n) if n is not None else (0, 0, 0, 0))
    for k, (fid, (file_id, sheet2, sheet1)) in enumerate(mkdeath.spine_rip_entries().items()):
        out[fid - 2] = (len(Z_NAMES) + k + 1, file_id, sheet2 & 0xFF, sheet1 & 0xFF)
    return out


Z_NAMES = 'ZSH ZLR ZRX ZSL ZTR ZMD ZXV ZBD ZJT ZEC ZRP ZPH ZEX ZCH ZRV ZSN ZBS ZDW'.split()   # file $EC + n


def fxl_pieces(key):
    """[(dx, dy, raw tiles, frame record)] per pose in CAP_FATALS[key]['fxl']: the part
    of his fatality pose that his own frame can't hold (outside scorpion_full.kept_window:
    Raiden's burst ahead of him, his bolts > 127 px above his feet), centred on itself
    (a frame's pieces reach only +-128 px from its origin); (dx, dy) = that centre from
    his feet. Tiles numbered on from the first piece's (they go over his effect sheet's
    tiles at the fatality, as the heads')."""
    import numpy as np
    import scorpion_full as sf, mkprojectile
    from inputs import ROOT
    F = CAP_FATALS[key]
    poses, anchors, cram = sf.load_action(ROOT, 'fatality_mk')
    if F.get('kiss'):                                    # Sonya: her kiss alone (kiss_path flies it)
        img, _ = _kiss_sprite(key, F['kiss'][0])
        ox, oy = img.shape[1] // 2, img.shape[0] // 2
        tiles, pieces = mkprojectile.tiles_and_pieces(img, ox, oy, 0, skip_empty=True)
        return [(0, 0, b''.join(tiles), mkprojectile.frame_record(img, ox, oy, pieces))]
    out, first = [], 0
    for k in F['fxl']:
        full, (ax, ay) = sf.scale_pose(poses[k], anchors[k], cram)
        full = sf.remap_colours(full)
        x0, y0, x1, y1 = sf.kept_window(full, (ax, ay))
        lost = np.zeros_like(full)                       # (only what's lost ahead of him or above him:
        lost[:y0] = full[:y0]                            #  the bits behind are small)
        lost[:, x1:] = full[:, x1:]
        ys, xs = np.nonzero(lost)
        img = lost[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        ox, oy = img.shape[1] // 2, img.shape[0] // 2
        tiles, pieces = mkprojectile.tiles_and_pieces(img, ox, oy, first, skip_empty=True)
        first += len(tiles)
        out.append((xs.min() + ox - ax, ys.min() + oy - (ay - sf.FOOT_DROP),
                    b''.join(tiles), mkprojectile.frame_record(img, ox, oy, pieces)))
    return out


def _kiss_sprite(key, k):
    """(image, (dx, dy)): the kiss in her capture pose k (its smallest piece, < 200 px)
    and its centre from her feet, as fxl_pieces places a piece."""
    import numpy as np
    from scipy import ndimage
    import scorpion_full as sf
    from inputs import ROOT
    poses, anchors, cram = sf.load_action(ROOT, 'fatality_mk')
    full, (ax, ay) = sf.scale_pose(poses[k], anchors[k], cram)
    full = sf.remap_colours(full)
    lab, n = ndimage.label(full != 0, structure=np.ones((3, 3)))
    sizes = ndimage.sum(np.ones_like(lab), lab, range(1, n + 1))
    i = 1 + min((s, i) for i, s in enumerate(sizes) if s < 200)[1]
    ys, xs = np.nonzero(lab == i)
    img = np.where(lab == i, full, 0)[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    return img, (xs.min() + img.shape[1] // 2 - ax, ys.min() + img.shape[0] // 2 - (ay - sf.FOOT_DROP))


def kiss_path(key):
    """{capture t: (dx, dy)} for the rows where MK's kiss is off MK's screen (her pose
    without it, between its rise and its drop: F['kiss'] = (last rising pose, the one
    before, first falling pose)). MK's screen ends ~140 px above her feet, ours ~200:
    shown, it would vanish in mid-air. It arcs instead, as one throw would: up at its
    rising speed, down into the falling pose's place (x straight across)."""
    F = CAP_FATALS[key]
    his = cap_capture(key)[0]
    near = cap_near(F)
    top, prev, drop = F['kiss']
    ts = list(range(F['frm'], F['to'], F['step']))
    t_top = max(t for t in ts if near(max(his[t], 0)) == top)
    t_prev = max(t for t in ts if near(max(his[t], 0)) == prev)
    t_drop = min(t for t in ts if t > t_top and near(max(his[t], 0)) == drop)
    (x0, y0), (_, yp), (x1, y1) = (_kiss_sprite(key, k)[1] for k in (top, prev, drop))
    v0 = (y0 - yp) / (t_top - t_prev)
    T = t_drop - t_top
    acc = 2 * (y1 - y0 - v0 * T) / T ** 2
    return {t: (round(x0 + (x1 - x0) * (t - t_top) / T), round(y0 + v0 * (t - t_top) + acc * (t - t_top) ** 2 / 2))
            for t in ts if t_top < t < t_drop}


_FXL = {}


def fxl_cached(key):
    if key not in _FXL:
        _FXL[key] = fxl_pieces(key)
    return _FXL[key]


def szf_heads():
    """[(raw tiles, frame record)] per Z file n: the loser's own severed head
    (sheet 1 frame SZF_HEAD_FRAME), its tiles numbered from 0. The records go
    into his effect sheet ($44, after the projectile's frames: patches.mk_projectile);
    the tiles into his .PL's tail, uploaded over that sheet's tiles at the
    fatality (gk_head)."""
    import numpy as np
    import ecdeath, mkprojectile
    out = []
    for name in Z_NAMES:
        srcs, sheets = ecdeath.load(name)
        sid, src, sh = sheets[0]
        f = ecdeath.frames(srcs[src], sh)[SZF_HEAD_FRAME]
        ys, xs = np.nonzero(f)
        img = f[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        ox, oy = img.shape[1] // 2, img.shape[0] // 2   # centred (EC's own origins differ per fighter)
        tiles, pieces = mkprojectile.tiles_and_pieces(img, ox, oy, 0)
        out.append((b''.join(tiles), mkprojectile.frame_record(img, ox, oy, pieces)))
    import mkdeath                                    # the MK fighters': MK's own held head
    for who in mkdeath.FILES:
        img = mkdeath.held_head(who)
        ox, oy = img.shape[1] // 2, img.shape[0] // 2
        tiles, pieces = mkprojectile.tiles_and_pieces(img, ox, oy, 0)
        out.append((b''.join(tiles), mkprojectile.frame_record(img, ox, oy, pieces)))
    return out


SZF_HEAD_PAD = 4096           # bytes after the last head: EC's upload takes the source's whole size


def szf_head_desc():
    """A spawn descriptor for her head: Blade's projectile one (as emit_proj's),
    its frame set after the spawn."""
    from inputs import ROOT
    co = open(os.path.join(ROOT, 'extracted', 'ec_us', 'BLA.CO'), 'rb').read()
    desc = bytearray(co[PJ_DESC:PJ_DESC + 34])
    desc[0:4] = bytes((0, fx_sheet(), 0, 0))   # (a sheet that's loaded: his effect sheet)
    # Its message handler ($84 from +26) is Blade's, absolute: right only in BLA.CO
    # loaded for player 1; in player 2's module (.OC at another address) or another
    # host it is whatever lies there, and EC calls it (a delete sends message 6:
    # player 2's crashed on line A). These objects need no messages: an rts in SUB.BIN,
    # which never moves.
    sub = open(os.path.join(ROOT, 'extracted', 'ec_us', 'SUB.BIN'), 'rb').read()
    assert desc[26:30] == b'\x00\x01\xeb\x48' and sub[EC_RTS - 0x6000:EC_RTS - 0x5FFE] == b'\x4e\x75'
    desc[26:30] = EC_RTS.to_bytes(4, 'big')
    return bytes(desc)


EC_RTS = 0xFB10               # SUB.BIN: an rts (end of EC's pose-step routine)


SZF_TAIL = {}                 # 'off': his .PL tail offset, 'ztab': victim table offset in it (patches.mk_code)


def szf_pins():
    return [('fatality_held', [f'{f >> 8:02x}:{f & 0xFF:02x}={k}' for f, k in zip(SZF_HIS_SLOTS, SZF_HIS)])]


_SZF_HOFF = []


def SZF_HOFF():
    """szf_head_offsets(), computed once."""
    if not _SZF_HOFF:
        _SZF_HOFF.extend(szf_head_offsets())
    return _SZF_HOFF


# ---- fatalities built from MK's own capture (tools/lib/mkfatality_capture.py:
# fatality_mk/ = him, fatality_mk_victim/ = the loser, frames counted from the
# end of the input; their sounds: tools/lib/mkfatalsound.py). Per fighter:
#   dir: his MK captures; poses: his capture poses pinned on SZF_HIS_SLOTS
#   (41:52-41:59) in his art; frm/to/step: the capture frames played (his
#   stance before frm becomes the pause); hit: the frame the head comes off;
#   hit_in_music: s from MK's track 13 start to it; gap: px between them;
#   taps: his input before HP (EC Y); head: the head flies (Johnny) or not (Raiden's explodes)
CAP_FATALS = {
    # Johnny Cage: F, F, F + HP close - the uppercut knocks the head off; it flies
    # up off the screen, drops beside him and rolls
    'johnny': dict(dir='mk_moves_johnny', poses=[0, 2, 3, 5, 6, 7, 17, 54], frm=75, to=420, step=4,
                   hit=180, hit_in_music=1.46, gap=50, taps=(FWD, FWD, FWD), head=True),
    # Raiden: F, B, B, B + HP close - his lightning holds the loser until the head
    # explodes; his victory pose crackles (21 / 31)
    # Liu Kang: D, B, U, F, D (MK CD) - the cartwheel, then the uppercut sends the loser
    # off the top of the screen; the body falls back further away and lies there
    # (his poses by what they show: the cartwheel is a leg swung up (7), a handstand (10),
    # the body flat with the legs kicking out into her (17); then crouched (22). Nearest
    # pose NUMBERS kept 4, 10, 16, 22: no handstand or kick, it read as a roundhouse.)
    'liukang': dict(dir='mk_moves_liukang', poses=[0, 7, 10, 17, 22, 28, 48, 60], frm=75, to=300, step=4,
                    map=((2, 0), (8, 7), (12, 10), (20, 17), (26, 22), (38, 28), (54, 48), (999, 60)),
                    hit=146, hit_in_music=1.30, gap=21, taps=(DOWN, BACK, UP, FWD, DOWN), head=False, fly=True,
                    react=True),   # (13 at 1.13 s; react: she reels from the cartwheel's kicks, as MK's)
    # Sonya: F, F, B, B + Block (anywhere) - she blows a kiss, it drifts over, the loser
    # bursts into flames, burns black and a charred skeleton collapses (mkburn.py: the
    # burning frames in her art, shown on the loser in her palette, as Scorpion's)
    # Her poses by what they show (the nearest NUMBER put the kiss back by her lips after it
    # landed, and showed it again later): she blows (8); the kiss rises (13, 17, 21); it
    # arcs over the victim's head higher than an EC frame reaches (> 127 px up) and is off
    # MK's own screen for a while: her pose without it (10); it drops onto the victim (52,
    # 56); her last pose (64).
    'sonya': dict(dir='mk_moves_sonya', poses=[10, 8, 13, 17, 21, 52, 56, 65], frm=133, to=420, step=4,
                  map=((2, 10), (9, 8), (12, 10), (14, 13), (18, 17), (21, 21), (48, 10), (53, 52),
                       (57, 56), (999, 65)),
                  hit=247, hit_in_music=2.62, gap=25, taps=(FWD, FWD, BACK, BACK), head=False, burn=True,
                  kiss=(21, 17, 52)),   # (13 at 1.50 s; kiss: off MK's screen after 21, back in 52: kiss_path)
    # Kano: B, B + LP (MK CD) - his hand into the chest, the heart held up beating; the loser
    # staggers, then falls back (as Liu Kang's: her own frame, the air pose, on her back)
    # (the heart held up beats on as MK's - poses 8-12, 8 frames each, from 273 to past the capture's
    # end: to 472, on a heart pose he then holds; 8 and 10 shown as 9 and 11, the heart in each - the
    # nearest kept pose put 8 on 7, his empty fist, and the timeline ended on it at 320: the heart
    # showed ~1 s, then vanished)
    'kano': dict(dir='mk_moves_kano', poses=[0, 2, 3, 5, 7, 9, 11, 12], frm=110, to=472, step=4,
                 map=((1, 0), (2, 2), (4, 3), (6, 5), (7, 7), (9, 9), (11, 11), (999, 12)),
                 hit=227, hit_in_music=2.59, gap=36, taps=(BACK, BACK), head=False, fly=True),   # (13 at 1.19 s)
    # (by what they show: wind-up (0), casting (5), the arc (8), the burst at her head (10),
    # his hat back on (15), arms out (17), arms up with the bolts flickering (21 / 31); the
    # nearest NUMBERS showed the burst again where he puts his hat back on)
    'raiden': dict(dir='mk_moves_raiden', poses=[0, 5, 8, 10, 15, 17, 21, 31], frm=140, to=460, step=4,
                   map=((3, 0), (6, 5), (9, 8), (11, 10), (13, 5), (15, 15), (17, 17), (29, 21), (999, 31)),
                   fxl=(10, 21, 31),     # poses whose lightning his frame can't hold: drawn by an object (fxl_pieces)
                   hit=208, hit_in_music=2.03, gap=38, taps=(FWD, BACK, BACK, BACK), head=False),   # (13 at 1.44 s)
}


def cap_near(F):
    """Capture pose -> the kept pose shown for it: F['map'] ((last capture pose,
    kept pose), ... in order) when given, else the nearest kept pose number."""
    if 'map' in F:
        return lambda k: next(q for last, q in F['map'] if k <= last)
    return lambda k: min(F['poses'], key=lambda q: (abs(q - k), q))


def cap_pins(key):
    return [('fatality_mk', [f'{f >> 8:02x}:{f & 0xFF:02x}={k}'
                             for f, k in zip(SZF_HIS_SLOTS, CAP_FATALS[key]['poses'])])]


def jcf_pins():
    return cap_pins('johnny')


def cap_capture(key):
    import json
    from inputs import ROOT
    import numpy as np
    d = os.path.join(ROOT, 'extracted', CAP_FATALS[key]['dir'])
    tl = json.load(open(os.path.join(d, 'fatality_mk', 'timeline.json')))
    vic = np.load(os.path.join(d, 'fatality_mk_victim', 'indexed.npy'))
    his_anchor = json.load(open(os.path.join(d, 'fatality_mk', 'anchors.json')))[0]
    vic_anchor = json.load(open(os.path.join(d, 'fatality_mk_victim', 'anchors.json')))[0]
    return tl['his'], tl['hers'], vic, his_anchor, vic_anchor


def cap_track(key):
    """Per capture frame: (her body's top from her feet, the head's centre (dx,
    dy) from HIS feet in MK px, or None). A flying head that goes above the
    capture's top (sprites there are the HUD's) is filled in on a parabola."""
    from scipy import ndimage
    import numpy as np
    F = CAP_FATALS[key]
    his, hers, vic, (hx, hy), (vx, vy) = cap_capture(key)
    tops, heads = [], []
    for t, v in enumerate(hers):
        if v < 0 or not vic[v].any():
            tops.append(None)
            heads.append(None)
            continue
        f = vic[v]
        lab, n = ndimage.label(f > 0, structure=np.ones((3, 3)))
        sizes = ndimage.sum(f > 0, lab, range(1, n + 1))
        big = int(np.argmax(sizes)) + 1
        tops.append(int(np.nonzero((lab == big).any(1))[0].min()) - vy)
        hd = [ndimage.center_of_mass(f > 0, lab, k) for k in range(1, n + 1) if k != big and sizes[k - 1] > 30]
        heads.append((hd[0][1] - hx, hd[0][0] - hy) if hd and t >= F['hit'] and F['head'] else None)
    if F['head']:
        seen = [t for t in range(F['hit'], len(heads)) if heads[t] is not None]
        up = [t for t in seen if t < seen[0] + 10]             # rising, then lost above the top
        down = [t for t in seen if t > up[-1] + 10][:4]        # coming back down
        ts = np.array(up + down, float)
        py = np.polyfit(ts, [heads[t][1] for t in up + down], 2)
        px = np.polyfit(ts, [heads[t][0] for t in up + down], 1)
        for t in range(F['hit'], down[0]):
            if heads[t] is None:
                heads[t] = (float(np.polyval(px, t)), float(np.polyval(py, t)))
    return tops, heads


_CAP_HOFF = {}


AIR, AIR_C = 8, (25, 12)      # Z sheet 1: the body in the air; its box centre from the origin (facing right)
LYING = 0                      # Z sheet 1: on the back (feet on the floor line)


STAGGER = 14                  # death art sheet 2 (code without $80): 14-19 stand reeling, head on


def cap_fly(key):
    """Per capture frame: (her death frame code, (dx, dy) from his feet or None) for a
    flying victim: her own frame before the hit (code 0); then the air pose ($80 |
    AIR + 1) where MK's body is, hidden above the screen while MK's is off its top,
    and on her back (LYING) where it lands."""
    import numpy as np
    F = CAP_FATALS[key]
    his, hers, vic, (hx, hy), (vx, vy) = cap_capture(key)
    out, last_dx = [], 0
    for t, v in enumerate(hers):
        if t < F['hit']:
            if F.get('react') and v > 3:                    # MK's victim reels from the kicks: her
                out.append((STAGGER + 1 + min(5, (v - 4) * 6 // 10), None))   # death art's stagger, head on
            else:
                out.append((0, None))
            continue
        if v < 0 or not vic[v].any():
            out.append((0x80 | (AIR + 1), (last_dx, -320)))   # above the screen
            continue
        ys, xs = np.nonzero(vic[v])
        cx, cy, bot = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2, ys.max() + 1
        if bot < vy - 6:                                      # in the air
            dx = round((cx - hx) * 1.08) + AIR_C[0]           # (she faces him: the box mirrored)
            out.append((0x80 | (AIR + 1), (dx, round((cy - hy) * 1.08) - AIR_C[1] or -1)))
        else:
            dx = round((cx - hx) * 1.08)
            out.append((0x80 | (LYING + 1), (dx, -1)))
        last_dx = dx
    return out


BURN_FIRE = [0x415A, 0x415B, 0x415C, 0x415D]                 # mkburn.FIRE's frames in her art
BURN_BONES = [0x4140, 0x4141, 0x4142, 0x4143, 0x4144, 0x4145]  # mkburn.BONES'


def burn_pins():
    import mkburn
    slots = BURN_FIRE[:len(mkburn.FIRE)] + BURN_BONES
    return [('fatality_burn', [f'{f >> 8:02x}:{f & 0xFF:02x}={k}' for k, f in enumerate(slots)])]


def _burn_table(key):
    """Rows whose 4th word is the loser's frame from HER art (0: keep hers)."""
    import mkburn
    F = CAP_FATALS[key]
    his, hers, *_ = cap_capture(key)
    near = cap_near(F)
    pause = round(((SZF_MUSIC_LAG + F['hit_in_music']) * 60 - (F['hit'] - F['frm'])) / 2)
    caps = mkburn.FIRE + mkburn.BONES
    slots = BURN_FIRE[:len(mkburn.FIRE)] + BURN_BONES
    kiss = kiss_path(key) if F.get('kiss') else {}
    rows = [(max(pause, 1), 0, 0, 0)]
    for t in range(F['frm'], F['to'], F['step']):
        h = SZF_HIS_SLOTS[F['poses'].index(near(max(his[t], 0)))]
        v = hers[t]
        fv = 0
        if t >= F['hit'] and v >= min(caps):
            fv = fr(slots[caps.index(min(caps, key=lambda q: (abs(q - v), q)))])
        elif t in kiss:                                 # $8000 + n: her kiss at kiss_path's n-th place
            fv = 0x8000 | sorted(kiss).index(t)
        row = (F['step'] // 2, h, 0, fv)
        if rows[-1][1:] == row[1:]:
            rows[-1] = (rows[-1][0] + row[0],) + row[1:]
        else:
            rows.append(row)
    _CAP_HOFF[key] = []
    return rows


def cap_table(key):
    """[(calls, his frame, her death frame + 1, head position + 1)] (as szf_table)."""
    F = CAP_FATALS[key]
    if F.get('fly'):
        return _fly_table(key)
    if F.get('burn'):
        return _burn_table(key)
    his, hers, *_ = cap_capture(key)
    tops, heads = cap_track(key)
    near = cap_near(F)
    pause = round(((SZF_MUSIC_LAG + F['hit_in_music']) * 60 - (F['hit'] - F['frm'])) / 2) if F['hit_in_music'] else 0
    rows, down, hoff = [(max(pause, 1), 0, 0, 0)], 0, []
    for t in range(F['frm'], F['to'], F['step']):
        h = SZF_HIS_SLOTS[F['poses'].index(near(max(his[t], 0)))]
        top = tops[t]
        if t < F['hit'] or top is None:
            z = -1                                          # her own (dazed) frame
        elif top <= -78:
            z = 4                                           # EC's headless body, upright
        elif top <= -50:
            z = 7                                           # on her knees
        elif top <= -30:
            z = 8                                           # falling forward
        else:
            z = min(12, 9 + down // SZF_SETTLE)             # flat
            down += 1
        hv = 0
        if F.get('fxl'):                                    # the lightning piece of his pose + 1
            k = near(max(his[t], 0))
            hv = F['fxl'].index(k) + 1 if k in F['fxl'] else 0
        elif heads[t] is not None:
            pos = (round(heads[t][0] * 1.08), round(heads[t][1] * 1.08) or -1)
            if not hoff or hoff[-1] != pos:                 # (still: the same entry, rows merge)
                hoff.append(pos)
            hv = len(hoff)
        row = (F['step'] // 2, h, z + 1, hv)
        if rows[-1][1:] == row[1:]:
            rows[-1] = (rows[-1][0] + row[0],) + row[1:]
        else:
            rows.append(row)
    _CAP_HOFF[key] = hoff
    return rows


def _fly_table(key):
    F = CAP_FATALS[key]
    his = cap_capture(key)[0]
    fly = cap_fly(key)
    near = cap_near(F)
    pause = round(((SZF_MUSIC_LAG + F['hit_in_music']) * 60 - (F['hit'] - F['frm'])) / 2) if F['hit_in_music'] else 0
    rows, hoff = [(max(pause, 1), 0, 0, 0)], []
    for t in range(F['frm'], F['to'], F['step']):
        h = SZF_HIS_SLOTS[F['poses'].index(near(max(his[t], 0)))]
        code, pos = fly[t]
        pv = 0
        if pos is not None:
            if not hoff or hoff[-1] != pos:
                hoff.append(pos)
            pv = len(hoff)
        row = (F['step'] // 2, h, code, pv)
        if rows[-1][1:] == row[1:]:
            rows[-1] = (rows[-1][0] + row[0],) + row[1:]
        else:
            rows.append(row)
    _CAP_HOFF[key] = hoff
    return rows


def cap_hoff(key):
    if key not in _CAP_HOFF:
        cap_table(key)
    return list(_CAP_HOFF[key])


def _head_base(key):
    import mkprojectile
    _, flight, impact = mkprojectile.PROJ[key]
    return len(flight) + len(impact)      # his effect sheet: the projectile's frames, then the heads


# fighters with an MK decapitation fatality on the shared engine (emit_gfatal)
FATALS = {
    SUBZERO_ID: dict(taps=SZF_TAPS, gap=SZF_GAP, table=szf_table, hoff=SZF_HOFF, music='f_time_sz',
                     head_base=lambda: _head_base('subzero')),
    JOHNNY_ID: dict(taps=CAP_FATALS['johnny']['taps'], gap=CAP_FATALS['johnny']['gap'],
                    table=lambda: cap_table('johnny'), hoff=lambda: cap_hoff('johnny'), music='f_time_jc',
                    head_base=lambda: _head_base('johnny')),
    LIUKANG_ID: dict(taps=CAP_FATALS['liukang']['taps'], gap=CAP_FATALS['liukang']['gap'],
                     table=lambda: cap_table('liukang'), hoff=lambda: cap_hoff('liukang'), music='f_time_lk',
                     head_base=lambda: _head_base('liukang'), heads=False, move=True, bleed=False,
                     button=None),        # (MK CD: the last tap does it, no button)
    SONYA_ID: dict(taps=CAP_FATALS['sonya']['taps'], gap=CAP_FATALS['sonya']['gap'],
                   table=lambda: cap_table('sonya'), hoff=lambda: cap_hoff('sonya'), music='f_time_sn',
                   head_base=lambda: _head_base('sonya'), heads=False, burn=True, bleed=False, button_bit=8,   # (MK's Block: EC Z)
                   fxl=lambda: fxl_cached('sonya'), kiss=lambda: kiss_path('sonya')),   # her kiss over his head: an object
    KANO_ID: dict(taps=CAP_FATALS['kano']['taps'], gap=CAP_FATALS['kano']['gap'],
                  table=lambda: cap_table('kano'), hoff=lambda: cap_hoff('kano'), music='f_time_kn',
                  head_base=lambda: 0, heads=False, move=True, bleed=False),
    RAIDEN_ID: dict(taps=CAP_FATALS['raiden']['taps'], gap=CAP_FATALS['raiden']['gap'],
                    table=lambda: cap_table('raiden'), hoff=lambda: cap_hoff('raiden'), music='f_time_rd',
                    head_base=lambda: _head_base('raiden'), heads=False,    # (the head explodes)
                    fxl=lambda: fxl_cached('raiden')),     # his lightning beyond his frame: an object
}


def emit_kiss(a, F):
    """gq_kiss (a1 = her, the winner; d0 = the row's word, kept): her kiss over his
    head while it's off MK's screen (kiss_path) - an object showing her effect sheet's
    kiss piece (fxl_pieces) at the row's place; hidden otherwise. As the fxl object."""
    a.label('gq_kiss')
    a.w(0x48E7, 0xC090)                  # movem.l d0-d1/a0/a3,-(sp)
    a.pcrel(0x41FA, 'gq_obj')            # lea gq_obj(pc),a0   (its own: on player 2's side
    a.w(0x2210)                          # move.l (a0),d1       the head slot holds another object)
    a.bccw(0x66, 'gq_have')
    a.w(0x0C40, 0x8000)                  # cmpi.w #$8000,d0   kiss markers are $8000..$80FF;
    a.bccw(0x65, 'gq_out')               # bcs: none wanted
    a.w(0x0C40, 0x8100)                  # real frames can have bit 15 set too
    a.bccw(0x64, 'gq_out')               # bcc: a real frame, not a kiss marker
    a.w(0x48E7, 0xFFFE)                  # movem.l d0-d7/a0-a6,-(sp)
    a.bccw(0x61, 'pl_tail')              # bsr pl_tail         a0 = her tail (a1 = her)
    a.w(0xD0FC, SZF_TAIL.get('fxl', 0))  # adda.w #pieces,a0
    src = GEN_TAIL.get('fx_src', 0)
    a.w(0x45F9); a.l(0xD448 + 8 * src)   # lea $D448+src*8,a2  its source entry
    a.w(0x222E, (-0x67D0 + 4 * src) & 0xFFFF)   # move.l -$67D0+src*4(a6),d1  its VRAM block
    a.bcc(0x67, 'gq_noup')
    a.w(0x2241)                          # movea.l d1,a1
    a.w(0x2251)                          # movea.l (a1),a1     VRAM address
    a.w(0x3012)                          # move.w (a2),d0      kind
    a.w(0x323C, len(F['fxl']()[0][2]))   # move.w #size,d1     (the kiss's tiles alone)
    a.jsr(0xC760)
    a.label('gq_noup')
    a.w(0x4CDF, 0x7FFF)                  # movem.l (sp)+,d0-d7/a0-a6
    a.w(0x48E7, 0xFFFE)                  # movem.l d0-d7/a0-a6,-(sp)
    a.w(0x2A49)                          # movea.l a1,a5       her: its owner
    a.pcrel(0x43FA, 'gk_hdesc')          # lea desc(pc),a1
    a.w(0x303C, PJ_TYPE)                 # move.w #type,d0
    a.w(0x7600)                          # moveq #0,d3
    a.jsr(0x6BBA)
    a.bccw(0x65, 'gq_none')              # bcs: no object free
    a.pcrel(0x43FA, 'gq_obj')            # lea gq_obj(pc),a1
    a.w(0x2288)                          # move.l a0,(a1)      the object
    a.pcrel(0x43FA, 'gk_park')           # lea park(pc),a1
    a.w(0x2468, 0x0088)                  # movea.l $88(a0),a2
    a.w(0x2549, 0x0004)                  # move.l a1,4(a2)     its task: parked
    a.w(0x316D, 0x001E, 0x001E)          # move.w $1E(a5),$1E(a0)  her palette line
    a.w(0x317C, 0xFF00, 0x0052)          # move.w #-256,$52(a0) off screen
    a.label('gq_none')
    a.w(0x4CDF, 0x7FFF)                  # movem.l (sp)+,d0-d7/a0-a6
    a.pcrel(0x41FA, 'gq_obj')            # lea gq_obj(pc),a0   (shown at once)
    a.w(0x2210)                          # move.l (a0),d1
    a.bccw(0x67, 'gq_out')
    a.label('gq_have')
    a.w(0x2641)                          # movea.l d1,a3       the object
    a.w(0x0C40, 0x8000)                  # only $8000..$80FF names a kiss position
    a.bcc(0x65, 'gq_hide')               # bcs: no marker
    a.w(0x0C40, 0x8100)
    a.bcc(0x64, 'gq_hide')               # bcc: actual victim frame
    a.w(0x0240, 0x7FFF)                  # andi.w #$7FFF,d0    its place
    a.w(0x377C, fr_fx(F['head_base']()), 0x001A)   # move.w #sheet:kiss,$1A(a3)
    a.w(0x3769, 0x0020, 0x0020)          # move.w $20(a1),$20(a3)  her facing
    a.w(0xE548)                          # lsl.w #2,d0
    a.pcrel(0x41FA, 'gq_pos')            # lea places(pc),a0
    a.w(0xD0C0)                          # adda.w d0,a0
    a.w(0x3228, 0x0002)                  # move.w 2(a0),d1     dy from her feet
    a.w(0xD269, 0x0052)                  # add.w $52(a1),d1
    a.w(0x3741, 0x0052)                  # move.w d1,$52(a3)
    a.w(0x3010)                          # move.w (a0),d0      dx, her way round
    a.w(0x0829, 0x0003, 0x0020)          # btst #3,$20(a1)
    a.bcc(0x67, 'gq_r')
    a.w(0x4440)                          # neg.w d0
    a.label('gq_r')
    a.w(0xD069, 0x004E)                  # add.w $4E(a1),d0
    a.w(0x3740, 0x004E)                  # move.w d0,$4E(a3)
    a.bcc(0x60, 'gq_out')
    a.label('gq_hide')                   # landed: gone (EC's object delete, as its own effects do:
    a.w(0x48E7, 0xFFFE)                  #  kept hidden, player 2's victim never burnt - a hang)
    a.w(0x204B)                          # movea.l a3,a0
    a.w(0x08E8, 0x0002, 0x0082)          # bset #2,$82(a0): EC's delete (its object loop
                                         #  unlinks it, frees it and its task; API $6A14 is
                                         #  the palette-task free, not this: notes)
    a.pcrel(0x41FA, 'gq_obj')            # lea gq_obj(pc),a0
    a.w(0x4290)                          # clr.l (a0)
    a.w(0x4CDF, 0x7FFF)                  # movem.l (sp)+,d0-d7/a0-a6
    a.label('gq_out')
    a.w(0x4CDF, 0x0903)                  # movem.l (sp)+,d0-d1/a0/a3
    a.w(0x4E75)
    a.label('gq_pos')
    for _, (dx, dy) in sorted(F['kiss']().items()):
        a.w(dx & 0xFFFF, dy & 0xFFFF)
    a.label('gq_obj')
    a.l(0)                               # the kiss object (cleared at the fatality's start)


def emit_gkok(a):
    """'gkok' (from emit_gfatal's idle check: a1 = the winner, a2 = his vars; uses d0/a0): Z set when his
    fatality may start - he isn't being thrown (a hit out of her daze leaves her fighting on at 1 health;
    Kano's input, mashed while she threw him, started his fatality mid-throw: her throw cut, he hung
    thrown for ever, a Contest never ended), nor hit or knocked down, and the loser (52(a2)) is dazed or
    being hit (by his last press) - not out of her daze and fighting: Kano's input (back taps once
    crossed over) went through while Larcen, out of his daze, knocked him down; the fatality loaded
    Larcen's death art over his .PL, Larcen fought on and EC drew his next frame from it - a Contest
    froze, the sub CPU in Word RAM. In the second victory room (room_put)."""
    if 'gkok' in a.labels or any(l == 'gkok' for l, _, _ in getattr(a, 'late', [])):
        return
    r = Asm(0)
    r.w(0x1029, 0x00BF)                  # move.b $BF(a1),d0   his state's low byte
    r.w(0x0C00, THROWN)                  # cmpi.b #$37,d0      thrown
    r.bcc(0x67, 'ko_n')
    r.w(0x0400, HIT_FIRST)               # subi.b #$1A,d0
    r.w(0x0C00, HIT_LAST - HIT_FIRST)    # cmpi.b #3,d0
    r.bcc(0x63, 'ko_n')                  # bls: hit / knocked down
    r.w(0x206A, 0x0034)                  # movea.l 52(a2),a0   the loser
    r.w(0x1028, 0x00BF)                  # move.b $BF(a0),d0
    r.w(0x0C00, DIZZY)                   # cmpi.b #$1F,d0      dazed
    r.bcc(0x67, 'ko_y')
    r.w(0x0400, HIT_FIRST)               # subi.b #$1A,d0
    r.w(0x0C00, HIT_LAST - HIT_FIRST)    # cmpi.b #3,d0
    r.bcc(0x62, 'ko_n')                  # bhi: neither - she fights on
    r.label('ko_y')
    r.w(0x7000)                          # moveq #0,d0         (Z)
    r.w(0x4E75)
    r.label('ko_n')
    r.w(0x7001)                          # moveq #1,d0
    r.w(0x4E75)
    room_put(a, 'gkok', r.build())


def emit_gkbutton(a, F):
    """Z clear if his fatality's button is down (d2: his buttons, new or held; d1 used): a punch, either
    (MK CD: LP and HP both - EC X, Y); Sonya's: Block (EC Z, 'button_bit')."""
    if 'button_bit' in F:
        a.w(0x0802, F['button_bit'])     # btst #bit,d2
    else:
        a.w(0x3202)                      # move.w d2,d1
        a.w(0x0241, PUNCH)               # andi.w #X+Y,d1


def emit_gfatal(a):
    """In r_generic (a1 = him, a2 = vars; vars as Scorpion's: +24 running,
    +26 row, +28 calls in it, +30 him, +34 the loser, +38 her frame, +40 tap
    step, +42 its window, +52 the FINISH HIM loser). Branches to g_out while
    it runs (his other per-frame work stops). His recipe: FATALS[his id]."""
    F = FATALS[SCORPION_ID]
    a.w(0x4A6A, 0x0018)                  # tst.w 24(a2)        running?
    a.bccw(0x67, 'gk_idle')
    a.w(0x41EE, 0x0A3A)                  # lea $A3A(a6),a0     his pad reads nothing
    a.w(0xB3FC); a.l(0x2E188)            # cmpa.l #P1,a1
    a.bcc(0x67, 'gk_p1')
    a.w(0x5488)                          # addq.l #2,a0
    a.label('gk_p1')
    a.w(0x4250)                          # clr.w (a0)
    a.bccw(0x61, 'gk_step')
    a.bccw(0x60, 'g_out')
    a.label('gk_idle')
    # the taps: directions held now or a frame ago (EC's reader keeps that pad 8 bytes on) that
    # weren't at his last call (+44: kept every call). This runs every other frame, at times every
    # third, and EC shows a quick tap for a frame or two: by EC's new presses ($162) alone a
    # 3-frame tap was lost at 1 timing in 7
    a.w(0x41EE, 0x0A3A)                  # lea $A3A(a6),a0     his pad (player 1's ...
    a.w(0xB3FC); a.l(0x2E188)            # cmpa.l #P1,a1
    a.bcc(0x67, 'gk_tp1')
    a.w(0x5488)                          # addq.l #2,a0        ... or 2's)
    a.label('gk_tp1')
    a.w(0x3210)                          # move.w (a0),d1
    a.w(0x8268, 0x0008)                  # or.w 8(a0),d1       and a frame ago
    a.w(0x302A, 0x002C)                  # move.w 44(a2),d0    at his last call
    a.w(0x3541, 0x002C)                  # move.w d1,44(a2)
    a.w(0x4640)                          # not.w d0
    a.w(0xC240)                          # and.w d0,d1         new since (gkok keeps d1)
    a.w(0x4AAA, 0x0034)                  # tst.l 52(a2)        only in his FINISH HIM window
    a.bccw(0x67, 'gk_x')
    emit_gkok(a)
    a.bccw(0x61, 'gkok')                 # bsr.w gkok          (both free to start it: thrown, hit, out of her daze)
    a.bccw(0x66, 'gk_x')                 # bne: not now
    a.w(0x3429, 0x0162)                  # move.w $162(a1),d2  buttons: new presses,
    a.w(0x846A, 0x002C)                  # or.w 44(a2),d2      or held (now or a frame ago)
    a.w(0x3001)                          # move.w d1,d0
    a.w(0x0240, 0x000F)                  # andi.w #$F,d0       taps, his way round:
    a.w(0x0829, 0x0003, 0x0020)          # btst #3,$20(a1)
    a.bcc(0x67, 'gk_nf')
    a.w(0x3600)                          # move.w d0,d3
    a.w(0x0243, 0x000C)                  # andi.w #$C,d3
    a.bcc(0x67, 'gk_nf')
    a.w(0x0A40, 0x000C)                  # eori.w #$C,d0
    a.label('gk_nf')
    a.w(0x4A6A, 0x002A)                  # tst.w 42(a2)        window
    a.bcc(0x67, 'gk_rst')
    a.w(0x536A, 0x002A)                  # subq.w #1,42(a2)
    a.bcc(0x66, 'gk_go')
    a.label('gk_rst')
    a.w(0x426A, 0x0028)                  # clr.w 40(a2)        step 0
    a.label('gk_go')
    a.w(0x362A, 0x0028)                  # move.w 40(a2),d3
    a.w(0x0C43, len(F['taps']))          # cmpi.w #3,d3
    a.bcc(0x67, 'gk_btn')
    if F['taps'][-1] in (FWD, BACK):     # (a horizontal last tap)
        # the last tap pressed together with the button (MK: forward + high punch):
        # EC reads that press as its throw, so take the direction from the held pad
        a.w(0x0C43, len(F['taps']) - 1)      # cmpi.w #2,d3
        a.bcc(0x66, 'gk_ntb')
        emit_gkbutton(a, F)                  # the button now
        a.bcc(0x67, 'gk_ntb')
        a.w(0x41EE, 0x0A3A)                  # lea $A3A(a6),a0     his held pad
        a.w(0xB3FC); a.l(0x2E188)            # cmpa.l #P1,a1
        a.bcc(0x67, 'gk_hp1')
        a.w(0x5488)                          # addq.l #2,a0
        a.label('gk_hp1')
        a.w(0x3210)                          # move.w (a0),d1
        a.w(0x0241, 0x000C)                  # andi.w #$C,d1       left or right held: the pad word read
        a.bccw(0x66, 'gk_btn')               #  in the frame Y goes down has it the wrong way round (6-button
                                             #  read), the next frame right: either counts
        a.label('gk_ntb')
    a.w(0x4A40)                          # tst.w d0            a tap this call?
    a.bccw(0x67, 'gk_x')
    a.pcrel(0x41FA, 'gk_seq')            # lea seq(pc),a0
    a.w(0xD643)                          # add.w d3,d3
    a.w(0xB070, 0x3000)                  # cmp.w (a0,d3.w),d0  the one due?
    a.bcc(0x67, 'gk_tok')
    a.w(0x426A, 0x0028)                  # clr.w 40(a2)        wrong: from the start
    a.bccw(0x60, 'gk_x')
    a.label('gk_tok')
    a.w(0x526A, 0x0028)                  # addq.w #1,40(a2)
    a.w(0x357C, 12, 0x002A)              # move.w #12,42(a2)   the next within 12 calls
    a.w(0x0C6A, len(F['taps']), 0x0028)  # cmpi.w #3,40(a2)    the last tap: its button may come with it
    a.bccw(0x66, 'gk_x')
    a.label('gk_btn')
    if F.get('button', 'y'):             # (Liu Kang's has none: the taps do it)
        emit_gkbutton(a, F)
        a.bccw(0x67, 'gk_x')
    a.w(0x266A, 0x0034)                  # movea.l 52(a2),a3   the loser (dazed - or hit inside the
                                         #  window by his last press: r_finish keeps her on 1)
    if UP in F['taps']:                  # an Up in his input is EC's jump: start once he has landed
        a.w(0x302E, 0x1496)              # move.w $1496(a6),d0 the floor (not hers: Blast's daze sinks
                                         #  him 7 px, and Liu Kang never 'landed' on him)
        a.w(0x5540)                      # subq.w #2,d0
        a.w(0xB069, 0x0052)              # cmp.w $52(a1),d0
        a.bcc(0x6F, 'gk_land')           # ble: he's down
        a.w(0x357C, 12, 0x002A)          # move.w #12,42(a2)   still in the air: keep the input, wait
        a.bccw(0x60, 'gk_x')
        a.label('gk_land')
    a.w(0x426A, 0x0028)                  # clr.w 40(a2)
    a.w(0x42AA, 0x0034)                  # clr.l 52(a2)        FINISH HIM is over
    a.w(0x357C, 0x0001, 0x0018)          # move.w #1,24(a2)    start
    a.w(0x426A, 0x001A)                  # clr.w 26(a2)
    a.w(0x426A, 0x001C)                  # clr.w 28(a2)
    a.w(0x2549, 0x001E)                  # move.l a1,30(a2)
    a.w(0x254B, 0x0022)                  # move.l a3,34(a2)
    a.w(0x356B, 0x001A, 0x0026)          # move.w $1A(a3),38(a2)
    a.w(0x426B, 0x00BE)                  # clr.w $BE(a3)       not dazed now: an MK loser's own block
                                         #  (Scorpion's wobble) must not pick her frames either
    a.w(0x426B, 0x015E)                  # clr.w $15E(a3)      and EC's daze loop ended: while it counts,
                                         #  EC's stepper (PLYR $182B4) puts her script back to her daze
                                         #  ($15A) - her own frames, from a .PL her death art replaced: a
                                         #  CPU loser's (its AI re-dazes her: $15E = 100) killed the game
    # her script held too: her art is about to be overwritten (gk_load), so
    # a step of hers must never pick another of her own frames (EC steps a
    # fighter's script outside the move task we park)
    a.bccw(0x61, 'gk_face')              # she faces him
    a.w(0x302B, 0x001A)                  # move.w $1A(a3),d0
    a.bccw(0x61, 'gk_hset')              # bsr gk_hset         her hold steps show d0
    a.w(0x5888)                          # addq.l #4,a0
    a.w(0x2748, 0x00AE)                  # move.l a0,$AE(a3)   (PLYR $18174: $AE = the step)
    a.w(0x426B, 0x00C2)                  # clr.w $C2(a3)       steps taken: its end never comes
    a.w(0x377C, 0x0002, 0x00C4)          # move.w #2,$C4(a3)   (two stepper tasks: 3 copies)
    a.pcrel(0x41FA, 'gk_hold')           # lea hold(pc),a0     his own script held
    a.w(0x5888)                          # addq.l #4,a0
    a.w(0x2348, 0x00AE)                  # move.l a0,$AE(a1)
    a.w(0x337C, fr(0x4000), 0x001A)      # move.w #stance,$1A(a1)  at once (not the pose the input left
                                         #  him in: a crouch from a down tap) - his stance while it darkens
    a.pcrel(0x41FA, 'gk_z')              # lea gk_z(pc),a0     no death art yet
    a.w(0x4250)                          # clr.w (a0)
    a.w(0x42A8, 0x0002)                  # clr.l 2(a0)         no head object
    if SCORPION_ID == RAIDEN_ID:
        a.pcrel(0x41FA, 'gr_flash_count')
        a.w(0x4250)                      # new fatality, restart flash timeline
    if F.get('kiss'):
        a.pcrel(0x41FA, 'gq_obj')        # lea gq_obj(pc),a0
        a.w(0x4290)                      # clr.l (a0)          no kiss object
    for obj, task in ((0x2069, 'gk_park'), (0x206B, 'gk_load')):   # his move task parked,
        a.pcrel(0x49FA, task)            # lea task(pc),a4     hers loads her death art
        a.w(obj, 0x0088)
        a.w(0x2050)
        a.w(0x214C, 0x0004)
        a.w(0x4268, 0x0008)
    a.w(0x3029, 0x00B2)                  # move.w $B2(a1),d0   she, his gap in front of him
    a.w(0x362B, 0x00B2)
    a.w(0xB640)
    a.bcc(0x6C, 'gk_r')
    a.w(0x0440, F['gap'])
    a.bcc(0x60, 'gk_sx')
    a.label('gk_r')
    a.w(0x0640, F['gap'])
    a.label('gk_sx')
    for o in POS_X_ALL:
        a.w(0x3740, o)                   # move.w d0,o(a3)
    for o in (0xC6, 0x5E):               # no sliding
        a.w(0x42AB, o)
        a.w(0x42A9, o)
    a.bccw(0x61, 'gk_dark')              # (the music: once her art is in, gk_load)
    a.bccw(0x60, 'gk_x')
    # the stage's palette lines halved (as Scorpion's f_dark)
    a.label('gk_dark')
    a.w(0x7400)
    a.label('gkd_l')
    for reg in (0x3029, 0x302B):         # skip his line and hers
        a.w(reg, 0x007A)
        a.w(0x0240, 0x0003)
        a.w(0x0A40, 0x0001)
        a.w(0xB042)
        a.bcc(0x67, 'gkd_n')
    a.w(0x49EE, PAL_BUF & 0xFFFF)
    a.w(0x3002)
    a.w(0xEB48)
    a.w(0xD8C0)
    a.w(0x700F)
    a.label('gkd_c')
    a.w(0x3614); a.w(0xE24B); a.w(0x0243, 0x0EEE); a.w(0x38C3)
    a.dbra(0, 'gkd_c')
    a.label('gkd_n')
    a.w(0x5242)
    a.w(0x0C42, 0x0004)
    a.bcc(0x6D, 'gkd_l')
    a.w(0x3D7C, 0xFFFF, PAL_DIRTY & 0xFFFF)
    a.w(0x4E75)
    # one timeline call (as Scorpion's f_step / f_end / f_kill / f_pal)
    a.label('gk_step')
    a.w(0x206A, 0x0022)                  # movea.l 34(a2),a0   her daze loop kept ended every frame: a
    a.w(0x4268, 0x015E)                  # clr.w $15E(a0)       CPU's AI or a boss re-dazes her (Eternal)
    # no move of hers starts while it plays: a CPU loser's request ($BE bit 15, with $100
    # bit 0) made EC start her own move - her own frames, from a .PL her death art replaced
    a.w(0x0828, 0x0007, 0x00BE)          # btst #7,$BE(a0)
    a.bcc(0x67, 'gk_nrq')
    a.w(0x4268, 0x00BE)                  # clr.w $BE(a0)
    a.w(0x08A8, 0x0000, 0x0101)          # bclr #0,$101(a0)
    a.label('gk_nrq')
    a.bccw(0x61, 'gk_tail')              # the timeline: in his .PL's tail
    a.w(0x2848)                          # movea.l a0,a4
    a.w(0x342A, 0x001A); a.w(0xE74A); a.w(0xD8C2)
    a.w(0x4A54)
    a.bccw(0x67, 'gk_end')
    a.w(0x526A, 0x001C); a.w(0x362A, 0x001C); a.w(0xB654)
    a.bcc(0x6D, 'gk_ap')
    a.w(0x426A, 0x001C); a.w(0x526A, 0x001A); a.w(0x504C)
    a.w(0x4A54)
    a.bccw(0x67, 'gk_end')
    a.label('gk_ap')
    if SCORPION_ID == RAIDEN_ID:
        a.bccw(0x61, 'gr_flash')        # MK's four blue flashes and the explosion
    a.w(0x362C, 0x0002)
    a.bcc(0x67, 'gk_ns')
    a.w(0x3343, 0x001A)                  # his frame
    a.pcrel(0x41FA, 'gk_hold')           # lea hold(pc),a0     ... and his hold steps the same (EC's
    a.w(0x3143, 0x0004)                  # move.w d3,4(a0)      stepper re-applies them when his jump -
    a.w(0x3143, 0x0010)                  # move.w d3,16(a0)     Liu Kang's input has an Up - lands)
    a.w(0x3143, 0x001C)                  # move.w d3,28(a0)
    a.label('gk_ns')
    a.bccw(0x61, 'gk_head')              # her head where he holds it
    a.w(0x266A, 0x0022)
    a.bccw(0x61, 'gk_face')              # she faces him, whatever steps her script takes
    a.w(0x362C, 0x0004)                  # move.w 4(a4),d3     her death frame + 1
    a.bcc(0x67, 'gk_ret')
    a.pcrel(0x41FA, 'gk_z')              # lea gk_z(pc),a0
    a.w(0x3010)                          # move.w (a0),d0      her death sheet (- $100)
    a.bcc(0x67, 'gk_ret')                # none: she keeps her frame
    a.w(0x0803, 0x0007)                  # btst #7,d3          $80: a frame of sheet 1 (the air pose, lying)
    a.bcc(0x67, 'gk_s2')
    a.w(0x3028, 0x0008)                  # move.w 8(a0),d0     sheet 1
    a.w(0x0243, 0x007F)                  # andi.w #$7F,d3
    a.label('gk_s2')
    a.w(0xE148)                          # lsl.w #8,d0
    a.w(0xD043)                          # add.w d3,d0
    a.w(0x5340)                          # subq.w #1,d0
    a.w(0x3740, 0x001A)                  # move.w d0,$1A(a3)   her own object, her own colours
    a.bccw(0x61, 'gk_hset')              # (her hold steps: the same frame)
    a.w(0x377C, 0x0001, 0x0028)          # move.w #1,$28(a3)   (sheets $100+)
    if F.get('bleed', True):            # (a decapitation: her neck bleeds)
        # blood from her neck at each timeline step (MK's droplets, his palette's red)
        a.pcrel(0x41FA, 'gk_bc')             # lea count(pc),a0    a steady flow: every SZF_FLOW calls
        a.w(0x5250)                          # addq.w #1,(a0)
        a.w(0x3010)                          # move.w (a0),d0
        a.w(0x0240, SZF_FLOW - 1)            # andi.w #flow-1,d0
        a.bccw(0x66, 'gk_ret')
        a.w(0x3003)                          # move.w d3,d0
        a.w(0x5340)                          # subq.w #1,d0        her death frame
        a.w(0x0C40, SZF_BLEED)               # cmpi.w #bleed,d0
        a.bccw(0x64, 'gk_ret')
        a.w(0xD040, 0xD040)                  # add.w d0,d0 (x2)
        a.pcrel(0x41FA, 'gk_neck')           # lea neck(pc),a0
        a.w(0xD0C0)                          # adda.w d0,a0
        a.w(0x3218)                          # move.w (a0)+,d1     dx
        a.w(0x082B, 0x0003, 0x0020)          # btst #3,$20(a3)     her art mirrored?
        a.bcc(0x67, 'gk_nr')
        a.w(0x4441)                          # neg.w d1
        a.label('gk_nr')
        a.w(0xD26B, 0x004E)                  # add.w $4E(a3),d1
        a.w(0x3D41, 0x1444)                  # move.w d1,$1444(a6) the 'hit point'
        a.w(0x3210)                          # move.w (a0),d1      dy
        a.w(0xD26B, 0x0052)                  # add.w $52(a3),d1
        a.w(0x3D41, 0x1446)                  # move.w d1,$1446(a6)
        a.w(0x2F0D)                          # move.l a5,-(sp)
        a.w(0x2A49)                          # movea.l a1,a5       (him: the 'attacker', his red)
        a.jsr(SUB_AT.get('blood', 0))        # jsr blood (SUB.BIN)
        a.w(0x2A5F)                          # movea.l (sp)+,a5
    a.label('gk_ret')
    a.w(0x4E75)
    a.label('gk_end')
    a.w(0x426A, 0x0018)
    a.w(0x266A, 0x0022)
    a.w(0x426B, 0x0076)                  # no health left
    a.w(0x2069, 0x0088); a.w(0x2050)
    a.pcrel(0x47FA, 'gk_kill')
    a.w(0x214B, 0x0004); a.w(0x4268, 0x0008)
    a.w(0x4E75)
    a.label('gk_kill')                   # his move task: EC's finisher ending (as f_kill)
    a.jsr(0x6D28)
    a.w(0x266D, 0x008C)
    a.w(0x08EB, 0x0007, 0x0082)          # she stays drawn
    a.w(0x3D7C, 0x0003, 0x1CD4)          # a finisher won the round
    for _ in range(1 + GK_HOLD):         # (the scene held while MK's announcer speaks: its
        a.w(0x7000 | FAT_PAUSE)          #  '<NAME> WINS' comes ~9 s into the fatality music, in
        a.jsr(0x68D6)                    #  mkfatalsound's recording; the round's end stops the CD)
    a.w(0x08EE, 0x0000, 0x0AB7)
    a.w(0x08EE, 0x0001, 0x0AB7)          # round over
    a.bccw(0x60, 'gk_park')
    a.label('gk_park')
    a.w(0x7001)
    a.jsr(0x68D6)
    a.bcc(0x60, 'gk_park')
    a.label('gk_hold')
    for _ in range(3):                   # (two stepper tasks may each take a step)
        a.w(0x0000, 0x0000, fr(SZF_HIS_SLOTS[0]), 0x7FFF, 0x0000, 0x0000)
    a.label('gk_seq')
    for t in F['taps']:
        a.w(t)
    # a0 = his .PL's tail (a1 = him): P1's .PL is in Word RAM at $81800, P2's at $51800
    a.label('gk_tail')
    a.bccw(0x61, 'pl_tail')              # bsr pl_tail
    a.w(0xD0FC, SZF_TAIL.get('off', 0))  # adda.w #fatality data,a0
    a.w(0x4E75)
    # her move task (a5 = her): EC's loader puts her Z<xx>.BIN over her own .PL
    # (her art isn't drawn again: she holds her frame, then shows the death
    # art), as the Chicago Theater's Sudden Death does at $7C000
    a.label('gk_load')
    a.w(0x226D, 0x008C)                  # movea.l $8C(a5),a1  him
    if F.get('burn'):                    # (her frames come from his art: no death art loaded)
        a.bccw(0x60, 'gl_mus')
    a.bccw(0x61, 'gk_tail')
    a.w(0xD0FC, SZF_TAIL.get('ztab', 0)) # adda.w #ztab,a0
    a.w(0x7000)                          # moveq #0,d0
    a.w(0x302D, 0x004C)                  # move.w $4C(a5),d0   her id
    a.w(0x5540)                          # subq.w #2,d0
    a.w(0x0C40, 0x0019)                  # cmpi.w #25,d0
    a.bccw(0x64, 'gl_mus')               # bcc: not a fighter id
    a.w(0xE548)                          # lsl.w #2,d0         x4
    a.w(0xD0C0)                          # adda.w d0,a0        her entry (szf_ztab)
    a.pcrel(0x43FA, 'gk_z')              # lea gk_z(pc),a1
    a.w(0x7000)                          # moveq #0,d0
    a.w(0x1028, 0x0003)                  # move.b 3(a0),d0     sheet 1 - $100
    a.w(0x3340, 0x0008)                  # move.w d0,8(a1)
    a.w(0x7000)                          # moveq #0,d0
    a.w(0x1010)                          # move.b (a0),d0      head + 1
    a.bccw(0x67, 'gl_mus')               # no death art
    a.w(0x3F00)                          # move.w d0,-(sp)
    a.w(0x7000)                          # moveq #0,d0
    a.w(0x1028, 0x0002)                  # move.b 2(a0),d0     sheet 2 - $100
    a.w(0x3F00)                          # move.w d0,-(sp)
    a.w(0x7000)                          # moveq #0,d0
    a.w(0x1028, 0x0001)                  # move.b 1(a0),d0     file id
    a.w(0x3200, 0xD241, 0xD241)          # move.w d0,d1 / add.w d1,d1 (x2)
    a.w(0x3F01)                          # move.w d1,-(sp)
    a.w(0x41EE, 0x8CB4)                  # lea -$734C(a6),a0   EC's loaded-file list:
    a.w(0x42B0, 0x1000)                  # clr.l (a0,d1.w)     read it again
    a.w(0x223C); a.l(0x51800)            # move.l #$51800,d1   her .PL
    a.w(0xBBFC); a.l(0x2E188)            # cmpa.l #P1,a5
    a.bcc(0x66, 'gl_p2')
    a.w(0x226D, 0x008C)                  # movea.l $8C(a5),a1  (a mirror match: one .PL, at $81800,
    a.w(0x3069, 0x004C)                  # movea.w $4C(a1),a0   his too - the free $51800 then;
    a.w(0xB0ED, 0x004C)                  # cmpa.w $4C(a5),a0    d0 is the file id: kept)
    a.bcc(0x67, 'gl_p2')
    a.w(0x223C); a.l(0x81800)            # move.l #$81800,d1
    a.label('gl_p2')
    a.w(0x2D41, 0x9190)                  # move.l d1,-$6E70(a6)  load there
    a.jsr(0x6C26)                        # EC's file load (CD read, chunks registered)
    a.w(0x42AE, 0x9190)                  # clr.l -$6E70(a6)
    a.w(0x321F)                          # move.w (sp)+,d1
    a.w(0x41EE, 0x8CB4)                  # lea -$734C(a6),a0
    a.w(0x42B0, 0x1000)                  # clr.l (a0,d1.w)     (not in EC's list: nothing frees it)
    a.w(0x301F)                          # move.w (sp)+,d0     sheet 2 - $100
    a.w(0x341F)                          # move.w (sp)+,d2     head + 1
    a.w(0x5342)                          # subq.w #1,d2        her head (gk_head)
    a.pcrel(0x41FA, 'gk_z')              # lea gk_z(pc),a0
    a.w(0x3080)                          # move.w d0,(a0)
    a.w(0x3142, 0x0006)                  # move.w d2,6(a0)     her head
    a.label('gl_mus')
    a.pcrel(0x41FA, F['music'])          # lea f_time_..(pc),a0  MK's fatality music + its sounds (after the read:
    a.bccw(0x61, 'f_music')              #  a CD read stops CD audio)
    a.bccw(0x60, 'gk_park')
    # she (a3) faces him (a1): her $20 bit 11, and $100's (EC's stepper sets $20's
    # from its step's $F6 ^ $100 on each step: her hold steps have $F6 = 0)
    a.label('gk_face')
    a.w(0x48E7, 0xC000)                  # movem.l d0-d1,-(sp)
    a.w(0x7200)                          # moveq #0,d1         face right ...
    a.w(0x3029, 0x004E)                  # move.w $4E(a1),d0
    a.w(0xB06B, 0x004E)                  # cmp.w $4E(a3),d0
    a.bcc(0x6C, 'gf_r')                  # bge: he's on her right
    a.w(0x323C, 0x0800)                  # move.w #$800,d1     ... or left
    a.label('gf_r')
    if SZF_ZFLIP:
        a.w(0x4A6B, 0x0028)              # tst.w $28(a3)       her death art: the other way
        a.bcc(0x67, 'gf_z')
        a.w(0x0A41, 0x0800)              # eori.w #$800,d1
        a.label('gf_z')
    a.w(0x026B, 0xF7FF, 0x0020)          # andi.w #$F7FF,$20(a3)
    a.w(0x836B, 0x0020)                  # or.w d1,$20(a3)
    a.w(0x026B, 0xF7FF, 0x0100)          # andi.w #$F7FF,$100(a3)
    a.w(0x836B, 0x0100)                  # or.w d1,$100(a3)
    a.w(0x4CDF, 0x0003)                  # movem.l (sp)+,d0-d1
    a.w(0x4E75)
    a.label('gk_hset')                   # a0 = her hold steps, both showing d0
    # and her hit's restore: EC's hit stun (Blade's module $13BE, a task of hers) sleeps, then puts
    # back the frame she had ($A4) - woken mid-fatality (a Contest: 130 frames after Kano's last
    # hit) it showed 87:01 after gk_load's art had overwritten her .PL: EC unpacked garbage over
    # its stack and the sub CPU crashed. Her held frame there instead: the restore changes nothing
    a.w(0x3740, 0x00A4)                  # move.w d0,$A4(a3)   (a3 = her at every call)
    a.pcrel(0x41FA, 'gk_hs')             # lea gk_hs(pc),a0
    a.w(0x3140, 0x0004)                  # move.w d0,4(a0)
    a.w(0x3140, 0x0010)                  # move.w d0,16(a0)
    a.w(0x3140, 0x001C)                  # move.w d0,28(a0)
    a.w(0x4E75)
    a.label('gk_hs')
    for _ in range(3):
        a.w(0x0000, 0x0000, 0x0000, 0x7FFF, 0x0000, 0x0000)
    # her head at his hand (a1 = him): his held slot -> offset from his feet
    a.label('gk_head')
    if F.get('move'):                    # her position from the row (a flying victim: Liu Kang's uppercut)
        a.w(0x48E7, 0xC090)              # movem.l d0-d1/a0/a3,-(sp)
        a.w(0x266A, 0x0022)              # movea.l 34(a2),a3   her
        a.w(0x302C, 0x0006)              # move.w 6(a4),d0     position + 1
        a.bcc(0x67, 'gp_out')
        a.w(0x5340)                      # subq.w #1,d0
        a.w(0xE548)                      # lsl.w #2,d0
        a.bccw(0x61, 'gk_tail')          # bsr gk_tail
        a.w(0xD0FC, SZF_TAIL.get('hoff', 0))   # adda.w #positions,a0
        a.w(0xD0C0)                      # adda.w d0,a0
        a.w(0x3228, 0x0002)              # move.w 2(a0),d1     dy
        a.w(0xD269, 0x0052)              # add.w $52(a1),d1    from his feet
        for o in POS_Y:
            a.w(0x3741, o)               # move.w d1,o(a3)
        a.w(0x3010)                      # move.w (a0),d0      dx, his way round
        a.w(0x0829, 0x0003, 0x0020)      # btst #3,$20(a1)
        a.bcc(0x67, 'gp_r')
        a.w(0x4440)                      # neg.w d0
        a.label('gp_r')
        a.w(0xD069, 0x004E)              # add.w $4E(a1),d0
        for o in POS_X_ALL:
            a.w(0x3740, o)               # move.w d0,o(a3)
        a.label('gp_out')
        a.w(0x4CDF, 0x0903)              # movem.l (sp)+,d0-d1/a0/a3
        a.w(0x4E75)
    elif F.get('burn'):                  # the loser shows frames of HIS art in HIS colours (Sonya's kiss)
        a.w(0x48E7, 0xF0B0)              # movem.l d0-d3/a0/a2-a3,-(sp)
        a.w(0x266A, 0x0022)              # movea.l 34(a2),a3   her
        a.w(0x302C, 0x0006)              # move.w 6(a4),d0     a frame of his art (0: hers kept)
        if F.get('kiss'):                # ($8000 + n: none, her kiss at its n-th place)
            a.bccw(0x61, 'gq_kiss')      # bsr gq_kiss
            a.w(0x4A40)                  # tst.w d0
            a.bccw(0x67, 'gb_out')       # zero: keep the victim's own frame
            a.w(0x0C40, 0x8000)          # kiss markers are $8000..$80FF;
            a.bcc(0x65, 'gb_frame')      # lower nonzero values are real frames
            a.w(0x0C40, 0x8100)
            a.bccw(0x65, 'gb_out')       # bcs: marker, not a victim frame
            a.label('gb_frame')
        else:
            a.bcc(0x67, 'gb_out')
        # a player-1 victim's poses are unpacked by the main CPU ($2A bit 8: SUB
        # $1178E), which can't reach player 2's art in PRG RAM (garbage, or a
        # hang): with the winner player 2 they're unpacked here instead
        a.w(0xB3FC); a.l(0x2E330)        # cmpa.l #P2,a1
        a.bcc(0x66, 'gb_p1')
        a.w(0x08AB, 0x0000, 0x002A)      # bclr #0,$2A(a3)     (bit 8 of the word)
        a.label('gb_p1')
        a.w(0x3740, 0x001A)              # move.w d0,$1A(a3)
        a.w(0x426B, 0x0028)              # clr.w $28(a3)       (sheets below $100)
        a.bccw(0x61, 'gk_hset')          # her hold steps the same
        # in his colours: her sprites take his palette line ($20 bits 13-14), which
        # shows on the same frame as the pose (as Scorpion's f_p1v)
        a.w(0x3629, 0x0020)              # move.w $20(a1),d3
        a.w(0x0243, 0x6000)              # andi.w #$6000,d3
        a.w(0x026B, 0x9FFF, 0x0020)      # andi.w #$9FFF,$20(a3)
        a.w(0x876B, 0x0020)              # or.w d3,$20(a3)
        a.label('gb_out')
        a.w(0x4CDF, 0x0D0F)              # movem.l (sp)+,d0-d3/a0/a2-a3
        a.w(0x4E75)
        if F.get('kiss'):
            emit_kiss(a, F)
    elif F.get('fxl'):                   # his lightning beyond his frame (Raiden): an object showing
        a.w(0x48E7, 0xC090)              # movem.l d0-d1/a0/a3,-(sp)   the row's piece at its place
        a.w(0x302C, 0x0006)              # move.w 6(a4),d0     piece + 1 (0: none)
        a.pcrel(0x41FA, 'gk_z')          # lea gk_z(pc),a0
        a.w(0x2228, 0x0002)              # move.l 2(a0),d1     the object
        a.bccw(0x66, 'gl_have')
        a.w(0x4A40)                      # tst.w d0
        a.bccw(0x67, 'gl_out')           # (none yet, none wanted)
        a.w(0x48E7, 0xFFFE)              # movem.l d0-d7/a0-a6,-(sp)
        # the pieces' tiles over his effect sheet's in VRAM (his projectile's: not needed now)
        a.bccw(0x61, 'pl_tail')          # bsr pl_tail         a0 = his tail (a1 = him)
        a.w(0xD0FC, SZF_TAIL.get('fxl', 0))   # adda.w #pieces,a0
        src = GEN_TAIL.get('fx_src', 0)
        a.w(0x45F9); a.l(0xD448 + 8 * src)   # lea $D448+src*8,a2  its source entry
        a.w(0x222E, (-0x67D0 + 4 * src) & 0xFFFF)   # move.l -$67D0+src*4(a6),d1  its VRAM block
        a.bcc(0x67, 'gl_noup')
        a.w(0x2241)                      # movea.l d1,a1
        a.w(0x2251)                      # movea.l (a1),a1     VRAM address
        a.w(0x3012)                      # move.w (a2),d0      kind
        a.w(0x322A, 0x0006)              # move.w 6(a2),d1     size
        a.jsr(0xC760)
        a.label('gl_noup')
        a.w(0x4CDF, 0x7FFF)              # movem.l (sp)+,d0-d7/a0-a6
        a.w(0x48E7, 0xFFFE)              # movem.l d0-d7/a0-a6,-(sp)
        a.w(0x2A49)                      # movea.l a1,a5       him: its owner
        a.pcrel(0x43FA, 'gk_hdesc')      # lea desc(pc),a1
        a.w(0x303C, PJ_TYPE)             # move.w #type,d0
        a.w(0x7600)                      # moveq #0,d3
        a.jsr(0x6BBA)
        a.bccw(0x65, 'gl_none')          # bcs: no object free
        a.pcrel(0x43FA, 'gk_z')          # lea gk_z(pc),a1
        a.w(0x2348, 0x0002)              # move.l a0,2(a1)     the object
        a.pcrel(0x43FA, 'gk_park')       # lea park(pc),a1
        a.w(0x2468, 0x0088)              # movea.l $88(a0),a2
        a.w(0x2549, 0x0004)              # move.l a1,4(a2)     its task: parked
        a.w(0x316D, 0x001E, 0x001E)      # move.w $1E(a5),$1E(a0)  his palette line
        a.w(0x317C, 0xFF00, 0x0052)      # move.w #-256,$52(a0) off screen
        a.label('gl_none')
        a.w(0x4CDF, 0x7FFF)              # movem.l (sp)+,d0-d7/a0-a6
        a.bccw(0x60, 'gl_out')
        a.label('gl_have')
        a.w(0x2641)                      # movea.l d1,a3       the object
        a.w(0x4A40)                      # tst.w d0
        a.bcc(0x67, 'gl_hide')
        a.w(0x5340)                      # subq.w #1,d0
        a.w(0x3200)                      # move.w d0,d1
        a.w(0x0641, fr_fx(F['head_base']()))   # addi.w #sheet:first piece,d1
        a.w(0x3741, 0x001A)              # move.w d1,$1A(a3)   the piece
        a.w(0x3769, 0x0020, 0x0020)      # move.w $20(a1),$20(a3)  his facing
        a.w(0xE548)                      # lsl.w #2,d0
        a.pcrel(0x41FA, 'gl_pos')        # lea positions(pc),a0
        a.w(0xD0C0)                      # adda.w d0,a0
        a.w(0x3228, 0x0002)              # move.w 2(a0),d1     dy from his feet
        a.w(0xD269, 0x0052)              # add.w $52(a1),d1
        a.w(0x3741, 0x0052)              # move.w d1,$52(a3)
        a.w(0x3010)                      # move.w (a0),d0      dx, his way round
        a.w(0x0829, 0x0003, 0x0020)      # btst #3,$20(a1)
        a.bcc(0x67, 'gl_r')
        a.w(0x4440)                      # neg.w d0
        a.label('gl_r')
        a.w(0xD069, 0x004E)              # add.w $4E(a1),d0
        a.w(0x3740, 0x004E)              # move.w d0,$4E(a3)
        a.bcc(0x60, 'gl_out')
        a.label('gl_hide')
        a.w(0x377C, 0xFF00, 0x0052)      # move.w #-256,$52(a3) off screen
        a.label('gl_out')
        a.w(0x4CDF, 0x0903)              # movem.l (sp)+,d0-d1/a0/a3
        a.w(0x4E75)
        a.label('gl_pos')
        for dx, dy, *_ in F['fxl']():
            a.w(dx & 0xFFFF, dy & 0xFFFF)
    elif not F.get('heads', True):       # no head object (Raiden's: it explodes)
        a.w(0x4E75)
    a.w(0x48E7, 0xC090)                  # movem.l d0-d1/a0/a3,-(sp)
    a.pcrel(0x41FA, 'gk_z')              # lea gk_z(pc),a0
    a.w(0x2028, 0x0002)                  # move.l 2(a0),d0     the head object
    a.bccw(0x66, 'gh_have')
    a.w(0x4A50)                          # tst.w (a0)          her death art in?
    a.bccw(0x67, 'gh_out')
    # spawn it (as emit_proj: here, his owner fighter in a5; not from a task)
    a.w(0x48E7, 0xFFFE)                  # movem.l d0-d7/a0-a6,-(sp)
    # her head's tiles over his effect sheet's in VRAM (his projectile's: not
    # needed now): EC's own copy ($C760, as $D3DA does at load) from his tail
    a.bccw(0x61, 'pl_tail')              # bsr pl_tail         a0 = his tail (a1 = him)
    a.w(0xD0FC, SZF_TAIL.get('heads', 0))   # adda.w #heads,a0
    a.pcrel(0x45FA, 'gk_z')              # lea gk_z(pc),a2
    a.w(0x302A, 0x0006)                  # move.w 6(a2),d0     n
    a.w(0xD040)                          # add.w d0,d0
    a.pcrel(0x45FA, 'gk_hto')            # lea offsets(pc),a2
    a.w(0xD0F2, 0x0000)                  # adda.w (a2,d0.w),a0 her head's tiles
    src = GEN_TAIL.get('fx_src', 0)
    a.w(0x45F9); a.l(0xD448 + 8 * src)   # lea $D448+src*8,a2  its source entry
    a.w(0x222E, (-0x67D0 + 4 * src) & 0xFFFF)   # move.l -$67D0+src*4(a6),d1  its VRAM block
    a.bcc(0x67, 'gh_noup')
    a.w(0x2241)                          # movea.l d1,a1
    a.w(0x2251)                          # movea.l (a1),a1     VRAM address
    a.w(0x3012)                          # move.w (a2),d0      kind
    a.w(0x322A, 0x0006)                  # move.w 6(a2),d1     size
    a.jsr(0xC760)
    a.label('gh_noup')
    a.w(0x4CDF, 0x7FFF)                  # movem.l (sp)+,d0-d7/a0-a6
    a.w(0x48E7, 0xFFFE)                  # movem.l d0-d7/a0-a6,-(sp)
    a.w(0x266A, 0x0022)                  # movea.l 34(a2),a3   her
    a.w(0x2A49)                          # movea.l a1,a5       him: its owner
    a.pcrel(0x43FA, 'gk_hdesc')          # lea desc(pc),a1
    a.w(0x303C, PJ_TYPE)                 # move.w #type,d0
    a.w(0x7600)                          # moveq #0,d3
    a.jsr(0x6BBA)
    a.bccw(0x65, 'gh_none')              # bcs: no object free
    a.pcrel(0x43FA, 'gk_z')              # lea gk_z(pc),a1
    a.w(0x2348, 0x0002)                  # move.l a0,2(a1)     the head
    a.w(0x3029, 0x0006)                  # move.w 6(a1),d0     n
    a.pcrel(0x43FA, 'gk_park')           # lea park(pc),a1
    a.w(0x2468, 0x0088)                  # movea.l $88(a0),a2
    a.w(0x2549, 0x0004)                  # move.l a1,4(a2)     its task: parked
    a.w(0x0640, fr_fx(F['head_base']())) # addi.w #sheet:head 0,d0
    a.w(0x3140, 0x001A)                  # move.w d0,$1A(a0)   his effect sheet, her head
    a.w(0x316B, 0x001E, 0x001E)          # move.w $1E(a3),$1E(a0)  her palette line ...
    a.w(0x316B, 0x0020, 0x0020)          # move.w $20(a3),$20(a0)  ... and facing
    a.w(0x317C, 0xFF00, 0x0052)          # move.w #-256,$52(a0) off screen
    a.label('gh_none')
    a.w(0x4CDF, 0x7FFF)                  # movem.l (sp)+,d0-d7/a0-a6
    a.bccw(0x60, 'gh_out')
    a.label('gh_have')
    a.w(0x2640)                          # movea.l d0,a3       the head
    a.w(0x302C, 0x0006)                  # move.w 6(a4),d0     this row's head position + 1 (a4 = the row)
    a.bcc(0x67, 'gh_hide')               # none: hidden
    a.w(0x5340)                          # subq.w #1,d0
    a.w(0xE548)                          # lsl.w #2,d0
    a.bccw(0x61, 'gk_tail')              # bsr gk_tail         a0 = his fatality data
    a.w(0xD0FC, SZF_TAIL.get('hoff', 0)) # adda.w #positions,a0
    a.w(0xD0C0)                          # adda.w d0,a0
    a.w(0x3228, 0x0002)                  # move.w 2(a0),d1     dy (0: not yet)
    a.bcc(0x67, 'gh_hide')
    a.w(0xD269, 0x0052)                  # add.w $52(a1),d1
    a.w(0x3741, 0x0052)                  # move.w d1,$52(a3)
    a.w(0x3010)                          # move.w (a0),d0      dx, his way round
    a.w(0x0829, 0x0003, 0x0020)          # btst #3,$20(a1)
    a.bcc(0x67, 'gh_r')
    a.w(0x4440)                          # neg.w d0
    a.label('gh_r')
    a.w(0xD069, 0x004E)                  # add.w $4E(a1),d0
    a.w(0x3740, 0x004E)                  # move.w d0,$4E(a3)
    a.bcc(0x60, 'gh_out')
    a.label('gh_hide')
    a.w(0x377C, 0xFF00, 0x0052)          # move.w #-256,$52(a3) off screen
    a.label('gh_out')
    a.w(0x4CDF, 0x0903)                  # movem.l (sp)+,d0-d1/a0/a3
    a.w(0x4E75)
    a.label('gk_bc')
    a.w(0)
    a.label('gk_neck')
    for dx, dy in SZF_NECK:
        a.w(dx & 0xFFFF, dy & 0xFFFF)
    a.label('gk_hdesc')
    a.out += szf_head_desc()
    a.label('gk_hto')
    for o in SZF_TAIL.get('head_offs', [0] * (len(Z_NAMES) + len(MK_IDS))):
        a.w(o)
    a.label('gk_z')
    a.w(0)                               # her death sheet (- $100); 0 = none
    a.l(0)                               # her head object
    a.w(0)                               # n: her head's sheet $100 + n
    a.w(0)                               # her death file's sheet 1 (- $100)
    if SCORPION_ID == RAIDEN_ID:
        # MK CD's victim palette flashes four times, 3 frames on / 3 off,
        # from captured frames 180-200; the explosion is at frame 208.
        a.label('gr_flash')
        a.w(0x48E7, 0xFFFE)              # preserve gk_step's registers
        a.pcrel(0x41FA, 'gr_flash_count')
        a.w(0x5250)                      # addq.w #1,(a0)
        a.w(0x3010)                      # move.w (a0),d0
        a.w(0x0C40, 102)                 # explosion (capture frame 208)
        a.bcc(0x66, 'gr_no_blood')
        a.w(0x266A, 0x0022)              # a3 = victim
        a.w(0x2A49)                      # a5 = attacker
        a.w(0x3D6B, 0x004E, 0x1444)      # hit x = victim's x
        a.w(0x302B, 0x0052)
        a.w(0x0440, 96)                  # at the head, not the chest
        a.w(0x3D40, 0x1446)
        a.jsr(SUB_AT['blood'])
        a.pcrel(0x41FA, 'gr_flash_count')
        a.w(0x3010)
        a.label('gr_no_blood')
        a.w(0x0440, 88)                  # first of four flashes
        a.w(0x0C40, 11)
        a.bccw(0x62, 'gr_flash_out')      # outside 12 calls (unsigned)
        a.pcrel(0x43FA, 'gr_events')
        a.w(0x7200)
        a.w(0x1231, 0x0000)              # move.b (a1,d0.w),d1
        a.bccw(0x67, 'gr_flash_out')      # no change this call
        a.w(0x3801)                      # move.w d1,d4 (1 tint, 2 restore)
        a.w(0x266A, 0x0022)              # a3 = victim
        a.w(0x302B, 0x007A)
        a.w(0x0240, 0x0003)
        a.w(0x0A40, 0x0001)
        a.w(0xEB48)                      # palette line * 32
        a.w(0x41EE, PAL_BUF & 0xFFFF)
        a.w(0xD0C0)
        a.w(0x5488)                      # skip backdrop colour
        a.pcrel(0x49FA, 'gr_saved')       # a4 = original 15 colours
        a.w(0x0C44, 1)
        a.bcc(0x66, 'gr_restore')
        a.pcrel(0x4BFA, 'gr_tint')       # a5 = luminance-to-blue table
        a.w(0x760E)                      # 15 colours
        a.label('gr_tint_loop')
        a.w(0x3010)                      # d0 = original colour
        a.w(0x38C0)                      # save original, then map to blue
        a.w(0x3200); a.w(0xE249); a.w(0x0241, 0x0007)
        a.w(0x3400); a.w(0xEA4A); a.w(0x0242, 0x0007); a.w(0xD242)
        a.w(0xE048); a.w(0xE248); a.w(0x0240, 0x0007); a.w(0xD240)
        a.w(0xD241)
        a.w(0x30F5, 0x1000)
        a.dbra(3, 'gr_tint_loop')
        a.bcc(0x60, 'gr_dirty')
        a.label('gr_restore')
        a.w(0x760E)
        a.label('gr_restore_loop')
        a.w(0x30DC)
        a.dbra(3, 'gr_restore_loop')
        a.label('gr_dirty')
        a.w(0x3D7C, 0xFFFF, PAL_DIRTY & 0xFFFF)
        a.label('gr_flash_out')
        a.w(0x4CDF, 0x7FFF)
        a.w(0x4E75)
        a.label('gr_events')
        a.out += bytes((1,0,2,1,0,2,1,0,2,1,0,2))
        a.label('gr_flash_count')
        a.w(0)
        a.label('gr_saved')
        a.out += bytes(30)
        a.label('gr_tint')
        for colour in _freeze_tint():
            a.w(colour)
    a.label('gk_x')


def emit_throwcall(a):
    """Call SUB.BIN's thr for a1 (his block's fighter), his THROW_PUSH
    signed away from him (toward his opponent's side). Uses d0/a0."""
    push = THROW_PUSH[SCORPION_ID]
    if push:
        a.w(0x2F01)                      # move.l d1,-(sp)
        a.w(0x2069, 0x008C)              # movea.l $8C(a1),a0
        a.w(0x323C, push)                # move.w #push,d1
        a.w(0x3029, 0x004E)              # move.w $4E(a1),d0
        a.w(0xB068, 0x004E)              # cmp.w $4E(a0),d0
        a.bcc(0x6F, 'tc_r')              # ble: she is on his right
        a.w(0x4441)                      # neg.w d1
        a.label('tc_r')
        a.w(0x33C1); a.l(SUB_AT['thr_spd'])   # move.w d1,thr_spd
        a.w(0x221F)                      # move.l (sp)+,d1
    else:
        a.w(0x4279); a.l(SUB_AT['thr_spd'])   # clr.w thr_spd
    a.jsr(SUB_AT['thr'])
    # in the air off the throw: no rise (EC's knockdown arc kept her
    # tumbling ~36 frames; MK's victim is down at once)
    a.w(0x0C40, 0x0001)                  # cmpi.w #1,d0
    a.bcc(0x66, 'tc_x')
    a.w(0x2069, 0x008C)                  # movea.l $8C(a1),a0
    # (falling THROW_DROP px a frame: cleared, she floated down ~0.5 px a frame
    #  in the knockdown's flight pose; MK's victim is down at once)
    a.w(0x217C); a.l(THROW_DROP << 16); a.w(0x00CA)   # move.l #drop,$CA(a0)
    a.w(0x4AA8, 0x0062)                  # tst.l $62(a0)
    a.bcc(0x6A, 'tc_x')                  # bpl
    a.w(0x42A8, 0x0062)                  # clr.l $62(a0)
    a.label('tc_x')
    # her bounce was just cut (phase 3): her knockdown script goes to the
    # step before its lying step (the 'fly till landing' step, $F6 bit 8),
    # so EC plays her lying pose and gets her up (EC's own order: fly, land,
    # bounce, land, lie, get up). Not again once her script is past it.
    a.w(0x0C40, 0x0003)                  # cmpi.w #3,d0
    a.bccw(0x66, 'tc_nk')
    a.w(0x48E7, 0x4020)                  # movem.l d1/a2,-(sp)
    a.w(0x2469, 0x008C)                  # movea.l $8C(a1),a2   her
    a.w(0x206A, 0x00AA)                  # movea.l $AA(a2),a0   her script's steps
    a.w(0x7200)                          # moveq #0,d1
    a.w(0x0C2A, DARK_CHAMPION, 0x004D)   # cmpi.b #25,$4D(a2)   the Dark Champion: his 'fly till landing'
    a.bcc(0x67, 'tc_dc')                 #  is his knockdown's first step, then his bounce - no lying step
    a.label('tc_lp')
    a.w(0x0C50, 0x0100)                  # cmpi.w #$100,(a0)    the end: none
    a.bcc(0x65, 'tc_none')
    a.w(0x0828, 0x0000, 0x0008)          # btst #0,8(a0)        $F6 bit 8: fly till landing
    a.bcc(0x66, 'tc_fw')
    a.w(0x41E8, 0x000C)                  # lea 12(a0),a0
    a.w(0x5241)                          # addq.w #1,d1
    a.bcc(0x60, 'tc_lp')
    a.label('tc_fw')
    a.w(0x202A, 0x00AE)                  # move.l $AE(a2),d0
    a.w(0xB088)                          # cmp.l a0,d0
    a.bcc(0x62, 'tc_nf')                 # bhi: past it already
    a.w(0x2548, 0x00AE)                  # move.l a0,$AE(a2)
    a.w(0x3541, 0x00C2)                  # move.w d1,$C2(a2)
    a.w(0x3568, 0x000C, 0x001A)          # move.w 12(a0),$1A(a2)   her lying pose now
    a.w(0x206A, 0x0088)                  # movea.l $88(a2),a0
    a.w(0x2050)                          # movea.l (a0),a0
    a.w(0x317C, 0x0001, 0x0026)          # move.w #1,$26(a0)    on to it
    a.bcc(0x60, 'tc_nf')
    # the Dark Champion: his first step (fly till landing), every call while she's in phase 3. After the
    # throw's damage EC's landing restarts his knockdown - its bounce, rising - and left to it (found once,
    # 'past it' after), it ended in the air with his motion gone (thr's cut): EC's landing code waited for
    # the floor forever and a Contest's last fight never ended (contestcheck.py --ending --throws).
    # Flying till landing brings him down. None found (no such victim seen): her script ends here,
    # where thr put her - on the floor, her landing frame
    a.label('tc_dc')
    a.label('tc_none')
    a.w(0x2548, 0x00AE)                  # move.l a0,$AE(a2)    the end marker
    a.w(0x3541, 0x00C2)                  # move.w d1,$C2(a2)
    a.w(0x206A, 0x0088)                  # movea.l $88(a2),a0
    a.w(0x2050)                          # movea.l (a0),a0
    a.w(0x317C, 0x0001, 0x0026)          # move.w #1,$26(a0)    this step ends now
    a.label('tc_nf')
    a.w(0x4CDF, 0x0402)                  # movem.l (sp)+,d1/a2
    a.label('tc_nk')


def emit_throwfix(a, pfx):
    """Subroutine pfx (a1 = an MK fighter; d1 = his player 0/4 when
    per_player): his throw's victim lands like MK's. EC releases her with a
    knockdown that throws her ~115 px further and bounces her ~35 px more
    (270 px behind him); MK's victim drops where the roll left her (~110 px
    behind) and lies there. From the release (her state $37 -> knockdown $1C)
    to the landing her speed across is cut; the knockdown's replay after she lands
    (the bounce) is ended as on the Pit (ecstage nobounce): back on the
    floor, steps used up, the landing frame kept. Saves its registers. One
    copy in SUB.BIN for every MK fighter (8 bytes of state per player)."""
    a.label(pfx)
    a.w(0x48E7, 0x40E0)                  # movem.l d1/a0-a2,-(sp)    (d0 out: her phase)
    a.w(0x2069, 0x008C)                  # movea.l $8C(a1),a0   his opponent
    a.pcrel(0x45FA, f'{pfx}_v')          # lea v(pc),a2         +0 her last state, +2 phase, +4 landing frame
    a.w(0xB3FC); a.l(0x2E188)            # cmpa.l #P1,a1
    a.bcc(0x67, f'{pfx}_p1')
    a.w(0x504A)                          # addq.w #8,a2         player 2's
    a.label(f'{pfx}_p1')
    a.w(0x3028, 0x00BE)                  # move.w $BE(a0),d0
    a.w(0x0240, 0x7FFF)                  # andi.w #$7FFF,d0
    a.w(0x0C40, KNOCKDOWN)               # cmpi.w #$1C,d0
    a.bcc(0x67, f'{pfx}_kd')
    a.w(0x426A, 0x0002)                  # clr.w 2(a2)          not knocked down: nothing to watch
    a.bccw(0x60, f'{pfx}_sv')
    a.label(f'{pfx}_kd')
    a.w(0x0C52, THROWN)                  # cmpi.w #$37,(a2)
    a.bcc(0x66, f'{pfx}_nr')
    a.w(0x357C, 0x0001, 0x0002)          # move.w #1,2(a2)      released: in the air
    a.label(f'{pfx}_nr')
    a.w(0x4A6A, 0x0002)                  # tst.w 2(a2)
    a.bccw(0x67, f'{pfx}_sv')
    a.w(0x0C6A, 0x0001, 0x0002)          # cmpi.w #1,2(a2)
    a.bcc(0x66, f'{pfx}_fl')
    # off the roll: EC's own short arc up and down (its frames land her in
    # her lying pose), at the thrower's speed across (THROW_PUSH: EC's
    # knockdown steps set it again from $C6, so both, every call till she
    # lands), away from him (the caller signs it: emit_throwcall)
    a.pcrel(0x323A, f'{pfx}_spd')        # move.w spd(pc),d1    px/frame x256
    a.w(0x48C1)                          # ext.l d1
    a.w(0xE181)                          # asl.l #8,d1          16.16
    a.w(0x2141, 0x005E)                  # move.l d1,$5E(a0)
    a.w(0x2141, 0x00C6)                  # move.l d1,$C6(a0)
    a.label(f'{pfx}_fl')
    a.w(0x3228, 0x0052)                  # move.w $52(a0),d1
    a.w(0xB26E, FLOOR_Y)                 # cmp.w $1496(a6),d1
    a.bcc(0x6D, f'{pfx}_air')            # blt: off the floor
    a.w(0x0C6A, 0x0001, 0x0002)          # cmpi.w #1,2(a2)
    a.bcc(0x66, f'{pfx}_sv')
    a.w(0x357C, 0x0002, 0x0002)          # move.w #2,2(a2)      landed
    a.w(0x3568, 0x001A, 0x0004)          # move.w $1A(a0),4(a2) her landing frame
    a.w(0x42A8, 0x005E)                  # clr.l $5E(a0)
    a.bcc(0x60, f'{pfx}_sv')
    a.label(f'{pfx}_air')
    a.w(0x0C6A, 0x0002, 0x0002)          # cmpi.w #2,2(a2)      up again after landing: the bounce
    a.bcc(0x66, f'{pfx}_sv')
    a.w(0x322E, FLOOR_Y)                 # move.w $1496(a6),d1
    for o in POS_Y:
        a.w(0x3141, o)                   # move.w d1,y(a0)
    a.w(0x42A8, 0x0062)                  # clr.l $62(a0)
    a.w(0x42A8, 0x005E)                  # clr.l $5E(a0)
    a.w(0x42A8, 0x00C6)                  # clr.l $C6(a0)
    a.w(0x42A8, 0x00CA)                  # clr.l $CA(a0)
    a.w(0x3168, 0x00C4, 0x00C2)          # move.w $C4(a0),$C2(a0)   steps used up
    a.w(0x316A, 0x0004, 0x001A)          # move.w 4(a2),$1A(a0)     the landing frame
    a.w(0x2068, 0x0088)                  # movea.l $88(a0),a0
    a.w(0x2050)                          # movea.l (a0),a0
    a.w(0x317C, 0x0001, 0x0026)          # move.w #1,$26(a0)        this step ends now
    a.w(0x357C, 0x0003, 0x0002)          # move.w #3,2(a2)      done: phase 3 (inert till she gets up;
                                         #   the caller sends her script to its lying step)
    a.label(f'{pfx}_sv')
    a.w(0x3480)                          # move.w d0,(a2)       her state, for the next call
    a.w(0x302A, 0x0002)                  # move.w 2(a2),d0      phase: 1 = in the air off the throw
    a.w(0x4CDF, 0x0702)                  # movem.l (sp)+,d1/a0-a2
    a.w(0x4E75)
    a.label(f'{pfx}_spd')                # set by the thrower's block before each call (THROW_PUSH)
    a.w(0)
    a.label(f'{pfx}_v')
    a.out += bytes(16)


def emit_wdir(a, name):
    """Subroutine: Z clear if the walk is toward the opponent. EC's walk
    states are left/right (8 = right) whichever way he faces ($20 bit 11 =
    facing left), so toward = bit 3 of ($BF xor $20's high byte)."""
    a.label(name)
    a.w(0x48E7, 0x3000)                  # movem.l d2-d3,-(sp)
    a.w(0x1429, 0x00BF)                  # move.b $BF(a1),d2
    a.w(0x1629, 0x0020)                  # move.b $20(a1),d3
    a.w(0xB702)                          # eor.b d3,d2
    a.w(0x0802, 0x0003)                  # btst #3,d2
    a.w(0x4CDF, 0x000C)                  # movem.l (sp)+,d2-d3
    a.w(0x4E75)


def r_generic(a, scripts, fwd, back, hit, throw, sounds={}, leg=None, kick=None):
    """A generic MK fighter's per-frame routine (a1 = him, this block's
    slot): his MK attack scripts in his move table, toward + Y throws behind,
    MK's walk cycle."""
    a.label('r_drag')
    a.w(0x0C69, SCORPION_ID, 0x004C)     # cmpi.w #id,$4C(a1)
    a.bccw(0x66, 'g_out')
    emit_zblock(a)
    a.bccw(0x61, 'zblock')               # bsr zblock          Z: MK's Block
    if SCORPION_ID == SONYA_ID:          # (her block has no room for it: a subroutine in her module's rooms -
        r = Asm(0)                       #  a dead script body of Blade's, GEN_DEAD - 4 bytes of her block)
        r_swept_by(r)
        r.w(0x4E75)                      # rts
        at = dead_put(r.build())         # (straight to a dead body: in her victory room it pushed a
        if at is None:                   #  bigger routine out to her block)
            room_put(a, 'swept_by', r.build())
        else:
            a.labels['swept_by'] = at - EXT_OFF
        a.bccw(0x61, 'swept_by')         # bsr swept_by         her sweep drops the victim where he stands
    elif SCORPION_ID != SHANG_ID:        # (MK's Shang has no sweep)
        r_swept_by(a)                    # his sweep drops the victim where he stands
    if SCORPION_ID == SHANG_ID:
        emit_morph(a)                    # his morph into his opponent
    a.bccw(0x61, 'g_reg')                # bsr g_reg            his MK specials (r_gmoves)
    if SCORPION_ID == KANO_ID:
        # EC queues the recognized knife while Kano is holding Z in move 3,
        # but that move's task never checks the queue again until it ends.
        # Resume his own task at the normal special dispatcher only for that
        # queued move; all other blocks and inputs retain EC's normal handling.
        a.w(0x0C69, 3, 0x00BE)
        a.bccw(0x66, 'g_kno')
        a.w(0x4A69, 0x012A)              # CPU fighter? leave its task alone
        a.bccw(0x66, 'g_kno')
        a.w(0x0829, 0x0003, 0x011A)     # recognizer has a queued special
        a.bccw(0x67, 'g_kno')
        a.w(0x2069, 0x0184)              # his input task's move queue
        a.w(0x0C68, 0x0034, 0x0042)     # the knife, not another special
        a.bccw(0x66, 'g_kno')
        a.w(0x2069, 0x0088)              # fighter -> move task -> TCB
        a.w(0x2050)
        a.pcrel(0x45FA, 'g_kstart')
        a.w(0x214A, 0x0004)              # move.l a2,4(a0)  next task PC
        a.w(0x4268, 0x0008)              # run without the old delay
        a.label('g_kno')
    if SCORPION_ID == SONYA_ID:
        emit_sq_lift(a)
    if SCORPION_ID == JOHNNY_ID:
        a.bccw(0x61, 'jk_drive')
    if SCORPION_ID == REPTILE_ID:
        a.bccw(0x61, 'rs_drive')         # his spear's pull and daze (Scorpion's, from his side)
    if SCORPION_ID in KD_FIGHTERS:       # MK's knockdown between EC's frame changes
        a.w(0x2F0D)                      # move.l a5,-(sp)
        a.w(0x2A49)                      # movea.l a1,a5
        a.bccw(0x61, 'g_kd')
        a.w(0x2A5F)                      # movea.l (sp)+,a5
    emit_mk_daze(a)                      # dazed: MK's 7-pose sway
    # FINISH HIM (r_finish set vars+52): the loser has no block, so his daze
    # is driven from here
    a.pcrel(0x45FA, 'vars')              # lea vars(pc),a2
    a.w(0x4AAA, 0x0034)                  # tst.l 52(a2)
    a.bccw(0x67, 'g_nfh')
    a.w(0x2F09)                          # move.l a1,-(sp)
    a.w(0x226A, 0x0034)                  # movea.l 52(a2),a1
    emit_finish_daze(a, 'gf_', sounds.get('finish', 0), sounds.get('finish_f', 0))
    a.w(0x225F)                          # movea.l (sp)+,a1
    a.label('g_nfh')
    if SCORPION_ID in FATALS:
        a.pcrel(0x45FA, 'vars')          # lea vars(pc),a2
        emit_gfatal(a)                   # his MK fatality (Sub-Zero's spine rip, Johnny's decapitation)
    if any(isinstance(m, int) for m in sounds):   # his MK sound when one of his specials starts
        a.w(0x3029, 0x00BE)              # move.w $BE(a1),d0
        a.w(0x0240, 0x7FFF)              # andi.w #$7FFF,d0
        a.pcrel(0x45FA, 'g_slast')       # lea last(pc),a2
        a.w(0xB052)                      # cmp.w (a2),d0
        a.bccw(0x67, 'g_snd')
        a.w(0x3480)                      # move.w d0,(a2)
        if PROJ_TEST and SCORPION_ID == RAIDEN_ID:
            a.w(0x0C40, 0x0034)          # cmpi.w #$34,d0       (experiment: a flying object)
            a.bcc(0x66, 'g_pjn')
            a.w(0x3F00)                  # move.w d0,-(sp)
            a.bccw(0x61, 'g_proj')
            a.w(0x301F)                  # move.w (sp)+,d0
            a.label('g_pjn')
        for k, (move, sid) in enumerate(sorted((m, v) for m, v in sounds.items() if isinstance(m, int))):
            a.w(0x0C40, move)            # cmpi.w #move,d0
            a.bcc(0x66, f'g_sn{k}')
            a.w(0x48E7, 0x7FFE)          # movem.l d1-d7/a0-a6,-(sp)
            a.w(0x303C, sid)             # move.w #id,d0
            a.jsr(0x6D58)
            a.w(0x4CDF, 0x7FFE)          # movem.l (sp)+,d1-d7/a0-a6
            a.label(f'g_sn{k}')
        a.bccw(0x60, 'g_snd')
        a.label('g_slast')
        a.w(0)
        if PROJ_TEST and SCORPION_ID == RAIDEN_ID:
            emit_proj_test(a)
        a.label('g_snd')
    if SCORPION_ID in PJ_FIGHTERS:
        emit_proj(a, PJ_FIGHTERS[SCORPION_ID])   # his MK projectile flies
    elif SCORPION_ID == SHANG_ID:
        emit_skull(a)                    # his skull volley
    if SCORPION_ID in (SUBZERO_ID, REPTILE_ID):
        emit_freeze(a)                   # his ice blast freezes
    # an uppercut flight this block's launch started (no full block in the
    # fight): EC's victim has no block, so his flight runs from here
    a.pcrel(0x45FA, 'vars')              # lea vars(pc),a2
    a.w(0x202A, 0x000E)                  # move.l 14(a2),d0
    a.bccw(0x67, 'g_nfl')
    a.w(0x2F09)                          # move.l a1,-(sp)
    a.w(0x2240)                          # movea.l d0,a1
    emit_flight(a, 'g_fle')
    a.label('g_fle')
    a.w(0x225F)                          # movea.l (sp)+,a1
    a.label('g_nfl')
    if SCORPION_ID == JOHNNY_ID:
        # his split punch (down + Z: move $10, Blade's script, strike step
        # 42:07) does nothing to a woman (as in MK): the split, no
        # hit. The hit lands on the very frame its step loads, before this
        # runs, so the step's hit word in his move script is cleared ahead
        # while his opponent is a woman, and put back (saved) for a man
        a.w(0x48E7, 0x40A0)              # movem.l d1/a0/a2,-(sp)
        a.w(0x2069, 0x00A6)              # movea.l $A6(a1),a0  his move table
        a.w(0x2068, 4 * SPLIT_MOVE)      # movea.l 4*$10(a0),a0
        # its steps (BLA.CO $43B4): split 42:05, punch 42:06, strike 42:07
        # (the hit), punch 42:06. A woman: the split held through all of them
        # (MK: his fist doesn't come out), no hit. A man: as built.
        a.w(0x41E8, 20 + 12 * SPLIT_STRIKE)   # lea strike(a0),a0
        a.w(0x2469, 0x008C)              # movea.l $8C(a1),a2  his opponent
        a.w(0x322A, 0x004C)              # move.w $4C(a2),d1
        a.pcrel(0x45FA, 'g_sphit')       # lea saved(pc),a2
        a.w(0x3028, 0x000A)              # move.w 10(a0),d0    the hit
        a.bcc(0x67, 'g_spk')
        a.w(0x3480)                      # move.w d0,(a2)      saved
        a.label('g_spk')
        for fem in FEMALE:
            a.w(0x0C41, fem)             # cmpi.w #id,d1
            a.bcc(0x67, 'g_spf')
        a.w(0x3152, 0x000A)              # move.w (a2),10(a0)  a man: the hit back
        a.w(0x317C, fr(0x4206), 0xFFF4)  # move.w #punch,-12(a0)
        a.w(0x30BC, fr(0x4207))          # move.w #strike,(a0)
        a.w(0x317C, fr(0x4206), 0x000C)  # move.w #punch,12(a0)
        a.bcc(0x60, 'g_spx')
        a.label('g_spf')
        a.w(0x4268, 0x000A)              # clr.w 10(a0)        a woman: no hit ...
        a.w(0x317C, fr(0x4205), 0xFFF4)  # move.w #split,-12(a0)   ... and no punch
        a.w(0x30BC, fr(0x4205))          # move.w #split,(a0)
        a.w(0x317C, fr(0x4205), 0x000C)  # move.w #split,12(a0)
        a.label('g_spx')
        a.w(0x4CDF, 0x0502)              # movem.l (sp)+,d1/a0/a2
    if SCRIPT_TAIL:                      # his scripts in his .PL's tail (generic_block)
        a.w(0x2F0B)                      # move.l a3,-(sp)
        a.bccw(0x61, 'pl_tail')          # bsr pl_tail         a0 = the tail
        a.w(0x2648)                      # movea.l a0,a3
    a.w(0x2069, 0x00A6)                  # movea.l $A6(a1),a0
    for mid in sorted(scripts):
        if SCRIPT_TAIL:
            a.w(0x486B, SCRIPT_TAIL[mid])    # pea off(a3)
        else:
            a.pcrel(0x487A, f'gs_{mid}')     # pea script(pc)
        a.w(0x215F, 4 * mid)             # move.l (sp)+,4*id(a0)
    if SCRIPT_TAIL:
        a.w(0x265F)                      # movea.l (sp)+,a3
    emit_vendetta_ok(a, SCORPION_ID, 'g_')
    # throw: toward + Y reads as back + Y
    a.w(0x41EE, 0x0A3A)                  # lea $A3A(a6),a0     P1 pad ...
    a.w(0xB3FC); a.l(0x2E188)            # cmpa.l #P1,a1
    a.bcc(0x67, 'g_pad')
    a.w(0x41EE, 0x0A3C)                  # lea $A3C(a6),a0     ... P2 pad
    a.label('g_pad')
    a.w(0x3010)                          # move.w (a0),d0
    if SCORPION_ID == SONYA_ID:
        emit_leggrab_pad(a)              # her leg grab: back + Y (EC's throw)
    a.w(0x0800, THROW_BIT)               # btst #9,d0
    a.bcc(0x67, 'g_nthr')
    a.w(0x0829, 0x0003, 0x0020)          # btst #3,$20(a1)     facing left?
    a.bcc(0x66, 'g_thl')
    a.w(0x0800, 0x0003)                  # btst #3,d0
    a.bcc(0x67, 'g_nthr')
    a.w(0x0880, 0x0003)                  # bclr #3,d0
    a.w(0x08C0, 0x0002)                  # bset #2,d0
    a.bcc(0x60, 'g_thw')
    a.label('g_thl')
    a.w(0x0800, 0x0002)                  # btst #2,d0
    a.bcc(0x67, 'g_nthr')
    a.w(0x0880, 0x0002)                  # bclr #2,d0
    a.w(0x08C0, 0x0003)                  # bset #3,d0
    a.label('g_thw')
    a.w(0x3080)                          # move.w d0,(a0)
    # ... and the back it made held already last frame, not a fresh tap (EC's new presses, $162, are this
    # pad & ~the last one it saw, $A0(a5): a5 is the input task's own at DRAG_SITES, where this runs, just
    # before EC reads it): forward, then this back + HP was Sonya's square wave (forward, back + HP) -
    # holding forward and pressing HP flew instead of punching
    a.w(0x0240, 0x000C)                  # andi.w #$C,d0       the back bit
    a.w(0x816D, 0x00A0)                  # or.w d0,$A0(a5)
    a.label('g_nthr')
    if SCORPION_ID == RAIDEN_ID:
        emit_rtele(a)
    if SCORPION_ID == LIUKANG_ID:
        emit_flykick_stop(a)             # his flying kick floats back when it connects
    emit_throwcall(a)                    # his throw's victim lands like MK's
    if SCORPION_ID == SONYA_ID:
        emit_leggrab_drive(a, leg)
    emit_hitdrive(a, throw, 'g_tw', 'g_out', False, THROW_MOVE, False, room=True)   # MK's throw animation
    emit_hitdrive(a, kick or hit, 'g_ht', 'g_out', False, room=True, calls_b=hit if kick else None)
    # Shang's glide needs no drive: his walk scripts show his poses (glide_scripts)
    if SCORPION_ID != SHANG_ID:
        # walk: as Scorpion's (r_drag), resynced at each of EC's steps
        a.pcrel(0x45FA, 'gvars')             # lea gvars(pc),a2
        # held by an EC grab ($100 bit 1): no new walk pose (as Scorpion's d_ block:
        # a new pose puts him back at $B6, and the Dark Champion's drain never ended)
        a.w(0x0829, 0x0001, 0x0101)          # btst #1,$101(a1)
        a.bcc(0x66, 'g_nwk')
        a.w(0x3029, 0x00BE)                  # move.w $BE(a1),d0
        a.w(0x0240, 0x7FFF)                  # andi.w #$7FFF,d0
        a.w(0x0C40, WALK_FWD)
        a.bcc(0x67, 'g_wst')
        a.w(0x0C40, WALK_BACK)
        a.bcc(0x66, 'g_nwk')
        a.label('g_wst')
        a.w(0x0C29, fr(0x4000) >> 8, 0x001A)  # cmpi.b #sheet,$1A(a1)
        a.bcc(0x66, 'g_nwk')
        a.w(0x1029, 0x001B)                  # move.b $1B(a1),d0
        a.w(0x0C00, 0x0016)
        a.bcc(0x65, 'g_nwk')
        a.w(0x0C00, 0x001B)
        a.bcc(0x63, 'g_wok')
        a.w(0x0C00, WALK_FRAMES[0] & 0xFF)
        a.bcc(0x65, 'g_nwk')
        a.w(0x0C00, WALK_FRAMES[-1] & 0xFF)
        a.bcc(0x63, 'g_wok')
        a.label('g_nwk')
        a.w(0x4252)                          # clr.w (a2)
        a.bccw(0x60, 'g_out')
        a.label('g_wok')
        a.w(0x7000)                          # moveq #0,d0
        a.w(0x1029, 0x001B)                  # move.b $1B(a1),d0
        a.w(0x0440, 0x0016)                  # subi.w #$16,d0
        a.bcc(0x6D, 'g_wcnt')
        a.w(0x0C40, 0x0005)
        a.bcc(0x6E, 'g_wcnt')
        a.bccw(0x61, 'gwdir')                # bsr gwdir          toward?
        a.bcc(0x66, 'g_wfs')
        a.w(0x4440)                          # neg.w d0
        a.w(0x5A40)                          # addq.w #5,d0
        a.label('g_wfs')
        a.w(0x3040)                          # movea.w d0,a0
        a.w(0xD040)                          # add.w d0,d0
        a.w(0xD048)                          # add.w a0,d0
        a.w(0x5240)                          # addq.w #1,d0
        a.w(0x3480)                          # move.w d0,(a2)
        a.bcc(0x60, 'g_wki')
        a.label('g_wcnt')
        a.w(0x5252)                          # addq.w #1,(a2)
        a.w(0x3012)                          # move.w (a2),d0
        a.w(0x0C40, len(fwd))
        a.bcc(0x65, 'g_wki')
        a.w(0x7000)
        a.w(0x3480)                          # move.w d0,(a2)
        a.label('g_wki')
        a.w(0xD040)                          # add.w d0,d0
        a.pcrel(0x41FA, 'g_walkf')
        a.bccw(0x61, 'gwdir')                # bsr gwdir
        a.bcc(0x66, 'g_wset')
        a.pcrel(0x41FA, 'g_walkb')
        a.label('g_wset')
        a.w(0x3370, 0x0000, 0x001A)          # move.w (a0,d0.w),$1A(a1)
    a.label('g_out')
    a.w(0x4E75)
    if SCORPION_ID == KANO_ID:
        a.label('g_kstart')              # resumed as his own move task (a5 = fighter)
        a.w(0x7034)                      # moveq #$34,d0
        disp = 0x2206 - (EXT_OFF + len(a.out) + 2)
        a.w(0x6000, disp & 0xFFFF)       # bra.w Blade module's special dispatcher
    if SCORPION_ID == JOHNNY_ID:
        emit_johnny_shadow(a)
    if SCORPION_ID == REPTILE_ID:
        emit_reptile_spear(a)
    if SCORPION_ID in JUMP_FIGHTERS and SCORPION_ID not in JUMP_LOW:
        _f, _b, _ = jump_plan(MK_DIR_BY_ID[SCORPION_ID])
        emit_jump_drive(a, _f, _b, jump_up_plan(MK_DIR_BY_ID[SCORPION_ID]),
                        JUMP_TAIL.get('off') if SCORPION_ID in JUMP_IN_TAIL else None)
    if SCORPION_ID in KD_FIGHTERS and SCORPION_ID not in KD_LOW:
        emit_kd_drive(a)
    if SCORPION_ID != SHANG_ID:
        emit_wdir(a, 'gwdir')
        a.label('g_walkf')
        for k in fwd:
            a.w(fr(WALK_FRAMES[k]))
        a.label('g_walkb')
        for k in back:
            a.w(fr(WALK_FRAMES[k]))
    a.label('gvars')
    a.w(0)
    a.label('g_sphit')                   # Johnny's split punch's hit word (r_generic)
    a.w(0)
    if not SCRIPT_TAIL:
        for mid, sc in sorted(scripts.items()):
            a.label(f'gs_{mid}')
            a.out += script_bytes(sc)


# (Riptide, Raven, Dawson: checked on MK losers with tools/lib/vendettacheck.py (each has its own
#  range: ~90 / 130 / 130+ px): Riptide's ice monster and Raven's remains are their own art,
#  Dawson's shot leaves the loser's own body lying in blood)
# (Trident, Midknight: their .VC victim records for the MK slots were empty or a
#  host's (patches.mk_victim_poses): Raiden hung, the others vanished; on all seven, both sides)
VENDETTA_WINNERS = (4, 6, 7, 8, 10, 14, 21, 24)  # EC winners whose Vendetta plays right on an MK loser (Rax,
                              #  Trident, Midknight, Xavier, Jetta: tools/lib/vendettacheck.py, compared with
                              #  the same on Shadow; the death-art ones would draw an EC body)
VENDETTA_OK = 0x15F1B         # PLYR.CO: a byte per loser (id - 2): Vendettas allowed on him
# ... and these too on an MK loser with death art of his own (tools/lib/mkdeath.py:
# their Vendettas draw the loser from his slot's Z<xx>.BIN): Shadow, Larcen,
# Slash, Blade, Ramses
DEATH_ART_WINNERS = (2, 3, 5, 9, 15)


def emit_vendetta_ok(a, fid, pfx):
    """(a1 = this block's MK fighter) Vendettas on him only from VENDETTA_WINNERS
    (and DEATH_ART_WINNERS when his slot's death art is his: mkdeath.art_ids):
    his PLYR.CO $15F1B byte follows his opponent each frame. Uses d0/a0."""
    a.w(0x2069, 0x008C)                  # movea.l $8C(a1),a0  his opponent
    a.w(0x3028, 0x004C)                  # move.w $4C(a0),d0
    a.pcrel(0x41FA, f'{pfx}vok')         # lea vok(pc),a0
    a.w(0x13F0, 0x0000); a.l(VENDETTA_OK + fid - 2)   # move.b 0(a0,d0.w),VENDETTA_OK+his id-2
    a.bcc(0x60, f'{pfx}vx')
    a.label(f'{pfx}vok')
    import mkdeath
    ok = set(VENDETTA_WINNERS) | (set(DEATH_ART_WINNERS) if fid in mkdeath.art_ids() else set())
    a.out += bytes(1 if i in ok else 0 for i in range(40))
    a.label(f'{pfx}vx')


def script_bytes(sc):
    """An MK script with its frame words in his numbering (fr)."""
    out = bytearray(sc[:20])
    for o in range(20, len(sc), 12):
        f = int.from_bytes(sc[o:o + 2], 'big')
        out += struct.pack('>H', fr(f) if f >= 0x100 else f) + sc[o + 2:o + 12]
    return bytes(out)


# His .PL's tail (patches.mk_code): data appended after the .PL's chunk chain,
# loaded with it and never parsed by EC. P1's .PL is at $81800 (Word RAM),
# P2's at $51800: pl_tail (a1 = him) gives the tail's address.
# TAIL_FIGHTERS (with SZF_ZFILE): fighters whose scripts live there
GEN_TAIL = {'off': None, 'data': b''}   # 'off' set by patches.mk_code before generic_block
SCRIPT_TAIL = {}              # move id -> offset in the tail (while assembling)


def emit_pl_tail(a, off=None, label='pl_tail'):
    a.label(label)
    a.w(0x207C); a.l(0x81800)            # movea.l #$81800,a0  player 1's .PL ...
    a.w(0xB3FC); a.l(0x2E188)            # cmpa.l #P1,a1
    a.bcc(0x67, f'{label}_p2')
    # ... player 2's at $51800 - unless both play him: EC's file cache loads the .PL
    # once (player 1's copy for both; scripts read at $51800 were garbage: a hang)
    a.w(0x48E7, 0x8020)                  # movem.l d0/a2,-(sp)
    a.w(0x2469, 0x008C)                  # movea.l $8C(a1),a2  the other player
    a.w(0x302A, 0x004C)                  # move.w $4C(a2),d0
    a.w(0xB069, 0x004C)                  # cmp.w $4C(a1),d0
    a.w(0x4CDF, 0x0401)                  # movem.l (sp)+,d0/a2 (flags kept)
    a.bcc(0x67, f'{label}_p2')           # the same fighter: player 1's copy
    a.w(0x207C); a.l(0x51800)            # movea.l #$51800,a0
    a.label(f'{label}_p2')
    a.w(0xD1FC); a.l((GEN_TAIL['off'] if off is None else off) or 0)   # adda.l #tail,a0
    a.w(0x4E75)


GENERIC_VARS = 66             # bytes: a generic block's vars (as Scorpion's: +14..+23 the flight, +24 a fatality,
                              # +44 its pad, +52..+61 FINISH HIM, +63 Sonya lifted, +64/+65 her leg grab)


DAZE_PAD = 0xCD8              # a generic module: daze_pad, the second victory room's end (VROOM; it was
                              #  the 90 bytes between BLA.CO's end and EXT_OFF: no room for the freeze check)
DAZE_TAIL = {}                # 'at': daze_tail's address (PLYR.CO's gap, after the stubs: build())


def emit_mk_daze(a):
    """Dazed (EC's dizzy, state $1F: FINISH HIM, the spear): MK's 7-pose sway,
    by his module's daze_pad. (His block has no room for it: Sonya's is full.)"""
    disp = DAZE_PAD - (EXT_OFF + len(a.out) + 2)
    a.w(0x6100, disp & 0xFFFF)           # bsr.w daze_pad


def daze_pad(sheet_shift):
    """A generic MK fighter's daze (emit_mk_daze calls it; Scorpion's r_drag
    has his own), at DAZE_PAD in his module. a1 = the fighter. While EC has
    him dazed, cycle his 7 MK sway poses at MK's timing (DAZE_SEQ, one entry
    per call: every other frame); EC's own loop holds its first pose
    (dizzy_hold). Not while a finisher, a Vendetta or a grab owns his frames
    (as r_drag). A counter per player, counting down; the frame from the
    shared table (daze_tail). Uses d0/a0 only (scratch in r_generic)."""
    keep = SHEET_SHIFT
    globals()['SHEET_SHIFT'] = sheet_shift
    try:
        sheet = fr(DAZE_FRAMES[0]) >> 8
        daze_lo = fr(0x4125)
        assert len({fr(f) >> 8 for f in DAZE_FRAMES}) == 1
    finally:
        globals()['SHEET_SHIFT'] = keep
    a = Asm(0)
    a.w(0x4A6E, 0x1CD4)                  # tst.w $1CD4(a6)     a finisher owns his frames
    a.bcc(0x66, 'x')
    a.w(0x2069, 0x008C)                  # movea.l $8C(a1),a0  the other's Vendetta starts before its flag
    a.w(0x0C28, VENDETTA_MOVE, 0x00BF)   # cmpi.b #$3C,$BF(a0)
    a.bcc(0x67, 'x')
    a.w(0x0829, 0x0001, 0x0101)          # btst #1,$101(a1)    held by a grab
    a.bcc(0x66, 'x')
    # frozen (Sub-Zero's ice: emit_freeze holds him in $1F in the pose he was in, every call): only
    # while his frame is one of the daze's - EC's dizzy frames and the sway's (41:25-41:4C) - else
    # the sway and the frozen pose took turns (he wiggled while frozen)
    a.w(0x3029, 0x001A)                  # move.w $1A(a1),d0
    a.w(0x0440, daze_lo)                 # subi.w #41:25,d0    (his numbering)
    a.w(0x0C40, 0x4C - 0x25)             # cmpi.w #$27,d0
    a.bcc(0x62, 'x')                     # bhi: not a daze frame
    assert not 0x2E188 & 0x20 and 0x2E330 & 0x20
    a.w(0x3009)                          # move.w a1,d0        P1 $2E188 / P2 $2E330:
    a.w(0x0240, 0x0020)                  # andi.w #$20,d0      bit 5 says which
    a.w(0xE848)                          # lsr.w #4,d0         0 / 2
    at = len(a.out)
    a.w(0x41FB, 0x0000)                  # lea cnt(pc,d0.w),a0 his counter
    a.w(0x0C29, DIZZY, 0x00BF)           # cmpi.b #$1F,$BF(a1) dazed (the move's low byte)?
    a.bcc(0x67, 'dz')
    a.w(0x4250)                          # clr.w (a0)          no: the next daze starts at pose 0
    a.w(0x4E75)
    a.label('dz')
    a.w(0x137C, sheet, 0x001A)           # move.b #sheet,$1A(a1)
    a.w(0x3010)                          # move.w (a0),d0
    a.w(0x5340)                          # subq.w #1,d0
    a.bcc(0x6A, 'i')                     # bpl
    a.w(0x7000 | (len(DAZE_SEQ) - 1))    # moveq #len-1,d0
    a.label('i')
    a.w(0x3080)                          # move.w d0,(a0)
    a.w(0x4EF9); a.l(DAZE_TAIL['at'])    # jmp daze_tail       his frame
    a.label('x')
    a.w(0x4E75)
    cnt = len(a.out)
    a.w(0, 0)                            # the counters
    out = bytearray(a.build())
    disp = cnt - (at + 2)
    assert 0 < disp < 0x80
    out[at + 3] = disp
    assert DAZE_PAD + len(out) <= VROOM[1][1], 'daze_pad past the victory room'
    return bytes(out)


def daze_table():
    """daze_tail's table: the sway's frame (low byte, any fighter's numbering) per call."""
    t = bytes(DAZE_FRAMES[k] & 0xFF for k in reversed(DAZE_SEQ))    # (counted down)
    assert len(t) <= 0x7E
    return t + bytes(len(t) % 2)


def daze_tail():
    """daze_pad's end, shared (PLYR.CO's gap): d0 = the count, a1 = the fighter."""
    out = bytearray.fromhex('137b0000001b' '4e75')   # move.b tbl(pc,d0.w),$1B(a1) ; rts
    out[3] = len(out) - 2                # tbl: just after (the extension word is at +2)
    return bytes(out) + daze_table()


def johnny_shadow_extra(first_tile):
    """Static effect pieces outside Johnny's retained shadow-kick pose."""
    import numpy as np
    import scorpion_full as sf, mkprojectile
    from inputs import ROOT
    poses, anchors, cram = sf.load_action(ROOT, 'shadowkick')
    full, (ax, ay) = sf.scale_pose(poses[15], anchors[15], cram)
    full = sf.remap_colours(full)
    x0, y0, x1, y1 = sf.kept_window(full, (ax, ay))
    tiles, pieces = [], []
    lost = np.zeros_like(full)
    lost[:, :x0] = full[:, :x0]
    lost[:, x1:] = full[:, x1:]
    lost[:y0, x0:x1] = full[:y0, x0:x1]
    lost[y1:, x0:x1] = full[y1:, x0:x1]
    assert not lost[:y0, x0:x1].any() and not lost[y1:, x0:x1].any()
    for band, xbase in ((lost[:, :x0], 0), (lost[:, x1:], x1)):
        if not band.any(): continue
        yy, xx = np.nonzero(band)
        xlo, xhi = int(xx.min()) + xbase, int(xx.max()) + 1 + xbase
        ylo, yhi = int(yy.min()), int(yy.max()) + 1
        img = full[ylo:yhi, xlo:xhi]
        t, rec = mkprojectile.tiles_and_pieces(img, ax - xlo, ay - sf.FOOT_DROP - ylo,
                                                first_tile + len(tiles), skip_empty=True)
        tiles.extend(t); pieces.extend(rec)
    yy, xx = np.nonzero(lost)
    img = lost[yy.min():yy.max()+1, xx.min():xx.max()+1]
    record = mkprojectile.frame_record(img, ax - int(xx.min()), ay - sf.FOOT_DROP - int(yy.min()), pieces)
    assert first_tile + len(tiles) <= 91, (first_tile, len(tiles))
    return tiles, record


def emit_reptile_spear(a):
    """rs_drive (a1 = Reptile, every call of his input task): Scorpion's spear pull and
    daze (r_drag's, which only Scorpion's full block has, run for his victim) from
    Reptile's side - a3 = his opponent. While the victim stands, where his move task
    resumes is kept; the spear ($34) stuck in him (reeling) cancels his knock-back,
    holds him while Reptile's frame is in the rope's hold (42:2E-42:31), then drags him
    PULL_SPEED px a call to PULL_GAP and dazes him (EC's dizzy) for DAZE_CALLS calls;
    then he is sent back to standing with EC's dizzy-exit cleanup. Saves what it uses."""
    a.label('rs_drive')
    a.w(0x48E7, 0x80B0)                  # movem.l d0/a0/a2-a3,-(sp)
    import patches                       # missed / blocked: his bare throw, as Scorpion's (MK draws
    emit_spear_miss(a, 'rsm_', patches.REPTILE.spear_bare)   #  Reptile with Scorpion's sprites)
    a.pcrel(0x45FA, 'rs_v')              # lea rs_v(pc),a2     +0 his idle PC, +4 dazed, +8 calls
    # the CPU (CHX.AI knows Blade's $34 and $35 only): every other spear it starts is
    # the ice blast instead (MK's Reptile throws both) - his move task is sent back to
    # Blade's special dispatcher with ICE_MOVE (as Kano's queued knife: g_kstart)
    a.w(0x0C69, SPEAR_MOVE, 0x00BE)      # cmpi.w #$34,$BE(a1)
    a.bcc(0x67, 'rs_c34')
    a.w(0x426A, 0x000C)                  # clr.w 12(a2)        (not in it: the next one is new)
    a.w(0x426A, 0x0010)                  # clr.w 16(a2)        its sounds still to play
    a.w(0x426A, 0x0012)                  # clr.w 18(a2)        where its victim was hit: not yet seen
    a.bcc(0x60, 'rs_cx')
    a.label('rs_c34')
    a.w(0x4A69, 0x012A)                  # tst.w $12A(a1)      the CPU's?
    a.bcc(0x67, 'rs_cx')
    a.w(0x4A6A, 0x000C)                  # tst.w 12(a2)        seen this one already
    a.bcc(0x66, 'rs_cx')
    a.w(0x357C, 0x0001, 0x000C)          # move.w #1,12(a2)
    a.w(0x086A, 0x0000, 0x000B)          # bchg #0,11(a2)      every other one
    a.bcc(0x66, 'rs_cx')                 # (bit was set: this one stays the spear)
    a.w(0x2069, 0x0088)                  # movea.l $88(a1),a0
    a.w(0x2050)                          # movea.l (a0),a0     his move task
    a.pcrel(0x47FA, 'rs_ice')            # lea rs_ice(pc),a3
    a.w(0x214B, 0x0004)                  # move.l a3,4(a0)     resumes there
    a.w(0x4268, 0x0008)                  # clr.w 8(a0)         at once
    a.label('rs_cx')
    # MK's Reptile throws ~4.5 projectiles a minute (mk_fidelity_spec 1), his AI ~1.3: while
    # the CPU's Reptile stands, every RS_EVERY calls he starts one himself - the spear when
    # his opponent is in its reach, else the ice blast (it crosses the screen)
    a.w(0x4A69, 0x012A)                  # tst.w $12A(a1)      the CPU's?
    a.bcc(0x67, 'rs_ax')
    a.w(0x2079); a.l(0x30000 + CLOCK_OBJ)   # movea.l clock.l,a0  the round clock: still on 99
    a.w(0x0C68, 0x0099, CLOCK_TIME)      # cmpi.w #$99,time(a0)   until FIGHT (a special forced in the
    a.bcc(0x67, 'rs_ax')                 #  round's intro held it there: round 2 never started)
    a.w(0x4A69, 0x00BE)                  # tst.w $BE(a1)       standing
    a.bcc(0x66, 'rs_ax')
    a.w(0x526A, 0x000E)                  # addq.w #1,14(a2)    calls standing
    a.w(0x0C6A, RS_EVERY, 0x000E)        # cmpi.w #n,14(a2)
    a.bcc(0x65, 'rs_ax')                 # bcs: not yet
    a.w(0x426A, 0x000E)                  # clr.w 14(a2)
    a.w(0x2069, 0x008C)                  # movea.l $8C(a1),a0
    a.w(0x3029, 0x004E)                  # move.w $4E(a1),d0
    a.w(0x9068, 0x004E)                  # sub.w $4E(a0),d0    apart
    a.bcc(0x6A, 'rs_ap')                 # bpl
    a.w(0x4440)                          # neg.w d0
    a.label('rs_ap')
    a.pcrel(0x47FA, 'rs_ice')            # lea rs_ice(pc),a3   far: the ice blast
    a.w(0x0C40, RS_REACH)                # cmpi.w #reach,d0
    a.bcc(0x6E, 'rs_ago')                # bgt
    a.w(0x086A, 0x0000, 0x000B)          # bchg #0,11(a2)      near: spear and ice by turns
    a.bcc(0x67, 'rs_ago')                # (bit was clear: the ice blast)
    a.pcrel(0x47FA, 'rs_spr')            # lea rs_spr(pc),a3   the spear
    a.w(0x357C, 0x0001, 0x000C)          # move.w #1,12(a2)    (seen: no ice conversion)
    a.label('rs_ago')
    a.w(0x2069, 0x0088)                  # movea.l $88(a1),a0
    a.w(0x2050)                          # movea.l (a0),a0     his move task
    a.w(0x214B, 0x0004)                  # move.l a3,4(a0)
    a.w(0x4268, 0x0008)                  # clr.w 8(a0)
    a.label('rs_ax')
    a.w(0x2669, 0x008C)                  # movea.l $8C(a1),a3  the victim
    a.w(0x206B, 0x0088)                  # movea.l $88(a3),a0
    a.w(0x2050)                          # movea.l (a0),a0     his move task
    a.w(0x4A6B, 0x00BE)                  # tst.w $BE(a3)       standing?
    a.bcc(0x66, 'rs_ni')
    a.w(0x24A8, 0x0004)                  # move.l 4(a0),(a2)   where he resumes
    a.label('rs_ni')
    a.w(0xB7EA, 0x0004)                  # cmpa.l 4(a2),a3     dazed by the spear?
    a.bcc(0x66, 'rs_nd')
    a.w(0x536A, 0x0008)                  # subq.w #1,8(a2)
    a.bcc(0x66, 'rs_nd')
    a.w(0x42AA, 0x0004)                  # clr.l 4(a2)         daze over:
    a.w(0x0C6B, DIZZY, 0x00BE)           # cmpi.w #$1F,$BE(a3) (still dizzy, not hit out of it)
    a.bcc(0x66, 'rs_nd')
    a.w(0x4A92)                          # tst.l (a2)          (never seen standing: leave him)
    a.bcc(0x67, 'rs_nd')
    a.w(0x2152, 0x0004)                  # move.l (a2),4(a0)   back to standing
    a.w(0x4268, 0x0008)                  # clr.w 8(a0)
    a.w(0x426B, 0x00BE)                  # clr.w $BE(a3)
    a.w(0x08AB, 0x0003, 0x0101)          # bclr #3,$101(a3)    EC's dizzy-exit cleanup (BLA.CO $22850)
    a.w(0x08AB, 0x0007, 0x011A)          # bclr #7,$11A(a3)
    a.w(0x08AB, 0x0005, 0x00F7)          # bclr #5,$F7(a3)
    a.label('rs_nd')
    a.w(0x0C69, SPEAR_MOVE, 0x00BE)      # cmpi.w #$34,$BE(a1) his spear
    a.bccw(0x66, 'rs_out')
    a.w(0x4A6B, 0x0076)                  # tst.w $76(a3)       knocked out by it: EC's KO
    a.bccw(0x67, 'rs_out')
    a.w(0x302B, 0x00BE)                  # move.w $BE(a3),d0
    a.w(0x0440, HIT_FIRST)               # subi.w #first,d0
    a.w(0x0C40, HIT_LAST - HIT_FIRST)    # cmpi.w #n,d0
    a.bccw(0x62, 'rs_out')               # bhi: not reeling
    if RS_SOUNDS:                        # MK: the victim screams at the hit (a man's or a woman's)
        a.w(0x08EA, 0x0000, 0x0011)      # bset #0,17(a2)      (once a throw)
        a.bcc(0x66, 'rs_said')
        a.w(0x48E7, 0xFFFE)              # movem.l d0-d7/a0-a6,-(sp)
        a.w(0x322B, 0x004C)              # move.w $4C(a3),d1   the victim
        a.w(0x203C); a.l(FEMALE_MASK)    # move.l #women,d0
        a.w(0x0300)                      # btst d1,d0
        a.bcc(0x66, 'rs_sf')
        a.w(0x303C, RS_SOUNDS['scream_m'])   # move.w #MALEHURT,d0
        a.bcc(0x60, 'rs_sp')
        a.label('rs_sf')
        a.w(0x303C, RS_SOUNDS['scream_f'])   # move.w #GIRLHURT,d0
        a.label('rs_sp')
        a.jsr(0x6D58)
        a.w(0x4CDF, 0x7FFF)              # movem.l (sp)+,d0-d7/a0-a6
        a.label('rs_said')
    # speared in the air (decided at the first reeling call): EC's knockdown takes him - no hold, pull
    # or daze (dazed mid-fall, EC's landing code looped, its thud flooding the sound queue: a hang)
    a.w(0x4A2A, 0x0013)                  # tst.b 19(a2)
    a.bcc(0x66, 'rs_dk')
    a.w(0x157C, 0x0001, 0x0013)          # move.b #1,19(a2)    on the floor ...
    a.w(0x302B, 0x0052)                  # move.w $52(a3),d0
    a.w(0x5840)                          # addq.w #4,d0
    a.w(0xB079); a.l(0x30000 + 0x1496)   # cmp.w floor.l,d0
    a.bcc(0x6C, 'rs_dk')                 # bge
    a.w(0x157C, 0x0002, 0x0013)          # move.b #2,19(a2)    ... or in the air
    a.label('rs_dk')
    a.w(0x0C2A, 0x0002, 0x0013)          # cmpi.b #2,19(a2)
    a.bccw(0x67, 'rs_out')
    a.w(0x42AB, 0x00C6)                  # clr.l $C6(a3)       no knock-back
    a.w(0x3029, 0x001A)                  # move.w $1A(a1),d0   his frame: only after the rope's hit
    emit_spear_phase(a, 'rs_')           #  (a hang: a knocked-down Kano 'reeling' at the
    a.label('rs_pull')                   #  spear's start was dazed lying - EC's landing then looped)
    if RS_SOUNDS:                        # GET OVER HERE as he yanks (MK)
        a.w(0x08EA, 0x0001, 0x0011)      # bset #1,17(a2)
        a.bcc(0x66, 'rs_ysaid')
        a.w(0x48E7, 0xFFFE)              # movem.l d0-d7/a0-a6,-(sp)
        a.w(0x303C, RS_SOUNDS['yank'])   # move.w #GETOHERE,d0
        a.jsr(0x6D58)
        a.w(0x4CDF, 0x7FFF)              # movem.l (sp)+,d0-d7/a0-a6
        a.label('rs_ysaid')
    a.w(0x3769, 0x00B6, 0x00B6)          # move.w $B6(a1),$B6(a3)  along the floor
    a.w(0x3769, 0x00B6, 0x0052)          # move.w $B6(a1),$52(a3)
    a.w(0x302B, 0x00B2)                  # move.w $B2(a3),d0
    a.w(0x9069, 0x00B2)                  # sub.w $B2(a1),d0    gap (victim - Reptile)
    a.bcc(0x6A, 'rs_right')              # bpl
    a.w(0x4440)                          # neg.w d0
    a.w(0x0C40, PULL_GAP)
    a.bcc(0x6F, 'rs_near')               # ble
    a.w(0x066B, PULL_SPEED, 0x00B2)      # addi.w #SPEED,$B2(a3)
    a.w(0x066B, PULL_SPEED, 0x004E)      # addi.w #SPEED,$4E(a3)
    a.bcc(0x60, 'rs_out')
    a.label('rs_right')
    a.w(0x0C40, PULL_GAP)
    a.bcc(0x6F, 'rs_near')
    a.w(0x046B, PULL_SPEED, 0x00B2)      # subi.w #SPEED,$B2(a3)
    a.w(0x046B, PULL_SPEED, 0x004E)      # subi.w #SPEED,$4E(a3)
    a.bcc(0x60, 'rs_out')
    a.label('rs_near')                   # yanked in: dazed (his move task resumes in EC's dizzy)
    a.w(0x217C); a.l(DIZZY_CODE); a.w(0x0004)   # move.l #dizzy,4(a0)
    a.w(0x4268, 0x0008)                  # clr.w 8(a0)
    a.w(0x254B, 0x0004)                  # move.l a3,4(a2)
    a.w(0x357C, DAZE_CALLS, 0x0008)      # move.w #calls,8(a2)
    a.label('rs_out')
    a.w(0x4CDF, 0x0D01)                  # movem.l (sp)+,d0/a0/a2-a3
    a.w(0x4E75)
    a.label('rs_spr')                    # (his move task, a5 = him) the spear, as if chosen
    a.w(0x7000 | SPEAR_MOVE)             # moveq #$34,d0
    disp = 0x2206 - (EXT_OFF + len(a.out) + 2)
    a.w(0x6000, disp & 0xFFFF)           # bra.w Blade module's special dispatcher
    a.label('rs_ice')                    # (his move task, a5 = him) the ice blast, as if chosen
    a.w(0x7000 | ICE_MOVE)               # moveq #$31,d0
    disp = 0x2206 - (EXT_OFF + len(a.out) + 2)
    a.w(0x6000, disp & 0xFFFF)           # bra.w Blade module's special dispatcher
    a.label('rs_v')
    a.l(0); a.l(0); a.w(0); a.w(0); a.w(0); a.w(0); a.w(0); a.w(0)   # +10 toggle (bit 0 of +11), +12 this $34 seen,
                                                      # +14 calls the CPU's Reptile has stood, +16 sounds
                                                      #  played this throw (bit 0 the scream, 1 the yank's line),
                                                      # +19 its victim hit on the floor (1) or in the air (2)


def low_jump(a, mk_dir):
    """His jump drive (code and tables) for the module's low room (GEN_LOW, written by patches /
    build), bsr'd from r_jumpup in block a."""
    lo = Asm(0)
    _f, _b, _ = jump_plan(mk_dir)
    emit_jump_drive(lo, _f, _b, jump_up_plan(mk_dir))
    GEN_LOW.update(off=JUMP_LOW_OFF, data=lo.build())
    assert JUMP_LOW_OFF + len(GEN_LOW['data']) <= JUMP_LOW_END, \
        f'{mk_dir}: low jump drive over by {JUMP_LOW_OFF + len(GEN_LOW["data"]) - JUMP_LOW_END}'
    a.labels['g_jump'] = JUMP_LOW_OFF - EXT_OFF


def emit_jump_drive(a, fwd, back, up, tail=None):
    """g_jump (from r_jumpup: the step loader has just put EC's frame in $1A; a5 = him;
    d0/a0 free): MK's roll on a forward or back jump (EC's jump is one upright
    animation). While he is in the air in EC's move 8 with an x speed, $1A becomes the
    roll's frame (jump_plan) for the calls (2 frames) since he left the floor - by the sub
    CPU's frame counter, as this hook isn't called on a beat - forward or back by his speed
    against his facing. A jump attack (another move) or the landing ends it; any other
    call resets it. Landing from it (move 8 or $28 on the floor, still rolling): MK's FEETLAND
    (FEET_SOUND); any other move on the floor (a jump attack's landing, a knockdown, a hit) ends
    it silently. Inline, the tables are a pose index a call (bytes) and the poses (words): his
    module's low room was full with a word a call (132 bytes)."""
    idx = tail is None
    if idx:
        poses = sorted(set(fwd + back + up), key=(fwd + back + up).index)
        assert len(poses) <= 127
    a.label('g_jump')
    a.w(0x2F01)                          # move.l d1,-(sp)
    a.pcrel(0x41FA, 'jr_c')              # lea jr_c(pc),a0     +0 rolling, +2 its first frame
    a.w(0x0C2D, 0x0008, 0x00BF)          # cmpi.b #8,$BF(a5)   (EC's move 8; the high byte is its request flag)
    a.bcc(0x67, 'jr_m8')
    a.w(0x0C2D, 0x0028, 0x00BF)          # cmpi.b #$28,$BF(a5) Z in a moving jump (MK's Block: nothing -
    a.bcc(0x66, 'jr_ot')                 #  patches.mk_air_block; EC stays in it, on its jump frames, to the
    a.label('jr_m8')                     #  ground): the roll goes on. Any other move keeps the roll's count
    a.w(0x302D, 0x0052)                  # move.w $52(a5),d0
    a.w(0xB06E, 0x1496)                  # cmp.w $1496(a6),d0  above the floor? (a6: EC's base in a move task)
    a.bcc(0x6D, 'jr_air')                # blt: in the air
    if FEET_SOUND:                       # on it - a jump's landing: MK's feet on the floor (once: rolling clears)
        a.w(0x4A50)                      # tst.w (a0)
        a.bcc(0x67, 'jr_no')
        a.w(0x48E7, 0xFFFE)              # movem.l d0-d7/a0-a6,-(sp)
        a.w(0x303C, FEET_SOUND)          # move.w #FEETLAND,d0
        a.jsr(0x6D58)
        a.w(0x4CDF, 0x7FFF)              # movem.l (sp)+,d0-d7/a0-a6
    a.label('jr_no')
    a.w(0x4250)                          # clr.w (a0)
    a.label('jr_x')
    a.w(0x221F)                          # move.l (sp)+,d1
    a.w(0x4E75)
    a.label('jr_ot')                     # another move: in the air the roll's count is kept; on the floor
    if FEET_SOUND:                       #  the jump is over, silently (a jump attack's landing, a knockdown,
        a.w(0x302D, 0x0052)              #  a hit: still rolling, his next walk played the landing)
        a.w(0xB06E, 0x1496)              # move.w $52(a5),d0 / cmp.w $1496(a6),d0
        a.bcc(0x6C, 'jr_no')             # bge
    a.bcc(0x60, 'jr_x')
    a.label('jr_air')
    # EC's walk is move 8 too, and its steps bob him above the floor: the roll showed mid-walk (Kano's
    # forward walk: a roll pose for 6 frames every cycle). Only EC's jump frames (just loaded) count:
    # 41:00-41:04 rising, 40:00 falling
    a.w(0x302D, 0x001A)                  # move.w $1A(a5),d0
    a.w(0x0C40, fr(0x4000))              # cmpi.w #40:00,d0
    a.bcc(0x67, 'jr_ec')
    a.w(0x0440, fr(0x4100))              # subi.w #41:00,d0
    a.w(0x0C40, 0x0004)                  # cmpi.w #4,d0
    a.bcc(0x62, 'jr_no')                 # bhi: a walk frame
    a.label('jr_ec')
    a.w(0x302D, 0x00C6)                  # move.w $C6(a5),d0   x speed (0: straight up)
    a.w(0x082D, 0x0003, 0x0020)          # btst #3,$20(a5)     facing left?
    a.bcc(0x67, 'jr_r')
    a.w(0x4440)                          # neg.w d0
    a.label('jr_r')
    a.w(0x322E, 0x800E)                  # move.w -$7FF2(a6),d1  the sub CPU's frame counter
    a.w(0x4A50)                          # tst.w (a0)
    a.bcc(0x66, 'jr_go')
    a.w(0x5250)                          # addq.w #1,(a0)      rolling
    a.w(0x3141, 0x0002)                  # move.w d1,2(a0)
    if JUMP_GRUNT:                       # off the floor: MK's grunt (once: rolling is set now)
        a.w(0x48E7, 0xFFFE)              # movem.l d0-d7/a0-a6,-(sp)
        a.w(0x303C, JUMP_GRUNT)          # move.w #MALEJUMP,d0
        a.jsr(0x6D58)
        a.w(0x4CDF, 0x7FFF)              # movem.l (sp)+,d0-d7/a0-a6
    a.w(0x4A40)                          # tst.w d0            (straight up: its height is the script's)
    a.bcc(0x67, 'jr_go')
    a.w(0x0C6D, -math.ceil(jump_up_launch(SCORPION_ID)[0] - 2.5) & 0xFFFF, 0x00CA)
    a.bcc(0x6E, 'jr_go')                 # cmpi.w #takeoff,$CA(a5) / bgt: only at the takeoff (rising at the
                                         #  launch speed): a jump kick leaves move 8 and comes back - each return
                                         #  launched him again: a jump kick kept going up)
    a.w(0x2B7C); a.l(-round(JUMP_VY_FWD[SCORPION_ID] * 0x10000) & 0xFFFFFFFF); a.w(0x00CA)   # MK's forward height
    a.w(0x2B7C); a.l(round(EC_GRAVITY * 0x10000)); a.w(0x006A)   # EC's gravity in the flight ($6A: from the script's
                                         #  header via $CE at the launch - the straight-up jump's, MK's lower)
    a.label('jr_go')
    a.w(0x9268, 0x0002)                  # sub.w 2(a0),d1
    a.w(0xE249)                          # lsr.w #1,d1         calls
    a.w(0x0C41, len(fwd) - 1)            # cmpi.w #n-1,d1
    a.bcc(0x63, 'jr_i')                  # bls
    a.w(0x7200 | (len(fwd) - 1))         # moveq #n-1,d1
    a.label('jr_i')
    if not idx:
        a.w(0xD241)                      # add.w d1,d1
    if tail is None:
        a.pcrel(0x41FA, 'jr_f')          # lea forward(pc),a0  (then back, then straight up)
    else:                                # (the tables in his .PL's tail: block room)
        a.w(0x2F09)                      # move.l a1,-(sp)
        a.w(0x224D)                      # movea.l a5,a1
        a.bccw(0x61, 'pl_tail')          # bsr pl_tail         a0 = his tail
        a.w(0x225F)                      # movea.l (sp)+,a1
        a.w(0xD0FC, tail)                # adda.w #forward,a0
    k = 1 if idx else 2                  # (an entry's bytes)
    a.w(0x4A40)                          # tst.w d0            (adda leaves the flags)
    a.bcc(0x6E, 'jr_s')                  # bgt: toward
    a.w(0xD0FC, k * len(fwd))            # adda.w #back,a0
    a.bcc(0x6D, 'jr_s')                  # blt: away
    a.w(0xD0FC, k * len(back))           # adda.w #up,a0       (0: straight up)
    a.label('jr_s')
    if idx:
        a.w(0x1230, 0x1000)              # move.b (a0,d1.w),d1 its pose (d1's high byte 0: a count < 22)
        a.w(0xD241)                      # add.w d1,d1
        a.w(0x3B7B); ext = len(a.out)    # move.w jr_p(pc,d1.w),$1A(a5)
        a.w(0x1000, 0x001A)
    else:
        a.w(0x3B70, 0x1000, 0x001A)      # move.w (a0,d1.w),$1A(a5)
    a.w(0x221F)                          # move.l (sp)+,d1     (jr_x: out of a short branch's reach)
    a.w(0x4E75)
    a.label('jr_c')
    a.w(0); a.w(0)
    if idx:
        a.label('jr_p')
        d = a.labels['jr_p'] - ext       # (d8,PC,Xn): from its extension word
        assert d <= 127, f'jump poses {d} bytes past their read'
        a.out[ext + 1] = d
        for f in poses:
            a.w(fr(f))
        a.label('jr_f')
        a.out += bytes(poses.index(f) for f in fwd + back + up)
        a.out += bytes(len(a.out) & 1)
    elif tail is None:
        a.label('jr_f')
        for f in fwd + back + up:
            a.w(fr(f))


SWEPT_DIRS = ('mk_moves', 'mk_moves_kano', 'mk_moves_johnny', 'mk_moves_liukang', 'mk_moves_subzero',
              'mk_moves_sonya')   # (MK's own fall when swept; Raiden: no .PL room)
SWEEP_MOVE = 0x13                 # the attacker's move when a sweep knocks him down (EC's and ours: crouch + C)


def low_kd(a, mk_dir):
    """His knockdown drive with its tables (inline) for the first victory room (GEN_KD, written by patches
    mk_code), called from r_jumpup / r_drag in block a."""
    lo = Asm(0)
    air, floor, _ = kd_plan(mk_dir)
    swept = kd_plan(mk_dir, 'swept')[:2] if mk_dir in SWEPT_DIRS else None
    emit_kd_drive(lo, (air, floor), swept)
    GEN_KD.update(off=VROOM[0][0], data=lo.build())
    assert VROOM[0][0] + len(GEN_KD['data']) <= VROOM[0][1], f'{mk_dir}: knockdown drive over by ' \
        f'{VROOM[0][0] + len(GEN_KD["data"]) - VROOM[0][1]}'
    a.labels['g_kd'] = VROOM[0][0] - EXT_OFF


def emit_kd_drive(a, tables=None, swept=None):
    """g_kd (a5 = him; saves what it uses): MK's knockdown (kd_plan). While he is in EC's
    knockdown ($1C): in the air (EC's flag: $F6 bit 0) MK's airborne poses by the calls since
    the launch (the sub CPU's frame counter), held on the last; on the floor MK's landing and
    getting up, by the calls since he first touched it. Run from the step loader (r_jumpup:
    after EC's frame) and every call (r_drag: EC holds one frame for the whole flight).
    Its tables are in his .PL's tail (KD_TAIL), or tables = (air, floor) inline after it."""
    if swept is not None:                # (both sets as long: the counts' clamps; the last pose held)
        na = max(len(tables[0]), len(swept[0]))
        nf = max(len(tables[1]), len(swept[1]))
        pad = lambda t, n: list(t) + [t[-1]] * (n - len(t))
        tables = (pad(tables[0], na), pad(tables[1], nf))
        swept = (pad(swept[0], na), pad(swept[1], nf))
    na, nf = KD_TAIL['n'] if tables is None else map(len, tables)
    base = KD_TAIL['off'] if tables is None else 0
    a.label('g_kd')
    a.w(0x48E7, 0xC080)                  # movem.l d0-d1/a0,-(sp)
    a.pcrel(0x41FA, 'kd_c')              # lea kd_c(pc),a0    +0 started, +2 its frame, +4 landed, +6 its frame
    a.w(0x302D, 0x00BE)                  # move.w $BE(a5),d0
    a.w(0x0240, 0x7FFF)
    a.w(0x0C40, KD_STATE)                # cmpi.w #$1C,d0
    a.bccw(0x66, 'kd_no')
    if swept is not None:                # which fall: decided on his first call down (+8), the table
        a.w(0x4A68, 0x0008)              #  offset at +10 - a sweep's (the attacker's move then) MK's
        a.bcc(0x66, 'kd_dec')            #  swept, any other his knockdown
        a.w(0x317C, 0x0001, 0x0008)      # move.w #1,8(a0)
        a.w(0x4268, 0x000A)              # clr.w 10(a0)
        a.w(0x2F09)                      # move.l a1,-(sp)
        a.w(0x226D, 0x008C)              # movea.l $8C(a5),a1  the attacker
        a.w(0x3029, 0x00BE)              # move.w $BE(a1),d0
        a.w(0x0240, 0x7FFF)              # andi.w #$7FFF,d0
        a.w(0x0C40, SWEEP_MOVE)          # cmpi.w #$13,d0
        a.w(0x225F)                      # movea.l (sp)+,a1    (flags kept)
        a.bcc(0x66, 'kd_dec')
        a.w(0x317C, 2 * (na + nf), 0x000A)   # move.w #swept,10(a0)
        a.label('kd_dec')
    a.w(0x3239); a.l(0x30000 - 0x7FF2)   # move.w frames.l,d1
    a.w(0x082D, 0x0000, 0x00F6)          # btst #0,$F6(a5)    in the air?
    a.bcc(0x67, 'kd_fl')
    a.w(0x08D0, 0x0007)                  # bset #7,(a0)       (he has been in the air: +0's top bit)
    a.label('kd_air')
    a.w(0x4A50)                          # tst.w (a0)
    a.bcc(0x66, 'kd_ag')
    a.w(0x30BC, 0x0001)                  # move.w #1,(a0)
    a.w(0x3141, 0x0002)                  # move.w d1,2(a0)
    a.w(0x4268, 0x0004)                  # clr.w 4(a0)
    a.label('kd_ag')
    a.w(0x9268, 0x0002)                  # sub.w 2(a0),d1
    a.w(0xE249)                          # lsr.w #1,d1        calls
    a.w(0x0C41, na - 1)                  # cmpi.w #n-1,d1
    a.bcc(0x63, 'kd_ai')
    a.w(0x323C, na - 1)                  # move.w #n-1,d1
    a.label('kd_ai')
    a.w(0x303C, base)                    # move.w #air,d0
    a.bcc(0x60, 'kd_set')
    a.label('kd_fl')
    # on the floor: the landing and getting up only after he has been in the air (EC flags a
    # roundhouse's knockdown airborne only some frames in: the floor's poses showed first, then the
    # flight's, then the floor's) - or, never flagged (a sweep), once the flight's poses are done
    a.w(0x4A50)                          # tst.w (a0)
    a.bcc(0x67, 'kd_air')                # beq: just down - the flight starts
    a.bcc(0x6B, 'kd_fok')                # bmi: he has flown, and landed
    a.w(0x3001)                          # move.w d1,d0
    a.w(0x9068, 0x0002)                  # sub.w 2(a0),d0
    a.w(0xE248)                          # lsr.w #1,d0        calls since he went down
    a.w(0x0C40, na - 1)                  # cmpi.w #n-1,d0
    a.bcc(0x63, 'kd_air')                # bls: the flight's poses still
    a.label('kd_fok')
    a.w(0x4A68, 0x0004)                  # tst.w 4(a0)
    a.bcc(0x66, 'kd_fg')
    a.w(0x317C, 0x0001, 0x0004)          # move.w #1,4(a0)
    a.w(0x3141, 0x0006)                  # move.w d1,6(a0)
    a.label('kd_fg')
    a.w(0x9268, 0x0006)                  # sub.w 6(a0),d1
    a.w(0xE249)                          # lsr.w #1,d1
    a.w(0x0C41, nf - 1)
    a.bcc(0x63, 'kd_f0')
    a.w(0x323C, nf - 1)
    a.label('kd_f0')                     # out of the round (no health, or a finisher): no getting up -
    mk_dir = MK_DIR_BY_ID[SCORPION_ID]   #  held on the flat pose (KD_FLAT)
    fk = KD_FLAT[(mk_dir, 'knockdown')]
    fs = KD_FLAT.get((mk_dir, 'swept'), fk) if swept is not None else fk
    assert fk < 128 and fs < 128
    a.w(0x4A6D, 0x0076)                  # tst.w $76(a5)       health
    a.bcc(0x6F, 'kd_ko')                 # ble
    a.w(0x4A6E, 0x1CD4)                  # tst.w $1CD4(a6)     a finisher
    a.bcc(0x67, 'kd_fi')                 # beq: in the round
    a.label('kd_ko')
    a.w(0x7000 | fk)                     # moveq #flat,d0
    if fs != fk:
        a.w(0x4A68, 0x000A)              # tst.w 10(a0)        the swept set?
        a.bcc(0x67, 'kd_kk')
        a.w(0x7000 | fs)                 # moveq #flat (swept),d0
        a.label('kd_kk')
    a.w(0xB240)                          # cmp.w d0,d1
    a.bcc(0x63, 'kd_fi')                 # bls: not there yet
    a.w(0x3200)                          # move.w d0,d1
    a.label('kd_fi')
    a.w(0x303C, base + 2 * na)           # move.w #floor,d0
    a.label('kd_set')
    a.w(0xD241)                          # add.w d1,d1
    a.w(0xD041)                          # add.w d1,d0
    if swept is not None:
        a.w(0xD068, 0x000A)              # add.w 10(a0),d0     (the swept set)
    if tables is None:
        a.w(0x2F09)                      # move.l a1,-(sp)
        a.w(0x224D)                      # movea.l a5,a1
        a.bccw(0x61, 'pl_tail')          # bsr pl_tail         a0 = his tail
        a.w(0x225F)                      # movea.l (sp)+,a1
    else:
        a.pcrel(0x41FA, 'kd_tab')        # lea kd_tab(pc),a0
    a.w(0x3B70, 0x0000, 0x001A)          # move.w (a0,d0.w),$1A(a5)
    a.bcc(0x60, 'kd_x')
    a.label('kd_no')
    a.w(0x4290)                          # clr.l (a0)
    a.w(0x42A8, 0x0004)                  # clr.l 4(a0)
    if swept is not None:
        a.w(0x42A8, 0x0008)              # clr.l 8(a0)
    a.label('kd_x')
    a.w(0x4CDF, 0x0103)                  # movem.l (sp)+,d0-d1/a0
    a.w(0x4E75)
    a.label('kd_c')
    a.l(0); a.l(0)
    if swept is not None:
        a.l(0)
    if tables is not None:
        a.label('kd_tab')
        for f in tables[0] + tables[1] + (swept[0] + swept[1] if swept is not None else []):
            a.w(fr(f))                   # (his numbering, as the tail's)


def emit_johnny_shadow(a):
    """A static effect object supplies the clipped pieces of flight pose 15."""
    import mkdeath, mkprojectile
    frame = len(mkprojectile.PROJ['johnny'][1]) + len(mkprojectile.PROJ['johnny'][2]) + len(Z_NAMES) + len(mkdeath.FILES)
    a.label('jk_drive')
    a.w(0x48E7, 0xFFFE)                 # movem.l d0-d7/a0-a6,-(sp)
    a.pcrel(0x45FA, 'jk_objects')        # a2 = this player's pointer
    a.w(0xB3FC); a.l(0x2E188)
    a.bcc(0x67, 'jk_side')
    a.w(0x588A)                         # addq.l #4,a2
    a.label('jk_side')
    a.w(0x3029, 0x00BE); a.w(0x0240, 0x7FFF)
    a.w(0x0C40, 0x0035)
    a.bcc(0x67, 'jk_flying')
    a.w(0x4A92)                         # tst.l (a2)
    a.bccw(0x67, 'jk_exit')
    a.w(0x2052)                         # movea.l (a2),a0
    a.w(0x2F0A)                         # retain the pointer slot through deletion
    a.w(0x08E8, 0x0002, 0x0082)         # bset #2,$82(a0): delete it and its task, as EC
                                        #  does (its object loop; not $6A14: notes)
    a.w(0x245F)                         # restore a2
    a.w(0x4292)                         # clr.l (a2)
    a.bccw(0x60, 'jk_exit')
    a.label('jk_flying')
    a.w(0x4A92)
    a.bcc(0x66, 'jk_have')
    a.w(0x48E7, 0xFFFE)
    a.w(0x2A49)                         # a5 = fighter, owner
    a.pcrel(0x43FA, 'jk_desc')
    a.w(0x303C, PJ_TYPE); a.w(0x7600)
    a.w(0x2F0A)                         # keep the slot pointer across spawn
    a.jsr(0x6BBA)
    a.w(0x245F)                         # movea.l (sp)+,a2; flags preserved
    a.bcc(0x65, 'jk_spawned')
    a.w(0x2488)                         # move.l a0,(a2)
    a.pcrel(0x43FA, 'gk_park')
    a.w(0x2468, 0x0088)
    a.w(0x2549, 0x0004)                 # park its task
    a.w(0x316D, 0x001E, 0x001E)       # fighter's palette
    a.label('jk_spawned')
    a.w(0x4CDF, 0x7FFF)
    a.w(0x4A92)
    a.bccw(0x67, 'jk_exit')
    a.label('jk_have')
    a.w(0x2652)                         # a3 = effect object
    # The effect is displayed two frames after this update, as the fighter
    # advances from 41:30 to the clipped 41:31 frame.
    a.w(0x0C69, fr(0x4130), 0x001A)
    a.bcc(0x67, 'jk_show')
    a.w(0x377C, 0xFF00, 0x0052)       # hide until the cropped frame
    a.bcc(0x60, 'jk_exit')
    a.label('jk_show')
    a.w(0x377C, fr_fx(frame), 0x001A)
    a.w(0x3769, 0x0020, 0x0020)       # same facing
    a.w(0x3769, 0x004E, 0x004E)
    a.w(0x3769, 0x0052, 0x0052)
    a.label('jk_exit')
    a.w(0x4CDF, 0x7FFF)
    a.w(0x4E75)
    a.label('jk_desc')
    a.out += szf_head_desc()
    a.label('jk_objects')
    a.l(0); a.l(0)


# Sonya's square wave flies over a standing opponent's head (MK CD, vs Sub-Zero: she
# passes over him unhit and lands behind; it catches jumpers). Higher than a frame
# reaches over its anchor (127 px), so SHE is lifted: during her dash (move $35) her
# ground y ($B6, which EC copies to $52 each frame) is the floor ($1496(a6)) less MK's
# height for the step's pose (feet above MK's floor x 1.08: patches.SQUARE_STEPS
# frames: 41:30 pose 10, 41:31 pose 11, 41:61 pose 12, 41:62 pose 13, 41:32 pose 17,
# 41:34 pose 18), and the floor again after it. Her hit boxes go up with her.
SQ_LIFT = ((0x30, 27), (0x31, 93), (0x61, 125), (0x62, 119), (0x32, 73), (0x34, 70))
SQ_FLAG = 63                  # vars byte: bit 0/1 = player 1/2 lifted by us


def emit_sq_lift(a):
    """(a1 = Sonya, each call) Her square wave's height (SQ_LIFT). Uses a0/a2."""
    a.pcrel(0x45FA, 'vars')              # lea vars(pc),a2
    a.w(0x48E7, 0xE000)                  # movem.l d0-d2,-(sp)
    a.w(0x7000)                          # moveq #0,d0         her bit
    a.w(0xB3FC); a.l(0x2E188)            # cmpa.l #P1,a1
    a.bcc(0x67, 'sq_p')
    a.w(0x7001)                          # moveq #1,d0
    a.label('sq_p')
    a.w(0x3229, 0x00BE)                  # move.w $BE(a1),d1
    a.w(0x0241, 0x7FFF)                  # andi.w #$7FFF,d1
    a.w(0x0C41, 0x0035)                  # cmpi.w #$35,d1      her dash: the square wave
    a.bcc(0x66, 'sq_dn')
    a.w(0x7200)                          # moveq #0,d1
    a.w(0x1229, 0x001B)                  # move.b $1B(a1),d1   the step's frame
    a.pcrel(0x41FA, 'sq_tab')            # lea sq_tab(pc),a0
    a.label('sq_lp')
    a.w(0x3418)                          # move.w (a0)+,d2
    a.bcc(0x6B, 'sq_0')                  # bmi: not listed: on the floor
    a.w(0xB441)                          # cmp.w d1,d2
    a.bcc(0x67, 'sq_f')
    a.w(0x5488)                          # addq.l #2,a0
    a.bcc(0x60, 'sq_lp')
    a.label('sq_f')
    a.w(0x3410)                          # move.w (a0),d2      her height
    a.bcc(0x60, 'sq_h')
    a.label('sq_0')
    a.w(0x7400)                          # moveq #0,d2
    a.label('sq_h')
    a.w(0x4A42)                          # only while actually airborne
    a.bcc(0x67, 'sq_nohit')
    a.w(0x0829, 0x0005, 0x0100)         # pending hit reaction?
    a.bcc(0x67, 'sq_nohit')
    a.w(0x0C69, 0x001A, 0x0118)         # ordinary hit reaction
    a.bcc(0x66, 'sq_nohit')
    a.w(0x5469, 0x0118)                  # addq.w #2 -> knockdown
    a.label('sq_nohit')
    a.w(0x01EA, SQ_FLAG)                 # bset d0,63(a2)
    a.w(0x4442)                          # neg.w d2
    a.w(0xD46E, 0x1496)                  # add.w $1496(a6),d2  the floor
    a.bcc(0x60, 'sq_set')
    a.label('sq_dn')
    a.w(0x012A, SQ_FLAG)                 # btst d0,63(a2)
    a.bcc(0x67, 'sq_x')                  # not lifted by us
    a.w(0x0C41, 0x001C)                  # knockdown: EC already applies its own arc
    a.bcc(0x66, 'sq_floor')
    a.w(0x01AA, SQ_FLAG)                 # release the lift without moving her
    a.bcc(0x60, 'sq_x')
    a.label('sq_floor')
    a.w(0x01AA, SQ_FLAG)                 # bclr d0,63(a2)
    a.w(0x342E, 0x1496)                  # move.w $1496(a6),d2
    a.label('sq_set')
    a.w(0x3342, 0x00B6)                  # move.w d2,$B6(a1)
    a.w(0x3342, 0x0052)                  # move.w d2,$52(a1)
    a.label('sq_x')
    a.w(0x4CDF, 0x0007)                  # movem.l (sp)+,d0-d2
    room_put(a, 'sq_tab', b''.join(struct.pack('>HH', f, h) for f, h in SQ_LIFT) + b'\xff\xff')   # (her block is full)


# The other MK fighters' specials (MK1's inputs) on Blade's moves: $34 his
# projectile, $35 his dash. (dir1, dir2, button / DIR3|dir / 0, move)
GENERIC_MOVES = {
    22: MK_MOVES,                        # Scorpion (the Senator's slot): spear, teleport punch (his full block runs r_gmoves too)
    19: [(DOWN, FWD, PUNCH, 0x34),       # Raiden: lightning (down, forward + a punch)
         (BACK, BACK, DIR3 | FWD, 0x35),  #   torpedo (back, back, forward)
         (DOWN, UP, 0, RTELE_MOVE)],      #   teleport (down, up): Blade's $31, a plain script, ours
    18: [(BACK, FWD, PUNCH, 0x34),       # Johnny Cage: green bolt (back, forward + a punch)
         (BACK, FWD, LK, 0x35)],         #   shadow kick (back, forward + LK)
    20: [(DOWN, FWD, PUNCH, 0x34),       # Sub-Zero: ice blast (down, forward + a punch)
         (BACK, 0, CHORD | LK | HK, 0x35)],   #   slide (MK CD: back + LK + HK - back + LK + Block is a low kick): Blade's dash
    12: [(FWD, FWD, PUNCH, 0x34),        # Liu Kang: fireball (forward, forward + a punch)
         (FWD, FWD, HK, 0x35)],          #   flying kick (forward, forward + HK): Blade's dash
    13: [(BACK, FWD, CHORD | BLOCK, 0x34),   # Kano: knife throw (Block held: back, forward)
         (FWD, DOWN, DIR3 | BACK | UP << TAP4, 0x35)],   #   cannonball (MK CD's full circle: forward, down, back, up -
                                             #  Block held or not; three of the four, or another order: nothing)
    17: [(FWD, BACK, PUNCH, 0x35),       # Sonya: square-wave punch (forward, back + a punch): Blade's dash
         (BTN1 | HP, BACK, PUNCH, 0x34)],   #   energy rings (MK CD: high punch, back, a punch - the first is her
                                         #  jab, here as there; a low punch first, or back + a punch alone, are
                                         #  not; checked after the square wave, which ends the same way)
    26: [(DOWN, FWD, LP, ICE_MOVE),      # Reptile (MK's CPU-only secret): Sub-Zero's ice blast (on $31),
         (BACK, BACK, LP, 0x34),         #   Scorpion's spear (MK CD's Reptile throws both; LP only, as they were)
         (BACK, 0, CHORD | LK | HK, 0x35)],   #   and Sub-Zero's slide
    11: [(BACK, FWD, HP, 0x34)],         # Shang Tsung: skull volley (MK: back, back, forward + HP; only the
                                         #  CPU plays him - this is for tests driving him as player 2)
}


def r_gmoves(a, fid):
    """A generic fighter's special-move list and his copy of Blade's move
    handler (as Scorpion's in SUB.BIN, build), in his block: 'g_reg' (a1 =
    him) fills the list's absolute entry pointers (his slot's) and points
    the handler table's entry for his id at the handler. An entry: level 0,
    its progress slot, TYPE, then r_taps' four words."""
    moves = GENERIC_MOVES.get(fid, [])
    a.label('g_reg')
    if not moves:
        a.w(0x4E75)
        return
    a.pcrel(0x41FA, 'gm_list')           # lea list(pc),a0
    for i in range(len(moves)):
        a.pcrel(0x45FA, f'gm_e{i}')      # lea entry(pc),a2
        a.w(0x20CA)                      # move.l a2,(a0)+
    a.w(0x20BC); a.l(0xFFFFFFFF)         # move.l #-1,(a0)
    a.pcrel(0x41FA, 'gm_hnd')            # lea handler(pc),a0
    a.w(0x23C8); a.l(HANDLERS + 4 * (fid - 2))   # move.l a0,table+4*(id-2)
    a.w(0x4E75)
    a.label('gm_hnd')                    # Blade's handler (PLYR.CO $15604) on his list
    a.w(0x08A9, 0x0003, 0x011A)          # bclr #3,$11A(a1)
    a.pcrel(0x45FA, 'gm_list')           # lea list(pc),a2
    a.jsr(0x159D0)                       # the recogniser
    a.w(0x302E, 0x1634)                  # move.w $1634(a6),d0
    a.bcc(0x67, 'gm_no')
    for m in (0x30, 0x34, 0x32):         # Blade's filters, as in his handler
        a.w(0x0C40, m)
        a.bcc(0x67, 'gm_no')
    a.w(0x4A69, 0x0122)                  # tst.w $122(a1)
    a.bcc(0x66, 'gm_go')
    a.w(0x4A69, 0x0126)                  # tst.w $126(a1)
    a.bcc(0x67, 'gm_no')
    a.label('gm_go')
    a.jmp(0x15404)
    a.label('gm_no')
    a.jmp(0x68CA)
    room_put(a, 'gm_list', bytes(4 * (len(moves) + 1)))   # (the list and its entries in a room: his block's
    for i, (d1, d2, btn, move) in enumerate(moves):       #  own bytes are r_taps' - Raiden's, Scorpion's are full)
        room_put(a, f'gm_e{i}', struct.pack('>7H', 0, 2 * i, TYPE, d1, d2, btn, move))


def generic_block(fid, sheet_shift, mk_dir, sounds=None):
    """The block for an MK fighter other than Scorpion (frames in his own
    numbering: sheet_shift = his first sheet - $40)."""
    global SCORPION_ID, SHEET_SHIFT
    import mkscripts
    from inputs import ROOT
    keep = SCORPION_ID, SHEET_SHIFT
    SCORPION_ID, SHEET_SHIFT = fid, sheet_shift
    try:
        co = open(os.path.join(ROOT, 'extracted', 'ec_us', 'BLA.CO'), 'rb').read()
        scripts = mkscripts.build(co, mk_dir)[0]
        GEN_DEAD.clear()                 # (his basic attacks' slots only: Blade's scripts the build edits stay out)
        GEN_DEAD.update(free=[b for b in dead_bodies(co, {int.from_bytes(sc[0:2], 'big') for sc in scripts.values()})
                              if b != CTRL_ROOM], pieces=[])
        if fid == RAIDEN_ID:
            scripts[RTELE_MOVE] = rtele_plan(mk_dir)[0]
        if fid == REPTILE_ID:
            scripts[ICE_MOVE] = ice_plan(mk_dir)[0]
        if fid == SHANG_ID:
            scripts[0x34] = skull_plan(mk_dir)[0]     # his cast: 11 held for the volley
            scripts.update(glide_scripts(mk_dir))     # his walks: MK's glide
        fwd, back, _ = walk_plan(mk_dir)
        global SCRIPT_TAIL
        SCRIPT_TAIL = {}
        SZF_TAIL.clear()
        tail = bytearray()
        if fid in TAIL_FIGHTERS and GEN_TAIL['off'] is not None:
            for mid, sc in sorted(scripts.items()):
                SCRIPT_TAIL[mid] = len(tail)
                tail += script_bytes(sc)
                tail += bytes(len(tail) % 2)
            if fid in FATALS:
                d, offs = fat_tail(fid)
                SZF_TAIL.update(off=len(tail), **offs)
                tail += d
                tail += bytes(-len(tail) % 32)          # (the 68000 reads words at even addresses only)
                SZF_TAIL['heads'] = len(tail)
                SZF_TAIL['head_offs'] = []
                if FATALS[fid].get('fxl'):                  # his lightning pieces' tiles (one upload)
                    SZF_TAIL['fxl'] = len(tail)
                    n = 0
                    for *_, tiles, _rec in FATALS[fid]['fxl']():
                        tail += tiles
                        n += len(tiles)
                    if FATALS[fid].get('kiss'):             # (Sonya's kiss: an upload of its own size)
                        tail += bytes(32)
                    else:
                        tail += bytes(max(0, GEN_TAIL.get('fx_size', n + SZF_HEAD_PAD) - n) + 32)   # (the upload reads its whole source)
                elif FATALS[fid].get('heads', True):
                    for tiles, _ in szf_heads():
                        SZF_TAIL['head_offs'].append(len(tail) - SZF_TAIL['heads'])
                        tail += tiles
                    tail += bytes(SZF_HEAD_PAD)
        elif fid in FATALS:
            raise ValueError('his fatality needs his .PL tail (GEN_TAIL off)')
        KD_TAIL.clear()
        if fid in KD_FIGHTERS and fid not in KD_LOW and GEN_TAIL['off'] is not None:
            tail += bytes(len(tail) % 2)
            _a, _f, _ = kd_plan(MK_DIR_BY_ID[fid])
            KD_TAIL.update(off=len(tail), n=(len(_a), len(_f)))
            tail += b''.join(fr(x).to_bytes(2, 'big') for x in _a + _f)
        JUMP_TAIL.clear()
        if fid in JUMP_FIGHTERS and fid in JUMP_IN_TAIL and fid not in JUMP_LOW and GEN_TAIL['off'] is not None:
            tail += bytes(len(tail) % 2)
            _f, _b, _ = jump_plan(MK_DIR_BY_ID[fid])
            JUMP_TAIL['off'] = len(tail)
            tail += b''.join(fr(f).to_bytes(2, 'big') for f in _f + _b + jump_up_plan(MK_DIR_BY_ID[fid]))
        GEN_TAIL['data'] = bytes(tail)
        a = Asm(0)
        GEN_LOW.clear()
        if fid in JUMP_LOW:
            low_jump(a, mk_dir)
        GEN_KD.clear()
        GEN_ROOM.clear()
        if fid in KD_FIGHTERS and fid in KD_LOW:
            low_kd(a, mk_dir)
        _block(a, False, fid, ('drag', 'jumpup', 'launch', 'taps', 'finish', 'ai'))
        r_generic(a, scripts, fwd, back, hit_plan(mk_dir)[0], throw_plan(mk_dir)[0], sounds or {},
                  leg_plan(mk_dir)[0] if fid == SONYA_ID else None, kick_plan(mk_dir)[0])
        for name, fn in (('jumpup', r_jumpup), ('launch', r_launch), ('taps', r_taps),
                         ('ai', r_ai),
                         ('gmoves', lambda a: r_gmoves(a, fid)), ('finish', lambda a: r_finish(a, False)),
                         ('music', emit_music)):
            while len(a.out) % 2:
                a.out += b'\0'
            if name in ENTRIES:
                a.label(f'r_{name}')
            fn(a)
        while len(a.out) % 2:
            a.out += b'\0'
        if 'g_ht_cnt' in a.labels:
            emit_hitfix(a)
        if GEN_TAIL['data']:
            emit_pl_tail(a)
        if fid == SHANG_ID:
            emit_morph_subs(a)
            emit_pl_tail(a, MORPH['off'], 'mo_pl')
        flush_late(a)
        a.label('vars')                  # as Scorpion's (r_drag): +14..+23 flight
        a.out += bytes(GENERIC_VARS)
        out = a.build()
        if os.environ.get('EK_LABELS'):  # (debugging: his block's labels, offsets from EXT_OFF)
            import json
            with open(os.path.join(os.environ['EK_LABELS'], f'block_{fid}.json'), 'w') as f:
                json.dump(a.labels, f)
        return out
    finally:
        SCORPION_ID, SHEET_SHIFT = keep
        SCRIPT_TAIL = {}


# ---------------------------------------------------------------- PLYR.CO stubs

def stubs(org, offs):
    """Stubs in PLYR.CO's free tail. Returns (bytes, {stub: address})."""
    a = Asm(org)
    at = {}

    def here(name):
        at[name] = org + len(a.out)
        a.label(name)

    # find: a0 = extension block (Z set) or Z clear if Scorpion's module isn't loaded
    here('find')
    for i, slot in enumerate(SLOTS):
        a.w(0x41F9); a.l(slot + EXT_OFF)          # lea slot+EXT,a0
        a.w(0x0C90); a.l(MAGIC)                   # cmpi.l #MAGIC,(a0)
        if i == 0:
            a.bcc(0x67, 'f_ok')                   # beq: found in slot 1
    a.label('f_ok')
    a.w(0x4E75)                                   # rts (Z from the last compare)

    # dispatch hook (replaces move.w (a0)+,d0 ; jmp $15A82(pc,d0.w))
    here('dispatch')
    a.w(0x3018)                                   # move.w (a0)+,d0
    a.w(0x0C40, TYPE)                             # cmpi.w #TYPE,d0
    a.bcc(0x67, 'dp_mine')
    a.w(0x4879); a.l(0x15A82)                     # pea $15A82
    a.w(0xD16F, 0x0002)                           # add.w d0,2(sp)
    a.w(0x4E75)                                   # rts -> jump table entry
    a.label('dp_mine')
    a.w(0x2F08)                                   # move.l a0,-(sp)   args
    a.bsr_back('find')
    a.bcc(0x66, 'dp_none')
    a.w(0x41E8, offs['taps'])                     # lea taps(a0),a0
    a.w(0x2C08)                                   # move.l a0,d6
    a.w(0x205F)                                   # movea.l (sp)+,a0
    a.w(0x2F06)                                   # move.l d6,-(sp)
    a.w(0x4E75)                                   # rts -> taps
    a.label('dp_none')
    a.w(0x205F)                                   # movea.l (sp)+,a0
    a.jmp(NEXT)

    # CPU special filter (replaces move.w $1D20(a6),$1634(a6))
    here('ai')
    a.w(0x48E7, 0x8080)                           # movem.l d0/a0,-(sp)
    a.w(0x302E, 0x1D20)                           # move.w $1D20(a6),d0
    a.bsr_back('find')
    a.bcc(0x66, 'ai_st')
    a.w(0x4EA8, offs['ai'])                       # jsr ai(a0)
    a.label('ai_st')
    a.w(0x3D40, 0x1634)                           # move.w d0,$1634(a6)
    a.w(0x4CDF, 0x0101)                           # movem.l (sp)+,d0/a0
    a.w(0x4E75)

    # step loader (replaces movea.l $AE(a5),a0 ; move.w (a0),$1A(a5)): Scorpion's
    # straight-up jump attacks
    here('frame_e2')
    a.w(0x206D, 0x00E2)                           # movea.l $E2(a5),a0
    a.bcc(0x60, 'fr_go')
    here('frame')
    a.w(0x206D, 0x00AE)                           # movea.l $AE(a5),a0
    a.label('fr_go')
    a.w(0x3B50, 0x001A)                           # move.w (a0),$1A(a5)
    a.w(0x48E7, 0x8080)                           # movem.l d0/a0,-(sp)
    a.bsr_back('find')
    a.bcc(0x66, 'fr_none')
    a.w(0x4EA8, offs['jumpup'])                   # jsr jumpup(a0)
    a.label('fr_none')
    a.w(0x4CDF, 0x0101)                           # movem.l (sp)+,d0/a0
    a.w(0x4E75)

    # drag (replaces lea x(a6),a3 ; tst.w $12A(a1)) - one stub per input task
    for site, off in DRAG_SITES:
        here(f'drag{off:x}')
        a.w(0x48E7, 0x8080)                       # movem.l d0/a0,-(sp)
        a.bsr_back('find')
        a.bcc(0x66, f'dr_{off:x}')
        a.w(0x4EA8, offs['drag'])                 # jsr drag(a0)
        a.label(f'dr_{off:x}')
        a.w(0x4CDF, 0x0101)                       # movem.l (sp)+,d0/a0
        a.w(0x47EE, off)                          # lea off(a6),a3       (displaced)
        a.w(0x4A69, 0x012A)                       # tst.w $12A(a1)       (displaced; flags for the bne)
        a.w(0x4E75)

    # after the hit reaction (replaces move.w $1444(a6),d1 ; move.w $1446(a6),d2)
    here('launch')
    a.w(0x48E7, 0x8080)                           # movem.l d0/a0,-(sp)
    a.bsr_back('find')
    a.bcc(0x66, 'la_none')
    a.w(0x4EA8, offs['launch'])                   # jsr launch(a0)
    a.label('la_none')
    a.w(0x4CDF, 0x0101)                           # movem.l (sp)+,d0/a0
    a.w(0x322E, 0x1444)                           # move.w $1444(a6),d1   (displaced)
    a.w(0x342E, 0x1446)                           # move.w $1446(a6),d2   (displaced)
    a.w(0x4E75)

    # hit sound (replaces move.w 8(a1),$1640(a6))
    for site, proj in HIT_SOUND_SITES:
        here(f'hit{site:x}')
        a.w(0x3D69, 0x0008, 0x1640)               # move.w 8(a1),$1640(a6)  (displaced)
        a.w(0x2F08)                               # move.l a0,-(sp)
        a.bsr_back('find')
        a.bcc(0x66, f'hr_{site:x}')
        a.w(0x4EA8, offs['hit_p' if proj else 'hit_f'])   # jsr hit(a0)
        a.label(f'hr_{site:x}')
        a.w(0x205F)                               # movea.l (sp)+,a0
        a.w(0x4E75)
    # a throw's damage, taken as the thrown fighter lands (each fighter module's THROW_DAMAGE): when it
    # leaves him on 0 or less his module does exg a3,a5; jsr throwko; bra.s on (patches.throw_finish), so
    # the after-damage path below (clamp, then finish) runs with him as the victim (a throw that would win
    # the match left the loser with no FINISH HIM). 6 bytes: the gap's last
    here('throwko')
    a.w(0x6104)                                   # bsr.s clamp
    a.w(0xC74D)                                   # exg a3,a5           back
    a.w(0x4E75)                                   # rts
    # after damage (replaces tst.w $76(a3); bpl.s; clr.w $76(a3))
    here('clamp')
    a.w(0x4A6B, 0x0076)                           # tst.w $76(a3)       (displaced)
    a.bcc(0x6A, 'cl_pos')
    a.w(0x426B, 0x0076)                           # clr.w $76(a3)       (displaced)
    a.label('cl_pos')
    a.w(0x48E7, 0xC0C0)                           # movem.l d0-d1/a0-a1,-(sp)
    a.bsr_back('find')
    a.bcc(0x66, 'cl_none')
    a.w(0x4EA8, offs['finish'])                   # jsr finish(a0)
    a.label('cl_none')
    a.w(0x4CDF, 0x0303)                           # movem.l (sp)+,d0-d1/a0-a1
    a.w(0x4E75)
    # projectile damage (replaces sub.w d6,d4 ; move.w d4,$76(a3); the bgt.s after it uses our flags)
    here('ko')
    a.w(0x9846)                                   # sub.w d6,d4         (displaced)
    a.w(0x3744, 0x0076)                           # move.w d4,$76(a3)   (displaced)
    a.bsr_back('cl_pos')                          # bsr cl_pos          clamp's finish (its 0 clamp skipped)
    a.w(0x4A6B, 0x0076)                           # tst.w $76(a3)       flags for the bgt.s
    a.w(0x4E75)
    return a.build(), at


def build(plyr, blaco, sub_org):
    """Return (PLYR.CO, BLA.CO, blob for SUB.BIN at RAM sub_org) with Scorpion's
    MK behaviour."""
    assert len(plyr) == END - BASE, 'unexpected PLYR.CO'
    assert len(blaco) <= EXT_OFF, 'BLA.CO grew into the extension offset'
    # shared by every MK fighter's block: blood (+ mkrow), at the start of the SUB.BIN blob
    sh = Asm(sub_org)
    r_blood(sh, 'bcnt', 0)
    sh.label('bcnt')
    sh.w(0)
    emit_throwfix(sh, 'thr')
    shared = sh.build()
    SUB_AT.clear()
    SUB_AT.update({n: sub_org + sh.labels[n] for n in ('blood', 'blood_body', 'mkrow', 'thr', 'thr_spd')})
    sub_org += len(shared)
    ext, offs = ext_block()
    if EXT_OFF + len(ext) > MORPH_MV:
        raise ValueError(f'extension block reaches ${MORPH_MV:X} (the slot end: Shang\'s morph vars, trampoline) by {EXT_OFF + len(ext) - MORPH_MV} bytes')
    for piece in (GEN_LOW, GEN_KD, GEN_ROOM):   # (his jump drive, knockdown, hit tables: low_jump, low_kd, room_put)
        if piece.get('data'):
            lo = piece['off']
            blaco = blaco[:lo] + piece['data'] + blaco[lo + len(piece['data']):]
    bla = bytes(blaco) + bytes(EXT_OFF - len(blaco)) + ext

    org = (END + 1) & ~1                     # (even: the gap after PLYR.CO is tight)
    code, at = stubs(org, offs)
    THROWKO['at'] = at['throwko']
    # (Scorpion's move list and Blade's handler on it live in his block now: r_gmoves)
    sub_blob = shared
    blob = code
    DAZE_TAIL['at'] = org + len(blob)        # the generic fighters' daze (daze_pad) ends here
    blob = blob + daze_tail()
    if org + len(blob) > GAP_END:
        raise ValueError(f'PLYR.CO stubs overflow by {org + len(blob) - GAP_END} bytes')
    out = bytearray(plyr) + bytes(org - END) + blob

    def put(site, orig, new):
        h = site - BASE
        assert out[h:h + len(orig)] == orig, hex(site)
        out[h:h + len(new)] = new

    put(HOOK_AT, HOOK_ORIG, bytes.fromhex('4EF9') + struct.pack('>I', at['dispatch']))
    for site in AI_SITES:
        put(site, AI_ORIG, bytes.fromhex('4EB9') + struct.pack('>I', at['ai']))
    for site, off in DRAG_SITES:
        put(site, bytes.fromhex('47ee') + struct.pack('>H', off) + bytes.fromhex('4a69012a'),
            bytes.fromhex('4EB9') + struct.pack('>I', at[f'drag{off:x}']) + bytes.fromhex('4E71'))
    put(LAUNCH_AT, LAUNCH_ORIG, bytes.fromhex('4EB9') + struct.pack('>I', at['launch']) + bytes.fromhex('4E71'))
    put(KO_SITE, KO_ORIG, bytes.fromhex('4EB9') + struct.pack('>I', at['ko']))
    for site, ptr in FRAME_SITES:
        put(site, bytes.fromhex('206d') + struct.pack('>H', ptr) + bytes.fromhex('3b50001a'),
            bytes.fromhex('4EB9') + struct.pack('>I', at['frame' if ptr == 0xAE else 'frame_e2']) + bytes.fromhex('4E71'))
    for site in CLAMP_SITES:
        put(site, CLAMP_ORIG, bytes.fromhex('4EB9') + struct.pack('>I', at['clamp']) + bytes.fromhex('4E714E71'))
    for site, _ in HIT_SOUND_SITES:
        put(site, HIT_SOUND_ORIG, bytes.fromhex('4EB9') + struct.pack('>I', at[f'hit{site:x}']))
    return bytes(out), bla, sub_blob


# ---------------------------------------------------------------- spear script (BLA.CO $26584)
# 12-byte steps: word duration (or $80xx = attack event: '80 16 nn 1D' damage
# nn, reaction $1D; '80 12' = Blade's throw-over), word, word frame, word,
# word dx, word dy. Blade's spear hits several times and finishes with a
# throw over the head and steps forward; MK's spear hits once and Scorpion
# stays put.
SCRIPT = 0x26584 - 0x21800
SPEAR_SCRIPT_EDITS = [
    # (offset in BLA.CO, expected 12 bytes' first 4, new first 4) - attack events -> plain steps
    (0x265C0, '8016021d', '00020000'),     # 42:29 swing hit (close range) - MK's spear only hits with the spear
    (0x26638, '8016031d', '00060000'),     # 42:31 second rope hit
    (0x2668C, '8016031d', '00060000'),     # 42:35 hit
    (0x266BC, '8012031d', '00060000'),     # 42:33 throw over the head
]
STAND_STILL = range(0x266E0, 0x2674C + 1, 12)   # 40:64-40:6D recovery steps: no forward drift
STEP_FORWARD = range(0x26704, 0x26740 + 1, 12)  # '04 xx 04 1A' steps (40:67-40:6B): walk-forward events -> plain
HOLD_LONGER = (0x26614, 0x26620)   # the rope's hold: these steps show 42:30 (as taut as 42:2E/2F, which then
                                   # only show before the hit is decided). (Their words were also set to $11 as
                                   # 'durations': they are the step before's flags ($F6) - EC's duration is the word
                                   # after the frame, below - and stay EC's $0006.)
# The spear on MK's timeline (mk_fidelity_spec 6: MK CD's capture, a hit: wind-up 3 frames a pose, the spear
# flying 1, the hit 5, the hold ~35, the pull ~17, then 24 and 12 to the stance; ours had every step one tick and
# was half as long, the hold ~16). EC's step: frame, ticks (x2 frames: PLYR $181DA, move.w 2(a0),$12(a4)), dx,
# dy, flags, $102 - from BLA.CO $26588 + 12 x step. Step -> ticks (steps not named keep their one tick).
SPEAR_STEP0 = 0x26588
SPEAR_TICKS = {0: 2, 1: 2, 2: 2, 3: 2,                  # wind-up 40:60-63: 16 frames (MK 17)
               11: 2,                                    # the hit, 42:2F: 4 (MK 5)
               12: 3, 13: 3, 14: 2, 15: 2, 16: 1,        # the hold, 42:30/31: 22 (MK ~35). EC's hit reaction lets
                                                         #  the victim go ~32 frames after the hit (then a ~14-frame
                                                         #  stagger) whatever $10C holds, and the pull and daze
                                                         #  (r_drag) run in his input task, idle while he's stunned:
                                                         #  the yank must end ~48 frames after the hit. 22 + the pull
                                                         #  at 7 px a frame: dazed by 45 from the spear's full reach
                                                         #  (Scorpion 142 px, Reptile 145); 26 lost Reptile's longest
               27: 2, 28: 2}                             # after the pull, 40:5E/5F: 8 - MK's yank-to-free is ~37
                                                         #  frames (86 -> 123) with the victim dazed ~80: his
                                                         #  ~43-frame punish window; ours yanks earlier (the
                                                         #  hold above), so the recovery is cut to keep it
CLOSE_JAB_HIT2 = 0x26034      # close X script: the second punch's attack step (42:20)
DIZZY_STEPS = (0x26314, 0x26320)   # dizzy script: 41:25 (hold 6), 41:26 (flag $2000: cut to 2 frames), then loop
DIZZY_HOLD = 0x7FFF           # Blade's own two-frame dizzy loop barely moves: the MK blocks drive the daze (dizzy_hold)
DAZE_FRAMES = (0x4125, 0x4126, 0x4147, 0x4148, 0x4149, 0x414A, 0x414C)   # MK's 7 dazed poses (scorpion_map 'dizzy')
# MK's FINISH HIM daze (tools/capture/mkdizzy.py, Sub-Zero waiting): a 7-pose sway,
# ~10 frames a pose, looped (~70 frames). One entry per r_drag call (every
# other frame): 5, 4, 5, 5, 5, 5, 6 calls per pose
DAZE_SEQ = tuple(k for k, n in enumerate((5, 4, 5, 5, 5, 5, 6)) for _ in range(n))
WALK_FWD, WALK_BACK = 8, 4      # EC states: walking forward / back (both play Blade's 40:16-40:1B cycle)
WALK_FRAMES = tuple(0x4064 + k for k in range(9))   # MK's 9 walk poses (scorpion_map 'walk_fwd')
# MK's forward walk (tools/lib/mkmoves.py walk_fwd), frames per pose 3 4 4 5 3 4 5 3 5 (36);
# walking back is the same 36 frames reversed. One entry per r_drag call (every other frame).
_WALK36 = [k for k, n in enumerate((3, 4, 4, 5, 3, 4, 5, 3, 5)) for _ in range(n)]
# Walking back runs the same frames reversed, phased so that both line up
# with EC's own cycle (6 steps x 3 calls = the same 36 frames): at each
# step's first call EC shows its frame 40:16+j, whose art is the pose due
# then (WALK_EC_POSES). r_drag resyncs to EC's step, so no frame is off.
WALK_SEQ = tuple(_WALK36[2 * t] for t in range(18))
WALK_SEQ_BACK = tuple(_WALK36[(30 - 2 * t) % 36] for t in range(18))
WALK_EC_POSES = tuple(_WALK36[6 * j] for j in range(6))      # 40:16..40:1B


def dizzy_hold(b):
    """Blade's dizzy shows 41:25 for ~12 frames and 41:26 for 2, looped; an MK
    fighter's holds 41:25 for good, so that his block alone picks the pose (r_drag's
    or daze_pad's cycle of MK's sway: DAZE_FRAMES) - with EC's loop still
    running, its two poses cut into the sway for a frame or two every cycle.
    (Its first step still ends ~8 frames in: hence 41:25 in both, the sway's
    first pose then. DIZZY_HOLD: no step change after that, ~9 minutes.)
    In place, on a module (a copy of BLA.CO, any sheet numbering)."""
    for k, a in enumerate(DIZZY_STEPS):
        o = a - 0x21800
        assert b[o + 5] == 0x25 + k, hex(a)
        b[o:o + 2] = bytes(2)                              # no flag
        b[o + 5] = 0x25                                    # (41:25 both: EC's first step ends early,
        b[o + 6:o + 8] = DIZZY_HOLD.to_bytes(2, 'big')     #  ~8 frames in, while the sway is on pose 0)


PJ_RECOVERY = range(0x4EE4, 0x4F5D, 12)   # BLA.CO: his projectile ($34)'s recovery steps 29-39 (40:64-40:6D)
STANCE_CYCLE = (0x00, 0x01, 0x02, 0x01)
PJ_TAIL = (0x4F4C, 0x4F58, 0x4F64, 0x4F70)   # BLA.CO: the recovery's last steps (40:6C 40:6D 40:60, the end):
                                    # their first byte $04 kept him walking forward (3 px a frame, ~30 px)
PJ_TAIL_FRAME = 0x4F69              # 40:60 there: MK's first cast pose (a flash of the throw again) -> his stance


STANCE_STEPS = 5                 # recovery steps (a tick, 2 frames, each) per stance pose: MK's ~10 frames


def pj_tail_still(b, stance=True):
    """The projectile recovery's tail (PJ_TAIL): no walking on, no flash of the cast pose. With stance,
    its steps (40:64-40:6D, MK's walk now) show his stance too."""
    if stance:                           # (a pose per STANCE_STEPS steps of a tick: MK's stance pace, ~10
        for k, o in enumerate(PJ_RECOVERY):  #  frames a pose - a pose a step shuffled his feet: he looked
            assert 0x64 <= b[o + 1] <= 0x6D, hex(o)   #  as if walking after Liu Kang's fireball)
            b[o + 1] = STANCE_CYCLE[k // STANCE_STEPS % 4]   # (the sheet byte kept: his numbering)
    for o in PJ_TAIL:
        assert b[o] == 0x04, hex(o)
        b[o] = 0x00
    assert b[PJ_TAIL_FRAME] == 0x60
    b[PJ_TAIL_FRAME] = STANCE_CYCLE[len(PJ_RECOVERY) // STANCE_STEPS % 4]


def recovery_still(co):
    """A generic MK fighter's module (a copy of Blade's): his projectile's
    recovery steps (40:64-40:6D) without Blade's forward drift, as Scorpion's
    (spear_script), and on his stance's frames: 40:64-40:6D are MK's walk now (walk_plan) - after a
    fireball he took steps on his own. Module offsets as BLA.CO's."""
    b = bytearray(co)
    for off in STAND_STILL:
        o = off - 0x21800
        b[o + 8:o + 12] = bytes(4)
    for off in STEP_FORWARD:
        o = off - 0x21800
        assert b[o] == 0x04 and b[o + 2:o + 4] == bytes.fromhex('041a'), hex(off)
        b[o] = 0x00
        b[o + 2:o + 4] = bytes(2)
    pj_tail_still(b)
    dizzy_hold(b)                        # his daze: MK's sway (emit_mk_daze), not EC's loop
    return bytes(b)


def spear_script(blaco):
    b = bytearray(blaco)
    for off, exp, new in SPEAR_SCRIPT_EDITS:
        o = off - 0x21800
        assert b[o:o + 4].hex() == exp, (hex(off), b[o:o + 4].hex())
        b[o:o + 4] = bytes.fromhex(new)
    for off in STAND_STILL:
        o = off - 0x21800
        b[o + 8:o + 12] = bytes(4)
    for off in STEP_FORWARD:
        o = off - 0x21800
        assert b[o] == 0x04 and b[o + 2:o + 4] == bytes.fromhex('041a'), hex(off)
        b[o] = 0x00
        b[o + 2:o + 4] = bytes(2)
    for off in HOLD_LONGER:
        o = off - 0x21800
        assert b[o:o + 4] == bytes.fromhex('00060000'), hex(off)
        # the rope's long hold on 42:30 (as taut as 42:2E/2F): 42:2E/2F then only show before the hit
        # is decided - r_drag's spear miss turns the frames after it into the bare throw (SPEAR_MISS)
        f = int.from_bytes(b[o + 4:o + 6], 'big')
        assert f in (0x422E, 0x422F, fr(0x422E), fr(0x422F)), hex(f)
        b[o + 4:o + 6] = (0x4230 if f >> 8 == 0x42 else fr(0x4230)).to_bytes(2, 'big')
    for k, ticks in SPEAR_TICKS.items():
        o = SPEAR_STEP0 - 0x21800 + 12 * k + 2
        assert int.from_bytes(b[o:o + 2], 'big') == 1, (k, b[o - 2:o + 2].hex())
        b[o:o + 2] = ticks.to_bytes(2, 'big')
    # Blade's close-range X is a double punch (two hits per press); MK's jab
    # is one: the second punch's attack step becomes a plain step (moving the
    # script's end up instead froze fights). Its frames show MK's stance
    # (scorpion_map), so it reads as one jab and the recovery.
    pj_tail_still(b)                     # (after the spear he too walked on: 40:64-40:6D are MK's walk)
    dizzy_hold(b)
    o = CLOSE_JAB_HIT2 - 0x21800
    assert b[o:o + 4] == bytes.fromhex('02060301') and int.from_bytes(b[o + 4:o + 6], 'big') in (0x4220, fr(0x4220)), b[o:o + 6].hex()
    b[o:o + 4] = bytes.fromhex('00060000')
    return bytes(b)


if __name__ == '__main__':
    from capstone import Cs, CS_ARCH_M68K, CS_MODE_BIG_ENDIAN, CS_MODE_M68K_000
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ex = os.path.join(root, 'extracted', 'ec_us')
    p, b = (open(os.path.join(ex, n), 'rb').read() for n in ('PLYR.CO', 'BLA.CO'))
    q, c, _ = build(p, spear_script(b), 0x20000)
    md = Cs(CS_ARCH_M68K, CS_MODE_BIG_ENDIAN | CS_MODE_M68K_000)
    org = (END + 1) & ~1                     # (even: the gap after PLYR.CO is tight)
    print('--- PLYR.CO stubs')
    for i in md.disasm(q[org - BASE:], org):
        print(f'{i.address:06x} {i.mnemonic} {i.op_str}')
    ext, offs = ext_block()
    print('--- BLA.CO extension', {k: hex(v) for k, v in offs.items()}, len(ext), 'bytes')
    for i in md.disasm(ext[4:], 4):
        print(f'  +{i.address:04x} {i.mnemonic} {i.op_str}')
    print(f'PLYR.CO +{len(q) - len(p)} bytes (ends ${BASE + len(q):X}, limit ${GAP_END:X}); BLA.CO {len(b)} -> {len(c)}')
