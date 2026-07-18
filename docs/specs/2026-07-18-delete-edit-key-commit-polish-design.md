# sideview: delete key, e-to-edit, conventional commits, flicker-free C

Date: 2026-07-18
Status: approved

## Goal

Four small UX changes to the sideview TUI:

1. `e` becomes the only key that opens a file in `$EDITOR`; Enter no
   longer opens files (it still expands/collapses directories).
2. `x` (pressed twice) deletes the selected file from disk. Files only.
3. Generated commit messages (`c` / `C`) use Conventional Commits
   prefixes (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`).
4. `C` (instant commit) no longer suspends the TUI — no flash back to
   the terminal; progress and result appear in the status bar.

## 1. `e` opens files, Enter does not

`main.py` key loop currently binds `(10, 13, KEY_ENTER, ord("e"))` to
one handler that edits files and toggles directories.

Change:

- `e` → edit the selected file. Keeps all current edit behaviors:
  from the changes view it opens the file at the diff line under the
  preview cursor; with preview focus it opens at the current preview
  line; from the tree it opens the file and clears an active fuzzy
  filter.
- Enter → on a directory, toggle expand/collapse (as today); on a
  file, do nothing.
- Input modes are unchanged: Enter still confirms the fuzzy-find
  filter (`/`) and the in-preview search prompt.
- Update the module docstring (help text) in `main.py`: the
  `l or Enter   expand dir` / `Enter or e   edit file` lines and the
  fuzzy-find line ("Enter open" → open with `e` after closing the
  filter with Enter).

## 2. `x x` deletes the selected file

Mirrors the existing `X` (discard) press-twice pattern:

- New `App.pending_delete` field (rel path awaiting confirmation),
  next to `pending_discard`.
- First `x` on a file: status bar shows
  `delete <rel>? press x again`.
- Second consecutive `x` on the same file: `os.remove(path)`, then
  refresh (`git.refresh()`, invalidate `preview_cache` / `repo_diff`,
  `build_visible()`), clamp `app.sel` to the new list length, and show
  `deleted <rel>`.
- Any other key cancels the pending delete (same clearing mechanism as
  `pending_discard`).
- `x` on a directory: message `can't delete directories`, no action.
- `os.remove` failure (permissions, vanished file): show the error in
  the status bar, don't crash.
- Plain filesystem delete — not `git rm`. A tracked file shows up as
  deleted in git afterwards; the user can stage that with `s`.

Implementation: `App.delete_file(node)` method in `app.py` (does the
remove + refresh), key branch in `main.py`.

## 3. Conventional-commit prefixes

`App.commit_suggestion()` in `app.py`:

- AI path: change the haiku prompt to require Conventional Commits
  format — "Write a single-line git commit message in Conventional
  Commits format (type: description, types: feat/fix/chore/docs/
  refactor/test), max 70 chars, imperative mood…". The model picks the
  type from the staged diff.
- Heuristic fallback: prefix the existing summary with `feat:` when
  any file was added, otherwise `chore:`.

Applies to both `c` and `C` (shared generator).

## 4. `C` stays in the TUI

`App.run_commit(stdscr, auto)` currently calls `suspend_tui()` for
both modes.

- `auto=True` (`C`): do not suspend. Before the blocking work, set a
  status message `generating commit message…` and draw one frame so
  the user sees it. Run `commit_suggestion()` and
  `git commit -m <msg>` with output captured
  (`subprocess.run(..., capture_output=True)`). Show
  `committed ✔ <msg>` (truncated to fit) or the git error's first line
  in the status bar. The screen never leaves sideview.
- `auto=False` (`c`): unchanged — suspend, open `$EDITOR` prefilled,
  resume.

Note: during generation (up to a few seconds with the Claude CLI) the
UI blocks on the same thread, as it effectively does today; the only
difference is the status bar replaces the terminal flash. Drawing the
frame needs the `draw()` call or an explicit refresh from within
`run_commit` before blocking.

## Testing

Extend the pty-based `tests/test_tui.py`:

- Enter on a file does not launch the editor (file stays unopened /
  no editor process).
- `e` on a file launches `$EDITOR` (use a stub editor script).
- `x` then `x` on a temp file removes it from disk and the tree.
- `x` then a different key (e.g. `j`) leaves the file in place.
- `x` on a directory leaves it in place and shows the refusal message.
- Heuristic `commit_suggestion` output starts with `feat:` when a file
  is added, `chore:` for modifications (unit-style, `SIDEVIEW_COMMIT_AI=off`).
- `C` with `SIDEVIEW_COMMIT_AI=off` creates a commit whose subject has
  a conventional prefix, without the TUI suspending (screen still
  shows sideview afterwards).

## Out of scope

- Deleting directories (recursively or empty).
- Trash/undo for deleted files.
- Async/non-blocking message generation for `C`.
