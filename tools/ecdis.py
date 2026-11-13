#!/usr/bin/env python3
"""Disassembler for Eternal Champions CD sub-CPU modules (.CO .OC .AI .BGI).

Module layout (as observed):
    +0x00  10-byte header  (00000000 0018 0000 0000)
    +0x0A  code; .CO files open with a table of bra.w entry points

Calls into SUB.BIN's jump table ($68B2.., 6 bytes per entry) are labelled
api_NNN so modules can be compared against each other.

Addresses are shown as module-relative offsets: the module's load address
isn't known yet. Everything in it is PC-relative except calls into SUB.BIN.

usage: ecdis.py MODULE [--sub SUB.BIN] [--names names.txt] [--linear]
"""
import argparse, os, re, sys
import capstone
from capstone import m68k

HEADER = 10
SUB_BASE = 0x6000
API_BASE = 0x68B2
API_STRIDE = 6


def load_api(sub):
    """Return {api_addr: (index, target)} parsed from the jmp.l table."""
    api = {}
    off = API_BASE - SUB_BASE
    idx = 0
    while off + 6 <= len(sub) and sub[off:off + 2] == b'\x4e\xf9':
        api[API_BASE + idx * API_STRIDE] = (idx, int.from_bytes(sub[off + 2:off + 6], 'big'))
        off += API_STRIDE
        idx += 1
    return api


def load_names(path):
    names = {}
    if path and os.path.exists(path):
        for line in open(path):
            line = line.split('#', 1)[0].strip()
            if line:
                k, v = line.split(None, 1)
                names[int(k, 0)] = v.strip()
    return names


def make_cs():
    cs = capstone.Cs(capstone.CS_ARCH_M68K, capstone.CS_MODE_M68K_000)
    cs.detail = True
    return cs


BRANCH_RE = re.compile(r'^(b\w+|db\w+|jmp|jsr|bsr\.?\w*|bra\.?\w*)$')
TERMINAL = {'rts', 'rte', 'rtr', 'jmp', 'bra', 'bra.b', 'bra.w', 'bra.s'}


def branch_target(insn):
    """Absolute target of a pc-relative branch, or None."""
    if insn.mnemonic.startswith(('b', 'db')) and insn.mnemonic not in ('btst', 'bclr', 'bset', 'bchg'):
        m = re.search(r'\$([0-9a-f]+)\s*$', insn.op_str)
        if m:
            return int(m.group(1), 16)
    return None


def abs_call(insn):
    """Absolute address of jsr.l / jmp.l $xxxxxx, or None."""
    if insn.mnemonic in ('jsr', 'jmp'):
        m = re.fullmatch(r'\$([0-9a-f]+)(\.l)?', insn.op_str.strip())
        if m:
            return int(m.group(1), 16)
    return None


def pc_ref(insn):
    """Target of an (d16,pc) operand, e.g. lea $64(pc), a1. Capstone prints
    the raw displacement, so resolve it against the extension word's address."""
    m = re.search(r'\$([0-9a-f]+)\(pc\)', insn.op_str)
    if m:
        disp = int(m.group(1), 16)
        if disp >= 0x8000:
            disp -= 0x10000
        return insn.address + 2 + disp
    return None


# engine calls followed by inline word arguments terminated by $FFFF
INLINE_FFFF = {0x6966, 0x696C}
# engine calls that take a code pointer in a1 (spawn task / set next state)
TASK_SPAWN = {0x6BB4}
# engine calls that never return to the caller (end task / jump into engine)
NORETURN = {0x68CA}


def trace(cs, data, entries, code, inline):
    """Recursive-descent decode from entries into code/inline (in place).
    Returns (ok, calls): ok=False if any path hit an undecodable word or ran
    off the end; calls = number of engine calls seen."""
    todo = list(entries)
    seen = set(code)
    ok, calls = True, 0
    while todo:
        pc = todo.pop()
        last_a1 = None
        while pc not in seen:
            if not (HEADER <= pc < len(data)):
                ok = False
                break
            seen.add(pc)
            try:
                insn = next(cs.disasm(data[pc:pc + 10], pc, 1))
            except StopIteration:
                ok = False
                break
            code[pc] = insn
            if abs_call(insn) is not None:
                calls += 1
            t = branch_target(insn)
            if t is not None:
                todo.append(t)
            r = pc_ref(insn)
            if r is not None and insn.mnemonic.startswith('lea') and insn.op_str.endswith('a1'):
                last_a1 = r
            c = abs_call(insn)
            if c in TASK_SPAWN and last_a1 is not None:
                todo.append(last_a1)       # spawned task body
            if insn.mnemonic.startswith('move.l') and insn.op_str.replace(' ', '') == 'a1,$4(a2)' and last_a1 is not None:
                todo.append(last_a1)       # next-state pointer
            if insn.mnemonic in TERMINAL or (insn.mnemonic == 'jmp' and c is None):
                break
            if c in NORETURN and insn.mnemonic == 'jmp':
                break
            pc += insn.size
            if c in INLINE_FFFF:
                start = pc
                while pc + 2 <= len(data) and data[pc:pc + 2] != b'\xff\xff':
                    pc += 2
                pc += 2
                inline[start] = pc - start
    return ok, calls


def disassemble(data, entries, linear=False):
    """Confirmed decode from entry points, then speculative passes from
    pc-relative pointers. A guess is kept only if it decodes cleanly, makes at
    least one engine call, and doesn't land inside an existing instruction."""
    cs = make_cs()
    code, inline = {}, {}
    trace(cs, data, entries, code, inline)
    guessed = set()
    tried = set()
    while True:
        starts = {pc_ref(i) for i in code.values()} - {None} - set(code) - tried
        added = False
        for s in sorted(starts):
            tried.add(s)
            covered = {a + k for a, i in code.items() for k in range(i.size)}
            covered |= {a + k for a, n in inline.items() for k in range(n)}
            if s in covered or s % 2:
                continue
            tc, ti = dict(code), dict(inline)
            ok, calls = trace(cs, data, [s], tc, ti)
            new = set(tc) - set(code)
            clash = any(a + k in covered for a in new for k in range(tc[a].size))
            if ok and calls and not clash:
                guessed |= new
                code, inline = tc, ti
                added = True
        if not added:
            break
    code['_inline'] = inline
    code['_guessed'] = guessed
    if linear:
        pc = HEADER
        for insn in cs.disasm(data[HEADER:], HEADER):
            code.setdefault(insn.address, insn)
    return code


def find_entries(data):
    """Leading run of bra.w (6000 xxxx) after the header = entry table."""
    entries = []
    pc = HEADER
    while data[pc:pc + 2] == b'\x60\x00':
        disp = int.from_bytes(data[pc + 2:pc + 4], 'big', signed=True)
        entries.append((pc, pc + 2 + disp))
        pc += 4
    return entries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('module')
    ap.add_argument('--sub', default=None, help='SUB.BIN (defaults to sibling of module)')
    ap.add_argument('--names', default=os.path.join(os.path.dirname(__file__), 'ec_api_names.txt'))
    ap.add_argument('--linear', action='store_true', help='also linear-sweep undecoded areas')
    a = ap.parse_args()

    data = open(a.module, 'rb').read()
    sub = open(a.sub or os.path.join(os.path.dirname(a.module), 'SUB.BIN'), 'rb').read()
    api = load_api(sub)
    names = load_names(a.names)

    entries = find_entries(data)
    starts = [t for _, t in entries] + [HEADER]
    code = disassemble(data, starts, a.linear)
    inline = code.pop('_inline')
    guessed = code.pop('_guessed')

    labels = {}
    for i, (_, t) in enumerate(entries):
        labels[t] = f'entry_{i}'
    for insn in code.values():
        t = branch_target(insn)
        if t is not None and t not in labels:
            labels[t] = f'loc_{t:04X}'
        r = pc_ref(insn)
        if r is not None and r not in labels and r not in code:
            labels[r] = f'dat_{r:04X}'

    def api_label(addr):
        n = names.get(addr)
        lab = f'sys_{addr:04X}' + (f' {n}' if n else '')
        if SUB_BASE <= addr < SUB_BASE + len(sub):
            o = addr - SUB_BASE
            if sub[o:o + 2] == b'\x4e\xf9':
                lab += f'  -> ${int.from_bytes(sub[o + 2:o + 6], "big"):05X}'
            return lab
        return n or f'ext_{addr:05X}'   # another resident module

    name = os.path.basename(a.module)
    print(f'; {name}  {len(data)} bytes  header {data[:HEADER].hex()}')
    print(f'; entries: ' + ', '.join(f'{labels[t]}=${t:04X}' for _, t in entries))
    covered = sum(i.size for i in code.values()) + sum(inline.values())
    print(f'; lines marked ? were decoded speculatively from a pointer ({len(guessed)} insns)')
    print(f'; decoded {covered} of {len(data) - HEADER} code-area bytes ({100 * covered / max(1, len(data) - HEADER):.0f}%)\n')

    pc = HEADER
    end = len(data)
    while pc < end:
        if pc in labels:
            print(f'\n{labels[pc]}:')
        if pc in inline:
            words = [int.from_bytes(data[pc + i:pc + i + 2], 'big') for i in range(0, inline[pc], 2)]
            print(f'  {pc:05X}  {"":20s}  dc.w     ' + ', '.join(f'${w:04X}' for w in words))
            pc += inline[pc]
            continue
        if pc in code:
            insn = code[pc]
            txt = f'{insn.mnemonic:8s} {insn.op_str}'
            c = abs_call(insn)
            note = api_label(c) if c is not None else None
            r = pc_ref(insn)
            if note is None and r is not None:
                note = labels.get(r, f'${r:04X}')
            hexs = data[pc:pc + insn.size].hex()
            mark = '?' if pc in guessed else ' '
            print(f' {mark}{pc:05X}  {hexs:20s}  {txt:36s}' + (f'  ; {note}' if note else ''))
            pc += insn.size
        else:
            # undecoded: dump as words until the next decoded address
            nxt = min([x for x in list(code) + list(inline) if x > pc] + [end])
            nxt_l = min([x for x in labels if x > pc] + [nxt])
            chunk = data[pc:nxt_l]
            for i in range(0, len(chunk), 16):
                print(f'  {pc + i:05X}  dc.b {chunk[i:i + 16].hex(" ")}')
            pc = nxt_l


if __name__ == '__main__':
    main()
