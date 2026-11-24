# MK fidelity: the remaining differences (spec, 2026-11-19; updated 2026-11-23)

How these are worked: measure MK CD first (its own states, tools/lib/mkshangref.py and
tools/capture/mkreptileref.py, RAM where we can, enlarged frames where we can't), write the numbers
here, make a check that fails on today's build, then change the build until it passes. A fix is done
when its check is in tools/checks/allchecks.py, every check passes, and it has been seen in play.

Each item: what MK does (and how we know), what ours does, the target, the check, the cost.
Ordered by what the player notices most.

---

## 0. Play feel (a play test, Kano vs Reptile, 2026-11-19)

The fighters didn't feel like MK's in play. What was found, worst first.

### 0a. Jumps look like standing (Kano forward)
**Found**: the jump captures start with the fighter's stance cycle before the takeoff (Kano's
jump_fwd: poses 0-6 his stance, 7-8 takeoff, 9-17 the tuck); the build spreads the whole
capture over Blade's jump frames (scorpion_full.pick), so the early part of every jump shows
stance poses. Kano, Sonya, Sub-Zero and Liu Kang start with the stance; Kano's, Sonya's,
Sub-Zero's and Liu Kang's jump_fwd / jump_back / jump_up orders are identical (one recording
used three times? check against MK's screen before trusting them).
**Measured (ours, Kano)**: EC has one jump animation for every direction (Blade doesn't
flip): 40:02, 40:06 (crouch) 2, then 41:00 x12, 41:01 x12, 41:02 x10, 41:03 x8, 41:04 x2 in
the air, 40:06 x6, 40:00 - up, forward and back alike. 41:00-41:04 is the 'jump_up' group, so
every jump showed MK's straight jump, its first part his stance.
**Done** (scorpion_full.stance_lead): the jump frames start at the takeoff (no stance pose).
**Done for Kano, Johnny, Liu Kang, Reptile**: MK's roll (mkinputs.jump_plan, emit_jump_drive):
in the step-loader hook (r_jumpup, right after EC puts its frame in $1A) a forward / back
jump in the air shows the capture's airborne poses (<= 10, on free slots) on MK's timeline
fitted to EC's airtime (22 calls), timed by the sub CPU's frame counter ($2800E); the back
jump through the same poses. Checked from enlarged frames (rise, tuck, roll, upright, land).
**Open**: Sub-Zero (block 138 bytes free: tables to his .PL tail), Raiden (5 free slots, ~70
bytes), Sonya (18 bytes), Scorpion (his full block, its own r_jumpup); a jumpcheck in allchecks.
**MK**: from the takeoff (jump input + ~2 frames) the crouch-spring then the tuck/flip.
**Target**: no stance pose on any airborne frame; forward/back jumps show MK's roll at MK's
timing.
**Check**: a jumpcheck per fighter and direction: every frame while airborne ($52 above the
floor) shows a jump-capture pose past the stance (jumpcheck.py today checks heights and times
only); frame sheets to look at.

### 0b. Attacks move him / a kick glides forward
**Ours**: one kick slides him forward while it plays (Blade's scripts move him: step dx, the
header's speed flag $0400; mkscripts keeps Blade's wind-up step).
**MK**: measure each button's x travel (mk_2p states, his x per frame).
**Target**: per button, ours within ~5 px of MK's travel.
**Check**: attackcheck: x before/after each of the six buttons, standing and close, ours vs MK.

**Measured**: MK's Kano ($7BE34 = player 1's world x): every button lunges 10-13 px and ends
where it started. Ours: B (EC move 5, Blade's hopping lunge kick) went 59 px, ended 35 px on;
the others 0-4.
**Done** (mkscripts.build): MK attacks keep Blade's hit flags and data but none of his
movement (no wind-up step, slide or lunge): every button 0 px; B still hits from 57-89 px
(damage 6-7). Still to add: the attackcheck in allchecks, and MK's own 10-13 px lunge.

### 0c. A button "looks like it tries to throw"
**Ours**: unknown which (reported: one button at any moment shows a throw-like pose). Likely a
close attack (EC plays other moves up close: mkscripts MOVES $20-$25) or a pose spread from the
wrong capture.
**Check**: frame sheets of all six buttons far and close, ours beside MK's same button; find
the throw-like one, then fix its capture/pose mapping.

**Seen (Kano, sheets)**: close up, X and Y (EC $20/$21) are his MK headbutt (captured from MK
CD: MK1's Kano headbutts with his close punches): he lurches in, head bent into the
opponent - the likeliest "throw". (EC also throws on toward + Y up close; MK CD's own throw,
the high kick up close, is B here: notes 2026-11-23.)
**Done (2026-11-24)**: every MK fighter's close punch (X, Y) and knee (A) are MK CD's own close
moves, captured (mkmoves close_punch / close_knee); Raiden keeps the far ones (no room in his
.PL). tools/checks/closemovecheck.py; notes 2026-11-24.

### 0d. The Pit's music (fixed)
**Found**: the Pit is the Senator's stage mode ($1F), whose track is EC 13 (the Senator's
theme: "sounds like the Star-Spangled Banner"); MK's Pit music (MK track 4) was still on EC
track 17 (Blast's stage, from when the Pit was there). cdaudio.STAGE_MUSIC = {13: 4}.
**Check**: the built disc's track 13 file is MK's track 4; track 17 is EC's again.

### 0e. Attack timing ("still a bit clunky")
**Method**: both games, the attacker walked to the victim, one press; startup = frames to
the victim's health dropping; cycle = the least gap at which a second press does more
damage than one (MK: $7D7CA player 2's health; ours $2E330+$76). (MK's player x $7BE34,
player 2 $7BE3C screen, $7BE26 world.)
**Measured (Kano, at contact)**: MK - punches (his headbutt) hit at 13, again from 39; low
kick 10, again from 43. Ours - punches 9 / 50, low kick 9 / 40, high kick 7 / 34, roundhouse
9 / 44. EC adds ~12 frames around every script (LP's 22-frame script ends at 34).
**Measured (mid range; MK's contact gap is ~81, ours ~50)**: MK - punches hit at 10, cycle
~20-24 frames (a second press 20 frames on lands; pressed every 12, a hit every 24); low
kick 11 / 49. Ours - punches 9 / 33-35, low kick 9 / 40, high kick 7 / 34, roundhouse 9 / 40.
**Done**: the headbutt's strike hold gives back EC's ~12 frames (38, MK 39); every MK
fighter's punches (mkscripts PUNCHES) give back what they can after the strike (recovery,
then the strike hold to HIT_TICKS; not the wind-up): hit at 9, cycle 28 (MK 10 / ~22).
**Other fighters (MK, mid range, 2026-11-19)**: kicks land at 9-10 and the low kick cycles
at ~39 (Scorpion, Johnny) - as ours (40): kicks left as they are. The rest unreliable: each
MK state starts at its own distance with its own opponent (Raiden's never connected; the
damage-based cycle shows 4 for punches - the drain, see Kano's per-hit measure). **Open**: a
per-fighter MK measure with the gap set the same way in every state; an attackcheck.

### 0f. Throws between MK fighters (reported: thrown from one side of the screen to the other)
**Measured (throwcmp ec WHO --victim, path)**: Kano on Johnny - ours lands ~172 px behind, ends
167; MK 203 / 181 (MK's Kano throws that far: right). Johnny on Kano - ends 136 (MK 135), but in
the air ours swings out to -157 at 32 frames (MK -85) and -160 at 44, then snaps ~40 px back
(-121 at 48) before landing; MK's arc is smooth (-124 at 40, -141 at 48). Johnny is a swap-mode
thrower (turns on the last step: EC's side swap there); THROW_FAR's +35 px may be stale since
the tracks follow MK's path.
**Target**: Johnny's victim within ~15 px of MK's path every 4 frames, no snap.
**Check**: throwcmp path johnny (and raiden, the other THROW_FAR thrower) on an MK victim and
an EC one.

### 0g. Animation: where MK's poses are lost
**Tool**: tools/dev/animaudit.py (static: the build's frame map vs each MK capture's distinct poses).
**Measured (2026-11-19)**: our frames can show 41% of MK's distinct poses (1325 of 3170, 269
actions). Real losses, worst first: knockdown (MK 23-33 poses: fall, bounce, lie, get up - ours
2-3; every sweep, uppercut, big hit), throws (MK 24-32, ours 7-11), projectile casts (green
bolt 25->6, fireball 22->6, lightning 23->6, ice 18->5), the spear (34->8), Raiden's teleport
(31->8) and torpedo (25->7). Misleading rows: fatalities (their own playback, not frame groups),
jump attacks (MK's captures include the jump around the kick).
**Why**: each MK fighter is Blade with MK's art; EC plays a move through Blade's script (its
frame slots and timing): a 5-slot script shows 5 of MK's 12 poses. Attacks, walk, jumps now run
our own scripts / drives; knockdown, throws, casts still Blade's.
**Plan**: knockdown first (most seen); then throws, casts.
**Knockdown, measured (Kano as the victim of an uppercut, ours)**: $1C: 42:24 x20 (hit), 42:18
x44 (the whole flight: one pose), 42:17 x20 (lying), 40:06 x6, 40:1E x8 (getting up), stance.
MK's capture (Kano): stance, 16 airborne poses (7-22, up to ~147 px, down again), the landing
(23), getting up (24-28); Scorpion's: 7-26 airborne, 27-35 on the floor.
**Design**: one table-driven drive in the step-loader hook (r_jumpup) for every driven
animation - the roll and the knockdown (and later others): entries (EC state, condition
air/floor, its timeline of frame words, start by the frame counter), so a new animation costs
tables (in the .PL tail) rather than code: the roll's code (~110 bytes) becomes the one
routine. Knockdown: in the air (F6 bit 0) MK's airborne poses on MK's timeline (clamped at the
last falling pose: EC's flight time varies by the launch); on the floor in $1C MK's landing and
getting-up poses fitted to EC's 34 frames. Slots: ~12 per fighter (Kano 16 free after the
roll, Scorpion 19, Johnny 18, Liu Kang 21, Sub-Zero 13, Sonya 20; Raiden 5). Room: Sub-Zero
~12 bytes, Sonya/Raiden full - the refactor (one routine) first, then dead Blade code for room.
**Done (Kano, Johnny, Liu Kang, Reptile)**: mkinputs.kd_plan / emit_kd_drive - two routines
(roll, knockdown) rather than one table-driven: those four had room once the tables went to
the .PL tail (Johnny's block now exactly 5600). In the air the capture's airborne poses (<= 8)
by the calls since the launch; on the floor its landing and getting-up poses (<= 5). Checked
from enlarged frames (uppercut victims tumble, land, lie, get up). **Since done** for all seven
(mkinputs.KD_FIGHTERS, 2026-11-21): 2 air poses and 3 on the floor, Scorpion 4 in all
(KD_POSES_CAP), Kano's floor only his lying pose (KD_FLOOR_N): .PL room. **Open**: more poses (art
room); a kdcheck (distinct poses in the flight).

## 1. Reptile's aggression (CPU)

**MK** (tools/capture/mkreptileref.py video, a standing Kano): spear ~6 s, freeze ~12 s and ~28 s,
slide ~27 s, plus uppercuts and throws; Kano loses each round in ~10 s.
Not measured yet: a per-move count over a fixed time from MK's RAM (Reptile's move id each
frame), which is what the check should compare against.

**Ours** (90 s, Kano kept standing): ice 1, spear 1, slide 5; his AI (CHX.AI, the Eternal
Champion's second form's) picks a projectile about once a minute.

From the video's 40 s of fighting: projectiles 3 (spear 1, freeze 2) = ~4.5 a minute, slide 1.
Ours: projectiles ~1.3 a minute, slides ~3.3 a minute - the gap is his projectiles.

**Target**: over 60 s against a standing opponent, 3-6 projectiles with spear and freeze
both present (MK's ~4.5; to be confirmed by the RAM count), slides not above ~2; no stall.

**Check**: reptilecheck: a 60 s CPU fight, counting move starts $31/$34/$35.

**Done (2026-11-19)**: option (b) - rs_drive: while the CPU's Reptile has stood RS_EVERY (100)
calls he throws one himself (the spear within 125 px, else the ice blast). 60 s twice: ice 2,
spear 2, slide 3-4; no stall. (Slides from his AI stay ~3-4 a minute against MK's ~1.5.)

**Cost / risk**: medium. Options: (a) another EC AI file for him (an aggressive projectile
user: compare the .AI files' special rates); (b) in rs_drive, while the CPU's Reptile stands
at range, start a special at MK's rate (his own block has ~1.5 KB free). (a) first; (b) if no
AI fits.

## 2. EC throwers holding MK fighters by the wrong place (Rax "by the crotch")

**MK**: n/a (EC's throws). The fidelity target is EC's own: an EC thrower's hands land where
they land on an EC victim.

**Ours**: an MK victim of an EC throw shows his MK art on Blade's victim frames; EC's
thrower poses assume Blade's body (where his neck and shoulders are), so the hands land
elsewhere (Rax lifts Kano by the crotch).

**Target**: for each EC thrower x MK victim, the grabbed point (EC victim's neck/shoulder
in EC's own throw, recorded) within ~6 px of the MK victim's same body point, on the lift
frames.

**Check**: throwcmp ec (stock EC victim) vs ours: contact-point distance per lift frame,
plus enlarged frame sheets to look at.

**Cost / risk**: large: per EC thrower (about 13), victim poses or offsets per MK fighter
(dx/dy per step in the victim records - the throw tables already have per-victim entries).
Do the worst offenders first (Rax, then by measured distance).

## 3. Reptile's secret: MK's message over the win scene

**MK** (reference video): after the qualifying win, "YOU HAVE FOUND ME / NOW PROVE
YOURSELF !!" is written over the win scene (the loser lying there), ~5 s, then a fade,
LOADING, his fight. No button press.

**Ours**: the words are on EC's final-statistics screen after the win scene, and it waits
for Start.

**Target**: the words over the win scene within ~1 s of MK's moment, held ~5 s, then his
fight with no input.

**Check**: contest run to the secret (contestcheck with the qualifying win), recording the
frame the text appears and that no Start is pressed before his fight.

**Cost / risk**: medium. Needs where EC draws the win scene's text (the win message call in
SUB) and the skip of STATS's wait for Start (not found yet: STATS.CO's task end, $4FC).

## 4. Roll throws land late (Scorpion, Sub-Zero)

**MK** (throwcmp, mk_2p states): the victim lies flat on touching down ~50 frames in;
Scorpion stands out of his kick ~62.

**Ours**: ~58 and ~70 (8 frames late each).

**Target**: within ~3 frames of MK for both.

**Check**: throwcmp track scorpion/subzero: frame of lying, frame of the thrower's stance.

**Measured again (2026-11-19, Scorpion)**: ours knocked down at 48, flat at 57 (MK ~50): the
7 frames are EC's own fall/bounce (260A) - cutting it short makes EC replay the landing later
with him floating (tried: see the notebook), so not forced. Our victim lands ~27 px farther back
(-138 vs MK -111) and ends ~18 px farther (-100 vs -82); the thrower turns at 72 as MK's.
Next: the track's landing x (patches.THROW_TRACK / throwsim) for the distance.

**Cost / risk**: small/medium: the track's last ticks and THROW_POST for the roll throws;
throwsim predicts it.

## 5. Sonya: her normal throw, her sweep, her leg grab's track

**MK**: normal throw measured ((10, 2, 2, 2, 2, 2, 2) ticks, turn ~87); leg grab holds him
bent over her 16-44, flings ~175 px, lands ~104; her sweep drops him in place (as the others').

**Ours**: EC's timing for the throw; her sweep launches him ~150 px back (EC's); the leg
grab works but on its own track.

**Target**: as the other MK fighters (their checks: throwcmp, the sweep's drop distance).

**Check**: throwcmp sonya / sonya_sweep / leggrab.

**Done (2026-11-22, night): her normal throw, MK's.** MK CD's measured (throwcmp.py mk sonya / track
sonya): ticks (10, 2, 2, 2, 2, 2, 2), she turns as she stands (MK frame 87), the victim's path
patches.THROW_TRACK['sonya']. Room: her leg grab's hit-drive tables (60 bytes) went to a room
(emit_hitdrive room=True): her block 5540 of 5600. Ours against MK's (throwcmp path sonya): the
victim at MK's heights and frames (71 px at 32-36, ~20 at 40, ~12 at 44), lands at MK's frame, she
turns 4 frames later; seen side by side. Her leg grab (its own drive on EC's throw) passes both sides.

**Done (2026-11-22, night): the sweep.** A fourth room for room_put (mkinputs.GEN_DEAD): the bodies of
Blade's move scripts his block replaces every frame - PLYR $1A278 reads only each chain script's slot
and step count, so the rest is never read (deadscriptcheck.py: a fighter's running script never in
them). ~1 KB a fighter. Her r_swept_by (88 bytes) is there, its bsr the last 4 bytes of her block:
Larcen drops 9 px, as the others (sweepcheck.py now checks her). Her throw table (26) and anything
else of hers can go there too: move a room_put item out of her block (airland, zpose: 104 bytes).

**Cost / risk** (before): blocked on room. The sweep can't be data: EC takes the launch from the victim's
own knockdown header (PLYR $18984 loads $C6/$CA into his speed), the same whoever sweeps him, so
it needs r_swept_by's code: ~96 bytes, ~74 written tighter, plus its call. Her block had 0 bytes
left on 2026-11-22 (r_swept_by as a room_put subroutine: 104 over; her rooms are full - airland
and zpose already spill into the block), and SUB.BIN and PLYR's gap are full (14 bytes). Room
found so far: the leg-grab drive's two 7-frame lists as a table and a loop (~24 bytes) and its
hit-drive table (g_lg_tab, 52) into her .PL tail (~48 net) - ~72, still short. The throw table
needs 26 more. Check: sweepcheck.py 16 (Larcen slides 135 px; the others 9-12).

---

## 6. Scorpion's spear: MK's rhythm

**Measured** 2026-11-22: MK CD's capture (extracted/mk_moves/spear/order.txt, a hit) against ours
(Scorpion against Shadow, 109 px, back, back + LP, frame by frame):

| phase | MK CD (frames from the input) | ours |
|---|---|---|
| wind-up | poses 1-6, 3 frames each (5-21) | 2 poses, 4 frames |
| the spear flies | poses 7-14, 1 frame each (22-29) | 6 poses, about 12 frames |
| hit | frame 30 (pose 15, 5 frames) | frame 17 |
| hold (GET OVER HERE) | poses 16 / 18 alternating 2 frames each (35-57), then 16 held 12 (to 69): about 40 frames | about 13 frames |
| pull | poses 19-31 over 17 frames (70-86) | 12 frames (30-42) |
| after the pull | pose 32 held 24 frames, then 33 (5) and 34 (7): the move ends at 123 | back in stance at 55 |

**Ours is about half as long.** The hold after the hit and the recovery after the pull are cut short:
MK's spear has a long, menacing pause before the yank, and ours snaps.

**Cause, found:** EC's step duration is the word after the frame (ticks of 2 frames: PLYR $181DA,
move.w 2(a0),$12(a4)). Every spear step had 1. mkinputs.HOLD_LONGER had written its 'duration' $11 into
the step before's flags word ($F6), which never timed anything.

**Done 2026-11-22 (mkinputs.SPEAR_TICKS):**

| | ours before | ours now | MK |
|---|---|---|---|
| hit | 17 | 25 | 30 |
| hold | 10 frames | 16 | 35 |
| Scorpion free | 55 | about 105 | 123 |
| punish window (victim dazed after Scorpion is free) | 74 | about 42 | 43 |

The same at 90, 110 and 125 px. Reptile's spear too.

**The limit:** EC's hit reaction lets the victim go about 32 frames after the hit, then staggers him
about 14 more, whatever its stun count ($10C) holds: topping $10C up from the hit kept it up but not him
(traced 2026-11-22). The pull and the daze (r_drag) run in the victim's input task, which sleeps while he
is stunned, so a stun held longer also stops the yank: why both earlier tries lost the daze. The yank
must end about 48 frames after the hit.

**Done 2026-11-22 (later):** the hold 22 frames (from 16) and the pull 7 px a frame (from 6; MK ~6.4):
dazed about 45 frames after the hit from the spear's full reach (Scorpion 142 px, Reptile 145), at every
frame parity tried. Scorpion free ~117 frames after the button (MK 123), the punish window 43 (MK 43).
A 26-frame hold lost Reptile's longest yanks. **Open:** MK's 35-frame hold needs the daze started at
the hit (the victim drawn reeling until the yank, the daze's count from the yank) - a rework of r_drag
with no room in Scorpion's block today.

**Target:** our spear's poses on MK's timeline within a frame or two per phase. The victim's daze
already runs on (Shadow stands again 129 frames in). **Check:** `mkcompare.py scorpion spear --gap
100` (added 2026-11-22) at 80% or more frames on MK's pose. Today it is 38%, and the comparison
should be confirmed at a hitting distance. **Cost:** the spear script's step durations
(mkinputs.SPEAR_SCRIPT_EDITS / HOLD_LONGER) and the pull's drive (r_drag), and Reptile's copy.

## 7. The title says ETERNAL KOMBAT (done 2026-11-23)

The title screen and the main menu (drawn over the same picture) said "ETERNAL CHAMPIONS / CHALLENGE FROM
THE DARK SIDE". The picture is a still on plane B (40 x 28 cells, tiles 709-1537, GAME.DAT $3B0C-$A2AC,
plain pixels), palette GAME.CO $39A; the emblem's triangle is sprites. **Now** it reads ETERNAL KOMBAT -
CHALLENGE FROM THE DARK SIDE, the look chosen from mock-ups compared on the 23rd (MK's gold
KOMBAT tried first): KOMBAT in EC's own lettering (K from DARK, O and M from CHAMPIONS, T and A from
ETERNAL, B from CHAMPIONS' P), on ETERNAL's baseline, the K close in to the emblem with its red glow
fading onto it (4 colours in palette line 2's unused slots 12-15). 76 tiles rewritten, none shared;
the plane's map (in no file as plain words) kept as numbers in data/ec_title/plane_b.json.
**Check:** titlecheck.py (title and main menu, colour index for index; EC's picture everywhere else).
**Cost:** tools/lib/ectitle.py (the title-logo patch).

## Done 2026-11-20 to 22 (from play reports)

Each with what MK does, and the check that holds it. Where there is no check yet, it says so.

- **Hit sounds:** hits play MK's SMACK1, blocks BLOCK1, falls FALL2, in every fight, EC vs EC
  too (EC's thuds sounded weak). Each table entry has its own clip (a shared one left
  the hit sound looping). Check: `soundbankcheck.py`.
- **Grunts:** MK grunts (MALEJUMP; Sonya GIRLJUMP) as he leaves the floor on every jump. MK
  grunts on punches too, but over EC's music that made the whole game sound worse in play
  (compared against the build without grunts), so punches keep EC's whoosh. Check:
  `gruntcheck.py` (a grunt on each jump, none on punches or kicks).
- **Landing:** FEETLAND as a jump lands. Check: `feetcheck.py`.
- **Knocked out:** the loser lies flat; EC's landing frame is drawn lying (it showed MK's
  getting-up under Trident's vines). Covered by the fatality and stage checks' frame strips; no
  dedicated check.
- **Blocks:**
  - Z is MK's Block. Check: `blockcheck.py`.
  - EC has one frame each for the standing and the crouching block (42:36, 42:38). They now
    show the pose MK holds while blocking (`scorpion_full.held_pose`: the longest on the
    capture's timeline). The crouching block showed him standing, the standing one its wind-up.
    Seen for all seven fighters; **no check yet** (open: a pose check against the timeline).
- **FINISH HIM after a throw:** a throw that would win the match leaves the loser dazed on 1.
  EC applies a throw's damage in each fighter module's landing code, outside the hit path.
  Check: `throwfinishcheck.py`.
- **FINISH HIM left alone:** MK's FINISH HIM music stops at its end. Ours ran on into the
  fatality music, scream included, over the fade to the stats: the CD plays on past a part's
  end, so 30 s of silence follow it now. Check: `finishmusiccheck.py`.
- **Names:** EC's health-bar and win-message font has no hyphen: those say SUB ZERO (the
  versus screen and the stats keep SUB-ZERO). No check.

- **Shang Tsung and Reptile, selectable once unlocked:** they hold the Eternal Champion's two slots (11,
  26), which EC unlocks together when the Contest's Eternal stage is won (GAME.CO $14BE8: its counter at
  12). They are hidden at the start, as in MK1. Their select icons were EC's:
  - Reptile's is Sub-Zero's MK portrait with the blues turned green (MK's own palette swap);
  - Shang's is his standing pose's head and shoulders (MK1 has no picture of him), brightened for the
    icons' shared palette;
  - Shang's versus portrait is the same (also before the Contest's boss fight), his versus name SHANG
    ('SHANG TSUNG' ran off the screen);
  - Reptile's versus portrait is Sub-Zero's with the blues turned green, as his icon. EC has
    portraits for ids 2-25 only (writing one for 26 broke the game: `scorpion_portrait` asserts it)
    and drew id 26 as id 11 (GAME.CO $DF60), Shang's since he took that slot. Now id 26 draws
    Sub-Zero's tiles with a palette of its own, kept in the bytes freed by folding EC's palette
    loader's four copies (one per side) into one (2026-11-22, `reptile_portrait`; check:
    versuscheck.py).
  - Their pad specials already worked:
    - Reptile: ice blast (down, forward + LP), spear (back, back + LP), slide;
    - Shang: skull volley (back, forward, then HP; MK2's back, back, forward + HP needs three
      directions and a button, which the recogniser's entries can't hold).

- **MK's straight-up jump, as long in the air as its forward one** (2026-11-22): MK's captures
  (data/mk_meta jump_up, feet more than 12 px up) give 40-43 frames straight up, 38-46 forward, the
  straight-up jump lower - a lower gravity. Ours had EC's gravity (2 px a tick per tick) at MK's
  straight-up height: Kano 33 frames to MK's 43, Raiden 36 to 42. Now each MK fighter's jump script
  launches slower with a lower gravity (mkinputs.jump_up_launch, header +8 / +12) for MK's height and
  time; forward/back jumps get EC's gravity back in the flight ($6A) where the roll sets MK's launch,
  so they are unchanged (Kano 44 frames, 133 px). (The '54 frames, ours 42' noted before was the time
  between jumps with Up held - with the floor time - not the time in the air.) Check: jumpcheck.py.

- **EC's tints on MK fighters** (2026-11-22): EC fades a fighter caught by an effect (Riptide's
  bubble: down, down-forward, forward + Y) to one of six tint palettes kept in his module before his
  own ($3D20-$3DDF; PLYR's tint tasks at $1AC40-$1AD2C, through the module header +$18). Every MK
  fighter had Blade's, made for Blade's art's slots: Kano came out red and blue. Now each MK fighter's
  are his own colours mapped by brightness onto each tint's (patches.tint_palette). Check: tintcheck.py.

- **Liu Kang's flying kick, as quick off the mark as MK's** (2026-11-22; it was slow getting
  going): live on MK CD (mkmoves' script, the scroll taken out) he leaves the floor 4-5 frames after
  HK and kicks ~9-10 frames after it, travelling ~7 px a frame all the way. Ours stood 12 frames in
  place: flykick_plan read the capture's order.txt, whose first poses off the stance are his walk
  (forward held for the input) and which starts 24 frames after HK. Now the crouch a tick in place,
  the tuck two ticks on the move, then the kick: travelling 5 frames after HK, kicking at 8 (EC's
  recogniser starts the move 2 frames after the press). Raiden's torpedo, measured the same way, already
  matches MK's (moving 7 frames after forward, its flying pose on MK's frame, 7 px a frame to MK's
  7.5). Check: flykickcheck.py.

Still open from these reports:
- Blast's Vendetta, switched off on MK losers (VENDETTA_WINNERS): allowed in RAM (vendettacheck.py 14
  LOSER), as player 1 on Kano and Liu Kang it plays as on Blade (the loser in his own colours, then
  EC's burnt remains; no longer pale, 2026-11-22). As player 2, and on Sub-Zero, the test's grab never
  takes - but it never takes on Shadow (an EC loser) either, at any distance from 20 to 140 px: the
  test's setup, not the MK fighters. Switching it on (mkinputs.VENDETTA_WINNERS + 23) is a maintainer's decision.
- Kano's getting-up (his lying pose only) and Scorpion's knockdown (4 poses): .PL room.
- Trident's vines Overkill on an MK fighter is unverified (the lie-flat fix covers its frames).

## Earlier results of this method (2026-11-19, for reference)

- Reptile's spear: MK reference (rope out, stuck, yanked, dazed ~80 frames) -> reptilecheck
  (hit from ~125 px, pulled to <= 60, dazed 60-110 frames, stands again).
- His fight's height: MK's feet at screen line ~217 of 224 against the same wall rows
  (ours ~194) -> floor 757; reptilecheck checks the floor.
