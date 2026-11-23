#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""With no free effect object, EC's spawns get a scratch object (patches.ec_object_pool).

EC's allocator (SUB $10844) left a0 on the free objects' stack itself (-$35D2(a6)) with carry set, and
EC's spawns (the hit spark, the dust, ~80 more) never check: their fields went over the stack and the
first object's link - the object loop jumped to $102 (Johnny's Contest froze). With the free count
held at 0, an MK fighter (blood) and an EC fighter jab each other for 400 frames: the sub CPU must
live, the object list must stay whole (every link a pool object or a fighter), the free stack hold
only pool objects after, and the spawns' writes must reach the scratch object.

    poolcheck.py [--disc CUE]
"""
import argparse, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))   # (the library: tools/lib/)
import scd, cpuregs, watchwrite
from inputs import ROOT
from patches import POOL_SCRATCH

FREE = 0x30000 - 0x35D2          # the free stack: word = 4 x free, then the pointers
ACTIVE = 0x30000 - 0x1E92        # the object list's head
P1, P2 = 0x2E188, 0x2E330
W = lambda r, o: int.from_bytes(r[o:o + 2], 'big', signed=True)
L = lambda r, o: int.from_bytes(r[o:o + 4], 'big')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--disc', default=os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue'))
    a = ap.parse_args()
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        for p1, name in ((18, 'Kano'), (8, 'Blade')):
            st = os.path.join(tmp, 'duel.state')
            subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'lib', 'duelstate.py'), '--disc', a.disc,
                            '--p1', str(p1), '--p2', '0', '--stage', '11', '--out', st], check=True, capture_output=True)
            c = scd.Core(saves=os.path.join(tmp, 'saves'))
            c.load(a.disc)
            c.load_state(st)
            c.run(60)
            for _ in range(300):                       # walk up to him
                r = c.prg_ram()
                if abs(W(r, P2 + 0x4E) - W(r, P1 + 0x4E)) < 45:
                    break
                c.buttons[0] = {'right'}
                c.run(1)
            keep = bytes(c.prg_ram()[FREE:FREE + 2])
            wrote = []
            hook = watchwrite.watch(c, {POOL_SCRATCH + o for o in range(0, 0xA6, 2)}, lambda at, v, n: wrote.append(at))
            hits, dead, broken = 0, False, ''
            for t in range(400):
                c.poke_prg(FREE, b'\0\0')              # none free
                c.poke_prg(P1 + 0x76, b'\x00\x68'); c.poke_prg(P2 + 0x76, b'\x00\x68')
                c.buttons[0] = {'x'} if t % 10 < 2 else set()
                c.buttons[1] = {'x'} if t % 14 < 2 else set()
                c.run(1)
                r = c.prg_ram()
                hits += W(r, P1 + 0x76) < 0x68 or W(r, P2 + 0x76) < 0x68     # (either side: a hit)
                pc = cpuregs.regs(c, 'sub')['pc']
                if pc in (0x5E8, 0x5EE) or 0x5F40 <= pc <= 0x5F76:
                    dead = True
                    break
                n, seen = L(r, ACTIVE), 0
                while n and seen < 80:
                    if not 0x20000 <= n < 0x40000:
                        broken = f'link {n:X} at frame {t}'
                        break
                    n, seen = L(r, n), seen + 1
                if broken:
                    break
            c.poke_prg(FREE, keep)
            hook()
            r = c.prg_ram()
            n = W(r, FREE) // 4
            pool = [L(r, FREE + 2 + 4 * i) for i in range(n)]
            stray = [p for p in pool if (p - POOL_SCRATCH) % 0xA6 or not 1 <= (p - POOL_SCRATCH) // 0xA6 < 35]
            ok = not dead and not broken and not stray and hits > 0 and wrote
            bad += not ok
            print(f'  {name} vs Shadow, no free object: {hits} hits, '
                  f'{"sub CPU crashed" if dead else "alive"}, {broken or "list whole"}, '
                  f'{len(wrote)} writes to the scratch object, free stack {"STRAY " + str(stray) if stray else "whole"}'
                  f' -> {"ok" if ok else "FAIL"}')
    print(f'pool: {"ok" if not bad else f"{bad} FAIL"}')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
