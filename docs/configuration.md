# Configuration

sideview is zero-config by default; everything below is optional.

## Environment variables

| Variable | Values | Effect |
|---|---|---|
| `EDITOR` | `nvim`, `vim`, `cursor`, `code`, `zed`, `subl`, … | Editor for `e` and commit messages. Auto-detects `nvim`, then `vim`. GUI editors open detached at the selected line. |
| `SIDEVIEW_ICONS` | `nerd` \| `emoji` \| `off` | File icon style. Default: `nerd` when a Nerd Font is installed, else `emoji`. |
| `SIDEVIEW_TRUECOLOR` | `on` (default) \| `off` | Redefine the terminal's 256-color slots to exact tokyonight-night RGB. `off` keeps the stock palette. |
| `SIDEVIEW_COMMIT_AI` | `on` (default) \| `claude` \| `cursor` \| `off` | Commit-message generator. `on` auto-picks the first installed agent CLI (`claude`, then `cursor-agent`); `claude`/`cursor` force one; `off` uses the heuristic file summary only. |
| `SIDEVIEW_WIDTHPROBE` | `on` (default) \| `off` | Startup probe that measures how the terminal really renders the chrome glyphs (see below). |
| `SIDEVIEW_NO_FONT_INSTALL` | `1` | Don't auto-install the Symbols Nerd Font on first run. |
| `SIDEVIEW_STATE` | path | Where to keep per-repo state. Default `~/.config/sideview/state.json`. |

## Persistence

Expanded directories, the pane split, and the hidden-files toggle are
saved per root directory in `state.json` and restored next launch. The
file keeps the 20 most recently used roots.

## Icons and fonts

Nerd icons need a [Nerd Font](https://www.nerdfonts.com). `sideview
--doctor` checks your setup; `sideview --install-font` installs the
Symbols Nerd Font into your user fonts (also offered automatically on
first run). No Nerd Font? `SIDEVIEW_ICONS=emoji` looks almost as good.

## The width probe (garbled-text protection)

Terminals occasionally render a symbol wider than curses thinks it is —
Warp, for example, draws some glyphs two cells wide. When that happens
to a glyph in the header, partial repaints (e.g. moving between repos)
leave crunched, overlapping text.

At startup sideview asks the terminal how wide it actually renders the
branch symbol `⎇`, the focus arrow, and the selection gutter, and swaps
any mis-rendered glyph for a safe fallback. The probe takes a few
milliseconds; `SIDEVIEW_WIDTHPROBE=off` disables it if your terminal
does something odd with cursor-position queries.

## Theme

The palette is tokyonight-night, matched to LazyVim. On terminals that
support palette redefinition you get the exact RGB values; otherwise the
closest 256-color approximations; on 8-color terminals a plain fallback.
