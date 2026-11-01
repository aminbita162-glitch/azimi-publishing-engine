"""Parser for content.md as defined in documentation/content-format.md.

The parser is strict: any syntax outside the specification is rejected with an
error that names the line number. It never evaluates or executes content.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from ..errors import ContentError
from .diagram_spec import DiagramSpec, parse_diagram

MAX_HEADING_DEPTH = 3
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")

_HEADING = re.compile(r"^(#{1,})\s+(\S.*?)\s*$")
_BULLET = re.compile(r"^- +(\S.*)$")
_NUMBERED = re.compile(r"^\d+\. +(\S.*)$")
_FENCE_LANG = re.compile(r"^[A-Za-z0-9_+.#-]+$")
_TABLE_SEPARATOR_CELL = re.compile(r"^:?-+:?$")
_HTML = re.compile(r"</?[A-Za-z!]")
CALLOUT_KINDS = ("NOTE", "WARNING", "TIP", "KEY", "CHECKPOINT", "OBJECTIVES", "EXAMPLE", "PITFALL")
_REF_ID = re.compile(r"^[a-z][a-z0-9-]{0,39}$")
_ATTRS = re.compile(r"\s*\{([^{}]*)\}\s*$")
_CALLOUT = re.compile(r"^(" + "|".join(CALLOUT_KINDS) + r"):\s*(\S.*)$", re.DOTALL)


@dataclass(frozen=True)
class Block:
    """Base class of all document blocks. line is the 1-based source line."""

    line: int


@dataclass(frozen=True)
class Heading(Block):
    level: int
    text: str
    ref_id: Optional[str] = None
    numbered: bool = True


@dataclass(frozen=True)
class Paragraph(Block):
    text: str


@dataclass(frozen=True)
class BulletList(Block):
    items: Tuple[str, ...]


@dataclass(frozen=True)
class NumberedList(Block):
    items: Tuple[str, ...]


@dataclass(frozen=True)
class Code(Block):
    language: str
    lines: Tuple[str, ...]


@dataclass(frozen=True)
class Table(Block):
    header: Tuple[str, ...]
    rows: Tuple[Tuple[str, ...], ...]
    align: Tuple[str, ...]
    ref_id: Optional[str] = None
    caption: Optional[str] = None


@dataclass(frozen=True)
class Image(Block):
    path: str
    alt: str
    caption: Optional[str]
    ref_id: Optional[str] = None


@dataclass(frozen=True)
class Callout(Block):
    kind: str
    text: str


@dataclass(frozen=True)
class Diagram(Block):
    """A diagram described in text; spec is a validated DiagramSpec."""

    spec: "DiagramSpec"
    ref_id: Optional[str] = None
    caption: Optional[str] = None


@dataclass(frozen=True)
class PageBreak(Block):
    pass


def _check_text(text: str, line: int) -> None:
    if _HTML.search(text):
        raise ContentError("raw HTML is not allowed", line)
    if "\t" in text:
        raise ContentError("tab characters are not allowed outside code blocks", line)
    if any(ord(ch) < 32 for ch in text):
        raise ContentError("control characters are not allowed", line)


def _check_ref_id(value: str, number: int) -> None:
    if not _REF_ID.match(value):
        raise ContentError("an id must be lowercase letters, digits and hyphens, starting with a letter", number)


def _split_heading_attributes(text: str, number: int):
    """Return (text, ref_id, numbered) for a heading that may end in {#id .nonum}."""
    match = _ATTRS.search(text)
    if not match:
        return text, None, True
    ref_id = None
    numbered = True
    for token in match.group(1).split():
        if token.startswith("#"):
            ref_id = token[1:]
            _check_ref_id(ref_id, number)
        elif token == ".nonum":
            numbered = False
        else:
            raise ContentError(f"unknown heading attribute: {token}", number)
    return text[: match.start()].rstrip(), ref_id, numbered


def _is_block_start(line: str) -> bool:
    stripped = line.strip()
    return bool(
        line.startswith("~~~")
        or stripped == "PAGEBREAK"
        or stripped.startswith("IMG:")
        or stripped.startswith("TABLE:")
        or stripped.startswith("|")
        or _HEADING.match(line)
        or _BULLET.match(line)
        or _NUMBERED.match(line)
    )


def _parse_image(line_text: str, number: int) -> Image:
    parts = [part.strip() for part in line_text.strip()[len("IMG:"):].split("|")]
    if len(parts) not in (2, 3, 4):
        raise ContentError("image syntax is IMG: path | alt text | caption | id", number)
    path, alt = parts[0], parts[1]
    caption = parts[2] if len(parts) >= 3 and parts[2] else None
    ref_id = parts[3] if len(parts) == 4 and parts[3] else None
    if ref_id is not None:
        _check_ref_id(ref_id, number)
        if caption is None:
            raise ContentError("an image with an id needs a caption", number)
    if not path:
        raise ContentError("image path is empty", number)
    if not alt:
        raise ContentError("image alt text is mandatory", number)
    if "://" in path or path.startswith("/") or "\\" in path:
        raise ContentError("image path must be a relative local path", number)
    if any(part in ("..", ".", "") for part in path.split("/")):
        raise ContentError("image path must not contain parent or empty components", number)
    if not path.lower().endswith(IMAGE_EXTENSIONS):
        raise ContentError("image must be PNG or JPEG", number)
    for text in (alt, caption or ""):
        _check_text(text, number)
    return Image(line=number, path=path, alt=alt, caption=caption, ref_id=ref_id)


def _split_row(line_text: str) -> Tuple[str, ...]:
    return tuple(cell.strip() for cell in line_text.strip().strip("|").split("|"))


def _parse_table(rows: List[Tuple[int, str]]) -> Table:
    first = rows[0][0]
    if len(rows) < 3:
        raise ContentError("table needs a header row, a separator row and at least one data row", first)
    header = _split_row(rows[0][1])
    separator = _split_row(rows[1][1])
    if len(separator) != len(header) or not all(_TABLE_SEPARATOR_CELL.match(c) for c in separator):
        raise ContentError("table separator row is missing or malformed", rows[1][0])
    if not all(header):
        raise ContentError("table header cells must not be empty", first)
    data = []
    for number, text in rows[2:]:
        cells = _split_row(text)
        if len(cells) != len(header):
            raise ContentError(f"table row has {len(cells)} cells, expected {len(header)}", number)
        data.append(cells)
    for number, text in rows:
        _check_text(text, number)
    align = tuple(
        "center" if c.startswith(":") and c.endswith(":") else "right" if c.endswith(":") else "left"
        for c in separator
    )
    return Table(line=first, header=header, rows=tuple(data), align=align)


def parse(text: str) -> List[Block]:
    """Parse content.md text into a list of blocks."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: List[Block] = []
    index = 0
    count = len(lines)
    last_heading = 0
    pending_table = None

    while index < count:
        line = lines[index]
        number = index + 1

        if not line.strip():
            index += 1
            continue

        if line.startswith("~~~"):
            language = line[3:].strip()
            if not language:
                raise ContentError("code fence requires a language label", number)
            if not _FENCE_LANG.match(language):
                raise ContentError("code fence language label is invalid", number)
            body: List[str] = []
            index += 1
            closed = False
            while index < count:
                if lines[index].strip() == "~~~":
                    closed = True
                    break
                body.append(lines[index])
                index += 1
            if not closed:
                raise ContentError("code block is not closed", number)
            if language == "diagram":
                spec = parse_diagram(body, number + 1)
                blocks.append(Diagram(line=number, spec=spec, ref_id=spec.ref_id, caption=spec.caption))
            else:
                blocks.append(Code(line=number, language=language, lines=tuple(body)))
            index += 1
            continue

        stripped = line.strip()

        if stripped == "PAGEBREAK":
            blocks.append(PageBreak(line=number))
            index += 1
            continue

        if stripped.startswith("IMG:"):
            blocks.append(_parse_image(line, number))
            index += 1
            continue

        if stripped.startswith("TABLE:"):
            parts = [part.strip() for part in stripped[len("TABLE:"):].split("|")]
            if len(parts) != 2 or not parts[0] or not parts[1]:
                raise ContentError("table caption syntax is TABLE: id | caption", number)
            _check_ref_id(parts[0], number)
            _check_text(parts[1], number)
            pending_table = (parts[0], parts[1], number)
            index += 1
            while index < count and not lines[index].strip():
                index += 1
            if index >= count or not lines[index].strip().startswith("|"):
                raise ContentError("a TABLE: line must be followed by a table", number)
            continue

        heading = _HEADING.match(line)
        if heading:
            level = len(heading.group(1))
            if level > MAX_HEADING_DEPTH:
                raise ContentError(f"heading depth exceeds {MAX_HEADING_DEPTH}", number)
            if level > last_heading + 1:
                raise ContentError("heading level skips a level", number)
            heading_text, ref_id, numbered_heading = _split_heading_attributes(heading.group(2), number)
            _check_text(heading_text, number)
            if not heading_text:
                raise ContentError("heading text is empty", number)
            blocks.append(
                Heading(line=number, level=level, text=heading_text, ref_id=ref_id, numbered=numbered_heading)
            )
            last_heading = level
            index += 1
            continue

        if stripped.startswith("|"):
            rows: List[Tuple[int, str]] = []
            while index < count and lines[index].strip().startswith("|"):
                rows.append((index + 1, lines[index]))
                index += 1
            table = _parse_table(rows)
            if pending_table is not None:
                table = Table(
                    line=table.line, header=table.header, rows=table.rows, align=table.align,
                    ref_id=pending_table[0], caption=pending_table[1],
                )
                pending_table = None
            blocks.append(table)
            continue

        bullet = _BULLET.match(line)
        numbered = _NUMBERED.match(line)
        if bullet or numbered:
            pattern = _BULLET if bullet else _NUMBERED
            items: List[str] = []
            while index < count and pattern.match(lines[index]):
                item = pattern.match(lines[index]).group(1).strip()  # type: ignore[union-attr]
                _check_text(item, index + 1)
                items.append(item)
                index += 1
            if index < count and lines[index].strip() and not _is_block_start(lines[index]):
                raise ContentError("a list must be followed by a blank line", index + 1)
            kind = BulletList if bullet else NumberedList
            blocks.append(kind(line=number, items=tuple(items)))
            continue

        paragraph: List[str] = []
        while index < count and lines[index].strip():
            if paragraph and _is_block_start(lines[index]):
                raise ContentError("a paragraph must be followed by a blank line", index + 1)
            paragraph.append(lines[index].strip())
            index += 1
        joined = " ".join(paragraph)
        _check_text(joined, number)
        callout = _CALLOUT.match(joined)
        if callout:
            blocks.append(Callout(line=number, kind=callout.group(1), text=callout.group(2)))
        else:
            blocks.append(Paragraph(line=number, text=joined))

    return blocks
