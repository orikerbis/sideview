# Follow Mode + Git Actions + Persistence/Search + CI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Four user-approved features: agent follow mode, git actions from the pane, per-repo persistence + in-preview search, CI + pipx packaging.

**Architecture:** All state stays in `App` (sideview_tui/app.py), keys in `main.py`, rendering in `ui.py`, tests in the existing pty harness. Persistence is a JSON file at `~/.config/sideview/state.json` keyed by repo root. CI is a GitHub Actions matrix (ubuntu + macos) running `python3 tests/test_tui.py`; packaging is a `pyproject.toml` console script so `pipx install git+…` works.

## Global Constraints

- Python stdlib only; single pty test suite must stay green.
- Destructive git ops (discard) require a two-keypress confirm.
- Push only at the end.

---

### Task 1: Git actions + open-at-line

- [x] `App.stage(node)` / `App.unstage(node)` / `App.discard(node)` wrapping `git add` / `git restore --staged` / `git checkout --` on `node.rel`; each refreshes git state, invalidates `repo_diff`/`preview_cache`, rebuilds. Keys: `s`, `u`, `X` (X requires a second press on the same file; first press sets `app.pending_discard = rel` and shows a warning message; any other key clears it). Messages: `staged <rel>` / `unstaged <rel>` / `discarded changes: <rel>` / untracked files refuse discard.
- [x] `c` commit: if staged count == 0 → message `nothing staged (s to stage)`; else suspend curses like `App.edit` and run `git commit` (opens $EDITOR), then refresh; message from exit code (`committed` / `commit aborted`).
- [x] `App.edit(stdscr, node, line=None)` gains optional line → `[EDITOR, "+%d" % line, path]`. Enter with `focus == "preview"`: plain preview opens at `pscroll + 1`; changes view uses new helper `App.changes_line_at(idx) -> (rel, line)` that scans `repo_diff_rows()` backward from `pscroll` for the current `file` row and forward for the first numbered row.
- [x] Tests: select modified `app.py`, `s` → wait `staged`, `u` → wait `unstaged`. Commit with staged file + `EDITOR=/usr/bin/true` → aborts cleanly (message, no crash).
- [x] Commit.

### Task 2: Agent follow mode + fresh-change markers

- [x] `app.follow` bool; key `F` toggles (auto-enters changes view when off). Header badge shows `FOLLOW` (instead of `CHANGES`).
- [x] On the idle git tick, when following: pick the changed file with the newest mtime (`os.stat`, missing → 0); if it differs from the current selection, select it and `scroll_to_selected_change()`.
- [x] Tree rows: files whose mtime is < 30s old draw their status mark in `C_MSG` (orange) bold — a "just changed" pulse.
- [x] Tests: `F` → badge appears; append to `README.md` → within the tick the view jumps there (`wait_for(b"README.md")` on fresh output).
- [x] Commit.

### Task 3: Per-repo persistence + preview search

- [x] `App.load_state()` in `__init__` / `App.save_state()` on quit (try/finally around the main loop): JSON at `~/.config/sideview/state.json` keyed by `self.root`, storing `expanded`, `split`, `show_hidden`; keep at most 20 repo entries (drop oldest by `saved_at`).
- [x] Preview search: when `focus == "preview"`, `/` opens an `in-file /` prompt (own input mode, like the filter); Enter jumps to the first matching line ≥ pscroll; `n`/`N` jump next/previous (wrapping); works on `preview_lines` or pretty-diff row text; case-insensitive; `no matches` message. Matches in visible plain-preview lines get a highlighted substring overlay.
- [x] Tests: expand src + resize, quit, respawn → `util.py` visible without pressing `l` (persisted); preview search: focus preview on util.py, `/return⏎` no crash, `n` cycles (message or scroll, smoke).
- [x] Commit.

### Task 4: CI + packaging + docs

- [x] `pyproject.toml`: project `sideview-tui`, version 0.3.0, `[project.scripts] sideview = "sideview_tui.main:cli"`, setuptools backend, packages `sideview_tui`.
- [x] `.github/workflows/test.yml`: push/PR, matrix ubuntu-latest + macos-latest, setup-python 3.12, `git config --global user.email/name` for fixtures, run `python3 tests/test_tui.py`.
- [x] README: CI badge, pipx install instructions, new keys (`s u c X F` and preview `/ n N`), features updated.
- [x] Full suite twice; commit; push.
