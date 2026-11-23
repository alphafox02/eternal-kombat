#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The 32X build's third step: the select-screen payload appended to GAME.CO.

On a copy of 32x_art_probe.py's disc: the packed portraits (32x_cd_roster_preview.py's
ROSTER_DIR), EC's cursor frames (from your EC disc), the 32X renderer
(32x_select_incremental_hook.py) and the cursor hook (32x_cursor_roster_hook.py) go after
GAME.CO's end (EC loads the file whole), and the startup coordinator (32x_art_probe.py) into
MAIN.BIN, hooked into its VBlank call. The flags pick the parts (tools/lib/build32x.py passes
the build's); info.json records where each part is, for the next steps. Emulator-tested only
(docs/32x.md).

    32x_select_payload_probe.py CUE ROSTER_DIR OUT_DIR [--sh2-... flags]
"""

# (the library: tools/lib/)
import sys as _research_sys
from pathlib import Path as _ResearchPath
_research_sys.path.insert(0, str(_ResearchPath(__file__).resolve().parent.parent / 'lib'))
import argparse,hashlib,importlib,json,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from disc import Disc,copy_disc
from inputs import require
roster=importlib.import_module('32x_cd_roster_preview');cursor=importlib.import_module('32x_ec_cursor_assets')
MAGIC=b'EK32SEL1';BASE=0x14000;CEILING=0x27000

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('cue',type=Path);p.add_argument('roster_dir',type=Path);p.add_argument('out',type=Path);p.add_argument('--sh2-fallback-demo',action='store_true',help='hide enhanced portraits during confirmation');p.add_argument('--sh2-fallback-input-demo',action='store_true',help='test-only generated confirmation input');p.add_argument('--sh2-cursor-input-demo',action='store_true',help='generate controller pulses in the on-disc cursor test (research only)');p.add_argument('--sh2-cursor-demo',action='store_true',help='experimental autonomous normal selection markers');p.add_argument('--sh2-double-render-demo',action='store_true',help='experimental autonomous rendering of both 32X buffers');p.add_argument('--sh2-render-demo',action='store_true',help='experimental autonomous one-buffer portrait renderer');p.add_argument('--main-extension-probe',action='store_true',help='test whether extra MAIN.BIN bytes are loaded');p.add_argument('--sh2-transfer-demo',action='store_true',help='on the isolated disc, also install the one-buffer select payload transfer');p.add_argument('--sh2-release-bus-demo',action='store_true',help='make the demo master return framebuffer access');p.add_argument('--sh2-startup-demo',action='store_true',help='install experimental idle-loop startup hook in the isolated disc only');a=p.parse_args()
 if a.out.exists():p.error('choose a new output directory')
 fb=(a.roster_dir/'framebuffer.bin').read_bytes();pal=(a.roster_dir/'palette.bin').read_bytes()
 if a.sh2_fallback_demo and not a.sh2_cursor_demo:raise ValueError('--sh2-fallback-demo requires --sh2-cursor-demo')
 if a.sh2_fallback_input_demo and not (a.sh2_fallback_demo and a.sh2_cursor_input_demo):raise ValueError('--sh2-fallback-input-demo requires fallback and cursor input options')
 if a.sh2_cursor_input_demo and not a.sh2_cursor_demo:raise ValueError('--sh2-cursor-input-demo requires --sh2-cursor-demo')
 if a.sh2_cursor_demo:
  if not a.sh2_double_render_demo:raise ValueError('--sh2-cursor-demo requires --sh2-double-render-demo')
  pal=pal[:510]+b'\x80\x00'
 if len(fb)!=72192 or len(pal)!=512:raise ValueError('unexpected packed roster assets')
 pixels=np.frombuffer(fb,dtype=np.uint8,offset=512).reshape(224,320);pdat=bytearray(MAGIC+pal)
 for name,folder,x,y in roster.ROSTER:pdat+=bytes((x>>8,x&255,y>>8,y&255))+pixels[y:y+48,x:x+32].tobytes()
 source=Disc(require('ec_us').cue);dat=source.read_file('GAME.DAT');co=source.read_file('GAME.CO');raw=co[cursor.PALETTE:cursor.PALETTE+32]
 if hashlib.sha256(raw).hexdigest()!=cursor.EXPECTED_PALETTE or any(hashlib.sha256(dat[off:off+128]).hexdigest()!=want for (_,off),want in zip(cursor.FRAMES,cursor.EXPECTED)):raise ValueError('unsupported original EC disc cursor assets')
 if not a.sh2_cursor_demo:
  pdat+=raw
  for _,off in cursor.FRAMES:pdat+=dat[off:off+128]
 if a.sh2_double_render_demo and not a.sh2_render_demo:raise ValueError('--sh2-double-render-demo requires --sh2-render-demo')
 renderer_offset=len(pdat);renderer_size=0
 if a.sh2_render_demo:
  if not a.sh2_transfer_demo:raise ValueError('--sh2-render-demo requires --sh2-transfer-demo')
  renderer_module=importlib.import_module('32x_select_incremental_hook')
  if a.sh2_cursor_demo:
   raw_variants,_,_=importlib.import_module('32x_cursor_overwrite_assets').generate(dat,co)
   masks=bytes(255 if b else 0 for b in raw_variants)
   if len(masks)!=4352 or masks[:2176]!=masks[2176:]:raise ValueError('P1/P2 cursor opacity differs')
   masks=masks[:2176];hook_module=importlib.import_module('32x_cursor_roster_hook')
   hook=hook_module.code(cave=0x6900,marker=0xff7600,cursors=0,guard_screen=True,share_p1_masks=True,drive_two_pads=a.sh2_cursor_input_demo,fallback_confirmation=a.sh2_fallback_demo,input_confirmation=a.sh2_fallback_input_demo,fallback_report_mode=False)
   hook+=bytes((-len(hook))%4);hook_size=len(hook)
   renderer=renderer_module.code(cave=0x63fa,marker=0xff6c00,guard_screen=True,double_buffer=True,cursor_source=0,cursor_size=hook_size)[6:]
   renderer_size=(len(renderer)+3)&~3;mask_offset=renderer_offset+renderer_size;hook_offset=mask_offset+len(masks)
   hook=hook_module.code(cave=0x6900,marker=0xff7600,cursors=0x85b000+mask_offset,guard_screen=True,share_p1_masks=True,drive_two_pads=a.sh2_cursor_input_demo,fallback_confirmation=a.sh2_fallback_demo,input_confirmation=a.sh2_fallback_input_demo,fallback_report_mode=False)
   hook+=bytes((-len(hook))%4)
   renderer=renderer_module.code(cave=0x63fa,marker=0xff6c00,guard_screen=True,double_buffer=True,cursor_source=0x85b000+hook_offset,cursor_size=len(hook))[6:]
   renderer+=bytes((-len(renderer))%4)
   if len(renderer)!=renderer_size:raise RuntimeError('renderer size changed during relocation')
   pdat+=renderer+masks+hook
  else:
   renderer=renderer_module.code(cave=0x63fa,marker=0xff6c00,guard_screen=True,double_buffer=a.sh2_double_render_demo)[6:]
   renderer+=bytes((-len(renderer))%4);renderer_size=len(renderer);pdat+=renderer
 src=Disc(str(a.cue));game=src.read_file('GAME.CO');start=BASE+len(game);end=start+len(pdat)
 if start&1 or end>(0x28000 if a.sh2_render_demo else CEILING):raise ValueError(f'GAME.CO payload would extend to ${end:X}, outside test allocation')
 a.out.mkdir(parents=True);cue=copy_disc(str(a.cue),str(a.out),'probe');dst=Disc(cue);dst.replace_file('GAME.CO',game+pdat)
 if dst.read_file('GAME.CO')!=game+pdat:raise RuntimeError('disc copy verification failed')
 if a.sh2_transfer_demo and not (a.sh2_startup_demo and a.sh2_release_bus_demo):raise ValueError('--sh2-transfer-demo requires both startup and bus-release options')
 if a.sh2_release_bus_demo and not a.sh2_startup_demo:raise ValueError('--sh2-release-bus-demo requires --sh2-startup-demo')
 if a.sh2_startup_demo:
  module=importlib.import_module('32x_art_probe')
  if a.sh2_render_demo:
   marker=0x5be0;demo=module.sh2_transfer_demo(boot_marker=0xff5be0,transfer_marker=0xff5bf0,transfer_entry=0xff5ab0,source_prg=start,size=len(pdat),renderer_source=0x85b000+renderer_offset,renderer_size=renderer_size,hold_input=a.sh2_cursor_input_demo)
  else:
   marker=0x5bb0 if a.sh2_transfer_demo else 0x5b00;demo=module.sh2_transfer_demo(source_prg=start,size=len(pdat)) if a.sh2_transfer_demo else module.sh2_boot_demo(release_bus=a.sh2_release_bus_demo)
  main=dst.read_file('MAIN.BIN')
  if main[0x53a:0x540]!=bytes.fromhex('4eb900ff1540') or any(main[0x5940:0x5940+len(demo)]) or any(main[marker:marker+16]) or 0x5940+len(demo)>marker:raise RuntimeError('startup demo hook area is not empty')
  dst.patch_file('MAIN.BIN',0x5940,demo,expect=bytes(len(demo)));dst.patch_file('MAIN.BIN',marker,b'\x01\x00',expect=b'\x00\x00');dst.patch_file('MAIN.BIN',0x53a,bytes.fromhex('4eb900ff5940'),expect=bytes.fromhex('4eb900ff1540'))
 if a.main_extension_probe:
  current=dst.read_file('MAIN.BIN')
  if len(current)>0x6400:raise ValueError('MAIN.BIN is too large for the extension probe')
  dst.replace_file('MAIN.BIN',current+bytes(0x6400-len(current))+b'EK32-EXT-TEST-01')
 (a.out/'payload.bin').write_bytes(pdat);(a.out/'expected_palette.bin').write_bytes(pal);info={'cue':str(Path(cue).resolve()),'payload_pram':start,'payload_size':len(pdat),'end_exclusive':end,'sha256':hashlib.sha256(pdat).hexdigest(),'game_co_original_size':len(game),'renderer_offset':renderer_offset if a.sh2_render_demo else None,'renderer_size':renderer_size,'cursor_mask_offset':mask_offset if a.sh2_cursor_demo else None,'cursor_hook_offset':hook_offset if a.sh2_cursor_demo else None,'cursor_hook_size':hook_size if a.sh2_cursor_demo else None,'status':'isolated payload diagnostic only'};(a.out/'info.json').write_text(json.dumps(info,indent=2)+'\n');print(json.dumps(info,indent=2))
if __name__=='__main__':main()
