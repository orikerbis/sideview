"""Git repository state: branch, ahead/behind, per-path porcelain status."""
import os
import subprocess


def run(args, cwd):
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                           timeout=5, errors="replace")
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None


class Git:
    def __init__(self, root):
        self.root = root
        self.branch = None
        self.ahead = self.behind = 0
        self.files = {}       # relpath -> XY porcelain code
        self.dirty_dirs = set()
        self.refresh()

    def refresh(self):
        inside = run(["git", "rev-parse", "--is-inside-work-tree"], self.root)
        if not inside or inside.strip() != "true":
            self.branch = None
            return
        b = run(["git", "symbolic-ref", "--short", "HEAD"], self.root)
        if b:
            self.branch = b.strip()
        else:
            sha = run(["git", "rev-parse", "--short", "HEAD"], self.root)
            self.branch = "@" + sha.strip() if sha else "?"
        ab = run(["git", "rev-list", "--left-right", "--count", "@{u}...HEAD"],
                 self.root)
        if ab:
            behind, ahead = ab.split()
            self.ahead, self.behind = int(ahead), int(behind)
        self.files, self.dirty_dirs = {}, set()
        out = run(["git", "status", "--porcelain"], self.root) or ""
        for line in out.splitlines():
            if len(line) < 4:
                continue
            xy, path = line[:2], line[3:].strip().strip('"')
            if path.endswith("/"):
                path = path[:-1]
            self.files[path] = xy
            parent = os.path.dirname(path)
            while parent:
                self.dirty_dirs.add(parent)
                parent = os.path.dirname(parent)

    def code(self, relpath):
        return self.files.get(relpath)

    def counts(self):
        staged = sum(1 for xy in self.files.values() if xy[0] not in " ?")
        unstaged = sum(1 for xy in self.files.values()
                       if xy[1] not in " " and xy != "??")
        untracked = sum(1 for xy in self.files.values() if xy == "??")
        return staged, unstaged, untracked
