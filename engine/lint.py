"""Content lint: rules that protect a document before it is rendered.

Rules: terms that must never appear (a per-brand list), repeated words, and the
structure of the course profile. Every problem names its line in content.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Tuple

from .build.parser import (
    Block, BulletList, Callout, Code, Diagram, Heading, Image, NumberedList, Paragraph, Table,
)
from .errors import ConfigError

FORBIDDEN_FILE = "forbidden.txt"
MAX_TERMS = 200
_REPEAT = re.compile(r"\b([A-Za-z]{2,})\s+\1\b", re.IGNORECASE)
_ALLOWED_REPEATS = {"that", "had"}


@dataclass(frozen=True)
class Issue:
    line: int
    message: str

    def __str__(self) -> str:
        return f"line {self.line}: {self.message}"


def load_forbidden_terms(brand_dir: Path) -> Tuple[str, ...]:
    """Read brand/NAME/forbidden.txt: one term per line, # starts a comment."""
    path = brand_dir / FORBIDDEN_FILE
    if not path.is_file():
        return ()
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"{FORBIDDEN_FILE} cannot be read") from exc
    terms = [line.strip() for line in raw.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if len(terms) > MAX_TERMS:
        raise ConfigError(f"{FORBIDDEN_FILE} lists more than {MAX_TERMS} terms")
    return tuple(terms)


def block_texts(block: Block) -> List[str]:
    """All human-readable text of a block, including code and diagrams."""
    if isinstance(block, (Heading, Paragraph, Callout)):
        return [block.text]
    if isinstance(block, (BulletList, NumberedList)):
        return list(block.items)
    if isinstance(block, Table):
        cells = list(block.header) + [c for row in block.rows for c in row]
        return cells + ([block.caption] if block.caption else [])
    if isinstance(block, Image):
        return [block.alt] + ([block.caption] if block.caption else [])
    if isinstance(block, Code):
        return list(block.lines)
    if isinstance(block, Diagram):
        spec = block.spec
        texts = [n.label for n in spec.nodes] + [e.label for e in spec.edges if e.label]
        texts += [a.label for a in spec.actors] + [m.label for m in spec.messages]  # type: ignore[attr-defined]
        for layer in spec.layers:
            texts += [layer.name, layer.text]
        return texts + ([block.caption] if block.caption else [])
    return []


def lint(blocks: Sequence[Block], forbidden: Sequence[str], profile: str = "plain") -> List[Issue]:
    issues: List[Issue] = []
    patterns = [(term, re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", re.IGNORECASE))
                for term in forbidden]
    for block in blocks:
        is_code = isinstance(block, Code)
        for text in block_texts(block):
            for term, pattern in patterns:
                if pattern.search(text):
                    issues.append(Issue(block.line, f"the term '{term}' is on the forbidden list"))
            if not is_code:
                for match in _REPEAT.finditer(text):
                    if match.group(1).lower() not in _ALLOWED_REPEATS:
                        issues.append(Issue(block.line, f"repeated word '{match.group(1)}'"))
    if profile == "course":
        issues.extend(_course_issues(blocks))
    return sorted(set(issues), key=lambda i: (i.line, i.message))


def _course_issues(blocks: Sequence[Block]) -> List[Issue]:
    issues: List[Issue] = []
    chapters: List[Tuple[Heading, List[Block]]] = []
    for block in blocks:
        if isinstance(block, Heading) and block.level == 1:
            chapters.append((block, []))
        elif chapters:
            chapters[-1][1].append(block)
    for heading, body in chapters:
        if not heading.numbered:
            continue
        kinds = {b.kind for b in body if isinstance(b, Callout)}
        if "OBJECTIVES" not in kinds:
            issues.append(Issue(heading.line, f"chapter '{heading.text}' has no OBJECTIVES box"))
        summaries = [b for b in body if isinstance(b, Callout) and b.kind == "KEY"
                     and b.text.startswith("Chapter summary")]
        if not summaries:
            issues.append(Issue(heading.line, f"chapter '{heading.text}' has no 'Chapter summary' KEY box"))
    return issues
