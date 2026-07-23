"""All drawing: header bar, tree pane, preview pane, bottom bar."""
import curses
import os
import time

from . import icons, syntax, theme
from .textutil import cells, fit


def put(win, y, x, text, attr=0, maxw=None):
    if maxw is not None:
        text = fit(text, max(0, maxw))
    try:
        win.addstr(y, x, text, attr)
    except curses.error:
        pass


def layout(app, w):
    """Shared pane geometry: (split_visible, tree_width). Columns 0 and w-1
    are the outer frame; content lives in 1..w-2. The tree occupies cols
    1..tree_w, the divider sits at tree_w+1, the preview runs tree_w+2..w-2."""
    inner = w - 2
    split = (app.preview_on and inner >= 56
             and not app.filter_input and not app.grep_input)
    if not split:
        return False, inner
    tree_w = max(20, min(int(inner * app.split), inner - 26))
    return True, tree_w


def tree_guides(visible):
    """Per-node indent-guide prefix (│ ├ └ + spaces), same width as a plain
    2-per-depth indent, so nesting reads at a glance."""
    n = len(visible)
    # is_last[i]: no later sibling at the same depth in the same parent. One
    # reverse pass (O(n·depth)): a node is last unless we've already seen a
    # same-depth node to its right that a shallower node hasn't reset.
    is_last = [True] * n
    seen = {}
    for i in range(n - 1, -1, -1):
        d = visible[i].depth
        is_last[i] = not seen.get(d, False)
        seen[d] = True
        for dd in [k for k in seen if k > d]:   # deeper nodes were this node's
            del seen[dd]                        # subtree; reset past its parent
    out, cont = [], []
    for i in range(n):
        d = visible[i].depth
        s = "".join("│ " if (L < len(cont) and cont[L]) else "  "
                    for L in range(d - 1))
        if d > 0:
            s += "└ " if is_last[i] else "├ "
        if len(cont) < d + 1:
            cont += [False] * (d + 1 - len(cont))
        cont[d] = not is_last[i]
        del cont[d + 1:]
        out.append(s)
    return out


def fmt_size(nbytes):
    for unit in ("B", "K", "M", "G"):
        if nbytes < 1024 or unit == "G":
            return ("%d%s" if unit == "B" else "%.1f%s") % (nbytes, unit)
        nbytes /= 1024.0


def fmt_age(secs):
    for n, unit in ((86400, "d"), (3600, "h"), (60, "m")):
        if secs >= n:
            return "%d%s ago" % (secs // n, unit)
    return "just now"


def status_text(app):
    """The file-info line: what the selected item is."""
    if app.changes:
        return "%d changed file(s)" % len(app.git.files)
    node = app.selected()
    if node is None:
        return ""
    if node.is_dir:
        return node.name + "/  ·  directory"
    try:
        st = os.stat(node.path)
    except OSError:
        return node.rel
    bits = [node.name, fmt_size(st.st_size)]
    if not app.diff_mode:
        bits.append("%d lines" % len(app.preview_lines(node)))
    lang = syntax.detect(node.name)
    if lang:
        bits.append(lang)
    bits.append(fmt_age(max(0, int(time.time() - st.st_mtime))))
    return "  ·  ".join(bits)


def draw_frame(stdscr, w, h, hints):
    """Rounded outer frame with the key hints in the bottom edge. The header
    text (repo/branch + change indicator) is drawn by draw_header."""
    b = curses.color_pair(theme.C_BORDER)
    put(stdscr, 0, 0, "╭" + "─" * (w - 2) + "╮", b)
    # bottom edge: draw cols 0..w-2 normally, then insert the corner at the
    # last cell — writing there with addstr trips the curses lower-right-corner
    # error and drops the whole line (taking the bottom-left ╰ with it)
    put(stdscr, h - 1, 0, "╰" + "─" * (w - 2), b)
    try:
        stdscr.insstr(h - 1, w - 1, "╯", b)
    except curses.error:
        pass
    for y in range(1, h - 1):
        put(stdscr, y, 0, "│", b)
        put(stdscr, y, w - 1, "│", b)
    put(stdscr, h - 1, 3, " " + hints + " ",
        curses.color_pair(theme.C_BAR), w - 6)


def draw_header(stdscr, w, left, right, badge):
    """Top border content: repo name + branch on the left (updates with the
    selection), a compact + / - change indicator on the right. Both share the
    border background so they sit flush on the frame line, and the left is
    capped short of the right so they can never collide in a narrow pane."""
    bd = curses.color_pair(theme.C_BORDER)
    # right side first, so the left can budget around it
    rtotal = sum(cells(t) for t, _ in right)
    rx = w - rtotal - 3
    if rtotal:
        put(stdscr, 0, rx - 1, " ", bd)
        x = rx
        for text, pair in right:
            put(stdscr, 0, x, text, curses.color_pair(pair) | curses.A_BOLD)
            x += cells(text)
        put(stdscr, 0, min(w - 1, x), " ", bd)
    # left: repo name + branch (+ optional mode badge), capped short of right
    limit = (rx if rtotal else w - 1) - 1
    x = 2
    put(stdscr, 0, x, " ", bd)
    x += 1
    for text, pair in left:
        if x >= limit:
            break
        seg = fit(text, limit - x)
        put(stdscr, 0, x, seg, curses.color_pair(pair) | curses.A_BOLD)
        x += cells(seg)
    if badge and x + cells(badge) + 3 < limit:
        put(stdscr, 0, x + 1, " " + badge + " ",
            curses.color_pair(theme.C_MSG) | curses.A_BOLD)
        x += cells(badge) + 3
    if x < limit:
        put(stdscr, 0, x, " ", bd)


def draw_scrollbar(stdscr, x, top, height, total, offset):
    if total <= height:
        return
    for row in range(height):
        put(stdscr, top + row, x, "│", curses.color_pair(theme.C_DIM))
    thumb_h = max(1, height * height // total)
    thumb_top = min(height - thumb_h, offset * height // total)
    for row in range(thumb_h):
        put(stdscr, top + thumb_top + row, x, "┃",
            curses.color_pair(theme.C_TEXT) | curses.A_BOLD)


def draw_pretty_diff(stdscr, app, rows_data, px, pw, body_h):
    """Delta-style diff rendering: file header bars with stats, hunk
    markers, line-number gutter, colored change bars, syntax-highlighted
    added/context lines."""
    sel_range = sorted(app.psel) if app.psel else None
    for row in range(2, body_h):
        i = app.pscroll + row - 2
        if i >= len(rows_data):
            break
        kind, num, text, lang = rows_data[i]
        text = text.replace("\t", "    ")
        y = 1 + row
        if sel_range and sel_range[0] <= i <= sel_range[1]:
            put(stdscr, y, px, " " * pw, theme.SEL_ATTR)
            put(stdscr, y, px, text, theme.SEL_ATTR, pw)
            continue
        if kind == "blank":
            continue
        if kind == "file":
            put(stdscr, y, px, " " * pw, curses.color_pair(theme.C_HEAD))
            name = text.rsplit("  ", 1)[0]
            ic = icons.icon_for(os.path.basename(name), False)
            put(stdscr, y, px + 1, ic + text,
                curses.color_pair(theme.C_HEAD) | curses.A_BOLD, pw - 2)
            continue
        if kind == "hunk":
            put(stdscr, y, px + 6, text,
                curses.color_pair(theme.C_UNTR) | curses.A_BOLD, pw - 6)
            continue
        if kind == "meta":
            put(stdscr, y, px + 6, text, curses.color_pair(theme.C_DIM), pw - 6)
            continue
        # add / del / ctx: gutter bar + line number + code
        bar, num_pair = " ", theme.C_LINENO
        if kind == "add":
            bar, num_pair = "▎", theme.C_ADD
        elif kind == "del":
            bar, num_pair = "▎", theme.C_DEL
        put(stdscr, y, px, "%4s " % num, curses.color_pair(theme.C_LINENO))
        put(stdscr, y, px + 5, bar, curses.color_pair(num_pair))
        x, budget = px + 6, pw - 6
        if kind == "del":
            put(stdscr, y, x, text, curses.color_pair(theme.C_DEL), budget)
        elif lang:
            for seg, tok in syntax.segments(text, lang):
                if budget <= 0:
                    break
                pair = theme.SYNTAX_PAIRS.get(tok, theme.C_TEXT)
                attr = curses.color_pair(pair)
                if kind == "ctx" and tok == "":
                    attr = curses.color_pair(theme.C_DIM)
                put(stdscr, y, x, seg, attr, budget)
                used = min(cells(seg), budget)
                x += used
                budget -= used
        else:
            attr = curses.color_pair(
                theme.C_TEXT if kind == "add" else theme.C_DIM)
            put(stdscr, y, x, text, attr, budget)


HELP = [
    ("j / k", "move selection (arrow keys work too)"),
    ("gg / G", "jump to top / bottom"),
    ("Ctrl-d / Ctrl-u", "half page down / up"),
    ("l", "expand directory"),
    ("h", "collapse, or jump to parent"),
    ("Enter", "expand / collapse directory"),
    ("e", "edit file in $EDITOR"),
    ("/", "fuzzy find file: Up/Down browse, Enter keep, Esc cancel"),
    ("f", "find in files: grep an expression across all files"),
    ("D", "changes view: live repo-wide diff"),
    ("[ / ]", "previous / next diff hunk"),
    ("F", "follow mode: auto-jump to the newest change"),
    ("s / u", "git stage / unstage the selected file"),
    ("c", "commit: generated message, review in $EDITOR"),
    ("C", "commit instantly with the generated message"),
    ("P", "git push"),
    ("X X", "discard changes to the file (press twice)"),
    ("x x", "delete the file from disk (press twice)"),
    ("Tab", "switch focus: tree <-> preview"),
    ("Right / Left", "enter the preview / back to the tree"),
    ("J / K", "scroll the preview"),
    ("d", "toggle diff view in the preview"),
    ("p", "toggle the preview pane"),
    ("< >  or  - +", "make the tree pane narrower / wider"),
    ("/ (in preview)", "search in the file/diff; n / N next / prev"),
    ("y / Y", "copy file path / file contents"),
    (".", "show hidden files"),
    ("r", "refresh"),
    ("?", "this help"),
    ("q", "quit"),
    ("mouse", "click select, double-click open, wheel scroll,"),
    ("", "drag separator to resize, drag preview lines to copy"),
]


def draw_help(stdscr, app):
    """Full-screen key reference (?)."""
    h, w = stdscr.getmaxyx()
    stdscr.erase()
    for y in range(h):
        put(stdscr, y, 0, " " * w, curses.color_pair(theme.C_TEXT))
    put(stdscr, 0, 0, " " * w, curses.color_pair(theme.C_HEAD))
    put(stdscr, 0, 1, "sideview — keys",
        curses.color_pair(theme.C_HEAD) | curses.A_BOLD, w - 2)
    body = h - 2
    app.help_scroll = max(0, min(app.help_scroll, len(HELP) - body))
    for row in range(body):
        i = app.help_scroll + row
        if i >= len(HELP):
            break
        key, desc = HELP[i]
        put(stdscr, 1 + row, 2, key,
            curses.color_pair(theme.C_TITLE) | curses.A_BOLD, 16)
        put(stdscr, 1 + row, 19, desc,
            curses.color_pair(theme.C_TEXT), w - 20)
    draw_scrollbar(stdscr, w - 1, 1, body, len(HELP), app.help_scroll)
    put(stdscr, h - 1, 0, " " * w, curses.color_pair(theme.C_BAR))
    put(stdscr, h - 1, 1, "j/k scroll   ? / Esc / q close",
        curses.color_pair(theme.C_MSG) | curses.A_BOLD, w - 2)
    curses.curs_set(0)
    stdscr.refresh()


def draw(stdscr, app):
    if app.help_on:
        draw_help(stdscr, app)
        return
    h, w = stdscr.getmaxyx()
    stdscr.erase()
    # paint the dark background explicitly: wbkgd() merges its color pair
    # into every cell on some ncurses builds, flattening per-cell colors
    for y in range(h):
        put(stdscr, y, 0, " " * w, curses.color_pair(theme.C_TEXT))

    # ----- outer frame + header -----
    root_is_repo = any(r.prefix == "" for r in app.git.repos)
    sel = app.selected()
    repo = app.git.repo_for(sel.rel) if sel else None
    if repo is None and root_is_repo:
        repo = app.git.repos[0]
    title = os.path.basename(app.root.rstrip("/")) or app.root
    # left of the top border: the owning repo's name (cyan) + branch (yellow),
    # updating as the selection moves between repos
    left = []
    if repo is not None:
        left.append((repo.name(), theme.C_TITLE))
        left.append(("  ⎇ " + repo.branch, theme.C_MOD))
    elif app.git.repos:
        left.append((title, theme.C_HEAD))
        left.append(("  %d repos" % len(app.git.repos), theme.C_DIM))
    else:
        left.append((title, theme.C_HEAD))
    # right of the top border: a compact change indicator — +new (green) and
    # -modified (red), shown only when there is something to report
    right = []
    if repo is not None:
        s, u, t = app.git.counts(repo.prefix)
        if s + t:
            right.append(("+%d" % (s + t), theme.C_ADD))
        if u:
            right.append((("  " if right else "") + "-%d" % u, theme.C_DEL))
    badge = ("GREP" if app.grep_on else "FOLLOW" if app.follow
             else "CHANGES" if app.changes else "")
    if app.grep_on:
        hints = "j/k result  e open at line  Esc back to tree"
    elif app.changes:
        hints = "j/k file  [ ] hunks  s/u stage  c commit  Esc back"
    else:
        hints = "e edit  / find  f grep  D changes  →← focus  ? keys  q quit"
    draw_frame(stdscr, w, h, hints)
    draw_header(stdscr, w, left, right, badge)

    body_h = h - 3                          # rows 1..h-3; h-2 is the info line
    split, tree_w = layout(app, w)

    if app.sel < app.scroll:
        app.scroll = app.sel
    if app.sel >= app.scroll + body_h:
        app.scroll = app.sel - body_h + 1

    # ----- tree pane (cols 1..tree_w; col 1 is the accent gutter) -----
    guides = tree_guides(app.visible)
    mark_x = tree_w                         # git-status marker gutter (right)
    for row in range(body_h):
        idx = app.scroll + row
        if idx >= len(app.visible):
            break
        n = app.visible[idx]
        attr, mark = theme.node_attr(app, n)
        ic = icons.icon_for(n.name, n.is_dir, n.rel in app.expanded)
        name = n.name + ("/" if n.is_dir else "")
        if n.is_dir and n.rel in app.git.dirty_dirs \
                and n.rel not in app.expanded:
            mark = "•"
        mark_attr = None
        if mark and not n.is_dir:
            try:  # pulse: file changed in the last 30s (e.g. by an agent)
                if time.time() - os.stat(n.path).st_mtime < 30:
                    mark_attr = curses.color_pair(theme.C_MSG)
            except OSError:
                pass
        y = 1 + row
        sel = idx == app.sel
        if sel:
            put(stdscr, y, 1, " " * tree_w, theme.SEL_ATTR)
            put(stdscr, y, 1, "▌",
                curses.color_pair(theme.C_ACCENT) | curses.A_BOLD)
            attr = theme.SEL_ATTR
        cls = icons.classify(n.name, n.is_dir, n.rel in app.expanded)
        icon_attr = (theme.ICON_PAIRS.get(cls, (attr, attr))[1 if sel else 0]
                     if theme.ICON_PAIRS else attr)
        g = guides[idx]
        put(stdscr, y, 2, g,
            attr if sel else curses.color_pair(theme.C_GUIDE), mark_x - 2)
        x = 2 + cells(g)
        if x < mark_x - 1:
            put(stdscr, y, x, ic, icon_attr, mark_x - 1 - x)
            x += cells(ic)
        put(stdscr, y, x, name, attr, mark_x - 1 - x)
        if mark:
            put(stdscr, y, mark_x, mark,
                (mark_attr if mark_attr and not sel else attr)
                | curses.A_BOLD)

    if not app.visible:
        put(stdscr, 1, 2, "(no matches)" if app.filter else "(empty)",
            curses.color_pair(theme.C_DIM))

    # ----- divider + preview pane -----
    if split:
        bd = curses.color_pair(theme.C_BORDER)
        for row in range(body_h):
            put(stdscr, 1 + row, tree_w + 1, "│", bd)
        put(stdscr, 0, tree_w + 1, "┬", bd)       # meet the top border
        # (no ┴ at the bottom: the bottom border carries the key hints)
        px, pw = tree_w + 2, w - tree_w - 3
        node = app.selected()
        if app.changes:
            rows_data = app.repo_diff_rows()
            total = len(rows_data)
        else:
            lines = app.preview_lines(node)
            total = len(lines)
        app.pscroll = max(0, min(app.pscroll, max(0, total - body_h + 2)))
        if app.changes:
            x = px
            if app.focus == "preview":
                put(stdscr, 1, x, "▶ ",
                    curses.color_pair(theme.C_MSG) | curses.A_BOLD)
                x += 2
            put(stdscr, 1, x,
                "± all changes — %d file(s)" % len(app.git.files),
                curses.color_pair(theme.C_TITLE) | curses.A_BOLD, pw)
        elif node:
            x = px
            if app.focus == "preview":
                put(stdscr, 1, x, "▶ ",
                    curses.color_pair(theme.C_MSG) | curses.A_BOLD)
                x += 2
            cls = icons.classify(node.name, node.is_dir,
                                 node.rel in app.expanded)
            t_icon = icons.icon_for(node.name, node.is_dir,
                                    node.rel in app.expanded)
            i_attr = (theme.ICON_PAIRS.get(cls, (0, 0))[0]
                      if theme.ICON_PAIRS
                      else curses.color_pair(theme.C_TITLE))
            put(stdscr, 1, x, t_icon, i_attr, pw)
            put(stdscr, 1, x + cells(t_icon),
                node.rel + ("  [diff]" if app.diff_mode else ""),
                curses.color_pair(theme.C_TITLE) | curses.A_BOLD,
                pw - cells(t_icon) - (x - px))
        # title underline, connected to the divider and the right border
        put(stdscr, 2, px, "─" * pw, bd)
        put(stdscr, 2, tree_w + 1, "├", bd)
        try:
            stdscr.insstr(2, w - 1, "┤", bd)
        except curses.error:
            pass
        if app.changes:
            draw_pretty_diff(stdscr, app, rows_data, px, pw, body_h)
        lang = (syntax.detect(node.name)
                if not app.changes and node and not node.is_dir else None)
        sel_range = sorted(app.psel) if app.psel else None
        for row in range(2, body_h) if not app.changes else ():
            i = app.pscroll + row - 2
            if i >= len(lines):
                break
            ln = lines[i].replace("\t", "    ")
            if sel_range and sel_range[0] <= i <= sel_range[1] \
                    and not app.diff_mode:
                put(stdscr, 1 + row, px, " " * pw, theme.SEL_ATTR)
                put(stdscr, 1 + row, px, "%4d " % (i + 1) + ln,
                    theme.SEL_ATTR, pw)
                continue
            if app.diff_mode:
                attr = curses.color_pair(theme.C_TEXT)
                if ln.startswith("diff --git"):
                    attr = curses.color_pair(theme.C_TITLE) | curses.A_BOLD
                elif ln.startswith("+") and not ln.startswith("+++"):
                    attr = curses.color_pair(theme.C_ADD)
                elif ln.startswith("-") and not ln.startswith("---"):
                    attr = curses.color_pair(theme.C_DEL)
                elif ln.startswith("@@"):
                    attr = curses.color_pair(theme.C_UNTR)
                elif ln[:5] in ("diff ", "index"):
                    attr = curses.color_pair(theme.C_DIM)
                put(stdscr, 1 + row, px, ln, attr, pw)
                continue
            num = "%4d " % (i + 1)
            put(stdscr, 1 + row, px, num, curses.color_pair(theme.C_LINENO))
            x, budget = px + len(num), pw - len(num)
            x0, budget0 = x, budget
            if lang:
                for text, tok in syntax.segments(ln, lang):
                    if budget <= 0:
                        break
                    pair = theme.SYNTAX_PAIRS.get(tok, theme.C_TEXT)
                    put(stdscr, 1 + row, x, text,
                        curses.color_pair(pair), budget)
                    used = min(cells(text), budget)
                    x += used
                    budget -= used
            else:
                put(stdscr, 1 + row, x, ln,
                    curses.color_pair(theme.C_TEXT), budget)
            if app.psearch and app.psearch.lower() in ln.lower():
                c = ln.lower().index(app.psearch.lower())
                put(stdscr, 1 + row, x0 + c, ln[c:c + len(app.psearch)],
                    curses.color_pair(theme.C_MSG) | curses.A_BOLD
                    | curses.A_REVERSE, max(0, budget0 - c))
        draw_scrollbar(stdscr, w - 2, 3, body_h - 2, total, app.pscroll)

    # ----- status line (row h-2): input prompt, message, or file info.
    # The key hints live in the frame's bottom border. -----
    sy = h - 2
    if app.psearch_input:
        prompt = "in-file / " + app.psearch
        put(stdscr, sy, 2, prompt,
            curses.color_pair(theme.C_MSG) | curses.A_BOLD, w - 4)
        curses.curs_set(1)
        stdscr.move(sy, min(w - 2, 2 + cells(prompt)))
    elif app.filter_input:
        prompt = ("🔍" if icons.ICON_STYLE == "emoji" else "/") \
            + " " + app.filter
        put(stdscr, sy, 2, prompt,
            curses.color_pair(theme.C_MSG) | curses.A_BOLD, w - 4)
        pos = f"{min(app.sel + 1, len(app.visible))}/{len(app.visible)}"
        put(stdscr, sy, max(0, w - len(pos) - 2), pos,
            curses.color_pair(theme.C_DIM) | curses.A_BOLD)
        curses.curs_set(1)
        stdscr.move(sy, min(w - 2, 2 + cells(prompt)))
    elif app.grep_input:
        prompt = "find in files: " + app.grep_q
        put(stdscr, sy, 2, prompt,
            curses.color_pair(theme.C_MSG) | curses.A_BOLD, w - 4)
        curses.curs_set(1)
        stdscr.move(sy, min(w - 2, 2 + cells(prompt)))
    else:
        curses.curs_set(0)
        if app.message:
            put(stdscr, sy, 2, app.message,
                curses.color_pair(theme.C_MSG) | curses.A_BOLD, w - 4)
        elif app.grep_on:
            if app.grep_busy:
                info = "grep '%s' — searching…" % app.grep_q
            else:
                info = "grep '%s' — %d match(es)" % (
                    app.grep_q, len(app.grep_results))
            put(stdscr, sy, 2, info,
                curses.color_pair(theme.C_TITLE) | curses.A_BOLD, w - 4)
        else:
            put(stdscr, sy, 2, status_text(app),
                curses.color_pair(theme.C_DIM), w - 4)
    stdscr.refresh()
