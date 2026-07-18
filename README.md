# sideview

[![tests](https://github.com/orikerbis/sideview/actions/workflows/test.yml/badge.svg)](https://github.com/orikerbis/sideview/actions/workflows/test.yml)

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
- **Agent follow mode** (`F`): auto-jumps to whichever file changed most
  recently — leave it on while an AI agent works and the diff tracks it;
  freshly-changed files pulse orange in the tree for 30s
- **Git actions**: `s` stage, `u` unstage, `X` discard (double-press
  confirm); `c` commit with your editor prefilled by a **generated commit
  message** (Claude CLI if installed, heuristic otherwise), `C` commits
  instantly with the generated message; `e` on a focused diff/preview
  opens Neovim at that exact line
- **Per-repo persistence**: expanded folders, split size and hidden-files
  toggle are remembered between sessions (`~/.config/sideview/state.json`)
- **In-preview search**: `/` while the preview is focused, `n`/`N` to jump
  between matches (works on files and on the repo diff)
- **Changes view** (`D`): a delta-style pretty diff of the whole repo —
  file header bars with +/− stats, clean hunk markers, line numbers,
  colored change gutters, syntax-highlighted added lines; untracked
  files included. Updates live as files change on disk — watch an AI
  agent's edits land in real time. The changed-file list on the left
  jumps to each file's section; `[` / `]` jump hunks
- **Pane focus** (`Tab`): move focus to the preview so `j/k`, `gg/G`,
  `Ctrl-d/u` scroll the file instead of the tree
- **Fuzzy file finder** (`/`) — subsequence matching like an IDE quick-open
- **Edit in Neovim/vim**: `e` suspends the TUI and opens the file in
  `$EDITOR` (defaults to `nvim` when installed, else `vim`)
- **Dark 256-color theme** matching **tokyonight-night** (the LazyVim
  default) with graceful 8-color fallback
- **Mouse support** (dual X10/SGR protocol parsing — works on terminals
  old ncurses can't handle): click to select, double-click to open, wheel
  scrolls either pane, drag the separator to resize, drag over preview
  lines to select and auto-copy them; hold ⌥ Option for native selection
- **Live updates**: preview re-reads changed files (~1s); git status and
  the tree pick up new/deleted files every ~3s
- **VSCode-style file icons**: colored Nerd Font glyphs by default,
  emoji fallback for terminals without a Nerd Font

## Install

```bash
pipx install git+https://github.com/orikerbis/sideview   # as a package
# or, from a clone:
ln -sf "$PWD/sideview" ~/.local/bin/sideview

sideview --doctor         # check your setup (fonts, editor, git, claude)
```

Zero-config: on first run sideview installs the icon glyph font
automatically if none is found (Symbols Nerd Font; opt out with
`SIDEVIEW_NO_FONT_INSTALL=1`, or run `sideview --install-font` manually).
Icons auto-detect (Nerd Font glyphs when installed, emoji otherwise), the
editor auto-detects (`nvim`, then `vim`), and the theme falls back
gracefully on basic terminals.

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
| `Enter` | expand / collapse dir |
| `e` | edit file (even from search results) |
| `/` | fuzzy find file (`↑`/`↓` browse results while typing, `e` open, `Esc` cancel) |
| `D` | changes view: changed files + live diff preview (`Esc` exits) |
| `F` | follow mode: auto-jump to the newest change (great with AI agents) |
| `s` / `u` | git stage / unstage selected file |
| `c` / `C` | commit: editor prefilled with generated message / instant auto-commit |
| `P` | git push |
| `X` | discard changes to selected file (press twice to confirm) |
| `x` | delete selected file from disk (press twice to confirm) |
| `/` (preview focused) | search inside the file/diff; `n` / `N` next/prev match |
| `[` / `]` | previous / next diff hunk |
| `Tab` or `→` / `←` | focus tree ↔ preview (`→` on a file enters the preview; focused pane gets j/k, gg/G, Ctrl-d/u) |
| `d` | toggle git-diff view in preview |
| `p` | toggle preview pane |
| `<` `>` or `-` `+` | make the tree pane narrower / wider |
| `J` / `K` | scroll preview |
| `.` | show hidden files |
| `r` | refresh |
| `q` / `Ctrl-C` | quit |
| mouse | click/double-click, wheel, drag separator to resize, drag in preview to copy lines (⌥-drag = native selection) |
| `y` / `Y` | copy selected file's path / contents to clipboard |

## Configuration

| Env var | Values | Default |
|---|---|---|
| `SIDEVIEW_COMMIT_AI` | `on`, `off` | `on` (uses `claude` CLI when found) |
| `SIDEVIEW_ICONS` | `nerd`, `emoji`, `off` | `nerd` |
| `EDITOR` | any editor command | `nvim`, falling back to `vim` |

## Development

Code lives in the `sideview_tui/` package (`icons`, `textutil`, `gitstate`,
`app`, `theme`, `ui`, `main`); the root `sideview` script is a thin launcher.
Run the pty-based regression tests with:

```bash
python3 tests/test_tui.py
```
