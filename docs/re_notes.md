# Reverse-engineering notes

Facts are marked as **seen** (verified in data or the emulator) or **guess**.

## The discs

- **seen** MK Kanzen-ban (JP) has the same files and audio as MK USA. Only the
  boot sector, region byte and file-index sectors differ.
- **seen** Psycho RFG v1.1 changes a few bytes in place: palettes in
  `BACKGD*.BIN`, code in `PAC.PRG` and `RJC.PRG` (cheat menu, credits, timer),
  plus new audio tracks. No files are resized.
- **seen** MK's `X*` files are exact duplicates of others, probably placed to
  shorten seeks.

## Mortal Kombat CD

- Each fighter is `NAME.OBJ` + `NAME.SCH`.
- **seen** `.SCH` is about 50% zero bytes with low entropy. **guess:** raw 4bpp tiles.
- **seen** `.OBJ` has no 68000 code. It opens with a table of offsets.
  **guess:** animation and frame tables, with the moves in the shared `RJC.PRG` / `PAC.PRG`.
- **seen** `BACKGD1-6.BIN` (stages) have high entropy. **guess:** compressed.

## Eternal Champions CD

### Architecture
- **seen** The game logic runs on the **sub CPU**. `SUB.BIN` loads at `$6000`
  (it uses the sub BIOS vectors at `$5Fxx` and gate-array registers `$FF80xx`).
  `MAIN.BIN` drives the VDP.
- **seen** Starting at `$68B2`, `SUB.BIN` holds a table of `jmp.l` entries.
  Further on, entries mix with small `move.l #x,d0; rts` getters, so the stride
  isn't uniform. Modules call these by absolute address: this is the engine API.
- **seen** Modules also call absolute addresses in `$4xxxx` (other resident
  modules, probably `GAME.CO`).
- **seen** Sub-CPU PRG-RAM is readable through a savestate (`Core.prg_ram()`,
  `dump` in scenarios). Calling `retro_get_memory_data(2)` segfaults in this core build.

### PRG-RAM map during a fight (Shadow P1 vs Blade CPU, Blade's stage)
| address | module | |
|---|---|---|
| `$06000` | `SUB.BIN` | engine |
| `$14000` | `PLYR.CO` | shared fighter code |
| `$1B000` | `SHA.CO` | fighter slot 1, `$6800` bytes |
| `$21800` | `BLA.CO` | fighter slot 2, `$6800` bytes |
| `$32000` | `PLYRSPR.BIN` | |
| `$34000` | `BLA.BGI` | stage code |
| `$37000` | `BLA.BG` | stage art |
| `$40800` | `BLAD.AI` | CPU AI |
| `$4A000`, `$4C800` | `SHA.SND`, `BLA.SND` | partly overwritten |
| `$51800` | `BLA.PL` | sprites, loaded byte-identical to disc |

- **seen** A fighter module can load in either slot, so modules are
  position-independent apart from engine calls. Budget: 26 KB of code per
  fighter (the largest EC fighter, `XAV.CO`, is 22 KB).
- **seen** `BLA.OC` and `BLA1/2.OD` aren't resident at the start of the fight;
  **guess** they load when the finisher triggers.
- **seen** Only one `.PL` is in PRG-RAM; **guess** the other fighter's is in Word RAM.
- **seen** `.PL` loads unchanged; frames are unpacked as they're drawn (below).

### File table
- **seen** `SUB.BIN` ends with the disc's file list (`$D107`-`$13CF4`): 308
  length-prefixed names (`MISC.BIN;1`, ...). A file's number is its index.
  Load call: `move.w #id,d0; move.l #dest,-$6E70(a6); jsr $6CC6` (also `$65C8`).
  Blade: `$21` BG, `$22` BGI, `$23` PL, `$24` CO, `$7B` OC, `$7C/$7D` OD,
  `$9E` SND, `$B8` AI, `$E0` VC, `$E1` VD. `$90` GAME.CO, `$48` PLYR.CO.
- **seen** About 780 bytes are free between the table end and `$14000`, room
  for roughly 50 new file names.
- **seen** `.VC` is loaded to `$51800` and called at `+$0A`: it's code.

### Resource files (`.PL`, `.VD`)
- **seen** Header: three longs, then (word type, long offset) entries from
  `+$0C`. Type `$18` = compressed sprite frames (`BLA.PL` at `0x14`); type
  `$04` = raw 4bpp tiles (`BLA.VD` at `0x14`, `0x7380` bytes).
- **seen** Frame unpacker: `SUB.BIN $11784`, called from `$FC24` with a0 = type-$18
  resource, d0 = frame (0-255), a1 = output (`$2F2D4`), a5 = fighter object.
  Output is at most `$12C0` bytes (150 tiles). Then `$CE1A` queues the VRAM transfer.
  - resource: long offset to the bank section, then 6-byte frame records
    (bank#, dictionary offset/2, literal-stream offset, opcode-stream offset).
  - bank section: `+2+4*bank` -> long offset of the bank.
  - opcode bytes dispatch via a jump table at `$1180C` into unrolled copy code
    (literal words from the literal stream, dictionary words by index).
  - `$1176E` resumes a partly unpacked frame (`-$3F6E(a6)` saves the state).
  - flag d6 bit 8: instead of unpacking, queue command `$88` in Word RAM
    (`$BDACE`) for the main CPU. The other fighter's frames are unpacked there.
- `tools/ecsprite.py` runs this exact routine under unicorn (68000 model).
  It's verified: decoded frame 25 matches 15/16 of tiles Blade has on screen,
  and the frames render as recognisable Blade art.
- **seen** Opcodes (measured by running the unpacker on synthetic data):
  `$00-$1D` n+1 zero words; `$1E-$49` n-$1D dictionary words (index bytes follow);
  `$4A-$53` n-$49 literal words; `$54-$67` alternating zero/dictionary;
  `$68-$6F` alternating zero/literal; `$70-$7B` repeated dictionary word;
  `$7C-$D1` literal + dictionary runs; `$D2-$F3` sequential runs from the
  second dictionary (a4); `$F4/$F5/$F6` **call** shared sub-frame (index byte +
  0/$100/$200) from the table at bank-section + word0; `$F7` return from call
  (no-op otherwise); **`$F8` yield**: save state, return, resume next video
  frame; `$FF` end.
- **seen** Sega's frames unpack in exactly two slices (one `$F8`, on a tile
  boundary, <= 77 tiles per slice). A frame with no yield unpacks fine in an
  emulator but deadlocks the real game (sub CPU frame budget).
- **seen** Bank section: word0 = offset to the shared sub-frame table (so
  bank count = (word0-2)/4: 48 for Blade), then long bank offsets. The shared
  sub-frames (288 for Blade) are body parts reused across poses and live in
  the banks too. No bank is used by only one pose, so overwriting any bank
  corrupts other poses (that was the first Scorpion test's hang).
- **seen** `.PL` chunk header: long length, long, long, word type, long
  absolute offset of the resource (= header + $14). Types: `$18` compressed
  frames (4 in BLA.PL: $14, $206C0, $23CB8, $25DFA, one per sheet $40-$43,
  all sharing the bank section at $2B8), `$04` raw tile pools ($2661C, $27DAA,
  for sheets $44/$45: effects). Sheet chunk header: long length, then
  `0004 0000 0000 01xx 00yy 0000`, then the sheet.
- **seen** Sheet frame record = word A + A x 4-byte boxes (x1 x2 y1 y2,
  signed bytes from the anchor, x forward), word B + B x 2-byte points (x y),
  then the piece list. Blade: A=5, B=4. Box 0 is the strike box (sits by the
  head at rest, reaches x=99 in the front kick 40:13); boxes 1-4 are the body.
  Same coordinates as the pieces. Keeping Blade's boxes under Scorpion's
  shorter art made hits land at Blade's reach; scorpion_full.fit_boxes now
  rescales them per frame from Blade's outline to Scorpion's (median front
  0.71, back 0.76, height 0.92).
- **seen** On the compressed path the game ignores the tile numbers stored in
  pieces: a pose's tiles are unpacked into one block and pieces take them in
  order. A piece = size word (VDP w/h bits << 8 | $50), attr word, x, y.
- **seen** Room to grow: player 1's `.PL` loads into Word RAM at $81800 with
  ~40 KB free after it (to $B1420). Player 2's loads into PRG-RAM at $51800
  with only ~1 KB before $7A800 (tile data). The Scorpion test grows BLA.PL
  by ~6.5 KB; it works as P1, and as P2 it ran a 30 s fight fine but
  overlaps that region: to be fixed.
- **seen** Piece lists follow the unpack at `$FC84`: word size/flags (negative
  = end), word tile attr (eor flip bits), byte x, byte y. **open**: where these
  lists live (`$2(a2)`, from the fighter's animation data).

### Module format (`.CO .OC .AI .BGI`)
- **seen** 10-byte header `00000000 0018 0000 0000`, code from offset `0x0A`.
- **seen** `.CO` (fighter) opens with five `bra.w` entry points.
- **seen** The engine is task-based. `lea body(pc),a1` + `jsr $6BB4` spawns a
  task running `body`; `move.l a1,4(a2)` (with a2 from `$88(a0)`) sets an
  object's next-state code.
- **seen** `$6966` and `$696C` take inline word lists ending in `$FFFF`.
- **seen** Engine = cooperative task scheduler. Task control block in a4:
  `+0` next, `+4` resume PC, `+8` sleep counter, `+A` return PC. Names in
  `tools/ec_api_names.txt`: `$68D6` sleep(d0), `$68D0` yield, `$6960` mark,
  `$68CA` end_frame (jmp; resume at mark), `$6A1A` halt, `$68B8/BE/C4` set code
  of the 1st/2nd/3rd next task, `$6BB4` spawn_object(d0 graphic, d1 x, d2 y, a1 code),
  `$6966/$696C` load resource lists, `$69FC` set_palette.

### Per-fighter / per-stage files (3-letter code)
| ext | contents |
|---|---|
| `.CO` | fighter code (moves) |
| `.AI` | CPU behaviour (e.g. `BLAD.AI`) |
| `.PL` | sprites, **guess** compressed |
| `.SND .VC .VD` | sound effects, voice |
| `.BG` | stage art |
| `.BGI` | stage code: about 44 engine calls, **guess** animated background |
| `.OC` | stage finisher code: 125-200 engine calls |
| `1.OD 2.OD` | finisher data, no code; **guess** Overkill and Sudden Death graphics |

- 16 stages have the full stage set. `CIR` and `PHA` are stages with no fighter.
- Hidden fighters `CHI DOG MON OWL SNA` have `.CO/.AI/.PL` but no voice.
- `ZB.* ZE.* ZK.*` (14 each) and `ZZ*.BIN` are large: **guess** video.

### Text
- **seen** `BACKUP.CO`: the warning screen is plain ASCII in fixed-width,
  space-padded lines separated by NULs, starting at `0x30A`.

### Graphics
- **seen** Neither game stores fighter tiles raw. Blade's on-screen tiles aren't
  in any EC file. Only HUD, shadows (`PLYRSPR.BIN`) and a few tiles in `BLA.VD`
  match. Scorpion's aren't in any MK file. Both compress fighter art.
- **seen** MK `.SCH` byte stats: 50% `$00`, 17% `$0C`, then values 16, 17, 18, ...
  with falling frequency. Looks like control codes of an RLE/LZ scheme.
- **seen** MK fighters are drawn as grids of 16x16 (2x2-tile) sprites with
  empty cells skipped. EC fighters use mixed sprite sizes.
- **guess** `.VC/.VD` = Vendetta code/data: the hidden animals have no Vendetta
  and no `.VC/.VD`.
- `tools/vdp.py` renders the sprite layer, sprite list and palettes from any
  savestate. That's ground truth for both games.

### Stats screen (`STATS.CO`)
- **seen** "FINAL STATISTICS": `STR LNG SWG SNP THR WHL SPC WPN`, finishing move
  (None / Overkill / Sudden Death / Vendetta / Cinekill), contest wins and losses.
- **seen** STATS.CO loads at $34000. Finishing-move text: 5-entry table at $65A
  indexed by `$1CD4(a6)`, record = x, y, text. Names: pointer table at $6B4
  indexed by fighter id - 2 (Blade = entry 7, 'BLADE' at $74C).
- **done** 'SCORPION' appended and repointed; `lea $3465A(pc),a2` (twice) ->
  `bsr` to a helper that uses a copy of the table with entry 3 = 'Fatality'
  when the finish is type 3 and the winner (`$8C` of the loser at `$1490(a6)`)
  is Scorpion.

### How a round ends (finishers)
- **seen** SUB.BIN's fight runner ($BDA4) loops until `$AB7(a6)` bit 7, or
  bits 0 and 1, are set; then the round-end handler ($6D8C). If
  `$1CD4(a6)` (round-end type: 0 normal, 1 Overkill, 2 Sudden Death,
  3 Vendetta, 4 Cinekill) is non-zero it's a finisher: `$1488(a6)` = $FFFF,
  the fighter with more health gets +8 wins (match over) -> final stats.
  GAME.CO indexes score tables by `$1CD4` ($7AAA, $FAF8): no new types.
- **seen** Vendetta: the finisher move (BLA.CO $1D2D2) calls `$6D10` (d0=3,
  music), `$6D28` (= PLYR.CO $19472: parks both fighters' other tasks,
  victim health 0, victim hidden ($82 bit 7), `$1490(a6)` = victim), loads
  BLA.VC/VD at $51800 and runs it; BLA.VC sets `$1CD4` = 3 and later
  `bset #0/#1,$AB7(a6)`. These must run in the fighter's own move task
  (they act on the task chain through a4).
- **seen** Health 0 alone ends nothing: a fighter idling at 0 just stands.
- **done** Scorpion's fatality ends the same way (mkinputs `f_kill`).
- **seen** Damage is applied at PLYR.CO $19854/$19D22/$19EC6 (then
  `tst; bpl; clr` clamps at $1985A/$19D26/$19EFA) and $19FAE (projectile:
  `sub.w d6,d4; move.w d4,$76(a3); bgt` -> straight to the KO when <= 0).
  During a hit reaction the move task is parked ($104FA) and its own resume
  address restored afterwards, so a new daze must start once BE is 0 again.
- **seen** MK (measured on the MK disc): at FINISH HIM the round music fades
  out; when the fatality starts the stage darkens to about half (fighters
  stay lit) and the fatality music plays.
- **done** Same here: FINISH HIM pauses the music; the fatality halves the
  stage's palette lines and plays MK's music; the victim gives his own
  knock-down yell when the fire hits (each module's `move.w #id,d0; jsr
  $6D58; move.w #$1C,$118(a5)`; fighter ids follow SUB.BIN's .SND list).
  FINISH HER for Shadow, Jetta, Raven (ids 2, 10, 21).
- **done** FINISH HIM (MK rule): all four sites call mkinputs `finish`: when
  the blow that would win Scorpion the match lands (EC's own test: wins + 1
  >= $15F16[$1CFE]), the loser keeps 1 health, is dazed when the reaction
  ends, and FINISH HIM plays. ~1 s grace (rest of the winning blow doesn't
  count), then a hit is an ordinary KO; the fatality only works in this
  window; no time limit (EC's round timer still applies).

## File loader (SUB.BIN $65C8)
- **seen** `.PL`/resource files are a chain of chunks: long length (0 = end),
  word type (index into the jump table at $65EE: 0 = register a $D448 tile
  source (slot, type, -, word, data), 4 = register a sheet (slot*4, head
  words, sheet), 8 = $13A4 table, $1C = relocated pointer table at -$6E6C...),
  skipped long, body. The next chunk = this chunk + length. Zeroing a
  chunk's length ends the file for the loader: nothing after it gets
  registered (that was the full-skin hang).

## Controls and move map (measured)
`tools/ecprobe.py` plays every input in a 2-player duel (tests/scenarios/
04_duel saves states/duel.state; P1 object $2E188, P2 $2E330) and records
Blade's frames. EC: X/Y/Z punches, A/B/C kicks, hold back = block, QCF+C =
Blade's projectile (frames $40:60-63, $42:28-29). Frame $42:26 = stance he
returns to after moves. Mapping to Scorpion in tools/scorpion_map.py
MEASURED (overrides the visual RANGES): X jab -> MK low punch, Y -> high
punch, Z overhead -> uppercut, A knee -> low kick, B front kick -> high kick,
C spin kick -> roundhouse, down+C -> sweep, QCF+C -> spear throw.
Palettes: BLA.CO $3DE0 main, $3E00 alternate (mirror match) -> MK Sub-Zero
(MK1's Sub-Zero is Scorpion's sprites with another palette).

## Sound
- **seen** MK CD's `SFX*.BIN` are IFF 8SVX: one FORM per sample with NAME,
  VHDR (rate) and BODY (signed 8-bit). 118 named samples, including
  GETOHERE.SVX (8025 Hz, 1.01 s), SCORwins, SCORPION, FATALITY, FIGHT,
  FINISHim, FLAWVICT, MALEHURT, CHEERING. `patches.mk_sample(name)` reads one.
- **seen** EC `.SND` files are the same chunk chain as `.PL`: type `$1C`
  (sound table: slot, count, entries with id, flags and a rate-like word,
  e.g. `$28A0`), type `$20` (PCM for the Sega CD RF5C164: sign-magnitude
  8-bit, `$80` silence, `$FF` end of clip). Data starts 16 bytes into the
  chunk (`slot word, long, then PCM`).
- **seen** Sound table entries ($1A bytes): id word, ..., rate word (Hz) at
  +10, clip word at +$18. When a bank loads, the driver (PRG RAM ~$47000-
  $49000) fills +2 (length - 1), +$14 (start page) and +$16 (end address:
  each frame it compares every channel's address with it and keys the
  channel off on a match).
- **seen** A PCM chunk (type $20: +10 sample slot, +12 clip 0's length) holds
  clip 0, then for each further clip a 4-byte length and the clip (every
  EC .SND: BLA had 00 00 16 E4 right after clip 0). Lengths include the
  closing $FF and must be even (the next length is read as a long). The
  driver reads clips until the chunk ends, copies each to its own page of
  sound RAM (FIGHT.SND at 0, player 1's bank from $3F00, player 2's right
  after, then the stage's).
- **seen** Broken layouts and what they did: data where a length belongs
  hung the stage card or crashed; $80 filler after the last clip (read as
  a huge length) crashed; a missing clip end leaves the loop address $0000,
  so the channel loops FIGHT.SND's first sound.
- **done** `scorpion-voice`: BLA.SND chunk rebuilt as GETOHERE ($06D6),
  FINISHim ($06D9), FINISHER ($06DB), silence, all at 5200 Hz. Blade's own
  plays of $06D7/$06DA/$06DB in BLA.CO are skipped (bra.s).
- **seen** CD music: $60DE(d0 = track) = BIOS MSCPLAYR ($13) + fader ($85,
  $2B3); $6D10(d0 = 3) = BIOS MSCPAUSEON. Stage tracks: SUB.BIN $ABEC
  (stage ids) / $AC12 (tracks); track 19 = menus. EC freezes mid-fight on a
  disc with 20 tracks (even a copy of track 19); a longer track is fine.
  Emulators play pregap (INDEX 00) audio as silence.
- **seen** MK (sound chip traced on the MK disc): FINISH HIM at frame 1521;
  track 13 (2 s silent head, then the music) starts 26 frames later; when
  the fire hits, BURNUP.SVX and an unnamed 16 kHz man's scream (SFX3E.BIN,
  Scorpion's fatality bank, also in 3A/3F/3G) play together; later
  FLAWLESS VICTORY and FATALITY. An unfinished loser collapses ~250 frames
  after FINISH HIM. MK has no woman's fatality scream (GIRLHURT is
  Sonya's cry).
- **done** Appended to track 19 (build.add_mk_jingle): MK's track 13 (with its
  head), and two mixes of its music with BURNUP + the man's scream / Sonya's
  cry at the fire (108 frames after the fatality starts, less 0.2 s CD jump
  delay). FINISH HIM starts the first (BIOS MSCPLAYT $14, BCD mm:ss:ff:00),
  the fatality jumps to the mix for the victim. Times written by the last
  patch (fatality-music). A menu left for its whole 110 s loop plays them.
- **seen** Round clock: BCD word at -$2AE6(a6) ($2D51A). Set to 1, EC's next
  tick is time-up and the one with health wins (0 wraps to 99). An
  unfinished FINISH HIM uses that after 125 r_drag calls (MK's 250 frames);
  she stands through EC's time-up instead of collapsing.

## Blood and the spear rope
- **seen** EC's normal hits draw no blood (white sparks only). Effect objects
  ($A6 bytes) take their sprite palette line from bits 13-14 of $1E/$20:
  line = ((attr >> 13) & 3) ^ 1 (probed); a fighter's is ($7A & 3) ^ 1.
- **seen** EC's hit code waits for a free effect object: too many live blood
  drops froze a fighter mid-reaction (and the mashing tests).
- **done** Blood: EC's spark tile (colours 12/13) drawn with Scorpion's line,
  where 12/13 are dark red / red. His art's 12/13 moved to 7/8 (exact
  duplicates of 2/5, so scaled art never used them): scorpion_full
  COLOUR_MOVES, patches.scorpion_palette. 6 drops per hit, at most 6 alive,
  sprayed away from the attacker; the spear bleeds from the victim's chest.
- **seen** The double rope: MK's capture shows two strands for one frame
  (pose 17) as the rope snaps taut; evenly sampled, that pose filled the
  hold frames 42:2E-42:30. scorpion_full.pick skips double-strand poses.

## Close jab, walking back, blocking
- **seen** Blade's X up close is a different move: a double punch (41:46,
  42:19-42:22; two hits of 3, script at BLA.CO $25FD4). 41:46 sat in the
  spear art range and showed MK's spear-with-rope pose. Now: second attack
  step ($26034) a plain step, art = MK's jab then MK's stance. (Moving the
  script's end up instead froze fights.)
- **seen** Holding back: frames 40:1B..40:16, state 4 (walking back); a block
  is 42:36, state 7. The map had walk_back and block swapped.
- **seen** Opponent attacking: $F6 bit 5 clears from an attack's first frame
  (also in jumps); $100 bit 5 clears later. State ($BE) values overlap
  (walk forward and the knee are both 4).
- **done** Z (MK Block) stands still: Z/Up/left/right removed from the pad,
  back fed only while the opponent attacks. Holding back stays EC's
  walk-back-and-block.

## Roster: fighters in their own slots
- **seen** (subagent survey + checks) Selection index idx = id - 2 ($1428/$142A);
  real id from SUB $AED2[idx]. Per-idx tables: SUB $AF04 .CO, $AF36 .PL,
  $AF68 .SND (file, bank slot), $B6B8 .AI; $5970 HUD name pointers; $CB90..
  fixed win-name fields; $11E8C object descriptors (by real id, 34 bytes:
  first frame, module entry, ...). GAME.CO $DB1C versus names, $E048 + 32 *
  (idx + 3) versus palettes; GAME.DAT versus portraits ($EA0 bytes: idx < 17
  from $23D30, else $33604 + (idx - 17) * $EA0), select icons $300 bytes from
  $1FAC8 + $300 * (idx - 7). STATS.CO $6B4 names. PLYR.CO $153A0 move
  handlers (longs by idx).
- **seen** The select grid already has 25 slots (3 rows); a slot shows when
  bit idx is set in $1CC8(a6), initialised (with $14A4) by move.l #$004831FF
  at SUB $BC6C/$BC84.
- **seen** A .SND carries its fighter's sample slots (+10 of each chunk) and
  sound ids; Blade's bank in another slot crashed the fight loader.
- **done** Scorpion = Blade's files + patches in Blast's slot (BST.*, id 23,
  idx 21, unlocked, 13 presses right on the grid). His own copy of Blade's
  move handler + MK move list live at the end of SUB.BIN (PLYR.CO's gap is
  full; SUB.BIN may end below $14000: ~700 bytes left). Blade is stock again.
- **seen** A .PL's tile sources (chunk type 0, +10 = id * 4) and sheets (type
  4, +10 = sheet * 4, +12 = its tile source id) are numbered per fighter
  (Blade: sources $8A-$94, sheets $40-$45; Blast: $124-.., $8D-$93) in global
  tables. Two fighters with the same numbers (Scorpion as a copy of Blade, vs
  Blade) hung the fight after loading; same for the .SND slots.
- **done** patches.renumber_sheets: Scorpion's sheets $40-$43 -> $8D-$90 (329
  frame words in animation steps and other records, 42 move.b #sheet,$1A,
  4 registrations, the descriptor's first sheet), tile sources -> Blast's;
  effect sheets $44/$45 keep their numbers (same art in both files).
  mkinputs.fr() for my frame constants. tools/sheetcheck.py plays every probe
  action + MK specials, at range and close: all 107 frames on $8D-$90.
- **seen** Chicago Theater Overkill (correction 2026-11-13: the theater is LAR's stage,
  mode $1B, on the stock disc; mode $13 / BST is the 'Song Hung Delta 1955' jungle;
  the ranges below are LAR.BGI's): handler (via
  $14FA(a6)) checks the loser's x against $223-$279 (also $170-$1C3, and
  $284-$2C4 by facing); with the deciding round, loser health <= 20 and 10+
  damage taken ($190), the drive-by plays (tools/overkillvideo.py).
- **seen** The Overkill first stuns the victim with EC's dizzy (state $1F,
  Blade frames 41:25/41:26, ~8 s), then knocks him down (42:24, 42:18,
  42:17) and leaves him lying (42:0C, state $7FFF). Its shots are not
  fighter hits (no blood from the hit path).
- **done** 41:25/41:26 = MK's hunched dazed poses (tools/mkdizzy.py: Scorpion
  as the loser at FINISH HIM, poses 0-1); 42:0C = MK's flat pose from the
  same capture (pose 13; the knockdown capture's flat pose was cut off at the
  screen edge: no head). The pose crop is anchored at the head, so flat
  poses get a centred anchor. EC's own white hit spark is sent off-screen
  ($1444) when Scorpion is in the hit: MK has only blood. Scorpion bleeds
  whenever he reaches his hit frame while $1CD4 is set (r_drag).

## Full skin (scorpion-full patch)
All 293 poses of sheets $40-$43 rebuilt from MK poses captured by
`tools/mkmoves.py` (2-player MK, Sub-Zero idle; button map A LP, X HP,
B/Y block, C LK, Z HK). Mapping by category in `tools/scorpion_map.py`;
87 distinct poses in 5 banks, 104 KB in the 120 KB that Blade's banks held,
same file size (both player slots fine). Shared sub-frame table emptied.
Name: HUD/versus still read BLADE (packed name lists, not yet changed).

## First crossover (scorpion-idle patch, superseded by scorpion-full)
Blade's idle (sheet $40 frames 0-2) and intro poses replaced by Scorpion's MK
idle frames, captured from MK from VRAM (now done by `tools/mkmoves.py`; exact
pixels and palette); palette swapped in BLA.CO $3DE0. New data is appended to
BLA.PL behind a new bank section for resource $14 (48 re-based banks + 1
new, copy of the sub-frame table); the file is relocated to the end of the
data track (`Disc.replace_file`). Verified: all 99 untouched sheet-$40 frames
decode byte-identical; scenarios 02/03 fight to the end.

## Emulator quirks
- The bundled Genesis Plus GX build dereferences every core option without
  checking, so the front-end must answer every `GET_VARIABLE`. See `DEFAULT_OPTIONS`.
- A savestate taken while the game is reading the CD restores broken: the
  screen jumps back and later CD loads hang. Save only when the game is idle.
- VDP state in a savestate: offset `0x12025` (SAT cache, VRAM word-swapped,
  CRAM 9-bit BBBGGGRRR little-endian, VSRAM, regs at `+0x10500`).
- Loading the core twice in one process doesn't fully reset its CD drive.
  `play.py test` runs each scenario in its own process.


## Special moves, hit reactions, CPU (PLYR.CO)
- **seen** Special-move recogniser: PLYR.CO `$159D0`/`$15A62`. Per fighter a
  handler from the table at `$153A0`, indexed by fighter id (`$4C(a1)` - 2;
  Blade = 9, Shadow = 2) loads `a2` = longword list of entries (Blade:
  `$164AC`, 12 entries). Entry: word level (skipped while > `$148`, inner
  strength), word progress slot, word type (x4, jump table `$15A82`), args.
  Types: `$00` charge back -> fwd+btn, `$04` charge down -> up+btn, `$08` hold
  button, `$0C` QCF+btn, `$10` QCB+btn, `$14` half circle, `$18` button combo,
  `$1C` fwd+btn, `$20` hold buttons, `$24` direction sequence (finishers:
  opponent dizzy `$BE`=`$1F` and close). Success: d6 = move id -> `$15AB0`.
- **seen** Player object input: `$162` new presses, `$164` held directions
  (raw; flip L/R when `$20` bit 3 is set), buttons X `$400` Y `$200` Z `$100`
  A `$40` B `$10` C `$20`. Blade's moves: `$34` projectile (QCF+C), `$35`
  dash (charge back, fwd+B) - travels ~130 px through the opponent.
- **done** tools/mkinputs.py: new type `$28` "two taps + button" in the 398
  free bytes after PLYR.CO (`$1AE72`-`$1B000`, zero in every fight), via a
  hook on the dispatch at `$15A7C`. Blade's list now: back, back + X (LP) =
  `$34` spear; down, back + Y (HP) = `$35` teleport; his finisher entry.
- **seen** CPU fighters skip the recogniser: the AI's move id `$1D20(a6)` is
  copied to `$1634(a6)` at `$15120` (and `$152E0`). **done** filtered so
  Scorpion's CPU only uses `$34`/`$35` from Blade's specials (`$2C`-`$36`).
- **seen** Hit routine `$1978E`..: a5 = attacker, a3 = victim, a1 = attack
  record (word stun -> `$10C`, byte push frames -> `$112`, byte push -> `$110`,
  byte reaction -> `$118`); the spear uses the shared record at `$1A48C`.
- **seen** `$18852` is the animation-step routine for every fighter: reads
  the step (frame, velocity...) and sets x velocity `$C6` (16.16, 2 units =
  1 px/frame), signed away from the opponent for hit reactions. Velocity
  tweaks there only act once per step, so they can't steer a pull.
- **done** spear pull = per-frame drag hooked into both input tasks
  (`$1504E` P2, `$15210` P1, before the human/CPU split): while the opponent
  is Scorpion in move `$34` and this fighter is reeling (`$BE` `$1A`-`$1D`),
  cancel his knock-back (`$C6`), move him 6 px/frame (`$B2` and `$4E`) to
  60 px from Scorpion, and keep him there. Hits from <= ~133 px.
- **seen** Spear reach isn't the frame boxes or points (stretching them to
  127 changed nothing measurable); Blade's projectile code decides it.
- **correction** Bytes appended to SUB.BIN DO load (the name patch uses
  them). The earlier test was fooled by states/menu.state: SUB.BIN loads at
  boot, so every scenario starting from that state runs the SUB.BIN of the
  build that made it. Rebuild it (scenario 01) after changing SUB.BIN.
- **seen** Real 2-player Duel: player 2 must press start on the select screen
  before player 1 picks (tools/duelstate.py); otherwise player 2 is the CPU.
- **seen** "Enter Duel" with the opponent picked on the select screen is
  against the CPU (player 2 acts on its own); bots there aren't symmetric.
- **seen** Frames over ~112 tiles draw as scrambled tiles for a frame or two
  (unpack runs past its two time slices); scorpion_full caps poses (TILE_CAP).


## Scorpion's MK behaviour (tools/mkinputs.py), measured against MK
- **seen** Sounds: `jsr $6D58`, d0 = sound id. Ids come from each .SND's
  type-$1C tables (FIGHT.SND $03EA-$03F0, BLA.SND $06D6-$06DB); the rate word
  is Hz. A hit plays the attack record's sound (word +8, copied to `$1640`).
  RF5C164 channel state in the savestate at `0x28085` (16 bytes per channel,
  little-endian addr<<11, start<<11, fd), PCM RAM at `0x2810D`.
- **seen** Animation scripts are 12-byte steps (BLA.CO spear: `$26584`):
  `80 16 nn 1D` = attack event (damage nn, reaction $1D), `80 12` = Blade's
  throw-over, `04 xx 04 1A` = step forward; frame word at +4, dx/dy at +8.
- **seen** `$118` is the reaction applied on the next hit (consumed in each
  fighter module, e.g. BLA.CO `$22B54`), not a general move queue. Tasks:
  object `$88` = task chain, TCB +4 resume PC, +8 sleep. A fighter's moves run in
  the SECOND task of the chain (the first never changes); his dizzy can be
  started by resuming that task at PLYR.CO `$17C9A`; that generic
  dizzy never ends by itself (EC players mash out).
- **done** Extension block appended to BLA.CO at `$5200` (tag 'EKSC'); stubs
  in PLYR.CO's tail find it in slot 1 or 2. Bytes appended to SUB.BIN never
  load; the .CO loader loads the whole file.
- **done** MK measurements (MK disc, `mk_2p.state`): spear sticks ~35 frames,
  yank ~16 frames at ~6.4 px/f, lands ~42 px away, daze ~80 frames; uppercut
  peak ~150 px, ~86 px back, ~68 frames in the air. Implemented: rope stuck
  while Scorpion's hold frames play, yank 6 px/f to 56 px (EC bodies are
  wider), daze 80 frames via a countdown that returns the victim's task to
  its recorded idle address, uppercut (down + HP) flies the victim on MK's arc.
  Works on Blade/Sub-Zero and on Shadow.
- **done** Fatality (MK: hold Block, Up, Up from about half a screen; here Z =
  Block): with the opponent dazed at <= 21 health, both move tasks are parked,
  the victim is put 90 px away and a timeline plays Scorpion's MK frames
  (unmask, skull, fire) and draws the victim with Scorpion's fire, charred
  (his own pose, black palette) and skeleton frames (victim palette line =
  Scorpion's). Then Scorpion's move task runs `f_kill` (see "How a round
  ends"). `tools/fatalitycheck.py` checks it end to end.

## Names and portrait
- **seen** HUD (health bar) names: window plane, font tiles $64F + letter;
  text from SUB.BIN's NUL-separated list ($5A08 BLADE), pointer table
  (longs) with Blade's pointer at $598C. Versus title: GAME.CO list
  ('\x04BLADE', first byte = centering offset), pointer table at $DB1C,
  Blade's at $DB38 (GAME.CO loads at $14000 on menu screens). "SCORPION" is
  appended to both files and the pointers moved.
- **seen** Versus portrait: 9x13 tiles on plane A (rows 10-22), stored row
  by row in BIODAT.BIN $D4B8 and GAME.DAT $2A390 (the copy that's loaded);
  palette line 2 = GAME.CO $E188 (copy at $55E2); colour 15 = 2-px gold frame.
- **done** Select-screen icon: 4x6 tiles row by row at GAME.DAT $1FAC8,
  palette line 2 shared by all icons (mapped to nearest colours).
- **seen** EC has no "finish him" window by default: the deciding blow
  knocks the loser down ($1C) and he stays down ($7FFF).
- **seen** Hit spark spawn in the fighter hit path: `move.w #$24,d0;
  move.w $1444(a6),d1; move.w $1446(a6),d2; jsr $6954` (returns a0 = object;
  $1444/$1446 = impact point). Blade's spawn of an object with its own code:
  `lea desc,a1; move.w #id,d0; jsr $6BB4` then a0's task resume PC is set.

## Dazed sway, Scorpion-only file, player-2 art limit (2026-11-08)

### MK's FINISH HIM daze

The first daze capture was wrong. tools/mkdizzy.py kept Sub-Zero attacking, so raw poses 0-4 are Scorpion standing and getting jabbed, not dazed.

- With Sub-Zero waiting from FINISH HIM on (QUIET = 1502), the real daze is raw poses 5-11.
- It is a 7-pose sway, held 10/8/10/10/10/10/12 frames: a ~70-frame loop.
- It plays ~3 times, then he falls on his own (12-15) and lies flat (16).
- extracted/mk_moves/dizzy holds those 7 poses, all on one anchor. A per-pose head anchor cancels the sway and slides the feet instead.
- scorpion_full exempts 'dizzy' from the stance filter.
- mkinputs r_drag (every other frame) replays the loop from DAZE_SEQ (35 entries).
- Frames used: 41:25, 41:26, 41:47, 41:48, 41:49, 41:4a, 41:4c. The game never shows those slots in sheetcheck's play.

### Scorpion-only file

BST.PL was a copy of BLA.PL, including Blade's sheets $44/$45: his gauntlet projectile and its blast (BLA.CO $31F6/$3914).

- scorpion_full.strip_sheets drops those 4 chunks (9560 bytes). They are the file's last chunks, so no offset moves.
- Blade registers the same sheets from his own file. Checked: his blast draws correctly vs Scorpion.
- The freed room bought the 7-pose daze and the full walk (below).

### The walk

- EC has one walk cycle, 40:16-40:1B (6 steps x 3 calls = 36 frames).
  - Walking forward (state 8) plays it in order.
  - Walking back (state 4) plays it reversed.
- MK is the same: its back walk is its forward walk reversed. That is 9 poses over 36 frames (3 4 4 5 3 4 5 3 5).
- Before this fix, MK's back-walk poses (3 of them) sat on 40:16-1B for both directions. The forward-walk art was on 40:64-6D, which the walk never shows, so his legs barely moved.
- Now:
  - MK's 9 poses are on 40:64-40:6C.
  - mkinputs r_drag drives them: WALK_SEQ forward, WALK_SEQ_BACK reversed.
  - It resyncs whenever EC's own step frame shows. That frame's art is the pose due then (WALK_EC_POSES, via scorpion_map 'frame=pose'), so no frame is off.
  - The separate walk_back art is gone.
- The rest of the file beyond Scorpion's art (~35 KB) is the frame records: hitboxes and piece lists, one per Blade frame slot. Scorpion overwrites the ones he uses; unused slots keep Blade's. Repacking them is the next source of room.

### Player-2 art limit

- Player 2's .PL loads at PRG-RAM $51800. MAX_PL is 188416: ECX.PL's 92-sector footprint. BST.PL is now 187856.
- tools/p2check.py verifies it with Scorpion as player 2:
  - the file is intact in RAM once the fight starts;
  - nothing touches it or the RAM above it in 1200 frames of fighting.
- The game itself writes each art chunk's sheet number into its header after loading (6 words; Blade's own file too). The check allows those.
- The hard ceiling is PRG-RAM's end: 190464 bytes.
- tools/sheetcheck.py now also has Shadow attack him, and writes every frame he showed to extracted/ec_probe/scorpion_seen.json.

### Fatality start, duplicate art, jump attacks (2026-11-08, later)

#### Fatality start
- The fatality parks Scorpion in state 4 (EC's walk-back number). The walk driver now only acts while a walk frame shows.
- EC's animation script kept running after parking.
  - $AA = script start; $AE = the current step's *frame word*. A step's flags word sits 4 bytes before it.
  - The fatality now points $AE at a held step (mkinputs f_hold).
- Holding Block (Z) fed "back" while the opponent was dazed, because EC's daze is a move and $F6 bit 5 is clear. A dazed opponent now never triggers blocking.

#### Duplicate art
- 24 of 113 chosen poses were the same MK image under another action: shared stance frames, LK = HK jump kicks, the hit reactions.
- scorpion_full now stores each image once. The art went from ~141 KB to 118 KB, within Blade's original region, and BST.PL is 166756 bytes.
- 19 frames still have pieces dropped because Blade's per-frame layout record is too small (build report "frames trimmed"). Repacking the records would fix that.

#### Jump attacks
- tools/mkmoves.py's jump_* captures were all forward jumps: MK's flying kick and flying punch.
- The new jumpup_* captures are MK's straight-up attacks. Kicks are near-upright (LK = HK), and so are punches (LP = HP).
- EC uses the same frames up or forward (A 41:06; X 41:07/08; Y 42:08-0B; B 40:03/43:03). The only exception: C straight up plays 41:15, 40:24, 40:23, 40:25.
- $5E is horizontal speed: 0 going straight up, ±6/7 otherwise.
- PLYR.CO's script interpreter writes step frames with move.w (a0),$1A(a5) at ~10 sites (e.g. $4178). Hooking those would allow direction-aware art without flashes.

## Teleport punch, straight-up jump attacks, sweep (2026-11-08, night)

### EC script internals
- Script step, counted from the frame word ($AE points at it): frame, ticks (2 frames each), $E6 dx, $E8 dy, $F6 flags, $102.
  - $F6 bit 10: apply velocity $C6/$CA.
  - $F6 bit 11: mirror relative to $100.
- Opcodes < $100 sit in the frame slot (e.g. $D8).
- Steps load at PLYR $18174 and five other sites (mkinputs FRAME_SITES).
  - The $E2 pointer at $186D8 is the attack script a jump attack runs alongside the main one.
- The player advances $AE *before* reading a step, so a redirect must point one step early.
- EC ends a move after $C4 steps; $C2 counts them (PLYR $182CE). Blade's dash: 7.
- Move task: TCB = (($88(fighter))); +$26 = the current step's ticks left.

### Camera and screen
- The camera's left edge is -$4F90(a6) = $2B070.
- $AB6 bit 1 stops the camera following (PLYR $14D88).
- Fighters are clamped to [cam + $46, cam + 320 - $46] ($46 = 25).
- Touching that clamp sets $11C and ends a velocity move.

### Teleport (move $35, down, back + HP)
mkinputs r_teleport takes Blade's dash over:
1. Points $AE at its own TELE_STEPS: crouch, spring, tuck, stretch, fly out, punch in, land (teleport_mk poses, cleaned).
2. Sets $C4 = 7, zeroes the speed, and freezes the camera.
3. Moves him out 16 px a call, until EC's clamp stops him at the edge. The fly pose is drawn behind him, so he leaves the screen.
4. Puts him at cam + 294 (or 26), facing back ($100/$20 bit 11). The incoming poses are stored mirrored.
5. The punch step keeps Blade's dash frame 41:62 (its attack box, $102 = $0C1C). If she's by that edge, the contact is the hit.

The MK capture shows a frozen copy of his stance at the take-off spot for the whole teleport (idle pose 3, exact). It isn't reproduced. Ask the user.

### Straight-up jump attacks
- The frame hook swaps JUMP_UP frames for the jumpup_* poses while $5E = 0.

### Sweep
- r_swept: a fighter knocked down ($1C) by Scorpion's down + C gets vy -4 and a quarter of vx: a low hop, falling in place.

## Memory: how MK fits its art, and a better encoder (2026-11-08, research run)

### MK CD
- MK CD never reads the data track during a fight.
- Each fighter's whole art (e.g. SCORPION.SCH 194,944 + .OBJ 62,778) stays resident.
  - Scorpion: Word RAM bank 0 (1M mode, +$3000) plus PRG $383C0.
  - Sub-Zero: bank 1.
- Its format is a fixed 2:1 code over 16x16 cells, about 1.27 KB per frame.
- MK's Scorpion has 201 frames; captures overcount, because of spear-rope and teleport variants.

### EC fight memory
| Range | Contents |
|---|---|
| PRG $51800-$7FFFF | P2 .PL (190,464 bytes max) |
| Word $81800-$B17FF | P1 .PL (196,608) |
| Word $B1800-$B97FB | VRAM transfer heap |

- Poke-tested free:
  - PRG $7A364 up;
  - Word $80000-$817FF;
  - Word $B9960-$BD8FF;
  - Word $BDAE8-$BFACF.
- P2 art banks still work when moved into Word RAM; bank offsets are 32-bit (SUB $117B8).
- Overkill/Vendetta load .OC/.VC files over $51800 at the finisher.

### Encoder
- tools/ecpl2.py: a DP parse over all of EC's unpacker opcodes.
- About 25% smaller than ecpl.encode_bank; yields in the same places.
- scorpion_full decodes every frame with EC's own unpacker (tools/ecunpack.py) at build time.
- Scorpion's art went 122 KB → 97 KB. The caps were then raised: 117 poses in 115 KB, inside Blade's original region.
- The file is now replaced, not patched in place: it had kept a 9.5 KB stale tail.

### Still open
- Repacking the frame records: about +13 KB, and it fixes the 19 trimmed frames.
- Shared sub-frames (opcodes $F4-$F7).
- Word RAM overflow for P2 banks.
- tools/ecsprite.py stops at the first yield. Fix: set d6 = $40, or write the frame to $1A(a5).

## More MK fighters: Raiden, Johnny Cage, Sub-Zero (2026-11-08, night)

patches.Spec / use() / for_spec run the Scorpion patches for any MK fighter: slot, full, palette, name, roster, portrait, icon. scorpion_full.CFG and scorpion_map.assignments(aliases, exact) take the fighter's capture folder and aliases.

| Fighter | Slot | Sheets | Tile sources |
|---|---|---|---|
| Raiden | Chin Wo (CHW, id 19, CHW.AI) | $72- (Chin Wo's own) | Chin Wo's |
| Johnny Cage | Zuni (MON, id 18, MONK.AI) | $D9- | $236-$240 |
| Sub-Zero | Yappy (DOG, id 20, DOG.AI) | $DD- | $242-$24C |

- Neither Zuni nor Yappy is special-cased by any EC module.
- Their own sheet and source numbers (2 / 5) are too few for Blade's 6, hence the numbers above:
  - Sheets: no EC file registers $D9-$FF.
  - Sources: the table at RAM $D448 has 300 entries of 8 bytes (to $DDA8), and ids up to $234 belong to EC files.

### What these first versions are
- Blade's code and moves with the fighter's MK poses.
- Blade's projectile = Raiden's lightning, Johnny's green bolt, Sub-Zero's ice blast.
- Blade's dash = Raiden's torpedo, Johnny's shadow kick.
- No MK specials, voice or fatality yet.
- Blade's effect sheets $44/$45 are kept: they share Blade's numbers, same art.

### Select grid
- Raiden is the first of row 2. Sub-Zero and Johnny are in a new row 3, which has no gold frames yet.
- Right presses: 7 Raiden, 8 Blade, 14 Scorpion, 15 Sub-Zero, 16 Johnny.

### Tools
- tools/mkduelstate.py: MK 2-player states (mk_johnny_2p, mk_subzero_2p).
- tools/mkportrait.py --fighter.
- tools/showcase.py --fighter (shots/*_moves.mp4).

### Known issues
- **Circus stage colours.** The circus stage (Zuni's home, so Johnny's duels) animates entries 3, 4, 7, 8, 9 of palette line 3. Zuni's sprite never uses them; Johnny's does, so his colours cycle there.
- **Missing captures.**
  - Sub-Zero's slide didn't trigger (input).
  - Johnny's nut punch (Block + LP close) didn't trigger.
  - No daze or straight-up jump captures for Raiden.
- Johnny's split punch: MK CD has it as Down + HK (Sega Retro). It's his crouch_z capture.
  - Spec.extra pins EC's down + Z frames 42:05/06/07 to poses 5 (split), 7 (punch) and 8 (back up).
  - It hits anyone. MK's nut reaction on male EC fighters (bend over + nuts sound) needs fighter code in his module; not done yet.

## The teleport's double (MK): not yet (2026-11-09)

- MK leaves a frozen copy of Scorpion's stance (idle pose 3) where he took off, from the leap until he lands.
- Tried an effect object showing frame 41:3A (pinned to idle pose 3): mkinputs ghost_new and the 'ghost' task, GHOST_ON.
- It draws as stripes. The spawn type is an id in the descriptor table at $11E8C (the spark is $24; fighters 2-24), and neither the spark's nor his own (23) unpacks a frame for the object.
- EC unpacks a fighter's frame each video frame into that fighter's VRAM area (unpacker called at SUB $FC3A, buffer $2F2D4). A second figure needs a second unpack area.
- Baking the double into his frames only works for a fixed take-off to landing distance.

## Johnny's colours on the circus, the size line-up (2026-11-09)

### Circus colours
- The circus (Zuni's home stage, so Johnny's duels) animates entries 3, 4, 7, 8, 9 of the P1 fighter's palette line. The animation is data-driven; I didn't find it in CIR.BGI's code.
- Fix: Spec.colour_map / palette_set move Johnny off those entries. His MK palette has black at 5, 6 and 12, so 3 → 5 and 4 → 6. Entry 9 is nearly entry 3's colour; 8 and 7 go to their nearest (13 grey, 12 black).

### Size line-up (shots/lineup.png, standing heights in px)
| Fighters | Height |
|---|---|
| EC | 86-112, around 99 |
| Scorpion, Sub-Zero | 107 |
| Johnny | 106 |
| Raiden | 110 (with the hat) |
| Blade | 112 |
| Shadow | 92 |

## MK animations for Scorpion's basic attacks (2026-11-09)

### How EC starts a move
- PLYR $180D6: $AA = ($A6(fighter))[move id $BE * 4], a move table in RAM.
- That points at a script header (20 bytes): word, word → $C4 (step advances allowed), long vx, long vy, long, word $198, word $19A.
- Then come the 12-byte steps. Blade's scripts end by the $C4 count; the word after the last step is the next script's header.
- Blade's move ids: 1 X jab, 2 Y, 3 Z overhead, 4 A knee, 5 B front kick, 6 C spin kick. The table (module offsets) is $409C, $40D4, $4118, $42C8, $4284, $4228.

### What tools/mkscripts.py builds
For moves 1, 2, 4, 5, 6, each script is:
- MK's poses in MK's order and timing (capture runs, stance trimmed), on free frame slots (FREE: sheet $40, frames no Blade script or code uses);
- Blade's last hit step (frame/hitbox, lunge, flags, $102 hit data) on MK's strike pose (within 8 px of full reach, held longest; at least 2 ticks).

Wiring:
- patches.use(SCORPION) adds the slots to the art map.
- mkinputs r_drag points his move table at the scripts every call.

### Result
| Attack | Steps | Damage at 55 px |
|---|---|---|
| X | 5 | 3 |
| Y | 5 | 7 |
| A | 6 | 5 |
| B | 9 | 7 |
| C | 8 | 9 |

- Y's reach is now shorter than at 70 px.
- Only 4 new poses of art: the rest were already in his file.

### Still Blade's frames
Crouch attacks, close variants and the Z overhead.

### Close range, and blank slots (2026-11-09)
- Up close EC plays other moves for the same buttons: X $20, Y $21, A $23, B $24, C $25 (headers $47C4, $485C, $492C, $4964, $499C). mkscripts gives them the same MK animations with their own hit steps.
  - The slots are shared with the far versions.
  - A strike frame claimed by another action (close A and close B both strike on 40:15) falls back to the action's far strike frame.
- Some unused Blade frames have 6-byte layout records (40:04, 40:05, 40:21, 40:28...), so a pose there draws blank. mkscripts.free_slots needs at least 96 bytes and an unshared record.

### Crouch attacks (2026-11-09)
- EC's crouching moves: down+X $0E, down+Y $0F, down+A $11, down+B $12, down+C $13. Down+Z has none.
- MK CD's crouching punches (A, X) are both the uppercut, and its crouching kicks (C, Z) are both the same low kick. The sweep capture is MK's back + low kick.
- mkscripts 'crouch' trim drops the capture's crouch-down and stand-up poses (the 'crouch' capture's poses).
- 'height' strikes on the highest pose.
- The uppercut keeps strike frame 42:03 (UPPERCUT_FRAMES launch) and the sweep keeps 43:0D (r_swept).
- 129 poses; BST.PL 161,832 bytes.

### Sharing the MK move code with Raiden, Johnny and Sub-Zero
- The extension block (mkinputs) is Scorpion's: it lives in his .CO, and its routines check SCORPION_ID and use his frame numbering.
- The PLYR stubs' `find` returns the first module carrying MAGIC. With two MK fighters in a fight, only one module's code would run.
- Plan: build the block per fighter (his id, sheet shift, scripts from his captures). The stubs call every loaded block.
- Fight-wide routines (hit blood, FINISH HIM, the fatality) must run once, so mark them per block.

### How a fighter's move table is built (2026-11-09): the way to give Raiden, Johnny and Sub-Zero MK animations
- PLYR $190CE/$190FC sets $A6 = a6+$1742 (P1) or a6+$1646 (P2), then calls $1A278 with a0 = $11E(fighter).
- $1A278 walks a chain of move scripts starting 64 bytes past a0. In BLA.CO that's $3FA0. When the fighter's $7B bit 0 is set and both players are the same fighter, it starts 32 bytes later.
- Each script: header word0 = move id × 4 (its table slot), word1 = step count; then 20-byte header + 12 × (steps+1). The walk stops at a negative word.
- Blade's chain: 53 scripts, ending at $51A4 with $FF00, which is the end of BLA.CO ($51A6).
- So MK scripts can simply be appended to any fighter's .CO before the terminator. A later script with the same id overwrites the table slot. No shared code needed.
  - For Scorpion, his extension block starts at $5200, after the terminator.
- Next: append each MK fighter's mkscripts output (his captures, his sheet numbering) to his .CO, plus the frame-slot art map (Spec.extra).

### MK attack animations for Raiden, Johnny Cage, Sub-Zero (2026-11-09)
- patches.mk_attack_scripts (each '<fighter>-scripts' patch, before '-roster') appends mkscripts.build(BLA.CO, the fighter's captures) to the fighter's .CO move chain, at $51A4 before the $FF00 terminator. renumber_sheets then renumbers their frame words.
- use() adds the frame-slot art for every fighter.
- mkscripts.FREE now also takes sheets $41-$43. A move whose capture shows no attack keeps Blade's script.
- Probe at 50 px: every standing and crouching attack plays 4-10 frames and lands, except down + X, which is short-ranged.
- Sub-Zero's state (mk_subzero_2p) ignored the pad for its first frames: his btn/crouch captures were just his stance. mkmoves LEAD_IN = 30 frames of no input first; recaptured. He now has 91 poses (from 55).

### Intro videos (for a random or back-to-back EC/MK intro)
- MK CD: MORTAL.ANM (21.4 MB), MK's own video format, played by MK's program at boot.
- EC CD: ZZ00.BIN (31.8 MB) is the largest file and looks like the intro. ZK.*/ZB.* look like the Cinekills (finisher videos).
- Options:
  - (a) Put MORTAL.ANM and MK's player program on our disc and boot into the player sometimes, patched to return to EC's boot afterwards.
  - (b) Decode MORTAL.ANM and re-encode it in EC's format.
- Both need the formats/players reverse-engineered. (a) is likely less work.

### The spear head is clipped off (found 2026-11-09, to fix next)
- Scorpion's spear has no projectile object. The pull comes from the throw frames' stretched hit box (scorpion_full.spear_reach).
- So the only rope and spear head you see is what fits in his own pose.
- MK's flying-spear poses (spear capture 7-15) run from -106 px (the wavy rope behind him) to +79..+144 px (the black spear head out front).
- pose_pieces clips symmetrically around the anchor (dx 120 → 48) until the pose fits TILE_CAP = 112 tiles. Those poses end up at dx 48-64, which cuts off the spear head and most of the rope.
- Fix: for 'spear' clip asymmetrically. Keep the forward side (rope + head toward the opponent, up to +150) and cut the wavy slack behind him first. A thin rope costs few tiles per 8 px.
- Check the in-game throw against MK's (shots/ + tools/mkvideo.py).

## The Pit (MK) - reference (2026-11-09)
- MK CD's 2-player mode moves to the next stage each match: Courtyard → Warrior Shrine → the statue stage → ... → the Pit.
- states/mk_pit_raw.state: Kano vs Kano at the start of a fight on the Pit (moon, clouds, stone bridge). It was reached by replaying matches from mk_2p (the script is in this session's history; it needs a proper tool).
- shots/mk_pit.mp4: a Pit round with MK's music (player 2 wins).
- The FINISH HIM uppercut there knocked the loser down onto the bridge, not off it, in the first tests. Solved below ("MK's Pit fatality, found").
- User's plan: the Pit's stage finisher for MK fighters (uppercut off the bridge onto the spikes), EC victims too (fly up, fall onto the spikes). The stage itself goes in as an EC stage (CIR-style .BG/.BGI).

## Hit check: tools/hitmatrix.py (2026-11-09)
- Every standing and crouching attack, at 45 and 70 px, against a standing and a crouching victim.
- MK fighters attacking EC fighters are compared with Blade attacking the same victim; EC fighters attacking MK fighters are compared with the same attack on Blade.
- **Found: MK hit boxes were scaled down.** fit_boxes shrank Blade's boxes to the MK outline, so EC fighters' attacks missed crouching Scorpion and Sub-Zero, and some MK far attacks fell short. Box scaling is now floored at Blade's (1.0-1.3).
- **Found: no forward movement in the wind-up.** mkscripts' wind-up steps dropped Blade's forward step ($E6) and slide (flag $0400). Restored.
- Before both fixes: 17 left (X@70 vs Ramses, X@45 vs crouching Jetta...).

## Pit fatality on MK CD: not triggered yet
- MK health: PRG-RAM $7D6C4 (P1, full 119).
- At FINISH HIM (P1 at 0), P2's down + X uppercut at waits 0/20/60 and gaps 30/45/60 hit, but the loser landed on the bridge, never below it (sprite y ≤ 213).
- Sources say a plain uppercut does it on Sega CD. Not yet known: blood code? 1-player only? a specific button?

## Throws (2026-11-09)
- **MK CD's throw:** walk into the opponent and press toward + Z.
  - Low punch up close is just a jab; this was found by testing every button up close and watching for the victim to end up behind.
  - The old 'throw' capture was a walk and a jab; recaptured for all four fighters.
  - Scorpion and Sub-Zero grab and roll back onto their shoulders, tossing the victim overhead (the "roll throw"). Raiden grabs and slams; Johnny throws over his shoulder.
- **EC's throw:** close + Y, move $0D (back + Y throws behind).
  - It isn't a script: Blade's module code sets frames 42:10, 42:0F, 42:0E (victim lifted), 42:0D (victim overhead), then 42:0F, 42:10, 42:11.
  - No other move shows 42:0D-42:10 (scorpion_seen), so mkscripts.throw_art pins them to the MK throw's grab, pull, pre-peak and peak (longest-held) poses for each fighter.
  - Scorpion: grab, pull, rolled back, feet up as she flies over.

## Hit boxes: only the outer edges grow
- fit_boxes scaled both edges of each box, so a taller strike box lost its bottom: low punches went over crouching victims.
- Now only the far edge and the top scale (≥ Blade's); the inner edge and the bottom stay Blade's.

## Pit: player 2's input after FINISH HIM
- In the Pit test, every button after FINISH HIM left player 1 in exactly the same place, so player 2's uppercut never happened.
- Next: try player 1 as the attacker, or check whether the 2nd pad is 3-button in that state.
- Pit, more:
  - MK health: P1 $7D6C4, P2 $7D7CA (PRG-RAM, full 119).
  - Inputs after FINISH HIM are ignored for about the first 60 frames. After that, P1's down + X uppercut launches P2 (to sprite y 21), but P2 lands back on the bridge.
  - Tested in 2-player mode on the US disc (prefinish states in scratch). The Pit fatality did not trigger.
  - Not yet tried: 1-player vs CPU, and other spacings.
  - Our Pit finisher in EC will be our own: launch, fall to the spikes. MK's spike art (bodies, heads) still needs finding on the disc (BACKGD*.BIN?).

## The Pit's art (2026-11-09)
- tools/mkstage.py dumps an MK stage's two background layers and palettes from a fight state into extracted/mk_stages/<name>/.
- tools/vdp.py gained plane_size() and plane().
- **The Pit** (128x32-cell planes):
  - plane B: night sky with two rows of clouds (they scroll);
  - plane A: moon, bridge, dragon statues and pillars, with the spike tips just visible at the very bottom.
  - The pit's depths (spikes, bodies) are only on screen during the fatality and aren't captured yet.
- **Next:** EC's stage format (.BG/.BGI; e.g. CIR.BGI holds code plus background-object records). Make a "PIT" stage from these layers.

### Throw direction, close jab, voices (2026-11-09)
- **EC's throw (BLA.CO $19E6):** a choreographed list ($15A → $1CB10) played by PLYR $1911C, with a per-victim position table ($9A, from $1CAAC indexed by the victim's id - 2). Holding back sends the victim behind.
- **MK's throw sends the victim behind from toward:** mkinputs swaps toward → back in Scorpion's pad word while Y is held (THROW_BIT 9). Measured: toward + Y lands Shadow 270 px behind him, for 16 damage.
- **Pad word bits:** up 1, down 2, left 4, right 8, B $10, C $20, A $40, Start $80, Z $100 (stripped: MK block), Y $200, X $400.
- **Close jab:** mkscripts now prefers a strike step with F6 bit 15 (hits crouching victims). Blade's close X is a double punch whose first hit has it. The quick hitmatrix now gives 0 misses.
- **MK voice samples:** FIGHT.SVX (SFX2), FATALITY.SVX and <NAME>wins.SVX (SFX4A-G), FLAWVICT.SVX, nuts2.svx (SFX1).
  - At 5200 Hz FIGHT is 2983 bytes, and fits Scorpion's bank (17702 room, about 13.3 KB used).
  - FATALITY (5948) and SCORwins (8845) don't fit: that needs a bigger bank or a lower rate.

## Stages: EC's format and the Pit as a stage (2026-11-09)
The full format is in tools/ecstage.py's docstring (from a research run, verified against live VRAM on 3 stages: ~100% of cells).

### Format
- **.BG** = chunks:
  - 0: raw tiles;
  - 4: sprite sheet;
  - 8: the background (layer ids, records).
- **A layer** = a grid of 4x4-cell blocks. Layer objects ($E062 + inline plane/x/y/w/h) put a layer into a band of plane A or B and stream columns or rows.
- **.BGI** = 68000 code at $34000 with no fixed entry. The stage's init in SUB.BIN (mode table $6862, modes $11-$22) loads both files and sets up everything: the camera ($E00E), objects, palette (lines 0-1 from a table in SUB.BIN!), descriptors in the BGI, and the Overkill check pointer $14FA.
- **Which stage a duel uses:** GAME.CO $C28, a word per fighter idx. duelstate.py --stage HH forces it in RAM.

### The Pit
- It replaces Blast's stage (mode $13, BST.BG/BGI). Blast's slot is Scorpion's, so it is his home stage, and no EC fighter loses one.
- **patches.pit_stage** patches Blast's init:
  - camera right limit 500 (as MK's), start centred;
  - plane A's main layer down to y $F0 (Blast's narrow floor band at $D8 was a parallax layer only 512 px wide, which showed black);
  - the plane B bottom band's per-line scroll routine ($E332) off.
  - It then builds the BG/BGI with ecstage.build against that init.
- **The moon** is in the back layer under the clouds, because MK's priority layering would cover EC's fighters. It sits at the top as in MK.
- **The backdrop** (black in EC) is filled with MK's night blue.
- shots/scorpion_pit.mp4: a fight on it.
- **Not yet:** the Pit fatality (uppercut off the bridge, spikes); the spike-pit art isn't captured.

## Every MK fighter has a code block (2026-11-09)
- **Layout:** a block at EXT_OFF ($5200) in each MK module: MAGIC, fighter id, full flag, then an entry table (the stubs call it) and a raw table.
- **Dispatch (mkinputs._block):**
  - per-fighter hooks (drag, jumpup) run in the block of the fighter's own slot, plus the full block (Scorpion's) wherever it is;
  - fight-wide hooks run in the full block;
  - a mirror match of full blocks runs only the first.
- **Generic block (mkinputs.generic_block):** MK attack scripts (in his move table, like Scorpion's), toward + Y throws behind, MK's walk loop (walk_plan: his own capture's 9-pose loop; EC's walk frames pinned).
- **Walk direction:** EC's walk states are left (4) and right (8), so toward = bit 3 of $BF xor $20's high byte (emit_wdir). Before this, the facing-left player walked the cycle backwards.
- **Scorpion's walk count** is per player (+84/+88), for the mirror match. His block is now 0x67F6 / 0x6800 (10 bytes free!).
- **Throw victim tables:** every fighter module has one (23 found and validated). The MK victims' entries now hold the attacker's Blade entry shifted to their sheets (patches.mk_throw_victims). Before this, Raiden (Chin Wo's entry) couldn't be thrown, and the others showed wrong poses.

### Pit sky, matched to MK (2026-11-09)
- **MK's Pit, measured** (hscroll per line over 4 s, camera still): the moon's lines (plane A) don't move; the clouds (plane B) drift in three bands, at screen lines 32-71, 72-111 and 112-127, at 0.69, 0.51 and 0.43 px a frame; the rest is still.
- **Ours:**
  - Blast's plane B band objects are re-laid as PIT_BANDS. Band y = screen line + 8, because this stage's camera starts 8 down. x mode $14 = drift by speed/1024 px a frame.
  - The back layer is one 512 px period of MK's (repeating) sky. That fits the 64-cell plane, so the bands can drift without streaming. We feed 544 px because build() crops by PIT_OFFSET.
  - EC's front layer scrolls as one, so the moon goes in it, placed where MK shows it at the fight's start. It moves with the camera, and sits in front of the clouds (MK draws the clouds over it by priority, which in EC would also cover the fighters).
- **Fighters' feet:** screen y 209 vs MK's 211, so they stand on the bridge as in MK.
- **Gotcha:** states made from menu.state keep the SUB.BIN that was in memory when menu.state was saved. After a build, run the tests (01_boot remakes menu.state) before duelstate.py, or SUB.BIN patches won't show.
- **Pit music:** EC track 17 (Blast's stage only, matched by audio correlation) is swapped for MK track 4 (build.add_stage_music, STAGE_MUSIC). MK plays track 4 on the Pit and on the Courtyard.
- **Pit floor:** $1496 = $CE (patched in the init, `move.w #$D8,$1496(a6)`), so the fighters stand up on the walkway like MK's. Measured side by side (shots/pit_mk_vs_ours.mp4).
- **No shadows on the Pit:** SUB.BIN spawns shadow object $1D per fighter at $B44A / $B4E2, skipped when $AB2 = $18 (`cmpi.w #$18,$AB2(a6)` at $B442 / $B4DA). That compare is now a jsr to a SUB.BIN tail routine that also matches $13.
- **Open: clouds over the moon.** MK draws the clouds over the moon with priority. In EC, high-priority plane B cells would also cover the fighters (they are low-priority sprites). The top cloud band (lines 32-71) only meets a fighter's head at the top of a jump, so it could be high priority there.

### The Pit's finisher (2026-11-09)
- The Pit's .BGI (built by ecstage, so ours) keeps its task running after the palette settle: ecstage.PIT_FALL, build(pit_fall=True).
- **Each frame, per fighter:**
  - knocked out (hp 0), down ($1C), in the deciding round (the other fighter's wins: $31D26 P1 / $31D28 P2 ≥ 1), and launched high (y < floor - 48) → marked;
  - coming down (vy $62 > 0) past floor - 24 → $1496 = $1F0, so he falls out of the screen;
  - after 90 frames, or below y $130 → floor back. He lands there, below the screen, and the round ends as usual (measured: "SCORPION WINS CONTEST", round over).
- $2A bit 6 is set on fighters all the time: not a hide flag.
- Works for any winner. With MK fighters it is their FINISH HIM uppercut (shots/scorpion_pit_fatality.mp4, tools/pitvideo.py).
- **Not yet:**
  - the pit's spikes and bodies (MK's pit-bottom art isn't captured);
  - a scream: there is no MK fall scream sample by name, MK's fatality scream is SFX3E #2, and the stage has no sound bank of its own;
  - MK CD's own Pit fatality never triggered in 2-player tests.

## MK's Pit fatality, found (2026-11-09)
- **Trigger** (victim reaction code at $178D4): stage $8E8A = 3 (the Pit), $8F6E = 0, the victim's health 0 after the hit, the winner's round count ($7BA82 / $7BA84) = 2. That is a match-winning uppercut at FINISH HIM.
  - It works in 2-player mode. The earlier tests failed because Kano never crouched: the 1-frame walk holds left him throwing a standing lunge punch.
  - What works: from FINISH HIM wait 150 frames, then down 8, down+X 4, down 10.
- **Art:** BACKGD4.BIN is the Pit. Sections 0-2 are Rob Northen ProPack method 1 (`RNC\x01`):
  - 0: 818 tiles;
  - 1: the plane-A map, 110x86 cells (880x688 px), every cell palette line 3, $0800 = h-flip;
  - 2: the clouds;
  - 5: palettes (lines 2 and 3).
  - The fight shows map rows 0-20 (the bridge). Rows 21-85 are the pillars with spikes, a body impaled on the middle pillar, the brick wall, and the spike floor with heads.
  - PAC.PRG holds a second packed copy of the map (at $242F8 in PRG-RAM), which the fatality code ($1797C) streams one row per 8 px of scroll.
- **The sequence** (frames from the uppercut):
  - 44-76: the victim flies off the top (the camera tilts up ~12 px);
  - 80-100: he comes back down past the bridge;
  - 82/87/92: the sky and clouds fade to black;
  - 92-169: the camera scrolls straight down 8 px a frame to the bottom (VSRAM 544). The winner leaves the top; the victim falls slower than the camera;
  - 169-189: he drops onto the spike floor; blood until ~290; "KANO WINS" ~420.
  - It is a scroll, not a cut.
- **Tool:** tools/mkpitbottom.py decodes the art from the disc (extracted/mk_stages/pit_bottom/: pit_full.png 880x688, pit_bottom.png = the final screen, palettes in pit_bottom.json). `--video` records shots/mk_pit_fatality.mp4.
- **Possibly the Reptile fight:** stage loader entry 6 ($F1A0) puts map rows 55-86 on plane A and clears plane B (the pit bottom as a stage). It is selected via $1508A when $21A44's check passes: Pit, counter $8E9C = $12, $7BAC0/$7BAC2 = 2, $7BA20 set. Untested.

## Strike boxes and MK anchors (2026-11-09)
- **Found:** the Pit video's jabs hit Shadow with Scorpion's fist well short. Blade's strike box (box 0) on his jab frame is 44-94 px (his arm blade, pose front 98). Scorpion's MK pose was measured at 44: the whole box sat past the fist.
- **Found, worse:** mkmoves.anchor centres each pose on its top 12 rows (the head).
  - That cancels MK's own lean: the jab's head goes 26 px forward, so the fist fell 26 px short of MK's.
  - In high kicks, crouch kicks and roundhouses the foot is above the head, so the anchor sat on the foot and the body was drawn ~55 px back on the strike pose.
- **Fix (scorpion_full.steady_anchors):**
  - IN_PLACE actions (standing and crouching attacks, block, sweep, straight-up jumps) use the stance pose's x for every pose. The planted foot never moves in those captures, so this is MK's own placement.
  - Elsewhere a lone outlier pose (25 px off two agreeing neighbours) takes their x.
- **Fix (fit_boxes):** box 0 (the strike box) is moved back, same size, to end at the MK pose's front (STRIKE_SLACK 0: the front is already rounded up to the 8 px tile).
- **Reach now** (largest gap that still hits a standing Shadow, px): Blade X 130 / Y 100 / C 142; Scorpion 100 / 100 / 112; Raiden 106 / 106 / 100; Johnny 112 / 106 / 94; Sub-Zero 100 / 100 / 106. hitmatrix --quick: 0 misses.
- Scorpion's art is 8 banks now (BLA.PL 168776 bytes).
- **Gotcha again:** a build that changes file sizes moves files on the disc, and menu.state then loads garbage ("player 1 never responded"). Run the tests first.

## The Pit's cut to the spikes (2026-11-09)
- **EC can't scroll down the pit like MK.** No EC stage layer is taller than 8 blocks (256 px = one plane), and camera y never goes past 88: there is no vertical streaming. MK scrolls 544 px down a 688 px map.
- **So it's a cut** (ecstage.pit_cut / pit_fall_code). Once the loser has fallen past the bridge and out of sight:
  1. fade out in 3 steps (each colour halved per step; the HUD colours, line 1 10-15, are kept);
  2. swap the front layer object to layer 2 and force a redraw;
  3. hold the camera at (248, 16) and turn the fighters' screen clamp off;
  4. put the winner 200 px off the left of the screen;
  5. drop the loser from above the screen onto the spike floor;
  6. fade in.
  The winner is kept off screen, with bits 1 and 2 re-set every frame, until the match moves on: the round's end clears them and EC walks him back for his win pose. The game then goes on to the final statistics as usual.
- **Layer 2** (patches.pit_bottom_layer) is Blast's floor strip. Its band object sits at plane rows $F0-$FF, below the screen. The layer's first 16 rows stay the bridge art for that band; below them are MK's map rows 456-687 (map x = world x + 32). Pit tiles: 754, within the largest EC stage's 775.
- **Layer objects:** a list at -$5A6E(a6), layer id at $58.
  - Changing the id and resetting $16-$20 to $E0D8's start values ($C000, $C000, $3FFF, $3FFF, $C000, $C000) redraws the whole plane with the new layer.
- **Fighter position:** six copies, x at $36/$3A/$4E/$56/$B2/$BA and y at +2 of each. PLYR rebuilds the rest from the others, so all six must be written.
- **$AB6(a6):** bit 1 holds the camera; bit 2 skips the fighters' screen clamp (PLYR $14E6C → $14F4C). The clamp keeps fighters at cam + 25 … cam + 295 ($46(a5) = 25).
- **Hiding a fighter, what didn't work:**
  - $82 bit 7 and $101 bit 3 don't hide one.
  - Fighter sprites are all high priority, so plane cells can't cover them.
  - A standing fighter snaps back to the floor line.
  - Frame word 0 shows a stray 2x2 sprite; $3B00 is empty only for some fighters.
- **Open:**
  - EC's knockdown bounces her twice on the spikes, where MK's victim stays down;
  - no blood or scream yet;
  - MK's own map art has a body on the spike floor, under where she lands.

## The Pit: the scroll down to the spikes, done (2026-11-09)
- **EC's layer streamer does rows too:**
  - $E924 streams them and wraps at the plane's 32 rows. It is turned on by layer-object flag $5F bit 2 (bit 1 = columns, 3 = hscroll, 4 = vscroll; $5E bit 0 = always the full height). No EC stage turns it on, because their layers are at most 256 px tall.
  - Row index = (camera y - object y + $2E) / 8. The object is drawn only while its band (+$A y, +$E height) overlaps the screen ($E3F6).
  - Layer columns don't wrap: past the layer's width the default block is drawn.
- **The camera:** the streamer ($E378) clamps camera x and y into the stage limits (-$4FA8 x min, -$4FA6 y min, -$4FA4 x max, -$4FA2 y max) every frame. Pinning min = max moves the camera anywhere, whatever PLYR's follow code wants.
- **Ours** (ecstage.pit_fall_code with a cut, patches.pit_tall_layer):
  - Layer 2 is the whole pit: 800 px tall, world y = map y + 88, only the 320 px strip the camera shows (x 248-567). 699 tiles in all.
  - Blast's floor-strip object, layer 2's own band, is moved to y $4000 in the init so it is never drawn; layer 1 now covers plane rows 0-255.
  - As the loser falls past the bridge:
    1. fade out (frames 1, 4, 7);
    2. frame 9: layer 1's object → layer 2 with rows streamed and the whole height, redrawn; camera on rails at x 248; floor line = the spikes (734); loser at screen y 150, vy 4; winner away;
    3. fade in (frames 10, 13, 16);
    4. camera y += 8 a frame to 544, with the loser's fall capped at 7 px a frame (he rises on screen, as in MK);
    5. hold: camera, winner away, no upward velocity.
- **Fighter state:** $C2/$C4 are the knockdown script's step count and limit. PLYR's knockdown ($17B60) always plays one bounce, a scripted move about 18 px up, after the first landing. Clearing $16C/$170 (the bounce's start velocities), $C6, $180, or setting $C2 = $C4 all fail to stop it. Still open.
- The bridge layer object starts the cut at camera y 0, so the black sky fills the top and the bridge sits at the bottom, like MK's.

### The Pit's fall, matched to MK's (2026-11-09, later)
- **As in MK** (shots/mk_pit_fatality.mp4, compared frame by frame):
  - only the sky goes dark;
  - the bridge stays lit, and the winner stays standing on it and scrolls off the top;
  - no cut;
  - blood sprays when the loser lands on the spikes.
- **Sky-only fade:** build(fade=...) finds the palette colours that only the back layer and the front layer's moon rows use. That 32-bit mask goes into the BGI's fade routine.
- **Camera x** holds while the bridge is on screen (camera y < 208), then drifts 16 px a frame to the strip (x 248), over the dark pillars. The loser is moved with the drift.
  - So the tall layer is full width down to map row 480 (bricks repeat: still 779 tiles), and only the strip below that.
- **The scroll starts** once the sky is dark and the loser has fallen back to the bridge's floor minus 40. During it he isn't allowed above screen y 110 (EC holds his fall below the camera's 8 px a frame).
- **No bounce (fixed):** PLYR's knockdown replays its script after the first landing. The first frame of the replay (in the air again, state $1C), he is put back on the floor (y copies), vy 0, $C2 = $C4, and the task's step ticks (+$26 of (($88))) = 1. The replay ends and he lies down ($7FFF).
- **Blood:** for 96 frames after the landing, 3 drops every 2nd frame (at most 6 alive), from 12 px above where he lies. They are plain effects ($6954, type $24) drawing sheet $1B frame 7 with sprite line 0. The stage palette's line 0 colours 12/13 are reserved as blood ($00A/$00E, build fixed_extra).
- **File-size limit:**
  - A 52,252-byte BST.BG hung on the stage's intro card. 46,650 and 40,956 load; the largest stock BG is 45,958. The limit is somewhere in between.
  - Blast's own stage-sprite tile chunks (slots 0-3: 368 tiles, 11.7 KB) are now cut to one blank tile each (build blank_tile_slots); the Pit doesn't show them.
- **VRAM:** stage tiles start at 708. EC places the HUD and effect sprites after them (Raven's stage: 775 tiles, HUD from 1550), so there is no fixed 775 cap.
- **Launch:** from the moment he is launched, the camera is held ($AB6 bit 1, re-set every frame: something clears it about 27 frames in) and his x is locked (fvars+16). The knockdown script's own steps ($E6, not vx $5E) carried him right into EC's screen clamp, the "bounce off the side". It is locked 16 px off the floor (PIT_LAUNCH; measured: x stays put from 3 frames after the hit). During the scroll it only moves with the camera's drift, so he keeps his place on the screen. (An earlier steer towards screen x 200 read as being pushed back left: removed.) What still shifts is EC's own knockdown art: the rising pose leans right of the fighter's anchor, the falling pose stretches left.

### MK CD's Pit fatality: its sounds (2026-11-09)
- Found by matching shots/mk_pit_fatality.mp4's audio against every 8SVX sample in MK's SFX*.BIN files (at 11 playback speeds) and against every CD audio track.
  - **At the uppercut:** SMACK1.SVX (with FEETLAND.SVX).
  - **During the fall:** **CD track 10**, an 11 s music piece (score 0.79; every other track 0.12 or less). It starts just after FINISH HIM, before the uppercut. No sample matched during the fall: no scream.
  - **After the landing**, ~frame 270: BLOOD.SVX (the blood spray).
- Our FINISH HIM plays MK track 13 (measured on Scorpion's fatality on the Courtyard). On the Pit, MK played track 10: by stage, or by chance? Not yet known.

### Clouds over the moon, as MK's (2026-11-09)
- **MK's planes on the Pit** (measured, states/mk_pit_raw.state):
  - plane B rows 0-10 (the top 88 px) are high priority, so its clouds there cross the moon;
  - plane A rows 0-10 (night blue and the moon) are low priority;
  - plane A rows 11-31 (bridge, statues) are high priority over plane B's lower clouds (low).
  - The per-cell map is saved as extracted/mk_stages/pit/plane_b_prio.npy.
- **No sprite crossed the moon** in 2 minutes of a 2-player fight. The flying silhouettes belong with the Reptile secret (the agent's $21A44 find).
- **Ours** (patches.pit_layers):
  - the front layer's top 88 rows are the night blue, the pillars' tops and the moon, opaque;
  - the back layer's top 88 rows are only the clouds, with priority (build layer_prio);
  - EC's fighter sprites are all high priority, so they stay in front.
- **At the cut**, the back layer's object is pointed at the pit layer and redrawn, all 32 rows ($5E bit 0), so no priority clouds wrap round over the pit while it scrolls.
- Pit: 807 tiles; BST.BG 41,980 bytes.

### tools/pitcheck.py
- Duels pairs on the Pit, sets up the deciding round, uppercuts, and checks the loser ends up lying on the spikes with the camera at the pit's floor.
- 2026-11-09: 9 of 9 pass (MK and EC winners and losers):
  - Scorpion over Shadow and Jetta;
  - Shadow over Scorpion and Larcen;
  - Raiden over Shadow;
  - Sub-Zero over Jetta and Scorpion;
  - Johnny over Trident;
  - Blade over Sub-Zero.
- **Cloud bands fixed:** MK's plane B is scrolled 16 down (VSRAM $10, measured with mk_pit_raw.state), so its drift bands are plane rows 48-87, 88-127, 128-143. Ours were set at MK's screen line + 8, which cut the clouds' bottoms off into slivers drifting at the next band's speed (the user saw it). PIT_BANDS now uses those plane rows; measured ours at camera y 13: screen 35-74, 75-114, 115-130.

### MK CD's CD-audio cues around FINISH HIM (2026-11-09)
Measured by matching the emulator's audio against the disc's tracks.
- **FINISH HIM itself** starts no CD track: the stage music plays on.
- **Track 10** (11 s, the yell) starts when the loser goes down for good:
  - at the Pit uppercut, 2.5 s after FINISH HIM in our run, for ~4 s while he falls;
  - after an unanswered FINISH HIM times out (Kano, Scorpion, Raiden, Johnny and Sub-Zero fights all gave 0.82-0.99);
  - after Scorpion's fatality, following track 13.
  - Track 9 correlates 0.75 with it: probably a variant, to check.
- **Track 13** (fatality music) starts ~2 s after the fatality input, not at FINISH HIM.
- **So:**
  - our FINISH HIM part (track 13 started at FINISH HIM) should move to the fatality;
  - the Pit fall should play track 10, which is the "male yell" the user hears;
  - FLAWVICT.SVX and <NAME>WINS.SVX are the announcer.

### MK CD's CD-audio cues, corrected (2026-11-09, with the user listening)
- **Track 9** (8 s) plays at every FINISH HIM: on the Pit 0.62-0.83 from FINISH HIM to the uppercut, and 0.74-0.78 in the Courtyard, Raiden, Johnny and Sub-Zero fights.
- **Track 10** (11 s) plays when the loser goes down for good: the Pit uppercut, the collapse after an unanswered FINISH HIM (~4 s after it), and after the fatality music. The user calls it the losing music; it is not the yell.
- **Track 13** is the fatality music, from the fatality input.
- **Our build is wrong here:** it starts track 13 at FINISH HIM. It should play 9 there, 13 at a fatality, and 10 on the loss.
- **The Pit's male yell** (the user hears it over track 10) is not a CD track and not an 8SVX sample.
  - With track 10 subtracted from shots/mk_pit_fatality.mp4, what is left is loud while he falls (3.2-5.0 s of the clip). That leftover is saved as shots/mk_pit_fall_without_track10.wav, for the user to confirm.
  - Searching it against every SFX*.BIN sample (9 speeds), the .BAD files, NEW_*.BIN, PAC/RJC.PRG and BONES.SCH as raw 8-bit PCM (signed, unsigned, RF5C164 sign-magnitude; 8-20 kHz) found nothing (all ≤ 0.36).
  - Next: dump the Sega CD PCM chip's RAM while it plays.

## UMK3 Toasty (2026-11-09, agent; tools/umk3toasty.py)
- It is in the Genesis UMK3. Outputs in extracted/umk3_toasty/: face.png (56x56, palette line 0 entries 1-5), toasty_rom.wav / toasty_gpgx.wav, toasty.json; clip shots/umk3_toasty.mp4.
- **Timing** (frames after the hit):
  - appears at 24, sliding in from x 299, 6 px a frame;
  - rests from 28 at top-left (275,175), showing 45x49 of it;
  - voice at ~30;
  - slides out from 61, gone at 68.
- **Voice:** sound $25, sample 37 of the bank at ROM $3AC0AC: 2036 bytes at $3B6790, 4-bit delta (table at driver +$200), 4072 samples, ~6974 Hz, 0.58 s.
- **Trigger:** an uppercut (or another launch); 19 frames later random(15) == 5. Both fighters must have energy left (not on the round's last hit), and neither may be Noob Saibot ($17) or $1A/$1B.

### The Pit's fall soundtrack (2026-11-09)
- **What MK plays:** from the uppercut, CD track 10 (the losing music) with the falling man's long yell and the blood splatter on top. The user confirmed by listening: track 10 alone is not the yell; shots/mk_pit_fall_without_track10.wav (track 10 subtracted) is the yell and the splatter.
- **The yell isn't in MK's files:**
  - not an 8SVX sample (SFX*.BIN, 9 speeds);
  - not raw 8-bit PCM in the .BAD/NEW_*/PRG files.
  - Where MK keeps it is still to find (the PCM chip's RAM while it plays).
- **Ours:**
  - tools/mkpitsound.py records MK's own soundtrack from the uppercut: 6.5 s into extracted/mk_stages/pit_bottom/fall.wav (from the user's MK disc).
  - build.mk_jingle appends it as part 3 (a man's), plus part 4 (a woman's: track 10 + SMACK1, Sonya's GIRLHURT and BLOOD.SVX at the man's times). The woman's is a stand-in: MK CD's only woman is Sonya, whose Pit fall wasn't captured.
  - patches.fatality_music writes their disc times after the 'EKPF' tag in BST.BGI.
  - The Pit code plays the one for the loser ($4C 2/10/21 = a woman) by MSCPLAYT when he is launched, and stops the disc (BIOS MSCSTOP, d0 = 2) 390 frames later. Otherwise the disc plays on into the next appended part.
- **Checked:**
  - Scorpion over Raiden: MK's man's soundtrack in our audio at 0.76 (EC's own sounds on top), then silence. shots/scorpion_pit_fatality_raiden.mp4.
  - Scorpion over Shadow: track 10 detected (the woman's).

## Unattended run, 2026-11-09 night
- **Knockdown poses (all MK fighters).**
  - Problem: scorpion_full.pick spread EC's knockdown frames (42:18 flight, 42:17 landing) over MK's knockdown capture, which gave its first and last poses, both standing. Raiden, Johnny and Sub-Zero also alias 'lying' (42:0c) to it, so they lay standing too. A fighter fell into the Pit standing up (the user saw it).
  - Fix: knockdown_pose picks by shape:
    - the flight: the flat pose off the ground with the most pixels (the flattest was an edge-on sliver for Raiden);
    - the landing: the first pose back down;
    - lying: the flattest pose on the ground after that.
  - Picks (flight, landing, lying): Scorpion 9/27/28, Raiden 29/39/41, Johnny 12/30/31, Sub-Zero 8/27/28.
  - Left: one or two frames of the bounce replay's first frame (42:24, a standing hit pose) at touchdown.
- **MK's CD cues.**
  - The FINISH HIM part is now track 9; the fatality parts are track 13 for 4.2 s, then track 10.
  - Fix: the tracks' 2 s of silence is the pregap (INDEX 00); MK plays from INDEX 01. The old part 0 included it.
  - Measured on our fatality clip: 13 at 10-15 s, then 10.
- **Johnny's split punch does nothing to a woman** (the user, from MK).
  - The hit lands on the frame its step loads, before any hook runs. So r_generic (Johnny's block) clears the hit word of his move $10 script's strike step (42:07) while his opponent is a woman, and puts it back (saved) for a man.
  - Measured: Shadow 0, Jetta 0, Trident 8 (crouch kick control: 8 on all).
- **The Pit's announcer for an MK winner.**
  - When the fall soundtrack's 5 s are over (PIT_FALL_FRAMES 300): "<NAME> WINS" (SCORwins/RAIDwins/CAGEWINS/ZEROWINS), plus "FLAWLESS VICTORY" 1.9 s later if the winner had all his health (104) when the loser was launched. These are build.mk_jingle parts 5-12, times after the EKPF tag. An EC winner: the disc is stopped.
  - Gotcha: ~3 s after the announcer starts, EC moves to its stats screen. STATS.CO loads at $34000 over the Pit's code, and the disc is cut off. MK's 3 s gap to FLAWLESS didn't fit, so it is 1.9 s.
  - Measured (Scorpion over Raiden): SCORwins 0.99, FLAWVICT 0.90.
- **No Cinekill on an MK fighter** (patches.no_cinekill_mk).
  - EC's Cinekill check (PLYR $14AA2, a5 = the victim: health at most 24, then $195/$7A flags; it then hides both fighters and runs DECKL.VC, the only module that sets $1CD4 = 4). Its first compare is now a jsr to a SUB.BIN tail routine that answers "no" for an MK victim (mkinputs.MK_IDS).
  - PLYR's stub space is full (36 bytes short), hence SUB.BIN.
  - Untested in play: the Cinekill's input isn't known yet (no direct references to $14AA2; reached through a table).
- **The woman's Pit yell:** not found. The yell isn't in the sound chip's memory in a snapshot taken during it (state searched as 8-bit PCM, signed/unsigned/sign-magnitude, 6-22 kHz: best 0.24). It may be played by the Genesis side (Z80/DAC) or stored packed. The women's version stays a stand-in (track 10 + Sonya's cry).
- **Checks after all of this:**
  - tests 0 failed;
  - hitmatrix --quick: 0 misses;
  - pitcheck: 7/7;
  - re-recorded raiden_moves / johnny_moves / subzero_moves (the knockdown and anchor changes), scorpion_fatality (cues), scorpion_pit_fatality(_raiden).
- **The touchdown flash fixed:** the bounce replay's first frame (42:24, a standing hit pose) showed for a frame or two. The Pit code saves the loser's frame word at touchdown (fvars+26) and puts it back when it ends the replay.

## Hit reactions, blood palettes (2026-11-10)

### Hit reactions
- **What EC plays.** Probed in a duel with every button: EC plays 42:01 (6 frames), 42:26 (6), 42:24 (6-12), then 42:01 again for ~10 while recovering.
  - The script is BLA.CO +$4A14: 42:01/3, 42:26/3, 42:24/$14.
  - The closing 42:01 isn't in the script. PLYR puts the script's first frame back (the step pointer stays on 42:24).
  - BLA.CO +$49E8 is a second hit script: 42:26/2, 42:24/$14.
- **The bug.** 42:26 sat in 'idle' and 42:01 in the 'idle' range, so two of the three frames showed the stance.
  - 42:24 got the first non-stance pose of the capture. For Raiden that was a stance pose his 60-frame idle capture missed, because his stance cycle runs about 60 frames. He showed no reaction at all.
- **The fix.**
  - scorpion_map 'hit_high' = 42:26 (MK's hit), 42:24 (stagger), 42:01 (recovery flinch); 42:25 and 42:27 are unused.
  - scorpion_full.hit_pose picks at 0.25 / 0.4 / 0.7 of MK's reaction poses.
  - Hit captures drop poses first seen before frame 64 (HIT_LANDS; P2 presses at 50, MK reacts from about 67).
- **Smoother.** Next would be an MK-timed driver for state $1A (like DAZE_SEQ) on spare frames.

### Blood palettes
- **Scorpion's blood** is r_blood droplets: sheet $1B frame 7, drawn in his palette line, whose colours 12/13 are red.
- **Raiden and Sub-Zero** now free 12/13 as well:
  - Raiden: colour_map {10:9, 6:5}, blood_moves {12:10, 13:6};
  - Sub-Zero: colour_map {6:12, 1:15}, blood_moves {12:6, 13:1}.
- **Johnny can't free them yet.** His home stage animates entries 3, 4, 7, 8 and 9, so the only slots left free are animated ones.
- **Still Scorpion-only:** the fight-wide hooks (blood, uppercut launch, FINISH HIM, fatality) live in his full block (mkinputs ext_block). A generic block only borrows them when Scorpion is in the fight.

### MK behaviour for every MK fighter (2026-11-10)
- **Shared code in SUB.BIN** (mkinputs.build, SUB_AT), one copy for every block:
  - blood (r_blood, droplet task, drop counter);
  - mkrow + mktab (4-byte rows: id.b, bleeds.b, his 42:02 word);
  - the throw landing (emit_throwfix).
- **SUB.BIN is now at its ceiling:** it ends $13FE6, 26 bytes below PLYR.CO at $14000. patches.put_sub refuses to overrun it.
- **Uppercut launch:**
  - r_launch launches for any MK fighter showing his own 42:02–42:04 (down + Y) or 40:09 (down + X). MK CD has both crouching punches as the uppercut.
  - Generic blocks have a 'launch' raw entry. With no full block (Scorpion's) in the fight, a generic block runs its own launch, and its per-frame call flies the victim (vars+14..23).
- **Uppercut strike pose:** mkscripts uppercut moves strike on the *highest* pose ('height').
  - 'reach' had put Raiden's hit on his follow-through and Johnny's on his first crouch.
  - The strike frames (42:03, 40:09) get a box reaching as far as any uppercut pose (scorpion_full.SWEEP_STRIKES). The height pose alone gave 61 hitmatrix misses.
- **Full block room:** its tables went to bytes (walk and daze tables; each table stays on one sheet), saving ~60 bytes.
- **Hit reaction at MK's timing** (mkinputs.hit_plan / emit_hitdrive):
  - MK's poses from the first reaction pose to the stance, one frame word per call, in state $1A.
  - It restarts when EC (re)starts its hit script ($AE == $AA after the first step, or the counter is -1).
  - EC's 42:01 / 42:26 / 42:24 are pinned to the poses due when EC loads them. The other poses go on free slots taken from the end of mkscripts' list.
  - Art group 'hit_seq' is drawn from the hit_high capture (scorpion_full.CAPTURE_OF).
  - EC rewrites 42:01 once in the recovery: a 2-frame flash of the first reaction pose.
- **Teleport punch:**
  - $102 low byte is an attack *type*, not a reaction: punches are 1/2, uppercuts $40/$41, Blade's dash $1C (a knockdown).
  - TELE_HIT = $1101: a standing stagger (~30 px; MK ~70) for 17 damage. MK takes 19/119.
- **Throws** (mkinputs.emit_throwfix, patches.mk_throw_arc). MK's roll throw, measured on mk_2p: the victim's lowest point ~74 px up, lands ~110 px behind and lies, about 50 frames, no bounce.
  - EC's victim records (10-byte steps: frame, dx, dy, flags, ticks) in the MK modules now have their lifts scaled ×0.5 and the overhead hold cut from 7 to 4 ticks.
  - At the release (victim state $37 → $1C) her speed across ($5E, $C6) is cleared every call until she lands. EC's vertical arc stays, so she lands in her lying frame.
  - The bounce (the knockdown replay) is ended as on the Pit. $C6/$CA must be cleared too, or the script relaunches her.
  - Shadow lands ~120 px behind Scorpion, lies, gets up. There is a 2-frame flash where the bounce starts.
- **Blood:** Raiden and Sub-Zero bleed (palette slots freed). Johnny doesn't yet: his home stage animates the only free slots.
- **Not done yet:**
  - Raiden's lightning, torpedo (with his yell) and teleport;
  - Sub-Zero's freeze and slide;
  - Johnny's blood;
  - the teleport punch's extra knock-back;
  - MK-timed sync of the first hit pose with EC's first call.

### Throws like MK, Johnny's split, Johnny's blood (2026-11-10, later)
- **MK disc checks:**
  - All four MK1 CD throws send the victim behind the thrower (shots/mk_raiden_throw.png, mk_johnny_throw.png).
  - Johnny's split vs Sonya (states/mk_johnny_sonya_2p.state, from mkduelstate johnny_sonya): he holds the split with his fists at his chest, no punch. Vs Sub-Zero the fist goes out (shots/mk_johnny_split_sonya_vs_subzero.png).
- **Thrower animation** (mkinputs.throw_plan, emit_hitdrive with state $0D, script=False): MK's throw poses fitted to EC's choreography.
  - The pre-peak poses are squeezed into 16 frames, the peak is held to the release (36), then MK's after-poses run until 52.
  - It steps aside once EC shows his stance (40:00-40:02).
- **Blade's thrower list** (BLA.CO $1B10) reused 42:0F/42:10 late, which flashed grab poses over MK's peak. In the MK modules it is now 42:10, 42:0F, 42:0E, 42:0D ×4 (mkinputs.THROW_LIST; patches.mk_throw_arc).
  - Each EC frame loads once and is pinned to the pose due then.
  - 42:11 (Blade's post-throw frame, BLA.CO $1A62) is pinned to the last recovery pose.
- **Victim records:**
  - Step 0's dx is capped at 56 px (Blade's reach put Shadow 117 px out; EC then shifted both fighters 97 px to keep her on screen). The cut goes onto step 1, because steps move her relative to the last.
  - Raiden's and Johnny's last step +35 px (THROW_FAR): their victims land ~155 px behind, as in MK, against ~120 for the roll throws.
- **The fall:**
  - Off the release, the victim gets no rise (SUB thr clears $5E/$C6 and returns phase 1 in d0).
  - The caller (emit_throwcall) clears $CA and an upward $62, and ends her knockdown step each call (task +$26 = 1).
  - She is down at once and the bounce is cut. She lies in the knockdown's flight pose (her script's lying step, after the $0100-flag "fly till landing" step, isn't reached). Next: jump $AE to that step at the landing.
- **Johnny's split on a woman:** the script's punch/strike/punch steps (BLA.CO $43B4, steps 1-3) show the split 42:05 and the hit is cleared. For a man the frames and hit are put back. The strike step is addressed by position (SPLIT_STRIKE).
- **Johnny's blood:** grey 13 (and 8) merges into dark brown 2 and light grey 14 into white (barely visible); black moves to 14 (blood_moves {12:14}). patches' moved() now applies palette_set before the blood moves.
- **Droplets:** none when no fighter in the hit bleeds (they had come out in Johnny's whites).
- **Room:**
  - SUB.BIN has 12 bytes left.
  - Scorpion's full block has ~20 bytes left (5610/5632).
  - Generic blocks: ~2 KB.

### MK specials for Raiden, Johnny, Sub-Zero (2026-11-10, later)
- **Why they had none:** the generic fighters run Blade's code, but PLYR's special-move handler table entry for their id still pointed at the host's (Chin Wo's / Zuni's / Yappy's) handler and list, so no input reached Blade's $34/$35.
- **mkinputs.r_gmoves:** each generic block holds its MK move list (GENERIC_MOVES), a copy of Blade's handler on it, and a raw 'taps' recogniser. Every frame 'g_reg' fills the list's absolute entry pointers (its own slot's) and writes the handler's address into PLYR's handler table (HANDLERS + 4 × (id − 2)).
- **Recogniser (r_taps):** a move's button word may be 0 (two taps are the move) or DIR3 | direction (a third, facing-relative tap).
- **Moves:**
  - Raiden: lightning D,F+LP ($34), torpedo B,B,F ($35);
  - Johnny: green bolt B,F+LP ($34), shadow kick B,F+LK ($35);
  - Sub-Zero: ice blast D,F+LP ($34).
  - EC buttons: X = MK LP, A = LK.
- **Projectile poses:**
  - Projectile art groups (lightning, iceblast, greenbolt) use the stance anchor (IN_PLACE). MK draws the bolt in the fighter's colours, and a burst above his head had become the "head", so the crop cut Raiden out.
  - Their strike box is the spear's (scorpion_full.PROJECTILES: stretched to 127 px on 42:2E). The lightning hits from ≤127 px (MK's travels the whole screen: a real projectile is still to do).
- **Generic modules** get mkinputs.recovery_still: the projectile's recovery steps without Blade's forward drift.
- **Raiden's torpedo** = Blade's dash. 41:16/17/61/62 are pinned to MK's crouch, spring, dive and flight (patches RAIDEN extra). scorpion_full.KEEP_HEIGHT keeps the torpedo poses at MK's height over his stance feet.
- **Still to do:**
  - Raiden's teleport (D,U), Sub-Zero's slide (a chord) and freeze;
  - travelling projectiles;
  - Raiden's torpedo yell;
  - special damage vs MK (lightning 3).

### Raiden's teleport, Sub-Zero's freeze and slide, special sounds (2026-11-10, later)
- **Raiden's teleport** (D,U → Blade's move $31, which is a plain script with no code of its own):
  - mkinputs.rtele_plan builds our own script on it: MK's crouch (3, 4), white silhouette (5, 6), then at step RTELE_AT emit_rtele puts him 41 px past his opponent (all x copies) and flips $20/$100 bit 3. Then the silhouette and his colours (14, 15). ~36 frames; MK's is 33.
  - MK draws a sinking silhouette and a rising one at once; one sprite can't.
- **Sub-Zero's freeze** (mkinputs.emit_freeze). MK, measured on mk_subzero_2p: 192 frames, a 2-px shake every 2 frames, no damage, colours icy.
  - On his ice blast's hit, the victim's move task is parked in a loop that sets $1F (dazed: input starts nothing).
  - His pose is held, his 15 colours are tinted from EC's palette copy (-$6956(a6); upload flag -$67D4(a6) = -1; line = ($7A & 3) ^ 1) by an R+G+B table, and he shakes.
  - EC's stun clock tries to stand him up after ~46 frames: he is re-parked each call unless hit ($1A-$1D, which breaks it).
  - At the end: his idle resume PC (recorded while he stands), the cleanup bits, colours back.
- **The recogniser** now also takes:
  - a second tap of 0 (none);
  - CHORD ($4000) | buttons: all of them held, read from the pad words $A3A/$A3C(a6). ($164(a1) holds directions only.)
- **Sub-Zero's slide** on MK CD is back + LK + HK (MK pad C + Z; EC A + B). Back + LK + Block is his low kick; the earlier 'slide' capture was that. It's mapped to Blade's dash ($35): 41:16/17/61 → MK pose 8 (drop), 41:62 (the hit) → 9 (the slide).
- **Special sounds** (patches.mk_voice, GENERIC_VOICE):
  - Raiden: RAIDDive (torpedo), spark2 (lightning);
  - Johnny: jctrails, FIRING2;
  - Sub-Zero: subzwep, subslide.
  - On Blade's voice ids $06D6.. at 8000 Hz. Blade's own plays of them are skipped; the block plays them when the move starts.
  - Raiden's clips were found in sound RAM after the torpedo, and the audio level rises.
- **Still to do:**
  - travelling projectiles (MK's freeze ball, lightning and green bolt cross the screen; ours reach ≤127 px). Plan: the ball's art in Blade's effect sheets $44/$45 and an effect object flying it (a fighter frame can't be shown twice);
  - FINISH HIM / fatalities for the other MK fighters.
- **Travelling projectiles: groundwork (not built yet):**
  - EC Blade's own $34 isn't a projectile: he throws his arm blades out on chains, inside his own frames.
  - His code's `move.b #$44/$45,$1B(a5)` write *frame* numbers (an object at BLA.CO $3914 plays frames 0-7 then removes itself), not sheets $44/$45.
  - Experiment: blood droplets drawn from sheet $44 frame 0 froze the game (test 03 hung). Blade's effect sheet isn't drawable that way.
  - Sheet $1B (the droplet's spark tile) is in no .PL; it must come from GAME.DAT/SUB.
  - **Next:** find how a static effect sheet's tiles get into VRAM (sheet $1B's loader). Then load MK's ball/bolt art the same way and fly a $24 effect object (as the droplets) with our own hit check.

### Travelling projectiles: how EC does them (2026-11-10, end of session)
- **Effect sheets:** every EC fighter's .PL has static effect sheets: type-4 chunks whose tile source (type 0, flag word +12 = 4) is RAW 4bpp tiles.
  - +14 points at the data; +18 is the VRAM area size, e.g. Blade's $92/$94 are 3392 bytes = 106 tiles.
  - Frame record: A-box count + boxes (x1 x2 y1 y2), B count, then pieces: size word ((w-1)<<10 | (h-1)<<8 | $50), attr (tile index + flip/palette bits), x, y; ends with $8000.
  - The offsets table is at sheet +22, relative to +22.
  - Blade's $44 (63 frames: sparkles, balls) and $45 (8 frames: an explosion) decode cleanly.
- **Drawing:** an object spawned with the FIGHTER'S OWN id ($6954 d0 = his id) can show his effect-sheet frames (test PROJ_TEST, now off: a sheet-$44 frame flew out of Raiden's lightning, fine). With the spark's id ($24) the game froze.
- **Projectile hits:** EC's own mechanism (PLYR $19D64), done by the hit engine.
  - The owner's long at $122 is his live projectile. Its $78 is damage, $79 the hit level (table $1A2CC, 16-byte entries), and $36/$3A/$38/$3C its world box, tested against the victim's hurt boxes.
  - `$6A38` (→ PLYR $1ABEC) registers it, a5 = the object with owner at $8C: palette bits from the owner, $94 = the owner's opponent, owner $122 = it.
  - On a hit PLYR calls the object's $84 with d0 (4 = a special case).
  - Xavier's $84 (XAV.CO $2F58) plays sounds, removes the object (bset #2,$82) and clears the owner's $122.
- **Xavier's recipe (XAV.CO $25FC / $33AC):**
  - lea descriptor(pc),a1 (34 bytes, first word = his effect sheet $0049; XAV $2F36); move.w #$1B5A,d0 (object type → $4C); move.w #0,d3; jsr $6BBA (spawn at the owner; d2 = the owner's $98).
  - Then: task code = $33AC, $84 = $2F58 (hit callback), $9A = 4.
  - The task: jsr $6A38 (register); sleep 2; move.l #$60000,d0; jsr $691E (speed 6 px/frame); bclr #1,$7B; move.w #2,$78; then it loops its flight frames.
  - Object type ids by fighter: Blade $1F40-$1F44, Xavier $1B5A/B, Shadow $03E8/9, Chin Wo $4651/4 ... (each fighter its own range).
- **Plan for MK projectiles:**
  - MK's flight art (ice: iceblast poses 14-17; green bolt: greenbolt 10-14; lightning: lightning 14-16, separate from the fighter in the captures) into sheet $45 + tile source $94 of each MK fighter's .PL (≤106 tiles).
  - A descriptor copied from Blade's with sheet $45. Spawn as Xavier does at the cast's release step, our own $84 that removes it and clears $122, MK's speed.
  - The casting moves: plain scripts (like the teleport on $31) instead of Blade's $34 (whose own projectile object would fight ours for $122).
  - Sub-Zero's freeze then triggers on his projectile's hit.

### MK projectiles fly (2026-11-10, evening)
- **Art:** tools/mkprojectile.py cuts the flying part out of MK's capture (components > 40 px in front of him) into his effect sheet **$44** and its raw-tile source (patch '<key>-proj'). Both chunks keep their sizes.
  - Sheet $45 must stay Blade's: EC draws its frames as the impact where a projectile hits (with our art there it showed as stripes).
  - Cast poses lose that part too (scorpion_full.load_action → mkprojectile.strip), so there is no second bolt in his hand.
- **Code** (mkinputs.emit_proj, generic blocks):
  - At his cast's release frame (42:2E) an object is spawned with `$6BBA` (a5 = him, d0 = Blade's type $1F40, a1 = a copy of Blade's descriptor BLA.CO $3B26 with sheet $44). Then its task and $84 hit callback are ours.
  - The task: `$6A38` registers it (his $122); $78 = damage byte : level byte (level 2), $A4 = reaction.
  - EC applies no velocity to it: the task moves it 12 px a run (it runs every other frame = MK's ~6 px/frame) for 35 runs, then removes it and clears his $122.
  - EC's collision box comes from the frame's A box. The hit callback removes it and sets pj_v+2.
- **Values:**
  - Raiden's lightning and Johnny's green bolt: 10 damage, reaction $1A. Verified hitting Shadow from 157 px away.
  - Sub-Zero's ice: 0 damage, no reaction. Its hit starts emit_freeze directly; EC's own brief reaction is overruled for FZ_GRACE calls. Verified frozen from frame 41 to 231 (MK 192 frames), then free to walk.
  - The casts' own strike boxes are off (scorpion_full.no_strike).
- **Next idea (user asked):** Sub-Zero's spine-rip fatality, built like Scorpion's.
  - MK's capture: his grab, pull and head+spine poses.
  - The headless victim from MK drawn in his palette over the EC loser; blood droplets.

## EC's own headless deaths: Z<xx>.BIN (2026-11-13)

Found while looking for art for headless MK fatality victims (the user remembered
EC's shotgun head-blow). tools/ecdeath.py renders them (shots/ec_deaths/).

- **seen** Chicago Theater = LAR files, stage mode $1B (stock disc, forced via GAME.CO
  $C28 once GAME.CO is in RAM). LAR.BGI's finisher checks ($14FA(a6) -> $3400A):
  - +0 (PLYR $17AA4 path, on a hit): loser x $223-$279 (or $170-$1C3 if $100 bit 3)
    -> drive-by Overkill ($1CD4 = 1). If the loser's $159 bit 6 is set instead:
    loser facing right, x $284-$2C4 -> the usher's Sudden Death ($1CD4 = 2).
  - +2 (PLYR $1784C path: loser hp <= 20, $190 >= 10, deciding round, d7 != 0):
    facing right, x $284-$2C4 -> sets $159 bit 6. Not reproduced by a plain hit
    (the $159 bit is rewritten on the hit frame); forced instead by patching LAR.BGI
    in RAM ($34054: bne -> bra), which plays the full usher Sudden Death.
  - The usher scene: drive-by knocks the loser flat, the usher climbs out of the
    booth and shoots the LYING loser's head off (blood spray), stats 'Sudden Death'.
- **seen** The Sudden Death loads LAR.OC/LAR1.OD/LAR2.OD (file ids $84-$86) and then
  a per-victim file at $7C000 via sys_6C26: table LAR.BGI +$284, word per victim
  id-2 = file id $EC-$FD. The runtime file table is at $12E9E (8 bytes per id:
  sector, sectors; built at boot, read it from RAM):
  ZSH ZLR ZRX ZSL ZTR ZMD ZXV ZBD ZJT ZEC(x3 ids) ZRP ZPH ZEX(x3) ZCH(x2) ZRV ZSN ZBS ZDW.
- **seen** Each Z file: two raw-tile sources (flag 4) + two type-4 sheets
  (ids $100+n and $112+n, n = file order; ZEC has only the first).
  - Sheet 1 (~18 frames): the usher kill (lying with head, head burst) and an
    'arched back, torn apart' death.
  - Sheet 2 (~27 frames): frames 0-11 a HEADLESS standing stagger -> knees -> lying
    flat; frames 12-23 the same with the head. All 17 regular EC fighters have it.
  - Palette: the loser's own fighter line (Shadow: line 2 in that capture).
- **seen** LAR.OC's death objects set the frame high byte to a small slot
  (move.b #4,$1A(a5)) and step $1B with sleeps: the resource loader
  (load_resources, list $0014) maps the file's sheets to object slots. Not yet traced.
- **plan** MK decapitation-style fatalities (Sub-Zero spine rip, Johnny's head punch,
  Raiden's head explosion) on EC losers: load the loser's Z file the same way and
  play sheet 2 frames 0-11 on the loser (their own colours: no ghost recolour), his
  held head/spine from the MK capture. MK losers keep MK's captured art.

## New fighter ids instead of hidden slots: survey (2026-11-13, agent, read-only)

The MK fighters currently replace EC's hidden Blast/Chin Wo/Zuni/Yappy. Survey of what
truly new ids would take (the agent's 'seen' = checked in bytes; not re-verified by me):

- Fighter ids are 2..26 (idx = id-2; $AED2 is identity). Object types 27..37 are other
  spawned objects (descriptor table $11E8C has 38 entries), so new fighters need id >= 38
  (idx >= 36).
- Unlock mask $1CC8/$14A4 is one long (saved to backup RAM $762C), tested with btst.l
  (mod 32): idx >= 32 aliases. Better: treat idx >= 25 as always selectable ($20CCC/$1FA3E).
- Hard bounds: GAME $1FA54 cmpi #$19 (25 grid slots); left/right wrap $18; up/down rows
  hard-coded (6, $E, $16; GAME $1FF90-$2011C, ~400 bytes); arcade lists idx 0..22
  ($1EC32, $14DCE, $2263A); portrait offset lsl.w at GAME $21FBE overflows idx >= 35.
- Every id-keyed table has exactly 25 entries and is followed by other data/code: all
  must move. SUB $AED2/$AF04/$AF36 (lea pc at $AE6C/$AE7A/$AEB2: can't reach SUB's end),
  $AF68 (.SND, idx 9 and $18 share slot $17, $AD7E), $B6B8 AI, $B970 HUD, $12A46 win
  names, $12E20 (d8(pc)), $11E8C descriptors; GAME $14C28 stage, $21620 idx->slot,
  $2163A grid (x, y, id; 6 bytes), $21B1C versus names, $22048 palettes (24); PLYR
  $148EC / $15F1B / $153A0 / $18096 (d8(pc) users at $148D8, $1539A, $15EEC); STATS $346B4.
- Space is the real problem: SUB and PLYR have ~10 bytes free each in our build; GAME.CO
  ends $23FDE (guess: free to ~$28000). Tile-source table $D448 (300 x 8 bytes) has only
  5 ids left ($24E-$256), a Blade copy needs 6: move and grow it. Sheets $D9-$FF: ~31 left.
  File-name list $12E9E..$13CF4 (308 entries) is full: new file names need it moved.
- Select-screen icons: GAME $1FA1A..$1FC9C, tile = (-$6320(a6)+$218) + idx*24 (4x6, line 2).
- Steps: (1) find resident free RAM / reclaim SUB space (riskiest), (2) ids 38+ with new
  descriptors, (3) pad and repoint every table, hook the d8(pc) users, (4) unlock rule,
  (5) 4th grid row + up/down rewrite + icons/portraits/palettes, (6) tile sources, sheets,
  sound slots, file names, (7) per-copied-CO id checks (cmpi #9,$4C as the roster patch).
  Untested risk: fighter modules telling objects apart by $4C value.

### Sub-Zero's spine rip on EC's own headless art (2026-11-13, done)

- **done** The fatality loads the loser's Z<xx>.BIN with EC's own loader (`$6C26`,
  -$6E70(a6) = destination, file id $EC + n) over the loser's own .PL ($51800 for P2,
  $81800 Word RAM for P1), from the loser's move task (mkinputs gk_load). It clears
  the loaded-file cache entry -$734C(a6)[id] before (else the loader returns without
  reading) and after (so EC's round-end free loop ignores it). Then MK's music starts:
  a CD data read stops CD audio, so the music must come after.
- **seen** The CD read blocks the whole sub CPU (~1.5 s, ~90 frames): the game pauses.
- **seen** Sheets $100-$1FF: the draw (SUB $F87E) adds $100 to $1A's sheet byte when
  the object's word $28 is non-zero. So the loser's own fighter object shows Z sheet 2
  ($112+n, n >= 10: one less) with $28 = 1, $1A = $12+n:frame, in her own palette.
  Frames used: 0 jerk, 1-5 headless stagger, 6 knees, 7 falling, 8-11 lying
  (mkinputs.szf_zframe, timed from MK's victim capture). She falls toward him.
- **seen** EC's script stepper (PLYR $18174 / $182A6): $AE = the current step (frame
  word -> $1A, +2 ticks -> TCB+$12, +4/+6 dx/dy, +8 -> $F6, +$A -> $102); on expiry
  $C2+1 > $C4 ends the script, else $AE += 12. It runs in TWO tasks of the fighter
  (tasks 3 and 4, PC $182A6), outside the move task (task 2) we park: each may take a
  step after $AE is redirected. A hold = 3 copies of (frame, $7FFF, 0, 0, 0, 0), $C2 = 0,
  $C4 = 2. Without it the loser's dazed script stepped to one of her own frames after
  her .PL was overwritten: EC unpacked garbage and the game hung (seen in the video run
  only, after the freeze/throw segments).
- **done** A fighter's .PL tail: EC loads the whole file but stops parsing at the zero
  chunk length, so data appended after it is resident and untouched (P1 at $81800+off,
  P2 at $51800+off; mkinputs.pl_tail). Sub-Zero's MK attack scripts and the fatality
  tables live there (patches.mk_code, mkinputs.GEN_TAIL / TAIL_FIGHTERS): his code
  block went 5628 -> ~4200 of 5632 bytes. Raiden's CHW.PL has only ~3.4 KB of room.
- Losers without Z art (MK fighters' hosts, the gag animals, the bosses) keep their
  dazed frame. MK-vs-MK FINISH HIM still doesn't reach Sub-Zero's block (open).
- **next** The loser's own severed head: Z sheet 1 frames 6 (upright) and 7 (tumbling),
  every fighter, drawn by a spawned object in the loser's palette at his hand (Sub-Zero)
  or flying up (Johnny's decapitation). The pasted skin-tone head (mkfatality_subzero
  held(), PASTE_HEAD) is off: the user found it looked terrible on Larcen.

### The loser's own severed head in his hand (2026-11-13, done)

- **done** Every EC fighter's head (Z sheet 1 frame 6) is cropped and centred at build
  time (mkinputs.szf_heads): frame records go into Sub-Zero's effect sheet $44 after
  the ice ball's (frames 2+n, tiles numbered from 0), the raw tiles into his .PL tail.
  At the fatality (first timeline call after the Z load) gk_head uploads the loser's
  head tiles over sheet $44's VRAM ($C760 kind 4 -> $CE1A; VRAM address from the
  allocation at -$67D0(a6)+4*src, src = sheet's raw source word / 2) and spawns an
  object (Blade's projectile descriptor, owner HIM) showing $44:2+n with the loser's
  $1E/$20 (her palette line, facing). Each call puts it at his hand (MK capture's head
  blob vs his feet, x1.08, his way round) or off screen (y -256) before he holds it.
- **seen** Gotchas hit on the way:
  - non-fighter objects draw from tiles uploaded once per source ($D3DA: -$6320(a6) =
    VRAM tile base per source id; skips sources already in VRAM), only fighters ($7B
    bit 7) upload per frame: a Z sheet drawn by a spawned object showed garbage;
  - spawning ($6BBA) with the loser as owner, or from inside a task, hung the game:
    spawn from his per-frame code with him as owner (as emit_proj);
  - tail data at an odd address (the 25-byte victim table) = 68000 address errors:
    the tail is padded to even / 32 bytes now.
- EC's own head-frame origins differ per fighter (Larcen's at his chin): centred instead.

### Spine rip polish and MK-vs-MK FINISH HIM (2026-11-13, later)

- **done** EC's death art faces the other way from the fighter's own frames: on her
  first death frame gk flips $20 and $100 bit 11 (the stepper recomputes facing from
  $F6 ^ $100), so she keeps facing him and falls toward him.
- **done** Blood: every 2nd call (gk_bc) MK's droplets (SUB blood, him as 'attacker':
  his red) from her neck - SZF_NECK, the top of the headless body per death frame
  (median over the fighters) - standing and lying. No persistent pool yet.
- **done** The fall goes on through EC's lying frames 8 -> 11 (SZF_SETTLE steps each).
- **seen/done** MK vs MK: FINISH HIM ('finish', after damage) is a fight-wide hook:
  _block runs it in ONE block (a full block if any, else player 1's), whose r_finish
  checks the winner is its own fighter. So Sub-Zero never got FINISH HIM vs Scorpion
  (or as P2 vs Raiden/Johnny). r_finish now forwards (fi_fwd) to the other slot's
  block's raw finish when that block's fighter is the winner. Verified: Sub-Zero vs
  Scorpion FINISH HIM + spine rip trigger. Scorpion's fatality still passes
  (tools/fatalitycheck.py).
- **open** MK losers have no EC death art: they stand intact during his fatality.
- **done** (user-caught, twice) EC's Z sheet 2 frames 0-2 are the shotgun blast: the
  body thrown back and bent the other way. They read as the loser turning round; the
  stagger now uses frames 3-5 only (szf_zframe). MK's own capture has no blood pool
  under the body (no red in the victim's lying poses), so none is drawn.
