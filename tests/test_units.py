#!/usr/bin/env python3
"""Unit tests that don't need a pty: drawing onto a fake curses window and
git-status parsing. Run: python3 tests/test_units.py"""
import curses
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

FAILURES = []


def check(name, ok):
    print(("PASS" if ok else "FAIL"), name)
    if not ok:
        FAILURES.append(name)


class FakeWin:
    """Char-grid stand-in for a curses window (attrs ignored). Good enough
    for layout assertions: every glyph the frame/header uses is one cell."""

    def __init__(self, h, w):
        self.h, self.w = h, w
        self.grid = [[" "] * w for _ in range(h)]

    def getmaxyx(self):
        return self.h, self.w

    def erase(self):
        self.grid = [[" "] * self.w for _ in range(self.h)]

    def addstr(self, y, x, text, attr=0):
        if not 0 <= y < self.h or x < 0:
            raise curses.error("out of window")
        for i, ch in enumerate(text):
            if x + i >= self.w:
                raise curses.error("write past end")
            self.grid[y][x + i] = ch

    def insstr(self, y, x, text, attr=0):
        for i, ch in enumerate(text):
            if 0 <= y < self.h and 0 <= x + i < self.w:
                self.grid[y][x + i] = ch

    def move(self, y, x):
        pass

    def refresh(self):
        pass

    def row(self, y):
        return "".join(self.grid[y])


def make_repo(parent, name, branch, dirty=False):
    d = os.path.join(parent, name)
    os.makedirs(d, exist_ok=True)

    def g(*a):
        subprocess.run(["git", "-C", d, "-c", "user.email=t@t",
                        "-c", "user.name=t", *a], capture_output=True)

    g("init", "-b", branch)
    open(os.path.join(d, "f.py"), "w").write("x = 1\n")
    g("add", "-A")
    g("commit", "-m", "init")
    if dirty:
        open(os.path.join(d, "f.py"), "a").write("y = 2\n")
    return d


def draw_fixture(branch):
    """(app, win) for a 60x30 pane over a repo with the given branch."""
    parent = tempfile.mkdtemp(prefix="sv-units-")
    repo = make_repo(parent, "proj", branch)
    os.environ["SIDEVIEW_STATE"] = os.path.join(parent, "state.json")
    from sideview_tui.app import App
    app = App(repo)
    app.build_visible()
    return app, FakeWin(30, 60)


def test_header_not_punctured_by_tee():
    """The ┬ joining the divider to the top border must never replace a
    character of the header text (repo name / branch)."""
    from sideview_tui import ui
    app, win = draw_fixture("feature/long-branch-name-here")
    curses.color_pair = lambda n: 0
    curses.curs_set = lambda n: 0
    ui.draw(win, app)
    top = win.row(0)
    check("header keeps branch name intact",
          "feature/long-branch-name-here" in top)
    hole = any(top[x] == "┬"
               and (top[x - 1].isalnum() or top[x + 1].isalnum())
               for x in range(1, win.w - 1))
    check("no ┬ hole inside a header word", not hole)


def test_tee_still_drawn_with_short_header():
    """When the header text ends before the divider column, the ┬ tee must
    still connect the divider to the top border."""
    from sideview_tui import ui
    app, win = draw_fixture("m")
    curses.color_pair = lambda n: 0
    curses.curs_set = lambda n: 0
    ui.draw(win, app)
    _split, tree_w = ui.layout(app, win.w)
    check("tee present on short header", win.row(0)[tree_w + 1] == "┬")


def test_git_status_nonascii_path():
    """git quotes non-ASCII paths in octal escapes; the parsed status keys
    must be the real filenames so marks and +N/-N counts include them."""
    from sideview_tui.gitstate import Git
    parent = tempfile.mkdtemp(prefix="sv-units-git-")
    repo = make_repo(parent, "heb", "main")
    name = "_דיאגרמה ללא שם_.drawio"
    open(os.path.join(repo, name), "w").write("x\n")
    git = Git(repo)
    check("non-ascii filename is a status key", git.files.get(name) == "??")
    staged, unstaged, untracked = git.counts("")
    check("non-ascii file counted as untracked", untracked == 1)


def test_truecolor_palette():
    """When the terminal can redefine its palette, init_theme sets the
    exact tokyonight RGB on the slots the theme uses; SIDEVIEW_TRUECOLOR=off
    keeps the stock 256-color palette."""
    from sideview_tui import theme
    calls = []
    curses.start_color = lambda: None
    curses.use_default_colors = lambda: None
    curses.COLORS = 256
    curses.can_change_color = lambda: True
    curses.init_color = lambda slot, r, g, b: calls.append((slot, r, g, b))
    curses.init_pair = lambda *a: None
    curses.color_pair = lambda n: 0
    theme.init_theme()
    by_slot = {c[0]: c[1:] for c in calls}
    check("truecolor redefines the fg slot", 189 in by_slot)
    # tokyonight fg #c0caf5 -> (753, 792, 961) on curses' 0-1000 scale
    check("fg slot gets exact tokyonight rgb",
          by_slot.get(189) == (753, 792, 961))
    check("truecolor redefines the bg slot", 234 in by_slot)
    calls.clear()
    os.environ["SIDEVIEW_TRUECOLOR"] = "off"
    theme.init_theme()
    check("SIDEVIEW_TRUECOLOR=off leaves palette alone", not calls)
    del os.environ["SIDEVIEW_TRUECOLOR"]


def test_guides_cached_in_build_visible():
    """Indent guides are computed once per build_visible (65% of frame time
    when recomputed per frame) and draw() renders from the cache."""
    from sideview_tui import ui
    parent = tempfile.mkdtemp(prefix="sv-units-guides-")
    repo = make_repo(parent, "proj", "main")
    sub = os.path.join(repo, "sub")
    os.makedirs(sub)
    open(os.path.join(sub, "child.py"), "w").write("x = 1\n")
    os.environ["SIDEVIEW_STATE"] = os.path.join(parent, "state.json")
    from sideview_tui.app import App
    app = App(repo)
    app.expanded = {"sub"}
    app.build_visible()
    curses.color_pair = lambda n: 0
    curses.curs_set = lambda n: 0
    win = FakeWin(30, 60)
    ui.draw(win, app)
    check("draw fills the guides cache",
          getattr(app, "guides", None) == ui.tree_guides(app.visible))
    # draw must render from the cache, not recompute
    app.guides = ["%%" for _ in app.visible]
    ui.draw(win, app)
    check("draw renders cached guides",
          any("%%" in win.row(y) for y in range(1, win.h - 1)))
    app.build_visible()
    check("build_visible invalidates the cache", app.guides is None)


def main():
    test_header_not_punctured_by_tee()
    test_tee_still_drawn_with_short_header()
    test_git_status_nonascii_path()
    test_truecolor_palette()
    test_guides_cached_in_build_visible()
    print()
    if FAILURES:
        print("FAILED:", ", ".join(FAILURES))
        sys.exit(1)
    print("all unit tests passed")


if __name__ == "__main__":
    main()
