"""All drawing: header bar, tree pane, preview pane, bottom bar."""
import curses
import os

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
    """Shared pane geometry: (split_visible, tree_width)."""
    split = app.preview_on and w >= 60 and not app.filter_input
    tree_w = max(24, min(int(w * app.split), w - 26)) if split else w
    return split, tree_w


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
    for row in range(2, body_h):
        i = app.pscroll + row - 2
        if i >= len(rows_data):
            break
        kind, num, text, lang = rows_data[i]
        text = text.replace("\t", "    ")
        y = 1 + row
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


def draw(stdscr, app):
    h, w = stdscr.getmaxyx()
    stdscr.erase()
    # paint the dark background explicitly: wbkgd() merges its color pair
    # into every cell on some ncurses builds, flattening per-cell colors
    for y in range(h):
        put(stdscr, y, 0, " " * w, curses.color_pair(theme.C_TEXT))

    # ----- header bar -----
    home = os.path.expanduser("~")
    disp = app.root.replace(home, "~", 1)
    info = ""
    if app.git.branch:
        info = "⎇ " + app.git.branch
        if app.git.ahead:
            info += " ↑%d" % app.git.ahead
        if app.git.behind:
            info += " ↓%d" % app.git.behind
        s, u, t = app.git.counts()
        parts = [f"{n}{lbl}" for n, lbl in ((s, "●"), (u, "±"), (t, "?")) if n]
        info += "  " + (" ".join(parts) if parts else "✔")
    badge = " CHANGES " if app.changes else ""
    room = w - cells(info) - cells(badge) - 4
    if len(disp) > room:
        disp = "…" + disp[-(max(room, 8) - 1):]
    put(stdscr, 0, 0, " " * w, curses.color_pair(theme.C_HEAD))
    put(stdscr, 0, 1, disp,
        curses.color_pair(theme.C_HEAD) | curses.A_BOLD, room + 1)
    if badge:
        put(stdscr, 0, 2 + cells(disp), badge,
            curses.color_pair(theme.C_MSG) | curses.A_BOLD)
    put(stdscr, 0, max(0, w - cells(info) - 1), info,
        curses.color_pair(theme.C_HEADGIT) | curses.A_BOLD)

    body_h = h - 2
    split, tree_w = layout(app, w)

    if app.sel < app.scroll:
        app.scroll = app.sel
    if app.sel >= app.scroll + body_h:
        app.scroll = app.sel - body_h + 1

    # ----- tree pane -----
    mark_x = tree_w - 3
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
        y = 1 + row
        sel = idx == app.sel
        if sel:
            put(stdscr, y, 0, " " * tree_w, theme.SEL_ATTR)
            put(stdscr, y, 0, "▌",
                curses.color_pair(theme.C_ACCENT) | curses.A_BOLD)
            attr = theme.SEL_ATTR
        cls = icons.classify(n.name, n.is_dir, n.rel in app.expanded)
        icon_attr = (theme.ICON_PAIRS.get(cls, (attr, attr))[1 if sel else 0]
                     if theme.ICON_PAIRS else attr)
        x = 1 + 2 * n.depth
        put(stdscr, y, 1, "  " * n.depth, attr)
        if x < mark_x - 1:
            put(stdscr, y, x, ic, icon_attr, mark_x - 1 - x)
            x += cells(ic)
        put(stdscr, y, x, name, attr, mark_x - 1 - x)
        if mark:
            put(stdscr, y, mark_x, mark, attr | curses.A_BOLD)
    draw_scrollbar(stdscr, tree_w - 1, 1, body_h, len(app.visible), app.scroll)

    if not app.visible:
        put(stdscr, 1, 1, "(no matches)" if app.filter else "(empty)",
            curses.color_pair(theme.C_DIM))

    # ----- preview pane -----
    if split:
        if len(app.visible) <= body_h:
            for row in range(body_h):
                put(stdscr, 1 + row, tree_w - 1, "│",
                    curses.color_pair(theme.C_DIM))
        px, pw = tree_w + 1, w - tree_w - 2
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
        put(stdscr, 2, px, "─" * pw, curses.color_pair(theme.C_DIM))
        if app.changes:
            draw_pretty_diff(stdscr, app, rows_data, px, pw, body_h)
        lang = (syntax.detect(node.name)
                if not app.changes and node and not node.is_dir else None)
        for row in range(2, body_h) if not app.changes else ():
            i = app.pscroll + row - 2
            if i >= len(lines):
                break
            ln = lines[i].replace("\t", "    ")
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
        draw_scrollbar(stdscr, w - 1, 3, body_h - 2, total, app.pscroll)

    # ----- bottom bar -----
    put(stdscr, h - 1, 0, " " * w, curses.color_pair(theme.C_BAR))
    if app.filter_input:
        prompt = ("🔍" if icons.ICON_STYLE == "emoji" else "/") \
            + " " + app.filter
        put(stdscr, h - 1, 1, prompt,
            curses.color_pair(theme.C_MSG) | curses.A_BOLD, w - 2)
        pos = f"{min(app.sel + 1, len(app.visible))}/{len(app.visible)}"
        put(stdscr, h - 1, max(0, w - len(pos) - 1), pos,
            curses.color_pair(theme.C_BAR) | curses.A_BOLD)
        curses.curs_set(1)
        stdscr.move(h - 1, min(w - 1, 1 + cells(prompt)))
    else:
        curses.curs_set(0)
        if app.message:
            put(stdscr, h - 1, 1, app.message,
                curses.color_pair(theme.C_MSG) | curses.A_BOLD, w - 2)
        elif app.changes:
            put(stdscr, h - 1, 1,
                "CHANGES  j/k file  [ ] hunks  ⇥ focus  ⏎ edit  Esc back",
                curses.color_pair(theme.C_MSG) | curses.A_BOLD, w - 12)
        else:
            put(stdscr, h - 1, 1,
                "⏎ open  / find  D changes  →← focus  y path  -+ size  q quit",
                curses.color_pair(theme.C_BAR), w - 12)
        pos = f"{min(app.sel + 1, len(app.visible))}/{len(app.visible)}"
        put(stdscr, h - 1, max(0, w - len(pos) - 1), pos,
            curses.color_pair(theme.C_BAR) | curses.A_BOLD)
    stdscr.refresh()
