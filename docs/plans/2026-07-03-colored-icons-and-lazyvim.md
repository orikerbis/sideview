# Module Split + Colored Icons + LazyVim Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the approved spec (docs/specs/2026-07-03-nvim-lazyvim-sideview-design.md) with the user-requested restructure: split sideview into modules, add per-filetype colored Nerd Font icons, and set up LazyVim with Python/DevOps/TypeScript extras.

**Architecture:** `sideview` at the repo root becomes a thin launcher that puts the repo on `sys.path` (resolving its own symlink) and calls `sideview_tui.main.cli()`. The `sideview_tui/` package splits by responsibility: `icons` (glyph/color tables + classification), `textutil` (cell-width helpers), `gitstate` (git status model), `app` (tree/search/preview state + actions), `theme` (curses colors), `ui` (drawing), `main` (event loop + cli). The Neovim config is the stock LazyVim starter in `~/.config/nvim` with extras enabled via `lazyvim.json`.

**Tech Stack:** Python 3 stdlib only (curses, pty for tests), LazyVim on Neovim 0.12.

## Global Constraints

- Python stdlib only — no third-party imports anywhere in `sideview_tui/`.
- Nerd Font glyphs only from devicons/seti/font-awesome ranges (stable in Nerd Fonts 2.3.3, the user's MesloLGS NF version).
- 8-color terminals: icons render uncolored (inherit row attr), no crash.
- `~/.local/bin/sideview` symlink must keep working (launcher resolves `os.path.realpath(__file__)`).
- Do not overwrite an existing `~/.config/nvim` (verified absent; re-check before clone).
- Push to github.com/orikerbis/sideview only in the final task.

---

### Task 1: Baseline pty test harness

**Files:**
- Test: `tests/test_tui.py` (new; self-contained, runnable with `python3 tests/test_tui.py`)

**Interfaces:**
- Consumes: the `sideview` executable at repo root (currently the single-file version).
- Produces: `make_fixture() -> str` (temp git repo with modified/staged/untracked files), `spawn(repo) -> (pid, fd)`, `drain(fd, wait) -> bytes`, `wait_exit(pid, fd, timeout=5) -> (status|None, bytes)` — reused by later tasks' assertions.

- [ ] **Step 1: Write the test** — full content:

```python
#!/usr/bin/env python3
"""pty regression test for sideview. Run: python3 tests/test_tui.py"""
import fcntl, os, pty, re, signal, struct, subprocess, sys, tempfile, termios, time

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
    raw = drain(fd, 1.5).decode("utf-8", "replace")
    txt = STRIP.sub("", raw)
    check("branch in header", "⎇ main" in txt or "main" in txt)
    check("py nerd glyph", "" in txt)
    check("md nerd glyph", "" in txt)
    check("folder nerd glyph", "" in txt)
    check("modified marker", "M" in txt)

    # --- navigate: expand src/, fuzzy find ---
    os.write(fd, b"l")
    txt = STRIP.sub("", drain(fd, 0.8).decode("utf-8", "replace"))
    check("expand shows util.py", "util.py" in txt)
    os.write(fd, b"/util\r")
    txt = STRIP.sub("", drain(fd, 0.8).decode("utf-8", "replace"))
    check("fuzzy find", "src/util.py" in txt)
    os.write(fd, b"q")
    status, _ = wait_exit(pid, fd)
    check("q clean exit", status == 0)

    # --- ctrl-c: clean exit, no traceback ---
    pid, fd = spawn(repo)
    drain(fd, 1.2)
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
```

- [ ] **Step 2: Run it** — `python3 tests/test_tui.py`. Expected: all PASS (this validates the earlier untested Ctrl-C raw-mode fix; if ctrl-c checks fail, fix before proceeding).

- [ ] **Step 3: Commit** — `git add tests/test_tui.py && git commit -m "test: pty regression harness"`

---

### Task 2: Split into modules

**Files:**
- Create: `sideview_tui/__init__.py`, `sideview_tui/icons.py`, `sideview_tui/textutil.py`, `sideview_tui/gitstate.py`, `sideview_tui/app.py`, `sideview_tui/theme.py`, `sideview_tui/ui.py`, `sideview_tui/main.py`
- Modify: `sideview` (becomes launcher)
- Test: `tests/test_tui.py` (unchanged — must stay green)

**Interfaces (what moves where; code moves verbatim unless noted):**
- `icons.py`: `EMOJI`, `NERD`, `ICON_COLORS`, `EXT_CLASS`, `NAME_CLASS`, `ICON_STYLE`, `ICONS`, `classify(name, is_dir, is_open=False) -> str`, `icon_for(name, is_dir, is_open=False) -> str`
- `textutil.py`: `cells(s) -> int`, `fit(s, width) -> str`
- `gitstate.py`: `run(args, cwd) -> str|None`, `class Git` (`.branch`, `.ahead`, `.behind`, `.files`, `.dirty_dirs`, `.refresh()`, `.code(rel)`, `.counts() -> (staged, unstaged, untracked)`)
- `app.py`: `NOISE_DIRS`, `PREVIEW_MAX_LINES`, `EDITOR`, `class Node`, `class App` (imports `Git`, `run` from `.gitstate`)
- `theme.py`: `C_*` pair constants, `SEL_ATTR`, `ICON_PAIRS = {}`, `init_theme()`, `node_attr(app, node)`. `SEL_ATTR` is set by `init_theme()`; consumers must reference it as `theme.SEL_ATTR` (module attribute), never `from theme import SEL_ATTR`.
- `ui.py`: `put(win, y, x, text, attr=0, maxw=None)`, `draw_scrollbar(...)`, `draw(stdscr, app)` (imports `icons`, `theme`, `cells`/`fit`)
- `main.py`: `main(stdscr, root)`, `cli()` (imports `App`, `draw`, `theme`)
- `sideview` launcher:

```python
#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from sideview_tui.main import cli

cli()
```

(`cli()` keeps the `__doc__` help text — move the docstring to `main.py` and print `main.__doc__`.)

- [ ] **Step 1: Create the package files**, moving code as mapped above.
- [ ] **Step 2: Syntax-check all modules** — `python3 -m compileall sideview_tui sideview` (expect no errors).
- [ ] **Step 3: Run tests** — `python3 tests/test_tui.py`. Expected: all PASS (pure refactor).
- [ ] **Step 4: Commit** — `git add -A && git commit -m "refactor: split single file into sideview_tui package"`

---

### Task 3: Colored per-filetype icons (TDD)

**Files:**
- Modify: `sideview_tui/theme.py` (`init_theme`), `sideview_tui/ui.py` (tree row + preview title), `tests/test_tui.py` (two assertions)

**Interfaces:**
- Produces: `theme.ICON_PAIRS: dict[str, tuple[int, int]]` — class → `(attr_normal, attr_selected)`; populated only for nerd style on 256-color terminals. Pair ids 30+ reserved for icons.

- [ ] **Step 1: Add failing assertions** to `tests/test_tui.py` after the glyph checks:

```python
    check("py icon colored (fg 68)", "38;5;68" in raw)
    check("md icon colored (fg 109)", "38;5;109" in raw)
```

- [ ] **Step 2: Run** — `python3 tests/test_tui.py`. Expected: exactly those two FAIL.

- [ ] **Step 3: Register icon pairs** at the end of the 256-color branch of `theme.init_theme()` (after `SEL_ATTR = ...`):

```python
        if icons.ICON_STYLE == "nerd":
            pair = 30
            for cls, col in icons.ICON_COLORS.items():
                curses.init_pair(pair, col, bg)
                curses.init_pair(pair + 1, col, sbg)
                ICON_PAIRS[cls] = (curses.color_pair(pair),
                                   curses.color_pair(pair + 1))
                pair += 2
```

- [ ] **Step 4: Draw icons with their own attr** in `ui.draw()`. Tree row — replace the single `line`/`put` with:

```python
        cls = icons.classify(n.name, n.is_dir, n.rel in app.expanded)
        icon_attr = attr
        if theme.ICON_PAIRS and not n.is_dir or (n.is_dir and theme.ICON_PAIRS):
            icon_attr = theme.ICON_PAIRS.get(cls, (attr, attr))[1 if sel else 0]
        x = 1 + 2 * n.depth
        put(stdscr, y, 1, "  " * n.depth, attr)
        if x < mark_x - 1:
            put(stdscr, y, x, ic, icon_attr, mark_x - 1 - x)
            x += cells(ic)
        put(stdscr, y, x, name, attr, mark_x - 1 - x)
```

(simplify the condition to `icon_attr = theme.ICON_PAIRS.get(cls, (attr, attr))[1 if sel else 0] if theme.ICON_PAIRS else attr`). Preview title — replace the single title `put` with:

```python
        if node:
            cls = icons.classify(node.name, node.is_dir,
                                 node.rel in app.expanded)
            t_icon = icons.icon_for(node.name, node.is_dir,
                                    node.rel in app.expanded)
            i_attr = (theme.ICON_PAIRS.get(cls, (0, 0))[0]
                      if theme.ICON_PAIRS
                      else curses.color_pair(theme.C_TITLE))
            put(stdscr, 1, px, t_icon, i_attr, pw)
            put(stdscr, 1, px + cells(t_icon),
                node.rel + ("  [diff]" if app.diff_mode else ""),
                curses.color_pair(theme.C_TITLE) | curses.A_BOLD,
                pw - cells(t_icon))
```

- [ ] **Step 5: Run tests** — `python3 tests/test_tui.py`. Expected: all PASS.
- [ ] **Step 6: Commit** — `git add -A && git commit -m "feat: per-filetype colored nerd icons"`

---

### Task 4: LazyVim install with language extras

**Files:**
- Create: `~/.config/nvim` (LazyVim starter clone, `.git` removed)
- Modify: `~/.config/nvim/lazyvim.json` (enable extras; preserve the starter's other keys)

- [ ] **Step 1: Verify absent + clone**

```bash
test -e ~/.config/nvim && echo "ABORT: config exists" || \
  git clone --depth=1 https://github.com/LazyVim/starter ~/.config/nvim
rm -rf ~/.config/nvim/.git
```

- [ ] **Step 2: Enable extras** — edit `~/.config/nvim/lazyvim.json` so `"extras"` contains:

```json
[
  "lazyvim.plugins.extras.lang.docker",
  "lazyvim.plugins.extras.lang.python",
  "lazyvim.plugins.extras.lang.terraform",
  "lazyvim.plugins.extras.lang.typescript",
  "lazyvim.plugins.extras.lang.yaml"
]
```

- [ ] **Step 3: Headless sync (background, minutes)** — `nvim --headless "+Lazy! sync" +qa; echo "exit=$?"` → `exit=0`.
- [ ] **Step 4: Verify** — `ls ~/.local/share/nvim/lazy | wc -l` > 25 and `nvim --headless "+lua print(#require('lazy').plugins())" +qa 2>&1` prints > 30. No commit (config lives outside the repo).

---

### Task 5: Final verification and push

- [ ] **Step 1: Full suite** — `python3 tests/test_tui.py` → all PASS.
- [ ] **Step 2: Editor resolution** — `python3 -c "import sys; sys.path.insert(0,'.'); from sideview_tui.app import EDITOR; print(EDITOR)"` → `nvim`.
- [ ] **Step 3: Symlink check** — `~/.local/bin/sideview --help` prints usage (proves launcher + symlink work).
- [ ] **Step 4: Check off plan boxes, commit, push**

```bash
git add -A && git commit -m "docs: implementation plan (executed)" && git push
```
