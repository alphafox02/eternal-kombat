"""Which Scorpion pose stands in for each of Blade's poses.

Blade's four compressed sheets ($40-$43, 293 poses) were catalogued visually
(shots/blade_sheet_*.png from ecdraw). Each range below says what Blade is
doing there; it is filled with the matching MK action's poses, spread in
order across the range. 'none' = an extra body-part object (Blade draws some
moves as two objects); Scorpion is a single image, so that part is left empty.
"""

# (sheet, first, last, action[, first_pose, last_pose])
RANGES = [
    # sheet $40: stance, kicks, jumps, taunt, block, gauntlet throws
    (0x40, 0x00, 0x02, 'idle'),
    (0x40, 0x03, 0x05, 'jump_up'),
    (0x40, 0x06, 0x08, 'crouch_c'),
    (0x40, 0x09, 0x0B, 'crouch'),
    (0x40, 0x0C, 0x0D, 'idle'),
    (0x40, 0x0E, 0x0E, 'walk_fwd'),
    (0x40, 0x0F, 0x12, 'jump_fwd'),
    (0x40, 0x13, 0x14, 'btn_z'),
    (0x40, 0x15, 0x15, 'btn_c'),     # close-range A/B (was thought an extra part; it's the knee)
    (0x40, 0x16, 0x1B, 'idle'),
    (0x40, 0x1C, 0x1C, 'walk_fwd'),
    (0x40, 0x1D, 0x1D, 'btn_x'),
    (0x40, 0x1E, 0x1E, 'crouch'),
    (0x40, 0x1F, 0x21, 'jump_z'),
    (0x40, 0x22, 0x22, 'crouch_c'),
    (0x40, 0x23, 0x23, 'btn_z'),
    (0x40, 0x24, 0x26, 'jump_fwd'),
    (0x40, 0x27, 0x28, 'sweep'),
    (0x40, 0x29, 0x37, 'idle'),
    (0x40, 0x38, 0x3D, 'jump_back'),
    (0x40, 0x3E, 0x41, 'hit_high'),
    (0x40, 0x42, 0x5D, 'block'),
    (0x40, 0x5E, 0x6F, 'spear'),
    # sheet $41: punches, projectile, hit, dizzy
    (0x41, 0x00, 0x00, 'idle'),
    (0x41, 0x01, 0x04, 'crouch'),
    (0x41, 0x05, 0x06, 'jump_c'),
    (0x41, 0x07, 0x08, 'sweep'),
    (0x41, 0x09, 0x0C, 'btn_x'),
    (0x41, 0x0D, 0x0E, 'uppercut'),
    (0x41, 0x0F, 0x14, 'btn_c'),
    (0x41, 0x15, 0x15, 'walk_fwd'),     # (MK's back walk is its forward walk reversed: no art of its own)
    (0x41, 0x16, 0x23, 'btn_a'),
    (0x41, 0x24, 0x3C, 'hit_high'),
    (0x41, 0x3D, 0x62, 'spear'),
    # sheet $42: victory, hit reactions, knockdown, gauntlet swings, crouch block
    (0x42, 0x00, 0x02, 'idle'),
    (0x42, 0x03, 0x0B, 'roundhouse'),
    (0x42, 0x0C, 0x0C, 'knockdown'),
    (0x42, 0x0D, 0x0E, 'uppercut'),
    (0x42, 0x0F, 0x13, 'hit_kick'),
    (0x42, 0x14, 0x16, 'btn_x'),
    (0x42, 0x17, 0x18, 'knockdown'),
    (0x42, 0x19, 0x23, 'btn_x'),
    (0x42, 0x24, 0x27, 'hit_high'),
    (0x42, 0x28, 0x35, 'teleport'),
    (0x42, 0x36, 0x38, 'crouch_block'),
    (0x42, 0x39, 0x3F, 'hit_low'),
    # sheet $43: walk-in, victory, run, flying kick, dive
    (0x43, 0x00, 0x02, 'walk_fwd'),
    (0x43, 0x03, 0x03, 'btn_c'),
    (0x43, 0x04, 0x05, 'uppercut'),
    (0x43, 0x06, 0x09, 'walk_fwd'),
    (0x43, 0x0A, 0x0B, 'idle'),
    (0x43, 0x0C, 0x0D, 'jump_z'),
    (0x43, 0x0E, 0x0F, 'crouch'),
    (0x43, 0x10, 0x11, 'jump_fwd'),
]


# Measured: frames Blade actually shows per input (tools/ecprobe.py in a duel,
# extracted/ec_probe/blade.json). EC: X/Y/Z punches, A/B/C kicks, QCF+C
# projectile. These override RANGES. Each group is in the order EC plays it.
MEASURED = [
    ('idle',        ['40:00', '40:01', '40:02']),
    # Blade's one walk cycle: forward (state 8) plays 40:16..40:1B, back
    # (state 4) the same frames reversed - as MK, whose back walk is its
    # forward walk reversed. mkinputs drives MK's full 9-pose cycle on
    # 40:64-40:6C (WALK_SEQ); these 6 hold the matching poses meanwhile.
    # Blocking a hit is 42:36 (state 7).
    ('walk_fwd',    ['40:16=0', '40:17=1', '40:18=3', '40:19=4', '40:1a=6', '40:1b=7']),   # mkinputs WALK_EC_POSES
    ('block',       ['42:36']),
    ('crouch_block', ['42:38']),
    ('crouch',      ['40:1e', '40:06']),
    ('jump_up',     ['41:00', '41:01', '41:02', '41:03', '41:04']),
    # move $34 (spear, back, back + LP) plays all of these, in this order
    ('spear',       ['40:60', '40:61', '40:62', '40:63', '42:28', '42:29', '42:2a', '42:2b',
                     '42:2c', '42:2d', '42:2e', '42:2f', '42:30', '42:31', '40:5e', '40:5f',
                     '42:32', '42:33', '42:34', '42:35']),
    ('walk_fwd',    ['40:64', '40:65', '40:66', '40:67', '40:68', '40:69', '40:6a', '40:6b',
                     '40:6c']),                      # MK's walk poses 1-9, in order (mkinputs WALK_FRAMES)
    ('walk_fwd',    ['40:6d']),
    # Hit (any button, probed in a duel): EC plays 42:01 (6 frames), 42:26 (6),
    # 42:24 (6-12; also the knockdown's first frame), then 42:01 again for ~10
    # while recovering (PLYR's code puts the script's first frame back, not the
    # script). So 42:26 is MK's hit, 42:24 the stagger, 42:01 the late recovery
    # flinch that brackets them (scorpion_full.hit_pose). 42:25/42:27: unused.
    ('hit_high',    ['42:26', '42:24', '42:01', '42:25', '42:27']),
    # dazed (EC's dizzy: FINISH HIM, a spear daze, a stage Overkill's stun):
    # MK's FINISH HIM sway, poses 5-11 of tools/mkdizzy.py, played by mkinputs
    # at MK's timing (DAZE_SEQ). 41:25/41:26 are Blade's dizzy frames; 41:47-41:4c belong
    # to his removed specials
    ('dizzy',       ['41:25', '41:26', '41:47', '41:48', '41:49', '41:4a', '41:4c']),
    # lying on the ground after a knock-down (state $7FFF; an Overkill ends
    # here): MK's flat pose (tools/mkdizzy.py, pose 13), not the fall's start
    ('lying',       ['42:0c']),
    ('knockdown',   ['42:18', '42:17']),
    ('btn_c',       ['40:12', '40:13']),                 # EC A: knee      -> MK low kick
    ('btn_z',       ['41:14', '41:13']),                 # EC B: front kick -> MK high kick
    ('roundhouse',  ['40:0c', '40:0d', '40:0e', '40:0f']),  # EC C: spin kick
    ('btn_a',       ['41:3e', '42:12', '42:13']),        # EC X: jab        -> MK low punch
    # EC X up close: Blade's double punch, cut to one punch (mkinputs CLOSE_JAB_CUT);
    # 41:46 sat in the spear range and showed MK's spear-with-rope pose
    ('btn_a',       ['41:46', '42:19', '42:1a', '42:1b', '42:1c', '42:1d', '42:1e']),
    ('idle',        ['42:1f', '42:20', '42:21', '42:22']),   # where Blade punched again: MK's stance
    ('idle',        ['41:3a=3']),       # the teleport's frozen double (mkinputs GHOST_FRAME): MK's idle pose 3
    ('btn_x',       ['40:1c', '40:1d', '40:37']),        # EC Y: straight   -> MK high punch
    ('btn_z',       ['42:0d', '42:0e', '42:0f', '42:10']),  # EC Z: overhead -> MK high kick (MK has 4 attack buttons)
    ('crouch_c',    ['40:22', '40:27', '40:07']),        # down+A/B
    ('sweep',       ['43:0e', '43:0f', '43:0d']),        # down+C
    ('crouch_a',    ['40:08', '40:09', '40:0a', '40:0b']),  # down+X
    ('uppercut',    ['42:02', '42:03', '42:04']),        # down+Y = MK down + high punch: uppercut
    ('crouch_z',    ['42:05', '42:06', '42:07']),        # down+Z -> MK crouching high kick
    # move $35 (down, back + HP): MK's teleport punch, played from mkinputs'
    # own script (TELE_STEPS); the punch coming in keeps Blade's dash frame 41:62 (its attack box)
    ('teleport_mk', ['41:16=0', '41:17=1', '41:30=2', '41:31=3', '41:32=4', '41:62=5', '41:34=6',
                     '41:61=4']),
    # jump attacks (2-player probe, extracted/ec_probe/blade_2p.json). MK button
    # names in the captures: a LP, x HP, c LK, z HK.
    # straight up: MK's own near-upright kick and punch (tools/mkmoves.py
    # jumpup_*); mkinputs JUMP_UP swaps them in while he jumps straight up.
    # EC's C straight up plays 41:15, 40:24, 40:23, 40:25 (only then)
    ('jumpup_c',    ['41:36=3', '41:37=4', '41:15=3', '40:24=4', '40:23=5', '40:25=6']),
    ('jumpup_a',    ['41:38=3', '41:39=4']),
    ('jump_a',      ['41:07', '41:08']),                 # jump + X (LP)
    ('jump_x',      ['42:08', '42:09', '42:0a', '42:0b']),  # jump + Y (HP)
    ('jump_c',      ['41:06']),                          # jump + A (LK)
    ('jump_z',      ['40:03', '43:03', '41:4b']),        # jump + B/C/Z (HK: flying kick)
    # fatality (tools/mkfatality.py), in frames of Blade's removed specials
    ('fatality',          ['41:52', '41:53', '41:54', '41:55', '41:56', '41:57', '41:58', '41:59']),
    ('fatality_fire',     ['41:5a', '41:5b', '41:5c', '41:5d', '41:5e', '41:5f']),
    ('fatality_skeleton', ['41:40', '41:41', '41:42', '41:43', '41:44', '41:45']),
]


def assignments(aliases=None, exact=True, extra=()):
    """{(sheet, frame): (action, k, n)}: k-th of n frames in its group
    (n None: k is the pose itself). Measured groups win over the visual RANGES.
    aliases: {action: action} for a fighter with no capture of some action;
    exact False: 'frame=pose' entries are spread like the rest (the pose
    numbers are Scorpion's)."""
    aliases = aliases or {}
    out = {}
    for r in RANGES:
        sheet, a, b, action = r[:4]
        n = b - a + 1
        for i, f in enumerate(range(a, b + 1)):
            out[(sheet, f)] = (aliases.get(action, action), i, n)
    for action, frames in MEASURED:
        n = len(frames)
        for i, k in enumerate(frames):
            k, _, pose = k.partition('=')            # 'sheet:frame=pose': that pose exactly
            s, f = (int(x, 16) for x in k.split(':'))
            act = aliases.get(action, action)
            out[(s, f)] = (act, int(pose), None) if pose and exact else (act, i, n)
    for action, frames in extra:                     # a fighter's own exact poses (always exact)
        for k in frames:
            k, _, pose = k.partition('=')
            s, f = (int(x, 16) for x in k.split(':'))
            out[(s, f)] = (action, int(pose), None)
    return out
