#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Package the launcher as one file to download: an AppImage (Linux) or an .exe (Windows).

Inside: a portable Python (python-build-standalone, pinned), the build's
packages (requirements.txt, and py7zr for RetroArch's archives; on Windows
7-Zip's 7zr.exe as well), and this
repository's tracked tools/ and data/ - no game data: the player's own discs
are read when the app runs (tools/launcher/boot.py, ekapp.py).

    package.py linux   [--out dist]    -> dist/EternalKombat-x86_64.AppImage
    package.py windows [--out dist]    -> dist/EternalKombat.exe  (needs PyInstaller in the Python running this)

Run by .github/workflows/launcher.yml on GitHub's machines; also by hand on the
system it packages for.
"""
import argparse, hashlib, os, shutil, subprocess, sys, tarfile, urllib.request, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PBS = 'https://github.com/astral-sh/python-build-standalone/releases/download/20261124/'
PYTHON = {
    'linux': (PBS + 'cpython-3.12.16%2B20261124-x86_64-unknown-linux-gnu-install_only.tar.gz',
              '6774c7f49ee21c1723f7ac91961a5bf9f3ee3ae6e4d82ff58bd358958b546461'),
    'windows': (PBS + 'cpython-3.12.16%2B20261124-x86_64-pc-windows-msvc-install_only.tar.gz',
                '8152ff5b6c6c044ddbbaa3531dda59cb9ce5bd6cb670d4c9ac2e3ab91afa8778'),
}
# 7-Zip's standalone extractor (GNU LGPL, 7-zip.org): libretro's Windows archives need it (BCJ2)
SEVENZIP = ('https://github.com/ip7z/7zip/releases/download/26.06/7zr.exe',
            'e80db2dad715a6c5adabe292d31ed54e11f4e9b99ca349827b50573b175891bc')
APPIMAGETOOL = ('https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage',
                'ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0')
# requirements.txt at the versions the game is built and checked with (art goes through Pillow and
# scipy: the same versions give the same disc as a checkout's), and py7zr (RetroArch's .7z archives)
PINS = ['Pillow==12.1.1', 'numpy==2.3.5', 'scipy==1.16.3', 'unicorn==2.1.4', 'capstone==5.0.9', 'py7zr==1.0.0']
FILES = ('LICENSE', 'README.md', 'requirements.txt')
NAME = 'Eternal Kombat'


def fetch(url, sha, dest):
    if not (os.path.exists(dest) and _sha256(dest) == sha):
        print(f'downloading {url}', flush=True)
        req = urllib.request.Request(url, headers={'User-Agent': 'EternalKombat-package'})
        with urllib.request.urlopen(req, timeout=120) as r, open(dest + '.part', 'wb') as f:
            shutil.copyfileobj(r, f)
        if _sha256(dest + '.part') != sha:
            raise SystemExit(f'{url}: fingerprint differs from the pinned one')
        os.replace(dest + '.part', dest)
    return dest


def _sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def version():
    try:
        return subprocess.run(['git', 'describe', '--tags', '--always', '--dirty'], cwd=ROOT, check=True,
                              capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return 'unknown'


def stage(target, work):
    """WORK/stage: python/ (with the packages) and app/ (the tracked tools/ and data/, VERSION)."""
    st = os.path.join(work, 'stage')
    if os.path.exists(st):
        shutil.rmtree(st)
    os.makedirs(st)
    tgz = fetch(*PYTHON[target], os.path.join(work, os.path.basename(PYTHON[target][0]).replace('%2B', '+')))
    with tarfile.open(tgz) as t:
        t.extractall(st, filter='tar') if hasattr(tarfile, 'data_filter') else t.extractall(st)
    py = os.path.join(st, 'python', 'python.exe' if target == 'windows' else os.path.join('bin', 'python3'))
    subprocess.run([py, '-m', 'pip', 'install', '--no-warn-script-location', '--disable-pip-version-check',
                    '-r', os.path.join(ROOT, 'requirements.txt')] + PINS, check=True)
    app = os.path.join(st, 'app')
    tracked = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard', 'tools', 'data'], cwd=ROOT, check=True, capture_output=True,
                             text=True).stdout.split('\n')
    for rel in [t for t in tracked if t] + list(FILES):
        dst = os.path.join(app, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(os.path.join(ROOT, rel), dst)
    open(os.path.join(app, 'VERSION'), 'w').write(version() + '\n')
    r = subprocess.run([py, '-P', os.path.join(app, 'tools', 'launcher', 'boot.py'), '--selftest'],
                       capture_output=True, text=True)
    print(r.stdout + r.stderr, end='')
    if r.returncode:
        raise SystemExit('the packaged Python fails its selftest')
    return st, py


def icon(path, size=256):
    """The app's icon: its initials (no game art)."""
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new('RGBA', (size, size), (24, 8, 8, 255))
    d = ImageDraw.Draw(im)
    d.rectangle([6, 6, size - 7, size - 7], outline=(200, 30, 30, 255), width=8)
    try:
        font = ImageFont.load_default(size=size // 2)
    except TypeError:                                  # (an older Pillow: its small bitmap font)
        font = ImageFont.load_default()
    d.text((size // 2, size // 2), 'EK', fill=(240, 200, 60, 255), font=font, anchor='mm')
    im.save(path)
    return im


def linux(out, work):
    st, _ = stage('linux', work)
    open(os.path.join(st, 'AppRun'), 'w').write(
        '#!/bin/sh\n'
        'HERE="$(dirname "$(readlink -f "$0")")"\n'
        'unset PYTHONHOME PYTHONPATH\n'
        'exec "$HERE/python/bin/python3" -P "$HERE/app/tools/launcher/boot.py" "$@"\n')
    os.chmod(os.path.join(st, 'AppRun'), 0o755)
    open(os.path.join(st, 'eternal-kombat.desktop'), 'w').write(
        f'[Desktop Entry]\nType=Application\nName={NAME}\nExec=AppRun\nIcon=eternal-kombat\n'
        'Categories=Game;\nTerminal=false\n')
    icon(os.path.join(st, 'eternal-kombat.png'))
    tool = fetch(*APPIMAGETOOL, os.path.join(work, 'appimagetool-1.9.1-x86_64.AppImage'))
    os.chmod(tool, 0o755)
    unpacked = os.path.join(work, 'appimagetool')        # (unpacked here, not to /tmp; no FUSE needed)
    if not os.path.exists(os.path.join(unpacked, 'squashfs-root', 'AppRun')):
        os.makedirs(unpacked, exist_ok=True)
        subprocess.run([tool, '--appimage-extract'], cwd=unpacked, check=True, stdout=subprocess.DEVNULL)
    dest = os.path.join(out, 'EternalKombat-x86_64.AppImage')
    subprocess.run([os.path.join(unpacked, 'squashfs-root', 'AppRun'), '--no-appstream', st, dest], check=True,
                   env=dict(os.environ, ARCH='x86_64'))
    print(dest)


def windows(out, work):
    st, _ = stage('windows', work)
    fetch(*SEVENZIP, os.path.join(st, '7zr.exe'))     # (beside python/: tools/launcher/retroarch.sevenzip)
    open(os.path.join(st, '7zr.txt'), 'w').write(
        '7zr.exe is 7-Zip 26.06\'s standalone extractor, by Igor Pavlov: GNU LGPL, source at https://7-zip.org\n')
    payload = os.path.join(work, 'payload.zip')
    with zipfile.ZipFile(payload, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for d, _, fs in os.walk(st):
            for f in fs:
                p = os.path.join(d, f)
                if '__pycache__' not in p:
                    z.write(p, os.path.relpath(p, st))
    shutil.copyfile(os.path.join(st, 'app', 'VERSION'), os.path.join(work, 'VERSION'))
    ico = os.path.join(work, 'eternal-kombat.ico')
    icon(os.path.join(work, 'icon.png')).save(ico, sizes=[(256, 256), (64, 64), (32, 32), (16, 16)])
    sep = ';' if os.name == 'nt' else ':'
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--onefile', '--noconsole', '--name', 'EternalKombat',
                    '--icon', ico, '--add-data', f'{payload}{sep}.', '--add-data', f'{os.path.join(work, "VERSION")}{sep}.',
                    '--distpath', out, '--workpath', os.path.join(work, 'pyi'), '--specpath', work,
                    os.path.join(ROOT, 'tools', 'launcher', 'winstub.py')], check=True)
    print(os.path.join(out, 'EternalKombat.exe'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('target', choices=('linux', 'windows'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'dist'))
    ap.add_argument('--work', default=os.path.join(ROOT, 'build', 'package'))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    os.makedirs(a.work, exist_ok=True)
    (linux if a.target == 'linux' else windows)(os.path.abspath(a.out), os.path.abspath(a.work))


if __name__ == '__main__':
    main()
