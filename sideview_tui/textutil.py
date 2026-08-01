"""Terminal-cell-aware text helpers (double-width emoji safe)."""
import os
import re
import select
import time
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


_DSR = re.compile(rb"\x1b\[(\d+);(\d+)R")


def parse_probe(buf, n):
    """Widths from n cursor-position replies. Each probe is CR + glyph +
    ESC[6n, so a reply column of c means the glyph rendered c-1 cells."""
    cols = [int(m.group(2)) for m in _DSR.finditer(buf)]
    if len(cols) != n:
        return None
    return [c - 1 for c in cols]


def probe_widths(chars, timeout=0.25):
    """Ask the terminal how many cells it really renders each char.

    Terminals disagree with wcwidth on some symbols (Warp draws a few of
    them two cells wide); chrome laid out around such a glyph garbles on
    partial repaints because curses' cursor model no longer matches the
    screen. Returns {char: cells}, or {} when the terminal can't be asked
    (no tty, no reply, SIDEVIEW_WIDTHPROBE=off).
    """
    if os.environ.get("SIDEVIEW_WIDTHPROBE", "on") == "off":
        return {}
    try:
        fd = os.open("/dev/tty", os.O_RDWR)
    except OSError:
        return {}
    import termios
    import tty
    try:
        old = termios.tcgetattr(fd)
    except termios.error:
        os.close(fd)
        return {}
    try:
        tty.setraw(fd)      # replies must not echo or wait for a newline
        os.write(fd, b"".join(b"\r" + ch.encode() + b"\x1b[6n"
                              for ch in chars))
        buf, deadline = b"", time.time() + timeout
        while buf.count(b"R") < len(chars) and time.time() < deadline:
            r, _, _ = select.select([fd], [], [], deadline - time.time())
            if not r:
                break
            buf += os.read(fd, 4096)
        os.write(fd, b"\r\x1b[2K")          # wipe the probe glyphs
        widths = parse_probe(buf, len(chars))
        return dict(zip(chars, widths)) if widths else {}
    except OSError:
        return {}
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        os.close(fd)


def safe_glyph(candidates, measured, default=""):
    """First candidate the terminal renders at the width curses assumes;
    unmeasured glyphs are trusted (probe unavailable = keep the default)."""
    for g in candidates:
        if all(measured.get(ch, cells(ch)) == cells(ch) for ch in g):
            return g
    return default
