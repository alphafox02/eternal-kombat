#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""EC's select cursors, prepared for the 32X's overwrite image.

From your EC (US) disc: each cursor frame, upright and turned 180 degrees, at even and odd
alignment, its colours moved to the 32X palette's slots from 192. 32x_select_payload_probe.py
calls generate() for the cursors' masks; run alone it writes the pixels, palette and an index.

    32x_cursor_overwrite_assets.py EC_CUE OUT_DIR
"""

# (the library: tools/lib/)
import sys as _research_sys
from pathlib import Path as _ResearchPath
_research_sys.path.insert(0, str(_ResearchPath(__file__).resolve().parent.parent / 'lib'))
import argparse,hashlib,importlib,json,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent));from disc import Disc
assets=importlib.import_module('32x_ec_cursor_assets')

def generate(dat,co):
 raw=co[assets.PALETTE:assets.PALETTE+32]
 if hashlib.sha256(raw).hexdigest()!=assets.EXPECTED_PALETTE or any(hashlib.sha256(dat[off:off+128]).hexdigest()!=expected for (_,off),expected in zip(assets.FRAMES,assets.EXPECTED)):raise ValueError('unsupported original EC US cursor data')
 pal=bytearray(32)
 for i in range(1,16):
  w=int.from_bytes(raw[2*i:2*i+2],'big');r=(w>>1)&7;g=(w>>5)&7;b=(w>>9)&7;v=round(r*31/7)|(round(g*31/7)<<5)|(round(b*31/7)<<10);pal[2*i:2*i+2]=v.to_bytes(2,'big')
 data=bytearray();info=[]
 for name,off in assets.FRAMES:
  idx=assets.decode(dat[off:off+128]);pixels=np.where(idx!=0,idx.astype(np.uint16)+192,0).astype(np.uint8)
  # Both flips together occur during the marker's real spinning animation.
  # Other flip combinations are not represented and need a safe fallback.
  for orientation in ('normal','rotate180'):
   oriented=pixels if orientation=='normal' else pixels[::-1,::-1]
   for variant in ('even','odd'):
    arr=oriented if variant=='even' else np.pad(oriented,((0,0),(1,1)))
    info.append({'name':name,'orientation':orientation,'alignment':variant,'offset':len(data),'width':int(arr.shape[1]),'height':16,'bytes':arr.size});data+=arr.tobytes()
 return bytes(data),bytes(pal),info

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('ec_cue',type=Path);p.add_argument('out',type=Path);a=p.parse_args()
 if a.out.exists():p.error('choose a new output directory')
 d=Disc(str(a.ec_cue));data,pal,info=generate(d.read_file('GAME.DAT'),d.read_file('GAME.CO'));a.out.mkdir(parents=True);(a.out/'cursor_pixels.bin').write_bytes(data);(a.out/'cursor_palette.bin').write_bytes(pal);(a.out/'info.json').write_text(json.dumps(info,indent=2)+'\n');print('Prepared',len(info),'aligned cursor variants:',len(data),'pixel bytes plus',len(pal),'palette bytes.')
if __name__=='__main__':main()
