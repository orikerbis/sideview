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

    g("init", "-b", "main")
    g("config", "user.email", "t@t")
    g("config", "user.name", "t")
    open(f"{d}/app.py", "w").write("print('hi')\n")
    open(f"{d}/README.md", "w").write("# test\n")
    os.makedirs(f"{d}/src")
    open(f"{d}/src/util.py", "w").write("def f():\n    return 1\n")
    g("add", "-A")
    g("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "init")
    open(f"{d}/app.py", "a").write("print('more')\n")
    open(f"{d}/notes.txt", "w").write("todo\n")
    return d


def make_multirepo():
    """A non-git parent dir holding two git repos: repoA has a modified
    tracked file, repoB has an untracked file."""
    parent = tempfile.mkdtemp(prefix="sideview-multi-")

    def g(d, *a):
        subprocess.run(["git", "-C", d, "-c", "user.email=t@t",
                        "-c", "user.name=t", *a], capture_output=True)

    for name, tracked in (("repoA", "alpha.py"), ("repoB", "beta.txt")):
        d = os.path.join(parent, name)
        os.makedirs(d)
        g(d, "init", "-b", "main")
        open(f"{d}/{tracked}", "w").write("x = 1\n")
        g(d, "add", "-A")
        g(d, "commit", "-m", "init")
    open(f"{parent}/repoA/alpha.py", "a").write("y = 2\n")   # -> modified
    open(f"{parent}/repoB/extra.txt", "w").write("todo\n")   # -> untracked
    return parent


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
    edlog = os.path.join(auxdir, "editor.log")
    with open(os.path.join(bindir, "fakeed"), "w") as f:
        f.write("#!/bin/sh\necho \"$@\" >> %s\n" % edlog)
    os.chmod(os.path.join(bindir, "fakeed"), 0o755)
    # first exec of a fresh script can take seconds (macOS Gatekeeper
    # scan); warm it up so "no editor ran" checks can trust a short wait
    subprocess.run([os.path.join(bindir, "fakeed"), "warmup"], timeout=30)
    os.remove(edlog)
    os.environ["EDITOR"] = os.path.join(bindir, "fakeed")
    os.environ["SIDEVIEW_STATE"] = os.path.join(auxdir, "state.json")
    os.environ["SIDEVIEW_COMMIT_AI"] = "off"   # deterministic commit msgs
    os.environ["SIDEVIEW_ICONS"] = "nerd"      # CI runners have no fonts

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

    # --- y: copy selected file's path to the clipboard ---
    os.write(fd, b"y")
    ok, _ = wait_for(fd, b"copied path")
    check("y copies path", ok)
    clip = open(clipfile).read() if os.path.exists(clipfile) else ""
    check("clipboard has file path", clip.endswith("src/util.py"))

    # --- Enter must not open files; e must ---
    os.write(fd, b"\r")
    # an editor launch suspends the TUI, which always emits the mouse-off
    # sequence first — a synchronous signal, unlike waiting for edlog
    out = drain(fd, 2.0)
    check("enter does not edit file",
          b"\x1b[?1002l" not in out and not os.path.exists(edlog)
          and b"Traceback" not in out)
    os.write(fd, b"e")
    end = time.time() + 10
    while time.time() < end and not os.path.exists(edlog):
        drain(fd, 0.2)
    logged = open(edlog).read() if os.path.exists(edlog) else ""
    check("e opens editor", "src/util.py" in logged)
    wait_for(fd, b"util.py")           # TUI resumed and redrew

    # --- mouse (SGR): drag-select lines in the preview, copy on release ---
    def sgr(b, x, y, release=False):
        return b"\x1b[<%d;%d;%d%s" % (b, x + 1, y + 1,
                                       b"m" if release else b"M")
    def x10(cb, x, y):
        return bytes([0x1b, ord("["), ord("M"), 32 + cb, 33 + x, 33 + y])
    px = int(80 * 0.42) + 1
    os.write(fd, sgr(0, px + 10, 3))       # press on line 1
    time.sleep(0.1)
    os.write(fd, sgr(32, px + 10, 4))      # drag to line 2
    time.sleep(0.1)
    os.write(fd, sgr(0, px + 10, 4, release=True))
    ok, buf = wait_for(fd, b"copied 2 line")
    check("mouse drag-select copies", ok)
    check("selection highlight shown", b"48;5;239" in buf)
    clip = open(clipfile).read() if os.path.exists(clipfile) else ""
    check("clipboard has dragged lines", "def f():" in clip)

    # --- mouse: drag the separator to resize (feedback message) ---
    sep = int(80 * 0.42) - 1
    os.write(fd, sgr(0, sep, 10))          # press on the separator
    time.sleep(0.1)
    os.write(fd, sgr(32, sep + 6, 10))     # drag right
    ok, _ = wait_for(fd, b"resize")
    check("separator drag resizes", ok)
    os.write(fd, sgr(0, sep + 6, 10, release=True))
    drain(fd, 0.3)

    # --- mouse (X10): wheel down + click still parsed ---
    os.write(fd, x10(0, 3, 2) + x10(3, 3, 2))   # click + release row 2
    os.write(fd, x10(65, px + 5, 5))            # wheel down over preview
    os.write(fd, x10(64, px + 5, 5))            # wheel up
    out = drain(fd, 0.6)
    check("x10 mouse no crash", b"Traceback" not in out)

    # --- arrows browse results while typing in / ---
    os.write(fd, b"/p")                # matches app.py and src/util.py
    wait_for(fd, b"src/util.py")       # results rendered
    os.write(fd, b"\x1bOB")            # Down arrow (application mode)
    # selection bar moves to result 2 and redraws that row
    ok, buf = wait_for(fd, "▌".encode())
    check("arrows browse search results", ok and b"src/util.py" in buf)
    os.write(fd, b"\x1b")              # cancel filter
    wait_for(fd, b"notes.txt")

    # --- Right arrow on a file focuses the preview, Left returns ---
    os.write(fd, b"j")                 # select util.py again
    os.write(fd, b"\x1bOC")            # Right arrow -> preview focus
    ok, _ = wait_for(fd, "▶".encode())
    check("right arrow enters preview", ok)
    os.write(fd, b"\x1bOD")            # Left arrow -> back to tree
    out = drain(fd, 0.5)
    check("left arrow returns no crash", b"Traceback" not in out)

    # --- resize split: smoke test (q exiting cleanly proves it survived) ---
    os.write(fd, b">><-+")
    out = drain(fd, 0.8)
    check("resize keys no crash", b"Traceback" not in out)

    # --- changes view: D shows one repo-wide diff, untracked included ---
    os.write(fd, b"D")
    ok, buf = wait_for(fd, b"@ line")      # pretty hunk marker
    check("changes view shows diff", ok)
    if b"@ new file" not in buf:           # same frame, may need a moment
        _, extra = wait_for(fd, b"@ new file", timeout=3)
        buf += extra
    check("repo diff includes untracked", b"@ new file" in buf)
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

    # --- git actions: stage / unstage / commit guard ---
    os.write(fd, b"gg")
    os.write(fd, b"jj")                # select app.py (modified)
    os.write(fd, b"s")
    ok, _ = wait_for(fd, b"staged app.py")
    check("stage from pane", ok)
    os.write(fd, b"u")
    ok, _ = wait_for(fd, b"unstaged app.py")
    check("unstage from pane", ok)
    os.write(fd, b"c")
    ok, _ = wait_for(fd, b"nothing staged")
    check("commit guard", ok)
    os.write(fd, b"s")                 # stage app.py again
    wait_for(fd, b"staged app.py")
    os.write(fd, b"C")                 # auto-commit with generated message
    ok, buf = wait_for(fd, b"committed")
    check("auto-commit works", ok)
    # C must stay in the TUI: no suspend, so mouse tracking never turns off
    check("no TUI suspend on C", b"\x1b[?1002l" not in buf)
    log = subprocess.run(["git", "-C", repo, "log", "-1", "--format=%s"],
                         capture_output=True, text=True).stdout.strip()
    check("auto commit message generated", log == "chore: update app.py")
    os.write(fd, b"P")                 # no remote configured in fixture
    ok, _ = wait_for(fd, b"push failed")
    check("push reports failure without remote", ok)

    # --- conventional prefix: added file -> feat: ---
    open(f"{repo}/newfile.py", "w").write("x = 1\n")
    subprocess.run(["git", "-C", repo, "add", "newfile.py"],
                   capture_output=True)
    r = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, sys.argv[1]);"
         "from sideview_tui.app import App;"
         "print(App(sys.argv[2]).commit_suggestion())",
         ROOT, repo],
        capture_output=True, text=True)
    check("feat prefix for added file",
          r.stdout.strip().startswith("feat: add newfile.py"))
    subprocess.run(["git", "-C", repo, "-c", "user.email=t@t",
                    "-c", "user.name=t", "commit", "-m", "chore: tmp"],
                   capture_output=True)   # leave nothing staged behind

    # --- follow mode: F auto-jumps to the newest change ---
    os.write(fd, b"F")
    ok, _ = wait_for(fd, b"FOLLOW")
    check("follow badge", ok)
    time.sleep(0.5)
    open(f"{repo}/README.md", "a").write("## follow me\n")
    ok, _ = wait_for(fd, b"follow me")     # jumps there on the git tick
    check("follow jumps to newest change", ok)
    os.write(fd, b"F\x1b")                 # follow off, exit changes
    wait_for(fd, b"notes.txt")

    # --- preview search: / inside the focused preview, n cycles ---
    os.write(fd, b"gg")
    os.write(fd, b"j")                 # util.py
    os.write(fd, b"\x1bOC")            # focus preview
    os.write(fd, b"/return\r")         # search in file
    ok, _ = wait_for(fd, b"match(es)")
    check("preview search", ok)
    os.write(fd, b"n")
    out = drain(fd, 0.5)
    check("search next no crash", b"Traceback" not in out)
    os.write(fd, b"\x1bOD")            # back to tree

    # --- x deletes a file (press twice); refuses directories ---
    os.write(fd, b"gg")                    # select src/ (a directory)
    drain(fd, 0.3)
    os.write(fd, b"x")
    ok, _ = wait_for(fd, b"can't delete directories")
    check("x refuses directories", ok)
    open(f"{repo}/junk.txt", "w").write("bye\n")
    os.write(fd, b"r")                     # pick up the new file
    ok, _ = wait_for(fd, b"junk.txt")
    check("junk.txt appears", ok)
    os.write(fd, b"/junk\r")               # select it via fuzzy find
    wait_for(fd, b"junk.txt")
    os.write(fd, b"x")
    ok, _ = wait_for(fd, b"press x again")
    check("delete asks to confirm", ok)
    os.write(fd, b"k")                     # any other key cancels
    drain(fd, 0.4)
    check("cancel keeps file", os.path.exists(f"{repo}/junk.txt"))
    os.write(fd, b"x")
    wait_for(fd, b"press x again")
    os.write(fd, b"x")                     # confirm
    # NB: can't wait for the "deleted junk.txt" message — it shares the
    # "delete" prefix with the confirm prompt, so ncurses redraws only the
    # tail. The emptied filtered tree is the deterministic signal.
    ok, _ = wait_for(fd, b"(no matches)")
    check("x x deletes file", ok)
    check("file gone from disk", not os.path.exists(f"{repo}/junk.txt"))
    os.write(fd, b"\x1b")                  # clear the filter
    wait_for(fd, b"notes.txt")

    # --- ?: key reference overlay; q closes it without quitting ---
    os.write(fd, b"?")
    ok, _ = wait_for(fd, "sideview — keys".encode())
    check("? opens help", ok)
    os.write(fd, b"\x04")                  # Ctrl-d: reveals the last rows
    ok, _ = wait_for(fd, b"drag separator")
    check("help scrolls", ok)
    os.write(fd, b"q")                     # closes help, app keeps running
    ok, _ = wait_for(fd, b"notes.txt")
    check("q closes help without quitting", ok)

    os.write(fd, b"q")
    status, _ = wait_exit(pid, fd)
    check("q clean exit", status == 0)

    # --- persistence: src/ expansion survives restart ---
    pid, fd = spawn(repo)
    ok, buf = wait_for(fd, "⎇".encode())
    if b"util.py" not in buf:                     # may land a frame later
        _, extra = wait_for(fd, b"util.py", timeout=3)
        buf += extra
    check("state persisted across restart", b"util.py" in buf)

    # --- ctrl-c: clean exit, no traceback ---
    os.write(fd, b"\x03")
    status, out = wait_exit(pid, fd)
    check("ctrl-c exit code 0", status == 0)
    check("no traceback on ctrl-c", b"Traceback" not in out)

    # --- doctor + emoji fallback (zero-config) ---
    r = subprocess.run([sys.executable, SIDEVIEW, "--doctor"],
                       capture_output=True, text=True)
    check("doctor runs", r.returncode == 0 and "icon style" in r.stdout)
    os.environ["SIDEVIEW_ICONS"] = "emoji"
    pid, fd = spawn(repo)
    ok, _ = wait_for(fd, "🐍".encode())
    check("emoji icon override", ok)
    os.write(fd, b"q")
    wait_exit(pid, fd)
    os.environ["SIDEVIEW_ICONS"] = "nerd"

    # --- multi-repo: git works on a non-git root containing repos ---
    multi = make_multirepo()
    pid, fd = spawn(multi)
    ok, buf = wait_for(fd, b"repoA")
    buf += drain(fd, 0.5)                   # let the startup frame finish
    check("multi: repos listed", b"repoA" in buf and b"repoB" in buf)
    # header shows the owning repo's branch even though the root isn't a repo
    check("multi: git visible on non-git root", "⎇".encode() in buf)
    os.write(fd, b"/alpha\r")              # find a file inside repoA
    ok, _ = wait_for(fd, b"alpha.py")
    check("multi: file found across repos", ok)
    os.write(fd, b"s")                     # stage it — must target repoA
    ok, _ = wait_for(fd, b"staged")
    check("multi: stage reported", ok)
    porcelain = subprocess.run(
        ["git", "-C", os.path.join(multi, "repoA"), "status", "--porcelain"],
        capture_output=True, text=True).stdout
    check("multi: staged in the owning repo", porcelain.startswith("M "))
    os.write(fd, b"q")
    wait_exit(pid, fd)

    print()
    if FAILURES:
        print("FAILED:", ", ".join(FAILURES))
        sys.exit(1)
    print("all tests passed")


if __name__ == "__main__":
    main()
