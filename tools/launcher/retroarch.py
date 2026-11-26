# SPDX-License-Identifier: MIT
"""RetroArch with the Genesis Plus GX core, to play the built disc.

One release of RetroArch and its cores pack, pinned by SHA-256, downloaded from
libretro's own server (buildbot.libretro.com) the first time the player presses
Play, into the launcher's folder. Only RetroArch and the Genesis Plus GX core
are unpacked. RetroArch then runs with a config file of ours (saves, the BIOS
folder, the window), straight into the game: the player never sees its menus.

A new RetroArch release changes nothing here until PINNED is moved on (after
trying the game on it). The BIOS is the player's: it goes to RetroArch's system
folder under the name the core looks for.
"""
import hashlib, os, shutil, subprocess, sys, urllib.request

VERSION = '1.22.2'
BASE = f'https://buildbot.libretro.com/stable/{VERSION}'
# os -> (RetroArch archive, its SHA-256), (cores archive, its SHA-256), RetroArch in the
# archive, the core in the cores archive
PINNED = {
    'windows': dict(
        ra=(f'{BASE}/windows/x86_64/RetroArch.7z',
            'b2139b1d0f9d4526dc6b5ce23cbb3efdc766096fa6f2c3df016818b486ac6372'),
        cores=(f'{BASE}/windows/x86_64/RetroArch_cores.7z',
               '86b871e11b9b4772ac644b40a38f2c8e9449da1f355eae7da08aa061148547b0'),
        top='RetroArch-Win64', exe='retroarch.exe',
        core='RetroArch-Win64/cores/genesis_plus_gx_libretro.dll'),
    'linux': dict(
        ra=(f'{BASE}/linux/x86_64/RetroArch.7z',
            '7d62da9a21397d6e1b9490785cedbeafd262781b50115076736fbe8a77ef30e9'),
        cores=(f'{BASE}/linux/x86_64/RetroArch_cores.7z',
               '4b7ed8dc97d4bf035fce182c64b5658c7662e2e9e5d42129538afbd4b6096307'),
        top='RetroArch-Linux-x86_64', exe='RetroArch-Linux-x86_64.AppImage',
        core='RetroArch-Linux-x86_64/RetroArch-Linux-x86_64.AppImage.home/.config/retroarch/cores/'
             'genesis_plus_gx_libretro.so'),
}
BIOS_NAME = 'bios_CD_U.bin'        # what Genesis Plus GX looks for (a US Sega CD)
UA = 'EternalKombat-launcher'      # (no personal details in requests)


def system():
    return 'windows' if sys.platform.startswith('win') else 'linux'


class Emulator:
    """RetroArch under DIR (the launcher's emulator folder)."""

    def __init__(self, dir):
        self.dir = os.path.abspath(dir)
        self.p = PINNED[system()]
        self.root = os.path.join(self.dir, self.p['top'])
        self.exe = os.path.join(self.root, self.p['exe'])
        # (Linux: its AppImage unpacked once, here: no FUSE needed, and nothing unpacked to /tmp each run)
        self.run = self.exe if system() == 'windows' else os.path.join(self.root, 'squashfs-root', 'AppRun')
        self.core = os.path.join(self.root, 'cores', os.path.basename(self.p['core']))
        self.system_dir = os.path.join(self.dir, 'system')
        self.saves = os.path.join(self.dir, 'saves')
        self.config = os.path.join(self.dir, 'eternal-kombat.cfg')
        self.stamp = os.path.join(self.dir, f'ready-{VERSION}')

    def ready(self):
        return all(os.path.exists(p) for p in (self.run, self.core, self.stamp))

    def has_bios(self):
        return os.path.exists(os.path.join(self.system_dir, BIOS_NAME))

    def put_bios(self, path):
        os.makedirs(self.system_dir, exist_ok=True)
        shutil.copyfile(path, os.path.join(self.system_dir, BIOS_NAME))

    # -- download and unpack
    def _fetch(self, url, sha, dest, say):
        if os.path.exists(dest) and _sha256(dest) == sha:
            return dest
        part = dest + '.part'
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=60) as r, open(part, 'wb') as f:
            total = int(r.headers.get('Content-Length') or 0)
            got = 0
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                f.write(b)
                got += len(b)
                say(f'Downloading {os.path.basename(dest)}: {got >> 20} of {total >> 20} MB'
                    if total else f'Downloading {os.path.basename(dest)}: {got >> 20} MB', got / total if total else None)
        if _sha256(part) != sha:
            os.remove(part)
            raise RuntimeError(f'{url} did not download correctly (its fingerprint differs). '
                               'Try again; if it keeps failing, libretro may have changed the file.')
        os.replace(part, dest)
        return dest

    def install(self, say=lambda msg, frac=None: None):
        """Download (once) and unpack RetroArch and the core. say(message, fraction or None)."""
        os.makedirs(self.dir, exist_ok=True)
        dl = os.path.join(self.dir, 'downloads')
        os.makedirs(dl, exist_ok=True)
        ra = self._fetch(*self.p['ra'], os.path.join(dl, f'RetroArch-{VERSION}.7z'), say)
        cores = self._fetch(*self.p['cores'], os.path.join(dl, f'RetroArch_cores-{VERSION}.7z'), say)
        if os.path.exists(self.root):
            shutil.rmtree(self.root)
        say('Unpacking RetroArch ...', None)
        unpack(ra, self.dir)
        say('Unpacking the Genesis Plus GX core ...', None)
        unpack(cores, self.dir, self.p['core'])
        src = os.path.join(self.dir, *self.p['core'].split('/'))
        os.makedirs(os.path.dirname(self.core), exist_ok=True)
        if os.path.abspath(src) != os.path.abspath(self.core):
            shutil.move(src, self.core)
        if system() == 'linux':
            os.chmod(self.exe, 0o755)
            say('Unpacking the RetroArch AppImage ...', None)
            subprocess.run([self.exe, '--appimage-extract'], cwd=self.root, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        open(self.stamp, 'w').write(VERSION)
        for f in os.listdir(dl):                     # (the archives: ~400 MB, no longer needed)
            os.remove(os.path.join(dl, f))
        say('RetroArch is ready.', 1.0)

    # -- play
    def write_config(self, fullscreen=False):
        os.makedirs(self.saves, exist_ok=True)
        os.makedirs(self.system_dir, exist_ok=True)
        q = lambda p: p.replace('\\', '/')
        lines = {
            'system_directory': q(self.system_dir),
            'savefile_directory': q(self.saves),
            'savestate_directory': q(self.saves),
            'video_fullscreen': 'true' if fullscreen else 'false',
            'video_scale': '3',
            'video_smooth': 'false',
            'input_autodetect_enable': 'true',
            'joypad_autoconfig_dir': q(os.path.join(self.root, 'autoconfig') if system() == 'windows' else
                                       os.path.join(self.root, 'RetroArch-Linux-x86_64.AppImage.home', '.config',
                                                    'retroarch', 'autoconfig')),
            'config_save_on_exit': 'false',
            'pause_nonactive': 'false',
            'menu_show_core_updater': 'false',
            'quit_press_twice': 'true',
        }
        # player 1's keyboard as tools/play.py window's: the bottom row A B C = Z X C, the top row
        # X Y Z = A S D (Genesis Plus GX: A, B, C, X, Y, Z are RetroPad Y, B, A, L, X, R)
        lines.update(input_player1_y='z', input_player1_b='x', input_player1_a='c',
                     input_player1_l='a', input_player1_x='s', input_player1_r='d',
                     input_player1_start='enter', input_player1_select='rshift')
        with open(self.config, 'w') as f:
            for k, v in lines.items():
                f.write(f'{k} = "{v}"\n')

    def play(self, cue, fullscreen=False):
        self.write_config(fullscreen)
        cmd = [self.run, '-L', self.core, '--config', self.config, os.path.abspath(cue)]
        env = dict(os.environ)
        if system() == 'linux':
            env.pop('PYTHONHOME', None)
            env.pop('PYTHONPATH', None)
            # its own home (the archive's portable one): run this way RetroArch would
            # otherwise make ~/.config/retroarch and keep its history there
            home = os.path.join(self.root, self.p['exe'] + '.home')
            env['HOME'] = home
            env['XDG_CONFIG_HOME'] = os.path.join(home, '.config')
        return subprocess.Popen(cmd, cwd=self.root, env=env)


def sevenzip():
    """7-Zip's own extractor on Windows: libretro's Windows archives use its BCJ2 filter, which
    py7zr can't undo. The app carries 7zr.exe beside its Python (tools/launcher/package.py);
    an installed 7-Zip will do too. None elsewhere (py7zr unpacks the Linux archives)."""
    if system() != 'windows':
        return None
    here = os.path.join(os.path.dirname(sys.prefix), '7zr.exe')
    for p in (here, shutil.which('7z'), shutil.which('7zr'),
              os.path.join(os.environ.get('ProgramFiles', r'C:\Program Files'), '7-Zip', '7z.exe')):
        if p and os.path.isfile(p):
            return p
    raise RuntimeError('RetroArch\'s archives need 7-Zip to unpack, and it wasn\'t found. '
                       'Install 7-Zip (7-zip.org), then press Play again.')


def unpack(archive, dest, member=None):
    """ARCHIVE (.7z) into DEST: all of it, or the one MEMBER (its path in the archive)."""
    seven = sevenzip()
    if seven:
        cmd = [seven, 'x', archive, f'-o{dest}', '-y'] + ([member.replace('/', os.sep)] if member else [])
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='replace',
                           creationflags=0x08000000)               # CREATE_NO_WINDOW
        if r.returncode:
            raise RuntimeError(f'unpacking {os.path.basename(archive)} failed: {r.stdout.strip()[-300:]}')
        return
    import py7zr
    with py7zr.SevenZipFile(archive) as z:
        if member:
            z.extract(dest, targets=[member])
        else:
            z.extractall(dest)


def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()
