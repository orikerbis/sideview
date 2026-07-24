"""Application state: file tree, fuzzy search, preview, actions."""
import curses
import json
import os
import shutil
import subprocess
import sys
import threading
import time

from . import syntax
from .gitstate import Git, run

GREP_MAX_HITS = 1000
GREP_MAX_BYTES = 512 * 1024

NOISE_DIRS = {
    "node_modules", "__pycache__", ".venv", "venv", ".cache", ".idea",
    ".vscode", "dist", "build", ".terraform", ".mypy_cache", ".pytest_cache",
    "target", ".next", ".Trash", "Library",
}
PREVIEW_MAX_LINES = 800
EDITOR = os.environ.get("EDITOR") or ("nvim" if shutil.which("nvim") else "vim")
STATE_PATH = (os.environ.get("SIDEVIEW_STATE")
              or os.path.expanduser("~/.config/sideview/state.json"))
MOUSE_ON = b"\x1b[?1002h\x1b[?1006h"   # motion-while-pressed + SGR coords
MOUSE_OFF = b"\x1b[?1006l\x1b[?1002l"


def suspend_tui():
    """Leave curses for an external command: stop mouse reports first so
    they don't spray escape sequences into the shell/editor."""
    os.write(sys.stdout.fileno(), MOUSE_OFF)
    curses.def_prog_mode()
    curses.endwin()


def resume_tui(stdscr):
    curses.reset_prog_mode()
    curses.flushinp()   # drop any mouse/key junk queued while suspended
    stdscr.clear()
    stdscr.refresh()
    os.write(sys.stdout.fileno(), MOUSE_ON)
MAX_STATE_REPOS = 20


class Node:
    __slots__ = ("path", "rel", "name", "is_dir", "depth")

    def __init__(self, path, rel, name, is_dir, depth):
        self.path, self.rel, self.name = path, rel, name
        self.is_dir, self.depth = is_dir, depth


class App:
    def __init__(self, root):
        self.root = root
        self.expanded = set()
        self.show_hidden = False
        self.preview_on = True
        self.split = 0.42  # tree pane fraction of the width; < > adjust
        self.focus = "tree"    # Tab toggles: "tree" | "preview"
        self.changes = False   # D: changed-files view with repo-wide diff
        self.repo_diff = None  # cached (rows, {rel: header_row_index})
        self.diff_mode = False
        self.sel = 0
        self.scroll = 0
        self.pscroll = 0
        self.filter = ""
        self.filter_input = False
        self.pending_g = False
        self.visible = []
        self.guides = None     # per-node indent guides, filled lazily by draw
        self.preview_cache = None
        self.last_git = time.time()
        self.message = ""
        self.dragging = False        # mouse-dragging the pane separator
        self.psel = None             # [start, end] preview line selection
        self.psel_active = False
        self.last_click_t = 0.0      # double-click detection
        self.last_click_idx = -1
        self.follow = False          # F: auto-select the newest change
        self.pending_discard = None  # rel awaiting X confirmation
        self.pending_delete = None   # rel awaiting x confirmation
        self.psearch = ""            # search string inside the preview
        self.psearch_input = False
        self.help_on = False         # ?: full-screen key reference
        self.help_scroll = 0
        self.grep_q = ""             # f: find-in-files (content grep)
        self.grep_input = False
        self.grep_on = False         # showing grep results in place of the tree
        self.grep_busy = False
        self.grep_results = []       # list of (rel, lineno, snippet)
        self._grep_lock = threading.Lock()
        self._grep_pending = None
        self._grep_token = 0         # ignore results from superseded searches
        self.load_state()
        # built after load_state so repo discovery honors show_hidden
        self.git = Git(root, self.show_hidden, NOISE_DIRS)

    # ---------- persistence ----------
    def load_state(self):
        try:
            state = json.load(open(STATE_PATH)).get(self.root, {})
        except Exception:
            return
        self.expanded = set(state.get("expanded", []))
        self.split = state.get("split", self.split)
        self.show_hidden = state.get("show_hidden", self.show_hidden)

    def save_state(self):
        try:
            all_state = json.load(open(STATE_PATH))
        except Exception:
            all_state = {}
        all_state[self.root] = {
            "expanded": sorted(self.expanded),
            "split": self.split,
            "show_hidden": self.show_hidden,
            "saved_at": time.time(),
        }
        repos = [r for r in all_state if not r.startswith("_")]
        if len(repos) > MAX_STATE_REPOS:
            oldest = sorted(repos,
                            key=lambda r: all_state[r].get("saved_at", 0))
            for r in oldest[:len(repos) - MAX_STATE_REPOS]:
                del all_state[r]
        try:
            os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
            json.dump(all_state, open(STATE_PATH, "w"), indent=1)
        except OSError:
            pass

    def newest_change(self):
        """rel of the changed file with the most recent mtime."""
        best, best_t = None, -1.0
        for rel in self.git.files:
            try:
                t = os.stat(os.path.join(self.root, rel)).st_mtime
            except OSError:
                t = 0.0
            if t > best_t:
                best, best_t = rel, t
        return best

    # ---------- tree ----------
    def list_dir(self, path):
        try:
            entries = list(os.scandir(path))
        except OSError:
            return []
        keep = []
        for e in entries:
            if e.name == ".git":
                continue
            if not self.show_hidden and (e.name.startswith(".")
                                         or e.name in NOISE_DIRS):
                continue
            keep.append(e)
        keep.sort(key=lambda e: (not e.is_dir(follow_symlinks=False),
                                 e.name.lower()))
        return keep

    def build_visible(self):
        self.guides = None     # visible list changes -> guides recompute
        if self.grep_on:
            self.visible = [
                Node(os.path.join(self.root, rel), rel,
                     "%s:%d" % (rel, ln), False, 0)
                for (rel, ln, _snip) in self.grep_results
            ]
            self.sel = min(self.sel, max(0, len(self.visible) - 1))
            return
        if self.changes:
            self.visible = [
                Node(os.path.join(self.root, rel), rel, rel, False, 0)
                for rel in sorted(self.git.files)
            ]
            self.sel = min(self.sel, max(0, len(self.visible) - 1))
            return
        if self.filter:
            self.visible = self.search(self.filter)
            self.sel = min(self.sel, max(0, len(self.visible) - 1))
            return
        out = []

        def walk(path, depth):
            for e in self.list_dir(path):
                rel = os.path.relpath(e.path, self.root)
                is_dir = e.is_dir(follow_symlinks=False)
                out.append(Node(e.path, rel, e.name, is_dir, depth))
                if is_dir and rel in self.expanded:
                    walk(e.path, depth + 1)

        walk(self.root, 0)
        self.visible = out
        self.sel = min(self.sel, max(0, len(self.visible) - 1))

    def search(self, query):
        q = query.lower()
        hits, scanned = [], 0
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d != ".git"
                           and (self.show_hidden
                                or (not d.startswith(".")
                                    and d not in NOISE_DIRS))]
            for f in filenames:
                if not self.show_hidden and f.startswith("."):
                    continue
                scanned += 1
                if scanned > 30000:
                    break
                rel = os.path.relpath(os.path.join(dirpath, f), self.root)
                low = rel.lower()
                i = 0
                for ch in low:
                    if i < len(q) and ch == q[i]:
                        i += 1
                if i == len(q):
                    rank = 0 if q in low else 1
                    hits.append((rank, len(rel), rel))
            if scanned > 30000:
                break
        hits.sort()
        return [Node(os.path.join(self.root, rel), rel, rel, False, 0)
                for _, _, rel in hits[:500]]

    # ---------- find in files (content grep) ----------
    def start_grep(self, query):
        """Run a content search across every file on a background thread so a
        huge tree never freezes the UI; consume_grep() picks up the result."""
        self.grep_q = query
        self.grep_on = True
        self.grep_busy = True
        self.grep_results = []
        self.psearch = query          # so the preview highlights matches
        self._grep_token += 1
        token = self._grep_token
        with self._grep_lock:
            self._grep_pending = None
        threading.Thread(target=self._grep_worker, args=(query, token),
                         daemon=True).start()

    def _grep_worker(self, query, token):
        q = query.lower()
        results = []
        try:
            for dirpath, dirnames, filenames in os.walk(self.root):
                if token != self._grep_token:
                    return                # superseded by a newer search
                dirnames[:] = [
                    d for d in dirnames if d != ".git"
                    and (self.show_hidden
                         or (not d.startswith(".") and d not in NOISE_DIRS))]
                for f in filenames:
                    if not self.show_hidden and f.startswith("."):
                        continue
                    path = os.path.join(dirpath, f)
                    try:
                        with open(path, "rb") as fh:
                            blob = fh.read(GREP_MAX_BYTES)
                    except OSError:
                        continue
                    if b"\0" in blob[:8192]:            # skip binaries
                        continue
                    text = blob.decode("utf-8", "replace")
                    if q not in text.lower():           # quick whole-file reject
                        continue
                    rel = os.path.relpath(path, self.root)
                    for i, line in enumerate(text.splitlines(), 1):
                        if q in line.lower():
                            results.append((rel, i, line.strip()[:200]))
                            if len(results) >= GREP_MAX_HITS:
                                raise StopIteration
        except StopIteration:
            pass
        with self._grep_lock:
            if token == self._grep_token:
                self._grep_pending = results
                self.grep_busy = False

    def consume_grep(self):
        """Apply finished grep results. True when results were applied."""
        with self._grep_lock:
            pending = self._grep_pending
            self._grep_pending = None
        if pending is None:
            return False
        self.grep_results = pending
        self.build_visible()
        self.scroll_to_grep()
        return True

    def scroll_to_grep(self):
        """Scroll the preview to the matched line of the selected result."""
        if not (self.grep_on and self.grep_results):
            return
        idx = min(self.sel, len(self.grep_results) - 1)
        _rel, ln, _snip = self.grep_results[idx]
        self.pscroll = max(0, ln - 3)     # a couple of lines of context above

    def exit_grep(self):
        self.grep_on = self.grep_input = False
        self.grep_q = self.psearch = ""
        self.grep_results = []
        self._grep_token += 1             # abandon any in-flight worker
        self.grep_busy = False

    # ---------- preview ----------
    def preview_lines(self, node):
        if node is None or node.is_dir:
            return ["(directory)"] if node else []
        try:
            mtime = os.stat(node.path).st_mtime
        except OSError:
            mtime = 0  # deleted file: diff view can still show its removal
            if not (self.diff_mode and self.git.code(node.rel)):
                return ["(unreadable)"]
        key = (node.path, mtime, self.diff_mode)
        if self.preview_cache and self.preview_cache[0] == key:
            return self.preview_cache[1]
        code = self.git.code(node.rel)
        t = self.git.target(node.rel)
        if self.diff_mode and t and code and code != "??":
            out = run(["git", "diff", "HEAD", "--", t[1]], t[0])
            lines = (out or "").splitlines()[:PREVIEW_MAX_LINES] or ["(no diff)"]
        else:
            try:
                with open(node.path, "rb") as f:
                    blob = f.read(256 * 1024)
                if b"\0" in blob[:8192]:
                    lines = ["(binary file, %d bytes)"
                             % os.path.getsize(node.path)]
                else:
                    lines = blob.decode("utf-8", errors="replace") \
                                .splitlines()[:PREVIEW_MAX_LINES]
            except OSError as e:
                lines = ["(%s)" % e]
        self.preview_cache = (key, lines)
        return lines

    def repo_diff_rows(self):
        """Pretty repo-wide diff as rows: (kind, lineno, text, lang).
        kinds: file, hunk, add, del, ctx, meta, blank."""
        if self.repo_diff is not None:
            return self.repo_diff[0]
        import re
        rows, index = [], {}
        lang, new_ln = None, 0
        hunk_re = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@ ?(.*)")
        diff_lines = []
        for repo in self.git.repos:
            raw = run(["git", "diff", "HEAD"], repo.root) or ""
            for line in raw.splitlines():
                # rewrite the repo-relative b/ path to a root-relative one so
                # file headers, scrolling and open-at-line stay keyed by rel
                if line.startswith("diff --git ") and repo.prefix:
                    line = re.sub(r" [ab]/",
                                  lambda m: m.group(0)[:3] + repo.prefix + "/",
                                  line)
                diff_lines.append(line)
        for line in diff_lines:
            if line.startswith("diff --git "):
                rel = line.split(" b/", 1)[-1]
                if rows:
                    rows.append(("blank", "", "", None))
                index[rel] = len(rows)
                lang = syntax.detect(os.path.basename(rel))
                rows.append(("file", "", rel, lang))
            elif line.startswith("Binary files"):
                rows.append(("meta", "", "(binary file changed)", None))
            elif line.startswith(("index ", "--- ", "+++ ", "new file",
                                  "deleted file", "old mode", "new mode",
                                  "similarity", "rename ")):
                pass  # plumbing noise
            elif line.startswith("@@"):
                mm = hunk_re.match(line)
                if mm:
                    new_ln = int(mm.group(1))
                    ctx = (" " + mm.group(2)) if mm.group(2) else ""
                    rows.append(("hunk", "", "@ line %d%s" % (new_ln, ctx),
                                 None))
                else:
                    rows.append(("hunk", "", line, None))
            elif line.startswith("+"):
                rows.append(("add", str(new_ln), line[1:], lang))
                new_ln += 1
            elif line.startswith("-"):
                rows.append(("del", "", line[1:], lang))
            else:
                rows.append(("ctx", str(new_ln), line[1:], lang))
                new_ln += 1
        for rel in sorted(self.git.files):
            if self.git.files[rel] != "??":
                continue
            if rows:
                rows.append(("blank", "", "", None))
            index[rel] = len(rows)
            lang = syntax.detect(os.path.basename(rel))
            rows.append(("file", "", rel, lang))
            rows.append(("hunk", "", "@ new file", None))
            try:
                blob = open(os.path.join(self.root, rel), "rb").read(256 * 1024)
                if b"\0" in blob[:8192]:
                    rows.append(("meta", "", "(binary file)", None))
                else:
                    body = blob.decode("utf-8", errors="replace").splitlines()
                    for n, l in enumerate(body[:400], 1):
                        rows.append(("add", str(n), l, lang))
            except OSError:
                pass
        # per-file +adds/-dels stats onto the file header rows
        stats, cur = {}, None
        for kind, _, text, _l in rows:
            if kind == "file":
                cur = text
                stats[cur] = [0, 0]
            elif cur and kind == "add":
                stats[cur][0] += 1
            elif cur and kind == "del":
                stats[cur][1] += 1
        rows = [(k, n, t + "  +%d −%d" % tuple(stats[t]), l)
                if k == "file" else (k, n, t, l)
                for k, n, t, l in rows]
        if not rows:
            rows = [("meta", "", "working tree clean — no changes", None)]
        self.repo_diff = (rows, index)
        return rows

    def scroll_to_selected_change(self):
        node = self.selected()
        self.repo_diff_rows()
        self.pscroll = self.repo_diff[1].get(node.rel, 0) if node else 0

    def changes_line_at(self, idx):
        """(rel, new-file line) for the pretty-diff row at idx."""
        rows = self.repo_diff_rows()
        if not rows:
            return None, None
        idx = min(idx, len(rows) - 1)
        rel = None
        for kind, _num, text, _lang in rows[:idx + 1]:
            if kind == "file":
                rel = text.rsplit("  ", 1)[0]
        line = None
        for kind, num, _text, _lang in rows[idx:]:
            if kind == "file":
                break
            if num:
                line = int(num)
                break
        return rel, line

    # ---------- git actions ----------
    def _after_git_change(self):
        self.git.refresh()
        self.preview_cache = None
        self.repo_diff = None
        self.build_visible()

    def stage(self, node):
        t = self.git.target(node.rel)
        if t:
            run(["git", "add", "--", t[1]], t[0])
            self._after_git_change()

    def unstage(self, node):
        t = self.git.target(node.rel)
        if t:
            run(["git", "restore", "--staged", "--", t[1]], t[0])
            self._after_git_change()

    def discard(self, node):
        t = self.git.target(node.rel)
        if t:
            run(["git", "checkout", "--", t[1]], t[0])
            self._after_git_change()

    def delete_file(self, node):
        """Remove the file from disk. Returns an error string or None."""
        try:
            os.remove(node.path)
        except OSError as e:
            return str(e)
        self._after_git_change()
        self.sel = min(self.sel, max(0, len(self.visible) - 1))
        return None

    def active_repo(self):
        """Repo that commit/push act on: the one owning the selected file
        (root repo in single-repo mode), or None if the selection is not in
        any repo."""
        node = self.selected()
        return self.git.repo_for(node.rel) if node else None

    # ---------- actions ----------
    def selected(self):
        return self.visible[self.sel] if self.visible else None

    def toggle_dir(self, node):
        if node.rel in self.expanded:
            self.expanded.discard(node.rel)
        else:
            self.expanded.add(node.rel)

    def collapse_or_parent(self):
        node = self.selected()
        if not node:
            return
        if node.is_dir and node.rel in self.expanded:
            self.expanded.discard(node.rel)
            return
        parent = os.path.dirname(node.rel)
        if parent:
            for i, n in enumerate(self.visible):
                if n.rel == parent:
                    self.sel = i
                    return

    def edit(self, stdscr, node, line=None):
        if node is None or node.is_dir:
            return
        cmd = [EDITOR] + (["+%d" % line] if line else []) + [node.path]
        suspend_tui()
        subprocess.call(cmd)
        resume_tui(stdscr)
        self.git.refresh()
        self.preview_cache = None
        self.repo_diff = None

    def commit_suggestion(self, cwd=None):
        """Commit message for the staged diff: Claude CLI when available,
        otherwise a heuristic file summary. SIDEVIEW_COMMIT_AI=off skips AI."""
        cwd = cwd or self.root
        ns = run(["git", "diff", "--staged", "--name-status"], cwd) or ""
        verbs = {"A": "add", "M": "update", "D": "remove", "R": "rename"}
        groups = {}
        for line in ns.splitlines():
            parts = line.split("\t")
            if not parts[0]:
                continue
            verb = verbs.get(parts[0][0], "update")
            groups.setdefault(verb, []).append(os.path.basename(parts[-1]))
        summary = "; ".join(
            v + " " + ", ".join(fs[:3]) + ("…" if len(fs) > 3 else "")
            for v, fs in groups.items()) or "update"
        summary = ("feat: " if "add" in groups else "chore: ") + summary
        if (os.environ.get("SIDEVIEW_COMMIT_AI", "on") != "off"
                and shutil.which("claude")):
            diff = run(["git", "diff", "--staged"], cwd) or ""
            try:
                r = subprocess.run(
                    ["claude", "-p", "--model", "haiku",
                     "Write a single-line git commit message in Conventional"
                     " Commits format '<type>: <description>' with type one"
                     " of feat|fix|chore|docs|refactor|test, max 70 chars,"
                     " imperative mood, for this diff. Reply with only the"
                     " message, nothing else."],
                    input=diff[:60000], capture_output=True, text=True,
                    timeout=45)
                out = (r.stdout or "").strip()
                if r.returncode == 0 and out:
                    return out.splitlines()[0].strip()[:120]
            except Exception:
                pass
        return summary

    def run_push(self, cwd=None):
        """git push captured in-TUI (no curses suspend): sets self.message
        with the result. GIT_TERMINAL_PROMPT=0 + a timeout means a missing
        credential fails fast with a message instead of hanging invisibly.
        Returns exit code (or None on timeout)."""
        cwd = cwd or self.root
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
        try:
            r = subprocess.run(["git", "push"], cwd=cwd, capture_output=True,
                               text=True, timeout=120, env=env)
        except subprocess.TimeoutExpired:
            self.message = "push timed out"
            return None
        except Exception as e:
            self.message = "push failed: " + str(e)[:80]
            return None
        self._after_git_change()
        out = (r.stderr or r.stdout or "").strip().splitlines()
        tail = out[-1].strip() if out else ""
        if r.returncode == 0:
            self.message = ("pushed ✔ " + tail)[:100] if tail else "pushed ✔"
        else:
            self.message = ("push failed: " + tail)[:100] if tail \
                else "push failed"
        return r.returncode

    def run_commit(self, stdscr, auto=False, cwd=None):
        """git commit with a generated message: `auto` commits in-TUI with
        output captured (and sets self.message), otherwise $EDITOR opens
        prefilled for review. Message generation always happens in-TUI so
        the terminal is only taken over for the editor itself.
        Returns exit code."""
        cwd = cwd or self.root
        msg = self.commit_suggestion(cwd)
        if auto:
            r = subprocess.run(["git", "commit", "-m", msg], cwd=cwd,
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
        rc = subprocess.call(["git", "commit", "-m", msg, "-e"], cwd=cwd)
        resume_tui(stdscr)
        self._after_git_change()
        return rc
