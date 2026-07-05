"""sideview — vim-style file navigator + git dashboard for a side terminal pane.

Usage:
    sideview [DIR]
    sideview --doctor          check fonts/editor/git/claude setup
    sideview --install-font    install the Symbols Nerd Font (icons)

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
    F               follow mode: auto-jump to the newest changed file
                    (leave on while an AI agent edits your repo)
    s / u           git stage / unstage the selected file
    c / C           git commit: c opens $EDITOR prefilled with a generated
                    message (Claude CLI if available, else a summary);
                    C commits immediately with the generated message
    X               discard changes to the selected file (press twice)
    Tab             switch focus: tree <-> preview (j/k etc. scroll the
                    focused pane); Right arrow on a file also enters the
                    preview, Left arrow returns to the tree
    d               toggle diff view in preview
    p               toggle preview pane
    < / > or - / +  make the tree pane narrower / wider
    J/K             scroll preview
    y / Y           copy selected file's path / contents to clipboard
    / (in preview)  search inside the file/diff; n / N next / prev match
    mouse           click select, double-click open, wheel scroll both
                    panes, drag the separator to resize, drag over preview
                    lines to select+copy them; hold Option (Alt) to use
                    the terminal's native text selection instead
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
from .app import App, MOUSE_OFF, MOUSE_ON, Node
from .ui import draw, layout

def set_mouse(on):
    os.write(sys.stdout.fileno(), MOUSE_ON if on else MOUSE_OFF)


def read_escape(stdscr):
    """After a 27, parse a mouse report in SGR ('[<b;x;y M|m') or X10
    ('[M' + 3 bytes) encoding. Returns an event dict, "csi" for other
    sequences, or None for a plain Esc. We parse both protocols ourselves:
    old ncurses can't report wheel-down and some terminals lack SGR."""
    stdscr.timeout(0)
    try:
        c = stdscr.getch()
        if c == -1:
            return None
        if c != ord("["):
            curses.ungetch(c)
            return None
        c = stdscr.getch()
        if c == ord("M"):                       # X10: Cb Cx Cy (+32)
            cb, cx, cy = (stdscr.getch() for _ in range(3))
            if -1 in (cb, cx, cy):
                return "csi"
            b = cb - 32
            wheel = bool(b & 64)
            release = (b & 3) == 3 and not wheel
            if release:
                b &= ~3                          # X10 release hides button
            return {"b": b, "x": cx - 33, "y": cy - 33, "release": release}
        if c != ord("<"):
            while c != -1 and not 64 <= c <= 126:  # swallow unknown CSI
                c = stdscr.getch()
            return "csi"
        buf = ""
        while True:
            c = stdscr.getch()
            if c == -1:
                return "csi"
            if chr(c) in "Mm":
                fin = chr(c)
                break
            buf += chr(c)
        try:
            b, x, y = (int(t) for t in buf.split(";"))
        except ValueError:
            return "csi"
        return {"b": b, "x": x - 1, "y": y - 1, "release": fin == "m"}
    finally:
        stdscr.timeout(1000)


def handle_mouse(stdscr, app, ev):
    mx, my, released = ev["x"], ev["y"], ev["release"]
    b = ev["b"]
    wheel = b & 64
    motion = bool(b & 32) and not wheel
    press = not released and not motion and not wheel and (b & 3) == 0
    h, w = stdscr.getmaxyx()
    split, tree_w = layout(app, w)
    sep = tree_w - 1

    if wheel:
        down = (b & 1) == 1
        if split and mx >= tree_w:
            app.pscroll = max(0, app.pscroll + (3 if down else -3))
        elif app.visible:
            app.sel = max(0, min(app.sel + (3 if down else -3),
                                 len(app.visible) - 1))
            if app.changes:
                app.scroll_to_selected_change()
        return

    if app.dragging:
        app.split = min(0.80, max(0.20, mx / max(w, 1)))
        app.message = "◂ resize: %d%% ▸ (also - / +)" % round(app.split * 100)
        if released:
            app.dragging = False
        return

    # drag in the preview pane: select lines, copy on release
    if app.psel_active and app.psel:
        app.psel[1] = max(0, app.pscroll + my - 3)
        if released:
            app.psel_active = False
            if app.changes:
                lines = [r[2] for r in app.repo_diff_rows()]
            else:
                node = app.selected()
                lines = (app.preview_lines(node)
                         if node and not node.is_dir else None)
            if lines:
                a, bb = sorted(app.psel)
                bb = min(bb, len(lines) - 1)
                text = "\n".join(lines[a:bb + 1])
                if text and clipboard(text):
                    app.message = "copied %d line(s)" % (bb - a + 1)
            # keep app.psel: highlight stays until the next key/click
        return

    if press and split and abs(mx - sep) <= 2:
        app.dragging = True
        app.message = "◂ resize ▸"
        return
    if press and split and mx > sep + 2 and 3 <= my <= h - 2:
        line = app.pscroll + my - 3
        app.psel = [line, line]
        app.psel_active = True
        return

    # click in the tree: select; fast second click: open
    if press and mx < tree_w and 1 <= my <= h - 2:
        idx = app.scroll + my - 1
        if idx < len(app.visible):
            double = (time.time() - app.last_click_t < 0.4
                      and app.last_click_idx == idx)
            app.last_click_t, app.last_click_idx = time.time(), idx
            app.sel = idx
            app.pscroll = 0
            app.psel = None
            if app.changes:
                app.scroll_to_selected_change()
            if double:
                node = app.visible[idx]
                if node.is_dir:
                    app.toggle_dir(node)
                else:
                    app.edit(stdscr, node)
                app.build_visible()


def clipboard(text):
    try:
        import subprocess
        subprocess.run(["pbcopy"], input=text.encode(), timeout=2)
        return True
    except Exception:
        return False


def psearch_jump(app, node, direction, from_here=False):
    if app.changes:
        lines = [r[2] for r in app.repo_diff_rows()]
    else:
        lines = app.preview_lines(node) if node else []
    q = app.psearch.lower()
    hits = [i for i, l in enumerate(lines) if q in l.lower()]
    if not hits:
        app.message = "no matches for: " + app.psearch
        return
    if from_here:
        nxt = [i for i in hits if i >= app.pscroll]
        app.pscroll = nxt[0] if nxt else hits[0]
    elif direction > 0:
        nxt = [i for i in hits if i > app.pscroll]
        app.pscroll = nxt[0] if nxt else hits[0]
    else:
        prev = [i for i in hits if i < app.pscroll]
        app.pscroll = prev[-1] if prev else hits[-1]
    app.message = "%d match(es)" % len(hits)


def main(stdscr, root):
    theme.init_theme()
    curses.raw()  # deliver Ctrl-C as a key (handled as quit), not SIGINT
    curses.curs_set(0)
    stdscr.timeout(1000)
    set_mouse(True)
    app = App(root)
    app.build_visible()

    try:
        _loop(stdscr, app)
    finally:
        app.save_state()


def _loop(stdscr, app):
    while True:
        draw(stdscr, app)
        # re-assert each frame: editors/ncurses can reset the modes
        os.write(sys.stdout.fileno(), MOUSE_ON)
        ch = stdscr.getch()
        app.message = ""

        if ch == -1:
            if time.time() - app.last_git > 3:
                app.git.refresh()
                app.last_git = time.time()
                app.preview_cache = None
                app.repo_diff = None
                app.build_visible()  # pick up created/deleted files
                if app.follow and app.changes:
                    newest = app.newest_change()
                    for i, n in enumerate(app.visible):
                        if n.rel == newest and i != app.sel:
                            app.sel = i
                            app.scroll_to_selected_change()
                            break
            continue

        if ch == 27:
            ev = read_escape(stdscr)
            if isinstance(ev, dict):
                handle_mouse(stdscr, app, ev)
                continue
            if ev == "csi":
                continue
            # plain Esc falls through to the handlers below
        elif ch != -1:
            # any real keypress clears the copy-selection highlight
            app.psel, app.psel_active = None, False

        if app.psearch_input:
            if ch == 27:
                app.psearch_input, app.psearch = False, ""
            elif ch in (10, 13, curses.KEY_ENTER):
                app.psearch_input = False
                psearch_jump(app, app.selected(), +1, from_here=True)
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                app.psearch = app.psearch[:-1]
            elif 32 <= ch < 127:
                app.psearch += chr(ch)
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
            if app.focus == "preview" and app.changes:
                rel, line = app.changes_line_at(app.pscroll)
                if rel:
                    path = os.path.join(app.root, rel)
                    app.edit(stdscr, Node(path, rel, os.path.basename(rel),
                                          False, 0), line)
                    app.build_visible()
            elif app.focus == "preview" and node and not node.is_dir:
                app.edit(stdscr, node, app.pscroll + 1)
                app.build_visible()
            elif node and node.is_dir and ch != ord("e"):
                app.toggle_dir(node)
                app.build_visible()
            elif node and not node.is_dir:
                app.edit(stdscr, node)
                if app.filter:
                    app.filter = ""
                app.build_visible()
        elif ch == ord("/"):
            if app.focus == "preview":
                app.psearch_input, app.psearch = True, ""
            else:
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
        elif ch == ord("s"):
            if node and not node.is_dir and app.git.code(node.rel):
                app.stage(node)
                app.message = "staged " + node.rel
        elif ch == ord("u"):
            if node and not node.is_dir:
                app.unstage(node)
                app.message = "unstaged " + node.rel
        elif ch == ord("X"):
            if node and not node.is_dir and app.git.code(node.rel):
                if app.git.code(node.rel) == "??":
                    app.message = "untracked — delete it yourself if you mean it"
                elif app.pending_discard == node.rel:
                    app.discard(node)
                    app.pending_discard = None
                    app.message = "discarded changes: " + node.rel
                else:
                    app.pending_discard = node.rel
                    app.message = ("discard changes to %s? press X again"
                                   % node.rel)
        elif ch in (ord("c"), ord("C")):
            if app.git.counts()[0]:
                rc = app.run_commit(stdscr, auto=(ch == ord("C")))
                app.message = "committed" if rc == 0 else "commit aborted"
            else:
                app.message = "nothing staged (s to stage)"
        elif ch == ord("F"):
            app.follow = not app.follow
            if app.follow and not app.changes:
                app.changes = True
                app.diff_mode = True
                app.sel = app.pscroll = 0
                app.repo_diff = None
                app.build_visible()
            app.message = "follow on" if app.follow else "follow off"
        elif ch in (ord("n"), ord("N")):
            if app.psearch:
                psearch_jump(app, node, +1 if ch == ord("n") else -1)
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
        if ch != ord("X"):
            app.pending_discard = None
        if app.changes and app.focus == "tree" and ch in (
                ord("j"), ord("k"), curses.KEY_DOWN, curses.KEY_UP,
                ord("g"), ord("G"), 4, 21, ord("D")):
            app.scroll_to_selected_change()
        app.pending_g = False


def cli():
    if "--doctor" in sys.argv[1:]:
        from .doctor import run_doctor
        sys.exit(run_doctor())
    if "--install-font" in sys.argv[1:]:
        from .doctor import install_font
        sys.exit(install_font())
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
    finally:
        os.write(sys.stdout.fileno(), MOUSE_OFF)
