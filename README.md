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
- **Fuzzy file finder** (`/`) — subsequence matching like an IDE quick-open
- **Edit in Neovim/vim**: `Enter` suspends the TUI and opens the file in
  `$EDITOR` (defaults to `nvim` when installed, else `vim`)
- **Dark 256-color theme** matching **tokyonight-night** (the LazyVim
  default) with graceful 8-color fallback
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
| `d` | toggle git-diff view in preview |
| `p` | toggle preview pane |
| `<` / `>` | make the tree pane narrower / wider |
| `J` / `K` | scroll preview |
| `.` | show hidden files |
| `r` | refresh |
| `q` / `Ctrl-C` | quit |

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
