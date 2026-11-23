#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""EC's select-cursor frames for the 32X (FRAMES), and the one-slot cursor renderer before them.

32x_cursor_roster_hook.py takes FRAMES (each cursor tile's offsets in the cursor pixels). code()
is the earlier renderer for Scorpion's slot alone: it restores his portrait and draws EC's sprite
entries 2 and 3 when their cursor is inside that slot (its synthetic pad pulses: emulator tests
only). The build doesn't use it.
"""

# (the library: tools/lib/)
import sys as _research_sys
from pathlib import Path as _ResearchPath
_research_sys.path.insert(0, str(_ResearchPath(__file__).resolve().parent.parent / 'lib'))
from mkinputs import Asm

# tile, normal-even, normal-odd, 180-degree-even, 180-degree-odd offsets
FRAMES=[(898,0,256,544,800),(902,1088,1344,1632,1888),(976,2176,2432,2720,2976),(980,3264,3520,3808,4064)]

def code(cave=0x6900,marker=0xff6e00,stage=0x85b000,cursors=0x85e000,drive_pad=False,drive_two_pads=False):
 if drive_two_pads and not drive_pad:raise ValueError('two-pad test requires synthetic pad driver')
 a=Asm(cave);a.w(0x4eb9);a.l(0xff1540);a.w(0x40e7)
 # Preserve d0-d7 and a0-a2, in addition to the caller's original registers.
 for r in range(8):a.w(0x2f00+r)
 for r in range(3):a.w(0x2f08+r)
 a.w(0x4a39);a.l(marker);a.bccw(0x67,'done')
 if drive_pad:
  # Synthetic controller pulses exercise EC's own selection code in the test.
  # Suppress the headless host's automatic Start so selection stays open.
  a.w(0x3039);a.l(marker+4);a.w(0x5240,0x33c0);a.l(marker+4)
  a.w(0x0c40,320);a.bccw(0x64,'padidle') # 20 right presses, then stop
  a.w(0x0240,15,0x0c40,3);a.bccw(0x64,'padidle')
  a.w(0x33fc,0xf008);a.l(0xfffce8);a.bccw(0x60,'paddone')
  a.label('padidle');a.w(0x33fc,0xf000);a.l(0xfffce8);a.label('paddone')
  if drive_two_pads:
   a.w(0x3039);a.l(marker+4);a.w(0x0c40,80);a.bccw(0x65,'p2idle')
   a.w(0x0c40,88);a.bccw(0x65,'p2join');a.w(0x0c40,112);a.bccw(0x65,'p2idle');a.w(0x0c40,432);a.bccw(0x64,'p2idle')
   a.w(0x0440,112,0x0240,15,0x0c40,3);a.bccw(0x64,'p2idle')
   a.w(0x33fc,0xf008);a.l(0xfffce6);a.bccw(0x60,'p2done')
   a.label('p2join');a.w(0x33fc,0xf080);a.l(0xfffce6);a.bccw(0x60,'p2done')
   a.label('p2idle');a.w(0x33fc,0xf000);a.l(0xfffce6);a.label('p2done')
 # Record the exact main-CPU SAT entries used by this experimental update.
 a.w(0x41f9);a.l(0xfff622);a.w(0x43f9);a.l(marker+8);a.w(0x22d8,0x22d8,0x22d8,0x22d8)
 # Restore the clean Scorpion portrait in the hidden buffer.
 a.w(0x41f9);a.l(stage+8+512+6*(4+1536)+4);a.w(0x43f9);a.l(0x840200+320+(144-96)*320+224)
 a.w(0x323c,47);a.label('restore_row');a.w(0x303c,7);a.label('restore_word');a.w(0x22d8);a.dbra(0,'restore_word');a.w(0xd2fc,288);a.dbra(1,'restore_row')
 # Later SAT entries draw first; earlier entries take priority on overlap.
 a.w(0x45f9);a.l(0xfff62a);a.bccw(0x61,'draw')
 a.w(0x45f9);a.l(0xfff622);a.bccw(0x61,'draw')
 a.w(0x1039);a.l(0xa1518b);a.w(0x0200,1,0x0a00,1,0x13c0);a.l(0xa1518b)
 a.w(0x5239);a.l(marker+1);a.bccw(0x60,'done')
 a.label('draw')
 # Only the two jitter positions normally observed in Scorpion's slot.
 a.w(0x3412,0x0242,0x03ff,0x0c42,288);a.bccw(0x67,'yok');a.w(0x0c42,289);a.bccw(0x66,'ret')
 a.label('yok');a.w(0x362a,6,0x0243,0x01ff,0x0c43,359);a.bccw(0x67,'xok');a.w(0x0c43,360);a.bccw(0x66,'ret')
 a.label('xok');a.w(0x382a,4,0x0244,0x1fff)
 for tile,even,odd,rot_even,rot_odd in FRAMES:
  for flip,off_even,off_odd in ((0,even,odd),(0x1800,rot_even,rot_odd)):
   a.w(0x0c44,tile|flip);a.bccw(0x67,f'src_{tile}_{flip}')
 a.bccw(0x60,'ret')
 for tile,even,odd,rot_even,rot_odd in FRAMES:
  for flip,off_even,off_odd in ((0,even,odd),(0x1800,rot_even,rot_odd)):
   label=f'src_{tile}_{flip}';a.label(label);a.w(0x0803,0);a.bccw(0x66,label+'_odd')
   a.w(0x41f9);a.l(cursors+off_even);a.w(0x7c07,0x3e3c,304);a.bccw(0x60,'draw_pixels')
   a.label(label+'_odd');a.w(0x41f9);a.l(cursors+off_odd);a.w(0x7c08,0x3e3c,302);a.bccw(0x60,'draw_pixels')
 a.label('draw_pixels')
 # Convert SAT screen coordinates to the 32X overwrite-image address.
 a.w(0x0442,128+96,0xc4fc,320,0x0443,128,0x0243,0xfffe,0xd443)
 a.w(0x43f9);a.l(0x860200+320);a.w(0xd2c2,0x323c,15)
 a.label('row');a.w(0x3006);a.label('word');a.w(0x32d8);a.dbra(0,'word');a.w(0xd2c7);a.dbra(1,'row')
 a.w(0x5239);a.l(marker+2)  # number of markers drawn, debugger telemetry
 a.label('ret');a.w(0x4e75)
 a.label('done')
 a.w(0x245f,0x225f,0x205f)
 for r in range(7,-1,-1):a.w(0x201f+(r<<9))
 a.w(0x44df,0x4e75)
 return a.build()
