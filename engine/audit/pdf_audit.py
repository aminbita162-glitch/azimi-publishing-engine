"""Audit layers applied to every built PDF.

Each check returns PASS or FAIL with evidence. A document that fails any check
is not released: the build command exits with a non-zero status.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pypdf import PdfReader

from ..render.styles import MARGIN_BOTTOM, MARGIN_TOP, PAGE_HEIGHT, PAGE_WIDTH
from ..schemas.meta import Meta

MAX_BLANK_RATIO = 0.28
MAX_PDF_BYTES = 25 * 1024 * 1024
MIN_PAGE_TEXT = 20
A4_TOLERANCE = 1.0


@dataclass(frozen=True)
class Check:
    id: str
    name: str
    status: str
    detail: str

    @property
    def passed(self) -> bool:
        return self.status == "PASS"


@dataclass(frozen=True)
class AuditReport:
    checks: Tuple[Check, ...]
    page_fill: Tuple[float, ...]
    exempt_pages: Tuple[int, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "result": "PASS" if self.passed else "FAIL",
            "checks": [
                {"id": c.id, "name": c.name, "status": c.status, "detail": c.detail} for c in self.checks
            ],
            "page_fill": [round(value, 3) for value in self.page_fill],
            "exempt_pages": list(self.exempt_pages),
            "max_blank_ratio": MAX_BLANK_RATIO,
        }


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def page_fill_ratios(reader: PdfReader) -> List[float]:
    """Fraction of the body area used on each page, measured from the lowest body text line."""
    top = PAGE_HEIGHT - MARGIN_TOP
    bottom = MARGIN_BOTTOM
    ratios: List[float] = []
    for page in reader.pages:
        lowest: List[float] = []

        def visit(text, cm, tm, font_dict, font_size, _lowest=lowest):
            if text.strip():
                y = tm[5] * cm[3] + cm[5] if cm else tm[5]
                if bottom - 2 <= y <= top + 2:
                    _lowest.append(y)

        page.extract_text(visitor_text=visit)
        if not lowest:
            ratios.append(0.0)
        else:
            ratios.append(max(0.0, min(1.0, (top - min(lowest)) / (top - bottom))))
    return ratios


def _outline_entries(reader: PdfReader) -> List[Tuple[str, int]]:
    entries: List[Tuple[str, int]] = []

    def walk(items):
        for item in items:
            if isinstance(item, list):
                walk(item)
            else:
                try:
                    page = reader.get_destination_page_number(item) + 1
                except Exception:
                    page = -1
                entries.append((str(item.title), page))

    walk(reader.outline)
    return entries


def audit_pdf(
    pdf: bytes,
    meta: Meta,
    exempt_pages: Sequence[int],
    expect_outline: bool = True,
    max_blank_ratio: float = MAX_BLANK_RATIO,
) -> AuditReport:
    """Run all audit checks on pdf and return the report."""
    reader = PdfReader(io.BytesIO(pdf))
    pages = list(reader.pages)
    texts = [page.extract_text() or "" for page in pages]
    checks: List[Check] = []

    def add(check_id: str, name: str, problems: Sequence[str], ok_detail: str) -> None:
        checks.append(
            Check(check_id, name, "FAIL" if problems else "PASS", "; ".join(problems[:6]) if problems else ok_detail)
        )

    # A1 text on every page
    empty = [i + 1 for i, text in enumerate(texts) if len(text.strip()) < MIN_PAGE_TEXT]
    add("A1", "Every page carries extractable text", [f"pages without text: {empty}"] if empty else [],
        f"{len(pages)} pages")

    # A2 fonts
    unembedded: List[str] = []
    for number, page in enumerate(pages, start=1):
        fonts = (page.get("/Resources") or {}).get("/Font", {})
        for ref in fonts.values():
            font = ref.get_object()
            descriptor = font.get("/FontDescriptor")
            if descriptor is None or not any(k in descriptor.get_object() for k in ("/FontFile2", "/FontFile3", "/FontFile")):
                unembedded.append(f"page {number}: {font.get('/BaseFont')}")
    add("A2", "All fonts are embedded", sorted(set(unembedded)), "every font embedded")

    # A3 metadata
    info = reader.metadata
    problems = []
    if info is None:
        problems.append("document information is missing")
    else:
        if (info.title or "") != meta.title:
            problems.append("title differs from meta.yaml")
        if (info.author or "") != meta.author:
            problems.append("author differs from meta.yaml")
        if not info.subject:
            problems.append("subject is empty")
        if not info.get("/CreationDate"):
            problems.append("creation date is missing")
    language = str(reader.trailer["/Root"].get("/Lang", ""))
    if language != meta.language:
        problems.append(f"document language is {language!r}, expected {meta.language!r}")
    add("A3", "Metadata and document language", problems, "title, author, subject, date and language set")

    # A4 outline and destinations
    entries = _outline_entries(reader)
    problems = []
    if expect_outline and not entries:
        problems.append("the outline is empty")
    for title, page in entries:
        if page < 1 or page > len(pages):
            problems.append(f"outline entry {title!r} has no valid destination")
        elif _normalize(title) not in _normalize(texts[page - 1]):
            problems.append(f"outline entry {title!r} is not on page {page}")
    add("A4", "Outline entries point to their headings", problems, f"{len(entries)} entries verified")

    # A5 links
    external = internal = 0
    problems = []
    for number, page in enumerate(pages, start=1):
        for annotation in page.get("/Annots") or []:
            obj = annotation.get_object()
            if obj.get("/Subtype") != "/Link":
                continue
            action = obj.get("/A")
            action = action.get_object() if action is not None else None
            if action is not None and action.get("/S") == "/URI":
                external += 1
                uri = str(action.get("/URI"))
                if not uri.lower().startswith(("https://", "http://")):
                    problems.append(f"page {number}: unsafe link {uri[:40]!r}")
            else:
                internal += 1
                if "/Dest" not in obj and (action is None or "/D" not in action):
                    problems.append(f"page {number}: link without destination")
    add("A5", "Links are safe and complete", problems, f"{external} external, {internal} internal")

    # A6 geometry
    bad = [
        i + 1 for i, page in enumerate(pages)
        if abs(float(page.mediabox.width) - PAGE_WIDTH) > A4_TOLERANCE
        or abs(float(page.mediabox.height) - PAGE_HEIGHT) > A4_TOLERANCE
    ]
    add("A6", "Every page is A4", [f"pages with another size: {bad}"] if bad else [], "A4 portrait")

    # A7 page fill
    fill = page_fill_ratios(reader)
    exempt = set(exempt_pages)
    low = [
        f"page {i + 1} ({round((1 - value) * 100)}% blank)"
        for i, value in enumerate(fill)
        if (i + 1) not in exempt and (1 - value) > max_blank_ratio
    ]
    checked = len(fill) - len([p for p in range(1, len(fill) + 1) if p in exempt])
    add("A7", f"Body pages are filled to at least {round((1 - max_blank_ratio) * 100)}%", low,
        f"{checked} body pages checked")

    # A8 size
    add("A8", "File size is reasonable", [f"{len(pdf)} bytes"] if len(pdf) > MAX_PDF_BYTES else [],
        f"{len(pdf) // 1024} KB")

    return AuditReport(tuple(checks), tuple(fill), tuple(sorted(exempt)))
