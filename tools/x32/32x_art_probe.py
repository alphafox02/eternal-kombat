#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The 32X build's first step: 32X detection hooked into MAIN.BIN's startup.

Run by tools/lib/build32x.py (tools/build.py --32x) on a copy of the plain disc. A hook at
MAIN.BIN $42 checks for a 32X ('MARS' at $A130EC) and, with one, enables the adapter and draws a
32x32 test image from MK's portrait (extracted/mk_moves/portrait.png) on the 32X framebuffer;
then it wipes its code, image and palette from work RAM. Step 4 (32x_repair_experiment.py)
reduces it to the detection and the adapter request; the RAM cleanup stays. The later steps'
startup code is here too (sh2_boot_demo, sh2_transfer_demo: the VBlank coordinator).
Emulator-tested only (docs/32x.md).

    32x_art_probe.py OUT_DIR [--source PLAIN_CUE] [--behind]     -> OUT_DIR/probe.cue
"""

# (the library: tools/lib/)
import sys as _research_sys
from pathlib import Path as _ResearchPath
_research_sys.path.insert(0, str(_ResearchPath(__file__).resolve().parent.parent / 'lib'))
import argparse
from pathlib import Path
import sys
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parent))
from disc import Disc, copy_disc
from inputs import ROOT
from mkinputs import Asm

SRC=Path(ROOT)/'build/Eternal Kombat/Eternal Kombat.cue'
PIC=Path(ROOT)/'extracted/mk_moves/portrait.png'
CAVE=0x51a0
IMG=0x5300
PAL=0x5700


def make_code(behind=False):
    a=Asm(CAVE)
    a.w(0x48e7,0xc0c0)                  # movem.l d0-d1/a0-a1,-(sp)
    a.w(0x0cb9); a.l(0x4d415253); a.l(0xa130ec)
    a.bccw(0x66,'cleanup')              # no 32X: skip all 32X writes
    a.w(0x13fc,0x0003); a.l(0xa15101)  # adapter enable, release reset
    a.w(0x41f9); a.l(0x840000)         # line table
    a.w(0x303c,223)
    a.label('lines'); a.w(0x30fc,0x0100); a.dbra(0,'lines')
    a.w(0x41f9); a.l(0x840400)         # blank 32 rows (320 pixels each)
    a.w(0x303c,32*160-1)
    a.label('clear'); a.w(0x4258); a.dbra(0,'clear')
    a.w(0x41f9); a.l(0x840000+28*2)    # point 32 display lines at rows
    a.w(0x323c,0x0200,0x303c,31)
    a.label('table'); a.w(0x30c1,0x0641,160); a.dbra(0,'table')
    a.w(0x41f9); a.l(0x840400+16)      # image at x=16, 32x32
    a.w(0x43f9); a.l(0xff0000+IMG)
    a.w(0x303c,31)
    a.label('row'); a.w(0x323c,7)
    a.label('pixels'); a.w(0x20d9); a.dbra(1,'pixels')
    a.w(0xd0fc,288); a.dbra(0,'row')
    a.w(0x41f9); a.l(0xa15200)         # 32X palette
    a.w(0x43f9); a.l(0xff0000+PAL)
    a.w(0x303c,16)
    a.label('colors'); a.w(0x30d9); a.dbra(0,'colors')
    a.w(0x13fc,0x0001 if behind else 0x0081); a.l(0xa15181) # packed 8-bit, selectable priority
    a.w(0x13fc,0x0001); a.l(0xa1518b) # display buffer written above
    a.label('cleanup')
    assert CAVE + a.labels['cleanup'] == 0x523c  # self-erase must stop before current code
    a.w(0x41f9); a.l(0xff0000+IMG)     # restore temporary art and palette storage
    a.w(0x303c,(PAL-IMG+34)//2-1)
    a.label('wipe'); a.w(0x4258); a.dbra(0,'wipe')
    # The beginning of the one-shot code occupied zero-filled workspace.
    # Erase the already-executed section, leaving the current epilogue intact.
    a.w(0x41f9); a.l(0xff0000+CAVE)
    a.w(0x303c,(0x523c-CAVE)//2-1)
    a.label('wipecode'); a.w(0x4258); a.dbra(0,'wipecode')
    a.w(0x4cdf,0x0303,0x46fc,0x2000,0x4e75)
    return a.build()


def sh2_boot_demo(cave=0x5940,marker=0xff5b00,release_bus=False):
    """One-shot experimental disc hook; unsafe outside isolated test discs.

    Stages only two idle-loop instructions, checks for 32X and requests the CD
    boot handshake. No timeout, reset, VDP ownership or production code.
    """
    program=bytes.fromhex('e000c000affe0009affe0009' if release_bus else 'affe0009affe0009')
    boot=bytearray(0x38+len(program))
    for offset,value in ((0x18,0x06000000),(0x1c,len(program)),(0x20,0x06000000),(0x24,0x06000008 if release_bus else 0x06000004),(0x28,0x06000000),(0x2c,0x06000000)):
        boot[offset:offset+4]=value.to_bytes(4,'big')
    boot[0x38:]=program
    a=Asm(cave);a.w(0x4eb9);a.l(0xff1540);a.w(0x40e7,0x2f00,0x4a39);a.l(marker);a.bccw(0x67,'done')
    a.w(0x4239);a.l(marker)
    a.w(0x0cb9);a.l(0x4d415253);a.l(0xa130ec);a.bccw(0x66,'absent')
    for off in range(0x18,len(boot),4):
        a.w(0x23fc);a.l(int.from_bytes(boot[off:off+4],'big'));a.l(0x840000+off)
    a.w(0x23fc);a.l(0x5f43445f);a.l(0xa15120);a.w(0x13fc,1);a.l(marker+1);a.bccw(0x60,'done')
    a.label('absent');a.w(0x13fc,2);a.l(marker+1)
    a.label('done');a.w(0x201f,0x44df,0x4e75)
    return a.build()

def sh2_transfer_demo(cave=0x5940,boot_marker=0xff5bb0,transfer_marker=0xff5bc0,transfer_entry=0xff5a80,source_prg=0x240e4,size=11844,renderer_source=None,renderer_size=0,hold_input=False):
    """Experimental on-disc startup and one-buffer payload transfer.

    Depends on heuristic select detection, unproven scratch and the temporary
    32X adapter initializer. No runtime renderer or safe recovery is provided.
    """
    from importlib import import_module
    program=bytes.fromhex('e000c000affe0009affe0009');boot=bytearray(0x38+len(program))
    for offset,value in ((0x18,0x06000000),(0x1c,len(program)),(0x20,0x06000000),(0x24,0x06000008),(0x28,0x06000000),(0x2c,0x06000000)):
        boot[offset:offset+4]=value.to_bytes(4,'big')
    boot[0x38:]=program
    a=Asm(cave);a.w(0x4eb9);a.l(0xff1540);a.w(0x40e7,0x2f00,0x2f08,0x2f09,0x0c39,1);a.l(boot_marker);a.bccw(0x66,'runtime')
    a.w(0x4239);a.l(boot_marker);a.w(0x0cb9);a.l(0x4d415253);a.l(0xa130ec);a.bccw(0x66,'absent')
    for offset in range(0x18,len(boot),4):
        a.w(0x23fc);a.l(int.from_bytes(boot[offset:offset+4],'big'));a.l(0x840000+offset)
    a.w(0x23fc);a.l(0x5f43445f);a.l(0xa15120);a.w(0x13fc,1);a.l(boot_marker+1);a.bccw(0x60,'runtime')
    a.label('absent');a.w(0x13fc,2);a.l(boot_marker+1)
    a.label('runtime');a.w(0x0c39,1);a.l(boot_marker+1);a.bccw(0x66,'done')
    a.w(0x4a39);a.l(transfer_marker);a.bccw(0x66,'transfer')
    for addr,value in ((0xa15120,0x4d5f4f4b),(0xa15124,0x535f4f4b)):
        a.w(0x0cb9);a.l(value);a.l(addr);a.bccw(0x66,'done')
    a.w(0x0839,7);a.l(0xa15100);a.bccw(0x66,'done')
    for addr,value in ((0xfff59e,120),(0xfff5a0,81),(0xfff8f0,0x0ec6)):
        a.w(0x0c79,value);a.l(addr);a.bccw(0x66,'done')
    a.w(0x13fc,1);a.l(transfer_marker)
    a.label('transfer');a.w(0x4eb9);a.l(transfer_entry)
    if renderer_source is not None:
        if renderer_size<=0 or renderer_size%4:raise ValueError('renderer size must be a positive multiple of four')
        a.w(0x0c39,0x80);a.l(transfer_marker);a.bccw(0x66,'done')
        a.w(0x4a39);a.l(0xff6c00);a.bccw(0x66,'render')
        a.w(0x41f9);a.l(renderer_source);a.w(0x43f9);a.l(0xff6400);a.w(0x303c,renderer_size//4-1)
        a.label('copy_renderer');a.w(0x22d8);a.dbra(0,'copy_renderer');a.w(0x13fc,1);a.l(0xff6c00)
        a.label('render');a.w(0x4eb9);a.l(0xff6400)
    a.label('done');a.w(0x225f,0x205f,0x201f,0x44df,0x4e75)
    coordinator=a.build();gap=transfer_entry-0xff0000-cave
    if len(coordinator)>gap:raise ValueError(f'coordinator exceeds reserved space: {len(coordinator)}>{gap}')
    transfer=import_module('32x_select_incremental_transfer').code(cave=transfer_entry-0xff0000-6,marker=transfer_marker,source_prg=source_prg,size=size,hold_input=hold_input)[6:]
    full=coordinator+bytes(gap-len(coordinator))+transfer
    if cave+len(full)>boot_marker-0xff0000:raise ValueError('transfer code overlaps its markers')
    return full

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('out',type=Path)
    p.add_argument('--behind',action='store_true',help='put the 32X layer behind the Genesis layer')
    p.add_argument('--source',type=Path,default=SRC,help='the plain disc to start from (tools/lib/build32x.py)')
    args=p.parse_args()
    src=args.source
    out=args.out.resolve()
    if out.exists():raise SystemExit('Choose a new output directory; refusing to overwrite.')
    if not src.is_file() or not PIC.is_file():raise SystemExit('Need the existing build and the extracted MK CD Scorpion portrait.')
    original=Image.open(PIC).convert('RGB').resize((32,32),Image.Resampling.LANCZOS)
    image=original.quantize(colors=16,method=Image.Quantize.MEDIANCUT)
    pixels=bytes(i+1 for i in image.tobytes())
    pal=image.getpalette(); colors=[0x8000]
    for i in range(16):
        r,g,b=pal[3*i:3*i+3];colors.append((r>>3)|((g>>3)<<5)|((b>>3)<<10))
    palette=b''.join(c.to_bytes(2,'big') for c in colors)
    code=make_code(behind=args.behind);assert len(code)<IMG-CAVE and IMG+len(pixels)<=PAL
    out.mkdir(parents=True);cue=copy_disc(str(src),str(out),'probe')
    d=Disc(cue);before=d.read_file('MAIN.BIN')
    assert before[0x42:0x46]==bytes.fromhex('46fc2000')
    for offset,data in ((CAVE,code),(IMG,pixels),(PAL,palette)):
        assert before[offset:offset+len(data)]==bytes(len(data)),f'not empty: {offset:x}'
        d.patch_file('MAIN.BIN',offset,data,expect=bytes(len(data)))
    d.patch_file('MAIN.BIN',0x42,bytes.fromhex('6100515c'),expect=bytes.fromhex('46fc2000'))
    original.resize((256,256),Image.Resampling.NEAREST).save(out/'source_portrait.png')
    print('Created isolated proof:',cue,'code bytes:',len(code))
    print('WARNING: experimental scratch-memory use; not a playable release.')


if __name__=='__main__':main()
