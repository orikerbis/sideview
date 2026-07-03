"""Lightweight per-line syntax highlighting for the preview pane.

Best-effort, regex-free sequential scan: strings, comments, numbers and
per-language keyword sets. Token classes: comment, string, number,
keyword, key (json/yaml keys). Unknown text gets class "".
"""
import os

PY_KW = {
    "def", "class", "return", "if", "elif", "else", "for", "while",
    "import", "from", "as", "with", "try", "except", "finally", "raise",
    "lambda", "pass", "break", "continue", "yield", "True", "False",
    "None", "and", "or", "not", "in", "is", "global", "nonlocal",
    "async", "await", "assert", "del", "match", "case",
}
SH_KW = {
    "if", "then", "else", "elif", "fi", "for", "while", "do", "done",
    "case", "esac", "function", "export", "local", "return", "echo",
    "source", "sudo", "set", "readonly", "shift", "exit", "in",
}
C_KW = {
    "function", "var", "let", "const", "if", "else", "for", "while",
    "return", "import", "export", "from", "class", "new", "this",
    "true", "false", "null", "undefined", "async", "await", "switch",
    "case", "break", "continue", "default", "typeof", "interface",
    "type", "enum", "extends", "implements", "static", "void", "int",
    "char", "float", "double", "struct", "public", "private", "final",
    "fn", "mut", "pub", "use", "mod", "impl", "match", "func", "package",
    "go", "defer", "chan", "map", "range", "nil",
}
LUA_KW = {
    "local", "function", "end", "if", "then", "else", "elseif", "for",
    "while", "do", "return", "require", "true", "false", "nil", "not",
    "and", "or", "in", "pairs", "ipairs",
}
TF_KW = {
    "resource", "variable", "output", "module", "provider", "data",
    "locals", "terraform", "true", "false", "null", "for_each", "count",
    "depends_on", "source", "type", "default", "description",
}
DOCKER_KW = {
    "FROM", "RUN", "CMD", "COPY", "ADD", "ENV", "EXPOSE", "WORKDIR",
    "ENTRYPOINT", "USER", "ARG", "VOLUME", "LABEL", "SHELL",
    "HEALTHCHECK", "ONBUILD", "AS",
}
SQL_KW = {
    "select", "from", "where", "insert", "update", "delete", "create",
    "table", "join", "left", "right", "inner", "on", "group", "by",
    "order", "limit", "values", "into", "set", "and", "or", "not",
    "null", "primary", "key", "index", "drop", "alter",
}

# lang -> (comment_prefix, keywords, keys_mode)
LANGS = {
    "py": ("#", PY_KW, False),
    "sh": ("#", SH_KW, False),
    "c": ("//", C_KW, False),
    "lua": ("--", LUA_KW, False),
    "sql": ("--", SQL_KW, False),
    "tf": ("#", TF_KW, False),
    "docker": ("#", DOCKER_KW, False),
    "json": (None, {"true", "false", "null"}, True),
    "yaml": ("#", {"true", "false", "null", "yes", "no"}, True),
}

EXT_LANG = {
    ".py": "py",
    ".sh": "sh", ".zsh": "sh", ".bash": "sh", ".fish": "sh",
    ".js": "c", ".jsx": "c", ".ts": "c", ".tsx": "c", ".mjs": "c",
    ".go": "c", ".rs": "c", ".c": "c", ".cpp": "c", ".h": "c",
    ".hpp": "c", ".java": "c", ".php": "c", ".swift": "c", ".kt": "c",
    ".lua": "lua", ".sql": "sql",
    ".json": "json", ".tfstate": "json",
    ".yaml": "yaml", ".yml": "yaml", ".toml": "yaml", ".ini": "yaml",
    ".cfg": "yaml", ".conf": "yaml",
    ".tf": "tf", ".tfvars": "tf",
}
NAME_LANG = {"dockerfile": "docker", "makefile": "sh"}


def detect(name):
    """Language key for a filename, or None."""
    low = name.lower()
    if low in NAME_LANG:
        return NAME_LANG[low]
    if low.endswith((".tfstate", ".tfstate.backup")):
        return "json"
    return EXT_LANG.get(os.path.splitext(low)[1])


def _flush(out, buf):
    if buf:
        out.append(("".join(buf), ""))
        buf.clear()


def segments(line, lang):
    """Split a line into (text, token_class) segments."""
    spec = LANGS.get(lang)
    if not spec or not line:
        return [(line, "")]
    comment, keywords, keys_mode = spec
    out, buf = [], []
    i, n = 0, len(line)
    while i < n:
        ch = line[i]
        if comment and line.startswith(comment, i):
            _flush(out, buf)
            out.append((line[i:], "comment"))
            return out
        if ch in "\"'":
            _flush(out, buf)
            j = i + 1
            while j < n and (line[j] != ch or line[j - 1] == "\\"):
                j += 1
            j = min(j + 1, n)
            cls = "string"
            if keys_mode:  # json/yaml: string followed by ':' is a key
                k = j
                while k < n and line[k] == " ":
                    k += 1
                if k < n and line[k] == ":":
                    cls = "key"
            out.append((line[i:j], cls))
            i = j
            continue
        if ch.isdigit() and (i == 0 or not (line[i - 1].isalnum()
                                            or line[i - 1] == "_")):
            _flush(out, buf)
            j = i
            while j < n and (line[j].isdigit() or line[j] in "._xXa-fA-F"):
                j += 1
            out.append((line[i:j], "number"))
            i = j
            continue
        if ch.isalpha() or ch == "_":
            _flush(out, buf)
            j = i
            while j < n and (line[j].isalnum() or line[j] == "_"):
                j += 1
            word = line[i:j]
            cls = "keyword" if word in keywords else ""
            if cls == "" and keys_mode and lang == "yaml":
                k = j
                if k < n and line[k] == ":" and not line[:i].strip():
                    cls = "key"
            out.append((word, cls))
            i = j
            continue
        buf.append(ch)
        i += 1
    _flush(out, buf)
    # merge adjacent same-class segments to reduce draw calls
    merged = []
    for text, cls in out:
        if merged and merged[-1][1] == cls:
            merged[-1] = (merged[-1][0] + text, cls)
        else:
            merged.append((text, cls))
    return merged
