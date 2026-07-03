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
    open(f"{d}/src/util.py", "w").write("x=1\n")
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
