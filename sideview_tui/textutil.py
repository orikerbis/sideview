"""Terminal-cell-aware text helpers (double-width emoji safe)."""
from unicodedata import east_asian_width


def cells(s):
    return sum(2 if east_asian_width(ch) in "WF" else 1 for ch in s)


def fit(s, width):
    """Truncate string to fit in `width` terminal cells."""
    out, w = [], 0
    for ch in s:
        cw = 2 if east_asian_width(ch) in "WF" else 1
        if w + cw > width:
            break
        out.append(ch)
        w += cw
    return "".join(out)
