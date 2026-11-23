#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The 32X build's second step: the seven MK portraits, packed for the 32X framebuffer.

From extracted/ (MK CD's portraits, made from your disc by prepare.py): each cut to 32x48 at
its place on the select screen, all quantised to one palette (--colors; the rest of the 32X's
256 is left for the cursors). Writes framebuffer.bin and palette.bin (32x_select_payload_probe.py
reads them), and a mock-up and comparison picture over SCREEN (a 320x224 screenshot, or - for a
blank background). MK CD's art only, from the player's own disc.

    32x_cd_roster_preview.py EXTRACTED_DIR SCREEN|- OUT_DIR [--colors 192]
"""

# (the library: tools/lib/)
import sys as _research_sys
from pathlib import Path as _ResearchPath
_research_sys.path.insert(0, str(_ResearchPath(__file__).resolve().parent.parent / 'lib'))
import argparse,json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont

ROSTER=[('raiden','mk_moves_raiden',32,96),('subzero','mk_moves_subzero',64,144),('sonya','mk_moves_sonya',96,144),('liukang','mk_moves_liukang',128,144),('kano','mk_moves_kano',160,144),('johnny','mk_moves_johnny',192,144),('scorpion','mk_moves',224,144)]

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('extracted',type=Path);ap.add_argument('screen',type=Path,help='320x224 comparison image, or - for a blank background');ap.add_argument('out',type=Path);ap.add_argument('--colors',type=int,default=192);a=ap.parse_args()
 if a.out.exists():ap.error('choose a new output directory')
 if not 2<=a.colors<=224:ap.error('choose 2 to 224 colors, leaving palette space for cursors')
 screen=Image.new('RGB',(320,224)) if str(a.screen)=='-' else Image.open(a.screen).convert('RGB')
 if screen.size!=(320,224):ap.error('screen must be 320x224')
 imgs=[]
 for name,folder,x,y in ROSTER:
  im=Image.open(a.extracted/folder/'portrait.png').convert('RGB');w=round(im.width*48/im.height);im=im.resize((w,48),Image.Resampling.LANCZOS);left=(w-32)//2;imgs.append(im.crop((left,0,left+32,48)))
 strip=Image.new('RGB',(32,48*len(imgs)))
 for i,im in enumerate(imgs):strip.paste(im,(0,i*48))
 q=strip.quantize(colors=a.colors,method=Image.Quantize.MEDIANCUT,dither=Image.Dither.NONE);ids=np.asarray(q,dtype=np.uint8)+1;table=q.getpalette();palette=bytearray(512);palette[:2]=bytes.fromhex('8000');rgb=np.zeros((256,3),np.uint8)
 for i in range(a.colors):
  r,g,b=table[i*3:i*3+3];v=(r>>3)|((g>>3)<<5)|((b>>3)<<10);palette[(i+1)*2:(i+2)*2]=v.to_bytes(2,'big');rgb[i+1]=[(r>>3)*255//31,(g>>3)*255//31,(b>>3)*255//31]
 pixels=np.zeros((224,320),np.uint8);base=np.array(screen);preview=base.copy();errors={}
 for i,(name,folder,x,y) in enumerate(ROSTER):
  chunk=ids[i*48:(i+1)*48];pixels[y:y+48,x:x+32]=chunk;preview[y:y+48,x:x+32]=rgb[chunk];errors[name]=round(float(np.abs(np.array(imgs[i],dtype=np.int16)-rgb[chunk].astype(np.int16)).mean()),2)
 fb=bytearray(512)+bytearray(pixels.tobytes())
 for y in range(224):fb[y*2:y*2+2]=(256+160*y).to_bytes(2,'big')
 a.out.mkdir(parents=True);(a.out/'framebuffer.bin').write_bytes(fb);(a.out/'palette.bin').write_bytes(palette);Image.fromarray(preview).save(a.out/'mockup_native.png')
 f=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',18);bold=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',22);can=Image.new('RGB',(1320,580),(20,22,28));d=ImageDraw.Draw(can);d.text((20,12),'Seven MK CD portraits with a shared 32X palette',font=bold,fill='white');d.text((20,45),'Offline mockup; no arcade art. Selection cursors and game integration not implemented.',font=f,fill=(210,210,210))
 for i,(label,pic) in enumerate([('CURRENT EK SELECT',base),('CD PORTRAITS: COLOR MOCKUP',preview)]):
  x=20+650*i;d.text((x,80),label,font=f,fill=(255,205,120));can.paste(Image.fromarray(pic).resize((640,448),Image.Resampling.NEAREST),(x,115))
 can.save(a.out/'comparison.png');info={'palette_entries':int(len(np.unique(ids))),'palette_limit':a.colors,'rgb555_mean_absolute_channel_error':errors,'source':'MK CD','positions':[[n,x,y] for n,_,x,y in ROSTER],'status':'offline mockup only'};(a.out/'info.json').write_text(json.dumps(info,indent=2)+'\n');print(json.dumps(info,indent=2))
if __name__=='__main__':main()
