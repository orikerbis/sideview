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


def test_width_probe_parsing_and_fallback():
    """DSR replies -> measured widths; safe_glyph keeps a glyph only when
    the terminal renders it at the width curses assumes (Warp draws some
    symbols two cells wide, garbling partial header repaints)."""
    from sideview_tui import textutil
    buf = b"\x1b[1;2R\x1b[1;3R"
    check("probe parses reply columns to widths",
          textutil.parse_probe(buf, 2) == [1, 2])
    check("probe rejects missing replies",
          textutil.parse_probe(b"\x1b[1;2R", 2) is None)
    measured = {"⎇": 2, "": 1}
    check("safe_glyph skips a wide-rendered glyph",
          textutil.safe_glyph(["⎇", ""], measured) == "")
    check("safe_glyph falls back to default",
          textutil.safe_glyph(["⎇"], {"⎇": 2}, "") == "")
    check("safe_glyph trusts unmeasured glyphs",
          textutil.safe_glyph(["⎇"], {}) == "⎇")


def test_header_without_branch_glyph():
    """With BRANCH_SYM disabled (terminal renders it mis-sized), the header
    still shows the branch, with no leftover glyph or double spaces gap."""
    from sideview_tui import ui
    app, win = draw_fixture("main")
    curses.color_pair = lambda n: 0
    curses.curs_set = lambda n: 0
    old = ui.BRANCH_SYM
    ui.BRANCH_SYM = ""
    try:
        ui.draw(win, app)
        top = win.row(0)
        check("branch shown without glyph",
              "⎇" not in top and "main" in top)
    finally:
        ui.BRANCH_SYM = old


def test_chrome_rows_redrawn_on_header_change():
    """When the header or preview title changes, rows 0-1 must be marked
    for a full physical rewrite (redrawln) so terminals that mis-track
    glyph widths can't mix stale and fresh fragments."""
    from sideview_tui import ui
    app, win = draw_fixture("main")
    curses.color_pair = lambda n: 0
    curses.curs_set = lambda n: 0
    calls = []
    win.redrawln = lambda beg, num: calls.append((beg, num))
    ui.draw(win, app)
    check("first draw touches the chrome rows", (0, 2) in calls)
    calls.clear()
    ui.draw(win, app)
    check("unchanged chrome not re-touched", not calls)
    app.focus = "preview"
    ui.draw(win, app)
    check("focus change re-touches chrome", (0, 2) in calls)


def test_markdown_render():
    """render() styles headings/bullets/fences/inline and keeps a strict
    one-row-per-line mapping so scroll and search indexes stay valid."""
    from sideview_tui import markdown
    src = ["# Title", "plain **bold** and `code`", "- item", "> quoted",
           "```", "x = 1", "```", "---", "[link label](https://x.y)"]
    rows = markdown.render(src)
    check("md keeps 1:1 line mapping", len(rows) == len(src))
    check("md heading styled, hashes stripped",
          rows[0] == [("Title", "h1")])
    styles1 = [s for _, s in rows[1]]
    check("md inline bold+code segmented",
          "bold" in styles1 and "code" in styles1)
    check("md bold markers stripped",
          ("bold", "bold") in rows[1] and ("code", "code") in rows[1])
    check("md bullet becomes dot", rows[2][0] == ("• ", "bullet"))
    check("md quote gets a bar", rows[3][0] == ("│ ", "quote_bar"))
    check("md fence line dimmed", rows[4] == [("```", "fence")])
    check("md code block styled", rows[5] == [("x = 1", "codeblock")])
    check("md rule row", rows[7] == [("", "rule")])
    check("md link shows label only",
          rows[8] == [("link label", "link")])
    check("md non-md name detected",
          markdown.is_markdown("README.md")
          and not markdown.is_markdown("readme.txt"))


def test_markdown_preview_drawn():
    """A selected .md file renders styled (no '#', no line numbers) with a
    [reading] tag; after the m toggle the raw text and numbers return."""
    from sideview_tui import ui
    parent = tempfile.mkdtemp(prefix="sv-units-md-")
    repo = make_repo(parent, "proj", "main")
    open(os.path.join(repo, "README.md"), "w").write(
        "# Big Title\n\n- first item\n")
    os.environ["SIDEVIEW_STATE"] = os.path.join(parent, "state.json")
    from sideview_tui.app import App
    app = App(repo)
    app.build_visible()
    app.sel = next(i for i, n in enumerate(app.visible)
                   if n.name == "README.md")
    curses.color_pair = lambda n: 0
    curses.curs_set = lambda n: 0
    win = FakeWin(30, 80)
    ui.draw(win, app)
    body = "\n".join(win.row(y) for y in range(3, win.h - 2))
    check("md title tag shown", "[reading]" in win.row(1))
    check("md heading text shown without #",
          "Big Title" in body and "# Big Title" not in body)
    check("md bullet rendered as dot", "• first item" in body)
    check("md hides line numbers", "   1 " not in body)
    app.md_render = False
    ui.draw(win, app)
    body = "\n".join(win.row(y) for y in range(3, win.h - 2))
    check("raw view restores markup", "# Big Title" in body)
    check("raw tag shown", "[raw]" in win.row(1))


def test_gui_editor_opens_without_suspend():
    """EDITOR=cursor (or code/zed/…) opens file:line detached — the TUI
    keeps running instead of suspending for a GUI that returns at once."""
    from sideview_tui import app as app_mod
    app, _ = draw_fixture("main")
    node = app.visible[0]
    calls = []
    old_popen, old_editor = app_mod.subprocess.Popen, app_mod.EDITOR
    app_mod.EDITOR = "cursor"
    app_mod.subprocess.Popen = lambda cmd, **k: calls.append(cmd)
    try:
        app.edit(None, node, line=12)   # stdscr unused on the GUI path
    finally:
        app_mod.subprocess.Popen, app_mod.EDITOR = old_popen, old_editor
    check("cursor gets -g file:line",
          calls == [["cursor", "-g", node.path + ":12"]])
    check("gui edit reports in status", "cursor" in app.message)


def test_commit_ai_cursor_agent_fallback():
    """Without the claude CLI, commit_suggestion falls back to
    cursor-agent in print mode before the heuristic summary."""
    from sideview_tui import app as app_mod
    app, _ = draw_fixture("main")
    calls = []

    class R:
        returncode, stdout = 0, "feat: shiny thing\n"

    old_which, old_run = app_mod.shutil.which, app_mod.subprocess.run
    app_mod.shutil.which = \
        lambda n: "/bin/ca" if n == "cursor-agent" else None
    app_mod.subprocess.run = lambda cmd, **k: (calls.append(cmd), R)[1]
    try:
        msg = app.commit_suggestion()
    finally:
        app_mod.shutil.which, app_mod.subprocess.run = old_which, old_run
    # patching subprocess.run is module-global, so git calls land here too
    agent = [c for c in calls if c[0] == "cursor-agent"]
    check("cursor-agent used when claude missing",
          agent and "-p" in agent[0])
    check("cursor-agent message returned", msg == "feat: shiny thing")
    # SIDEVIEW_COMMIT_AI=claude must never invoke cursor-agent, even
    # though it is the only agent CLI installed here
    calls.clear()
    os.environ["SIDEVIEW_COMMIT_AI"] = "claude"
    app_mod.shutil.which = \
        lambda n: "/bin/ca" if n == "cursor-agent" else None
    app_mod.subprocess.run = lambda cmd, **k: (calls.append(cmd), R)[1]
    try:
        msg = app.commit_suggestion()
    finally:
        app_mod.shutil.which, app_mod.subprocess.run = old_which, old_run
        del os.environ["SIDEVIEW_COMMIT_AI"]
    check("forced claude skips cursor-agent",
          not [c for c in calls if c[0] == "cursor-agent"]
          and msg != "feat: shiny thing")


def test_full_repaint_on_resize():
    """A window-size change must schedule a clear-and-repaint (clearok):
    terminals that reflow on resize (Warp panes) otherwise keep ghost
    fragments of old headers in cells curses believes are unchanged."""
    from sideview_tui import ui
    app, win = draw_fixture("main")
    curses.color_pair = lambda n: 0
    curses.curs_set = lambda n: 0
    calls = []
    win.clearok = lambda flag: calls.append(flag)
    ui.draw(win, app)
    check("first draw schedules full repaint", calls == [True])
    calls.clear()
    ui.draw(win, app)
    check("same size: no forced repaint", not calls)
    win.h, win.w = win.h, win.w - 10
    win.erase()
    ui.draw(win, app)
    check("width change schedules full repaint", calls == [True])


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
    test_width_probe_parsing_and_fallback()
    test_header_without_branch_glyph()
    test_chrome_rows_redrawn_on_header_change()
    test_markdown_render()
    test_markdown_preview_drawn()
    test_gui_editor_opens_without_suspend()
    test_commit_ai_cursor_agent_fallback()
    test_full_repaint_on_resize()
    test_guides_cached_in_build_visible()
    print()
    if FAILURES:
        print("FAILED:", ", ".join(FAILURES))
        sys.exit(1)
    print("all unit tests passed")


if __name__ == "__main__":
    main()
