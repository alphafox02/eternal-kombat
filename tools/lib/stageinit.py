# SPDX-License-Identifier: MIT
"""A stage's init (SUB.BIN) moved into its .BGI, after the files are loaded.

Every EC stage init (SUB.BIN $76E2-$AC37, by stage mode: ecstage.stage_inits) starts the same
way: the camera limits (jsr $E00E + 4 words), the stage card and round set-up (bsr $AC38), then -
unless a round is restarting ($AB7 bit 5) - the stage's .BG to $37000 and .BGI to $34000
($65C8), its BG slot ($DEF8) and a wait ($C0FA 10). From the bne past those loads (the "body")
it builds the layers, objects, floor, camera start and palette, and ends with bra $6D8C, its
palette table after it.

relocate() copies a body and the data after it to another address (a .BGI's, $34000 + n), so
that several stages can share one stage mode: only the loads differ (stagepick.py). The
code is copied instruction by instruction: bsr/bra out of the body become jsr/jmp absolute,
branches inside are re-aimed, absolute addresses into the body's own data (the palette table)
move with it. Inline-argument calls ($E00E 4 words, $E062 5 words, $F4BA a list to $FFFF) are
copied whole."""
import capstone

SUB_BASE = 0x6000
INLINE = {0xE00E: 8, 0xE062: 10}
LIST_CALL = 0xF4BA
END = 0x6D8C                            # every init ends with bra.w $6D8C


def W(d, o):
    return int.from_bytes(d[o:o + 2], 'big')


def _cs():
    return capstone.Cs(capstone.CS_ARCH_M68K, capstone.CS_MODE_M68K_000)


def split(sub, init, next_init):
    """{'head': [(addr, bytes, text)], 'body': addr, 'end': addr of its bra $6D8C, 'data': (lo, hi)}."""
    cs = _cs()
    pc, head = init, []
    body = None
    while body is None:
        i = next(cs.disasm(sub[pc - SUB_BASE:pc - SUB_BASE + 10], pc, 1))
        n = i.size + (INLINE.get(_target(i), 0) if i.mnemonic == 'jsr' else 0)
        text = f'{i.mnemonic} {i.op_str}'
        head.append((pc, sub[pc - SUB_BASE:pc - SUB_BASE + n], text))
        if i.mnemonic in ('bne.w', 'bne.b') and any('$ab7' in h[2] and '#$5' in h[2] for h in head[-2:]):
            body = int(i.op_str.lstrip('$'), 16)
        pc += n
        if pc - init > 0x80:
            raise ValueError(f'${init:X}: no round-restart branch in its head')
    end = None
    pc = body
    while end is None:
        i, n = _one(cs, sub, pc)
        if i.mnemonic in ('bra.w', 'jmp') and _target(i) == END:
            end = pc
        pc += n
        if pc >= next_init:
            raise ValueError(f'${init:X}: no bra $6D8C before ${next_init:X}')
    return dict(head=head, body=body, end=end, data=(end + 4 if sub[end - SUB_BASE:end - SUB_BASE + 2] == b'\x60\x00' else end + 6,
                                                      next_init))


def _target(i):
    op = i.op_str.split(',')[-1].strip()
    if op.startswith('$'):
        return int(op[1:].split('.')[0], 16)
    return None


def _one(cs, mem, pc):
    i = next(cs.disasm(mem[pc - SUB_BASE:pc - SUB_BASE + 10], pc, 1))
    n = i.size
    if i.mnemonic == 'jsr':
        t = _target(i)
        if t in INLINE:
            n += INLINE[t]
        elif t == LIST_CALL:
            k = pc + i.size
            while W(mem, k - SUB_BASE) != 0xFFFF:
                k += 2
            n = k + 2 - pc
    return i, n


BCC = {'bra': 0x60, 'bsr': 0x61, 'bhi': 0x62, 'bls': 0x63, 'bcc': 0x64, 'bhs': 0x64, 'bcs': 0x65, 'blo': 0x65,
       'bne': 0x66, 'beq': 0x67, 'bvc': 0x68, 'bvs': 0x69, 'bpl': 0x6A, 'bmi': 0x6B, 'bge': 0x6C, 'blt': 0x6D,
       'bgt': 0x6E, 'ble': 0x6F}


def relocate(sub, init, next_init, org):
    """The init's body and its data, moved to org. Returns (bytes, info): info['map'] old -> new
    address of each instruction; info['calls'] the routines it calls."""
    cs = _cs()
    sp = split(sub, init, next_init)
    lo, hi = sp['body'], sp['end']
    insns, pc = [], lo
    while pc <= hi:
        i, n = _one(cs, sub, pc)
        insns.append((pc, i, n))
        pc += n
    dlo, dhi = sp['data']
    # pass 1: sizes
    def size(pc, i, n):
        m = i.mnemonic.split('.')[0]
        if m in BCC:
            t = _target(i)
            if m == 'bsr' or not (lo <= t <= hi):
                if m not in ('bsr', 'bra'):
                    raise ValueError(f'${pc:X}: conditional branch out of the body ({i.mnemonic} {i.op_str})')
                return 6                                   # jsr/jmp abs.l
            return 4                                       # bcc.w
        if 'pc)' in i.op_str:
            raise ValueError(f'${pc:X}: pc-relative operand ({i.mnemonic} {i.op_str})')
        return n
    new, at = {}, org
    for pc, i, n in insns:
        new[pc] = at
        at += size(pc, i, n)
    data_at = at
    out = bytearray()
    calls = []
    for pc, i, n in insns:
        m = i.mnemonic.split('.')[0]
        raw = bytearray(sub[pc - SUB_BASE:pc - SUB_BASE + n])
        if m in BCC:
            t = _target(i)
            if m == 'bsr' or not (lo <= t <= hi):
                out += (b'\x4e\xb9' if m == 'bsr' else b'\x4e\xf9') + t.to_bytes(4, 'big')
                calls.append(t)
            else:
                disp = new[t] - (new[pc] + 2)
                out += bytes([BCC[m], 0]) + (disp & 0xFFFF).to_bytes(2, 'big')
            continue
        # absolute longs into the body's data (the palette table) move with it
        import re
        for v in [int(x, 16) for x in re.findall(r'\$([0-9a-f]+)', i.op_str)]:
            if dlo <= v < dhi:
                k = raw.find(v.to_bytes(4, 'big'), 2, i.size)
                assert k > 0, (hex(pc), i.op_str)
                raw[k:k + 4] = (data_at + v - dlo).to_bytes(4, 'big')
        if m == 'jsr':
            calls.append(_target(i))
        out += raw
    assert org + len(out) == data_at
    out += sub[dlo - SUB_BASE:dhi - SUB_BASE]
    return bytes(out), dict(map=new, calls=calls, split=sp, data_at=data_at)
