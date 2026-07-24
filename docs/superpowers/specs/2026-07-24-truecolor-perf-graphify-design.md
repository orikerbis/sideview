# Truecolor theme, frame-loop performance, Graphify setup — design

Date: 2026-07-24
Status: approved

## Context

Three pieces of work, approved together:

1. Header rendering bug (already fixed, ships with this work): the `┬`
   divider tee was drawn after the header text and punched a moving hole in
   repo/branch names on narrow panes; `+`/`-` moved the hole. Fixed by
   drawing the tee before `draw_header` so text paints over it. A second
   fix makes `git status` output non-ASCII filenames raw
   (`core.quotepath=off`) so files like `_דיאגרמה ללא שם_.drawio` keep
   their status marks and counts. Both covered by `tests/test_units.py`.
2. Visuals: exact tokyonight colors via terminal palette redefinition.
3. Performance and code quality in the draw loop, plus Graphify indexing
   for AI assistants.

## 1. Truecolor theme (`theme.py` only)

When the terminal supports palette redefinition — `curses.can_change_color()`
and `COLORS >= 256`, opt out with `SIDEVIEW_TRUECOLOR=off` — redefine only
the palette slots the theme already uses to exact tokyonight-night RGB
(fg `#c0caf5`, blue `#7aa2f7`, cyan `#7dcfff`, green `#9ece6a`, yellow
`#e0af68`, orange `#ff9e64`, red `#f7768e`, magenta `#bb9af7`, teal
`#73daca`, comment `#565f89`, backgrounds `#1a1b26`/`#24283b`/`#414868`)
via `curses.init_color` (0–1000 scale). Icon color slots keep their
256-color values; only theme slots are redefined.

- No pair ids, drawing code, or layout change.
- Terminals that ignore OSC 4 (Terminal.app) silently keep the current
  256-color approximations — that is the fallback, no detection needed
  beyond `can_change_color()`.
- ncurses restores the palette on exit via the `oc` capability where the
  terminal supports it.

## 2. Performance + code quality

Profiling (100 frames, 2,040 visible nodes, fake curses window):
`tree_guides` is 0.188s of 0.287s total — 65% of frame time — recomputed
per frame though it depends only on the visible list.

- Cache guides: compute in `App.build_visible()` (stored as `app.guides`),
  drop the per-frame call in `ui.draw`. Guides length always matches
  `app.visible`.
- ~~Skip idle repaints~~ — dropped during implementation: ncurses already
  diffs the virtual screen, so an unchanged 1 Hz redraw emits ~0 bytes and
  (with guides cached) costs ~1 ms of Python per second. Not worth the
  preview-liveness risk.
- Split the ~250-line `ui.draw` into `draw_tree`, `draw_preview`,
  `draw_status` (plus existing helpers). No behavior change; the pty suite
  and unit tests guard it.

## 3. Graphify setup

Vetted: GitHub `Graphify-Labs/graphify`, 95k stars, Apache-2.0, active;
PyPI package `graphifyy` links back to the same repo.

- Install isolated: `pipx install graphifyy`.
- Run its indexer on this repo per its README and wire the generated
  `/graphify` skill files into the repo so Claude Code (and other
  assistants) can query the codebase graph.
- Commit only config/skill files; `.gitignore` large generated artifacts.

## Out of scope

- Animated transitions (declined during brainstorming).
- App-side mitigation of macOS Terminal bidi reordering of RTL filenames
  (terminal behavior, not fixable from curses).

## Testing

- `tests/test_units.py`: fake-curses draw assertions (header integrity,
  tee presence) and git non-ASCII path parsing; extended with a guides-cache
  consistency check.
- `tests/test_tui.py`: full pty regression suite must stay green.
- Truecolor: assert `init_theme` calls `init_color` for the expected slots
  when `can_change_color()` is true (monkeypatched), and doesn't when
  `SIDEVIEW_TRUECOLOR=off`.
