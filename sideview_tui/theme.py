"""Dark 256-color theme (gruvbox-inspired) with 8-color fallback.

Consumers must reference SEL_ATTR as `theme.SEL_ATTR` (it is assigned by
init_theme after curses starts), never `from theme import SEL_ATTR`.
"""
import curses

from . import icons

(C_TEXT, C_DIR, C_MOD, C_ADD, C_DEL, C_UNTR, C_DIM, C_HEAD, C_HEADGIT,
 C_SEL, C_TITLE, C_BAR, C_LINENO, C_MSG, C_ACCENT) = range(1, 16)

SEL_ATTR = 0        # set by init_theme
ICON_PAIRS = {}     # icon class -> (attr_normal, attr_selected); nerd only


def init_theme():
    global SEL_ATTR
    curses.start_color()
    curses.use_default_colors()
    if curses.COLORS >= 256:
        bg, hbg, sbg = 234, 236, 239
        pairs = {
            C_TEXT: (250, bg), C_DIR: (111, bg), C_MOD: (179, bg),
            C_ADD: (142, bg), C_DEL: (167, bg), C_UNTR: (73, bg),
            C_DIM: (241, bg), C_HEAD: (223, hbg), C_HEADGIT: (142, hbg),
            C_SEL: (231, sbg), C_TITLE: (108, bg), C_BAR: (246, hbg),
            C_LINENO: (240, bg), C_MSG: (215, hbg), C_ACCENT: (208, sbg),
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
