# SPDX-License-Identifier: MIT
"""PicoDrive, for the 32X checks: a Sega CD with a 32X.

The same API as tools/lib/scd.py's Core (load, run, press, frame, save_state).
stable-retro (requirements-dev.txt) ships the core beside Genesis Plus GX;
$EK_PICO_CORE overrides it. Genesis Plus GX has no 32X: the disc plays there as
on a Sega CD alone.

PicoDrive keeps the sub CPU's PRG RAM in its 'PRGRAM' memory region with 16-bit words byte-swapped
(scd.Core.prg_ram reads Genesis Plus GX's save state, which reads zeros here): prg_ram / poke_prg are
replaced. Its options must all be set (an empty picodrive_sound_rate divides by zero in PsndRerate).

    from pico import core; c = core(); c.load(cue)
"""
import ctypes as C, importlib.util, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scd

OPTIONS = {'picodrive_region': 'US', 'picodrive_drc': 'disabled', 'picodrive_sound_rate': '44100',
           'picodrive_input1': '6 button pad', 'picodrive_input2': '6 button pad', 'picodrive_renderer': 'accurate',
           'picodrive_frameskip': 'disabled', 'picodrive_ramcart': 'disabled', 'picodrive_overclk68k': 'disabled',
           'picodrive_audio_filter': 'disabled', 'picodrive_sprlim': 'disabled', 'picodrive_aspect': 'PAR',
           'picodrive_dacnoise': 'disabled', 'picodrive_fm_filter': 'disabled', 'picodrive_smstype': 'Auto',
           'picodrive_frameskip_threshold': '33'}


def find_core():
    if os.environ.get('EK_PICO_CORE'):
        return os.environ['EK_PICO_CORE']
    spec = importlib.util.find_spec('stable_retro')
    for d in (spec.submodule_search_locations if spec else []):
        p = os.path.join(d, 'cores', 'picodrive_libretro.so')
        if os.path.exists(p):
            return p
    raise SystemExit('no PicoDrive core: pip install -r requirements-dev.txt (stable-retro), or set EK_PICO_CORE')


def core(audio=False, saves=None):
    c = scd.Core(core=find_core(), options=OPTIONS, audio=audio, saves=saves)
    c._check_layout = lambda *a: None          # (scd's check reads Genesis Plus GX's state layout)

    def region(name):
        return next(r for r in c.regions if r[0] == name)

    def prg_ram():
        r = region('PRGRAM')
        b = bytearray(C.string_at(r[3], r[2]))
        b[0::2], b[1::2] = b[1::2], b[0::2]
        return bytes(b)

    def poke_prg(addr, data):
        base = region('PRGRAM')[3]
        for i, v in enumerate(data):
            C.c_uint8.from_address(base + ((addr + i) ^ 1)).value = v
    c.prg_ram, c.poke_prg = prg_ram, poke_prg
    return c
