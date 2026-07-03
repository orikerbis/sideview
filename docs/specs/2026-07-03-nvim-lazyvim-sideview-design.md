# Neovim (LazyVim) setup + sideview integration — Design

Date: 2026-07-03
Status: Approved by user

## Goal

Give the user a full vim-style editing environment: LazyVim as the Neovim
config, sideview (the custom side-pane TUI at `~/.local/bin/sideview`)
opening files in Neovim, and VSCode-style colored file icons in sideview.

## Context

- Neovim 0.12.3 installed via Homebrew; no existing `~/.config/nvim`.
- MesloLGS NF (Nerd Font 2.3.3) installed and almost certainly the terminal
  font (powerlevel10k user), so Nerd Font glyphs render natively.
- ripgrep installed (needed by telescope/fzf live grep).
- `/usr/bin/cc` present (treesitter parser compilation works).
- User works with Python and a DevOps stack (Docker, Terraform, YAML/K8s,
  Bash), plus some web (JS/TS).

## Components

### 1. Neovim: LazyVim starter

- Clone the official LazyVim starter template into `~/.config/nvim`,
  remove its `.git` so the config belongs to the user.
- Enable LazyVim extras for the chosen languages by listing them in
  `lua/config/lazy.lua` (imports) or `lazyvim.json`:
  - `lazyvim.plugins.extras.lang.python` (pyright + ruff)
  - `lazyvim.plugins.extras.lang.yaml` (K8s schemas)
  - `lazyvim.plugins.extras.lang.docker`
  - `lazyvim.plugins.extras.lang.terraform`
  - `lazyvim.plugins.extras.lang.typescript`; HTML/CSS get treesitter
    highlighting by default, LSP servers addable later via mason
  - Bash: treesitter parser + bashls come with defaults/mason.
- Stock LazyVim already provides: tokyonight-night dark theme, lualine,
  neo-tree, telescope/fzf, gitsigns, which-key, nvim-web-devicons,
  treesitter, LSP + completion (blink.cmp), mason.
- First sync runs headless: `nvim --headless "+Lazy! sync" +qa`.
  LSP servers auto-install via mason on first real use.

### 2. sideview: editor default

- `EDITOR` env var still wins; otherwise default to `nvim` when on PATH,
  falling back to `vim`. (Already implemented.)

### 3. sideview: VSCode-style icons

- Nerd Font glyph set (devicons / seti / font-awesome codepoint ranges —
  all stable in Nerd Fonts 2.x) replaces the emoji default.
- Per-filetype colors in the spirit of the vscode-icons / Material Icon
  Theme extensions (yellow JS, blue TS/Python/Docker, orange HTML, cyan Go,
  orange Rust, green shell, …), defined in `ICON_COLORS`.
- `init_theme()` registers two curses color pairs per filetype class:
  one on the normal dark background, one on the selection-bar background.
- Tree rows and the preview title draw the icon with its own color pair;
  the filename keeps the git-status color.
- `SIDEVIEW_ICONS=nerd` is the new default; `emoji` and `off` remain as
  overrides for terminals without a Nerd Font.

## Error handling

- Nothing existing is overwritten (`~/.config/nvim` verified absent).
- sideview falls back to basic 8 colors on non-256-color terminals and to
  uncolored icons if pairs are unavailable.
- If the headless Lazy sync fails, report the error; LazyVim self-heals on
  first interactive launch (`:Lazy sync`).

## Testing

- pty-based regression test of sideview: nerd glyphs present, icon color
  pairs emitted, navigation/find/diff still work, Ctrl-C exits cleanly
  with no traceback (fix pending re-verification after an earlier test
  harness deadlock).
- `nvim --headless "+Lazy! sync" +qa` exit code + `:checkhealth lazy`
  spot check.
- Manual acceptance: user opens sideview in a side pane, presses Enter on
  a file, edits in LazyVim-powered Neovim.
