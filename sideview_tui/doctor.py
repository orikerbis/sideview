"""Zero-config helpers: environment check and Nerd Font installer."""
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

from . import icons
from .app import EDITOR

FONT_ZIP_URL = ("https://github.com/ryanoasis/nerd-fonts/releases/latest/"
                "download/NerdFontsSymbolsOnly.zip")


def font_dir():
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Fonts")
    return os.path.expanduser("~/.local/share/fonts")


def install_font():
    """Download the Symbols Nerd Font (icon glyphs only) into the user's
    font directory so terminals can fall back to it for icons."""
    dest = font_dir()
    os.makedirs(dest, exist_ok=True)
    print("Downloading Symbols Nerd Font…")
    with tempfile.TemporaryDirectory() as tmp:
        zpath = os.path.join(tmp, "font.zip")
        urllib.request.urlretrieve(FONT_ZIP_URL, zpath)
        installed = []
        with zipfile.ZipFile(zpath) as z:
            for name in z.namelist():
                if name.endswith(".ttf"):
                    z.extract(name, tmp)
                    shutil.copy(os.path.join(tmp, name),
                                os.path.join(dest, os.path.basename(name)))
                    installed.append(os.path.basename(name))
        if not installed:
            print("No .ttf files found in the download — aborting.")
            return 1
    if sys.platform != "darwin" and shutil.which("fc-cache"):
        subprocess.run(["fc-cache", "-f", dest], capture_output=True)
    print("Installed to %s:" % dest)
    for f in installed:
        print("  " + f)
    print("\nRestart your terminal. Most terminals (Terminal.app, iTerm2,")
    print("modern Linux terminals) pick it up via font fallback; in iTerm2")
    print("you can also set it under Profiles → Text → Non-ASCII Font.")
    return 0


def run_doctor():
    def row(label, ok, detail=""):
        mark = "✔" if ok else "✘"
        print(" %s %-18s %s" % (mark, label, detail))

    print("sideview doctor\n")
    row("python", True, sys.version.split()[0])
    git = shutil.which("git")
    row("git", bool(git), git or "not found — required")
    row("editor", bool(shutil.which(EDITOR.split()[0])), EDITOR)
    nerd = icons.nerd_font_installed()
    row("nerd font", nerd,
        "found" if nerd else "not found — run: sideview --install-font")
    row("icon style", True, icons.ICON_STYLE
        + ("" if os.environ.get("SIDEVIEW_ICONS") else " (auto-detected)"))
    claude = shutil.which("claude")
    row("claude cli", bool(claude),
        (claude or "not found") + " — used for commit messages (optional)")
    pb = shutil.which("pbcopy") or shutil.which("xclip")
    row("clipboard", bool(pb), pb or "pbcopy/xclip not found")
    colors = os.environ.get("TERM", "")
    row("terminal", "256color" in colors or "truecolor" in colors,
        colors or "TERM unset")
    return 0
