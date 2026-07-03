#!/usr/bin/env python3
"""pty regression test for sideview. Run: python3 tests/test_tui.py"""
import fcntl
import os
import pty
import re
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIDEVIEW = os.path.join(ROOT, "sideview")
STRIP = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b[()][0B]|\x1b[=>]")
FAILURES = []


def check(name, ok):
    print(("PASS" if ok else "FAIL"), name)
    if not ok:
        FAILURES.append(name)


def make_fixture():
    d = tempfile.mkdtemp(prefix="sideview-test-")

    def g(*a):
        subprocess.run(["git", "-C", d, *a], capture_output=True)

    g("init")
    open(f"{d}/app.py", "w").write("print('hi')\n")
    open(f"{d}/README.md", "w").write("# test\n")
    os.makedirs(f"{d}/src")
    open(f"{d}/src/util.py", "w").write("def f():\n    return 1\n")
    g("add", "-A")
    g("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "init")
    open(f"{d}/app.py", "a").write("print('more')\n")
    open(f"{d}/notes.txt", "w").write("todo\n")
    return d


def spawn(repo):
    pid, fd = pty.fork()
    if pid == 0:
        os.environ["TERM"] = "xterm-256color"
        os.execv(sys.executable, [sys.executable, SIDEVIEW, repo])
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 80, 0, 0))
    os.set_blocking(fd, False)
    return pid, fd


def drain(fd, wait):
    time.sleep(wait)
    out = b""
    while True:
        try:
            c = os.read(fd, 1 << 20)
            if not c:
                break
            out += c
        except OSError:
            break
    return out


def wait_for(fd, pattern, timeout=10):
    """Accumulate pty output until `pattern` (bytes) appears."""
    end = time.time() + timeout
    out = b""
    while time.time() < end:
        out += drain(fd, 0.2)
        if pattern in out:
            out += drain(fd, 0.3)  # let the frame finish
            return True, out
    return False, out


def wait_exit(pid, fd, timeout=5):
    """Reap child while draining the pty so it can't block on writes."""
    end = time.time() + timeout
    out = b""
    while time.time() < end:
        out += drain(fd, 0.1)
        done, status = os.waitpid(pid, os.WNOHANG)
        if done == pid:
            return status, out
    os.kill(pid, signal.SIGKILL)
    os.waitpid(pid, 0)
    return None, out


def main():
    repo = make_fixture()

    # fake pbcopy so tests don't clobber the real clipboard (outside the
    # fixture repo so it doesn't appear in the tree)
    auxdir = tempfile.mkdtemp(prefix="sideview-test-aux-")
    bindir = os.path.join(auxdir, "bin")
    os.makedirs(bindir)
    clipfile = os.path.join(auxdir, "clip.txt")
    with open(os.path.join(bindir, "pbcopy"), "w") as f:
        f.write("#!/bin/sh\ncat > %s\n" % clipfile)
    os.chmod(os.path.join(bindir, "pbcopy"), 0o755)
    os.environ["PATH"] = bindir + ":" + os.environ["PATH"]

    # --- startup, icons, header ---
    pid, fd = spawn(repo)
    ok, raw_b = wait_for(fd, "⎇ main".encode())
    raw = raw_b.decode("utf-8", "replace")
    txt = STRIP.sub("", raw)
    check("branch in header", ok)
    check("py nerd glyph", "" in txt)
    check("md nerd glyph", "" in txt)
    check("folder nerd glyph", "" in txt)
    check("py icon colored (fg 68)", "38;5;68m" in raw)
    check("md icon colored (fg 109)", "38;5;109m" in raw)

    # --- navigate: expand src/, fuzzy find ---
    os.write(fd, b"l")
    ok, _ = wait_for(fd, b"util.py")
    check("expand shows util.py", ok)
    os.write(fd, b"/util\r")
    ok, _ = wait_for(fd, b"src/util.py")
    check("fuzzy find", ok)

    # --- syntax highlighting: select util.py, expect keyword color ---
    os.write(fd, b"\x1b")            # clear filter, back to tree
    wait_for(fd, b"notes.txt")
    os.write(fd, b"j")               # src/ -> util.py
    ok, _ = wait_for(fd, b"38;5;141m")   # tokyonight keyword magenta
    check("syntax keyword colored", ok)

    # --- mouse drag in preview: selects lines, copies on release ---
    def m(cb, x, y):  # X10: ESC [ M Cb Cx Cy, all offset by 32, 1-based
        return bytes([0x1b, ord("["), ord("M"), 32 + cb, 33 + x, 33 + y])
    px = int(80 * 0.42) + 1            # preview x at default split
    os.write(fd, m(0, px + 10, 3))     # press on preview line 1
    time.sleep(0.3)                    # hold past mouseinterval (150ms)
    os.write(fd, m(32, px + 10, 4))    # drag down to line 2
    time.sleep(0.1)
    os.write(fd, m(3, px + 10, 4))     # release -> copy
    ok, _ = wait_for(fd, b"copied 2 line")
    check("preview drag-select copies", ok)
    clip = open(clipfile).read() if os.path.exists(clipfile) else ""
    check("clipboard has selected lines",
          "def f():" in clip and "return 1" in clip)

    # --- resize split: smoke test (q exiting cleanly proves it survived) ---
    os.write(fd, b">><")
    out = drain(fd, 0.8)
    check("resize keys no crash", b"Traceback" not in out)

    # --- mouse: drag separator + click row (X10 encoding, 80x30 pane) ---
    def m(cb, x, y):  # X10: ESC [ M Cb Cx Cy, all offset by 32, 1-based
        return bytes([0x1b, ord("["), ord("M"), 32 + cb, 33 + x, 33 + y])
    sep = max(24, min(int(80 * 0.42), 54)) - 1
    os.write(fd, m(0, sep, 10))       # press button1 on separator
    os.write(fd, m(32, sep + 6, 10))  # drag right (motion-while-pressed)
    os.write(fd, m(3, sep + 6, 10))   # release
    os.write(fd, m(0, 3, 2) + m(3, 3, 2))  # click row 2 in the tree
    out = drain(fd, 0.8)
    check("mouse events no crash", b"Traceback" not in out)

    # --- changes view: D shows one repo-wide diff, untracked included ---
    os.write(fd, b"D")
    ok, buf = wait_for(fd, b"@@")          # hunks of the repo diff
    check("changes view shows diff", ok)
    if b"+todo" not in buf:                # same frame, may need a moment
        _, extra = wait_for(fd, b"+todo", timeout=3)
        buf += extra
    check("repo diff includes untracked", b"+todo" in buf)
    open(f"{repo}/app.py", "a").write("print('live')\n")   # agent edit
    ok, _ = wait_for(fd, b"live")          # preview picks it up on its own
    check("changes view updates live", ok)

    # --- Tab focus: j scrolls the preview instead of the tree ---
    os.write(fd, b"\t")
    ok, _ = wait_for(fd, "▶".encode())     # focus marker on preview title
    check("tab focuses preview", ok)
    os.write(fd, b"jj\t")                  # scroll, then focus back
    out = drain(fd, 0.5)
    check("preview scroll no crash", b"Traceback" not in out)
    os.write(fd, b"\x1b")                  # Esc leaves changes view
    ok, _ = wait_for(fd, b"README.md")     # full tree is back
    check("esc exits changes view", ok)

    # --- copy mode: m toggles terminal mouse tracking off/on ---
    os.write(fd, b"m")
    ok, _ = wait_for(fd, b"\x1b[?1002l")
    check("copy mode disables mouse tracking", ok)
    os.write(fd, b"m")
    ok, _ = wait_for(fd, b"\x1b[?1002h")
    check("m re-enables mouse tracking", ok)

    os.write(fd, b"q")
    status, _ = wait_exit(pid, fd)
    check("q clean exit", status == 0)

    # --- ctrl-c: clean exit, no traceback ---
    pid, fd = spawn(repo)
    wait_for(fd, "⎇".encode())
    os.write(fd, b"\x03")
    status, out = wait_exit(pid, fd)
    check("ctrl-c exit code 0", status == 0)
    check("no traceback on ctrl-c", b"Traceback" not in out)

    print()
    if FAILURES:
        print("FAILED:", ", ".join(FAILURES))
        sys.exit(1)
    print("all tests passed")


if __name__ == "__main__":
    main()
