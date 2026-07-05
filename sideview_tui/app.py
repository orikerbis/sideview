"""Application state: file tree, fuzzy search, preview, actions."""
import curses
import json
import os
import shutil
import subprocess
import time

from . import syntax
from .gitstate import Git, run

NOISE_DIRS = {
    "node_modules", "__pycache__", ".venv", "venv", ".cache", ".idea",
    ".vscode", "dist", "build", ".terraform", ".mypy_cache", ".pytest_cache",
    "target", ".next", ".Trash", "Library",
}
PREVIEW_MAX_LINES = 800
EDITOR = os.environ.get("EDITOR") or ("nvim" if shutil.which("nvim") else "vim")
STATE_PATH = (os.environ.get("SIDEVIEW_STATE")
              or os.path.expanduser("~/.config/sideview/state.json"))
MAX_STATE_REPOS = 20


class Node:
    __slots__ = ("path", "rel", "name", "is_dir", "depth")

    def __init__(self, path, rel, name, is_dir, depth):
        self.path, self.rel, self.name = path, rel, name
        self.is_dir, self.depth = is_dir, depth


class App:
    def __init__(self, root):
        self.root = root
        self.git = Git(root)
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
        self.preview_cache = None
        self.last_git = time.time()
        self.message = ""
        self.follow = False          # F: auto-select the newest change
        self.pending_discard = None  # rel awaiting X confirmation
        self.psearch = ""            # search string inside the preview
        self.psearch_input = False
        self.load_state()

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
        if len(all_state) > MAX_STATE_REPOS:
            oldest = sorted(all_state,
                            key=lambda r: all_state[r].get("saved_at", 0))
            for r in oldest[:len(all_state) - MAX_STATE_REPOS]:
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
        if self.diff_mode and self.git.branch and code and code != "??":
            out = run(["git", "diff", "HEAD", "--", node.rel], self.root)
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
        raw = run(["git", "diff", "HEAD"], self.root) or ""
        rows, index = [], {}
        lang, new_ln = None, 0
        hunk_re = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@ ?(.*)")
        for line in raw.splitlines():
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
        run(["git", "add", "--", node.rel], self.root)
        self._after_git_change()

    def unstage(self, node):
        run(["git", "restore", "--staged", "--", node.rel], self.root)
        self._after_git_change()

    def discard(self, node):
        run(["git", "checkout", "--", node.rel], self.root)
        self._after_git_change()

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
        curses.def_prog_mode()
        curses.endwin()
        subprocess.call(cmd)
        curses.reset_prog_mode()
        stdscr.clear()
        stdscr.refresh()
        self.git.refresh()
        self.preview_cache = None
        self.repo_diff = None

    def run_commit(self, stdscr):
        """Interactive `git commit` (opens $EDITOR); returns exit code."""
        curses.def_prog_mode()
        curses.endwin()
        rc = subprocess.call(["git", "commit"], cwd=self.root)
        curses.reset_prog_mode()
        stdscr.clear()
        stdscr.refresh()
        self._after_git_change()
        return rc
