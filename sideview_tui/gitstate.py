"""Git repository state. Handles both a single repo at the tree root and a
non-git root that contains many repos (e.g. ~/code). Per-path status,
branch/ahead-behind, and git actions all resolve to the repo that owns the
path, so status markers and actions work the same either way."""
import os
import subprocess

MAX_REPOS = 80          # cap discovery so a huge tree can't stall a refresh
MAX_SCAN_DIRS = 4000    # bound the directory walk that looks for repos


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
        self.refresh()

    # ---------- discovery + status ----------
    def refresh(self):
        self.repos, self.files, self.dirty_dirs = [], {}, set()
        if _is_repo(self.root):
            self._add_repo(self.root, "")
        else:
            for repo_root in _discover_repos(self.root, self.show_hidden,
                                             self.noise_dirs):
                prefix = os.path.relpath(repo_root, self.root)
                self._add_repo(repo_root, prefix)

    def _add_repo(self, root, prefix):
        repo = Repo(root, prefix)
        b = run(["git", "symbolic-ref", "--short", "HEAD"], root)
        if b:
            repo.branch = b.strip()
        else:
            sha = run(["git", "rev-parse", "--short", "HEAD"], root)
            repo.branch = "@" + sha.strip() if sha else "?"
        ab = run(["git", "rev-list", "--left-right", "--count", "@{u}...HEAD"],
                 root)
        if ab and len(ab.split()) == 2:
            behind, ahead = ab.split()
            repo.ahead, repo.behind = int(ahead), int(behind)
        self.repos.append(repo)
        out = run(["git", "status", "--porcelain"], root) or ""
        for line in out.splitlines():
            if len(line) < 4:
                continue
            xy, path = line[:2], line[3:].strip().strip('"')
            if path.endswith("/"):
                path = path[:-1]
            rel = os.path.normpath(os.path.join(prefix, path)) if prefix \
                else path
            self.files[rel] = xy
            parent = os.path.dirname(rel)
            while parent:
                self.dirty_dirs.add(parent)
                parent = os.path.dirname(parent)

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
