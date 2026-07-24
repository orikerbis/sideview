"""Dark 256-color theme (tokyonight-night, matching LazyVim) with
8-color fallback.

Consumers must reference SEL_ATTR as `theme.SEL_ATTR` (it is assigned by
init_theme after curses starts), never `from theme import SEL_ATTR`.
"""
import curses
import os

from . import icons

(C_TEXT, C_DIR, C_MOD, C_ADD, C_DEL, C_UNTR, C_DIM, C_HEAD, C_HEADGIT,
 C_SEL, C_TITLE, C_BAR, C_LINENO, C_MSG, C_ACCENT,
 C_SYN_COMMENT, C_SYN_STRING, C_SYN_NUMBER, C_SYN_KEYWORD,
 C_SYN_KEY, C_BORDER, C_GUIDE) = range(1, 23)

SEL_ATTR = 0        # set by init_theme
ICON_PAIRS = {}     # icon class -> (attr_normal, attr_selected); nerd only

# exact tokyonight-night RGB for the 256-color slots the theme uses,
# applied when the terminal lets us redefine its palette (truecolor look
# with the 256-color pair ids unchanged). SIDEVIEW_TRUECOLOR=off skips it.
PALETTE = {
    234: 0x1A1B26, 236: 0x24283B, 239: 0x414868,   # bg / header bg / sel bg
    238: 0x3B4261, 240: 0x414868,                  # lineno+guide / border
    60: 0x565F89, 103: 0x737AA2,                   # comment-dim / bar text
    111: 0x7AA2F7, 116: 0x73DACA, 117: 0x7DCFFF,   # blue / teal / cyan
    141: 0xBB9AF7, 149: 0x9ECE6A, 179: 0xE0AF68,   # magenta / green / yellow
    189: 0xC0CAF5, 210: 0xF7768E, 215: 0xFF9E64,   # fg / red / orange
}


def _apply_truecolor():
    if os.environ.get("SIDEVIEW_TRUECOLOR", "on") == "off":
        return
    try:
        if not curses.can_change_color():
            return
        for slot, rgb in PALETTE.items():
            curses.init_color(slot,
                              round((rgb >> 16) * 1000 / 255),
                              round(((rgb >> 8) & 0xFF) * 1000 / 255),
                              round((rgb & 0xFF) * 1000 / 255))
    except curses.error:
        pass    # terminal lied about ccc: keep the stock palette

# syntax token class -> color pair id
SYNTAX_PAIRS = {
    "comment": C_SYN_COMMENT, "string": C_SYN_STRING,
    "number": C_SYN_NUMBER, "keyword": C_SYN_KEYWORD, "key": C_SYN_KEY,
}


def init_theme():
    global SEL_ATTR
    curses.start_color()
    curses.use_default_colors()
    if curses.COLORS >= 256:
        _apply_truecolor()
        # tokyonight-night approximations: fg #c0caf5→189, blue #7aa2f7→111,
        # cyan #7dcfff→117, green #9ece6a→149, yellow #e0af68→179,
        # orange #ff9e64→215, red #f7768e→210, magenta #bb9af7→141,
        # teal #73daca→116, comment #565f89→60
        bg, hbg, sbg = 234, 236, 239
        pairs = {
            C_TEXT: (189, bg), C_DIR: (111, bg), C_MOD: (179, bg),
            C_ADD: (149, bg), C_DEL: (210, bg), C_UNTR: (116, bg),
            C_DIM: (60, bg), C_HEAD: (189, hbg), C_HEADGIT: (149, hbg),
            C_SEL: (231, sbg), C_TITLE: (117, bg), C_BAR: (103, hbg),
            C_LINENO: (238, bg), C_MSG: (215, hbg), C_ACCENT: (215, sbg),
            C_SYN_COMMENT: (60, bg), C_SYN_STRING: (149, bg),
            C_SYN_NUMBER: (215, bg), C_SYN_KEYWORD: (141, bg),
            C_SYN_KEY: (111, bg),
            C_BORDER: (240, bg), C_GUIDE: (238, bg),
        }
        SEL_ATTR = curses.color_pair(C_SEL) | curses.A_BOLD
        if icons.ICON_STYLE == "nerd":
            pair = 30  # ids 30+ reserved for icon colors
            for cls, col in icons.ICON_COLORS.items():
                curses.init_pair(pair, col, bg)
                curses.init_pair(pair + 1, col, sbg)
                ICON_PAIRS[cls] = (curses.color_pair(pair),
                                   curses.color_pair(pair + 1))
                pair += 2
    else:
        pairs = {
            C_TEXT: (-1, -1), C_DIR: (curses.COLOR_BLUE, -1),
            C_MOD: (curses.COLOR_YELLOW, -1),
            C_ADD: (curses.COLOR_GREEN, -1),
            C_DEL: (curses.COLOR_RED, -1),
            C_UNTR: (curses.COLOR_CYAN, -1),
            C_DIM: (curses.COLOR_WHITE, -1), C_HEAD: (-1, -1),
            C_HEADGIT: (curses.COLOR_GREEN, -1), C_SEL: (-1, -1),
            C_TITLE: (curses.COLOR_GREEN, -1), C_BAR: (-1, -1),
            C_LINENO: (curses.COLOR_WHITE, -1),
            C_MSG: (curses.COLOR_YELLOW, -1),
            C_ACCENT: (curses.COLOR_YELLOW, -1),
            C_SYN_COMMENT: (curses.COLOR_CYAN, -1),
            C_SYN_STRING: (curses.COLOR_GREEN, -1),
            C_SYN_NUMBER: (curses.COLOR_YELLOW, -1),
            C_SYN_KEYWORD: (curses.COLOR_MAGENTA, -1),
            C_SYN_KEY: (curses.COLOR_BLUE, -1),
            C_BORDER: (curses.COLOR_BLUE, -1), C_GUIDE: (curses.COLOR_BLUE, -1),
        }
        SEL_ATTR = curses.A_REVERSE
    for pid, (f, b) in pairs.items():
        curses.init_pair(pid, f, b)


def node_attr(app, node):
    code = app.git.code(node.rel)
    if node.is_dir:
        return curses.color_pair(C_DIR) | curses.A_BOLD, ""
    if code is None:
        return curses.color_pair(C_TEXT), ""
    if code == "??":
        return curses.color_pair(C_UNTR), "?"
    x, y = code[0], code[1]
    ch = (y if y != " " else x)
    if "D" in code:
        return curses.color_pair(C_DEL), ch
    if x not in " ?" and y == " ":
        return curses.color_pair(C_ADD), ch
    return curses.color_pair(C_MOD), ch
