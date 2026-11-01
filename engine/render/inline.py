"""Inline formatting: bold, italic and inline code.

Converts the inline subset of content.md into the paragraph markup used by the
renderer. All other characters are escaped, so content can never inject markup.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from ..errors import ContentError

_TAG = re.compile(r"<[^>]+>")

LINK_COLOR = "#0B5CAD"
_TLDS = "com|org|net|io|dev|ai|app|edu|gov"
_URL = re.compile(
    r"(?<![\w@./-])(?:https?://[^\s<>\"'`]+|(?:[A-Za-z0-9-]+\.)+(?:" + _TLDS + r")(?:/[^\s<>\"'`]*)?)"
)
_TRAILING = ".,;:!?)]}"


def _link_spans(text: str) -> List[tuple]:
    """Return (start, end, url) for every address in text, ignoring inline code."""
    masked = list(text)
    inside = False
    for index, char in enumerate(text):
        if char == "`":
            inside = not inside
            masked[index] = " "
        elif inside:
            masked[index] = " "
    spans = []
    for match in _URL.finditer("".join(masked)):
        start, end = match.start(), match.end()
        while end > start and text[end - 1] in _TRAILING:
            end -= 1
        label = text[start:end]
        if "*" in label or "_" in label.split("/")[0]:
            continue
        url = label if label.lower().startswith(("http://", "https://")) else "https://" + label
        spans.append((start, end, url))
    return spans


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_REFERENCE = re.compile(r"\[\[([a-z][a-z0-9-]*)\]\]")


def reference_ids(text: str) -> List[str]:
    """Return the ids used as [[id]] cross-references in text (inline code excluded)."""
    masked = []
    inside = False
    for char in text:
        if char == "`":
            inside = not inside
            masked.append(" ")
        else:
            masked.append(" " if inside else char)
    return _REFERENCE.findall("".join(masked))


def to_markup(text: str, line: Optional[int] = None, refs: Optional[Dict[str, str]] = None) -> str:
    """Return paragraph markup for text, or raise ContentError for unbalanced markers.

    When refs maps ids to labels, [[id]] becomes a link to that anchor; an unknown id is an error.
    """
    out: List[str] = []
    stack: List[str] = []
    index = 0
    size = len(text)
    links = {start: (end, url) for start, end, url in _link_spans(text)}

    while index < size:
        char = text[index]

        if index in links:
            end, url = links[index]
            label = _escape(text[index:end])
            href = url.replace("&", "&amp;")
            out.append(f'<a href="{href}" color="{LINK_COLOR}">{label}</a>')
            index = end
            continue

        if char == "[" and refs is not None and text.startswith("[[", index):
            match = _REFERENCE.match(text, index)
            if match:
                target = match.group(1)
                if target not in refs:
                    raise ContentError(f"unknown cross-reference [[{target}]]", line)
                out.append(f'<a href="#{target}" color="{LINK_COLOR}">{_escape(refs[target])}</a>')
                index = match.end()
                continue

        if char == "`":
            end = text.find("`", index + 1)
            if end == -1 or end == index + 1:
                raise ContentError("inline code is not closed", line)
            out.append('<font face="Mono" size="9.2">' + _escape(text[index + 1:end]) + "</font>")
            index = end + 1
            continue

        if char == "*":
            if text.startswith("***", index):
                raise ContentError("ambiguous emphasis marker; use ** for bold or * for italic", line)
            double = text.startswith("**", index)
            width = 2 if double else 1
            tag = "b" if double else "i"
            following = text[index + width] if index + width < size else ""
            preceding = text[index - 1] if index > 0 else ""

            if tag in stack:
                if preceding and not preceding.isspace():
                    if stack[-1] != tag:
                        raise ContentError("emphasis markers cross each other", line)
                    stack.pop()
                    out.append(f"</{tag}>")
                else:
                    out.append("*" * width)
            elif following and not following.isspace() and following != "*":
                stack.append(tag)
                out.append(f"<{tag}>")
            else:
                out.append("*" * width)
            index += width
            continue

        out.append(_escape(char))
        index += 1

    if stack:
        raise ContentError("emphasis is not closed", line)
    return "".join(out)


def to_plain(text: str, line: Optional[int] = None) -> str:
    """Return text with inline markers removed (for outlines and table of contents)."""
    markup = to_markup(text, line)
    stripped = _TAG.sub("", markup)
    return stripped.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
