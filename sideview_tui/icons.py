"""File-type icon tables and classification.

Icon styles (SIDEVIEW_ICONS env var): nerd (default), emoji, off.
Glyphs are written as escape sequences so the source stays editable in any
editor/font. Nerd glyphs use devicons/seti/font-awesome codepoint ranges,
stable since Nerd Fonts 2.x. Colors follow the spirit of the vscode-icons /
Material Icon Theme extensions.
"""
import os

EMOJI = {
    "dir": "\U0001F4C1", "dir_open": "\U0001F4C2", "py": "\U0001F40D",
    "md": "\U0001F4DD", "config": "\U0001F527", "code": "\U0001F4DC",
    "js": "\U0001F7E8", "ts": "\U0001F7E6", "go": "\U0001F439",
    "rust": "\U0001F980", "java": "☕", "git": "\U0001F527",
    "image": "\U0001F4F7", "audio": "\U0001F3B5", "video": "\U0001F3AC",
    "archive": "\U0001F4E6", "pdf": "\U0001F4D5", "lock": "\U0001F512",
    "docker": "\U0001F433", "html": "\U0001F310", "css": "\U0001F3A8",
    "shell": "\U0001F41A", "key": "\U0001F511", "db": "\U0001F4BE",
    "default": "\U0001F4C4",
}
NERD = {
    "dir": "", "dir_open": "", "py": "", "md": "",
    "config": "", "code": "", "js": "", "ts": "",
    "go": "", "rust": "", "java": "", "git": "",
    "image": "", "audio": "", "video": "",
    "archive": "", "pdf": "", "lock": "",
    "docker": "", "html": "", "css": "",
    "shell": "", "key": "", "db": "",
    "default": "",
}
ICON_COLORS = {
    "dir": 110, "dir_open": 110, "py": 68, "md": 109, "config": 178,
    "code": 146, "js": 185, "ts": 74, "go": 44, "rust": 172, "java": 173,
    "git": 202, "image": 176, "audio": 214, "video": 203, "archive": 180,
    "pdf": 167, "lock": 244, "docker": 39, "html": 208, "css": 75,
    "shell": 114, "key": 179, "db": 137, "default": 250,
}
EXT_CLASS = {
    ".py": "py", ".md": "md", ".markdown": "md", ".rst": "md",
    ".json": "config", ".yaml": "config", ".yml": "config",
    ".toml": "config", ".ini": "config", ".cfg": "config", ".conf": "config",
    ".js": "js", ".jsx": "js", ".mjs": "js", ".cjs": "js",
    ".ts": "ts", ".tsx": "ts",
    ".go": "go", ".rs": "rust", ".java": "java",
    ".c": "code", ".cpp": "code", ".h": "code", ".hpp": "code",
    ".rb": "code", ".php": "code", ".swift": "code", ".kt": "code",
    ".lua": "code", ".vim": "code",
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image",
    ".svg": "image", ".webp": "image", ".ico": "image", ".bmp": "image",
    ".wav": "audio", ".mp3": "audio", ".flac": "audio", ".aiff": "audio",
    ".ogg": "audio", ".m4a": "audio",
    ".mp4": "video", ".mov": "video", ".mkv": "video", ".webm": "video",
    ".zip": "archive", ".tar": "archive", ".gz": "archive", ".tgz": "archive",
    ".rar": "archive", ".7z": "archive", ".bz2": "archive", ".xz": "archive",
    ".pdf": "pdf", ".lock": "lock",
    ".html": "html", ".htm": "html",
    ".css": "css", ".scss": "css", ".sass": "css", ".less": "css",
    ".sh": "shell", ".zsh": "shell", ".bash": "shell", ".fish": "shell",
    ".pem": "key", ".crt": "key", ".pub": "key",
    ".db": "db", ".sqlite": "db", ".sqlite3": "db", ".sql": "db",
}
NAME_CLASS = {
    "dockerfile": "docker", "docker-compose.yml": "docker",
    "docker-compose.yaml": "docker", "makefile": "config",
    ".env": "key", ".gitignore": "git", ".gitattributes": "git",
    ".gitmodules": "git",
}

ICON_STYLE = os.environ.get("SIDEVIEW_ICONS", "nerd").lower()
ICONS = {"emoji": EMOJI, "nerd": NERD}.get(ICON_STYLE)


def classify(name, is_dir, is_open=False):
    if is_dir:
        return "dir_open" if is_open else "dir"
    cls = NAME_CLASS.get(name.lower())
    if cls is None:
        cls = EXT_CLASS.get(os.path.splitext(name)[1].lower(), "default")
    return cls


def icon_for(name, is_dir, is_open=False):
    if ICONS is None:
        return ("▾ " if is_open else "▸ ") if is_dir else "  "
    return ICONS[classify(name, is_dir, is_open)] + " "
