#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The 32X select renderer (68000 code): the MK portraits drawn into the 32X framebuffer.

Built by 32x_select_payload_probe.py into the payload. Its work is spread over VBlanks, a phase
each (the line table, clearing, the palette, a portrait each, the flip); with guard_screen it
draws only on the select screen and hides the 32X layer elsewhere, with double_buffer it fills
both buffers, and it installs the cursor hook (32x_cursor_roster_hook.py) once both are ready.
Emulator-tested only (docs/32x.md).
"""

# (the library: tools/lib/)
import sys as _research_sys
from pathlib import Path as _ResearchPath
_research_sys.path.insert(0, str(_ResearchPath(__file__).resolve().parent.parent / 'lib'))
from mkinputs import Asm
ROSTER=[(32,96),(64,144),(96,144),(128,144),(160,144),(192,144),(224,144)]

def code(cave=0x6400,marker=0xff6c00,stage=0x85b000,guard_screen=False,double_buffer=False,transfer_marker=0xff5bf0,cursor_source=None,cursor_size=0):
 if double_buffer and not guard_screen:raise ValueError('double buffering requires screen guard')
 if cursor_source is not None and (not double_buffer or cursor_size<=0 or cursor_size%4):raise ValueError('cursor handoff requires double buffering and aligned code')
 a=Asm(cave)
 a.w(0x4eb9);a.l(0xff1540);a.w(0x40e7,0x2f00,0x2f01,0x2f08,0x2f09)
 if guard_screen:
  for addr,val in ((0xfff59e,120),(0xfff5a0,81)):
   a.w(0x0c79,val);a.l(addr);a.bccw(0x66,'screen_unseen')
  a.w(0x13fc,1);a.l(marker+6);a.label('screen_unseen')
 a.w(0x1039);a.l(marker)
 phases=[(1,'init'),(2,'clear'),(3,'palette')]+[(4+i,f'icon{i}') for i in range(7)]+[(11,'flip')]
 if guard_screen:phases.append((0x80,'active'))
 for phase,label in phases:
  a.w(0x0c00,phase);a.bccw(0x67,label)
 a.bccw(0x60,'done')
 a.label('init')
 a.w(0x41f9);a.l(0x840000);a.w(0x303c,0x100,0x323c,95)
 a.label('blanktop');a.w(0x30c0);a.dbra(1,'blanktop')
 a.w(0x303c,0x1a0,0x323c,95)
 a.label('mid');a.w(0x30c0,0x0640,160);a.dbra(1,'mid')
 a.w(0x303c,0x100,0x323c,31)
 a.label('blankbottom');a.w(0x30c0);a.dbra(1,'blankbottom')
 a.w(0x23fc);a.l(0x840200);a.l(marker+2) # clear pointer, even aligned
 a.w(0x13fc,13);a.l(marker+1);a.w(0x13fc,2);a.l(marker);a.bccw(0x60,'done')
 a.label('clear')
 a.w(0x2079);a.l(marker+2);a.w(0x7000,0x323c,639)
 a.label('clearloop');a.w(0x20c0);a.dbra(1,'clearloop')
 a.w(0x23c8);a.l(marker+2);a.w(0x5339);a.l(marker+1);a.bccw(0x66,'done')
 a.w(0x13fc,3);a.l(marker);a.bccw(0x60,'done')
 a.label('palette')
 a.w(0x41f9);a.l(stage+8);a.w(0x43f9);a.l(0xa15200);a.w(0x323c,255)
 a.label('colors');a.w(0x32d8);a.dbra(1,'colors')
 a.w(0x13fc,4);a.l(marker);a.bccw(0x60,'done')
 for i,(x,y) in enumerate(ROSTER):
  a.label(f'icon{i}');a.w(0x41f9);a.l(stage+8+512+i*(4+1536)+4)
  a.w(0x43f9);a.l(0x840200+320+(y-96)*320+x)
  a.w(0x323c,47);a.label(f'row{i}');a.w(0x303c,7);a.label(f'col{i}')
  a.w(0x22d8);a.dbra(0,f'col{i}');a.w(0xd2fc,288);a.dbra(1,f'row{i}')
  a.w(0x13fc,5+i);a.l(marker);a.bccw(0x60,'done')
 def screen_guard(fail):
  for addr,val in ((0xfff59e,120),(0xfff5a0,81),(0xfff8f0,0x0ec6)):
   a.w(0x0c79,val);a.l(addr);a.bccw(0x66,fail)
 a.label('flip')
 if guard_screen:
  for addr,val in ((0xfff59e,120),(0xfff5a0,81)):
   a.w(0x0c79,val);a.l(addr);a.bccw(0x66,'flip_not_select')
  a.w(0x0c79,0x0ec6);a.l(0xfff8f0);a.bccw(0x66,'done')
 if double_buffer:
  a.w(0x0c39,4);a.l(marker+7);a.bccw(0x67,'second_flip')
  a.w(0x1039);a.l(0xa1518b);a.w(0x0200,1,0x5200,0x13c0);a.l(marker+7);a.bccw(0x60,'do_flip')
  a.label('second_flip');a.w(0x13fc,5);a.l(marker+7);a.label('do_flip')
 a.w(0x1039);a.l(0xa1518b);a.w(0x0200,1,0x0a00,1);a.w(0x13c0);a.l(0xa1518b)
 a.w(0x13fc,0x80);a.l(marker)
 if guard_screen:
  a.bccw(0x60,'done');a.label('flip_not_select');a.w(0x4a39);a.l(marker+6);a.bccw(0x67,'done');a.bccw(0x60,'hide')
  a.label('active');screen_guard('hide')
  if double_buffer:
   if cursor_source is not None:
    a.w(0x0c39,5);a.l(marker+7);a.bccw(0x66,'cursor_not_ready')
    a.w(0x41f9);a.l(cursor_source);a.w(0x43f9);a.l(0xff6900);a.w(0x303c,cursor_size//4-1)
    a.label('copy_cursor');a.w(0x22d8);a.dbra(0,'copy_cursor')
    a.w(0x41f9);a.l(0xff7600);a.w(0x7000,0x323c,7)
    a.label('clear_cursor_marker');a.w(0x20c0);a.dbra(1,'clear_cursor_marker')
    a.w(0x13fc,1);a.l(0xff7600);a.w(0x23fc);a.l(0x4eb900ff);a.l(0xff053a);a.w(0x33fc,0x6900);a.l(0xff053e);a.bccw(0x60,'done')
    a.label('cursor_not_ready')
   a.w(0x0c39,1);a.l(marker+7);a.bccw(0x67,'check_first_flip')
   a.w(0x0c39,2);a.l(marker+7);a.bccw(0x67,'check_first_flip')
   a.w(0x0c39,3);a.l(marker+7);a.bccw(0x66,'done')
   a.w(0x0c39,0x80);a.l(transfer_marker);a.bccw(0x66,'done')
   a.w(0x13fc,1);a.l(marker);a.w(0x13fc,4);a.l(marker+7);a.bccw(0x60,'done')
   a.label('check_first_flip');a.w(0x1039);a.l(0xa1518b);a.w(0x0200,1,0x5200,0xb039);a.l(marker+7);a.bccw(0x67,'done')
   for offset in (0,4,8,12):a.w(0x42b9);a.l(transfer_marker+offset)
   a.w(0x13fc,1);a.l(transfer_marker);a.w(0x13fc,3);a.l(marker+7)
  a.bccw(0x60,'done')
  a.label('hide');a.w(0x13fc,0);a.l(0xa15181);a.w(0x13fc,0x81);a.l(marker)
 a.label('done');a.w(0x225f,0x205f,0x221f,0x201f,0x44df,0x4e75)
 return a.build()
