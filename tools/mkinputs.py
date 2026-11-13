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
"""
import os, struct

BASE = 0x14000
END = 0x1AE72                 # PLYR.CO's last byte + 1
GAP_END = 0x1B000
SLOTS = (0x1B000, 0x21800)    # fighter module slots (player 1, player 2)
EXT_OFF = 0x5200              # extension block's offset inside BLA.CO
MAGIC = 0x454B5343            # 'EKSC'

HOOK_AT = 0x15A7C             # move.w (a0)+,d0 ; jmp $15A82(pc,d0.w)
HOOK_ORIG = bytes.fromhex('30184efb0002')
BLADE_LIST = 0x164AC
BLADE_FINISHER = 0x16560      # type $24 entry: keep, so EC's finisher input still works
NEXT, SUCCESS = 0x15AAA, 0x15AB0
TYPE = 0x28

BACK, FWD, DOWN, UP = 4, 8, 2, 1
RAIDEN_ID = 19
RTELE_MOVE = 0x31             # Blade's move $31: a plain script (no code of its own): Raiden's teleport
CHORD = 0x4000                # in a move's button word: all these buttons held (not one pressed)
DIR3 = 0x8000                 # in a move's button word: a third tap (DIR3 | direction), not a button
LP, HP, LK, HK = 0x400, 0x200, 0x40, 0x10   # EC X, Y, A, B as mapped in scorpion_map
BLOCK = 0x100                 # EC Z: MK's Block

# (dir1, dir2, button, EC move id): Scorpion's MK1 specials
MK_MOVES = [
    (BACK, BACK, LP, 0x34),      # spear: back, back + low punch (Blade's projectile move)
    (DOWN, BACK, HP, 0x35),      # teleport punch: down, back + high punch
]

SPEAR_MOVE = 0x34
SCORPION_ID = 23              # his fighter id: Blast's slot (patches.HOST); Blade (9) stays EC's
HANDLERS = 0x153A0            # PLYR.CO special-move handler table, longs by id - 2
HIT_FIRST, HIT_LAST = 0x1A, 0x1D   # hit-reaction states ($1B standing, $1D airborne, ...)
STAGGER = 0x1B
DIZZY = 0x1F                  # EC's dizzy move
DIZZY_CODE = 0x17C9A          # its start in PLYR.CO (bsr; start anim; move.w #$1F,$BE(a5) ...)
SHEET_SHIFT = 0x4D            # Scorpion's art sheets $40-$43 live at $8D-$90 (patches.renumber_sheets)


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
PULL_SPEED = 12               # px per call; the input task runs every other frame -> ~6 px/frame (MK: ~6.4)
VOICE_ID = 0x05E6             # his bank's clip 0 = GETOHERE (patches.scorpion_voice; Blast's ids)
FINISH_VOICE = 0x05EC         # clip 1 = FINISHim
FINISH_VOICE_F = 0x05EE       # clip 2 = FINISHER: MK says 'FINISH HER' to a woman
FEMALE = (2, 10, 21)          # Shadow, Jetta, Raven (fighter ids, $4C)
JOHNNY_ID = 18                # Johnny Cage's slot (Zuni's, patches.JOHNNY host_id)
MK_IDS = (23, 19, 18, 20)     # Scorpion, Raiden, Johnny Cage, Sub-Zero ($4C)
# their first art sheet (patches Spec.sheet_base; Blade's $40): his frame
# 42:xx is (base + 2) << 8 | xx
MK_SHEET_BASE = {23: 0x8D, 19: 0x72, 18: 0xD9, 20: 0xDD}
# MK fighters whose palette has red in the spark colours 12/13 (patches
# Spec.blood): their hits and hurts bleed in their own palette line
BLOOD_IDS = (23, 19, 18, 20)
CINEKILL_SITE = 0x14AA2       # PLYR: cmpi.w #$18,$76(a5); bgt: the Cinekill check (victim at most 24 health)
SPLIT_STRIKE = 2              # his split punch's strike step (0-based; BLA.CO $43B4)
SPLIT_MOVE = 0x10             # EC's down + Z (Blade's script): Johnny's split punch

DRAG_SITES = ((0x1504E, 0x188E), (0x15210, 0x186E))   # input tasks P2, P1: lea x(a6),a3 ; tst.w $12A(a1)
AI_SITES = (0x15120, 0x152E0)  # move.w $1D20(a6),$1634(a6): CPU's chosen special (P1, P2)
AI_ORIG = bytes.fromhex('3d6e1d201634')
HIT_SOUND_SITES = ((0x19816, False), (0x19E74, True))   # move.w 8(a1),$1640(a6): fighter / projectile hit
HIT_SOUND_ORIG = bytes.fromhex('3d6900081640')
BLADE_SPECIALS = (0x2C, 0x36)
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
    """Type $28 recogniser. a0 = args (dir1, dir2, button, move), d1 = slot,
    a3 = progress table, a1 = fighter. Progress: high byte step, low byte
    frames since the last step. Exits to NEXT or SUCCESS (d6 = move)."""
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
    a.w(0xB050)                          # cmp.w (a0),d0        first tap
    a.bcc(0x66, 't_next')
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
    a.w(0x0246, 0x000F)                  # andi.w #$F,d6
    a.w(0xBC40)                          # cmp.w d0,d6          (d0: this frame's taps, facing-relative)
    a.bcc(0x66, 't_tick')
    a.label('t_ok')
    a.w(0x3C28, 0x0006)                  # move.w 6(a0),d6      move id
    a.w(0x4273, 0x1000)                  # clr.w (a3,d1.w)
    a.jmp(SUCCESS)
    a.label('t_tick')
    a.w(0x5233, 0x1001)                  # addq.b #1,1(a3,d1.w)
    a.w(0x0C33, 0x000C, 0x1001)          # cmpi.b #12,1(a3,d1.w)  12-frame window per step
    a.bcc(0x6D, 't_next')
    a.w(0x4273, 0x1000)                  # clr.w (a3,d1.w)
    a.label('t_next')
    a.jmp(NEXT)


def r_ai(a):
    """d0 = CPU's chosen special; returns d0 filtered: for Scorpion any of
    Blade's specials other than Scorpion's become 0 (no special)."""
    a.w(0x0C69, SCORPION_ID, 0x004C)     # cmpi.w #9,$4C(a1)
    a.bcc(0x66, 'ai_r')
    a.w(0x0C40, BLADE_SPECIALS[0])       # cmpi.w #first,d0
    a.bcc(0x6D, 'ai_r')
    a.w(0x0C40, BLADE_SPECIALS[1])       # cmpi.w #last,d0
    a.bcc(0x6E, 'ai_r')
    for m in sorted(KEEP):
        a.w(0x0C40, m)                   # cmpi.w #keep,d0
        a.bcc(0x67, 'ai_r')
    a.w(0x7000)                          # moveq #0,d0
    a.label('ai_r')
    a.w(0x4E75)                          # rts


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
    a.w(0x4A69, 0x0076)                  # tst.w $76(a1)       hit to 0 in the window:
    a.bcc(0x6E, f'{pfx}fa')                  # bgt
    a.w(0x42AA, 0x0034)                  # clr.l 52(a2)        ... an ordinary KO
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
    for fid in FEMALE:
        a.w(0x0C41, fid)                 # cmpi.w #id,d1
        a.bcc(0x66, f'{pfx}m{fid}')
        a.w(0x363C, voice_f)      # ... or 'FINISH HER'
        a.label(f'{pfx}m{fid}')
    a.pcrel(0x41FA, 'f_time')            # lea f_time(pc),a0   MK: the round music gives way to
    a.bccw(0x61, 'f_music')              # bsr.w f_music       the fatality track (2 s of silence first)
    a.w(0x3003)                          # move.w d3,d0
    a.jsr(0x6D58)
    a.w(0x4CDF, 0x7FFE)                  # movem.l (sp)+,d1-d7/a0-a6
    # a hit after the grace is an ordinary KO, the fatality the other way out;
    # left alone he gives out after FINISH_CALLS (the round clock runs out)
    a.label(f'{pfx}nf')


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
    # his basic attacks play MK's animation (tools/mkscripts.py): his move
    # table ($A6, longs by move id) points at our scripts
    a.w(0x2069, 0x00A6)                  # movea.l $A6(a1),a0
    for mid in sorted(MK_SCRIPTS):
        a.pcrel(0x487A, f'ms_{mid}')     # pea ms(pc)
        a.w(0x215F, 4 * mid)             # move.l (sp)+,4*id(a0)
    r_teleport(a)
    emit_throwcall(a)                    # his throw's victim lands like MK's
    emit_hitdrive(a, THROW_CALLS['mk_moves'], 'd_tw', 'd_nod', True, THROW_MOVE, False)   # MK's throw animation
    emit_hitdrive(a, HIT_CALLS['mk_moves'], 'd_ht', 'd_nod', True)
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
    a.w(0x3029, 0x00BE)                  # move.w $BE(a1),d0
    a.w(0x0440, HIT_FIRST)               # subi.w #first,d0
    a.w(0x0C40, HIT_LAST - HIT_FIRST)    # cmpi.w #n,d0
    a.bccw(0x62, 'd_out')                 # bhi: not reeling
    a.w(0x42A9, 0x00C6)                  # clr.l $C6(a1)        no knock-back
    a.w(0x3028, 0x001A)                  # move.w $1A(a0),d0    Scorpion's frame
    a.w(0x0C40, HOLD_FRAMES[0])
    a.bcc(0x65, 'd_pull')                # bcs: before the hold frames
    a.w(0x0C40, HOLD_FRAMES[1])
    a.bccw(0x63, 'd_out')                 # bls: rope still stuck in him
    a.label('d_pull')
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
    # +74 camera held, +76 teleport taken over, +78 where he lands, +80 his double stands,
    # +84/+88 walk count (P1/P2: a mirror match walks two Scorpions)
    a.l(0); a.w(0); a.w(0); a.w(0); a.w(0); a.w(0); a.w(0); a.w(0)
    a.w(0); a.w(0); a.w(0); a.w(0); a.w(0); a.w(0); a.l(0); a.l(0)


BLOOD_SHEET, BLOOD_FRAME, BLOOD_N, BLOOD_LIFE = 0x1B, 7, 6, 22
BLOOD_MAX = 6                 # drops alive at once: EC's hit code waits for a free effect object (a fighter froze mid-reaction)
BLOOD_CHEST = 75              # px above the feet: where the spear's blood comes from
EFFECT_SPAWN = 0x6954         # d0 type, d1 x, d2 y -> a0 object (carry set: none free)
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
    a.w(0x383C, 0xFFFF)                  # move.w #-1,d4
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
    # droplet task (a5 = the droplet)
    a.label('droplet')
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
    a.pcrel(0x41FA, cnt)                 # lea cnt(pc),a0
    a.w(0x5368, off)                     # subq.w #1,off(a0)
    a.w(0x08ED, 0x0002, 0x0082)          # bset #2,$82(a5)     remove
    a.jmp(0x6A1A)                        # halt
    emit_mkrow(a)


MUSIC_TAG = 0x454B4D55        # 'EKMU': the fatality music's disc time follows (patches.fatality_music)
FINISH_CALLS = 125            # MK: an unfinished loser collapses 250 frames after FINISH HIM (r_drag: every other frame)
ROUND_CLOCK = -0x2AE6         # (wrong: a fixed address; the clock lives in an object that moves)
CLOCK_OBJ, CLOCK_TIME = 0x15CA, 0xA4   # ($15CA(a6)) + $A4: the round time, BCD (found by its count-down
                                       # in three fights: $2D1DC, $2D282, $2D282)
FINISH_GRACE = 30             # calls (~1 s) after FINISH HIM in which hits can't take his last point
FINISH_TABLE = 0x15F16        # EC's wins-needed bytes by $1CFE (its own finisher check, PLYR.CO $15EC6)
CLAMP_SITES = (0x1985A, 0x19D26, 0x19EFA)   # tst.w $76(a3); bpl.s; clr.w $76(a3): after damage (fighter, projectile hits)
CLAMP_ORIG = bytes.fromhex('4a6b00766a04426b0076')
KO_SITE = 0x19FAE             # sub.w d6,d4; move.w d4,$76(a3); bgt.s: projectile damage, straight to the KO when <= 0
KO_ORIG = bytes.fromhex('984637440076')
FAT_GAP = 90                  # px: MK does it from half a screen
FAT_PAUSE = 100               # frames on the bones before the round ends (MK ~2 s, moveq max 127)
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
# MK's teleport (tools/mkmoves.py teleport; poses cleaned into teleport_mk):
# crouch, spring, a tucked leap back and up, out through his own screen edge
# head first; then in at the opposite edge fist first, landing just inside
# it - the punch lands only on someone near that edge. Our own animation
# script (EC plays the frames, no flashes); r_tele moves him.
# the punch's hit ($102: damage, attack type - Blade's punches are types
# 1/2, his uppercuts $40/$41, the dash $1C). The dash's $0C1C knocked the
# victim down and across the screen; MK's teleport punch (measured,
# states/mk_2p.state) staggers him ~70 px back on his feet, with blood, for
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
# the leap until he lands: an effect object showing GHOST_FRAME (scorpion_map)
GHOST_FRAME = 0x413A
# Off: an effect object shows a fighter frame as stripes - EC unpacks a
# fighter's frame each video frame into that fighter's own VRAM area, and a
# second object has no area of its own (tried the spark's descriptor $24 and
# his own, 23). Needs a second unpack area (docs/re_notes.md).
GHOST_ON = False
CAM_HOLD = 1                  # $AB6 bit 1: EC's camera stops following (PLYR $14D88)
TELE_OUT = 16                 # px per call flying out (outruns the camera; EC stops him at the edge)
TELE_EDGE = 294               # where he lands: just inside EC's edge limit (cam + 320 - $46 = 295;
                              # touching it ends the dash); MK lands at 299 of 320


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
    a.w(0x426A, 0x004C)                  # clr.w 76(a2)        not teleporting
    a.w(0x426A, 0x0050)                  # clr.w 80(a2)        no double
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
    a.w(0x426A, 0x0050)                  # clr.w 80(a2)        the double goes
    a.label('tp_g2')
    # d0 = T, where he lands: the far edge's side of the screen
    a.w(0x3039); a.l(CAMERA_X)           # move.w CAMERA_X,d0
    a.w(0x4A6A, 0x0046)                  # tst.w 70(a2)        away = left?
    a.bccw(0x6B, 'tp_tl')
    a.w(0x0640, 320 - TELE_EDGE)         # addi.w #20,d0       (away right: in from the left)
    a.bccw(0x60, 'tp_tt')
    a.label('tp_tl')
    a.w(0x0640, TELE_EDGE)               # addi.w #300,d0
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
        a.w(0x317C, fr(GHOST_FRAME), 0x001A)  # move.w #frame,$1A(a0)
        a.w(0x3029, 0x007A)                  # move.w $7A(a1),d0   attr = line << 13 | facing
        a.w(0x0240, 0x0003)                  # andi.w #3,d0
        a.w(0xE148)                          # lsl.w #8,d0
        a.w(0xEB48)                          # lsl.w #5,d0
        a.w(0x3229, 0x0020)                  # move.w $20(a1),d1
        a.w(0x0241, 0x0800)                  # andi.w #$800,d1
        a.w(0x8041)                          # or.w d1,d0
        a.w(0x3140, 0x001E)                  # move.w d0,$1E(a0)
        a.w(0x3140, 0x0020)                  # move.w d0,$20(a0)
        a.w(0x357C, 0x0001, 0x0050)          # move.w #1,80(a2)
        a.w(0x2068, 0x0088)                  # movea.l $88(a0),a0  its task
        a.pcrel(0x487A, 'ghost')             # pea ghost(pc)
        a.w(0x215F, 0x0004)                  # move.l (sp)+,4(a0)
        a.w(0x4268, 0x0008)                  # clr.w 8(a0)
        a.label('gh_out')
        a.w(0x4CDF, 0x030F)                  # movem.l (sp)+,d0-d3/a0-a1
        a.w(0x4E75)
        # the double's task (a5 = it): stand until he lands
        a.label('ghost')
        a.pcrel(0x41FA, 'vars')              # lea vars(pc),a0
        a.w(0x4A68, 0x0050)                  # tst.w 80(a0)
        a.bccw(0x67, 'gh_gone')
        a.w(0x7001)                          # moveq #1,d0
        a.jsr(0x68D6)                        # sleep 1 frame
        a.bccw(0x60, 'ghost')
        a.label('gh_gone')
        a.w(0x08ED, 0x0002, 0x0082)          # bset #2,$82(a5)     remove
        a.jmp(0x6A1A)
    a.label('tscript')                   # step 0: never played (EC moves on before reading)
    a.w(fr(0x4116), 1, 0, 0, 0, 0)
    for f, n, f6, x in TELE_STEPS:
        a.w(fr(f), n, 0, 0, f6, x)
    a.w(0x00D8, 0x0006, 0x0008, 0x0000, 0xFFF8, 0x0000)   # Blade's dash ending
    a.w(0, 0, 0, 0, 0, 0)
    for mid, sc in sorted(MK_SCRIPTS.items()):   # header, steps (frames in his numbering), terminator
        a.label(f'ms_{mid}')
        a.out += sc[:20]
        for o in range(20, len(sc), 12):
            f = int.from_bytes(sc[o:o + 2], 'big')
            a.w(fr(f) if f >= 0x100 else f)
            a.out += sc[o + 2:o + 12]
    a.label('tp_out')


# Straight-up jump attacks: EC plays the same frames whether Scorpion jumps
# straight up or forward; MK's straight-up kick and punch are near-upright
# poses of their own (tools/mkmoves.py jumpup_*). A hook on EC's step loader
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


def emit_music(a):
    """f_music (a0 = a disc time: MK's music from the end of EC's last track)
    and the times patches.fatality_music fills in after the 'EKMU' tag."""
    # MK's fatality music (MK CD track 13, appended to EC's last track:
    # build.add_mk_jingle), started by disc time; patches.fatality_music
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
    a.w(0x0803, UP_BIT)                  # btst #0,d3          Up now ...
    a.bcc(0x67, 'f_noup')
    a.w(0x3032, 0x2030)                  # move.w 48(a2,d2.w),d0
    a.w(0x0800, UP_BIT)                  # btst #0,d0          ... and not before
    a.bcc(0x66, 'f_noup')
    a.w(0x5272, 0x2028)                  # addq.w #1,40(a2,d2.w)   one more tap
    a.w(0x35BC, 0x0014, 0x202C)          # move.w #20,44(a2,d2.w)  window
    a.label('f_noup')
    a.w(0x3583, 0x2030)                  # move.w d3,48(a2,d2.w)
    # Z is MK's Block button: EC never sees Z or Up, it sees "back" (= block)
    # MK's Block stands still: no Z, Up, left or right reach EC. EC blocks by
    # holding back, so back is fed only while the opponent attacks ($F6 bit 5
    # clears from the first frame of an attack or jump, measured). Holding back stays EC's walk-
    # back-and-block for everyone.
    a.w(0x0253, 0xFEF2)                  # andi.w #$FEF2,(a3)  no Z, Up, left, right
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
    a.w(0x0C6B, DIZZY, 0x00BE)           # cmpi.w #$1F,$BE(a3)
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
    a.w(0x362C, 0x0002)                  # move.w 2(a4),d3
    a.bcc(0x67, 'f_nos')
    a.w(0x3343, 0x001A)                  # move.w d3,$1A(a1)   Scorpion's frame
    a.label('f_nos')
    a.w(0x266A, 0x0022)                  # movea.l 34(a2),a3   victim
    a.w(0x362C, 0x0004)                  # move.w 4(a4),d3     mode
    a.bcc(0x67, 'f_ret')
    a.w(0x0C43, 0x0002)                  # cmpi.w #2,d3
    a.bcc(0x67, 'f_char')
    a.w(0x376C, 0x0006, 0x001A)          # move.w 6(a4),$1A(a3)
    a.bccw(0x61, 'f_pal')                # victim gets Scorpion's colours
    a.label('f_ret')
    a.w(0x4E75)
    a.label('f_char')
    a.w(0x376A, 0x0026, 0x001A)          # move.w 38(a2),$1A(a3)   his own pose ...
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
    a.w(0x7000 | FAT_PAUSE)              # moveq #pause,d0
    a.jsr(0x68D6)                        # sleep
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


def r_finish(a):
    """After a hit's damage (a3 = victim, health already clamped at 0).
    MK rule: the blow that would win Scorpion the match (EC's own test, as
    its finishers use it) leaves the loser on 1 health; r_drag dazes him and
    runs the FINISH HIM window. A blow inside the window is an ordinary KO."""
    a.label('finish')
    a.w(0x4A6B, 0x0076)                  # tst.w $76(a3)
    a.bccw(0x6E, 'fi_out')               # bgt: still alive
    a.pcrel(0x41FA, 'vars')              # lea vars(pc),a0
    a.w(0xB7E8, 0x0034)                  # cmpa.l 52(a0),a3    in the window:
    a.bcc(0x66, 'fi_new')
    a.w(0x4A68, 0x0038)                  # tst.w 56(a0)        grace over: this blow KOs
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


def r_hit(a, projectile, tag):
    """Hit routine (after the displaced sound-id copy). a5 = attacker (the
    fighter, or for projectile=True the rope object, owner at $8C), a3 =
    victim. First contact of Scorpion's spear: the hit sound is his voice
    (and the victim staggers instead of the rope's own reaction). Repeat
    contacts while the victim is reeling: no damage, reaction or sound.
    Uses a0 (saved by the stub)."""
    a.w(0x204D)                          # movea.l a5,a0
    a.w(0x0C68, SCORPION_ID, 0x004C)     # cmpi.w #9,$4C(a0)
    a.bcc(0x67, f'h{tag}_chk')
    a.w(0x206D, 0x008C)                  # movea.l $8C(a5),a0  owner
    a.label(f'h{tag}_chk')
    a.w(0x0C68, SPEAR_MOVE, 0x00BE)      # cmpi.w #$34,$BE(a0)
    a.bcc(0x66, f'h{tag}_out')
    a.w(0x0C68, SCORPION_ID, 0x004C)     # cmpi.w #9,$4C(a0)
    a.bcc(0x66, f'h{tag}_out')
    a.w(0x0C6B, HIT_FIRST, 0x00BE)       # cmpi.w #$1A,$BE(a3)
    a.bcc(0x6D, f'h{tag}_first')         # blt
    a.w(0x0C6B, HIT_LAST, 0x00BE)        # cmpi.w #$1D,$BE(a3)
    a.bcc(0x6E, f'h{tag}_first')         # bgt
    if projectile:
        a.w(0x422D, 0x0078)              # clr.b $78(a5)        damage 0
        a.w(0x426D, 0x00A4)              # clr.w $A4(a5)        no new reaction
    else:
        a.w(0x422D, 0x0102)              # clr.b $102(a5)
    a.w(0x426E, 0x1640)                  # clr.w $1640(a6)      no sound
    a.bcc(0x60, f'h{tag}_out')
    a.label(f'h{tag}_first')
    a.w(0x3D7C, VOICE_ID, 0x1640)        # move.w #VOICE,$1640(a6)
    if projectile:
        a.w(0x3B7C, STAGGER, 0x00A4)     # move.w #$1B,$A4(a5)
        a.jsr(SUB_AT['blood_body'])      # jsr blood_body      MK: the spear draws blood
    a.label(f'h{tag}_out')
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
        elif full:
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
    a = Asm(0)
    raws = {}
    _block(a, True, SCORPION_ID, ('taps', 'ai', 'drag', 'hit_f', 'hit_p', 'launch', 'finish', 'jumpup'))
    for name, fn in (('taps', r_taps), ('ai', r_ai), ('drag', r_drag),
                     ('hit_f', lambda a: r_hit(a, False, 'f')),
                     ('hit_p', lambda a: r_hit(a, True, 'p')),
                     ('launch', r_launch), ('fatal', r_fatal),
                     ('finish', r_finish), ('jumpup', r_jumpup)):
        while len(a.out) % 2:
            a.out += b'\0'
        if name in ENTRIES:
            a.label(f'r_{name}')
        fn(a)
    return a.build(), {n: HEAD + 4 * i for i, n in enumerate(ENTRIES)}


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
    return [sid << 8 | f for sid, f in reversed(mkscripts.free_slots())
            if (sid << 8 | f) not in used and (sid << 8 | f) not in skip]


# EC's throw (move $0D): the thrower list (BLA.CO $1B10, 7 steps, 4 bytes:
# frame, flags) loads its frames at 0, 6, 12, 16, 24, 28, 32 frames (victim
# record ticks 3 3 2 THROW_HOLD 2 2 2); the victim is released ~36 frames
# in; then Blade's module shows 42:11 (BLA.CO $1A62, ~46) and his stance.
# Blade's list reuses 42:0F and 42:10 late, which flashed early poses over
# MK's: in the MK fighters' modules the list is rewritten (patches.mk_throw_arc)
# so each frame is loaded at one moment only.
THROW_LIST_AT = 0x1B10       # BLA.CO offset of the thrower list
THROW_LIST = (0x4210, 0x420F, 0x420E, 0x420D, 0x420D, 0x420D, 0x420D)
THROW_EC = ((0x4210, 0), (0x420F, 6), (0x420E, 12), (0x420D, 16), (0x4211, 46))
THROW_MOVE = 0x0D
THROW_PEAK_AT, THROW_RELEASE, THROW_END = 16, 36, 52   # frames


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
    act = [r for r in runs if mkscripts._key(P[r[0]]) not in skip]
    first_end = next((i for i, r in enumerate(act) if i and r[0] == act[0][0]), len(act))
    act = act[:first_end]
    peak = max(range(len(act)), key=lambda i: act[i][1])
    pre, post = act[:peak], act[peak + 1:]
    frames = []
    n = sum(r[1] for r in pre) or 1
    for k, m in pre:                                  # squeezed to THROW_PEAK_AT
        frames += [k] * max(1, round(m * THROW_PEAK_AT / n))
    frames = (frames + [act[peak][0]] * THROW_PEAK_AT)[:THROW_PEAK_AT]
    frames += [act[peak][0]] * (THROW_RELEASE - THROW_PEAK_AT)
    for k, m in post:
        frames += [k] * m
    frames = (frames + [frames[-1]] * THROW_END)[:THROW_END]
    calls = [frames[2 * c] for c in range(THROW_END // 2)]
    slot = {}
    for f, t in THROW_EC:                             # EC's own frames: the pose due when EC loads each
        slot.setdefault(calls[t // 2], f)
    hit_slots = set(hit_plan(mk_dir)[0])
    free = _free_slots(mk_dir, hit_slots)
    for k in calls:
        if k not in slot:
            slot[k] = free.pop(0)
    pins, seen = [], set()
    for f, t in THROW_EC:
        if f not in seen:
            seen.add(f)
            pins.append(f'{f >> 8:02x}:{f & 0xFF:02x}={calls[t // 2]}')
    pins += [f'{f >> 8:02x}:{f & 0xFF:02x}={k}' for k, f in slot.items() if f not in seen]
    return tuple(slot[k] for k in calls), pins


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


def hit_plan(mk_dir):
    """(calls, art pins) for MK's hit reaction (tools/mkmoves.py hit_high):
    the poses from the first reaction pose (first shown after the hit lands,
    scorpion_full.HIT_LANDS) until the stance is back, at MK's timing, one
    frame word per r_drag call (every other frame). EC's own hit frames are
    pinned to the pose due when EC loads them; the others go on free frame
    slots (from the end of mkscripts' list: its attack scripts take the front)."""
    import mkscripts, scorpion_full
    from inputs import ROOT
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


def walk_plan(mk_dir):
    """(forward calls, back calls, art pins) for a fighter's MK walk: 9
    poses on 40:64-40:6C, MK's timing over EC's 36-frame cycle, EC's own
    walk frames 40:16-40:1B pinned to the pose due when each step starts."""
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


def emit_hitdrive(a, calls, pfx, done, per_player, state=None, script=True):
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
    a.w(0x3370, 0x0000, 0x001A)          # move.w (a0,d0.w),$1A(a1)
    a.bccw(0x60, done)
    a.label(f'{pfx}_tab')
    for f in calls:
        a.w(fr(f))
    a.label(f'{pfx}_cnt')
    a.w(0xFFFF); a.w(0); a.w(0xFFFF); a.w(0)   # (P1 at +0, P2 at +4)
    a.label(f'{pfx}_no')


THROWN = 0x37                 # EC's victim state while being thrown
# speed across (px/frame x256) of the victim's fall after the release, by
# thrower (measured on the MK disc: Scorpion's and Sub-Zero's roll throws
# land him ~110 px behind - where EC's choreography leaves him - Raiden's
# and Johnny's overhead tosses ~155 px: +35 px over EC's ~28-frame arc)
THROW_PUSH = {23: 0, 20: 0, 19: 0, 18: 0}   # (the distance is the throw records' now: patches.THROW_FAR)
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
    a.pcrel(0x41FA, f'gs_{RTELE_MOVE}')  # lea script(pc),a0
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


# MK projectiles (tools/mkprojectile.py: the art in his effect sheet $45):
# an object spawned as Blade's (type $1F40, his descriptor with our sheet),
# registered as his projectile ($6A38: EC's own projectile hit check and
# reaction), flown at MK's speed (measured ~6 px/frame) from his cast's
# release frame (42:2E, Blade's projectile strike frame)
PJ_TYPE = 0x1F40              # Blade's own projectile object type
PJ_DESC = 0x3B26              # BLA.CO: his descriptor for it (word 0 = sheet)
PJ_RELEASE = 0x422E
PJ_SPEED, PJ_LIFE, PJ_AHEAD, PJ_UP = 6, 35, 70, 75   # px/frame, task runs (every other frame), px in front, px above his feet
PJ_FIGHTERS = {19: 'raiden', 18: 'johnny', 20: 'subzero'}
# $78: damage byte, hit level byte (EC's table at PLYR $1A2CC; Blade's and
# Xavier's projectiles use level 2, damage 0). MK: the bolts take ~10% of the
# bar (10 of EC's 104); the ice ball does no damage, it freezes (emit_freeze)
PJ_DAMAGE = {'raiden': 10, 'johnny': 10, 'subzero': 0}
PJ_LEVEL = 2
PJ_REACT = {'raiden': HIT_FIRST, 'johnny': HIT_FIRST, 'subzero': 0}   # $A4: MK's frozen victim has no hit reaction


def emit_proj(a, key):
    """In r_generic (a1 = him): when his cast ($34) shows its release frame,
    his MK projectile flies. Its hit (EC's) sets pj_v+2 (emit_freeze)."""
    import mkprojectile
    from inputs import ROOT
    nfl = len(mkprojectile.PROJ[key][1])
    co = open(os.path.join(ROOT, 'extracted', 'ec_us', 'BLA.CO'), 'rb').read()
    desc = bytearray(co[PJ_DESC:PJ_DESC + 34])
    assert desc[0:2] == b'\x00\x44', desc.hex()
    desc[0:4] = bytes((0, mkprojectile.SHEET, 0, 0))
    a.pcrel(0x45FA, 'pj_v')              # lea vars(pc),a2     +0 fired this cast, +2 hit
    a.w(0x3029, 0x00BE)                  # move.w $BE(a1),d0
    a.w(0x0240, 0x7FFF)
    a.w(0x0C40, 0x0034)                  # cmpi.w #$34,d0      his cast
    a.bcc(0x67, 'pj_in')
    a.w(0x4252)                          # clr.w (a2)
    a.bccw(0x60, 'pj_x')
    a.label('pj_in')
    a.w(0x4A52)                          # tst.w (a2)
    a.bccw(0x66, 'pj_x')
    a.w(0x0C69, fr(PJ_RELEASE), 0x001A)  # cmpi.w #release,$1A(a1)
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
    a.w(0x317C, mkprojectile.SHEET << 8, 0x001A)   # move.w #$4500,$1A(a0)
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


# Sub-Zero's MK fatality (the spine rip; tools/mkfatality_subzero.py): in his
# FINISH HIM window, forward, down, forward + high punch (EC Y) up close. His
# poses on 41:52-41:59; the loser's (MK's headless body as a dark figure,
# fatality_corpse) on 41:40-41:45 and 41:5A/5B, drawn with his palette
# (mode 1, as Scorpion's skeleton). MK's timeline sampled every 6 frames
# from his grab (capture frame 144), its pause before shortened to SZF_PAUSE.
SZF_HIS = [1, 3, 5, 7, 10, 15, 23, 27]                 # his capture poses kept
SZF_HIS_SLOTS = [0x4152 + k for k in range(8)]
SZF_VIC = [8, 10, 12, 15, 17, 21, 26, 32]              # the loser's (corpse) poses kept
SZF_VIC_SLOTS = [0x4140, 0x4141, 0x4142, 0x4143, 0x4144, 0x4145, 0x415A, 0x415B]
SZF_FROM, SZF_TO, SZF_STEP, SZF_PAUSE = 144, 420, 6, 20  # capture frames; pause in calls
SZF_GAP = 26                  # px between them when he grabs (MK: 24 between the captured centres, x1.08)
SZF_TAPS = (FWD, DOWN, FWD)   # then HP (EC Y)


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
        row = (SZF_STEP // 2, h, 0 if vic[t] < 8 else 1 + z, 0)
        if rows and rows[-1][1:] == row[1:]:
            rows[-1] = (rows[-1][0] + row[0],) + row[1:]
        else:
            rows.append(row)
    return rows


# EC's own death art for the loser (docs/re_notes.md "EC's own headless deaths"):
# Z<xx>.BIN file id $EC + n, its sheet 2 = $112 + n (n >= 10: one less, ZEC has
# no sheet 2). Victim idx (id - 2) -> n + 1; 0 = none (the MK fighters' hosts,
# the gag animals, the bosses: their Z art is someone else's or missing).
SZF_Z = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8, 12: 10, 13: 11,
         14: 12, 19: 14, 20: 15, 22: 17}
SZF_ZFILE = 0xEC
SZF_HEAD_FRAME = 6            # Z sheet 1 ($100 + n): the loser's own severed head, upright
SZF_HEAD_BASE = 2             # his effect sheet's frame of head 0 (after the ice ball's 1 + 1: mkprojectile.PROJ)
fr_fx = lambda k: (0x44 << 8) | k   # (effect sheet $44 keeps its number in every MK fighter)
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
TAIL_FIGHTERS = (SUBZERO_ID,)


def szf_tail():
    """Data appended to his .PL after its chunk chain (loaded with it, never
    parsed): the timeline rows, a zero row, then the victim table (25 bytes)."""
    rows = [(n, fr(h) if h else 0, m, v) for n, h, m, v in szf_table()]
    out = b''.join(struct.pack('>4H', *r) for r in rows) + bytes(8)
    ztab_off = len(out)
    out += bytes(SZF_Z.get(i, -1) + 1 for i in range(25))
    return out, ztab_off


Z_NAMES = 'ZSH ZLR ZRX ZSL ZTR ZMD ZXV ZBD ZJT ZEC ZRP ZPH ZEX ZCH ZRV ZSN ZBS ZDW'.split()   # file $EC + n


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
    return out


SZF_HEAD_PAD = 4096           # bytes after the last head: EC's upload takes the source's whole size


def szf_head_desc():
    """A spawn descriptor for her head: Blade's projectile one (as emit_proj's),
    its frame set after the spawn."""
    from inputs import ROOT
    co = open(os.path.join(ROOT, 'extracted', 'ec_us', 'BLA.CO'), 'rb').read()
    desc = bytearray(co[PJ_DESC:PJ_DESC + 34])
    import mkprojectile
    desc[0:4] = bytes((0, mkprojectile.SHEET, 0, 0))   # (a sheet that's loaded: his effect sheet)
    return bytes(desc)


SZF_TAIL = {}                 # 'off': his .PL tail offset, 'ztab': victim table offset in it (patches.mk_code)


def szf_pins():
    return [('fatality_held', [f'{f >> 8:02x}:{f & 0xFF:02x}={k}' for f, k in zip(SZF_HIS_SLOTS, SZF_HIS)])]


def emit_gfatal(a):
    """In r_generic (a1 = him, a2 = vars; vars as Scorpion's: +24 running,
    +26 row, +28 calls in it, +30 him, +34 the loser, +38 her frame, +40 tap
    step, +42 its window, +52 the FINISH HIM loser). Branches to g_out while
    it runs (his other per-frame work stops)."""
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
    a.w(0x4AAA, 0x0034)                  # tst.l 52(a2)        only in his FINISH HIM window
    a.bccw(0x67, 'gk_x')
    a.w(0x3029, 0x0162)                  # move.w $162(a1),d0  new presses
    a.w(0x3400)                          # move.w d0,d2
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
    a.w(0x0C43, len(SZF_TAPS))           # cmpi.w #3,d3
    a.bcc(0x67, 'gk_btn')
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
    a.bccw(0x60, 'gk_x')
    a.label('gk_btn')
    a.w(0x0802, 0x0009)                  # btst #9,d2          high punch (EC Y)
    a.bccw(0x67, 'gk_x')
    a.w(0x266A, 0x0034)                  # movea.l 52(a2),a3   the loser
    a.w(0x302B, 0x00BE)                  # move.w $BE(a3),d0
    a.w(0x0240, 0x7FFF)                  # andi.w #$7FFF,d0    (bit 15: the state ending)
    a.w(0x0C40, DIZZY)                   # cmpi.w #$1F,d0      dazed
    a.bccw(0x66, 'gk_x')
    a.w(0x426A, 0x0028)                  # clr.w 40(a2)
    a.w(0x42AA, 0x0034)                  # clr.l 52(a2)        FINISH HIM is over
    a.w(0x357C, 0x0001, 0x0018)          # move.w #1,24(a2)    start
    a.w(0x426A, 0x001A)                  # clr.w 26(a2)
    a.w(0x426A, 0x001C)                  # clr.w 28(a2)
    a.w(0x2549, 0x001E)                  # move.l a1,30(a2)
    a.w(0x254B, 0x0022)                  # move.l a3,34(a2)
    a.w(0x356B, 0x001A, 0x0026)          # move.w $1A(a3),38(a2)
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
    a.pcrel(0x41FA, 'gk_z')              # lea gk_z(pc),a0     no death art yet
    a.w(0x4250)                          # clr.w (a0)
    a.w(0x42A8, 0x0002)                  # clr.l 2(a0)         no head object
    for obj, task in ((0x2069, 'gk_park'), (0x206B, 'gk_load')):   # his move task parked,
        a.pcrel(0x49FA, task)            # lea task(pc),a4     hers loads her death art
        a.w(obj, 0x0088)
        a.w(0x2050)
        a.w(0x214C, 0x0004)
        a.w(0x4268, 0x0008)
    a.w(0x3029, 0x00B2)                  # move.w $B2(a1),d0   she, SZF_GAP px in front of him
    a.w(0x362B, 0x00B2)
    a.w(0xB640)
    a.bcc(0x6C, 'gk_r')
    a.w(0x0440, SZF_GAP)
    a.bcc(0x60, 'gk_sx')
    a.label('gk_r')
    a.w(0x0640, SZF_GAP)
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
    a.w(0x362C, 0x0002)
    a.bcc(0x67, 'gk_ns')
    a.w(0x3343, 0x001A)                  # his frame
    a.label('gk_ns')
    a.bccw(0x61, 'gk_head')              # her head where he holds it
    a.w(0x266A, 0x0022)
    a.bccw(0x61, 'gk_face')              # she faces him, whatever steps her script takes
    a.w(0x362C, 0x0004)                  # move.w 4(a4),d3     her death frame + 1
    a.bcc(0x67, 'gk_ret')
    a.pcrel(0x41FA, 'gk_z')              # lea gk_z(pc),a0
    a.w(0x3010)                          # move.w (a0),d0      her death sheet (- $100)
    a.bcc(0x67, 'gk_ret')                # none: she keeps her frame
    a.w(0xE148)                          # lsl.w #8,d0
    a.w(0xD043)                          # add.w d3,d0
    a.w(0x5340)                          # subq.w #1,d0
    a.w(0x3740, 0x001A)                  # move.w d0,$1A(a3)   her own object, her own colours
    a.bccw(0x61, 'gk_hset')              # (her hold steps: the same frame)
    a.w(0x377C, 0x0001, 0x0028)          # move.w #1,$28(a3)   (sheets $100+)
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
    a.w(0x7000 | FAT_PAUSE)
    a.jsr(0x68D6)
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
    for t in SZF_TAPS:
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
    a.bccw(0x61, 'gk_tail')
    a.w(0xD0FC, SZF_TAIL.get('ztab', 0)) # adda.w #ztab,a0
    a.w(0x7000)                          # moveq #0,d0
    a.w(0x302D, 0x004C)                  # move.w $4C(a5),d0   her id
    a.w(0x5540)                          # subq.w #2,d0
    a.w(0x0C40, 0x0019)                  # cmpi.w #25,d0
    a.bccw(0x64, 'gl_mus')               # bcc: not a fighter id
    a.w(0x1030, 0x0000)                  # move.b (a0,d0.w),d0 n + 1
    a.bccw(0x67, 'gl_mus')               # no death art
    a.w(0x3F00)                          # move.w d0,-(sp)
    a.w(0x0640, SZF_ZFILE - 1)           # addi.w #$EB,d0      file id
    a.w(0x3200, 0xD241, 0xD241)          # move.w d0,d1 / add.w d1,d1 (x2)
    a.w(0x3F01)                          # move.w d1,-(sp)
    a.w(0x41EE, 0x8CB4)                  # lea -$734C(a6),a0   EC's loaded-file list:
    a.w(0x42B0, 0x1000)                  # clr.l (a0,d1.w)     read it again
    a.w(0x223C); a.l(0x51800)            # move.l #$51800,d1   her .PL
    a.w(0xBBFC); a.l(0x2E188)            # cmpa.l #P1,a5
    a.bcc(0x66, 'gl_p2')
    a.w(0x223C); a.l(0x81800)            # move.l #$81800,d1
    a.label('gl_p2')
    a.w(0x2D41, 0x9190)                  # move.l d1,-$6E70(a6)  load there
    a.jsr(0x6C26)                        # EC's file load (CD read, chunks registered)
    a.w(0x42AE, 0x9190)                  # clr.l -$6E70(a6)
    a.w(0x321F)                          # move.w (sp)+,d1
    a.w(0x41EE, 0x8CB4)                  # lea -$734C(a6),a0
    a.w(0x42B0, 0x1000)                  # clr.l (a0,d1.w)     (not in EC's list: nothing frees it)
    a.w(0x301F)                          # move.w (sp)+,d0     n + 1
    a.w(0x3400)                          # move.w d0,d2
    a.w(0x5342)                          # subq.w #1,d2        n: sheet 1 = $100 + n (her head)
    a.w(0x0640, 0x0011)                  # addi.w #$11,d0      sheet $112 + n (- $100) ...
    a.w(0x0C40, 0x001C)                  # cmpi.w #$1C,d0
    a.bcc(0x6D, 'gl_s')
    a.w(0x5340)                          # subq.w #1,d0        ... one less from n = 10 (ZEC has none)
    a.label('gl_s')
    a.pcrel(0x41FA, 'gk_z')              # lea gk_z(pc),a0
    a.w(0x3080)                          # move.w d0,(a0)
    a.w(0x3142, 0x0006)                  # move.w d2,6(a0)     n: her head's sheet (gk_head spawns it)
    a.label('gl_mus')
    a.pcrel(0x41FA, 'f_time')            # lea f_time(pc),a0   MK's fatality music (after the read:
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
    a.w(0x0640, fr_fx(SZF_HEAD_BASE))    # addi.w #$44:head 0,d0
    a.w(0x3140, 0x001A)                  # move.w d0,$1A(a0)   his effect sheet, her head
    a.w(0x316B, 0x001E, 0x001E)          # move.w $1E(a3),$1E(a0)  her palette line ...
    a.w(0x316B, 0x0020, 0x0020)          # move.w $20(a3),$20(a0)  ... and facing
    a.w(0x317C, 0xFF00, 0x0052)          # move.w #-256,$52(a0) off screen
    a.label('gh_none')
    a.w(0x4CDF, 0x7FFF)                  # movem.l (sp)+,d0-d7/a0-a6
    a.bccw(0x60, 'gh_out')
    a.label('gh_have')
    a.w(0x2640)                          # movea.l d0,a3
    a.w(0x7000)                          # moveq #0,d0
    a.w(0x1029, 0x001B)                  # move.b $1B(a1),d0   his frame
    a.w(0x0440, fr(SZF_HIS_SLOTS[0]) & 0xFF)   # subi.w #first held slot,d0
    a.w(0x0C40, len(SZF_HIS_SLOTS))      # cmpi.w #8,d0
    a.bcc(0x64, 'gh_hide')               # bcc: not a held slot
    a.w(0xE548)                          # lsl.w #2,d0
    a.pcrel(0x41FA, 'gk_hoff')           # lea offsets(pc),a0
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
    a.label('gk_hoff')
    for dx, dy in szf_head_offsets():
        a.w(dx & 0xFFFF, dy & 0xFFFF)
    a.label('gk_hdesc')
    a.out += szf_head_desc()
    a.label('gk_hto')
    for o in SZF_TAIL.get('head_offs', [0] * len(Z_NAMES)):
        a.w(o)
    a.label('gk_z')
    a.w(0)                               # her death sheet (- $100); 0 = none
    a.l(0)                               # her head object
    a.w(0)                               # n: her head's sheet $100 + n
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
    a.w(0x42A8, 0x00CA)                  # clr.l $CA(a0)
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
    a.label('tc_lp')
    a.w(0x0C50, 0x0100)                  # cmpi.w #$100,(a0)    the end: none
    a.bcc(0x65, 'tc_nf')
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
    a.bccw(0x66, f'{pfx}_sv')
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


def r_generic(a, scripts, fwd, back, hit, throw, sounds={}):
    """A generic MK fighter's per-frame routine (a1 = him, this block's
    slot): his MK attack scripts in his move table, toward + Y throws behind,
    MK's walk cycle."""
    a.label('r_drag')
    a.w(0x0C69, SCORPION_ID, 0x004C)     # cmpi.w #id,$4C(a1)
    a.bccw(0x66, 'g_out')
    a.bccw(0x61, 'g_reg')                # bsr g_reg            his MK specials (r_gmoves)
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
    if SCORPION_ID == SUBZERO_ID:
        a.pcrel(0x45FA, 'vars')          # lea vars(pc),a2
        emit_gfatal(a)                   # his spine rip
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
    if SCORPION_ID == SUBZERO_ID:
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
        # 42:07) does nothing to a woman (the user, from MK): the split, no
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
    # throw: toward + Y reads as back + Y
    a.w(0x41EE, 0x0A3A)                  # lea $A3A(a6),a0     P1 pad ...
    a.w(0xB3FC); a.l(0x2E188)            # cmpa.l #P1,a1
    a.bcc(0x67, 'g_pad')
    a.w(0x41EE, 0x0A3C)                  # lea $A3C(a6),a0     ... P2 pad
    a.label('g_pad')
    a.w(0x3010)                          # move.w (a0),d0
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
    a.label('g_nthr')
    if SCORPION_ID == RAIDEN_ID:
        emit_rtele(a)
    emit_throwcall(a)                    # his throw's victim lands like MK's
    emit_hitdrive(a, throw, 'g_tw', 'g_out', False, THROW_MOVE, False)   # MK's throw animation
    emit_hitdrive(a, hit, 'g_ht', 'g_out', False)
    # walk: as Scorpion's (r_drag), resynced at each of EC's steps
    a.pcrel(0x45FA, 'gvars')             # lea gvars(pc),a2
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


def emit_pl_tail(a):
    a.label('pl_tail')
    a.w(0x207C); a.l(0x51800)            # movea.l #$51800,a0
    a.w(0xB3FC); a.l(0x2E188)            # cmpa.l #P1,a1
    a.bcc(0x66, 'plt_p2')
    a.w(0x207C); a.l(0x81800)            # movea.l #$81800,a0
    a.label('plt_p2')
    a.w(0xD1FC); a.l(GEN_TAIL['off'] or 0)   # adda.l #tail,a0
    a.w(0x4E75)


GENERIC_VARS = 64             # bytes: a generic block's vars (as Scorpion's: +14..+23 the flight, +24 a fatality,
                              # +52..+61 FINISH HIM)


# The other MK fighters' specials (MK1's inputs) on Blade's moves: $34 his
# projectile, $35 his dash. (dir1, dir2, button / DIR3|dir / 0, move)
GENERIC_MOVES = {
    19: [(DOWN, FWD, LP, 0x34),          # Raiden: lightning (down, forward + LP)
         (BACK, BACK, DIR3 | FWD, 0x35),  #   torpedo (back, back, forward)
         (DOWN, UP, 0, RTELE_MOVE)],      #   teleport (down, up): Blade's $31, a plain script, ours
    18: [(BACK, FWD, LP, 0x34),          # Johnny Cage: green bolt (back, forward + LP)
         (BACK, FWD, LK, 0x35)],         #   shadow kick (back, forward + LK)
    20: [(DOWN, FWD, LP, 0x34),          # Sub-Zero: ice blast (down, forward + LP)
         (BACK, 0, CHORD | LK | HK, 0x35)],   #   slide (MK CD: back + LK + HK - back + LK + Block is a low kick): Blade's dash
}


def r_gmoves(a, fid):
    """A generic fighter's special-move list and his copy of Blade's move
    handler (as Scorpion's in SUB.BIN, build), in his block: 'g_reg' (a1 =
    him) fills the list's absolute entry pointers (his slot's) and points
    the handler table's entry for his id at the handler."""
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
    a.label('gm_list')
    a.out += bytes(4 * (len(moves) + 1))
    for i, (d1, d2, btn, move) in enumerate(moves):
        a.label(f'gm_e{i}')
        a.out += struct.pack('>7H', 0, 2 * i, TYPE, d1, d2, btn, move)


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
        if fid == RAIDEN_ID:
            scripts[RTELE_MOVE] = rtele_plan(mk_dir)[0]
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
            if fid == SUBZERO_ID:
                d, ztab = szf_tail()
                SZF_TAIL.update(off=len(tail), ztab=ztab)
                tail += d
                tail += bytes(-len(tail) % 32)          # (the 68000 reads words at even addresses only)
                SZF_TAIL['heads'] = len(tail)
                SZF_TAIL['head_offs'] = []
                for tiles, _ in szf_heads():
                    SZF_TAIL['head_offs'].append(len(tail) - SZF_TAIL['heads'])
                    tail += tiles
                tail += bytes(SZF_HEAD_PAD)
        elif fid == SUBZERO_ID:
            raise ValueError('Sub-Zero\'s fatality needs his .PL tail (GEN_TAIL off)')
        GEN_TAIL['data'] = bytes(tail)
        a = Asm(0)
        _block(a, False, fid, ('drag', 'jumpup', 'launch', 'taps', 'finish'))
        r_generic(a, scripts, fwd, back, hit_plan(mk_dir)[0], throw_plan(mk_dir)[0], sounds or {})
        for name, fn in (('jumpup', r_jumpup), ('launch', r_launch), ('taps', r_taps),
                         ('gmoves', lambda a: r_gmoves(a, fid)), ('finish', r_finish),
                         ('music', emit_music)):
            while len(a.out) % 2:
                a.out += b'\0'
            if name in ENTRIES:
                a.label(f'r_{name}')
            fn(a)
        while len(a.out) % 2:
            a.out += b'\0'
        if GEN_TAIL['data']:
            emit_pl_tail(a)
        a.label('vars')                  # as Scorpion's (r_drag): +14..+23 flight
        a.out += bytes(GENERIC_VARS)
        return a.build()
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
    a.w(0x48E7, 0xC0C0)                           # movem.l d0-d1/a0-a1,-(sp)
    a.bsr_back('find')
    a.bcc(0x66, 'ko_none')
    a.w(0x4EA8, offs['finish'])                   # jsr finish(a0)
    a.label('ko_none')
    a.w(0x4CDF, 0x0303)                           # movem.l (sp)+,d0-d1/a0-a1
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
    if EXT_OFF + len(ext) > 0x6800:
        raise ValueError('extension block overflows the fighter slot ($6800)')
    bla = bytes(blaco) + bytes(EXT_OFF - len(blaco)) + ext

    org = (END + 15) & ~15
    code, at = stubs(org, offs)
    entries, ptrs = bytearray(), []
    eat = org + len(code)
    slot = 0x00                                  # Blade's own progress slots are free now
    for d1, d2, btn, move in MK_MOVES:
        ptrs.append(eat + len(entries))
        entries += struct.pack('>7H', 0, slot, TYPE, d1, d2, btn, move)
        slot += 2
    # Scorpion's own move list (MK moves only: his finisher is the fatality) and
    # his own copy of Blade's move handler (PLYR.CO $15604) reading it, so
    # Blade keeps his list. They live at sub_org (appended to SUB.BIN: PLYR.CO's
    # gap is full); the handler table ($153A0, by id - 2) points Scorpion's id
    # at the handler.
    h = Asm(sub_org)
    h.label('list')
    for q in ptrs:
        h.l(q)
    h.l(0xFFFFFFFF)
    h.label('handler')
    h.w(0x08A9, 0x0003, 0x011A)          # bclr #3,$11A(a1)
    h.w(0x45F9); h.l(sub_org)            # lea list,a2
    h.jsr(0x159D0)                       # the recogniser
    h.w(0x302E, 0x1634)                  # move.w $1634(a6),d0
    h.bcc(0x67, 'h_no')
    for m in (0x30, 0x34, 0x32):         # Blade's filters, as in his handler
        h.w(0x0C40, m)                   # cmpi.w #m,d0
        h.bcc(0x67, 'h_no')
    h.w(0x4A69, 0x0122)                  # tst.w $122(a1)
    h.bcc(0x66, 'h_go')
    h.w(0x4A69, 0x0126)                  # tst.w $126(a1)
    h.bcc(0x67, 'h_no')
    h.label('h_go')
    h.jmp(0x15404)
    h.label('h_no')
    h.jmp(0x68CA)
    sub_blob = shared + h.build()
    handler_at = sub_org + h.labels['handler']
    blob = code + bytes(entries)
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
    o = HANDLERS + 4 * (SCORPION_ID - 2) - BASE
    out[o:o + 4] = struct.pack('>I', handler_at)
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
HOLD_LONGER = ((0x26614, 0x11), (0x26620, 0x11))
CLOSE_JAB_HIT2 = 0x26034      # close X script: the second punch's attack step (42:20)
DIZZY_STEPS = (0x26314, 0x26320)   # dizzy script: 41:25 (hold 6), 41:26 (flag $2000: cut to 2 frames), then loop
DIZZY_HOLD = 120              # Blade's own two-frame dizzy loop barely moves: mkinputs drives the daze
DAZE_FRAMES = (0x4125, 0x4126, 0x4147, 0x4148, 0x4149, 0x414A, 0x414C)   # MK's 7 dazed poses (scorpion_map 'dizzy')
# MK's FINISH HIM daze (tools/mkdizzy.py, Sub-Zero waiting): a 7-pose sway,
# ~10 frames a pose, looped (~70 frames). One entry per r_drag call (every
# other frame): 5, 4, 5, 5, 5, 5, 6 calls per pose
DAZE_SEQ = tuple(k for k, n in enumerate((5, 4, 5, 5, 5, 5, 6)) for _ in range(n))
WALK_FWD, WALK_BACK = 8, 4      # EC states: walking forward / back (both play Blade's 40:16-40:1B cycle)
WALK_FRAMES = tuple(0x4064 + k for k in range(9))   # MK's 9 walk poses (scorpion_map 'walk_fwd')
# MK's forward walk (tools/mkmoves.py walk_fwd), frames per pose 3 4 4 5 3 4 5 3 5 (36);
# walking back is the same 36 frames reversed. One entry per r_drag call (every other frame).
_WALK36 = [k for k, n in enumerate((3, 4, 4, 5, 3, 4, 5, 3, 5)) for _ in range(n)]
# Walking back runs the same frames reversed, phased so that both line up
# with EC's own cycle (6 steps x 3 calls = the same 36 frames): at each
# step's first call EC shows its frame 40:16+j, whose art is the pose due
# then (WALK_EC_POSES). r_drag resyncs to EC's step, so no frame is off.
WALK_SEQ = tuple(_WALK36[2 * t] for t in range(18))
WALK_SEQ_BACK = tuple(_WALK36[(30 - 2 * t) % 36] for t in range(18))
WALK_EC_POSES = tuple(_WALK36[6 * j] for j in range(6))      # 40:16..40:1B


def recovery_still(co):
    """A generic MK fighter's module (a copy of Blade's): his projectile's
    recovery steps (40:64-40:6D) without Blade's forward drift, as Scorpion's
    (spear_script). Module offsets as BLA.CO's."""
    b = bytearray(co)
    for off in STAND_STILL:
        o = off - 0x21800
        b[o + 8:o + 12] = bytes(4)
    for off in STEP_FORWARD:
        o = off - 0x21800
        assert b[o] == 0x04 and b[o + 2:o + 4] == bytes.fromhex('041a'), hex(off)
        b[o] = 0x00
        b[o + 2:o + 4] = bytes(2)
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
    for off, dur in HOLD_LONGER:
        o = off - 0x21800
        assert b[o:o + 4] == bytes.fromhex('00060000'), hex(off)
        b[o:o + 2] = dur.to_bytes(2, 'big')
    # Blade's close-range X is a double punch (two hits per press); MK's jab
    # is one: the second punch's attack step becomes a plain step (moving the
    # script's end up instead froze fights). Its frames show MK's stance
    # (scorpion_map), so it reads as one jab and the recovery.
    # Blade's dizzy shows 41:25 for ~12 frames and 41:26 for 2; Scorpion's
    # holds the first (r_drag cycles MK's wobble over it: DAZE_FRAMES)
    for k, a in enumerate(DIZZY_STEPS):
        o = a - 0x21800
        assert int.from_bytes(b[o + 4:o + 6], 'big') in (0x4125 + k, fr(0x4125 + k)), hex(a)
        b[o:o + 2] = bytes(2)                              # no flag
        b[o + 6:o + 8] = DIZZY_HOLD.to_bytes(2, 'big')
    o = CLOSE_JAB_HIT2 - 0x21800
    assert b[o:o + 4] == bytes.fromhex('02060301') and int.from_bytes(b[o + 4:o + 6], 'big') in (0x4220, fr(0x4220)), b[o:o + 6].hex()
    b[o:o + 4] = bytes.fromhex('00060000')
    return bytes(b)


if __name__ == '__main__':
    from capstone import Cs, CS_ARCH_M68K, CS_MODE_BIG_ENDIAN, CS_MODE_M68K_000
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ex = os.path.join(root, 'extracted', 'ec_us')
    p, b = (open(os.path.join(ex, n), 'rb').read() for n in ('PLYR.CO', 'BLA.CO'))
    q, c, _ = build(p, spear_script(b), 0x20000)
    md = Cs(CS_ARCH_M68K, CS_MODE_BIG_ENDIAN | CS_MODE_M68K_000)
    org = (END + 15) & ~15
    print('--- PLYR.CO stubs')
    for i in md.disasm(q[org - BASE:], org):
        print(f'{i.address:06x} {i.mnemonic} {i.op_str}')
    ext, offs = ext_block()
    print('--- BLA.CO extension', {k: hex(v) for k, v in offs.items()}, len(ext), 'bytes')
    for i in md.disasm(ext[4:], 4):
        print(f'  +{i.address:04x} {i.mnemonic} {i.op_str}')
    print(f'PLYR.CO +{len(q) - len(p)} bytes (ends ${BASE + len(q):X}, limit ${GAP_END:X}); BLA.CO {len(b)} -> {len(c)}')
