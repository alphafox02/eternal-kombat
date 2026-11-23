# MK fighters that play like MK: the engine prototype (plan, 2026-11-19)

**Status:** superseded the same day by [../mk_fidelity_spec.md](../mk_fidelity_spec.md): rather than a
separate prototype, each difference from MK CD was measured, given a check and fixed in the build, one
at a time. Kept for its phase-0 findings (frame slots, the step loader, MK's timings).

From play: the MK fighters felt clumsy and erratic (odd animations, "a throw with nobody
there", a head disappearing), and without smooth, faithful MK fighters the mashup isn't fun.
Decision: a prototype - Kano made to play like MK CD's Kano - before converting the others.

## Why the current fighters are erratic

Every MK fighter is a copy of Blade's EC module with MK's art: every button, jump, hit and
throw runs Blade's move code with Blade's frame slots, timing and quirks. We have reshaped
moves one at a time (attack scripts, walk, roll, knockdown, punch timing); Blade's behaviour
leaks through everywhere else. Examples found in play on 2026-11-19:
- Z (our MK Block) is still Blade's move 3, his overhead punch, whose script shows his throw
  frames (42:0D-42:11) - MK's throw art: "a throw with nobody there".
- The straight-up jump: MK's height kept (scorpion_full KEEP_HEIGHT) on top of EC's own arc -
  at the peak his head leaves the screen.
- animaudit: our frames can show 41% of MK's poses (knockdown, throws, casts worst).

## Goal and how it's measured

Kano plays like MK CD's Kano: every action shows MK's poses in MK's order at MK's timing, his
inputs do what MK's do (MK's buttons: LP, HP, LK, HK, Block), nothing of Blade's shows.
Smoothness is measured, not judged by eye alone:
- **mkcompare** (to write): for an action, MK's frame-by-frame pose sequence (the capture's
  order.txt) beside ours (a recording of our fighter's $1A each frame, mapped to capture poses
  through the art map): pose match per frame, start latency (input -> first pose), duration.
  Exit: >= 90% of frames on MK's pose (+-1 frame) for every action in the list below.
- playing it (the final judge), with frame sheets for anything that looks wrong.

Actions: stance; walk forward / back; crouch; block (standing, crouching); LP, HP, LK, HK far
and close; roundhouse; crouching punches (uppercut) and kicks; sweep; jumps up / forward /
back and their attacks; getting hit (high, low), knocked down, swept, uppercut; throw;
his specials (knife, cannonball); dazed; his fatality.

## Two ways to build it

**A. Our scripts in EC's move system (the fast path).** Keep EC's move task and step loader;
make every one of Kano's move scripts ours: MK's timeline, every pose, exact ticks (a tick =
2 frames), on frame slots we lay out (his art is built by us: scorpion_full.build packs his
.PL). Remap inputs so MK's buttons start MK's moves (Z = Block: hold to block, no punch).
Drive what EC has no script for (jumps, reactions) as the roll and knockdown are driven.
Limits: EC reads input every other frame and adds ~12 frames around moves; EC's reaction and
physics code still decides hit reactions, knock-backs, jump arcs.

**B. Kano's own move task (the full path).** A move task written by us for him: reads the
pad every frame, runs MK's state machine (stand, walk, crouch, jump, attack, block, hit, down,
up), sets his frame, position and hit boxes every frame; EC's PLYR still does hit detection
(frame boxes) and health. His reactions as a victim ours too. Highest fidelity, the most
reverse engineering (what the engine expects of a fighter's task; the reaction pipeline).

**Plan**: A pushed as far as it goes for Kano, measured with mkcompare; whatever A can't
reach (latency, EC's reactions/physics) moves to B, one state at a time. Kano's module stops
being a Blade copy only where B replaces it.

## Phases

0. **Research** (below) and **mkcompare** + MK reference recordings for every action above
   (MK CD, mk_kano_2p.state, player 1 Kano; per action: input, frames until it ends).
1. **Kano A**: all scripts ours; Z = Block; jumps (heights: EC's arc, MK's poses); measured.
2. **Kano B for what A misses** (input latency first: a pad read every frame).
3. Kano played against EC fighters and against Kano. Go / no-go for converting the others.

## Research questions (phase 0)

1. Frame slots: can Kano's sheets hold more frames than Blade's (112/99/64/18)? (sheet tables
   in his .PL are ours: scorpion_full.build) - every MK pose its own slot.
2. Input: where EC reads the pad for a fighter and how often ($A3A/$A3C, the input task);
   can MK's Block be EC's block (hold away) without walking?
3. The move task and step loader: what a step can do (frame, ticks, dx/dy, hit event, flags);
   jump physics (EC's arc: $C6/$CA, the jump move); which of EC's per-move behaviours are
   in PLYR (shared) vs the module (Blade's).
4. Hit reactions: how PLYR applies a reaction to the victim (reaction id, knock-back, the
   victim's task parked/redirected) - what a fighter must do to show MK's hit poses.
5. MK's own timing per action from MK's RAM (frame per MK frame: MK's current animation
   pointer), not only the captures.

## Phase 0 results so far (2026-11-19)

- **Q1 answered**: his sheets can grow past Blade's counts (scorpion_full.build rebuilds each
  sheet chunk; up to 256 frames a sheet, 64 KB of records; the engine's bank registration
  carries the count - rewritten with the art): every MK pose can have its own slot.
- **tools/lib/mkcompare.py** (MK capture vs our recorded frames, per action; his stance by
  scorpion_full.stance_lead). Kano, first run:

  | action | match | MK frames / ours | note |
  |---|---|---|---|
  | btn_c (LK), btn_z (HK) | 89-90% | 34/36, 28/30 | MK's |
  | jump_fwd (the roll) | 89% | 45/42 | |
  | btn_a, btn_x (LP, HP) | 60% | 20/18 | right poses; MK holds the strike 9 frames, ours 4 (the punch trim cut the hold - MK's jab is 20 frames: 7x3 8x3 9x9 8x3 7x2) |
  | walk_fwd | 49% | 85/79 | right poses, the cycle's phase/timing |
  | jump_up | 17% | 47/44 | MK height + EC arc (head off screen) |
  | uppercut | 16% | 56/32 | |
  | roundhouse | 12% | 27/34 | |
  | crouch_c | 3% | 61/30 | |
  | jump_back, walk_back | - | | the tool maps them to the forward groups: to extend |

  So the standing kicks and the roll are already MK's; the worklist for phase 1 is the jab's
  hold (re-time: 7x3 8x3 9x9 8x3 7x2 in 2-frame ticks), crouching moves, roundhouse, uppercut,
  jump_up height, walk timing; then Z = Block, reactions.
