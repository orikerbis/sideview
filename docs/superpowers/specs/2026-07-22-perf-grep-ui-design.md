# sideview — perf, global grep, UI polish (2026-07-22)

Five changes, shipped together to `main` with a version bump.

## 1. Fix lag in a directory full of git repos

**Cause:** on a non-git root, `Git.refresh()` runs on the UI thread and spawns
3–4 git subprocesses per repo (`symbolic-ref` + `rev-list` + `status` [+ sha
fallback]) and re-walks up to 4000 dirs — on startup, every 3s idle, and after
every action. Up to ~320 spawns per refresh → the freeze.

**Fix:**
- One subprocess per repo: `git status --porcelain --branch` returns branch,
  ahead/behind, and file status together. Parse the `## branch...upstream
  [ahead N, behind M]` header line; fall back to a short-sha only when detached.
- Background periodic refresh: the 3s refresh runs on a daemon thread; the UI
  loop swaps the result in atomically via `consume_update()`. Manual `r` and
  post-action refreshes stay synchronous for immediate consistency.
- Cache repo discovery: walk for repos once (and on `r` / hidden-toggle), not
  every 3s.

## 2. Startup optimization

- Parallelize per-repo status in `_compute` with a small `ThreadPoolExecutor`
  (subprocess waits release the GIL), so N repos resolve in batched waits
  instead of N serial ones. Same code path used by the initial construction and
  the background refresh.

## 3. `f` — find in files (global content grep)

- `f` opens a `find in files:` prompt (mirrors the `/` filter UI); Enter runs
  the search on a daemon thread (huge trees never freeze), Esc cancels.
- Walks all files under the root (all repos), skips `.git`/noise/hidden and
  binary files, caps ~1000 hits.
- Results replace the tree as `path:line` rows; the preview shows the selected
  file scrolled to the match with the term highlighted (reuses the preview
  search highlight). `e` opens `$EDITOR` at that line; `Esc` returns to the tree.

## 4. Push (P) stays in the TUI

- `run_push` captures output with `subprocess.run` (no curses suspend), sets a
  result message (`pushed ✔ …` / `push failed: …`), `GIT_TERMINAL_PROMPT=0` +
  timeout so a credential need fails fast instead of hanging. Mirrors `C`.

## 5. Better visualization

- Divider integrates with the frame: `┬`/`┴` junctions top/bottom; the preview
  title rule connects with `├`/`┤`.
- Colored git status in the header: branch cyan, `↑` green, `↓` red, staged `●`
  green / modified `±` yellow / untracked `?` cyan (was one flat green blob).

## Testing

pty checks: multi-repo startup renders without hang; `f` finds a string across
repos and lists `path:line`; header shows colored counts. Existing branch/⎇/
frame assertions stay green.

## Files
`gitstate.py`, `app.py`, `main.py`, `ui.py`, `theme.py`, `tests/test_tui.py`,
`README.md`, `pyproject.toml` (version bump 0.4.0 → 0.5.0).
