# The tools, by job

Every tool, one line each. The commands are at the top of `tools/`; the library they use is in
`tools/lib/`, and five more folders hold the checks, the MK capture record, developer tools and the
32X support's steps ([maintaining.md](maintaining.md)). Scripts in the subfolders import the library
from `tools/lib/`. Run every tool from the repo root with `.venv/bin/python -P tools/...`; each
one's docstring has its options. `tools/checks/toolsdoccheck.py` (in the suite) fails if a tool has
no line here, or if a line names a tool that isn't there.

## tools/: the commands

What you run: find your discs, make `extracted/` from them, build the disc, play and test it.

| tool | what it does |
|---|---|
| `checkinputs.py` | Are the discs this project needs under roms/, and are they the right dumps? |
| `prepare.py` | Make everything tools/build.py reads, from your own discs: run once on a new machine (after tools/checkinputs.py says the discs are there). |
| `build.py` | Build the Eternal Kombat disc from your own Eternal Champions and MK discs (`--32x`: with the 32X support). |
| `play.py` | Play, script or auto-test a disc under Genesis Plus GX (Sega CD). |

## tools/lib/: the library

### The build's parts

| tool | what it does |
|---|---|
| `patches.py` | Patches applied to the Eternal Champions disc, in order. |
| `inputs.py` | The discs this project reads, and how to find them under roms/. |
| `cdaudio.py` | MK CD's CD audio on the disc (run by build.py before the patches): the menus' Mortal Monday music, the fatality music and cues, the Pit's music and fall, appended to EC's tracks. |
| `disc.py` | Sega CD disc images: cue sheets, raw MODE1/2352 sectors, ISO9660, patching. |
| `build32x.py` | The 32X support, added by `build.py --32x` to the plain disc (`add_32x`): MK CD's portraits on the select screen with a 32X ([32x.md](32x.md)). |
| `extract.py` | Unpack every recognised disc's filesystem to extracted/<id>/ for study. |

### MK's fighters, from your MK disc (run by prepare.py)

| tool | what it does |
|---|---|
| `mkburn.py` | The burning victim of Sonya's MK fatality (the kiss of death), for her art. |
| `mkcapmeta.py` | The number files beside each MK capture (anchors, pose orders, timelines, palette references), kept in data/mk_meta/. |
| `mkdazed.py` | Every MK fighter's own FINISH HIM daze (MK's 7-pose sway), drawn from his art on the MK disc and placed as MK places each frame. |
| `mkfatality.py` | Scorpion's MK fatality (unmask, fire breath, the burning victim), frame by frame. |
| `mkframes.py` | Draw any MK fighter frame by number (docs/research/reproducibility_2026-11.md). |
| `mkfromrecipes.py` | Rebuild MK captures from their recipes in data/mk_recipes/, drawing the frames from your MK disc. |
| `mklair_disc.py` | MK's Goro's Lair (the stage of MK's Shang Tsung fight), decoded from the MK disc's BACKGD6.BIN. |
| `mkpit_disc.py` | Rebuild the MK Pit fight planes and palette from disc data. |
| `mkpitbottom.py` | Extract MK CD's Pit bottom (spikes, heads, impaled body): the scene the Pit fatality scrolls down to when the loser is uppercut off the bridge. |
| `mkportraits_disc.py` | Rebuild the seven select portraits from MK CD's RJC.PRG. |
| `mkshangmoves.py` | Shang Tsung's MK moves as capture folders, drawn straight from MK's EMP.OBJ frames in MK's own order and timing. |
| `mksound_render.py` | MK CD's recorded sounds (the fatality sounds, the Pit fall) rendered from your MK disc without the emulator, byte for byte as recorded (`--check`). |

### Emulator and playing

| tool | what it does |
|---|---|
| `pico.py` | PicoDrive (a Sega CD with a 32X) as scd.py's Core, for the 32X checks. |
| `scd.py` | Minimal libretro front-end for Genesis Plus GX: Sega CD, scriptable. |
| `vdp.py` | Read the Genesis VDP out of a Genesis Plus GX savestate and render it. |
| `duelstate.py` | Make build/states/duel.state: a 2-player Duel (player 2 standing still), saved the moment player 1 can move. |
| `cpuregs.py` | Both 68000s' registers, read from the Genesis Plus GX core itself (a debugging aid). |
| `watchwrite.py` | Who writes a sub-CPU word? |

### The game's code and art (used by build.py) and their helpers

| tool | what it does |
|---|---|
| `ecdeath.py` | EC's per-fighter death art (Z<xx>.BIN, loaded by stage Sudden Deaths), read and drawn as contact sheets. |
| `ecpl.py` | Write Eternal Champions CD fighter sprite data (.PL) and frame records. |
| `ecpl2.py` | EC .PL art banks: an optimal (dynamic-programming) parse over every opcode family of EC's unpacker (SUB.BIN $11784), with the dictionary chosen by measured use. |
| `ecprobe.py` | Record which sheet frames an EC fighter uses for each action, by playing the actions in a 2-player duel. |
| `ecstage.py` | Eternal Champions CD stages: read, render and build NAME.BG / NAME.BGI. |
| `ectitle.py` | The title screen's logo says ETERNAL KOMBAT: EC's own letters rearranged in the title picture's tiles (GAME.DAT) and four spare palette slots (GAME.CO); --preview, --measure (the plane's map, data/ec_title/). |
| `ecunpack.py` | Run EC's own unpacker (SUB.BIN $11784) on a .PL resource, whole frame at once (d6 bit 6 = no yield). |
| `finishvideo.py` | Record Scorpion's FINISH HIM -> fatality as a shareable clip (with sound). |
| `mkcompare.py` | How close is one of our MK fighter's actions to MK's own, frame by frame? |
| `mkdeath.py` | An MK fighter's EC death art: a Z<xx>.BIN in EC's layout, drawn from MK. |
| `mkendings.py` | MK CD's endings (the story after beating Shang Tsung) for EC's ending scroller (patches.mk_endings). |
| `mkfatality_capture.py` | Capture an MK CD fatality from the user's MK disc: the winner (palette line 0) and the victim (line 1), each indexed in his own palette, frame by frame. |
| `mkfatality_subzero.py` | Capture Sub-Zero's MK fatality (the spine rip) from the MK disc, frame by frame. |
| `mkfatalitycheck.py` | End-to-end check of an MK fighter's fatality in a real 2-player duel, on any opponent: FINISH HIM, the input, the finisher, no freeze. |
| `mkfatalsound.py` | Record the sound effects of MK CD's Sub-Zero spine rip, from the user's MK disc, lined up with MK's fatality music (CD track 13). |
| `mkinputs.py` | The MK fighters' behaviour in Eternal Champions, as 68000 code: inputs, specials, voice, CPU. |
| `mkmoves.py` | Capture a fighter's MK poses action by action, from a 2-player MK match where player 2 stands still (build/states/mk_2p.state: Scorpion vs Sub-Zero). |
| `mkpalettes.py` | Read the fight palettes used by mk_meta directly from MK CD's PAC.PRG. |
| `mkpitsound.py` | Record MK CD's own Pit fall soundtrack (the uppercut off the bridge), from the user's MK disc. |
| `mkportrait.py` | Capture Scorpion's portrait from MK's character-select screen (build/states/mk_select.state) into extracted/mk_moves/portrait.png (RGB, native pixels). |
| `mkprojectile.py` | MK projectiles as EC effect art: the flying part of an MK special (Raiden's lightning ball, Sub-Zero's ice, Johnny's green bolt), cut out of the MK capture. |
| `mkrecipes.py` | MK captures as recipes (docs/research/reproducibility_2026-11.md): the MK frames drawn into each captured pose, as numbers. |
| `mksch.py` | Decode MK Sega CD fighter frames directly from a fighter's OBJ/SCH files. |
| `mkscripts.py` | MK's own animation for the MK fighters' basic attacks. |
| `mksfx.py` | Read MK Sega CD's 8SVX sound samples directly from its disc. |
| `mkshang.py` | MK's Shang Tsung (EMP.OBJ/EMP.SCH) as the art of EC's Eternal Champion, both forms (fighters 11 and 26). |
| `mkshangref.py` | MK CD's own Shang Tsung fight, as the reference for ours: which of his EMP frames MK shows, for how long and how he moves, action by action. |
| `mkspine_disc.py` | Extract Sub-Zero fatality sprite pieces directly from MK CD's PAC.PRG. |
| `mkstage.py` | Dump an MK stage's background layers (VDP planes A and B, the palettes) from a fight state on the MK disc. |
| `overkillvideo.py` | Record EC's Chicago Theater stage Overkill (the drive-by) on Scorpion. |
| `plmap.py` | Which bytes of an EC .PL file each compressed frame reads. |
| `plsheet.py` | Every pose of an EC fighter art file (.PL) on one contact sheet, labelled SHEET:FRAME. |
| `scorpion_full.py` | Rebuild all of Blade's compressed sprite art (BLA.PL sheets $40-$43) as an MK fighter, from his MK poses. |
| `scorpion_map.py` | Which MK pose stands in for each of Blade's poses. |
| `throwsim.py` | EC's throw, simulated: where the victim is after each step (PLYR's step loop $19124, the victim's state $37 at $17EB8; docs/notes/2026-11.md "EC's throw step loop"). |
| `usherdeath.py` | Play the Chicago Theater's Sudden Death (the usher's shotgun) on a loser and trace the death object's frames. |
| `vendettacheck.py` | Play an EC fighter's Vendetta on an MK loser and save a frame strip. |

## tools/checks/: the suite

Run after a build. `allchecks.py` runs them all (and a few library tools with `--check`); each writes ok or FAIL.

| tool | what it does |
|---|---|
| `airspearcheck.py` | Scorpion's spear on a jumping Kano must not hang the game. |
| `allchecks.py` | Every check, for every MK fighter, on the current build (run after tools/build.py; it starts with the test suite, which boots the new disc and re-saves build/states/menu.state). |
| `backkickcheck.py` | MK fighters' back + B is the roundhouse and back + A the sweep (as MK CD's away + kick), both sides; C, down + C, A, B as before; Sub-Zero's slide; a CPU fight unchanged. |
| `blockcheck.py` | Does Z block for an MK fighter? |
| `contestcheck.py` | One-player Contest (the ladder) with a fighter: does it run from match to match without freezing? |
| `dazecheck.py` | An MK fighter's FINISH HIM daze: MK's 7-pose sway (mkinputs.DAZE_FRAMES at MK's timing, DAZE_SEQ: ~10 frames a pose, looped). |
| `deadscriptcheck.py` | MK fighters in random fights: a fighter's running script is never one of Blade's that his block replaces (the build keeps code in their bodies). |
| `eitherpunchcheck.py` | The MK specials that name a punch come out with X and with Y (as on MK CD), each fighter's other specials, punches and uppercuts as before, on both sides; the CPU's fighter reads none of it. |
| `feetcheck.py` | MK's FEETLAND once at each landing of a jump (forward, straight up and back), never while walking. |
| `fightcheck.py` | Does a fight run without freezing? |
| `finishercheck.py` | Unit-test the built disc's finisher checks for MK losers (Cinekill, stage Sudden Death) on a 68000 under unicorn. |
| `finishmusiccheck.py` | An unfinished FINISH HIM must not run into the fatality music. |
| `flykickcheck.py` | Liu Kang's flying kick (forward, forward + HK): travelling within 6 frames of HK and kicking within 10, as MK's (it stood 12 frames first). |
| `gruntcheck.py` | MK's grunts: an MK fighter grunts once as he leaves the floor on a jump; punches, kicks and EC fighters don't. |
| `icecheck.py` | Sub-Zero's ice blast freezes, and a blocked one doesn't (as on MK CD). |
| `jumpcheck.py` | MK's jumps (patches.mk_jump_height, mkinputs.jump_up_launch): straight up as long in the air as MK's, forward / back at EC's gravity and MK's height, a jump kick lands with the jump. |
| `kanoballcheck.py` | Kano's cannonball on MK CD's full circle (toward, down, away, up; Block held or not), not on three of the taps or another order; his knife only with Block held; both sides; the CPU's Kano never runs the recogniser. |
| `kanoheadcheck.py` | Check Kano's close punches in a real duel on either player side. |
| `kanoknifecheck.py` | Check Kano's held-Block knife input on either player side. |
| `kickthrowcheck.py` | MK fighters throw with B (the high kick) up close, as MK CD, on both sides; toward + Y still throws; C, A, down + B don't; the CPU's fighters never run the code. |
| `leggrabcheck.py` | Sonya's leg grab (MK CD: down + LP + LK + Block, close; here down + X + A + Z). |
| `licensecheck.py` | Every tracked Python file has the MIT licence tag (SPDX) and LICENSE is there. |
| `menumusiccheck.py` | The title left alone (4 min 55 s, until EC's intro video): EC's song, then MK's Mortal Monday music (MK CD track 20), never the fight cues after them on the track. |
| `pitcheck.py` | Does the Pit's fall work for every pairing? |
| `pitstartcheck.py` | Reptile's fight starts on the Pit's bottom (never a frame on the bridge with him there); a plain Pit fight stays on the bridge. |
| `poolcheck.py` | No free effect object (patches.ec_object_pool): with EC's free count held at 0, fighters trade hits for 400 frames and the sub CPU and object list survive. |
| `reptilecheck.py` | Reptile (fighter 26, MK's secret) in a duel against Kano on the Pit's bottom: his ice blast, slide and spear. |
| `roundendcheck.py` | Does every knockout lead to the next round? |
| `shadowkickcheck.py` | Check Johnny's shadow-kick pose, overflow object, hit and cleanup. |
| `shangcheck.py` | Shang Tsung (fighter 11, the Contest's first boss) against MK's own Shang (tools/lib/mkshangref.py, docs/notes/2026-11.md). |
| `soakcheck.py` | A long fight that must never freeze: Kano jumps in at the CPU's Reptile on the Pit, both healths kept full. |
| `sonyainputcheck.py` | Sonya's specials from the pad, both sides: forward held + HP punches (not the square wave), forward, back + HP flies, HP, back, a punch throws the rings (MK CD's; back + HP alone doesn't), close forward + HP throws; the CPU's Sonya never runs the recogniser. |
| `soundbankcheck.py` | Do the fight's sound banks load whole? |
| `spearcheck.py` | The spear from near to its full reach: Scorpion's and Reptile's pull the victim in and daze him inside EC's hit stun; Scorpion's rope holds 20+ frames. |
| `spearsoundcheck.py` | Does the spear sound as MK's? |
| `splitpunchcheck.py` | Johnny Cage's split punch is down + B (MK CD's down + high kick) and his down + Z blocks, on both sides; the rest of his crouch and the others' down + B as before; the CPU's Johnny never runs the code. |
| `squarewavecheck.py` | Sonya's square wave at MK's height: over a standing opponent, into a jumping one. |
| `sweepcheck.py` | Each MK fighter's sweep (crouch, down + C) on Larcen: he falls where he stands (MK), not launched ~135 px (EC). |
| `teleportcheck.py` | Exercise Raiden's teleport and Scorpion's teleport punch on either side. |
| `throwfinishcheck.py` | A throw that would win the match leaves the loser dazed on FINISH HIM (patches.throw_finish), not knocked out. |
| `tintcheck.py` | Riptide's bubble on Kano: his palette fades to an even tint (no red slots, his own tint palettes, not Blade's) and his own colours come back. |
| `titlecheck.py` | The title screen and main menu say ETERNAL KOMBAT: plane B is ectitle.py's picture pixel for pixel, EC's everywhere else, with the glow's four reds in palette line 2. |
| `toolsdoccheck.py` | Every tool has its line in docs/tools.md, and every tool named there exists. |
| `versuscheck.py` | Reptile's versus portrait (patches.reptile_portrait): Sub-Zero's picture with his blues turned green, on either side; Shang's his own. |
| `x32check.py` | The 32X support with a 32X (PicoDrive) and without (Genesis Plus GX): warning screen, the MK portraits, a fight, back to select (allchecks runs the route without a 32X on the standard disc; the gate runs the whole check on the `--32x` disc). |

## tools/capture/: how the MK data was measured

Captures and measurements on the user's MK disc that made `data/` (recipes, sounds, states). Not run by prepare.py: kept as the record, and to redo a measurement.

| tool | what it does |
|---|---|
| `mkdizzy.py` | Capture Scorpion's MK dazed pose (FINISH HIM, as the loser) and his lying pose from the MK disc. |
| `mkduelstate.py` | Make an MK 2-player fight state for capturing a fighter's moves (tools/lib/mkmoves.py --fighter=...), from build/states/mk_select.state. |
| `mkfataltrial.py` | Find an MK CD fatality's input by trying candidates, each matched against the start of MK's fatality music (CD track 13). |
| `mkmovesounds.py` | Which MK CD samples does each move play, and when? |
| `mkpitstate.py` | Make build/states/mk_pit_raw.state: Kano vs Kano at the start of a fight on MK's Pit, where the Pit tools start. |
| `mkreptileref.py` | MK CD's own Reptile fight, as the reference for ours. |
| `mksch_probe.py` | Locate an MK fighter's untouched .SCH bytes in a live fight state. |
| `mkselectstate.py` | Make build/states/mk_select.state from a cold boot of the user's MK CD (US): the character-select screen every MK capture starts from (tools/capture/mkduelstate.py). |
| `mksound_measure.py` | Measure what MK does with its sound chip and CD drive during each recording tools/lib/mksound_render.py reproduces, into data/mk_sound/NAME.json. |
| `mksound_probe.py` | Find an MK disc sample in a recorded fatality WAV (research only). |
| `mkunclip.py` | MK captures whose frames ran off MK's screen, put back whole (data/mk_recipes, data/mk_meta). |
| `mkvictim.py` | Capture the victim of MK CD's Sub-Zero spine rip (the headless body), indexed in his own palette, for his EC death art. |
| `mkvideo.py` | Record MK CD itself (with sound) as a reference clip for a move, to set beside Eternal Kombat's version. |
| `umk3toasty.py` | Capture the "Toasty!" easter egg (Dan Forden's face + voice) from Ultimate Mortal Kombat 3 (USA, Genesis) into extracted/umk3_toasty/. |

## tools/dev/: inspecting, recording, auditing

For developers: disassembly, sprite and frame inspection, videos, audits, and `verify_fresh.py` (the release gate).

| tool | what it does |
|---|---|
| `animaudit.py` | Where do our MK fighters lose MK's animation? |
| `blastfinisher.py` | Blast's stage finishers recorded with sound: the Overkill (the gunship) or the Sudden Death (the watchtower gunner). |
| `buildreads.py` | Which captured poses does the build read? |
| `clean.py` | What's in the ignored output folders (build/, build/shots/, build/runs/, build/states/, build/saves/), and deleting only what you name. |
| `ecdis.py` | Disassembler for Eternal Champions CD sub-CPU modules (.CO .OC .AI .BGI). |
| `ecdraw.py` | Render any Eternal Champions fighter pose exactly, by running the game's own sprite routine (SUB.BIN $F85C) on a savestate's memory under unicorn. |
| `ecsprite.py` | Decode Eternal Champions CD fighter sprite frames (.PL) by running the game's own unpacker from SUB.BIN under a 68000 emulator (unicorn). |
| `finisherreel.py` | Compilation videos of the finishers, MK against EC and back, each clip after a title card. |
| `hitaudit.py` | How does an MK fighter take a hit? |
| `hitmatrix.py` | Do the MK fighters' attacks connect like Blade's (whose moves and hit data they use), and do EC fighters' attacks connect on the MK fighters like on Blade? |
| `inputaudit.py` | What does each direction + button do for our MK fighters? |
| `lineup.py` | Every fighter standing side by side, as the game draws them, to judge the MK fighters' size against EC's. |
| `movestrip.py` | Real frames of one move, enlarged side by side: an MK fighter against a standing opponent, each frame labelled. |
| `pitvideo.py` | Record the Pit finisher (with sound): the uppercut off the bridge and the fall. |
| `record.py` | Record a video (with sound) of the game from a savestate. |
| `showcase.py` | Record a shareable clip of Scorpion's moves against Shadow (with sound). |
| `stageaudit.py` | Every stage's round end, Overkill and Sudden Death with each MK fighter as the loser against Shadow: pictures only the MK loser's run draws, a different finisher, a frozen picture. |
| `stagevideo.py` | Record a stage's Overkill or Sudden Death on an MK loser (the spot found by walking him along the stage), with sound. |
| `throwcmp.py` | MK's throws beside ours: recorded with sound, each fighter's sprite box per frame, the victim's path, comparison sheets. |
| `trailer.py` | A one-minute trailer of the built disc cut to MK CD's Mortal Monday music: title, select screen, specials, fatalities, stage finishers, the Pit. |
| `verify_fresh.py` | Does a fresh clone build exactly this disc? |
| `victimtables.py` | Find EC's per-victim pose tables: tables with an entry per victim id 2-24 holding frame words in THAT victim's sheets. |

## tools/x32/: the 32X support's steps

Run by `tools/lib/build32x.py` (from `tools/build.py --32x`; [32x.md](32x.md)): five steps in order
(`32x_art_probe.py`, `32x_cd_roster_preview.py`, `32x_select_payload_probe.py`,
`32x_repair_experiment.py`, `32x_reentry.py`); the other six are modules those steps import. The
descriptions are the scripts' own, from when each was a separate experiment.

| tool | what it does |
|---|---|
| `32x_art_probe.py` | Step 1: 32X detection hooked into MAIN.BIN's startup (first written as a drawing experiment with an MK CD portrait). |
| `32x_cd_roster_preview.py` | Step 2: the seven MK portraits packed for the 32X framebuffer, with one shared palette. |
| `32x_cursor_live_hook.py` | Experimental live Scorpion-slot 32X cursor renderer (used by 32x_cursor_roster_hook.py). |
| `32x_cursor_overwrite_assets.py` | Prepare EC cursor sprites for 32X overwrite-image word writes. |
| `32x_cursor_roster_hook.py` | The seven-slot 68000 32X cursor renderer. |
| `32x_ec_cursor_assets.py` | Extract the four EC select-cursor pictures from your EC disc. |
| `32x_repair_experiment.py` | Step 4: the startup reduced to detection; the VBlank call handed back to EC's as select exits; the 32X layer enabled once select is ready. |
| `32x_reentry.py` | Step 5: the 32X portraits on every visit to the select screen, not just the first. |
| `32x_select_incremental_hook.py` | The incremental 68000 select renderer (its set-up spread over VBlanks). |
| `32x_select_incremental_transfer.py` | Chunked Sega CD PRG-RAM to 32X transfer, at most 512 bytes a VBlank. |
| `32x_select_payload_probe.py` | Step 3: the 32X select-screen payload appended to GAME.CO. |
