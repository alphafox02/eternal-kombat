#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The 32X cursor hook: EC's select cursors drawn over the seven MK portraits (68000 code).

Built by 32x_select_payload_probe.py into the payload. Each VBlank it restores, in the hidden
32X buffer, the portraits a cursor marked, and draws EC's cursor sprites over them from their
pre-expanded variants; on EC's larger confirmation sprites it shows the plain Genesis screen
(fallback_confirmation). Its synthetic pad pulses are for emulator tests only (off in the build).
Emulator-tested only (docs/32x.md).
"""

# (the library: tools/lib/)
import sys as _research_sys
from pathlib import Path as _ResearchPath
_research_sys.path.insert(0, str(_ResearchPath(__file__).resolve().parent.parent / 'lib'))
from mkinputs import Asm
from importlib import import_module
source=import_module('32x_cursor_live_hook')
ROSTER=[(32,96),(64,144),(96,144),(128,144),(160,144),(192,144),(224,144)]

def code(cave=0x6900,marker=0xff7400,stage=0x85b000,cursors=0x85e000,drive_two_pads=False,confirmation_variants=None,timing_control=False,confirmation_slot=160,exit_test=False,confirmation_start=350,guard_screen=False,share_p1_masks=False,fallback_confirmation=False,input_confirmation=False,fallback_report_mode=True):
 if (confirmation_variants or input_confirmation) and confirmation_slot not in (32,64,96,128,160,192,224):raise ValueError('unsupported experimental confirmation slot')
 a=Asm(cave);a.w(0x4eb9);a.l(0xff1540);a.w(0x40e7)
 for r in range(8):a.w(0x2f00+r)
 for r in range(4):a.w(0x2f08+r)
 if not input_confirmation:
  a.w(0x4a39);a.l(marker);a.bccw(0x67,'done')
 if guard_screen:
  for addr,val in ((0xfff59e,120),(0xfff5a0,81),(0xfff8f0,0x0ec6)):
   a.w(0x0c79,val);a.l(addr);a.bccw(0x66,'cursor_hide')
 if drive_two_pads:
  # These synthetic pad pulses are exclusively for the isolated emulator test.
  a.w(0x3039);a.l(marker+4);a.w(0x5240,0x33c0);a.l(marker+4)
  if input_confirmation:
   a.w(0x0c40,confirmation_start);a.bccw(0x66,'p1move');a.w(0x33fc,0xf080);a.l(0xfffce8);a.bccw(0x60,'p1done');a.label('p1move')
  elif confirmation_variants:
   a.w(0x0c40,confirmation_start);a.bccw(0x65,'p1move');a.w(0x0c40,confirmation_start+8);a.bccw(0x64,'p1idle');a.w(0x33fc,0xf080);a.l(0xfffce8);a.bccw(0x60,'p1done');a.label('p1move')
  a.w(0x0c40,(104 if confirmation_slot==32 else 248+(confirmation_slot-96)//2) if (confirmation_variants or input_confirmation) else 320);a.bccw(0x64,'p1idle');a.w(0x0240,15,0x0c40,3);a.bccw(0x64,'p1idle')
  a.w(0x33fc,0xf008);a.l(0xfffce8);a.bccw(0x60,'p1done');a.label('p1idle');a.w(0x33fc,0xf000);a.l(0xfffce8);a.label('p1done')
  if exit_test:
   a.w(0x3039);a.l(marker+4);a.w(0x0c40,80);a.bccw(0x65,'exit_p2idle');a.w(0x0c40,88);a.bccw(0x65,'exit_p2start')
   a.w(0x0c40,112);a.bccw(0x65,'exit_p2idle');a.w(0x0c40,392);a.bccw(0x65,'exit_p2move')
   a.w(0x0c40,430);a.bccw(0x65,'exit_p2idle');a.w(0x0c40,438);a.bccw(0x65,'exit_p2start');a.bccw(0x60,'exit_p2idle')
   a.label('exit_p2move');a.w(0x0440,112,0x0240,15,0x0c40,3);a.bccw(0x64,'exit_p2idle');a.w(0x33fc,0xf008);a.l(0xfffce6);a.bccw(0x60,'exit_p2done')
   a.label('exit_p2start');a.w(0x33fc,0xf080);a.l(0xfffce6);a.bccw(0x60,'exit_p2done')
   a.label('exit_p2idle');a.w(0x33fc,0xf000);a.l(0xfffce6);a.label('exit_p2done')
  elif input_confirmation:
   pass # single-player test; no P2 input is supplied
  elif confirmation_variants:
   a.w(0x33fc,0xf000);a.l(0xfffce6)
  else:
   a.w(0x3039);a.l(marker+4);a.w(0x0c40,80);a.bccw(0x65,'p2idle');a.w(0x0c40,88);a.bccw(0x65,'p2join');a.w(0x0c40,112);a.bccw(0x65,'p2idle');a.w(0x0c40,432);a.bccw(0x64,'p2idle')
   a.w(0x0440,112,0x0240,15,0x0c40,3);a.bccw(0x64,'p2idle');a.w(0x33fc,0xf008);a.l(0xfffce6);a.bccw(0x60,'p2done')
   a.label('p2join');a.w(0x33fc,0xf080);a.l(0xfffce6);a.bccw(0x60,'p2done');a.label('p2idle');a.w(0x33fc,0xf000);a.l(0xfffce6);a.label('p2done')
 if exit_test:
  for addr,val in ((0xfff59e,120),(0xfff5a0,81),(0xfff8f0,0x0ec6)):
   a.w(0x0c79,val);a.l(addr);a.bccw(0x66,'exit_hide')
 if fallback_confirmation:
  # During EC's larger confirmation sprites, reveal the ordinary Genesis
  # screen. Wait for two completed marker updates before re-enabling 32X.
  for entry in (0xfff622,0xfff62a):
   a.w(0x3039);a.l(entry);a.w(0x0240,0x03ff,0x0c40,128);a.bccw(0x65,f'fallback_next{entry}')
   a.w(0x3039);a.l(entry+4);a.w(0x0240,0x07ff)
   for tile in (906,910,922,938,947,963):a.w(0x0c40,tile);a.bccw(0x67,'fallback_hide')
   a.label(f'fallback_next{entry}')
  a.w(0x4a39);a.l(marker+28);a.bccw(0x67,'fallback_done')
  a.w(0x5239);a.l(marker+28);a.w(0x0c39,4);a.l(marker+28);a.bccw(0x66,'fallback_done')
  a.w(0x4239);a.l(marker+28);a.w(0x13fc,0x81);a.l(0xa15181)
  if fallback_report_mode:a.w(0x1039);a.l(0xa15181);a.w(0x13c0);a.l(marker+29)
  a.bccw(0x60,'fallback_done')
  a.label('fallback_hide');a.w(0x13fc,1);a.l(marker+28);a.w(0x13fc,0);a.l(0xa15181)
  if fallback_report_mode:a.w(0x1039);a.l(0xa15181);a.w(0x13c0);a.l(marker+29)
  a.label('fallback_done')
 # Capture exact SAT input for later debugger verification.
 a.w(0x41f9);a.l(0xfff622);a.w(0x43f9);a.l(marker+8);a.w(0x22d8,0x22d8,0x22d8,0x22d8)
 if timing_control:
  a.w(0x5239);a.l(marker+1);a.bccw(0x60,'done')
 # Select a dirty-mask byte based on the current front-buffer bit. The mapping
 # need only remain consistent: it identifies the opposite/hidden buffer.
 a.w(0x47f9);a.l(marker+25);a.w(0x1039);a.l(0xa1518b);a.w(0x0200,1);a.bccw(0x67,'mask_ready');a.w(0x528b);a.label('mask_ready')
 a.w(0x7a00,0x1a13,0x4213)       # moveq #0,d5; move.b (a3),d5; clr.b (a3)
 for i,(x,y) in enumerate(ROSTER):
  a.w(0x0805,i);a.bccw(0x67,f'restored{i}')
  a.w(0x41f9);a.l(stage+8+512+i*(4+1536)+4);a.w(0x43f9);a.l(0x840200+320+(y-96)*320+x)
  a.w(0x323c,47);a.label(f'restore_row{i}');a.w(0x303c,7);a.label(f'restore_word{i}');a.w(0x22d8);a.dbra(0,f'restore_word{i}');a.w(0xd2fc,288);a.dbra(1,f'restore_row{i}')
  a.label(f'restored{i}')
 a.w(0x45f9);a.l(0xfff62a);a.bccw(0x61,'draw')
 a.w(0x45f9);a.l(0xfff622);a.bccw(0x61,'draw')
 a.w(0x1039);a.l(0xa1518b);a.w(0x0200,1,0x0a00,1,0x13c0);a.l(0xa1518b)
 a.w(0x5239);a.l(marker+1);a.bccw(0x60,'done')
 a.label('draw');a.w(0x3412,0x0242,0x03ff,0x362a,6,0x0243,0x01ff)
 if confirmation_variants:
  a.w(0x382a,4,0x0244,0x1fff)
  # Clip each observed sprite to the MK portrait strip. The 32X background
  # is transparent outside these rectangles and must not be overwritten.
  confirm_sources={}
  metadata={v['tile']:v for v in confirmation_variants}
  for i,(sx,sy) in enumerate(ROSTER):
   left_bound,right_bound=(32,64) if i==0 else (64,256)
   dirty_mask=1 if i==0 else (6 if i==1 else (0x60 if i==6 else 7<<(i-1)))
   for tile,dx,dy in ((906,5,13),(910,-4,7),(922,-7,4),(938,25,4),(947,-8,1),(963,24,1)):
    x=sx+dx;y=sy+dy;v=metadata[tile];start=x&~1
    left=max(0,left_bound-start);right=max(0,start+v['width']-right_bound)
    if left%2 or right%2 or left+right>=v['width']:raise ValueError('unsupported sprite clipping')
    key=(tile,left,right);confirm_sources[key]=v
    label=f'confirm_next{i}_{tile}'
    a.w(0x0c44,tile);a.bccw(0x66,label);a.w(0x0c42,y+128);a.bccw(0x66,label);a.w(0x0c43,x+128);a.bccw(0x66,label);a.w(0x0013,dirty_mask);a.bccw(0x60,f'confirm_src{tile}_{left}_{right}');a.label(label)
 for i,(x,y) in enumerate(ROSTER):
  a.w(0x0c42,y+144);a.bccw(0x67,f'yok{i}');a.w(0x0c42,y+145);a.bccw(0x66,f'next{i}')
  a.label(f'yok{i}');a.w(0x0c43,x+135);a.bccw(0x67,f'slot{i}');a.w(0x0c43,x+136);a.bccw(0x66,f'next{i}')
  a.label(f'slot{i}');a.w(0x0013,1<<i);a.bccw(0x60,'slot_found');a.label(f'next{i}')
 a.bccw(0x60,'ret')
 a.label('slot_found');a.w(0x382a,4,0x0244,0x1fff)
 for tile,even,odd,rot_even,rot_odd in source.FRAMES:
  if (confirmation_variants or share_p1_masks) and tile in (976,980):even-=2176;odd-=2176;rot_even-=2176;rot_odd-=2176
  for flip,off_even,off_odd in ((0,even,odd),(0x1800,rot_even,rot_odd)):
   a.w(0x0c44,tile|flip);a.bccw(0x67,f'src_{tile}_{flip}')
 a.bccw(0x60,'ret')
 for tile,even,odd,rot_even,rot_odd in source.FRAMES:
  if (confirmation_variants or share_p1_masks) and tile in (976,980):even-=2176;odd-=2176;rot_even-=2176;rot_odd-=2176
  for flip,off_even,off_odd in ((0,even,odd),(0x1800,rot_even,rot_odd)):
   label=f'src_{tile}_{flip}';a.label(label);a.w(0x0803,0);a.bccw(0x66,label+'_odd')
   a.w(0x41f9);a.l(cursors+off_even);a.w(0x7c07,0x3e3c,304,0x7800,0x323c,15);a.bccw(0x60,'draw_pixels')
   a.label(label+'_odd');a.w(0x41f9);a.l(cursors+off_odd);a.w(0x7c08,0x3e3c,302,0x7800,0x323c,15);a.bccw(0x60,'draw_pixels')
 if confirmation_variants:
  for (tile,left,right),v in confirm_sources.items():
   width=v['width']-left-right
   a.label(f'confirm_src{tile}_{left}_{right}');a.w(0x41f9);a.l(cursors+v['offset']+left)
   if left:a.w(0x0643,left) # shift destination to the clipped left edge
   a.w(0x3c3c,width//2-1,0x3e3c,320-width,0x383c,left+right,0x323c,v['height']-1);a.bccw(0x60,'draw_pixels')
 a.label('draw_pixels');a.w(0x0442,128+96,0xc4fc,320,0x0443,128,0x0243,0xfffe,0xd443)
 a.w(0x43f9);a.l(0x860200+320);a.w(0xd2c2);a.label('row');a.w(0x3006);a.label('word');a.w(0x32d8);a.dbra(0,'word');a.w(0xd2c7,0xd0c4);a.dbra(1,'row')
 a.w(0x5239);a.l(marker+2);a.label('ret');a.w(0x4e75)
 if guard_screen:
  a.label('cursor_hide');a.w(0x13fc,0);a.l(0xa15181);a.w(0x1039);a.l(0xa15181);a.w(0x13c0);a.l(marker+29);a.w(0x4239);a.l(marker);a.w(0x13fc,1);a.l(marker+27);a.bccw(0x60,'done')
 if exit_test:
  a.label('exit_hide');a.w(0x13fc,0);a.l(0xa15181);a.w(0x1039);a.l(0xa15181);a.w(0x13c0);a.l(marker+28);a.w(0x4239);a.l(marker);a.w(0x13fc,1);a.l(marker+27)
 a.label('done');a.w(0x265f,0x245f,0x225f,0x205f)
 for r in range(7,-1,-1):a.w(0x201f+(r<<9))
 a.w(0x44df,0x4e75)
 return a.build()
