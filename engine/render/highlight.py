"""Lightweight, deterministic syntax classification for code blocks.

classify returns one class letter per character:

    k keyword    s string    c comment    n number    f definition name    p plain

No third-party library is used, so the result is identical on every machine.
"""

from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Pattern, Sequence, Tuple

PLAIN = "p"

_PY_KEYWORDS = (
    "False None True and as assert async await break class continue def del elif else except "
    "finally for from global if import in is lambda nonlocal not or pass raise return try while with yield"
).split()
_TS_KEYWORDS = (
    "abstract as async await break case catch class const continue declare default delete do else enum "
    "export extends false finally for from function if implements import in instanceof interface keyof let "
    "namespace new null of private protected public readonly return static super switch this throw true try "
    "type typeof undefined var void while yield"
).split()
_SH_KEYWORDS = "if then else elif fi for while until do done case esac function in select export local return".split()
_SQL_KEYWORDS = (
    "select from where insert into values update set delete create table primary key not null integer text "
    "begin commit rollback and or join on order by group limit default unique index drop alter add"
).split()
_JSON_KEYWORDS = ["true", "false", "null"]


def _words(words: Sequence[str], ignore_case: bool = False) -> Pattern[str]:
    flags = re.IGNORECASE if ignore_case else 0
    return re.compile(r"\b(?:" + "|".join(sorted(words, key=len, reverse=True)) + r")\b", flags)


_NUMBER = re.compile(r"\b\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?\b")


def _scanner(parts: Sequence[Tuple[str, str]]) -> Pattern[str]:
    return re.compile("|".join(f"(?P<{name}>{pattern})" for name, pattern in parts), re.DOTALL | re.MULTILINE)


_SCANNERS: Dict[str, Pattern[str]] = {
    "python": _scanner(
        [
            ("s", r'(?:[rRbBfF]{0,2})(?:"""|\'\'\').*?(?:"""|\'\'\')'),
            ("s2", r'(?:[rRbBfF]{0,2})"(?:\\.|[^"\\\n])*"'),
            ("s3", r"(?:[rRbBfF]{0,2})'(?:\\.|[^'\\\n])*'"),
            ("c", r"\#[^\n]*"),
            ("defn", r"\b(?:def|class)[ \t]+[A-Za-z_]\w*"),
            ("k", _words(_PY_KEYWORDS).pattern),
            ("n", _NUMBER.pattern),
        ]
    ),
    "typescript": _scanner(
        [
            ("c", r"//[^\n]*|/\*.*?\*/"),
            ("s", r"`(?:\\.|[^`\\])*`"),
            ("s2", r'"(?:\\.|[^"\\\n])*"'),
            ("s3", r"'(?:\\.|[^'\\\n])*'"),
            ("defn", r"\b(?:function|class|interface|type|enum)[ \t]+[A-Za-z_$][\w$]*"),
            ("k", _words(_TS_KEYWORDS).pattern),
            ("n", _NUMBER.pattern),
        ]
    ),
    "sh": _scanner(
        [
            ("c", r"(?:(?<=\s)|^)\#[^\n]*"),
            ("s2", r'"(?:\\.|[^"\\])*"'),
            ("s3", r"'[^']*'"),
            ("k", _words(_SH_KEYWORDS).pattern),
        ]
    ),
    "sql": _scanner(
        [
            ("c", r"--[^\n]*"),
            ("s3", r"'(?:''|[^'])*'"),
            ("k", _words(_SQL_KEYWORDS, ignore_case=True).pattern.replace("(?:", "(?i:", 1)),
            ("n", _NUMBER.pattern),
        ]
    ),
    "json": _scanner(
        [
            ("s2", r'"(?:\\.|[^"\\\n])*"'),
            ("k", _words(_JSON_KEYWORDS).pattern),
            ("n", r"-?\b\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?\b"),
        ]
    ),
    "yaml": _scanner(
        [
            ("c", r"(?:(?<=\s)|^)\#[^\n]*"),
            ("defn", r"^[ \t]*-?[ \t]*[A-Za-z_][\w.-]*(?=:)"),
            ("s2", r'"(?:\\.|[^"\\\n])*"'),
            ("s3", r"'[^'\n]*'"),
            ("k", _words(["true", "false", "null"]).pattern),
            ("n", _NUMBER.pattern),
        ]
    ),
}

ALIASES = {
    "py": "python", "python3": "python",
    "ts": "typescript", "tsx": "typescript", "js": "typescript", "javascript": "typescript",
    "bash": "sh", "shell": "sh", "zsh": "sh", "console": "sh",
    "yml": "yaml", "sqlite": "sql",
}

NUMBERED_LANGUAGES = {"python", "typescript", "sql", "json", "yaml"}


def normalize_language(language: str) -> str:
    key = language.strip().lower()
    return ALIASES.get(key, key)


def classify(lines: Sequence[str], language: str) -> List[List[str]]:
    """Return per-line, per-character class letters for lines."""
    scanner = _SCANNERS.get(normalize_language(language))
    text = "\n".join(lines)
    classes = [PLAIN] * len(text)

    if scanner is not None:
        for match in scanner.finditer(text):
            kind = match.lastgroup or ""
            start, end = match.start(), match.end()
            if kind == "defn":
                span = text[start:end]
                name = re.search(r"[A-Za-z_$][\w$.-]*$", span)
                split = start + (name.start() if name else 0)
                if language_is_yaml(language):
                    for index in range(start, end):
                        if text[index] not in " \t-":
                            classes[index] = "f"
                    continue
                for index in range(start, split):
                    classes[index] = "k"
                for index in range(split, end):
                    classes[index] = "f"
                continue
            letter = {"s": "s", "s2": "s", "s3": "s", "c": "c", "k": "k", "n": "n"}.get(kind, PLAIN)
            for index in range(start, end):
                classes[index] = letter

    result: List[List[str]] = []
    cursor = 0
    for line in lines:
        result.append(classes[cursor:cursor + len(line)])
        cursor += len(line) + 1
    return result


def language_is_yaml(language: str) -> bool:
    return normalize_language(language) == "yaml"


def to_markup(text: str, classes: Sequence[str], colors: Dict[str, str]) -> str:
    """Return paragraph markup for one line using colors keyed by class letter."""
    out: List[str] = []
    index = 0
    size = len(text)
    while index < size:
        letter = classes[index] if index < len(classes) else PLAIN
        end = index
        while end < size and (classes[end] if end < len(classes) else PLAIN) == letter:
            end += 1
        chunk = text[index:end].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        color = colors.get(letter)
        if letter == PLAIN or color is None:
            out.append(chunk)
        elif letter in ("k", "f"):
            out.append(f'<font color="{color}"><b>{chunk}</b></font>')
        else:
            out.append(f'<font color="{color}">{chunk}</font>')
        index = end
    return "".join(out)
