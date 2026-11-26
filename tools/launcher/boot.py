# SPDX-License-Identifier: MIT
"""Start the Eternal Kombat launcher from a packaged app (tools/launcher/package.py).

The app carries its own Python and this repository's tools/ and data/. The tools
write beside themselves (extracted/, build/, roms/), and an app's own files may
be read-only (an AppImage) or temporary, so they are copied to the player's
folder first - again whenever the app is a newer version - and run from there:

    Windows  %LOCALAPPDATA%/EternalKombat/game
    Linux    $XDG_DATA_HOME (~/.local/share)/EternalKombat/game

What the tools made there (the player's discs in roms/, extracted/, build/) is
kept across versions.

    boot.py              the launcher's window
    boot.py --selftest   import what the build needs, then exit (the packaging's check)
"""
import os, shutil, sys

APP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # the app's copy
COPIED = ('tools', 'data')
FILES = ('LICENSE', 'README.md', 'requirements.txt', 'VERSION')


def home():
    if sys.platform.startswith('win'):
        base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    else:
        base = os.environ.get('XDG_DATA_HOME') or os.path.join(os.path.expanduser('~'), '.local', 'share')
    return os.path.join(base, 'EternalKombat')


def version(root):
    try:
        return open(os.path.join(root, 'VERSION')).read().strip()
    except OSError:
        return None


def sync(game):
    """The app's tools/ and data/ into GAME, when its version differs (or GAME has none)."""
    if version(APP) is not None and version(APP) == version(game):
        return
    os.makedirs(game, exist_ok=True)
    for d in COPIED:
        dst = os.path.join(game, d)
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(os.path.join(APP, d), dst, ignore=shutil.ignore_patterns('__pycache__'))
    for f in FILES:
        if os.path.exists(os.path.join(APP, f)):
            shutil.copyfile(os.path.join(APP, f), os.path.join(game, f))


def selftest():
    """What tools/prepare.py and tools/build.py import from outside the repository, and the window's."""
    import importlib
    for m in ('numpy', 'scipy', 'scipy.signal', 'scipy.ndimage', 'PIL.Image', 'unicorn', 'capstone', 'py7zr',
              'tkinter', 'tkinter.ttk', 'multiprocessing', 'lzma', 'hashlib', 'json', 'wave', 'zlib', 'ctypes'):
        importlib.import_module(m)
    import tkinter
    print(f'selftest ok: Python {sys.version.split()[0]}, Tk {tkinter.TkVersion}')


def main():
    if '--selftest' in sys.argv:
        selftest()
        return
    game = os.path.join(home(), 'game')
    sync(game)
    launcher = os.path.join(game, 'tools', 'launcher')
    sys.path.insert(0, launcher)
    import ekapp
    ekapp.main(game, home())


if __name__ == '__main__':
    main()
