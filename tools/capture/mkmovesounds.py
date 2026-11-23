#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Which MK CD samples does each move play, and when? (Research: which hit sounds are MK's own.)

Plays each tools/lib/mkmoves.py action from build/states/mk_2p.state and watches the Sega CD PCM
chip in the save state (8 channels at $28085, 16 bytes: position and start, x 2048; the play mask
at +$86; sound RAM at $2810D): a channel starting a new sound is logged with the frame and the
sample it starts, found by matching sound RAM against every MK 8SVX sample (sign-magnitude).

    mkmovesounds.py ACTION ...      e.g. mkmovesounds.py btn_a uppercut hit_high knockdown
"""
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import mkmoves as m, numpy as np
CH, RAM = 0x28085, 0x2810D
ON = CH + 0x86                # the chip's channels playing (a bit each)
# MK samples as sign-magnitude (as loaded into sound RAM)
import glob
from patches import mk_form
lib={}
for f in sorted(glob.glob('extracted/mk_us/SFX*.BIN')):
    fn=os.path.basename(f); k=0
    while True:
        try: rate, body = mk_form(fn, k)
        except Exception: break
        if not body: break
        s=np.frombuffer(body,np.int8).astype(int)
        sm=bytes((0x80|min(v,126)) if v>=0 else min(-v,127) for v in s[:48])
        lib.setdefault(sm,f'{fn}:{k}'); k+=1
def name(ram, start):
    w=bytes(ram[start:start+48])
    for sm,n in lib.items():
        if w==sm: return n
    for sm,n in lib.items():
        if sum(a==b for a,b in zip(w,sm))>=40: return n+'~'
    return f'?{start:04x}'
import subprocess
NAMES={}
for line in subprocess.run([sys.executable,'-P','tools/lib/mksfx.py','list'],capture_output=True,text=True).stdout.splitlines():
    parts=line.split()
    if len(parts)>=2: NAMES[parts[0]]=parts[1]
s=m.Session(); c=s.core
for act in sys.argv[1:]:
    c.load_state('build/states/mk_2p.state'); prev=[None]*8; ev=[]; t=0
    for p1,p2,n in m.ACTIONS[act]:
        c.buttons[0]=set(p1.split('+'))-{''}; c.buttons[1]=set(p2.split('+'))-{''}
        for _ in range(n):
            c.run(1); t+=1; st=c.snapshot()
            for ch in range(8):
                e=st[CH+16*ch:CH+16*ch+16]; start=int.from_bytes(e[4:8],'little')>>11
                addr=int.from_bytes(e[0:4],'little')>>11
                on=st[ON]>>ch&1          # (a channel at its clip's end jumps back to its start as it stops:
                if prev[ch] is not None and on and (not prev[ch][2] or start!=prev[ch][1] or addr<prev[ch][0]) \
                        and 0<=addr-start<2000:   #  its play bit falls - not a new sound)
                    ev.append((t,ch,name(st[RAM:RAM+0x10000],start)))
                prev[ch]=(addr,start,on)
    print(f'{act:12s}', ' '.join(f'{t}:{NAMES.get(n.rstrip("~"), n)}' for t,ch,n in ev))
