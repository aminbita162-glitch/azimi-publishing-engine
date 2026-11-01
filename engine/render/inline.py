"""Inline formatting: bold, italic and inline code.

Converts the inline subset of content.md into the paragraph markup used by the
renderer. All other characters are escaped, so content can never inject markup.
"""

from __future__ import annotations

import re
from typing import List, Optional

from ..errors import ContentError

_TAG = re.compile(r"<[^>]+>")


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def to_markup(text: str, line: Optional[int] = None) -> str:
    """Return paragraph markup for text, or raise ContentError for unbalanced markers."""
    out: List[str] = []
    stack: List[str] = []
    index = 0
    size = len(text)

    while index < size:
        char = text[index]

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
