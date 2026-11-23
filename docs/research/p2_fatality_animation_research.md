# Player-two fatality art and MK animation table: investigation

Why an MK fatality's victim art broke when the winner was player 2 (2026-11-14), and what MK's
animation table holds. The player-2 fatalities have since been fixed in the build (each MK
fighter's fatality as player 2 is in allchecks); kept for the mechanism and the measurements.

## EC cross-player art: a promising isolated test

In a duel state with Scorpion as player 1 and Shadow as player 2 (tools/lib/duelstate.py):
the fighter objects are at `$2E188` and `$2E330` respectively. Their word at
`+$2A` is `$4100` for P1 and `$4000` for P2. Bit 8 is thus set on P1, clear
on P2 in this state. The previously reported unsuccessful experiment changed
bit 0 of byte `+$7B`; that is a different flag.

Disassembly of stock `SUB.BIN`:

- `$FC24` takes the tile-source pointer from the shared `$D448` table and
  loads the **victim object's** `+$2A` into D6 before calling `$11784`.
- `$1178E` tests D6 bit 8. When set, `$116A4` queues command `$88` for the
  main CPU, including the tile-source pointer; when clear, `$11796` unpacks
  locally on the sub CPU into `$2F2D4` and `$FC70` queues its transfer.
- This makes a player-1 victim showing player-2 art a plausible mismatch:
  the source is P2's PRG-RAM art but the victim still selects the P1/main-CPU
  path. The source address accessibility and full queue behaviour still need
  tracing; this is a hypothesis, not yet a complete root-cause proof.

**Test performed:** using `tools/dev/ecdraw.py`'s Unicorn `Drawer` on that state,
only an in-memory copy of P1's `+$2A` was changed, clearing `$0100`, and
P1 was asked to draw the current P2 Shadow frame `$3716`. P2 drawing its own frame and
P1 drawing the same frame with the flag cleared both produced 12 pieces and
queued 2,592 bytes from `$2F2D4`. Their copied tile bytes were identical;
their destination VRAM addresses differed as expected (`$3300` and `$45C0`).
Leaving P1's bit 8 set produced no local `$CE1A` copy in this isolated test,
consistent with dispatching work to the other CPU.

**Limits and proposed next test:** `Drawer` runs only the sub-CPU drawing
routine and intercepts transfers; it does not execute the full Genesis CPU,
fatality scheduler or the other fighter concurrently. Consequently this does
not prove the fatality is fixed. In an isolated emulator run, preserve the
victim's original `+$2A`, clear bit 8 only while it displays the winner's
PRG-RAM fighter art, force a fresh frame unpack (`+$19E`), and restore the
original flag afterward. Watch whether the other fighter and victim compete
for the unpacker's global time-slice state at `a6-$3F6E`, and verify the
picture, palette, both orientations, subsequent animation and mirror matches.
Do not change the existing fallback without those tests. If the flag is
rewritten every frame, identify the writer before selecting the hook.

### Full-game player-2 experiments (2026-11-14)

Using real two-player fight states with Shadow as P1 and Sonya or Scorpion as
P2, the already-loaded code was changed **in emulator PRG RAM only** to bypass
the P2 black-victim fallback, and three runs from the same state compared:
baseline; fallback bypassed alone; and bypass plus clearing P1 victim `+$2A`
bit 8. Each ran 750 video frames after the fatality input. These were independent
emulator processes; no build or source file was patched.

- Sonya: baseline finishes (finisher type 3, victim HP 0). Bypass alone freezes
  during the art transition (victim HP 1, finisher type 0; identical image
  for 511 frames). Bypass plus bit 8 clear completes (type 3, HP 0), with the
  victim's Sonya burn frames changing and the picture continuing to advance.
- Scorpion: baseline and both experimental runs complete (type 3, HP 0).
  Bypass without the flag gives visibly scrambled victim fire/skeleton art;
  bypass plus the flag gives a recognisable skeleton and collapse. This is a
  visual observation, not yet a pixel-for-pixel reference comparison.
- In these fight states the bit needed clearing only once per experiment; the
  victim retained `$4000` at `+$2A` during the observed 750 frames. The tests
  did not restore the original `$4100` or advance into another fight. Clear
  before the first foreign-art frame, and investigate a safe restore point.
- Extended flag runs to 1,600 frames: both still reported finisher type 3 and
  zero victim health, and the flag remained `$4000`. They settled on still end
  screens, so this extension is not a subsequent-round or reset test.

These tests support the unpacker-CPU mismatch as the immediate player-2 art
failure mechanism. They do **not** establish a fix for the separate Contest
freeze in `gk_load` during the loser's death-art disc load, or prove safety for
every victim, both orientations, mirror matches, or a subsequent round.
The in-memory patch sites were found by matching the winner-specific fallback
branch, not by assuming a fixed address: Sonya's `cmpa.l #$2E330,a1` followed
by `bne` was forced to the regular art path; Scorpion's matching `beq` to
`f_char` was replaced by a NOP. The research driver and its screenshots were
temporary and are not part of the project.

## MK animation table: measured Scorpion entries

The table begins at the longword in OBJ `$0E` plus `$CC` (`$EF54` for
Scorpion); its 36 entries are longword offsets into the OBJ. P1's animation
pointer at `$7D702` was sampled while running `tools/lib/mkmoves.py` input scripts
from `mk_2p.state`. These are pointers observed during the indicated actions,
not yet a complete or cross-fighter classification:

| Entry | Scorpion OBJ offset | Observation |
| --- | --- | --- |
| 3 | `$F1E0` | roundhouse script traverses this region |
| 5 | `$F060` | standing block script |
| 6 | `$F096` | standing high-punch script enters this region |
| 9 | `$F4A4` | spear script |
| 10 | `$F1BA` | standing low-kick script traverses this region |
| 14 | `$F3C8` | dazed sway, previously identified |
| 15 | `$EFFA` | idle, previously identified |
| 17 | `$F264` | knockdown/swept scripts enter this region |

The pointer can advance beyond the entry address, and several lists are
adjacent or share tails, so region overlap means these names require further
checks before use as definitive table labels. Some observed action lists do
not start at any of the 36 entry pointers: walking uses `$F3E0` forward and
`$F406` backward; crouch traverses `$F040`–`$F048`; a neutral jump traverses
`$F140`; low punch traverses `$F0D2`–`$F0D8`. These offsets are Scorpion
specific and should be identified by pointer/structure rather than copied to
other fighters.

Many sequences contain `$0000`, `$FFFC`, `$FFFD` and other control words;
some run into adjacent scripts before an `$FFFF`. Therefore blindly scanning
every entry to the next `$FFFF` can join multiple animations or misinterpret
arguments as frames. `tools/lib/mkdazed.py`'s `anim()` is safe for the observed
daze list but its current approach should not be generalized to all 36
entries without decoding the script interpreter and its termination rules.
