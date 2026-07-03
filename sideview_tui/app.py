"""Application state: file tree, fuzzy search, preview, actions."""
import curses
import os
import shutil
import subprocess
import time

from .gitstate import Git, run

NOISE_DIRS = {
    "node_modules", "__pycache__", ".venv", "venv", ".cache", ".idea",
    ".vscode", "dist", "build", ".terraform", ".mypy_cache", ".pytest_cache",
    "target", ".next", ".Trash", "Library",
}
PREVIEW_MAX_LINES = 800
EDITOR = os.environ.get("EDITOR") or ("nvim" if shutil.which("nvim") else "vim")


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
        self.dragging = False  # mouse-dragging the pane separator
        self.mouse_on = True   # m toggles: off = terminal-native selection
        self.psel = None       # [start, end] line selection in the preview
        self.psel_active = False
        self.focus = "tree"    # Tab toggles: "tree" | "preview"
        self.changes = False   # D: changed-files view with repo-wide diff
        self.repo_diff = None  # cached (lines, {rel: header_line_index})
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

    def repo_diff_lines(self):
        """One diff for the whole repo (untracked files as +added), plus
        an index of each file's header line for jump-to-file."""
        if self.repo_diff is not None:
            return self.repo_diff[0]
        out = run(["git", "diff", "HEAD"], self.root) or ""
        lines = out.splitlines()
        for rel in sorted(self.git.files):
            if self.git.files[rel] != "??":
                continue
            lines.append("diff --git a/%s b/%s" % (rel, rel))
            lines.append("new file (untracked)")
            try:
                blob = open(os.path.join(self.root, rel), "rb").read(256 * 1024)
                if b"\0" in blob[:8192]:
                    lines.append("+(binary file)")
                else:
                    body = blob.decode("utf-8", errors="replace").splitlines()
                    lines.extend("+" + l for l in body[:400])
            except OSError:
                pass
            lines.append("")
        index = {}
        for i, l in enumerate(lines):
            if l.startswith("diff --git "):
                index[l.split(" b/", 1)[-1]] = i
        if not lines:
            lines = ["(no changes)"]
        self.repo_diff = (lines, index)
        return lines

    def scroll_to_selected_change(self):
        node = self.selected()
        self.repo_diff_lines()
        self.pscroll = self.repo_diff[1].get(node.rel, 0) if node else 0

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

    def edit(self, stdscr, node):
        if node is None or node.is_dir:
            return
        curses.def_prog_mode()
        curses.endwin()
        subprocess.call([EDITOR, node.path])
        curses.reset_prog_mode()
        stdscr.clear()
        stdscr.refresh()
        self.git.refresh()
        self.preview_cache = None
        self.repo_diff = None
