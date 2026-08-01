"""Markdown → styled rows for the preview pane.

render(lines) returns one row per input line — never more, never fewer —
so preview scrolling, in-file search, and drag-copy keep using raw line
indexes. Each row is a list of (text, style) segments; ui maps the style
names to curses attributes, keeping this module curses-free.
"""
import re

_H = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_NUM = re.compile(r"^(\s*)(\d+[.)])\s+(.*)$")
_RULE = re.compile(r"^\s*([-*_])( *\1){2,}\s*$")
_INLINE = re.compile(
    r"(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*\s][^*]*\*)|(!?\[[^\]]+\]\([^)\s]+\))")


def _inline(text, base="text"):
    """Split a line into (text, style) segments: `code`, **bold**,
    *italic*, [label](url) — markers stripped, url hidden."""
    segs, pos = [], 0
    for m in _INLINE.finditer(text):
        if m.start() > pos:
            segs.append((text[pos:m.start()], base))
        tok = m.group(0)
        if tok.startswith("`"):
            segs.append((tok[1:-1], "code"))
        elif tok.startswith("**"):
            segs.append((tok[2:-2], "bold"))
        elif tok.startswith(("[", "![")):
            tok = tok.lstrip("!")
            segs.append((tok[1:tok.index("]")], "link"))
        else:
            segs.append((tok[1:-1], "em"))
        pos = m.end()
    if pos < len(text):
        segs.append((text[pos:], base))
    return segs or [("", base)]


def render(lines):
    rows, fence = [], False
    for ln in lines:
        ln = ln.expandtabs(4)
        stripped = ln.strip()
        if stripped.startswith("```"):
            fence = not fence
            rows.append([(stripped, "fence")])
            continue
        if fence:
            rows.append([(ln, "codeblock")])
            continue
        m = _H.match(ln)
        if m:
            level = len(m.group(1))
            style = "h1" if level == 1 else "h2" if level == 2 else "h3"
            rows.append([(m.group(2), style)])
            continue
        if stripped and _RULE.match(ln):
            rows.append([("", "rule")])
            continue
        if stripped.startswith(">"):
            rows.append([("│ ", "quote_bar")]
                        + _inline(stripped.lstrip("> "), "quote"))
            continue
        m = _BULLET.match(ln)
        if m:
            rows.append([(m.group(1) + "• ", "bullet")] + _inline(m.group(2)))
            continue
        m = _NUM.match(ln)
        if m:
            rows.append([(m.group(1) + m.group(2) + " ", "bullet")]
                        + _inline(m.group(3)))
            continue
        rows.append(_inline(ln))
    return rows


def is_markdown(name):
    return name.lower().endswith((".md", ".markdown"))
