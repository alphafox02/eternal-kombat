#!/usr/bin/env python3
"""MK's own animation for Scorpion's basic attacks.

EC plays an attack from a move script: a 20-byte header (word, word = steps
allowed ($C4), long vx, long vy, long, word, word) then 12-byte steps
(frame, ticks of 2 frames, $E6 dx, $E8 dy, $F6 flags, $102 hit data) and a
terminating op (a word < $100). Blade's attacks have 3-5 steps; MK's play 6-10
poses. For each move here a new script is built from MK's capture
(tools/mkmoves.py): every pose of the attack in MK's order and timing, on
frame slots nothing else uses, with Blade's hit step (its frame - so its hit
box - flags, hit data and lunge) on MK's strike (active_pose). mkinputs puts
the scripts in Scorpion's extension block and points his move table ($A6:
longs by move id = $BE) at them.

    mkscripts.py        # print the scripts it would build
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from inputs import ROOT

# EC move id ($BE) -> MK capture (scorpion_map: EC X jab = MK low punch,
# Y = high punch, A knee = low kick, B front kick = high kick, C spin kick =
# roundhouse). Blade's move table entry (module offset of the script header).
MOVES = [
    (1, 'btn_a', 0x409C),
    (2, 'btn_x', 0x40D4),
    (4, 'btn_c', 0x42C8),
    (5, 'btn_z', 0x4284),
    (6, 'roundhouse', 0x4228),
    # up close EC plays other moves for the same buttons (MK doesn't): the
    # same MK animations, with the close moves' own hit steps
    (0x20, 'btn_a', 0x47C4),
    (0x21, 'btn_x', 0x485C),
    (0x23, 'btn_c', 0x492C),
    (0x24, 'btn_z', 0x4964),
    (0x25, 'roundhouse', 0x499C),
    # crouching (MK CD: both crouching punches are the uppercut, both
    # crouching kicks the same low kick; the sweep is MK's back + low kick).
    # The captures crouch down first and stand up after: EC's moves start and
    # end crouched, so those poses are trimmed too ('crouch'). The uppercut
    # strikes on its highest pose and keeps Blade's strike frame 42:03
    # (mkinputs r_launch launches the victim from it). ('reach' put
    # Raiden's strike on his follow-through after the punch and Johnny's on
    # his first crouch: the hit came long after / before the fist went up.)
    (0x0E, 'uppercut', 0x4300, 'crouch', 'height'),
    (0x0F, 'uppercut', 0x4350, 'crouch', 'height'),
    (0x11, 'crouch_c', 0x43E4, 'crouch', 'reach'),
    (0x12, 'crouch_c', 0x4410, 'crouch', 'reach'),
    (0x13, 'sweep', 0x4460, 'crouch', 'reach'),
]
# frame slots no Blade script or code shows and scorpion_map doesn't pin
# (counted by hand from patches.module_frame_words and the move.b #frame sites)
FREE = [(0x40, f) for f in (0x04, 0x05, 0x1F, 0x20, 0x21, 0x26, 0x28, 0x2A, 0x2B, 0x2D, 0x2E, 0x2F,
                            0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x38, 0x39, 0x3A, 0x3B, 0x3C,
                            0x3D, 0x40, 0x41, 0x42, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49, 0x4A,
                            0x4B, 0x4C, 0x4D, 0x4E, 0x4F, 0x50, 0x51, 0x52, 0x53, 0x54, 0x55, 0x56)] + \
       [(0x41, f) for f in (0x23, 0x27, 0x28, 0x29, 0x2A, 0x2B, 0x2C, 0x2D, 0x2E, 0x2F, 0x33, 0x35,
                            0x3B, 0x3C, 0x3F, 0x4F, 0x50, 0x60)] + \
       [(0x42, f) for f in (0x00, 0x14, 0x15, 0x16, 0x23, 0x37, 0x39, 0x3A, 0x3B, 0x3C, 0x3E, 0x3F)] + \
       [(0x43, f) for f in (0x00, 0x01, 0x02, 0x04, 0x05, 0x08)]


HIT_TICKS = 2                 # the strike step lasts at least this (MK's roundhouse shows full reach 2 frames)


MIN_RECORD = 96                # bytes of Blade's layout record a slot needs to hold a whole MK pose


def free_slots():
    """FREE, less slots whose layout record in Blade's .PL is too small for a
    pose (some unused frames have 6-byte records: drawn blank)."""
    import scorpion_full
    pl = open(os.path.join(ROOT, 'extracted', 'ec_us', 'BLA.PL'), 'rb').read()
    W = lambda o: int.from_bytes(pl[o:o + 2], 'big')
    out = []
    for sid, f in FREE:
        res, sheet = scorpion_full.RESOURCES[sid]
        offs = [W(sheet + 6 + 2 * i) for i in range(W(sheet + 4))]
        nxt = min((x for x in set(offs) if x > offs[f]), default=None)
        if nxt is not None and nxt - offs[f] >= MIN_RECORD and offs.count(offs[f]) == 1:
            out.append((sid, f))
    return out


def _load(name, mk_dir='mk_moves'):
    d = os.path.join(ROOT, 'extracted', mk_dir, name)
    P = np.load(os.path.join(d, 'indexed.npy'))
    order = [int(x) for x in open(os.path.join(d, 'order.txt')).read().split()]
    return P, order


def _key(p):
    ys, xs = np.nonzero(p)
    return p[ys.min():ys.max() + 1, xs.min():xs.max() + 1].tobytes() if len(ys) else b''


def sequence(action, mk_dir='mk_moves', trim=''):
    """[(pose, frames)] of the attack itself: MK's runs, without the stance
    poses before it and from the first stance pose after its last attack pose
    (trim 'crouch': crouching poses too)."""
    P, order = _load(action, mk_dir)
    I, _ = _load('idle', mk_dir)
    stance = {_key(p) for p in I}
    if trim == 'crouch':
        C, _ = _load('crouch', mk_dir)
        stance |= {_key(p) for p in C}
    runs = []
    for k in order:
        if runs and runs[-1][0] == k:
            runs[-1][1] += 1
        else:
            runs.append([k, 1])
    is_st = [_key(P[k]) in stance or k == order[0] for k, _ in runs]
    if all(is_st):
        return None, P                              # the capture shows no attack (keep Blade's)
    first = next(i for i, s in enumerate(is_st) if not s)
    last = max(i for i, s in enumerate(is_st) if not s)
    # the attack ends where the fighter is back to a pose seen on the way out
    seq = [tuple(r) for r in runs[first:last + 1]]
    return seq, P


def active_pose(P, seq, how='reach'):
    """The strike: of the poses reaching within 8 px of the furthest (how
    'height': the highest), the one MK holds longest (a spin kick's widest
    pose can be a 2-frame blur)."""
    def reach(p):
        if how == 'height':
            ys = np.nonzero(p.any(1))[0]
            return -ys.min() if len(ys) else -999
        xs = np.nonzero(p.any(0))[0]
        return xs.max() if len(xs) else 0
    far = max(reach(P[k]) for k, _ in seq)
    held = {}
    for k, n in seq:
        held[k] = max(held.get(k, 0), n)
    return max((k for k, _ in seq if reach(P[k]) >= far - 8), key=lambda k: held[k])


def blade_script(co, head):
    W = lambda o: int.from_bytes(co[o:o + 2], 'big')
    steps, o = [], head + 20
    while W(o) >= 0x100:
        steps.append(bytes(co[o:o + 12]))
        o += 12
    return bytes(co[head:head + 20]), steps, bytes(co[o:o + 12])


def build(co, mk_dir='mk_moves'):
    """-> (scripts {move id: [(frame word or None for the terminator, bytes)]},
    art [(action, ['ss:ff=pose', ...])]). Frame words are Blade's numbering."""
    free = free_slots()
    scripts, art = {}, []
    shared = {}                                   # action -> {pose: slot} (far and close share)
    claimed = {}                                  # strike frame -> action showing it
    for mid, action, head, *opt in MOVES:
        trim, how = (opt + ['', 'reach'])[:2] if opt else ('', 'reach')
        hdr, steps, term = blade_script(co, head)
        hits = [s for s in steps if s[10:12] != b'\0\0']
        # Blade's last strike (his Y has two; the second reaches), unless one
        # of them also hits crouching victims ($F6 bit 15, as his crouch
        # attacks: his close jab's first punch)
        low = [s for s in hits if s[8] & 0x80]
        hit = low[0] if low else hits[-1]
        hit_frame = int.from_bytes(hit[0:2], 'big')
        seq, P = sequence(action, mk_dir, trim)
        if not seq:
            continue
        active = active_pose(P, seq, how)
        slots, entries = {}, []
        mine = shared.setdefault(action, {})
        if claimed.get(hit_frame, action) != action:
            # another attack strikes on this frame with another MK pose (EC's
            # close A and B share 40:15): use this action's far strike frame
            hit_frame = mine['strike']
        claimed[hit_frame] = action
        mine.setdefault('strike', hit_frame)
        for k, _ in seq:
            if k == active:
                slots[k] = hit_frame
            elif k not in slots:
                if k not in mine:
                    s, f = free.pop(0)
                    mine[k] = s << 8 | f
                slots[k] = mine[k]
        for k, f in slots.items():
            if k == 'strike':
                continue
            entries.append(f'{slots[k] >> 8:02x}:{slots[k] & 0xFF:02x}={k}')
        art.append((action, entries))
        # Blade's wind-up moves him forward (step dx $E6, and ticks of the
        # header speed: flag $0400) before the strike; MK's wind-up does the
        # same, or the strike falls a few px short at the edge of its range
        pre = steps[:steps.index(hit)]
        dx = sum(int.from_bytes(st[4:6], 'big', signed=True) for st in pre)
        slide = sum(int.from_bytes(st[2:4], 'big') for st in pre if int.from_bytes(st[8:10], 'big') & 0x0400)
        out, n_hit, first = [], 0, True
        for k, frames in seq:
            ticks = max(1, round(frames / 2))
            if k == active and not n_hit:
                body = hit[4:12]                      # Blade's lunge, flags, hit data
                ticks = max(ticks, HIT_TICKS)         # long enough to connect
                n_hit = 1
            elif not n_hit:
                flags = 0x0002 | (0x0400 if slide > 0 else 0)   # wind-up (Blade's: flags $0002)
                slide -= ticks
                body = (dx if first else 0).to_bytes(2, 'big', signed=True) + bytes(2) \
                    + flags.to_bytes(2, 'big') + bytes(2)
                first = False
            else:
                body = bytes(8)                       # recovery
            out.append(slots[k].to_bytes(2, 'big') + ticks.to_bytes(2, 'big') + body)
        hdr = hdr[:2] + (len(out) - 1).to_bytes(2, 'big') + hdr[4:]
        scripts[mid] = hdr + b''.join(out) + term
    return scripts, art


def main():
    co = open(os.path.join(ROOT, 'extracted', 'ec_us', 'BLA.CO'), 'rb').read()
    scripts, art = build(co)
    for (mid, action, *_), (_, ent) in zip([m for m in MOVES if m[0] in scripts], art):
        s = scripts[mid]
        print(f'move {mid} {action}: {len(s) // 12 - 2} steps; poses {ent}')
        for o in range(20, len(s), 12):
            print('   ', s[o:o + 12].hex(' ', 2))


if __name__ == '__main__':
    main()


# EC's throw (close + Y, move $0D) is played by Blade's module code, which
# shows 42:10, 42:0F, 42:0E (the victim lifted), 42:0D (the victim overhead),
# then 42:0F, 42:10 again. Nothing else shows those four frames: they get MK's
# throw (tools/mkmoves.py throw: walk in, toward + Z) - the grab, the pull,
# the pose before the longest-held one, and the longest-held one (Scorpion
# and Sub-Zero: rolled on his back, feet up, the victim going over).
THROW_FRAMES = ('42:10', '42:0f', '42:0e', '42:0d')


def throw_art(mk_dir='mk_moves'):
    P, order = _load('throw', mk_dir)
    skip = set()
    for other in ('idle', 'walk_fwd'):
        Q, _ = _load(other, mk_dir)
        skip |= {_key(p) for p in Q}
    runs = []
    for k in order:
        if runs and runs[-1][0] == k:
            runs[-1][1] += 1
        else:
            runs.append([k, 1])
    act = [r for r in runs if _key(P[r[0]]) not in skip]
    if len(act) < 4:
        return []
    first_end = next((i for i, r in enumerate(act) if i and r[0] == act[0][0]), len(act))
    act = act[:first_end]                     # one throw (the capture may repeat)
    peak = max(range(len(act)), key=lambda i: act[i][1])
    picks = [act[0][0], act[1][0], act[max(2, peak - 1)][0], act[peak][0]]
    return [('throw', [f'{f}={k}' for f, k in zip(THROW_FRAMES, picks)])]
