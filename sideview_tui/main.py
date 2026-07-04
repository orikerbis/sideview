"""sideview — vim-style file navigator + git dashboard for a side terminal pane.

Usage:
    sideview [DIR]

Environment:
    SIDEVIEW_ICONS=nerd|emoji|off   icon style (default nerd)
    EDITOR                          editor for Enter/e (default nvim, else vim)

Keys:
    j/k or arrows   move           gg / G       top / bottom
    h               collapse / up  l or Enter   expand dir
    Enter or e      edit file in $EDITOR
    Ctrl-d/Ctrl-u   half page down/up
    /               fuzzy find file (type to filter, Up/Down to
                    browse results, Enter open, Esc cancel)
    D               changes view: one repo-wide diff of everything that
                    changed (untracked files included), updating live as
                    files change on disk (e.g. by an AI agent); the file
                    list on the left jumps to that file's diff section
    [ / ]           previous / next hunk in a diff
    Tab             switch focus: tree <-> preview (j/k etc. scroll the
                    focused pane); Right arrow on a file also enters the
                    preview, Left arrow returns to the tree
    d               toggle diff view in preview
    p               toggle preview pane
    < / > or - / +  make the tree pane narrower / wider
    J/K             scroll preview
    y / Y           copy selected file's path / contents to clipboard
    mouse           no capture: your terminal's native text selection and
                    copy work everywhere; the scroll wheel scrolls the
                    focused pane (terminals send arrow keys in TUIs)
    .               toggle hidden files
    r               refresh
    q               quit
"""
import curses
import locale
import os
import sys
import time

from . import theme
from .app import App
from .ui import draw, layout

def clipboard(text):
    try:
        import subprocess
        subprocess.run(["pbcopy"], input=text.encode(), timeout=2)
        return True
    except Exception:
        return False


def main(stdscr, root):
    theme.init_theme()
    curses.raw()  # deliver Ctrl-C as a key (handled as quit), not SIGINT
    curses.curs_set(0)
    stdscr.timeout(1000)
    app = App(root)
    app.build_visible()

    while True:
        draw(stdscr, app)
        ch = stdscr.getch()
        app.message = ""

        if ch == -1:
            if time.time() - app.last_git > 3:
                app.git.refresh()
                app.last_git = time.time()
                app.preview_cache = None
                app.repo_diff = None
                app.build_visible()  # pick up created/deleted files
            continue

        if app.filter_input:
            if ch == 27:
                app.filter_input, app.filter = False, ""
            elif ch in (10, 13, curses.KEY_ENTER):
                app.filter_input = False
            elif ch in (curses.KEY_DOWN, 14):      # browse results (Ctrl-n)
                app.sel = min(app.sel + 1, max(0, len(app.visible) - 1))
                continue
            elif ch in (curses.KEY_UP, 16):        # browse results (Ctrl-p)
                app.sel = max(app.sel - 1, 0)
                continue
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                app.filter = app.filter[:-1]
            elif 32 <= ch < 127:
                app.filter += chr(ch)
                app.sel = 0
            app.build_visible()
            continue

        node = app.selected()
        if ch in (ord("q"), 3):
            break
        elif ch == 9:                              # Tab: switch pane focus
            app.focus = "preview" if app.focus == "tree" else "tree"
        elif app.focus == "preview" and ch in (
                ord("j"), curses.KEY_DOWN, ord("k"), curses.KEY_UP,
                ord("g"), ord("G"), 4, 21, ord("h"), curses.KEY_LEFT):
            h, _ = stdscr.getmaxyx()
            if ch in (ord("h"), curses.KEY_LEFT):  # back to the tree
                app.focus = "tree"
            elif ch in (ord("j"), curses.KEY_DOWN):
                app.pscroll += 1
            elif ch in (ord("k"), curses.KEY_UP):
                app.pscroll = max(0, app.pscroll - 1)
            elif ch == ord("g"):
                if app.pending_g:
                    app.pscroll, app.pending_g = 0, False
                else:
                    app.pending_g = True
                    continue
            elif ch == ord("G"):
                app.pscroll = 1 << 30  # draw() clamps to the last page
            elif ch == 4:
                app.pscroll += (h - 4) // 2
            elif ch == 21:
                app.pscroll = max(0, app.pscroll - (h - 4) // 2)
        elif ch in (ord("["), ord("]")):           # jump between diff hunks
            if app.changes:
                hunks = [i for i, r in enumerate(app.repo_diff_rows())
                         if r[0] in ("hunk", "file")]
            else:
                hunks = [i for i, l in enumerate(app.preview_lines(node))
                         if l.startswith("@@")]
            if hunks:
                if ch == ord("]"):
                    nxt = [i for i in hunks if i > app.pscroll]
                    app.pscroll = nxt[0] if nxt else hunks[0]
                else:
                    prev = [i for i in hunks if i < app.pscroll]
                    app.pscroll = prev[-1] if prev else hunks[-1]
        elif ch in (ord("j"), curses.KEY_DOWN):
            app.sel = min(app.sel + 1, max(0, len(app.visible) - 1))
            app.pscroll = 0
        elif ch in (ord("k"), curses.KEY_UP):
            app.sel = max(app.sel - 1, 0)
            app.pscroll = 0
        elif ch == ord("g"):
            if app.pending_g:
                app.sel, app.pending_g, app.pscroll = 0, False, 0
            else:
                app.pending_g = True
                continue
        elif ch == ord("G"):
            app.sel = max(0, len(app.visible) - 1)
            app.pscroll = 0
        elif ch == 4:                              # Ctrl-d
            h, _ = stdscr.getmaxyx()
            app.sel = min(app.sel + (h - 2) // 2, max(0, len(app.visible) - 1))
        elif ch == 21:                             # Ctrl-u
            h, _ = stdscr.getmaxyx()
            app.sel = max(app.sel - (h - 2) // 2, 0)
        elif ch == ord("D"):                       # changed-files (diff) view
            app.changes = not app.changes
            app.diff_mode = app.changes
            app.sel, app.pscroll = 0, 0
            app.preview_cache = None
            app.repo_diff = None
            app.build_visible()
        elif ch in (ord("l"), curses.KEY_RIGHT):
            if node and node.is_dir:
                app.expanded.add(node.rel)
                app.build_visible()
            elif node:                             # file: enter the preview
                app.focus = "preview"
        elif ch in (ord("h"), curses.KEY_LEFT):
            app.collapse_or_parent()
            app.build_visible()
        elif ch in (10, 13, curses.KEY_ENTER, ord("e")):
            if node and node.is_dir and ch != ord("e"):
                app.toggle_dir(node)
                app.build_visible()
            elif node and not node.is_dir:
                app.edit(stdscr, node)
                if app.filter:
                    app.filter = ""
                app.build_visible()
        elif ch == ord("/"):
            app.filter_input, app.filter, app.sel = True, "", 0
            app.build_visible()
        elif ch == 27:                             # Esc: leave changes/filter
            if app.changes:
                app.changes = app.diff_mode = False
                app.sel = app.pscroll = 0
            app.filter = ""
            app.build_visible()
        elif ch == ord("d"):
            app.diff_mode = not app.diff_mode
            app.pscroll = 0
            app.preview_cache = None
        elif ch == ord("p"):
            app.preview_on = not app.preview_on
        elif ch in (ord("<"), ord("-")):           # tree narrower
            app.split = max(0.20, round(app.split - 0.06, 2))
        elif ch in (ord(">"), ord("+"), ord("=")):  # tree wider
            app.split = min(0.80, round(app.split + 0.06, 2))
        elif ch == ord("y"):
            if node and clipboard(node.path):
                app.message = "copied path: " + node.rel
        elif ch == ord("Y"):
            if node and not node.is_dir:
                try:
                    text = open(node.path, "rb").read().decode(
                        "utf-8", "replace")
                except OSError:
                    text = None
                if text is not None and clipboard(text):
                    app.message = "copied contents: " + node.rel
        elif ch == ord("J"):
            app.pscroll += 3
        elif ch == ord("K"):
            app.pscroll = max(0, app.pscroll - 3)
        elif ch == ord("."):
            app.show_hidden = not app.show_hidden
            app.build_visible()
        elif ch == ord("r"):
            app.git.refresh()
            app.preview_cache = None
            app.repo_diff = None
            app.build_visible()
            app.message = "refreshed"
        elif ch == curses.KEY_RESIZE:
            pass
        if app.changes and app.focus == "tree" and ch in (
                ord("j"), ord("k"), curses.KEY_DOWN, curses.KEY_UP,
                ord("g"), ord("G"), 4, 21, ord("D")):
            app.scroll_to_selected_change()
        app.pending_g = False


def cli():
    args = [a for a in sys.argv[1:] if a not in ("-h", "--help")]
    if len(args) != len(sys.argv) - 1:
        print(__doc__)
        return
    root = os.path.abspath(os.path.expanduser(args[0])) if args else os.getcwd()
    if not os.path.isdir(root):
        sys.exit(f"sideview: not a directory: {root}")
    locale.setlocale(locale.LC_ALL, "")
    os.environ.setdefault("ESCDELAY", "50")
    try:
        curses.wrapper(main, root)
    except KeyboardInterrupt:
        pass
