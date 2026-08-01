# Using sideview

sideview is built to sit in a narrow terminal pane next to your editor
and answer "what's going on in this project?" at a glance: the file
tree, git status, diffs, and quick actions — without leaving the pane.

```bash
sideview              # watch the current directory
sideview ~/code       # a folder full of repos works too
tmux split-window -h -l 50 'sideview ~/myproject'
```

## The screen

- **Top border** — the repo that owns the selected file (cyan), its
  branch (yellow), and a compact change indicator on the right: `+n`
  staged/untracked, `-n` modified. In a folder of repos this updates as
  the selection moves between them.
- **Left pane** — the file tree with type icons, git status colors and
  markers, and indent guides. A `•` on a collapsed directory means
  something inside it changed.
- **Right pane** — the preview: syntax-highlighted file contents, a
  rendered view for markdown, or a diff.
- **Bottom border** — key hints for the current mode; the line above it
  shows messages, prompts, and file info.

## Views

**File preview** — select any file. Code gets syntax highlighting and
line numbers. `Tab` (or `→`) moves focus into the preview so `j`/`k`
scroll it; `h`/`←` goes back to the tree.

**Markdown reading view** — `.md` files render like a page: headings,
bullets, code blocks, links (title shows `[reading]`). Press `m` to
flip to the raw text (`[raw]`) and back. Search (`/` in preview) and
drag-to-copy still operate on the raw lines.

**Diff view** — `d` shows the selected file's uncommitted diff instead
of its contents.

**Changes view** — `D` replaces the preview with one live, repo-wide
diff of everything uncommitted (untracked files included), updating as
files change on disk. The tree becomes the changed-file list; selecting
a file jumps to its section. `[` / `]` hop between hunks. Great for
watching an AI agent edit your repo — add **follow mode** (`F`) to
auto-select whatever changed last.

**Fuzzy find** (`/`) filters the tree as you type; **find in files**
(`f`) greps every file in every repo under the root and lists
`file:line` matches — `e` opens the file at that line.

## Git actions

All in-TUI, resolved to the repo that owns the selected file:

- `s` / `u` — stage / unstage the file
- `c` — commit: opens `$EDITOR` prefilled with a generated
  Conventional-Commits message (Claude CLI if installed, else Cursor
  CLI, else a file summary). `C` commits with the generated message
  immediately.
- `P` — push, captured in the status line (no terminal takeover)
- `X` — discard the file's changes (asks twice); `x` — delete the file
  (asks twice)

## Editors

`e` opens the selected file in `$EDITOR` at the selected line.

- Terminal editors (nvim, vim, …) take over the pane and return to
  sideview on exit.
- GUI editors — `cursor`, `code`, `zed`, `subl`, `windsurf` — open the
  file at the right line in the app **without leaving the TUI**, so the
  pane keeps its place. Commit-message editing (`c`) blocks with the
  editor's `--wait` flag so git waits for you to close the message.

Set it like any other program: `EDITOR=cursor sideview ~/code`.

## Mouse

Click to select, double-click to open a dir/file, wheel scrolls either
pane, drag the divider to resize, drag across preview lines to select
and copy them. Hold Option/Alt for the terminal's native selection.

Press `?` inside sideview for the always-current key reference.
