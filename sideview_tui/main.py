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
    /               fuzzy find file (Enter open, Esc cancel)
    d               toggle diff view in preview
    p               toggle preview pane
    J/K             scroll preview
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
from .ui import draw


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
            continue

        if app.filter_input:
            if ch == 27:
                app.filter_input, app.filter = False, ""
            elif ch in (10, 13, curses.KEY_ENTER):
                app.filter_input = False
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
        elif ch in (ord("l"), curses.KEY_RIGHT):
            if node and node.is_dir:
                app.expanded.add(node.rel)
                app.build_visible()
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
        elif ch == 27:                             # Esc clears filter
            app.filter = ""
            app.build_visible()
        elif ch == ord("d"):
            app.diff_mode = not app.diff_mode
            app.pscroll = 0
            app.preview_cache = None
        elif ch == ord("p"):
            app.preview_on = not app.preview_on
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
            app.build_visible()
            app.message = "refreshed"
        elif ch == curses.KEY_RESIZE:
            pass
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
