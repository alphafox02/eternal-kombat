#!/usr/bin/env python3
"""Minimal libretro front-end for Genesis Plus GX: Sega CD, scriptable.

Headless use (screenshots, scripted input, savestates, RAM dumps):

    scd.py run DISC.cue --script "wait 900; press start 4; wait 600; shot title"

Script commands (separated by ';' or newlines):
    wait N                 run N frames with no input
    press BTN[+BTN] [N]    hold buttons for N frames (default 2), then release
    hold BTN[+BTN] N       same as press (alias)
    shot NAME              save the current frame to OUT/NAME.png
    save NAME / load NAME  savestate to/from OUT/NAME.state
    dump NAME              write every memory region the core exposes to OUT/NAME.<region>.bin
    every N                (headless) also save a numbered shot every N frames

Buttons: up down left right a b c x y z start mode

As a library: from scd import Core
"""
import argparse, ctypes as C, os, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_CORE = os.path.expanduser(
    '~/.local/lib/python3.14/site-packages/stable_retro/cores/genesis_plus_gx_libretro.so')
DEFAULT_BIOS = os.path.join(ROOT, 'bios')

# libretro joypad ids
RID = dict(b=0, y=1, select=2, start=3, up=4, down=5, left=6, right=7, a=8, x=9, l=10, r=11)
# Genesis button -> libretro id, Genesis Plus GX default mapping
GEN = dict(a=RID['y'], b=RID['b'], c=RID['a'], x=RID['l'], y=RID['x'], z=RID['r'],
           start=RID['start'], mode=RID['select'],
           up=RID['up'], down=RID['down'], left=RID['left'], right=RID['right'])

# This core build dereferences every option value without checking, so the
# front-end must answer every GET_VARIABLE. These are GPGX's usual defaults.
DEFAULT_OPTIONS = {
    'genesis_plus_gx_system_hw': 'auto', 'genesis_plus_gx_region_detect': 'auto',
    'genesis_plus_gx_bios': 'disabled', 'genesis_plus_gx_bram': 'per bios',
    'genesis_plus_gx_addr_error': 'enabled', 'genesis_plus_gx_lock_on': 'disabled',
    'genesis_plus_gx_ym2413': 'auto', 'genesis_plus_gx_dac_bits': 'disabled',
    'genesis_plus_gx_audio_filter': 'disabled', 'genesis_plus_gx_lowpass_range': '60',
    'genesis_plus_gx_render': 'single field', 'genesis_plus_gx_overscan': 'disabled',
    'genesis_plus_gx_aspect_ratio': 'auto', 'genesis_plus_gx_force_dtack': 'enabled',
    'genesis_plus_gx_lcd_filter': 'disabled', 'genesis_plus_gx_gg_extra': 'disabled',
    'genesis_plus_gx_blargg_ntsc_filter': 'disabled', 'genesis_plus_gx_invert_mouse': 'disabled',
    'genesis_plus_gx_gun_cursor': 'disabled',
}
EMPTY = C.c_char_p(b'')

ENV_GET_CAN_DUPE = 3
ENV_GET_SYSTEM_DIRECTORY = 9
ENV_SET_PIXEL_FORMAT = 10
ENV_GET_VARIABLE = 15
ENV_GET_VARIABLE_UPDATE = 17
ENV_GET_SAVE_DIRECTORY = 31
ENV_SET_MEMORY_MAPS = 36 | 0x10000


class GameInfo(C.Structure):
    _fields_ = [('path', C.c_char_p), ('data', C.c_void_p), ('size', C.c_size_t), ('meta', C.c_char_p)]


class Geometry(C.Structure):
    _fields_ = [('base_width', C.c_uint), ('base_height', C.c_uint), ('max_width', C.c_uint),
                ('max_height', C.c_uint), ('aspect_ratio', C.c_float)]


class Timing(C.Structure):
    _fields_ = [('fps', C.c_double), ('sample_rate', C.c_double)]


class AVInfo(C.Structure):
    _fields_ = [('geometry', Geometry), ('timing', Timing)]


class Variable(C.Structure):
    _fields_ = [('key', C.c_char_p), ('value', C.c_char_p)]


class MemDesc(C.Structure):
    _fields_ = [('flags', C.c_uint64), ('ptr', C.c_void_p), ('offset', C.c_size_t), ('start', C.c_size_t),
                ('select', C.c_size_t), ('disconnect', C.c_size_t), ('len', C.c_size_t),
                ('addrspace', C.c_char_p)]


class MemMap(C.Structure):
    _fields_ = [('descriptors', C.POINTER(MemDesc)), ('num_descriptors', C.c_uint)]


ENV_CB = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
VIDEO_CB = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
AUDIO_CB = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
AUDIO_BATCH_CB = C.CFUNCTYPE(C.c_size_t, C.c_void_p, C.c_size_t)
POLL_CB = C.CFUNCTYPE(None)
STATE_CB = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)


class Core:
    def __init__(self, core=DEFAULT_CORE, bios=DEFAULT_BIOS, options=None, audio=False, saves=None):
        self.lib = C.CDLL(core)
        self.sysdir = C.c_char_p(os.path.abspath(bios).encode())
        saves = saves or os.path.join(ROOT, 'saves')
        os.makedirs(saves, exist_ok=True)
        self.savedir = C.c_char_p(os.path.abspath(saves).encode())
        opts = dict(DEFAULT_OPTIONS, **(options or {}))
        self.options = {k.encode(): C.c_char_p(v.encode()) for k, v in opts.items()}
        self.pixfmt = 1
        self.frame = None                      # HxWx3 uint8
        self.buttons = [set(), set()]          # held Genesis buttons per port
        self.regions = []                      # (name, start, len, ptr)
        self.audio = [] if audio else None
        self.frames = 0
        # keep callbacks alive
        self._cbs = [ENV_CB(self._env), VIDEO_CB(self._video), AUDIO_CB(lambda l, r: None),
                     AUDIO_BATCH_CB(self._audio_batch), POLL_CB(lambda: None), STATE_CB(self._state)]
        L = self.lib
        L.retro_set_environment(self._cbs[0])
        L.retro_init()
        L.retro_set_video_refresh(self._cbs[1])
        L.retro_set_audio_sample(self._cbs[2])
        L.retro_set_audio_sample_batch(self._cbs[3])
        L.retro_set_input_poll(self._cbs[4])
        L.retro_set_input_state(self._cbs[5])
        L.retro_get_memory_data.restype = C.c_void_p
        L.retro_get_memory_size.restype = C.c_size_t
        L.retro_serialize_size.restype = C.c_size_t
        L.retro_load_game.restype = C.c_bool
        L.retro_serialize.restype = C.c_bool
        L.retro_unserialize.restype = C.c_bool

    # --- callbacks -------------------------------------------------------
    def _env(self, cmd, data):
        if cmd == ENV_GET_SYSTEM_DIRECTORY:
            C.cast(data, C.POINTER(C.c_char_p))[0] = self.sysdir
            return True
        if cmd == ENV_GET_SAVE_DIRECTORY:
            C.cast(data, C.POINTER(C.c_char_p))[0] = self.savedir
            return True
        if cmd == ENV_SET_PIXEL_FORMAT:
            self.pixfmt = C.cast(data, C.POINTER(C.c_int))[0]
            return self.pixfmt in (1, 2)
        if cmd == ENV_GET_CAN_DUPE:
            C.cast(data, C.POINTER(C.c_bool))[0] = True
            return True
        if cmd == ENV_GET_VARIABLE:
            v = C.cast(data, C.POINTER(Variable))[0]
            val = self.options.get(v.key, EMPTY)
            C.cast(data, C.POINTER(Variable))[0].value = val.value
            return True
        if cmd == ENV_GET_VARIABLE_UPDATE:
            C.cast(data, C.POINTER(C.c_bool))[0] = False
            return True
        if cmd == ENV_SET_MEMORY_MAPS:
            mm = C.cast(data, C.POINTER(MemMap))[0]
            self.regions = []
            for i in range(mm.num_descriptors):
                d = mm.descriptors[i]
                if d.ptr and d.len:
                    name = (d.addrspace or b'').decode() or f'm{i}'
                    self.regions.append((name, d.start, d.len, d.ptr + d.offset))
            return True
        return False

    def _video(self, data, w, h, pitch):
        if not data:
            return
        if self.pixfmt == 1:   # XRGB8888
            buf = np.ctypeslib.as_array(C.cast(data, C.POINTER(C.c_uint8)), (h, pitch))
            px = buf[:, :w * 4].reshape(h, w, 4)
            self.frame = px[:, :, [2, 1, 0]].copy()
        else:                  # RGB565
            buf = np.ctypeslib.as_array(C.cast(data, C.POINTER(C.c_uint16)), (h, pitch // 2))
            p = buf[:, :w].astype(np.uint32)
            r = ((p >> 11) & 31) * 255 // 31
            g = ((p >> 5) & 63) * 255 // 63
            b = (p & 31) * 255 // 31
            self.frame = np.dstack([r, g, b]).astype(np.uint8)

    def _audio_batch(self, data, frames):
        if self.audio is not None and data:
            self.audio.append(bytes(C.string_at(data, frames * 4)))
        return frames

    def _state(self, port, device, index, id_):
        if device != 1 or port > 1:
            return 0
        return int(any(GEN[b] == id_ for b in self.buttons[port]))

    # --- api -------------------------------------------------------------
    def load(self, path):
        path = os.path.abspath(path)
        self._path = C.c_char_p(path.encode())
        gi = GameInfo(self._path, None, 0, None)
        if not self.lib.retro_load_game(C.byref(gi)):
            raise RuntimeError(f'core refused to load {path} (missing BIOS in {self.sysdir.value.decode()}?)')
        av = AVInfo()
        self.lib.retro_get_system_av_info(C.byref(av))
        self.fps = av.timing.fps
        self.sample_rate = av.timing.sample_rate
        self.lib.retro_set_controller_port_device(0, 1)
        self.lib.retro_set_controller_port_device(1, 1)

    def run(self, n=1):
        for _ in range(n):
            self.lib.retro_run()
            self.frames += 1

    def press(self, buttons, n=2, port=0):
        self.buttons[port] = set(buttons)
        self.run(n)
        self.buttons[port] = set()

    def shot(self, path, scale=1):
        from PIL import Image
        if self.frame is None:
            return None
        img = Image.fromarray(self.frame)
        if scale != 1:
            img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
        img.save(path)
        return path

    def save_state(self, path):
        n = self.lib.retro_serialize_size()
        buf = C.create_string_buffer(n)
        if not self.lib.retro_serialize(buf, n):
            raise RuntimeError('serialize failed')
        open(path, 'wb').write(buf.raw)

    def snapshot(self):
        """Savestate as bytes (in memory)."""
        n = self.lib.retro_serialize_size()
        buf = C.create_string_buffer(n)
        if not self.lib.retro_serialize(buf, n):
            raise RuntimeError('serialize failed')
        return buf.raw

    def restore(self, d):
        if not self.lib.retro_unserialize(C.c_char_p(d), len(d)):
            raise RuntimeError('unserialize failed')

    def load_state(self, path):
        d = open(path, 'rb').read()
        if not self.lib.retro_unserialize(C.c_char_p(d), len(d)):
            raise RuntimeError('unserialize failed')

    # Sub-CPU PRG-RAM inside this core build's savestate: 512 KB at this
    # offset, 16-bit words byte-swapped. retro_get_memory_data(2) segfaults in
    # this build, so the savestate is the way in. Found by locating SUB.BIN.
    STATE_PRGRAM = 0x3810D

    def prg_ram(self):
        """Sub-CPU PRG-RAM ($00000-$7FFFF) as big-endian bytes."""
        n = self.lib.retro_serialize_size()
        buf = C.create_string_buffer(n)
        if not self.lib.retro_serialize(buf, n):
            raise RuntimeError('serialize failed')
        b = bytearray(buf.raw[self.STATE_PRGRAM:self.STATE_PRGRAM + 0x80000])
        b[0::2], b[1::2] = b[1::2], b[0::2]
        return bytes(b)

    def poke_prg(self, addr, data):
        """Write bytes into sub-CPU PRG-RAM (through a savestate round trip)."""
        st = bytearray(self.snapshot())
        for i, v in enumerate(data):
            a = addr + i
            st[self.STATE_PRGRAM + (a ^ 1)] = v      # words are byte-swapped in the state
        self.restore(bytes(st))

    def memory(self):
        """{name: bytes} of memory regions worth dumping."""
        return {'prgram': self.prg_ram()}


def run_script(core, script, out, every=0):
    os.makedirs(out, exist_ok=True)
    cmds = [c.strip() for line in script.replace(';', '\n').splitlines() for c in [line] if c.strip()]
    shotn = [0]

    def step(n):
        for _ in range(n):
            core.run(1)
            if every and core.frames % every == 0:
                shotn[0] += 1
                core.shot(os.path.join(out, f'f{core.frames:06d}.png'))

    for c in cmds:
        w = c.split()
        op = w[0].lower()
        if op == 'wait':
            step(int(w[1]))
        elif op in ('press', 'hold'):
            n = int(w[2]) if len(w) > 2 else 2
            core.buttons[0] = set(w[1].lower().split('+'))
            step(n)
            core.buttons[0] = set()
        elif op == 'shot':
            p = core.shot(os.path.join(out, w[1] + '.png'))
            print(f'shot {p} @ frame {core.frames}')
        elif op == 'save':
            core.save_state(os.path.join(out, w[1] + '.state'))
        elif op == 'load':
            core.load_state(os.path.join(out, w[1] + '.state'))
        elif op == 'dump':
            for nm, data in core.memory().items():
                open(os.path.join(out, f'{w[1]}.{nm}.bin'), 'wb').write(data)
            print('dumped', ', '.join(f'{k}({len(v)})' for k, v in core.memory().items()))
        else:
            raise SystemExit(f'unknown script command: {c}')


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest='cmd', required=True)
    r = sp.add_parser('run', help='headless scripted run')
    r.add_argument('disc')
    r.add_argument('--script', default='wait 600; shot end')
    r.add_argument('--out', default=os.path.join(ROOT, 'shots'))
    r.add_argument('--every', type=int, default=0)
    r.add_argument('--state', help='load this savestate first')
    a = ap.parse_args()

    core = Core()
    core.load(a.disc)
    if a.state:
        core.load_state(a.state)
    t = time.time()
    run_script(core, a.script, a.out, a.every)
    dt = time.time() - t
    print(f'{core.frames} frames in {dt:.1f}s ({core.frames / max(dt, 1e-9):.0f} fps); regions: '
          + ', '.join(f'{n}@{s:06X}+{l:X}' for n, s, l, _ in core.regions))


if __name__ == '__main__':
    main()
