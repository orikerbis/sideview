# Delete Key, e-to-Edit, Conventional Commits, Flicker-Free C — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Four UX changes to the sideview TUI: `e` (not Enter) opens files, `x x` deletes the selected file, generated commit messages get Conventional Commits prefixes, and `C` commits without suspending the TUI.

**Architecture:** All changes live in the existing key loop (`sideview_tui/main.py`) and `App` methods (`sideview_tui/app.py`). Testing is the repo's single pty-based regression script `tests/test_tui.py` — it spawns the real TUI on a pty, sends keystrokes, and asserts on screen output; new sections slot into its existing linear flow.

**Tech Stack:** Python 3.8+, curses, pty test harness. No new dependencies.

**Spec:** `docs/specs/2026-07-18-delete-edit-key-commit-polish-design.md`

## Global Constraints

- Repo root: `/Users/orikerbis/PycharmProjects/sideview`. Run tests with `python3 tests/test_tui.py` from the repo root; success ends with `all tests passed`, failure lists `FAILED: <names>` and exits 1.
- The test is one linear `main()` flow — later sections depend on earlier repo/TUI state. Insert new sections exactly where each task says.
- Tree sort order is dirs first, then files case-insensitively (`src/`=0, `util.py`=1 when expanded, `app.py`=2, `notes.txt`=3, `README.md`=4).
- `SIDEVIEW_COMMIT_AI=off` is set in tests — commit messages come from the deterministic heuristic, never the Claude CLI.
- Keep code style: stdlib only, ~79-col lines, comments only for non-obvious constraints.

---

### Task 1: `e` opens files, Enter only toggles directories

**Files:**
- Modify: `sideview_tui/main.py` (docstring lines 10, 15, 18–19; key branch at line 418)
- Modify: `README.md` (lines 39, 91, 93)
- Test: `tests/test_tui.py` (editor stub in setup; new section after "y copies path")

**Interfaces:**
- Consumes: existing `App.edit(stdscr, node, line=None)`, `App.toggle_dir(node)`, `App.build_visible()`.
- Produces: key semantics relied on by later tasks' tests — Enter on a file is a no-op; `e` is the only editor key.

- [ ] **Step 1: Write the failing test**

In `tests/test_tui.py`, replace the editor setup line

```python
    os.environ["EDITOR"] = "/usr/bin/true"
```

with a stub editor that logs its arguments:

```python
    edlog = os.path.join(auxdir, "editor.log")
    with open(os.path.join(bindir, "fakeed"), "w") as f:
        f.write("#!/bin/sh\necho \"$@\" >> %s\n" % edlog)
    os.chmod(os.path.join(bindir, "fakeed"), 0o755)
    os.environ["EDITOR"] = os.path.join(bindir, "fakeed")
```

Then insert a new section immediately after the `check("clipboard has file path", ...)` line (selection is on `src/util.py` at that point):

```python
    # --- Enter must not open files; e must ---
    os.write(fd, b"\r")
    out = drain(fd, 0.8)
    check("enter does not edit file",
          not os.path.exists(edlog) and b"Traceback" not in out)
    os.write(fd, b"e")
    end = time.time() + 5
    while time.time() < end and not os.path.exists(edlog):
        drain(fd, 0.2)
    logged = open(edlog).read() if os.path.exists(edlog) else ""
    check("e opens editor", "src/util.py" in logged)
    wait_for(fd, b"util.py")           # TUI resumed and redrew
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/test_tui.py`
Expected: `FAIL enter does not edit file` (Enter currently launches the editor, so `editor.log` exists). All previously passing checks still PASS.

- [ ] **Step 3: Split the key binding in main.py**

In `sideview_tui/main.py`, replace the combined branch:

```python
        elif ch in (10, 13, curses.KEY_ENTER, ord("e")):
            if app.focus == "preview" and app.changes:
                rel, line = app.changes_line_at(app.pscroll)
                if rel:
                    path = os.path.join(app.root, rel)
                    app.edit(stdscr, Node(path, rel, os.path.basename(rel),
                                          False, 0), line)
                    app.build_visible()
            elif app.focus == "preview" and node and not node.is_dir:
                app.edit(stdscr, node, app.pscroll + 1)
                app.build_visible()
            elif node and node.is_dir and ch != ord("e"):
                app.toggle_dir(node)
                app.build_visible()
            elif node and not node.is_dir:
                app.edit(stdscr, node)
                if app.filter:
                    app.filter = ""
                app.build_visible()
```

with two branches — Enter handles directories only, `e` handles files only:

```python
        elif ch in (10, 13, curses.KEY_ENTER):
            if node and node.is_dir:
                app.toggle_dir(node)
                app.build_visible()
        elif ch == ord("e"):
            if app.focus == "preview" and app.changes:
                rel, line = app.changes_line_at(app.pscroll)
                if rel:
                    path = os.path.join(app.root, rel)
                    app.edit(stdscr, Node(path, rel, os.path.basename(rel),
                                          False, 0), line)
                    app.build_visible()
            elif app.focus == "preview" and node and not node.is_dir:
                app.edit(stdscr, node, app.pscroll + 1)
                app.build_visible()
            elif node and not node.is_dir:
                app.edit(stdscr, node)
                if app.filter:
                    app.filter = ""
                app.build_visible()
```

- [ ] **Step 4: Update the help text (main.py docstring)**

Line 10: `EDITOR                          editor for Enter/e (default nvim, else vim)` → `EDITOR                          editor for e (default nvim, else vim)`

Line 15: `    Enter or e      edit file in $EDITOR` → `    e               edit file in $EDITOR`

Lines 18–19: change `browse results, Enter open, Esc cancel)` → `browse results, e open, Esc cancel)`

- [ ] **Step 5: Update README.md**

Line 39–40: `**Edit in Neovim/vim**: \`Enter\` suspends the TUI and opens the file in` → `**Edit in Neovim/vim**: \`e\` suspends the TUI and opens the file in`

Line 91: `` | `Enter` | open dir, or edit file in `$EDITOR` | `` → `` | `Enter` | expand / collapse dir | ``

Line 93: `` (`↑`/`↓` browse results while typing, `Enter` open, `Esc` cancel) `` → `` (`↑`/`↓` browse results while typing, `e` open, `Esc` cancel) ``

Line 24–25: `` `Enter` on a focused diff/preview opens Neovim at that exact line `` → `` `e` on a focused diff/preview opens Neovim at that exact line ``

- [ ] **Step 6: Run the full test to verify it passes**

Run: `python3 tests/test_tui.py`
Expected: `all tests passed` — including `PASS enter does not edit file` and `PASS e opens editor`.

- [ ] **Step 7: Commit**

```bash
git add sideview_tui/main.py README.md tests/test_tui.py
git commit -m "feat: e opens files; Enter only expands/collapses directories"
```

---

### Task 2: `x x` deletes the selected file

**Files:**
- Modify: `sideview_tui/app.py` (`App.__init__`, new `delete_file` method after `discard`)
- Modify: `sideview_tui/main.py` (new `x` branch; pending-delete clearing; docstring)
- Modify: `README.md` (new key row)
- Test: `tests/test_tui.py` (new section just before the final `os.write(fd, b"q")`)

**Interfaces:**
- Consumes: `App._after_git_change()` (refreshes git, invalidates caches, rebuilds tree), `Node.path`/`Node.rel`/`Node.is_dir`.
- Produces: `App.pending_delete` (rel path str or None), `App.delete_file(node) -> str | None` (error message or None on success).

- [ ] **Step 1: Write the failing test**

In `tests/test_tui.py`, insert immediately before the final quit (`os.write(fd, b"q")` followed by `status, _ = wait_exit(pid, fd)`), i.e. after the preview-search section ends with `os.write(fd, b"\x1bOD")`:

```python
    # --- x deletes a file (press twice); refuses directories ---
    os.write(fd, b"gg")                    # select src/ (a directory)
    drain(fd, 0.3)
    os.write(fd, b"x")
    ok, _ = wait_for(fd, b"can't delete directories")
    check("x refuses directories", ok)
    open(f"{repo}/junk.txt", "w").write("bye\n")
    os.write(fd, b"r")                     # pick up the new file
    ok, _ = wait_for(fd, b"junk.txt")
    check("junk.txt appears", ok)
    os.write(fd, b"/junk\r")               # select it via fuzzy find
    wait_for(fd, b"junk.txt")
    os.write(fd, b"x")
    ok, _ = wait_for(fd, b"press x again")
    check("delete asks to confirm", ok)
    os.write(fd, b"k")                     # any other key cancels
    drain(fd, 0.4)
    check("cancel keeps file", os.path.exists(f"{repo}/junk.txt"))
    os.write(fd, b"x")
    wait_for(fd, b"press x again")
    os.write(fd, b"x")                     # confirm
    ok, _ = wait_for(fd, b"deleted junk.txt")
    check("x x deletes file", ok)
    check("file gone from disk", not os.path.exists(f"{repo}/junk.txt"))
    os.write(fd, b"\x1b")                  # clear the filter
    wait_for(fd, b"notes.txt")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/test_tui.py`
Expected: `FAIL x refuses directories` and the section's other checks fail (`x` is currently unbound, so no messages appear and `junk.txt` survives). Prior checks still PASS.

- [ ] **Step 3: Add state + method in app.py**

In `App.__init__`, directly under `self.pending_discard = None  # rel awaiting X confirmation`, add:

```python
        self.pending_delete = None   # rel awaiting x confirmation
```

After the `discard` method, add:

```python
    def delete_file(self, node):
        """Remove the file from disk. Returns an error string or None."""
        try:
            os.remove(node.path)
        except OSError as e:
            return str(e)
        self._after_git_change()
        self.sel = min(self.sel, max(0, len(self.visible) - 1))
        return None
```

- [ ] **Step 4: Add the key branch in main.py**

Directly after the `elif ch == ord("X"):` branch, add:

```python
        elif ch == ord("x"):
            if node and node.is_dir:
                app.message = "can't delete directories"
            elif node:
                if app.pending_delete == node.rel:
                    err = app.delete_file(node)
                    app.pending_delete = None
                    app.message = ("deleted " + node.rel if err is None
                                   else "delete failed: " + err)
                else:
                    app.pending_delete = node.rel
                    app.message = "delete %s? press x again" % node.rel
```

And extend the pending-state clearing near the bottom of the loop — after `if ch != ord("X"): app.pending_discard = None`, add:

```python
        if ch != ord("x"):
            app.pending_delete = None
```

- [ ] **Step 5: Update help text and README**

`main.py` docstring — after the `X` line (`    X               discard changes to the selected file (press twice)`), add:

```
    x               delete the selected file from disk (press twice)
```

`README.md` — after the `X` row (line 99), add:

```
| `x` | delete selected file from disk (press twice to confirm) |
```

- [ ] **Step 6: Run the full test to verify it passes**

Run: `python3 tests/test_tui.py`
Expected: `all tests passed`, including the five new delete checks.

- [ ] **Step 7: Commit**

```bash
git add sideview_tui/app.py sideview_tui/main.py README.md tests/test_tui.py
git commit -m "feat: x deletes the selected file (press twice to confirm)"
```

---

### Task 3: Conventional Commits prefixes for generated messages

**Files:**
- Modify: `sideview_tui/app.py` (`App.commit_suggestion`)
- Test: `tests/test_tui.py` (update one existing assertion; add a headless prefix check)

**Interfaces:**
- Consumes: existing `commit_suggestion()` structure — `groups` dict maps verb (`add`/`update`/`remove`/`rename`) to file lists.
- Produces: `commit_suggestion()` return values always start with a Conventional Commits prefix; Task 4's test asserts the subject `chore: update app.py`.

- [ ] **Step 1: Update the existing assertion + add the failing test**

In `tests/test_tui.py`, the auto-commit check:

```python
    check("auto commit message generated", log == "update app.py")
```

becomes:

```python
    check("auto commit message generated", log == "chore: update app.py")
```

Then insert after the push check (`check("push reports failure without remote", ok)`):

```python
    # --- conventional prefix: added file -> feat: ---
    open(f"{repo}/newfile.py", "w").write("x = 1\n")
    subprocess.run(["git", "-C", repo, "add", "newfile.py"],
                   capture_output=True)
    r = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, sys.argv[1]);"
         "from sideview_tui.app import App;"
         "print(App(sys.argv[2]).commit_suggestion())",
         ROOT, repo],
        capture_output=True, text=True)
    check("feat prefix for added file",
          r.stdout.strip().startswith("feat: add newfile.py"))
    subprocess.run(["git", "-C", repo, "-c", "user.email=t@t",
                    "-c", "user.name=t", "commit", "-m", "chore: tmp"],
                   capture_output=True)   # leave nothing staged behind
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/test_tui.py`
Expected: `FAIL auto commit message generated` and `FAIL feat prefix for added file` (messages currently have no prefix). Prior checks still PASS.

- [ ] **Step 3: Implement in commit_suggestion**

In `sideview_tui/app.py`, change the summary line:

```python
        summary = "; ".join(
            v + " " + ", ".join(fs[:3]) + ("…" if len(fs) > 3 else "")
            for v, fs in groups.items()) or "update"
```

to:

```python
        summary = "; ".join(
            v + " " + ", ".join(fs[:3]) + ("…" if len(fs) > 3 else "")
            for v, fs in groups.items()) or "update"
        summary = ("feat: " if "add" in groups else "chore: ") + summary
```

And update the AI prompt in the same method:

```python
                    ["claude", "-p", "--model", "haiku",
                     "Write a single-line git commit message (max 70 chars,"
                     " imperative mood) for this diff. Reply with only the"
                     " message, nothing else."],
```

becomes:

```python
                    ["claude", "-p", "--model", "haiku",
                     "Write a single-line git commit message in Conventional"
                     " Commits format '<type>: <description>' with type one"
                     " of feat|fix|chore|docs|refactor|test, max 70 chars,"
                     " imperative mood, for this diff. Reply with only the"
                     " message, nothing else."],
```

- [ ] **Step 4: Run the full test to verify it passes**

Run: `python3 tests/test_tui.py`
Expected: `all tests passed`, including `PASS auto commit message generated` and `PASS feat prefix for added file`.

- [ ] **Step 5: Commit**

```bash
git add sideview_tui/app.py tests/test_tui.py
git commit -m "feat: conventional-commit prefixes for generated commit messages"
```

---

### Task 4: `C` commits without suspending the TUI

**Files:**
- Modify: `sideview_tui/app.py` (`App.run_commit`)
- Modify: `sideview_tui/main.py` (`c`/`C` key branch)
- Modify: `README.md` (line 23–24, mention C stays in the TUI)
- Test: `tests/test_tui.py` (invert the suspend assertion)

**Interfaces:**
- Consumes: `commit_suggestion()` from Task 3, `draw(stdscr, app)` (already imported in main.py), `App._after_git_change()`.
- Produces: `run_commit(stdscr, auto=True)` no longer suspends and sets `app.message` itself; the `auto=False` editor path is unchanged.

- [ ] **Step 1: Write the failing test**

In `tests/test_tui.py`, the check after the `C` auto-commit:

```python
    # mouse tracking must be OFF while suspended for the commit
    check("mouse disabled during commit", b"\x1b[?1002l" in buf)
```

becomes:

```python
    # C must stay in the TUI: no suspend, so mouse tracking never turns off
    check("no TUI suspend on C", b"\x1b[?1002l" not in buf)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/test_tui.py`
Expected: `FAIL no TUI suspend on C` (the current implementation suspends, emitting `\x1b[?1002l`). Prior checks still PASS.

- [ ] **Step 3: Rework run_commit in app.py**

Replace the whole method:

```python
    def run_commit(self, stdscr, auto=False):
        """git commit with a generated message: `auto` commits directly,
        otherwise $EDITOR opens prefilled for review. Returns exit code."""
        suspend_tui()
        print("sideview: generating commit message…", flush=True)
        msg = self.commit_suggestion()
        cmd = ["git", "commit", "-m", msg] + ([] if auto else ["-e"])
        rc = subprocess.call(cmd, cwd=self.root)
        resume_tui(stdscr)
        self._after_git_change()
        return rc
```

with:

```python
    def run_commit(self, stdscr, auto=False):
        """git commit with a generated message: `auto` commits in-TUI with
        output captured (and sets self.message), otherwise $EDITOR opens
        prefilled for review. Returns exit code."""
        if auto:
            msg = self.commit_suggestion()
            r = subprocess.run(["git", "commit", "-m", msg], cwd=self.root,
                               capture_output=True, text=True)
            self._after_git_change()
            if r.returncode == 0:
                self.message = ("committed ✔ " + msg)[:100]
            else:
                err = ((r.stderr or r.stdout or "").strip().splitlines()
                       or ["unknown error"])[0]
                self.message = "commit failed: " + err
            return r.returncode
        suspend_tui()
        print("sideview: generating commit message…", flush=True)
        msg = self.commit_suggestion()
        rc = subprocess.call(["git", "commit", "-m", msg, "-e"],
                             cwd=self.root)
        resume_tui(stdscr)
        self._after_git_change()
        return rc
```

- [ ] **Step 4: Update the key branch in main.py**

Replace:

```python
        elif ch in (ord("c"), ord("C")):
            if app.git.counts()[0]:
                rc = app.run_commit(stdscr, auto=(ch == ord("C")))
                app.message = "committed" if rc == 0 else "commit aborted"
            else:
                app.message = "nothing staged (s to stage)"
```

with:

```python
        elif ch in (ord("c"), ord("C")):
            if app.git.counts()[0]:
                if ch == ord("C"):
                    app.message = "generating commit message…"
                    draw(stdscr, app)   # show progress before blocking
                    app.run_commit(stdscr, auto=True)  # sets app.message
                else:
                    rc = app.run_commit(stdscr)
                    app.message = ("committed" if rc == 0
                                   else "commit aborted")
            else:
                app.message = "nothing staged (s to stage)"
```

- [ ] **Step 5: Update README**

Lines 22–25: `` `C` commits instantly with the generated message `` → `` `C` commits instantly with the generated message without leaving the TUI ``

- [ ] **Step 6: Run the full test to verify it passes**

Run: `python3 tests/test_tui.py`
Expected: `all tests passed`, including `PASS no TUI suspend on C` and the still-passing `PASS auto-commit works` (status message `committed ✔ chore: update app.py` contains `committed`).

- [ ] **Step 7: Commit**

```bash
git add sideview_tui/app.py sideview_tui/main.py README.md tests/test_tui.py
git commit -m "feat: C commits in-TUI (no terminal flash), status in the bar"
```
