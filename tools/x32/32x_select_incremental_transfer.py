#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The payload's copy from Sega CD PRG-RAM to the 32X (68000 code), a chunk per VBlank.

Each VBlank it asks for the sub CPU's bus (a bounded wait), copies at most 512 bytes and gives
the bus back. 32x_art_probe.py's coordinator (sh2_transfer_demo) runs it as part of the 32X
build's startup code. Emulator-tested only (docs/32x.md).
"""

# (the library: tools/lib/)
import sys as _research_sys
from pathlib import Path as _ResearchPath
_research_sys.path.insert(0, str(_ResearchPath(__file__).resolve().parent.parent / 'lib'))
from mkinputs import Asm

def code(cave=0x5940,marker=0xff5b00,source_prg=0x240e4,destination=0x1b000,size=11844,chunk=512,hold_input=False):
 if source_prg&1 or destination&1 or size<=0 or size%4 or chunk<=0 or chunk%4:raise ValueError('transfer alignment')
 bank=source_prg//0x20000
 if bank>3 or source_prg%0x20000+size>0x20000 or destination+size>0x20000:raise ValueError('transfer crosses bank')
 main_source=0x20000+source_prg%0x20000
 a=Asm(cave);a.w(0x4eb9);a.l(0xff1540)
 if hold_input:
  a.w(0x33fc,0xf000);a.l(0xfffce8);a.w(0x33fc,0xf000);a.l(0xfffce6)
 a.w(0x40e7,0x2f00,0x2f01,0x2f02,0x2f08,0x2f09)
 a.w(0x0c39,1);a.l(marker);a.bccw(0x66,'done') # state must be 1
 # First call initializes byte count and source/destination pointers.
 a.w(0x4a79);a.l(marker+2);a.bccw(0x66,'ready')
 a.w(0x33fc,size);a.l(marker+2);a.w(0x23fc);a.l(main_source);a.l(marker+4);a.w(0x23fc);a.l(0x840000+destination);a.l(marker+8)
 a.label('ready')
 a.w(0x1039);a.l(0xa12003);a.w(0x13c0);a.l(marker+12)
 a.w(0x1039);a.l(0xa12001);a.w(0x13c0);a.l(marker+13)
 a.w(0x0000,2,0x13c0);a.l(0xa12001)
 a.w(0x343c,63);a.label('wait');a.w(0x0839,1);a.l(0xa12001);a.bccw(0x66,'granted');a.dbra(2,'wait')
 a.w(0x13fc,1);a.l(marker+14);a.bccw(0x60,'release')
 a.label('granted')
 a.w(0x1039);a.l(marker+12);a.w(0x0200,0x003f,0x0000,bank<<6,0x13c0);a.l(0xa12003)
 a.w(0x2079);a.l(marker+4);a.w(0x2279);a.l(marker+8)
 a.w(0x3439);a.l(marker+2);a.w(0x0c42,chunk);a.bccw(0x63,'sized') # bls if remaining <= chunk
 a.w(0x343c,chunk)
 a.label('sized');a.w(0x9579);a.l(marker+2) # sub.w d2,remaining
 a.w(0xe44a,0x5342)                    # lsr.w #2,d2; subq.w #1,d2
 a.label('copy');a.w(0x22d8);a.dbra(2,'copy')
 a.w(0x23c8);a.l(marker+4);a.w(0x23c9);a.l(marker+8)
 a.w(0x1039);a.l(marker+12);a.w(0x13c0);a.l(0xa12003)
 a.label('release');a.w(0x1039);a.l(marker+13);a.w(0x0200,0x00fd,0x13c0);a.l(0xa12001)
 a.w(0x4a79);a.l(marker+2);a.bccw(0x66,'done');a.w(0x13fc,0x80);a.l(marker)
 a.label('done');a.w(0x225f,0x205f,0x241f,0x221f,0x201f,0x44df,0x4e75)
 return a.build()
