# sideview

A zero-dependency, vim-style file navigator + git dashboard TUI, built to
live in a side terminal pane next to your editor. Pure Python stdlib
(curses) — no pip installs.

## Features

- **File tree** with vim navigation, folder expand/collapse
- **Git-aware everywhere**: branch + ahead/behind + staged/modified/untracked
  counts in the header; per-file status colors and markers in the tree;
  changed-content dots on collapsed folders; auto-refresh every 3s
- **Preview pane** with line numbers and lightweight **syntax highlighting**
  (python, shell, js/ts, json/tfstate, yaml, terraform, dockerfile, …),
  or the file's **git diff** (`d`); resize the split with `<` / `>`
- **Changes view** (`D`): a delta-style pretty diff of the whole repo —
  file header bars with +/− stats, clean hunk markers, line numbers,
  colored change gutters, syntax-highlighted added lines; untracked
  files included. Updates live as files change on disk — watch an AI
  agent's edits land in real time. The changed-file list on the left
  jumps to each file's section; `[` / `]` jump hunks
- **Pane focus** (`Tab`): move focus to the preview so `j/k`, `gg/G`,
  `Ctrl-d/u` scroll the file instead of the tree
- **Fuzzy file finder** (`/`) — subsequence matching like an IDE quick-open
- **Edit in Neovim/vim**: `Enter` suspends the TUI and opens the file in
  `$EDITOR` (defaults to `nvim` when installed, else `vim`)
- **Dark 256-color theme** matching **tokyonight-night** (the LazyVim
  default) with graceful 8-color fallback
- **Mouse support**: drag the pane separator to resize, click to select,
  double-click to open, scroll wheel in both panes
- **Live updates**: preview re-reads changed files (~1s); git status and
  the tree pick up new/deleted files every ~3s
- **VSCode-style file icons**: colored Nerd Font glyphs by default,
  emoji fallback for terminals without a Nerd Font

## Install

```bash
ln -sf "$PWD/sideview" ~/.local/bin/sideview   # or copy it anywhere on PATH
```

Requires Python 3.8+. For the default icon style, use a
[Nerd Font](https://www.nerdfonts.com) in your terminal (e.g. MesloLGS NF,
the powerlevel10k font). Otherwise run with `SIDEVIEW_ICONS=emoji`.

## Usage

```bash
sideview              # watch current directory
sideview ~/myproject  # watch a specific directory
```

Put it in a side pane: `tmux split-window -h -l 50 'sideview ~/myproject'`,
or split your iTerm2/Terminal window and run it there.

## Keys

| Key | Action |
|---|---|
| `j` / `k`, arrows | move |
| `gg` / `G` | top / bottom |
| `Ctrl-d` / `Ctrl-u` | half page down / up |
| `l` / `h` | expand dir / collapse (or jump to parent) |
| `Enter` | open dir, or edit file in `$EDITOR` |
| `e` | edit file (even from search results) |
| `/` | fuzzy find file (`Enter` open, `Esc` cancel) |
| `D` | changes view: changed files + live diff preview (`Esc` exits) |
| `[` / `]` | previous / next diff hunk |
| `Tab` | focus tree ↔ preview (focused pane gets j/k, gg/G, Ctrl-d/u) |
| `d` | toggle git-diff view in preview |
| `p` | toggle preview pane |
| `<` / `>` | make the tree pane narrower / wider |
| `J` / `K` | scroll preview |
| `.` | show hidden files |
| `r` | refresh |
| `q` / `Ctrl-C` | quit |
| mouse | drag separator = resize, click = select, double-click = open, wheel = scroll |
| mouse drag in preview | select lines (highlighted), copied to clipboard on release |
| `m` | copy mode: frees the mouse for terminal-native text selection |
| `y` / `Y` | copy selected file's path / contents to clipboard |

## Configuration

| Env var | Values | Default |
|---|---|---|
| `SIDEVIEW_ICONS` | `nerd`, `emoji`, `off` | `nerd` |
| `EDITOR` | any editor command | `nvim`, falling back to `vim` |

## Development

Code lives in the `sideview_tui/` package (`icons`, `textutil`, `gitstate`,
`app`, `theme`, `ui`, `main`); the root `sideview` script is a thin launcher.
Run the pty-based regression tests with:

```bash
python3 tests/test_tui.py
```
