#!/usr/bin/env python3
"""Capture the "Toasty!" easter egg (Dan Forden's face + voice) from
Ultimate Mortal Kombat 3 (USA, Genesis) into extracted/umk3_toasty/.

From states/umk3_select.state: player 2 joins, Reptile vs Sub-Zero; the
first uppercut knocks Sub-Zero through the ceiling of the opening stage into
the Kombat Temple (no Toasty roll on a knock-through), then uppercuts are
tried at increasing delays until the game rolls a Toasty on its own (or,
with --force, with the 1-in-15 roll patched to always pass in a temporary
copy of the ROM). The face is read out of the VDP, frame by frame.

How the game does it (68000 code, ROM offsets):
  $024B6A.. launch reactions (uppercut and friends) start effect $0E
            (jsr $31C3E, d0=$0E) - not on stage knock-through uppercuts
  $032604   effect $0E: skip if either fighter is $1A/$1B; sleep 19 frames;
            random(15) == 5 ($028964) -> $03269C, else one of 5 other
            sounds (table $032676)
  $03269C   needs game state $FFF210 != 1 and both energies ($FFF228,
            $FFF39A) non-zero (the uppercut didn't win the round)
  $0326BE   no Toasty if either fighter is $17 (Noob Saibot); spawn image
            $801700DE, x speed -8 px/frame for 6 frames, play sound $25,
            hold 32 frames, +8 px/frame for 16 frames, delete
Sound $25 is GEMS sequence $25: sample 37 of the bank at $3AC0AC
(2036 bytes of 4-bit DPCM, low nibble first, deltas from the table at Z80
$0200 of the driver). toasty_gpgx.wav is that sequence played on its own by
the game's sound driver (music stopped through the GEMS command queue);
toasty_rom.wav is the sample decoded straight from the ROM.

    umk3toasty.py [--force] [--video shots/umk3_toasty.mp4] [--max-tries 600]
"""
import argparse, json, os, shutil, sys, tempfile, wave
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image
import scd, vdp
from inputs import ROOT, require

OUT = os.path.join(ROOT, 'extracted', 'umk3_toasty')
ROLL_BRANCH = 0x32652            # beq.b $3269C (random(15) == 5); bra.b = always
SAMPLE_BANK, SAMPLE_INDEX = 0x3AC0AC, 37
DRIVER = 0x3A4672                # GEMS Z80 driver image; DPCM deltas at +$200
SEQ_TOASTY = 0x25
MUSIC = 0x41                     # Kombat Temple song (GEMS stop-song target)
ZRAM = 0x10010                   # Z80 RAM in a Genesis Plus GX cart savestate
GEMS_QUEUE, GEMS_WRITE = 0x1B40, 0x36
WRAM = 0x10                      # 68000 RAM ($FF0000) in the savestate, words byte-swapped
UPPERCUT = [{'down'}] * 6 + [{'down', 'x'}] * 4 + [{'down'}] * 4


def ram_word(state, addr):
    o = WRAM + (addr - 0xFF0000)
    return state[o + 1] << 8 | state[o]


def gems(core, *cmds):
    """Queue GEMS commands (lists of bytes) the way the game's 68000 API does."""
    st = bytearray(core.snapshot())
    i = st[ZRAM + GEMS_WRITE]
    for cmd in cmds:
        for b in [0xFF] + list(cmd):
            st[ZRAM + GEMS_QUEUE + i] = b
            i = (i + 1) & 0x3F
    st[ZRAM + GEMS_WRITE] = i
    core.restore(bytes(st))


def temple(core):
    """Select screen -> Reptile vs Sub-Zero, close together in the Kombat Temple."""
    core.load_state(os.path.join(ROOT, 'states', 'umk3_select.state'))
    core.run(10)
    for port, btn, wait in [(1, 'start', 30), (0, 'right', 10), (0, 'a', 30),
                            (1, 'down', 10), (1, 'left', 10), (1, 'a', 660)]:
        core.press([btn], 4, port=port)
        core.run(wait)
    core.run(60)
    hold(core, [{'right'}] * 100)
    core.run(5)
    hold(core, UPPERCUT)            # through the ceiling into the temple
    core.run(400)
    hold(core, [{'right'}] * 60)
    core.run(5)
    st = core.snapshot()
    chars = ram_word(st, 0xFF0126), ram_word(st, 0xFF0128)
    assert chars == (0x13, 0x15), f'unexpected fighters {chars}'
    return st


def hold(core, seq):
    for b in seq:
        core.buttons[0] = set(b)
        core.run(1)
    core.buttons[0] = set()


def face_anchor(v):
    return next((s for s in v.sprites() if s['w'] == 4 and s['h'] == 4
                 and s['x'] >= 250 and s['y'] >= 160), None)


def find_delay(core, start, tries):
    for k in range(tries):
        core.restore(start)
        core.run(k)
        hold(core, UPPERCUT)
        for f in range(20, 64, 3):
            core.run(3)
            if face_anchor(vdp.VDPState(core.snapshot())):
                return k
    return None


def composite(v, sprites, pal_line):
    """RGBA image of the given sprites, and its top-left on screen."""
    x0 = min(s['x'] for s in sprites)
    y0 = min(s['y'] for s in sprites)
    x1 = max(s['x'] + 8 * s['w'] for s in sprites)
    y1 = max(s['y'] + 8 * s['h'] for s in sprites)
    pal = np.array(v.palette(pal_line), np.uint8)
    img = np.zeros((y1 - y0, x1 - x0, 4), np.uint8)
    for s in reversed(sprites):                      # earlier sprites in the list win
        px = v.sprite_pixels(s)
        ys, xs = np.nonzero(px)
        img[ys + s['y'] - y0, xs + s['x'] - x0, :3] = pal[px[ys, xs]]
        img[ys + s['y'] - y0, xs + s['x'] - x0, 3] = 255
    return img, (x0, y0)


def capture(core, start, k):
    """Frame-by-frame record from the uppercut input on: face sprites, energy, audio."""
    core.restore(start)
    core.run(k)
    core.audio.clear()
    rows, audio, tiles, pal_line = [], [], None, None
    for f in range(150):
        core.buttons[0] = set(UPPERCUT[f]) if f < len(UPPERCUT) else set()
        core.run(1)
        audio.append(b''.join(core.audio))
        core.audio.clear()
        st = core.snapshot()
        v = vdp.VDPState(st)
        if tiles is None and (a := face_anchor(v)):
            pal_line = a['pal']
            tiles = set()
            for s in v.sprites():
                if s['pal'] == pal_line and 0 <= s['tile'] - a['tile'] < 64 and abs(s['x'] - a['x']) < 64:
                    tiles.update(range(s['tile'], s['tile'] + s['w'] * s['h']))
        spr = [s for s in v.sprites() if tiles and s['pal'] == pal_line and s['tile'] in tiles
               and -32 < s['x'] < 320 and -32 < s['y'] < 224]
        rows.append(dict(f=f, p2_energy=ram_word(st, 0xFFF39A), sprites=spr, vdp=v,
                         frame=core.frame.copy()))
    core.buttons[0] = set()
    pcm = np.frombuffer(b''.join(audio), '<i2').reshape(-1, 2)
    return rows, pcm, pal_line


def clean_voice(core, start):
    """Sound $25 alone, played by the game's driver with the music stopped."""
    core.restore(start)
    core.run(2)
    gems(core, [0x12, MUSIC])
    core.run(30)
    core.audio.clear()
    gems(core, [0x10, SEQ_TOASTY])
    core.run(90)
    pcm = np.frombuffer(b''.join(core.audio), '<i2').reshape(-1, 2)[:, 0]
    nz = np.nonzero(np.abs(pcm.astype(int)) > 50)[0]
    return pcm[max(0, nz[0] - 32):nz[-1] + 32], (nz[-1] - nz[0]) / core.sample_rate


def rom_sample(rom):
    e = rom[SAMPLE_BANK + 12 * SAMPLE_INDEX:SAMPLE_BANK + 12 * SAMPLE_INDEX + 12]
    flags, addr = e[0], int.from_bytes(e[1:4], 'little')
    size = int.from_bytes(e[6:8], 'little')
    data = rom[SAMPLE_BANK + addr:SAMPLE_BANK + addr + size]
    deltas = [d - 256 if d > 127 else d for d in rom[DRIVER + 0x200:DRIVER + 0x210]]
    v, out = 0x80, []
    for b in data:
        for n in (b & 15, b >> 4):
            v = (v + deltas[n]) & 0xFF
            out.append(v)
    return dict(flags=flags, rom_offset=SAMPLE_BANK + addr, bytes=size, deltas=deltas), np.array(out, np.uint8)


def write_wav(path, pcm, rate, width=2):
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(width)
        w.setframerate(int(round(rate)))
        w.writeframes(pcm.tobytes())


def onset(mix, voice):
    """Sample index in mix where voice starts (cross-correlation)."""
    from scipy.signal import correlate
    m = mix.astype(float) - mix.mean()
    s = voice.astype(float) - voice.mean()
    c = correlate(m, s, mode='valid')
    return int(np.argmax(c))


def video(core, start, k, out, first, last):
    from finishvideo import Rec
    core.restore(start)
    core.run(max(0, k - 30))
    core.audio.clear()
    r = Rec(core, out)
    r.run(min(k, 30))
    for b in UPPERCUT:
        r.run(1, b)
    r.run(last + 40 - len(UPPERCUT))
    r.close()
    shutil.rmtree(r.tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--force', action='store_true', help='patch the 1-in-15 roll to always pass (temp ROM copy)')
    ap.add_argument('--video', help='also record a clip with sound, e.g. shots/umk3_toasty.mp4')
    ap.add_argument('--max-tries', type=int, default=600)
    a = ap.parse_args()

    rom_path = require('umk3_gen').path
    rom = open(rom_path, 'rb').read()
    tmp = tempfile.mkdtemp()
    if a.force:
        p = bytearray(rom)
        assert p[ROLL_BRANCH] == 0x67
        p[ROLL_BRANCH] = 0x60
        rom_path = os.path.join(tmp, 'umk3_forced.md')
        open(rom_path, 'wb').write(p)
    try:
        core = scd.Core(audio=True, saves=os.path.join(tmp, 'saves'))
        core.load(rom_path)
        start = temple(core)
        k = find_delay(core, start, a.max_tries)
        if k is None:
            raise SystemExit('no Toasty within --max-tries delays')
        print(f'Toasty rolled after a {k}-frame delay' + (' (forced)' if a.force else ''))
        rows, mix, pal_line = capture(core, start, k)
        voice, voice_len = clean_voice(core, start)
        meta, dpcm = rom_sample(rom)

        os.makedirs(OUT, exist_ok=True)
        for f in os.listdir(OUT):
            p = os.path.join(OUT, f)
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
        os.makedirs(os.path.join(OUT, 'screen'))
        hit = next(r['f'] for r in rows if r['p2_energy'] < rows[0]['p2_energy'])
        seen = [r for r in rows if r['sprites']]
        rest = min(seen, key=lambda r: min(s['x'] for s in r['sprites']))
        img, (rx, ry) = composite(rest['vdp'], rest['sprites'], pal_line)
        Image.fromarray(img, 'RGBA').save(os.path.join(OUT, 'face.png'))
        Image.fromarray(img, 'RGBA').resize((img.shape[1] * 4, img.shape[0] * 4), Image.NEAREST) \
            .save(os.path.join(OUT, 'face_x4.png'))
        tile_ids = sorted({t for s in rest['sprites'] for t in range(s['tile'], s['tile'] + s['w'] * s['h'])})
        timeline, shapes = [], set()
        for r in seen:
            im, (x, y) = composite(r['vdp'], r['sprites'], pal_line)
            shapes.add(b''.join(r['vdp'].vram[t * 32:t * 32 + 32] for t in tile_ids)
                       + bytes(str(r['vdp'].cram_raw[pal_line * 16:pal_line * 16 + 16]), 'ascii'))
            timeline.append(dict(frame_after_hit=r['f'] - hit, x=x, y=y,
                                 visible_px=int(min(320, x + img.shape[1]) - max(0, x))))
            Image.fromarray(r['frame']).save(os.path.join(OUT, 'screen', f'{r["f"] - hit:03d}.png'))
        v = rest['vdp']
        pal = dict(line=pal_line, cram_9bit=[f'{c:03X}' for c in v.cram_raw[pal_line * 16:pal_line * 16 + 16]],
                   rgb=[list(c) for c in v.palette(pal_line)], note='index 0 is transparent')
        sw = Image.new('RGB', (16 * 16, 16))
        for i, c in enumerate(v.palette(pal_line)):
            sw.paste(tuple(c), (i * 16, 0, i * 16 + 16, 16))
        sw.save(os.path.join(OUT, 'palette.png'))
        json.dump(pal, open(os.path.join(OUT, 'palette.json'), 'w'), indent=1)

        mono = mix[:, 0]
        write_wav(os.path.join(OUT, 'capture_mix.wav'), mono, core.sample_rate)
        write_wav(os.path.join(OUT, 'toasty_gpgx.wav'), voice, core.sample_rate)
        rate = 2 * meta['bytes'] / voice_len
        write_wav(os.path.join(OUT, 'toasty_rom.wav'), ((dpcm.astype(np.int16) - 128) << 8), rate)
        spf = core.sample_rate / core.fps
        v0 = onset(mono, voice)
        info = dict(
            source='Ultimate Mortal Kombat 3 (USA) Genesis, Reptile (P1) uppercuts Sub-Zero (P2), Kombat Temple',
            forced=a.force, delay_frames=k, fps=core.fps,
            hit_frame=hit, note_frames='frame 0 = first frame of the uppercut input; hit = P2 energy drops',
            face=dict(size=list(img.shape[1::-1]), rest_xy=[rx, ry], palette_line=pal_line,
                      vram_tiles=sorted(set(s['tile'] for s in rest['sprites'])),
                      sprites_at_rest=[dict(x=s['x'], y=s['y'], w=s['w'], h=s['h'], tile=s['tile'])
                                       for s in rest['sprites']],
                      visible_at_rest=[min(320, rx + img.shape[1]) - rx, min(224, ry + img.shape[0]) - ry],
                      image_changes=len(shapes) > 1,
                      note='x/y = top-left of the 56x56 box on the 320x224 screen; sprites past x=320 are not drawn',
                      first_frame_after_hit=timeline[0]['frame_after_hit'],
                      last_frame_after_hit=timeline[-1]['frame_after_hit'],
                      timeline=timeline),
            voice=dict(start_frame_after_hit=round(v0 / spf - hit, 1),
                       gems_sequence=SEQ_TOASTY, sample=dict(meta, index=SAMPLE_INDEX, bank=SAMPLE_BANK,
                                                             samples=len(dpcm), format='4-bit DPCM, low nibble first'),
                       length_s=round(voice_len, 3), rate_hz=round(rate)),
            trigger=dict(chance='1 in 15 per qualifying uppercut (random(15)==5)', delay='roll 19 frames after the hit',
                         excluded=['either fighter is $17 (Noob Saibot)', 'either fighter is $1A or $1B',
                                   'uppercut that ends the round (an energy is 0)', 'game state $FFF210 == 1',
                                   'stage knock-through uppercuts (no roll)'],
                         otherwise='one of 5 other sound effects (indices $0B,$7C,$7E,$7A,$26 at $032676)'))
        for f in info['face']['sprites_at_rest']:
            f['x'] -= rx
            f['y'] -= ry
        json.dump(info, open(os.path.join(OUT, 'toasty.json'), 'w'), indent=1)
        strip = [Image.fromarray(r['frame']) for r in seen[::2]]
        sheet = Image.new('RGB', (160 * 8, 112 * ((len(strip) + 7) // 8)))
        for i, im in enumerate(strip):
            sheet.paste(im.resize((160, 112)), ((i % 8) * 160, (i // 8) * 112))
        sheet.save(os.path.join(OUT, 'sheet.png'))
        print(f'face {img.shape[1]}x{img.shape[0]} at rest ({rx},{ry}), frames {timeline[0]["frame_after_hit"]}..'
              f'{timeline[-1]["frame_after_hit"]} after the hit; voice at +{info["voice"]["start_frame_after_hit"]}'
              f' frames, {voice_len:.3f}s, ~{rate:.0f} Hz -> {os.path.relpath(OUT, ROOT)}')
        if a.video:
            out = os.path.abspath(a.video)
            video(core, start, k, out, seen[0]['f'], seen[-1]['f'])
            print('->', os.path.relpath(out, ROOT))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()
