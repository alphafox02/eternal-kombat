# MK's recorded sounds, rendered from the disc

How the fatality sounds and the Pit fall, first recorded by playing MK in the emulator, came to be
rendered from the player's own MK disc byte for byte, and how the emulator core makes its output.

## Status (2026-11-15)

All nine sound files the build reads from MK are rendered from the MK disc,
byte for byte identical to the recordings `prepare.py` used to make by playing
MK (header and every sample), and `prepare.py` now renders them:

| name | file | exact |
| --- | --- | --- |
| `sonya` | `extracted/mk_moves_sonya/fatality_sfx.wav` | yes |
| `subzero` | `extracted/mk_moves_subzero/spinerip_sfx.wav` | yes |
| `johnny` | `extracted/mk_moves_johnny/fatality_sfx.wav` | yes |
| `raiden` | `extracted/mk_moves_raiden/fatality_sfx.wav` | yes |
| `liukang` | `extracted/mk_moves_liukang/fatality_sfx.wav` | yes |
| `kano` | `extracted/mk_moves_kano/fatality_sfx.wav` | yes |
| `scorpion` | `extracted/mk_moves/fatality_sfx_man.wav` | yes |
| `scorpion_sonya` | `extracted/mk_moves/fatality_sfx_woman.wav` | yes |
| `pit` | `extracted/mk_stages/pit_bottom/fall.wav` | yes |

- `tools/lib/mksound_render.py` renders them from `data/mk_sound/NAME.json` and
  the disc (the `SFX*.BIN` samples and the audio tracks); `--check` compares
  each with the file under `extracted/`; `--out DIR` writes elsewhere. No
  emulator. All nine take about 11 s.
- `tools/capture/mksound_measure.py` made the JSON files (once; research), with a
  logging build of the pinned core (`tools/capture/mksound_measure.patch`).
- `tools/lib/mksfx.py` reads the 19 sound banks (`--check`: identical to
  `extracted/mk_us/`).
- `prepare.py` no longer runs the emulator at all: the MK fight states
  (`mkselectstate.py`, `mkduelstate.py`, `mkpitstate.py`) existed only for the
  recordings and are no longer steps. A fresh clone with no emulator core
  (`EK_CORE` pointing nowhere) and no BIOS ran `prepare.py` through in under a
  minute and made the nine files identical to the working copy's.

An earlier tool, `mkpcmaudio.py` (the first 439,441 frames of Sonya's file),
is superseded and removed.

## Which recordings these are

`mkfatalsound.py NAME` plays the fatality from `build/states/<fight>_2p.state` twice:
from the real disc, to find where track 13 (the fatality music) starts, then
from a copy of the disc whose tracks 9, 10 and 13 are zero-filled; it keeps
15 s (661,500 frames) of the second run from that start. `mkpitsound.py` plays
the Pit fatality once, from the real disc, and keeps 390 frames' output from
the uppercut.

The files in the working copy came from **fight states made from a cold
boot**, as a fresh `prepare.py` made them (docs/research/reproducibility_2026-11.md: the
working copy's sounds were replaced by fresh recordings). Recording from the
working copy's own `states/` (made 2026-11-13) gives other bytes: the same
events at another sub-sample timing. States made afresh in a scratch folder
(`mkselectstate.py`, `mkduelstate.py`, `mkpitstate.py`) reproduced all nine
files exactly; the measurement used those.

What plays in each kept window (seconds into the WAV). "Muted" tracks are
read but zero (the zero-filled files); tracks 12 and 5 are not muted, so they
are in the effects-only files:

| name | CD tracks | PCM samples uploaded after the restore |
| --- | --- | --- |
| sonya | 13 muted 0-3.30; 10 muted 3.45-7.11; 12 9.96-14.75 | FINISHim, SONYKISS, BURNUP, SFX3A:4, SONYwins, FATALITY, FLAWVICT |
| subzero | 13 muted 0-3.45; 10 muted 3.60-7.23; 12 10.18-14.99 | FINISHim, BLOOD, FALL2, SMACK1, two unnamed, ZEROWINS, FATALITY, FLAWVICT |
| johnny | 13 muted 0-2.47; 10 muted 2.62-6.42; 12 9.31-14.10; 5 14.44-15.00 | FINISHim, BLOOD, FALL2, SMACK1, two unnamed, CAGEWINS, FATALITY, FLAWVICT |
| raiden | 13 muted 0-3.29; 10 muted 3.45-7.14; 12 10.00-14.77 | FINISHim, BLOOD, FALL2, spark2, RAIDDB1, RAIDDB2, RAIDwins, FATALITY, FLAWVICT |
| liukang | 13 muted 0-1.13; 10 muted 1.28-5.12; 12 8.01-12.82; 5 13.13-15.00 | FINISHim, BLOOD, FALL2, SMACK1, LKDEATBL, LUIKWINS, FATALITY, FLAWVICT |
| kano | 13 muted 0-3.15; 10 muted 3.32-6.94; 12 9.76-14.57; 5 14.89-15.00 | FINISHim, BLOOD, FALL2, SMACK1, one unnamed, KANOWINS, FATALITY, FLAWVICT |
| scorpion | 13 muted 0-3.92; 10 muted 4.07-7.69; 12 10.61-15.00 | FINISHim, HOTBRETH, BURNUP, one unnamed, SCORwins, FATALITY, FLAWVICT |
| scorpion_sonya | 13 muted 0-3.94; 10 muted 4.09-7.69; 12 10.61-15.00 | FINISHER, HOTBRETH, BURNUP, one unnamed, SCORwins, FATALITY, FLAWVICT |
| pit | 9 0-0.55; 10 0.70-5.74 | FINISHim, SFX2:3 (the falling scream) |

Other sounds play from samples already in the wave RAM at the restore (the
Pit's `legswipe`, `SMACK1`, `FALL2`, `BLOOD`, for example). MK fades track 10
out in software: it lowers the fader target by 16 (sometimes 32) every frame,
from 768 to 0.

## How the core makes the output (Genesis Plus GX 1.7.5, stable-retro 1.0.1)

From its source (stable-retro's `cores/genesis`, the pinned core's code):

- Three blip_buf buffers, mixed at the end of every frame: FM/PSG (silent
  throughout in all nine), the PCM chip, CD-DA. Output 44.1 kHz.
- Samples per frame: the FM/PSG buffer's clock is 53,693,175 Hz, 896,040
  cycles a frame; its blip factor `ceil(2^52 * 44100 / clock)` (in double
  precision) sets how many samples each frame gives (735 or 736).
- PCM chip: one sample per 1536 cycles of the 50 MHz Sega CD clock
  (32,552.08 Hz). Per sample, every channel that is on: read the wave RAM
  byte at `addr >> 11`; `$FF` loops (addr = loop start, that byte is read
  instead, no step), else `addr += step`. Bytes are sign/magnitude (bit 7 set:
  positive); each channel adds `(v * env * pan_nibble) >> 5` per side; the sum
  is clipped to 16 bits. With the chip disabled (CTRL bit 7 clear) it outputs
  0 and the channels stand still. A register write takes effect at the chip
  sample the sub CPU has reached (the core runs the chip up to the write
  first), so each event has an exact chip tick.
- MK uploads a sample by writing its bytes through the 4 KB bank window with
  the chip disabled: the 8SVX sample in sign/magnitude (+127 written as `$FE`,
  since `$FF` is the loop marker; -128 as `$80`), then `$FF $00`. Its silence
  is a 256-byte page of `$80 $FF`.
- Each output change `d` of the PCM chip at tick `t` goes into the buffer at
  `fixed = (t * f + f/2) >> 32` (`f = ceil(2^52 * 44100 / 32552.083)`): sample
  `(fixed >> 20) + 7` gets `d * (32768 - frac)`, the next one `d * frac`,
  `frac = (fixed >> 5) & 0x7fff` (`blip_add_delta_fast`: linear, no sinc).
  `t` counts from the last audio reset. That is exact because a savestate
  restore resets the whole sound system (`state_load` -> `system_reset` ->
  `audio_reset`: buffers cleared, offsets to factor/2, integrators 0). The
  recordings restore a state whenever they set the loser's health
  (`poke_prg`), so a render starts at the last such restore before the WAV,
  with the PCM registers and wave RAM the state held.
- CD-DA: the CD buffer's factor is exactly 2^52, so CD sample n of a frame
  goes to output sample n with a fraction of 1/2. Per sample the fader
  `curVol` steps by one towards its target (register $34 >> 4); the multiplier
  is `curVol & 0x7fc` (`curVol & 3` below 4), `out = sample * mul / 1024` (C
  division); at 0 with a target of 0 the rest of the frame is skipped (the file
  is still read for the whole frame). The JSON names the track and the byte
  offset in its bin file per frame (seeks, pregaps, where track 13 starts: all
  just offsets there).
- Mixing (`blip_mix_samples`): one integrator per side over the three
  buffers: `s = sum >> 15; sum += in; out = clamp(s); sum -= clamp(s) << 6`
  (the high-pass).

## The data and how it was measured

`data/mk_sound/NAME.json` (6-9 KB each, numbers only, plus 4 literal RAM
bytes): `pcm` (the registers at the restore), `ram` (the 64 KB wave RAM:
pieces of samples, partly overwritten ones included, zero runs, the `$80 $FF`
page, the 4 bytes), `events` (137-272: register writes and 2-11 uploads),
`cd` (the fader at the restore, the muted tracks, 47-53 runs of frames),
`skip` / `length` (output samples before the WAV starts / its length) and
`measured` (how it was recorded, frames from the restore to the capture start,
where track 13 starts).

`tools/capture/mksound_measure.patch` adds a log to the core's source: every PCM
register and wave RAM write with its chip tick, the PCM state and RAM at each
state load, and per frame the output samples and the CD track, file offset and
fader. Built as stable-retro builds it, its recordings were identical to the
pinned core's (all nine). `mksound_measure.py` repeats the recording procedure
with it, turns the log into the JSON (it stops on a DMA into the wave RAM,
FM/PSG sound, or a second reset during the capture: none happen) and checks
that the JSON renders the recording exactly.

A render applies an upload all at once at the tick of its first byte (the chip
is disabled while MK uploads, so nothing reads the RAM in between).

## Settled leads

- The Pit scream is the unnamed `SFX2.BIN:3` (19,282 bytes), played with step
  480 (about 7,629 samples/s).
- CD track 12 in the fatality files is real game audio the capture didn't mute
  (after the announcer); three of them also end in track 5.
- The event frames the earlier notes listed per capture are superseded by the
  exact ticks in the JSON files.
