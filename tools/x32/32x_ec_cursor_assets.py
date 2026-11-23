#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The four EC select-cursor pictures, from your EC disc (US).

Their offsets in GAME.DAT and palette in GAME.CO (checked by SHA-256 against the US disc).
32x_select_payload_probe.py and 32x_cursor_overwrite_assets.py read them through this module;
run alone it writes them as PNG and indexed arrays.

    32x_ec_cursor_assets.py EC_CUE OUT_DIR
"""

# (the library: tools/lib/)
import sys as _research_sys
from pathlib import Path as _ResearchPath
_research_sys.path.insert(0, str(_ResearchPath(__file__).resolve().parent.parent / 'lib'))
import argparse,hashlib,json,sys
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parent))
from disc import Disc

# Two 16x16, 2x2-tile animation frames per player, in VDP column-major order.
FRAMES=[('p1_0',0x13518),('p1_1',0x13598),('p2_0',0x13ed8),('p2_1',0x13f58)]
PALETTE=0x2ba
EXPECTED=['462d34e0ec27cc23a75f3467493b61091144fd06f48d608fef8b4dab9fda27e3',
          '2ec083e75dbc41b6b93d7b8945fce88fa8b54db566752e4cce21151103e06e09',
          '81b2ee11ff21f413a5cbed9aa4bde637c5ef7ec2ab47c51e8034247fb43fee88',
          'f3f459c6a9bb9843ef8201ce15e6e93f882f2789734a8398ec97e28e90e522a6']
EXPECTED_PALETTE='f19a8c20bea2fd7e4d917e4b3548b34236ed11561fe93eda02c7db103f83e5a4'

def decode(data):
 if len(data)!=128:raise ValueError('cursor data must be exactly 128 bytes')
 out=np.zeros((16,16),np.uint8)
 for tx in range(2):
  for ty in range(2):
   tile=np.frombuffer(data[(tx*2+ty)*32:(tx*2+ty+1)*32],np.uint8).reshape(8,4)
   pix=np.empty((8,8),np.uint8);pix[:,0::2]=tile>>4;pix[:,1::2]=tile&15
   out[ty*8:ty*8+8,tx*8:tx*8+8]=pix
 return out

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('ec_cue',type=Path);p.add_argument('out',type=Path);a=p.parse_args()
 if a.out.exists():p.error('choose a new output directory')
 disc=Disc(str(a.ec_cue));dat=disc.read_file('GAME.DAT');co=disc.read_file('GAME.CO');raw=co[PALETTE:PALETTE+32]
 if len(raw)!=32 or any(int.from_bytes(raw[i:i+2],'big') & 0xf111 for i in range(0,32,2)):raise ValueError('unexpected EC palette format')
 if hashlib.sha256(raw).hexdigest()!=EXPECTED_PALETTE or any(hashlib.sha256(dat[off:off+128]).hexdigest()!=want for (_,off),want in zip(FRAMES,EXPECTED)):
  raise ValueError('cursor graphics or palette differ from the supported EC US disc')
 colors=np.array([[((w>>1)&7)*36,((w>>5)&7)*36,((w>>9)&7)*36,255 if i else 0] for i,w in enumerate(int.from_bytes(raw[j:j+2],'big') for j in range(0,32,2))],np.uint8)
 a.out.mkdir(parents=True);details=[]
 for name,off in FRAMES:
  pixels=decode(dat[off:off+128]);Image.fromarray(colors[pixels],'RGBA').save(a.out/(name+'.png'));np.save(a.out/(name+'_indexed.npy'),pixels);details.append({'name':name,'offset':off,'nontransparent_pixels':int((pixels!=0).sum())})
 (a.out/'palette.bin').write_bytes(raw);(a.out/'info.json').write_text(json.dumps({'source':'EC GAME.DAT and GAME.CO','palette_offset':PALETTE,'frames':details},indent=2)+'\n');print(json.dumps(details,indent=2))
if __name__=='__main__':main()
