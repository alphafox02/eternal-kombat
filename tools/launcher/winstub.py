# SPDX-License-Identifier: MIT
"""EternalKombat.exe (Windows): unpack the launcher's runtime once, then start it.

tools/launcher/package.py builds this with PyInstaller around payload.zip (a
portable Python with the build's packages, and the repository's tools/ and
data/). The first run of each version unpacks it to
%LOCALAPPDATA%/EternalKombat/runtime-VERSION (a minute or so, with a small
window saying so); later runs start at once. Then the runtime's own Python
runs tools/launcher/boot.py, and this exits.
"""
import os, shutil, subprocess, sys, threading, zipfile


def main():
    here = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    ver = open(os.path.join(here, 'VERSION')).read().strip()
    base = os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'), 'EternalKombat')
    rt = os.path.join(base, 'runtime-' + ''.join(c if c.isalnum() or c in '.-' else '_' for c in ver))
    done = os.path.join(rt, '.unpacked')
    if not os.path.exists(done):
        unpack(os.path.join(here, 'payload.zip'), rt, done)
    for d in os.listdir(base):                       # older versions' runtimes (if not in use)
        if d.startswith('runtime-') and os.path.join(base, d) != rt:
            shutil.rmtree(os.path.join(base, d), ignore_errors=True)
    subprocess.Popen([os.path.join(rt, 'python', 'pythonw.exe'), '-P',
                      os.path.join(rt, 'app', 'tools', 'launcher', 'boot.py')],
                     cwd=rt, close_fds=True, creationflags=0x00000008)     # DETACHED_PROCESS


def unpack(payload, rt, done):
    import tkinter as tk
    from tkinter import ttk
    root = tk.Tk()
    root.title('Eternal Kombat')
    root.resizable(False, False)
    msg = tk.StringVar(value='Setting up Eternal Kombat (first run of this version) ...')
    ttk.Label(root, textvariable=msg, padding=16).pack()
    bar = ttk.Progressbar(root, length=360, maximum=1.0)
    bar.pack(padx=16, pady=(0, 16))
    state = {'frac': 0.0, 'error': None, 'done': False}

    def work():
        try:
            if os.path.exists(rt):
                shutil.rmtree(rt)
            with zipfile.ZipFile(payload) as z:
                names = z.infolist()
                for i, info in enumerate(names):
                    z.extract(info, rt)
                    state['frac'] = (i + 1) / len(names)
            open(done, 'w').write('ok')
        except Exception as e:                       # noqa: BLE001
            state['error'] = e
        state['done'] = True

    def poll():
        bar['value'] = state['frac']
        if state['done']:
            if state['error']:
                msg.set(f'Could not set up: {state["error"]}')
                root.after(8000, root.destroy)
            else:
                root.destroy()
            return
        root.after(100, poll)
    threading.Thread(target=work, daemon=True).start()
    root.after(100, poll)
    root.mainloop()
    if state['error']:
        sys.exit(1)


if __name__ == '__main__':
    main()
