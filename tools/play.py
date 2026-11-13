#!/usr/bin/env python3
"""Play, script or auto-test a disc under Genesis Plus GX (Sega CD).

    play.py window [DISC] [--state NAME]     interactive window with sound
    play.py run    [DISC] SCENARIO|"script"  headless scripted run -> shots/
    play.py test   [--no-build]              build, run tests/scenarios/*.txt,
                                             write runs/<time>/report.md

DISC defaults to the built disc (build/Eternal Kombat/Eternal Kombat.cue), or
the original EC disc if nothing is built yet. Use 'ec' or 'mk' for originals.

Savestates live in states/ and are shared: save in the window with F2 and a
scenario can 'load quick'; a scenario can 'save fight' and the window can open
it with --state fight.

Window keys
    arrows  d-pad          Z X C   A B C        A S D   X Y Z
    Enter   Start          Tab     Mode
    F2 save states/quick   F4 load quick        F12 screenshot
    F3 fast-forward        P  pause             Esc quit

Scenario commands (one per line or ';'-separated, '#' comments)
    wait N                  run N frames
    press BTN[+BTN] [N]     hold for N frames (default 4), then release
    p2 BTN[+BTN] [N]        same, on controller 2
    mash N [SEED]           random 6-button play for N frames (player 1)
    shot NAME               save frame as NAME.png in the run's folder
    sheet NAME              contact sheet of every shot so far in this run
    save NAME / load NAME   savestates in states/
    dump NAME               write exposed memory (512K sub-CPU PRG-RAM) to NAME.prgram.bin
    expect-change           fail unless the screen changed since the last shot
"""
import argparse, datetime, glob, os, random, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image
from scd import Core

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATES = os.path.join(ROOT, 'states')
SHOTS = os.path.join(ROOT, 'shots')
BUILT = os.path.join(ROOT, 'build', 'Eternal Kombat', 'Eternal Kombat.cue')
BUTTONS = ['a', 'b', 'c', 'x', 'y', 'z']
DIRS = ['up', 'down', 'left', 'right']


def resolve_disc(arg):
    if arg in (None, 'built'):
        if os.path.exists(BUILT):
            return BUILT
        arg = 'ec'
    if arg in ('ec', 'mk'):
        from inputs import require
        return require('ec_us' if arg == 'ec' else 'mk_us').cue
    return arg


def state_path(name):
    os.makedirs(STATES, exist_ok=True)
    return name if name.endswith('.state') and os.sep in name else os.path.join(STATES, name + '.state')


def contact_sheet(paths, out, cols=3):
    ims = [Image.open(p).convert('RGB') for p in paths]
    if not ims:
        return None
    w = max(i.width for i in ims)
    h = max(i.height for i in ims)
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * (w + 6) - 6, rows * (h + 6) - 6), 'white')
    for n, im in enumerate(ims):
        sheet.paste(im, ((n % cols) * (w + 6), (n // cols) * (h + 6)))
    sheet.save(out)
    return out


class ScenarioError(Exception):
    pass


def run_script(core, script, out, log=print):
    """Run scenario text. Returns list of shot paths."""
    os.makedirs(out, exist_ok=True)
    shots, last = [], None
    lines = []
    for raw in script.splitlines():
        raw = raw.split('#', 1)[0]
        lines += [c.strip() for c in raw.split(';') if c.strip()]
    for c in lines:
        w = c.split()
        op = w[0].lower()
        if op == 'wait':
            core.run(int(w[1]))
        elif op in ('press', 'hold'):
            core.press(w[1].lower().split('+'), int(w[2]) if len(w) > 2 else 4)
        elif op in ('p2', 'press2'):
            core.press(w[1].lower().split('+'), int(w[2]) if len(w) > 2 else 4, port=1)
        elif op == 'mash':
            rnd = random.Random(int(w[2]) if len(w) > 2 else 1)
            left = int(w[1])
            while left > 0:
                held = {rnd.choice(DIRS)} if rnd.random() < 0.6 else set()
                if rnd.random() < 0.7:
                    held.add(rnd.choice(BUTTONS))
                n = min(left, rnd.choice((4, 6, 8, 12)))
                core.press(held, n)
                left -= n
        elif op == 'shot':
            p = core.shot(os.path.join(out, w[1] + '.png'))
            shots.append(p)
            last = core.frame.copy() if core.frame is not None else None
            log(f'  shot  {w[1]:14s} frame {core.frames}')
        elif op == 'expect-change':
            if last is not None and core.frame is not None and np.array_equal(last, core.frame):
                raise ScenarioError(f'screen did not change by frame {core.frames}')
        elif op == 'sheet':
            p = contact_sheet(shots, os.path.join(out, w[1] + '.png'))
            log(f'  sheet {os.path.relpath(p, ROOT)}')
        elif op == 'save':
            core.save_state(state_path(w[1]))
            log(f'  saved states/{w[1]}.state')
        elif op == 'load':
            core.load_state(state_path(w[1]))
        elif op == 'dump':
            for nm, data in core.memory().items():
                open(os.path.join(out, f'{w[1]}.{nm}.bin'), 'wb').write(data)
        else:
            raise ScenarioError(f'unknown command: {c}')
    return shots


def read_scenario(arg):
    if os.path.exists(arg):
        return open(arg).read()
    p = os.path.join(ROOT, 'tests', 'scenarios', arg + ('' if arg.endswith('.txt') else '.txt'))
    if os.path.exists(p):
        return open(p).read()
    return arg   # inline script


# --------------------------------------------------------------------------
def cmd_run(a):
    disc = resolve_disc(a.disc)
    out = a.out or os.path.join(SHOTS, datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    core = Core(saves=os.path.join(out, 'saves'))
    core.load(disc)
    if a.state:
        core.load_state(state_path(a.state))
    t = time.time()
    try:
        run_script(core, read_scenario(a.scenario), out)
    except ScenarioError as e:
        print(f'FAIL: {e}')
        sys.exit(1)
    print(f'{core.frames} frames in {time.time() - t:.1f}s -> {os.path.relpath(out, ROOT)}/')


def cmd_test(a):
    """Build, then run each scenario in its own process (the core keeps global
    CD-drive state that doesn't survive being reloaded in one process)."""
    if not a.no_build:
        r = subprocess.run([sys.executable, '-P', '-E', os.path.join(ROOT, 'tools', 'build.py')])
        if r.returncode:
            raise SystemExit('build failed')
    disc = resolve_disc(a.disc)
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    run_dir = os.path.join(ROOT, 'runs', stamp)
    # keep the 3 most recent earlier runs; older ones are just clutter
    import shutil
    for old in sorted(glob.glob(os.path.join(ROOT, 'runs', '2*')))[:-3]:
        shutil.rmtree(old, ignore_errors=True)
    files = sorted(glob.glob(os.path.join(ROOT, 'tests', 'scenarios', '*.txt')))
    if a.only:
        files = [f for f in files if any(o in os.path.basename(f) for o in a.only)]
    report = [f'# Test run {stamp}', '', f'Disc: `{os.path.relpath(disc, ROOT)}`', '']
    failed = 0
    for f in files:
        name = os.path.splitext(os.path.basename(f))[0]
        out = os.path.join(run_dir, name)
        print(name, flush=True)
        t = time.time()
        r = subprocess.run([sys.executable, '-P', '-E', os.path.abspath(__file__), 'run', disc, f, '--out', out],
                           capture_output=True, text=True, timeout=a.timeout)
        log = (r.stdout + r.stderr).strip()
        print('\n'.join('  ' + l for l in log.splitlines()))
        status = 'pass' if r.returncode == 0 else f'FAIL (exit {r.returncode})'
        failed += r.returncode != 0
        pngs = sorted(glob.glob(os.path.join(out, '*.png')))
        sheet = contact_sheet(pngs, os.path.join(run_dir, name + '.png')) if pngs else None
        print(f'  {status}  ({time.time() - t:.1f}s)')
        report += [f'## {name}: {status}', '', '```', log, '```', '']
        if sheet:
            report += [f'![{name}]({name}.png)', '']
    with open(os.path.join(run_dir, 'report.md'), 'w') as o:
        o.write('\n'.join(report))
    print(f'report: {os.path.relpath(os.path.join(run_dir, "report.md"), ROOT)}  ({failed} failed)')
    sys.exit(1 if failed else 0)


# --------------------------------------------------------------------------
KEYMAP = {'up': 'up', 'down': 'down', 'left': 'left', 'right': 'right',
          'z': 'a', 'x': 'b', 'c': 'c', 'a': 'x', 's': 'y', 'd': 'z',
          'return': 'start', 'tab': 'mode'}


def cmd_window(a):
    import fcntl
    import tkinter as tk
    from PIL import ImageTk
    disc = resolve_disc(a.disc)
    core = Core(audio=not a.mute)
    core.load(disc)
    if a.state:
        core.load_state(state_path(a.state))

    audio = None
    if not a.mute:
        try:
            audio = subprocess.Popen(['pw-cat', '--playback', '--raw', '--rate', str(int(round(core.sample_rate))),
                                      '--channels', '2', '--format', 's16', '--latency', '100ms', '-'],
                                     stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
            afd = audio.stdin.fileno()
            fcntl.fcntl(afd, 1031, 65536)                      # F_SETPIPE_SZ
            os.set_blocking(afd, False)                        # never let audio stall the frame loop
        except (OSError, FileNotFoundError):
            audio = None

    root = tk.Tk()
    root.title(f'Eternal Kombat - {os.path.basename(disc)}')
    label = tk.Label(root, bg='black')
    label.pack()
    status = tk.Label(root, anchor='w', font=('monospace', 9),
                      text='arrows  ZXC=ABC  ASD=XYZ  Enter=Start  Tab=Mode  F2 save  F4 load  F12 shot  F3 fast  P pause  Esc quit')
    status.pack(fill='x')
    held, pending = set(), {}
    st = dict(paused=False, fast=False, img=None, size=None, next=time.perf_counter(), msg_until=0,
              drops=0, minq=None, t0=time.perf_counter(), f0=core.frames, late=0)

    def say(msg):
        status.configure(text=msg)
        st['msg_until'] = time.time() + 3

    def down(e):
        k = e.keysym.lower()
        if k in pending:                       # X11 autorepeat: cancel the fake release
            root.after_cancel(pending.pop(k))
        if k in KEYMAP:
            held.add(KEYMAP[k])
        elif k == 'f2':
            core.save_state(state_path('quick'))
            stamp = datetime.datetime.now().strftime('%H%M%S')
            core.save_state(state_path(f'quick-{stamp}'))
            say(f'saved states/quick.state (and quick-{stamp})')
        elif k == 'f4':
            if os.path.exists(state_path('quick')):
                core.load_state(state_path('quick'))
                say('loaded states/quick.state')
        elif k == 'f12':
            os.makedirs(SHOTS, exist_ok=True)
            p = core.shot(os.path.join(SHOTS, datetime.datetime.now().strftime('shot-%Y%m%d-%H%M%S.png')))
            say(f'screenshot {os.path.relpath(p, ROOT)}')
        elif k == 'f3':
            st['fast'] = not st['fast']
            say('fast-forward ' + ('on' if st['fast'] else 'off'))
        elif k == 'p':
            st['paused'] = not st['paused']
            say('paused' if st['paused'] else 'running')
        elif k == 'escape':
            root.destroy()

    def up(e):
        k = e.keysym.lower()
        if k in KEYMAP:
            def release():
                pending.pop(k, None)
                held.discard(KEYMAP[k])
            pending[k] = root.after(25, release)

    root.bind('<KeyPress>', down)
    root.bind('<KeyRelease>', up)
    frame_time = 1.0 / core.fps
    import termios, array
    # pw-cat pulls from the pipe as it plays and keeps its own ~100 ms cushion
    # (--latency). Start it with 100 ms of silence so frame-timing jitter in
    # this loop never runs it dry (gaps and crackle). Only if the backlog
    # passes half a second (e.g. after a long stall) is audio dropped.
    max_queued = int(core.sample_rate * 4 * 0.50)
    if audio:
        try:
            os.write(afd, bytes(int(core.sample_rate * 0.10) * 4))
        except OSError:
            pass

    def queued():
        buf = array.array('i', [0])
        fcntl.ioctl(afd, termios.FIONREAD, buf)
        return buf[0]

    def feed_audio():
        pcm = b''.join(core.audio)
        core.audio.clear()
        if not audio or st['fast'] or not pcm:
            return
        try:
            if queued() + len(pcm) > max_queued:           # running ahead: drop this slice
                st['drops'] += 1
                return
            os.write(afd, pcm)
        except (BlockingIOError, BrokenPipeError, OSError):
            st['drops'] += 1
        if st['minq'] is None or queued() < st['minq']:
            st['minq'] = queued()

    def tick():
        # The clock paces the game. Run as many frames as are due (up to 4, to
        # catch up after a hiccup without spiralling), then draw once.
        now = time.perf_counter()
        due = 8 if st['fast'] else max(0, min(4, int((now - st['next']) / frame_time) + 1))
        if now - st['next'] > 0.25:                        # long stall (window drag etc.): resync
            st['next'] = now
        if not st['paused']:
            core.buttons[0] = set(held)
            for _ in range(due):
                core.run(1)
                if core.audio is not None:
                    feed_audio()
            if not st['fast']:
                st['next'] += due * frame_time
        else:
            st['next'] = now
        if core.frame is not None:
            img = Image.fromarray(core.frame)
            img = img.resize((img.width * a.scale, img.height * a.scale), Image.NEAREST)
            if st['size'] != img.size:
                st['img'] = ImageTk.PhotoImage(img)
                st['size'] = img.size
                label.configure(image=st['img'])
            else:
                st['img'].paste(img)
        if st['msg_until'] and time.time() > st['msg_until']:
            status.configure(text=f'frame {core.frames}')
            st['msg_until'] = 0
        if due > 1:
            st['late'] += 1
        if a.bench and core.frames - st['f0'] >= a.bench:
            dt = time.perf_counter() - st['t0']
            n = core.frames - st['f0']
            print(f'{n} frames in {dt:.2f}s = {n / dt:.2f} fps (target {core.fps:.2f}); catch-up ticks {st["late"]}; '
                  f'audio drops {st["drops"]}; min queued {st["minq"]} bytes')
            root.destroy()
            return
        delay = 1 if st['fast'] else max(1, int((st['next'] - time.perf_counter()) * 1000))
        root.after(delay, tick)

    root.after(1, tick)
    root.mainloop()
    if audio:
        audio.stdin.close()
        audio.terminate()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest='cmd', required=True)
    w = sp.add_parser('window')
    w.add_argument('disc', nargs='?')
    w.add_argument('--state')
    w.add_argument('--scale', type=int, default=3)
    w.add_argument('--mute', action='store_true')
    w.add_argument('--bench', type=int, default=0, help='quit after N frames and print timing stats')
    r = sp.add_parser('run')
    r.add_argument('disc', nargs='?')
    r.add_argument('scenario')
    r.add_argument('--state')
    r.add_argument('--out')
    t = sp.add_parser('test')
    t.add_argument('--disc')
    t.add_argument('--no-build', action='store_true')
    t.add_argument('--only', nargs='*')
    t.add_argument('--timeout', type=int, default=600, help='seconds per scenario')
    a = ap.parse_args()
    if a.cmd == 'run' and a.scenario is None:
        a.scenario, a.disc = a.disc, None
    {'window': cmd_window, 'run': cmd_run, 'test': cmd_test}[a.cmd](a)


if __name__ == '__main__':
    main()
