"""EC .PL art banks: an optimal (dynamic-programming) parse over every opcode
family of EC's unpacker (SUB.BIN $11784), with the dictionary chosen by
measured use. About 25% smaller than ecpl.encode_bank's three opcodes.
Opcodes (measured with synthetic frames): $00-$1D zero runs, $1E-$49 dict
runs, $4A-$53 literal runs, $54-$67/$70-$75 (zero, dict) pairs, $68-$6F
(zero, literal) pairs, $76-$7B one dict word repeated, $7C-$A7 literal + dict
run, $A9-$D1 literal, dict, literal + dict run, $F8 yield, $FF end.
Same bank layout as ecpl.encode_bank (512-byte dictionary, then per frame
literal words and op bytes). Written by a research run; tools/ecunpack.py
decodes with EC's own code to check it (scorpion_full does, every build)."""
from collections import Counter

def parse_frame(f, index, start, stop):
    """DP over f[start:stop]; returns (cost_bytes, ops_bytes, lit_words)."""
    n = stop - start
    INF = 1 << 30
    best = [INF] * (n + 1); best[n] = 0; how = [None] * (n + 1)
    isZ = [f[start + i] == 0 for i in range(n)]
    isD = [f[start + i] != 0 and f[start + i] in index for i in range(n)]
    for i in range(n - 1, -1, -1):
        b = INF; h = None
        def cand(cost, k, kind):
            nonlocal b, h
            c = cost + best[i + k]
            if c < b: b, h = c, (kind, k)
        # zero run 1..30
        k = 0
        while k < 30 and i + k < n and isZ[i + k]:
            k += 1; cand(1, k, 'Z')
        # dict run 1..44
        k = 0
        while k < 44 and i + k < n and isD[i + k]:
            k += 1; cand(1 + k, k, 'D')
        # literal run 1..10 (any word, literal costs 2)
        k = 0
        while k < 10 and i + k < n:
            k += 1; cand(1 + 2 * k, k, 'L')
        # (Z D) x 1..26
        k = 0
        while k < 20 and i + 2 * k + 1 < n and isZ[i + 2 * k] and isD[i + 2 * k + 1]:
            k += 1; cand(1 + k, 2 * k, 'ZD')
        # (Z L) x 1..8
        k = 0
        while k < 8 and i + 2 * k + 1 < n and isZ[i + 2 * k]:
            k += 1; cand(1 + 2 * k, 2 * k, 'ZL')
        # repeated dict word x 3..8
        if isD[i]:
            k = 1
            while k < 8 and i + k < n and f[start + i + k] == f[start + i]:
                k += 1
                if k >= 3: cand(2, k, 'R')
        # L D x 1..44
        if i + 1 < n and isD[i + 1]:
            k = 0
            while k < 44 and i + 1 + k < n and isD[i + 1 + k]:
                k += 1; cand(1 + 2 + k, 1 + k, 'LD')
        # L D L D x 1..41
        if i + 3 < n and isD[i + 1] and isD[i + 3]:
            k = 0
            while k < 41 and i + 3 + k < n and isD[i + 3 + k]:
                k += 1; cand(1 + 4 + 1 + k, 3 + k, 'LDLD')
        best[i] = b; how[i] = h
    # walk
    i = 0; ops = []
    while i < n:
        kind, k = how[i]; ops.append((kind, k, start + i)); i += k
    return best[0], ops

def emit(f, ops, index):
    """op bytes + literal words for a list of parsed ops."""
    ob, lit = bytearray(), []
    for kind, k, s in ops:
        w = f[s:s + k]
        if kind == 'Z': ob.append(k - 1)
        elif kind == 'D': ob.append(0x1D + k); ob += bytes(index[x] for x in w)
        elif kind == 'L': ob.append(0x49 + k); lit += w
        elif kind == 'ZD':
            m = k // 2; ob.append(0x53 + m if m <= 20 else 0x70 + m - 3) if m <= 20 or m >= 3 else None
            ob += bytes(index[x] for x in w[1::2])
        elif kind == 'ZL': ob.append(0x67 + k // 2); lit += w[1::2]
        elif kind == 'R': ob.append(0x76 + k - 3); ob.append(index[w[0]])
        elif kind == 'LD': ob.append(0x7B + (k - 1)); lit.append(w[0]); ob += bytes(index[x] for x in w[1:])
        elif kind == 'LDLD':
            ob.append(0xA8 + (k - 3)); lit.append(w[0]); ob.append(index[w[1]]); lit.append(w[2]); ob += bytes(index[x] for x in w[3:])
    return ob, lit

def split_points(f):
    """Yield positions exactly as ecpl.encode_bank places them: halfway (on a
    tile boundary), then every 64 tiles after the last yield. (A frame that
    takes more slices than Sega's two shows a video frame late.)"""
    half = (len(f) // 2) // 16 * 16
    pts, p = [], half
    if half > 64 * 16:
        pts += list(range(64 * 16, half, 64 * 16))
    while 0 < p < len(f):
        pts.append(p)
        p += 64 * 16
    return pts

def encode_bank(frames, iters=3):
    freq = Counter(w for f in frames for w in f if w)
    dict_words = [w for w, _ in freq.most_common(256)]
    for it in range(iters):
        index = {w: i for i, w in enumerate(dict_words)}
        parsed = []
        use = Counter(); litc = Counter()
        for f in frames:
            segs = [0] + split_points(f) + [len(f)]
            fo = []
            for a, b in zip(segs, segs[1:]):
                _, ops = parse_frame(f, index, a, b); fo.append(ops)
                for kind, k, s in ops:
                    for x in f[s:s + k]:
                        if x: (use if x in index else litc)[x] += 1
            parsed.append(fo)
        # re-pick the dictionary: words in it that are used, plus the most frequent literals
        score = Counter({w: c for w, c in use.items()})
        score.update(litc)
        dict_words = [w for w, _ in score.most_common(256)]
    index = {w: i for i, w in enumerate(dict_words)}
    bank = bytearray(b''.join(w.to_bytes(2, 'big') for w in dict_words).ljust(512, b'\0'))
    offs = []
    for f, fo in zip(frames, parsed):
        ob, lit = bytearray(), []
        for j, ops in enumerate(fo):
            if j: ob.append(0xF8)
            o, l = emit(f, ops, index); ob += o; lit += l
        ob.append(0xFF)
        lo = len(bank); bank += b''.join(w.to_bytes(2, 'big') for w in lit)
        if len(bank) % 2: bank.append(0)
        oo = len(bank); bank += ob
        if len(bank) % 2: bank.append(0)
        offs.append((lo, oo))
    return bytes(bank), offs
