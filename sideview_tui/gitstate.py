"""Git repository state. Handles both a single repo at the tree root and a
non-git root that contains many repos (e.g. ~/code). Per-path status,
branch/ahead-behind, and git actions all resolve to the repo that owns the
path, so status markers and actions work the same either way.

Status for all repos is fetched with one `git status --porcelain --branch` per
repo, run in parallel, and the periodic refresh happens on a background thread
so a directory full of repos never stalls the UI."""
import os
import re
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor

MAX_REPOS = 80          # cap discovery so a huge tree can't stall a refresh
MAX_SCAN_DIRS = 4000    # bound the directory walk that looks for repos
_AHEAD = re.compile(r"ahead (\d+)")
_BEHIND = re.compile(r"behind (\d+)")


def run(args, cwd):
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                           timeout=5, errors="replace")
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None


def _is_repo(path):
    inside = run(["git", "rev-parse", "--is-inside-work-tree"], path)
    return bool(inside) and inside.strip() == "true"


def _discover_repos(root, show_hidden, noise_dirs):
    """Yield abspaths of git repos under root. A dir containing .git is a
    repo; we don't descend into it (its subdirs belong to that repo)."""
    found, scanned = [], 0
    stack = [root]
    while stack and len(found) < MAX_REPOS and scanned < MAX_SCAN_DIRS:
        cur = stack.pop()
        scanned += 1
        try:
            entries = list(os.scandir(cur))
        except OSError:
            continue
        if any(e.name == ".git" for e in entries):
            found.append(cur)
            continue                       # a repo owns everything below it
        for e in entries:
            if not e.is_dir(follow_symlinks=False):
                continue
            if e.name == ".git":
                continue
            if not show_hidden and e.name.startswith("."):
                continue
            if e.name in noise_dirs:
                continue
            stack.append(e.path)
    return found


class Repo:
    __slots__ = ("root", "prefix", "branch", "ahead", "behind")

    def __init__(self, root, prefix):
        self.root = root        # abspath of the repo
        self.prefix = prefix    # root-relative dir, "" when repo == tree root
        self.branch = None
        self.ahead = self.behind = 0

    def name(self):
        return os.path.basename(self.prefix or self.root)


class Git:
    def __init__(self, root, show_hidden=False, noise_dirs=frozenset()):
        self.root = root
        self.show_hidden = show_hidden
        self.noise_dirs = noise_dirs
        self.repos = []           # list[Repo]
        self.files = {}           # root-relative path -> XY porcelain code
        self.dirty_dirs = set()
        self._roots = None        # cached discovery: list[(abspath, prefix)]
        self._lock = threading.Lock()
        self._busy = False        # a background refresh is in flight
        self._pending = None      # (repos, files, dirty) waiting to be swapped
        self.refresh()

    # ---------- discovery + status ----------
    def _discover(self):
        """(abspath, root-relative prefix) for every repo we act on."""
        if _is_repo(self.root):
            return [(self.root, "")]
        return [(r, os.path.relpath(r, self.root))
                for r in _discover_repos(self.root, self.show_hidden,
                                         self.noise_dirs)]

    def _status_repo(self, root, prefix):
        """One repo's (Repo, {rel: xy}, {dirty dirs}) from a single git call."""
        repo = Repo(root, prefix)
        files, dirty = {}, set()
        out = run(["git", "status", "--porcelain", "--branch"], root)
        if out is None:
            repo.branch = "?"
            return repo, files, dirty
        lines = out.splitlines()
        if lines and lines[0].startswith("## "):
            self._parse_branch(repo, lines[0][3:])
            lines = lines[1:]
        for line in lines:
            if len(line) < 4:
                continue
            xy, path = line[:2], line[3:].strip().strip('"')
            if " -> " in path:                      # rename: key on the new name
                path = path.split(" -> ", 1)[1].strip().strip('"')
            if path.endswith("/"):
                path = path[:-1]
            rel = os.path.normpath(os.path.join(prefix, path)) if prefix \
                else path
            files[rel] = xy
            parent = os.path.dirname(rel)
            while parent:
                dirty.add(parent)
                parent = os.path.dirname(parent)
        return repo, files, dirty

    def _parse_branch(self, repo, body):
        """Parse the porcelain `## ` header, e.g.
        'main...origin/main [ahead 1, behind 2]'."""
        if "no branch" in body:                     # detached HEAD
            sha = run(["git", "rev-parse", "--short", "HEAD"], repo.root)
            repo.branch = "@" + sha.strip() if sha else "?"
            return
        if body.startswith("No commits yet on "):
            repo.branch = body[len("No commits yet on "):].strip()
            return
        ab = ""
        if body.endswith("]") and " [" in body:
            body, ab = body[:-1].rsplit(" [", 1)
        repo.branch = body.split("...", 1)[0].strip()
        m = _AHEAD.search(ab)
        if m:
            repo.ahead = int(m.group(1))
        m = _BEHIND.search(ab)
        if m:
            repo.behind = int(m.group(1))

    def _compute(self, roots):
        """Status for every repo, fetched in parallel (git waits release the
        GIL, so threads overlap the subprocess time)."""
        if len(roots) > 1:
            with ThreadPoolExecutor(max_workers=min(16, len(roots))) as ex:
                parts = list(ex.map(
                    lambda rp: self._status_repo(rp[0], rp[1]), roots))
        else:
            parts = [self._status_repo(r, p) for r, p in roots]
        repos, files, dirty = [], {}, set()
        for repo, f, d in parts:
            repos.append(repo)
            files.update(f)
            dirty |= d
        return repos, files, dirty

    def refresh(self, rediscover=True):
        """Synchronous refresh (startup, manual r, after an action)."""
        if rediscover or self._roots is None:
            self._roots = self._discover()
        self.repos, self.files, self.dirty_dirs = self._compute(self._roots)

    def start_refresh(self, rediscover=False):
        """Kick a background refresh; consume_update() applies the result.
        No-op while one is already running."""
        with self._lock:
            if self._busy:
                return
            self._busy = True

        def work():
            try:
                roots = (self._discover()
                         if (rediscover or self._roots is None) else self._roots)
                state = self._compute(roots)
                with self._lock:
                    self._roots = roots
                    self._pending = state
            finally:
                with self._lock:
                    self._busy = False

        threading.Thread(target=work, daemon=True).start()

    def consume_update(self):
        """Apply a finished background refresh. True when state changed."""
        with self._lock:
            state = self._pending
            self._pending = None
        if state is None:
            return False
        self.repos, self.files, self.dirty_dirs = state
        return True

    # ---------- path -> repo resolution ----------
    def repo_for(self, rel):
        """Repo owning a root-relative path (longest-prefix match), or None."""
        best = None
        for repo in self.repos:
            if repo.prefix == "":
                if best is None:
                    best = repo          # root repo owns everything
            elif rel == repo.prefix or rel.startswith(repo.prefix + os.sep):
                if best is None or len(repo.prefix) > len(best.prefix):
                    best = repo
        return best

    def target(self, rel):
        """(repo_root_abspath, path-relative-to-that-repo) or None."""
        repo = self.repo_for(rel)
        if repo is None:
            return None
        if repo.prefix == "":
            return repo.root, rel
        return repo.root, os.path.relpath(rel, repo.prefix)

    # ---------- single-repo compat + summaries ----------
    @property
    def branch(self):
        """Root repo's branch (single-repo mode), else None."""
        if len(self.repos) == 1 and self.repos[0].prefix == "":
            return self.repos[0].branch
        return None

    def code(self, relpath):
        return self.files.get(relpath)

    def counts(self, prefix=None):
        def match(rel):
            return (prefix is None or prefix == ""
                    or rel == prefix or rel.startswith(prefix + os.sep))
        xys = [xy for rel, xy in self.files.items() if match(rel)]
        staged = sum(1 for xy in xys if xy[0] not in " ?")
        unstaged = sum(1 for xy in xys if xy[1] not in " " and xy != "??")
        untracked = sum(1 for xy in xys if xy == "??")
        return staged, unstaged, untracked
