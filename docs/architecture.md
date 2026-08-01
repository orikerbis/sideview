# Architecture

Pure Python stdlib + curses; no dependencies. ~2.5k lines across small
modules with one job each:

```
sideview_tui/
  main.py      CLI entry, event loop, key/mouse dispatch, width probe
  app.py       application state: tree, selection, preview cache,
               fuzzy find, grep, git actions, editor integration
  ui.py        all drawing: frame, header, tree, preview, diffs, help
  markdown.py  .md → styled segment rows for the reading view
  syntax.py    tiny regex lexers for the syntax highlighting
  gitstate.py  repo discovery, status parsing, counts, branch info
  theme.py     tokyonight palette, color pairs, truecolor setup
  icons.py     file-type icon tables (nerd / emoji), classification
  textutil.py  cell-width helpers, terminal width probe
  doctor.py    --doctor checks, Nerd Font download/install
```

## Drawing model

One `draw()` per event: erase, paint background, frame, header, tree,
preview, status. curses diffs the virtual screen and emits minimal
updates, so a full logical redraw is cheap. Two caches keep big trees
snappy: indent guides are computed once per `build_visible()`, and the
preview (file contents or diff) is cached per `(path, mtime, mode)`.
Markdown rendering has its own `(path, mtime)` cache and returns exactly
one styled row per source line, so scrolling, in-file search, and
drag-copy all share raw line indexes.

The header and preview title are additionally marked for a full
physical rewrite (`redrawln`) whenever their content changes — some
terminals mis-track glyph widths across minimal updates and would
otherwise mix stale and fresh fragments (see the width probe in
`docs/configuration.md`).

## Git integration

`gitstate.Git` discovers every repo under the root (including the root
itself), parses `git status --porcelain -z` per repo off the UI thread,
and exposes:

- `repo_for(rel)` — which repo owns a path (the header follows this)
- `code(rel)` / `counts(prefix)` — per-file status and +/- totals
- `dirty_dirs` — collapsed dirs that contain changes (the `•` marker)

Actions (stage, commit, push, discard) always run `-C <owning repo>`,
so a folder of repos behaves like one workspace.

## Testing

`tests/test_units.py` runs without a pty: a `FakeWin` char grid stands
in for a curses window, so layout rules ("the tee never punctures the
header", "markdown hides line numbers") are plain string assertions.
Git behavior is tested against real throwaway repos in `/tmp`. CI runs
the suite on each push (`.github/workflows/test.yml`).
