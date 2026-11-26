# SPDX-License-Identifier: MIT
"""The Eternal Kombat launcher: pick your discs, build the game, play it.

A small window (Tk) over the same steps as the README's: the player's two disc
images (chosen, or found in a folder) go into roms/, tools/prepare.py and
tools/build.py make the disc, and RetroArch (tools/launcher/retroarch.py,
downloaded once) plays it with the player's Sega CD BIOS - or the built disc is
saved where the player wants it, for an emulator of their own. Started by tools/launcher/boot.py in a packaged app, or
from a checkout:

    python3 tools/launcher/ekapp.py
"""
import json, os, queue, re, shutil, subprocess, sys, threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'lib'))
sys.path.insert(0, os.path.dirname(HERE))           # (tools/: checkinputs' BIOS list)

DISCS = (('ec_us', 'Eternal Champions: Challenge from the Dark Side (USA)'),
         ('mk_us', 'Mortal Kombat (USA)'))
CONTROLS = ('Keyboard (player 1): arrows move; X  Y  Z = A  S  D;  A  B  C = Z  X  C;  Start = Enter.\n'
            'Gamepads work for both players (Xbox-style: A = B, B = C, X = A, Y = Y, LB = X, RB = Z).\n'
            'Esc twice quits; F1 opens RetroArch\'s menu.')


def identify(cue):
    """(key or None, note) for a .cue: which disc it is, by its data track's SHA-1."""
    from inputs import KNOWN, HEADER_HINTS
    from disc import Disc
    try:
        d = Disc(cue)
        sha = d.data_sha1()
        head = d.read(0)[:0x200]
        d.close()
    except Exception as e:                       # noqa: BLE001
        return None, f'can\'t read it: {e}'
    for k, v in KNOWN.items():
        if v['sha1'] == sha:
            return k, 'ok'
    for k, h in HEADER_HINTS.items():
        if h in head:
            return k, 'a different dump or revision than the one this was made with: it may still work'
    return None, 'not a disc this project knows'


def cue_files(cue):
    """The cue sheet and every file it names."""
    from disc import parse_cue
    return [cue] + sorted({t.file for t in parse_cue(cue)})


def place(cue, dest, say):
    """The disc's files into DEST: hard links where the file system allows (no copy), else copies."""
    if os.path.exists(dest):
        shutil.rmtree(dest)
    os.makedirs(dest)
    for f in cue_files(cue):
        out = os.path.join(dest, os.path.basename(f))
        try:
            os.link(f, out)
        except OSError:
            say(f'Copying {os.path.basename(f)} ...')
            shutil.copyfile(f, out)


def bios_ok(path):
    import hashlib
    from checkinputs import BIOS_MD5
    return hashlib.md5(open(path, 'rb').read()).hexdigest() in BIOS_MD5.values()


def find_inputs(top, say):
    """{'ec_us' / 'mk_us': .cue, 'bios': file} found under TOP (the first of each)."""
    import hashlib
    from checkinputs import BIOS_MD5
    found = {}
    cues, bios = [], []
    for d, _, fs in os.walk(top):
        for f in fs:
            p = os.path.join(d, f)
            if f.lower().endswith('.cue'):
                cues.append(p)
            elif f.lower().endswith('.bin') and os.path.getsize(p) == 128 << 10:   # (a Sega CD BIOS: 128 KB)
                bios.append(p)
    for p in bios:
        if hashlib.md5(open(p, 'rb').read()).hexdigest() in BIOS_MD5.values():
            found['bios'] = p
            break
    for p in sorted(cues):
        if all(k in found for k, _ in DISCS):
            break
        say(f'Looking at {os.path.basename(p)} ...')
        key, _ = identify(p)
        if key in dict(DISCS) and key not in found:
            found[key] = p
    return found


class App:
    def __init__(self, game, home):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk = tk, ttk
        self.game, self.home = game, home
        self.cue = os.path.join(game, 'build', 'Eternal Kombat', 'Eternal Kombat.cue')
        self.settings_path = os.path.join(home, 'settings.json')
        try:
            self.settings = json.load(open(self.settings_path))
        except (OSError, ValueError):
            self.settings = {}
        import retroarch
        self.emu = retroarch.Emulator(os.path.join(home, 'emulator'))
        self.q = queue.Queue()
        self.busy = False

        ver = open(os.path.join(game, 'VERSION')).read().strip() if os.path.exists(os.path.join(game, 'VERSION')) else 'dev'
        self.root = r = tk.Tk()
        r.title(f'Eternal Kombat  ({ver})')
        r.minsize(720, 520)
        pad = dict(padx=8, pady=4)
        f = ttk.Frame(r, padding=10)
        f.pack(fill='both', expand=True)
        ttk.Label(f, text='Eternal Kombat', font=('TkDefaultFont', 16, 'bold')).grid(row=0, column=0, columnspan=3, sticky='w')
        head = ('TkDefaultFont', 11, 'bold')
        s1 = ttk.Frame(f)
        s1.grid(row=1, column=0, columnspan=3, sticky='we', pady=(8, 0))
        ttk.Label(s1, text='1. Your discs', font=head).pack(side='left')
        ttk.Button(s1, text='Find them in a folder...', command=self.find).pack(side='left', padx=12)
        ttk.Label(f, text='Your own disc images (BIN/CUE) and Sega CD BIOS: point at the folder they\'re in, '
                          'or choose each one. Only the emulator is ever downloaded.', wraplength=680,
                  foreground='#555').grid(row=2, column=0, columnspan=3, sticky='w', padx=8)
        self.vars, self.notes = {}, {}
        rows = [(k, t + '  (.cue)') for k, t in DISCS] + [('bios', 'Sega CD BIOS, USA (only needed for Play)')]
        for i, (key, title) in enumerate(rows):
            ttk.Label(f, text=title).grid(row=3 + 2 * i, column=0, columnspan=3, sticky='w', **pad)
            v = tk.StringVar(value=self.settings.get(key, ''))
            self.vars[key] = v
            ttk.Entry(f, textvariable=v, width=80).grid(row=4 + 2 * i, column=0, sticky='we', padx=8)
            ttk.Button(f, text='Choose...', command=lambda k=key: self.choose(k)).grid(row=4 + 2 * i, column=1, padx=4)
            n = ttk.Label(f, text='', width=14)
            n.grid(row=4 + 2 * i, column=2, sticky='w')
            self.notes[key] = n
        f.columnconfigure(0, weight=1)
        s2 = ttk.Frame(f)
        s2.grid(row=9, column=0, columnspan=3, sticky='we', pady=(12, 0))
        ttk.Label(s2, text='2. Build', font=head, width=10).pack(side='left')
        self.build_btn = ttk.Button(s2, text='Build the game', command=self.build)
        self.build_btn.pack(side='left', padx=4)
        ttk.Label(s2, text='(a few minutes, once)', foreground='#555').pack(side='left', padx=8)
        s3 = ttk.Frame(f)
        s3.grid(row=10, column=0, columnspan=3, sticky='we', pady=(8, 8))
        ttk.Label(s3, text='3. Play', font=head, width=10).pack(side='left')
        self.play_btn = ttk.Button(s3, text='Play', command=self.play)
        self.play_btn.pack(side='left', padx=4)
        self.full = tk.BooleanVar(value=self.settings.get('fullscreen', False))
        ttk.Checkbutton(s3, text='Full screen', variable=self.full).pack(side='left', padx=8)
        ttk.Label(s3, text='or, for your own emulator:', foreground='#555').pack(side='left', padx=(16, 4))
        self.copy_btn = ttk.Button(s3, text='Save a copy to...', command=self.save_copy)
        self.copy_btn.pack(side='left', padx=4)
        ttk.Button(s3, text='Open its folder', command=self.open_folder).pack(side='left', padx=4)
        self.status = tk.StringVar(value='')
        ttk.Label(f, textvariable=self.status).grid(row=11, column=0, columnspan=3, sticky='w', padx=8)
        self.bar = ttk.Progressbar(f, mode='determinate', maximum=1.0)
        self.bar.grid(row=12, column=0, columnspan=3, sticky='we', padx=8)
        self.log = tk.Text(f, height=8, wrap='none', state='disabled', font=('TkFixedFont', 9))
        self.log.grid(row=13, column=0, columnspan=3, sticky='nsew', padx=8, pady=6)
        f.rowconfigure(13, weight=1)
        ttk.Label(f, text=CONTROLS, foreground='#555').grid(row=14, column=0, columnspan=3, sticky='w', padx=8)
        for key in self.vars:
            self.check(key)
        self.refresh()
        r.after(100, self.pump)

    # -- inputs
    def choose(self, key):
        from tkinter import filedialog
        types = [('BIOS', '*.bin *.BIN'), ('All files', '*')] if key == 'bios' else [('Cue sheet', '*.cue *.CUE')]
        p = filedialog.askopenfilename(title='Choose ' + ('the BIOS' if key == 'bios' else 'the disc\'s .cue'),
                                       filetypes=types)
        if p:
            self.vars[key].set(p)
            self.check(key)
            self.save()

    def check(self, key):
        p = self.vars[key].get().strip()
        if not p:
            self.notes[key].config(text='')
            return False
        if not os.path.isfile(p):
            self.notes[key].config(text='not found')
            return False
        if key == 'bios':
            ok = bios_ok(p)
            self.notes[key].config(text='ok' if ok else 'unknown BIOS')
            return True
        got, note = identify(p)
        if got == key:
            self.notes[key].config(text='ok' if note == 'ok' else 'other revision')
            if note != 'ok':
                self.say(f'{os.path.basename(p)}: {note}')
            return True
        self.notes[key].config(text='wrong disc' if got else 'not recognised')
        if got:
            self.say(f'{os.path.basename(p)} is the other disc ({dict(DISCS)[got]}).')
        return False

    def save(self):
        self.settings.update({k: v.get() for k, v in self.vars.items()}, fullscreen=self.full.get())
        os.makedirs(self.home, exist_ok=True)
        json.dump(self.settings, open(self.settings_path, 'w'), indent=1)

    # -- output
    def say(self, line):
        self.log.config(state='normal')
        self.log.insert('end', line.rstrip() + '\n')
        self.log.see('end')
        self.log.config(state='disabled')

    def pump(self):
        try:
            while True:
                kind, a, b = self.q.get_nowait()
                if kind == 'line':
                    self.say(a)
                elif kind == 'found':
                    self.vars[a].set(b)
                    self.check(a)
                    self.save()
                elif kind == 'status':
                    self.status.set(a)
                    if b is not None:
                        self.bar.config(mode='determinate')
                        self.bar.stop()
                        self.bar['value'] = b
                    else:
                        self.bar.config(mode='indeterminate')
                        self.bar.start(15)
                elif kind == 'done':
                    self.busy = False
                    self.bar.stop()
                    self.bar.config(mode='determinate')
                    self.bar['value'] = 1.0 if a else 0
                    self.status.set(b)
                    self.refresh()
        except queue.Empty:
            pass
        self.root.after(100, self.pump)

    def refresh(self):
        built = os.path.exists(self.cue)
        self.build_btn.config(state='disabled' if self.busy else 'normal')
        self.play_btn.config(state='normal' if built and not self.busy else 'disabled')
        self.copy_btn.config(state='normal' if built and not self.busy else 'disabled')
        if not self.busy and not self.status.get():
            self.status.set('Ready to play.' if built else 'Choose your two discs, then Build the game.')

    def run(self, work):
        if self.busy:
            return
        self.busy = True
        self.refresh()
        self.save()

        def go():
            try:
                self.q.put(('done', True, work()))
            except Exception as e:                   # noqa: BLE001
                self.q.put(('line', f'Error: {e}', None))
                self.q.put(('done', False, f'Stopped: {e}'))
        threading.Thread(target=go, daemon=True).start()

    def step(self, args, part, lo, hi):
        """Run a tool (tools/ path and args), its output into the log, the bar from LO to HI."""
        env = dict(os.environ, TMPDIR=os.path.join(self.home, 'tmp'), PYTHONUNBUFFERED='1')
        os.makedirs(env['TMPDIR'], exist_ok=True)
        kw = {}
        if sys.platform.startswith('win'):
            kw['creationflags'] = 0x08000000             # CREATE_NO_WINDOW
        p = subprocess.Popen([sys.executable, '-P', '-X', 'utf8', os.path.join(self.game, 'tools', *args[0].split('/'))]
                             + args[1:], cwd=self.game, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             encoding='utf-8', errors='replace', **kw)
        self.q.put(('status', part, lo))
        for line in p.stdout:
            self.q.put(('line', line, None))
            m = re.match(r'\[(\d+)/(\d+)\]', line)
            if m:
                self.q.put(('status', f'{part}: {line.split("]", 1)[1].strip().rstrip(".")}',
                            lo + (hi - lo) * (int(m.group(1)) - 1) / int(m.group(2))))
        if p.wait():
            raise RuntimeError(f'{part} failed (see the log above)')

    # -- actions
    def build(self):
        cues = {}
        for key, title in DISCS:
            if not self.check(key):
                self.say(f'Choose your {title} disc (its .cue) first.')
                return
            cues[key] = self.vars[key].get().strip()

        def work():
            for key, cue in cues.items():
                self.q.put(('status', f'Setting up {dict(DISCS)[key]} ...', None))
                place(cue, os.path.join(self.game, 'roms', key), lambda m: self.q.put(('line', m, None)))
            self.step(['prepare.py'], "Reading MK's fighters from your MK disc", 0.0, 0.6)
            self.q.put(('status', 'Building the disc (a few minutes) ...', None))
            self.step(['build.py'], 'Building the disc', 0.6, 1.0)
            return f'Built: {self.cue}'
        self.run(work)

    def play(self):
        if not os.path.exists(self.cue):
            return
        bios = self.vars['bios'].get().strip()
        if not self.emu.has_bios() and not (bios and os.path.isfile(bios)):
            self.say('Choose your Sega CD BIOS (USA) first: the emulator needs it to start a Sega CD game.')
            return

        def work():
            if bios and os.path.isfile(bios):
                self.emu.put_bios(bios)
            if not self.emu.ready():
                self.emu.install(lambda m, frac=None: self.q.put(('status', m, frac)))
            self.q.put(('status', 'Starting RetroArch ...', None))
            self.emu.play(self.cue, fullscreen=self.full.get())
            return 'Playing. (Esc twice to quit.)'
        self.run(work)

    def find(self):
        """Every disc and the BIOS under a folder the player picks, found by their contents."""
        from tkinter import filedialog
        top = filedialog.askdirectory(title='The folder your disc images (and BIOS) are in')
        if not top:
            return

        def work():
            found = find_inputs(top, lambda m: self.q.put(('status', m, None)))
            for key, path in found.items():
                self.q.put(('found', key, path))
            missing = [t for k, t in DISCS + (('bios', 'Sega CD BIOS'),) if k not in found]
            return ('Found everything.' if not missing else
                    'Found ' + (', '.join(t for k, t in DISCS + (('bios', 'the BIOS'),) if k in found) or 'nothing')
                    + '. Not there: ' + ', '.join(missing) + '.')
        self.run(work)

    def save_copy(self):
        """The built game (its .cue and tracks) into a folder the player picks."""
        from tkinter import filedialog
        top = filedialog.askdirectory(title='Where to save Eternal Kombat (a folder of its own is made there)')
        if not top or not os.path.exists(self.cue):
            return
        dest = os.path.join(top, 'Eternal Kombat')

        def work():
            files = cue_files(self.cue)
            os.makedirs(dest, exist_ok=True)
            for i, src in enumerate(files):
                self.q.put(('status', f'Copying {os.path.basename(src)} ...', i / len(files)))
                shutil.copyfile(src, os.path.join(dest, os.path.basename(src)))
            self.q.put(('line', f'Saved: {os.path.join(dest, "Eternal Kombat.cue")}', None))
            return f'Saved to {dest}: open Eternal Kombat.cue in your emulator.'
        self.run(work)

    def open_folder(self):
        d = os.path.dirname(self.cue) if os.path.exists(self.cue) else self.game
        if sys.platform.startswith('win'):
            os.startfile(d)                              # noqa: S606
        else:
            subprocess.Popen(['xdg-open', d])

    def mainloop(self):
        self.root.mainloop()


def main(game=None, home=None):
    game = game or os.path.dirname(os.path.dirname(HERE))
    home = home or os.path.join(game, 'build', 'launcher')
    App(game, home).mainloop()


if __name__ == '__main__':
    main()
