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

MAX_BLANK_RATIO = 0.13  # 87% minimum body-page coverage
MAX_PDF_BYTES = 25 * 1024 * 1024
MIN_PAGE_TEXT = 20
MIN_FONT_SIZE = 7.5
MIN_IMAGE_DPI = 140.0
MIN_CONTRAST = 4.5
A4_TOLERANCE = 1.0
# A painted rectangle that spans at least this fraction of the body-frame height
# is treated as a decorative full-page background, watermark or rule rather than
# substantive body fill, so it cannot inflate the measured page fill.  Real
# content rectangles (diagram nodes, table cells, code frames) are far shorter
# than the body frame and are always counted.
DECORATIVE_FULL_FRAME_FRACTION = 0.9


@dataclass(frozen=True)
class Check:
    id: str
    name: str
    status: str
    detail: str
    issues: Tuple[str, ...] = ()

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
                {
                    "id": c.id,
                    "name": c.name,
                    "status": c.status,
                    "detail": c.detail,
                    "issues": list(c.issues),
                }
                for c in self.checks
            ],
            "page_fill": [round(value, 3) for value in self.page_fill],
            "exempt_pages": list(self.exempt_pages),
            "max_blank_ratio": MAX_BLANK_RATIO,
        }


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def page_fill_ratios(reader: PdfReader) -> List[float]:
    """Fraction of the body area used on each page.

    Measured from the lowest drawn element (text characters, XObject images and
    the background rectangles of tables, code blocks and figures) to the top of
    the body frame.  A painted rectangle that spans at least
    ``DECORATIVE_FULL_FRAME_FRACTION`` of the body-frame height is a decorative
    full-page background, watermark or rule and is not counted, so it cannot
    inflate the measured fill (false-fill defence).  Real content rectangles
    are far shorter than the body frame and are always counted.
    """
    top = PAGE_HEIGHT - MARGIN_TOP
    bottom = MARGIN_BOTTOM
    span = top - bottom
    ratios: List[float] = []
    for page in reader.pages:
        lowest: List[float] = []

        def visit(text, cm, tm, font_dict, font_size, _lowest=lowest):
            if text.strip():
                y = tm[5] * cm[3] + cm[5] if cm else tm[5]
                if bottom - 2 <= y <= top + 2:
                    _lowest.append(y)

        page.extract_text(
            visitor_text=visit,
            visitor_operand_before=_rect_visitor(lowest, bottom, top, span),
        )
        if not lowest:
            ratios.append(0.0)
        else:
            ratios.append(max(0.0, min(1.0, (top - min(lowest)) / span)))
    return ratios


def _rect_visitor(lowest: list, bottom: float, top: float, span: float):
    """Return a visitor_operand_before callback that records painted-rectangle and
    XObject-image bottoms.

    pypdf calls visitor_operand_before(operator, operands, cm_matrix, tm_matrix).
    A rectangle ('re') whose height is at least DECORATIVE_FULL_FRAME_FRACTION of
    the body-frame height is a decorative full-page background and is skipped;
    XObject images ('Do') are always substantive content.
    """

    def visitor(operator, operands, cm_matrix, tm_matrix):  # noqa: ARG001
        # 're' (rectangle): operands are [x, y, width, height]; height may be
        # negative (ReportLab draws top-down).  Use the absolute height so a
        # decorative full-page background (height ~= the body frame) is skipped
        # while real content rectangles (cells, frames, diagram nodes) count.
        if operator == b"re" and len(operands) >= 4:
            try:
                y = float(operands[1])
                h = float(operands[3])
                if abs(h) < DECORATIVE_FULL_FRAME_FRACTION * span:
                    y_low = min(y, y + h)
                    if bottom - 2 <= y_low <= top + 2:
                        lowest.append(y_low)
            except (TypeError, ValueError):
                pass
        # 'Do' (XObject — drawn image/form): the current cm_matrix encodes the
        # bounding box.  For a unit-square image placed with [w 0 0 h x y] cm,
        # the bottom-left y is the cm_matrix translation component (index 5).
        elif operator == b"Do" and cm_matrix:
            try:
                y_low = float(cm_matrix[5])
                if bottom - 2 <= y_low <= top + 2:
                    lowest.append(y_low)
            except (TypeError, ValueError, IndexError):
                pass

    return visitor


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


def _unreadable_report(reason: str, exempt_pages: Sequence[int]) -> "AuditReport":
    """A failing audit report for an unreadable, encrypted or truncated PDF.

    No other check can run without readable pages, so the audit fails closed
    with a single readability check rather than crashing.
    """
    return AuditReport(
        checks=(Check("A0", "PDF is readable", "FAIL", reason, (reason,)),),
        page_fill=(),
        exempt_pages=tuple(sorted(set(exempt_pages))),
    )


def audit_pdf(
    pdf: bytes,
    meta: Meta,
    exempt_pages: Sequence[int],
    expect_outline: bool = True,
    max_blank_ratio: float = MAX_BLANK_RATIO,
    min_image_dpi: Optional[float] = None,
    contrast: Sequence[Tuple[str, float]] = (),
) -> AuditReport:
    """Run all audit checks on pdf and return the report."""
    try:
        reader = PdfReader(io.BytesIO(pdf))
        if reader.is_encrypted:
            return _unreadable_report(
                "encrypted PDF: the audit requires an unencrypted document", exempt_pages
            )
        pages = list(reader.pages)
        texts = [page.extract_text() or "" for page in pages]
    except Exception as exc:  # truncated, malformed or otherwise unreadable input
        return _unreadable_report(
            f"unreadable PDF: {type(exc).__name__}: {exc}", exempt_pages
        )

    checks: List[Check] = []

    def add(check_id: str, name: str, problems: Sequence[str], ok_detail: str) -> None:
        problems = list(problems)
        if problems:
            preview = "; ".join(problems[:6])
            if len(problems) > 6:
                preview += f"; … ({len(problems)} total, see issues)"
            detail = preview
        else:
            detail = ok_detail
        checks.append(
            Check(check_id, name, "FAIL" if problems else "PASS", detail, tuple(problems))
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

    # A9 internal links land on a page
    problems = []
    landed = 0
    for number, page in enumerate(pages, start=1):
        for annotation in page.get("/Annots") or []:
            obj = annotation.get_object()
            if obj.get("/Subtype") != "/Link":
                continue
            destination = obj.get("/Dest")
            action = obj.get("/A")
            if destination is None and action is not None:
                action = action.get_object()
                if action.get("/S") == "/URI":
                    continue
                destination = action.get("/D")
            if destination is None:
                continue
            try:
                if isinstance(destination, (str, bytes)) or not isinstance(destination, list):
                    resolved = reader.named_destinations.get(str(destination))
                    target = reader.get_destination_page_number(resolved) if resolved is not None else -1
                else:
                    target = reader.get_page_number(destination[0].get_object())
            except Exception:
                target = -1
            if target < 0 or target >= len(pages):
                problems.append(f"page {number}: a link points nowhere")
            else:
                landed += 1
    add("A9", "Internal links land on a page", problems, f"{landed} internal links resolve")

    # A10 figure and table numbers are continuous
    problems = []
    for label in ("Figure", "Table"):
        numbers = sorted({int(n) for text in texts for n in re.findall(rf"(?m)^{label} (\d+)\. ", text)})
        if numbers and numbers != list(range(1, numbers[-1] + 1)):
            problems.append(f"{label} numbers are {numbers}")
    add("A10", "Figure and table numbers are continuous", problems, "numbering has no gaps")

    # A11 smallest text
    sizes: List[float] = []
    for page in pages:
        def visit_size(text, cm, tm, font_dict, font_size, _sizes=sizes):
            if text.strip() and font_size:
                a = tm[0] * cm[0] + tm[1] * cm[2]
                d = tm[2] * cm[1] + tm[3] * cm[3]
                b = tm[0] * cm[1] + tm[1] * cm[3]
                c = tm[2] * cm[0] + tm[3] * cm[2]
                scale = abs(a * d - b * c) ** 0.5
                _sizes.append(round(font_size * scale, 2))

        page.extract_text(visitor_text=visit_size)
    smallest = min(sizes) if sizes else 0.0
    add("A11", f"Smallest text is at least {MIN_FONT_SIZE} pt",
        [f"smallest text is {smallest} pt"] if sizes and smallest < MIN_FONT_SIZE else [],
        f"smallest text {smallest} pt")

    # A12 image resolution
    if min_image_dpi is None:
        add("A12", "Raster images are sharp enough", [], "no raster figures")
    else:
        add("A12", f"Raster images have at least {int(MIN_IMAGE_DPI)} dpi",
            [f"lowest image resolution is {round(min_image_dpi)} dpi"] if min_image_dpi < MIN_IMAGE_DPI else [],
            f"lowest image resolution {round(min_image_dpi)} dpi")

    # A13 colour contrast
    weak = [f"{name} {ratio}:1" for name, ratio in contrast if ratio < MIN_CONTRAST]
    lowest = min((ratio for _, ratio in contrast), default=0.0)
    add("A13", f"Text contrast is at least {MIN_CONTRAST}:1", weak, f"lowest ratio {lowest}:1 over {len(contrast)} pairs")

    # A14 no active content
    problems = []
    root = reader.trailer["/Root"]
    for key in ("/OpenAction", "/AA", "/AcroForm"):
        if key in root:
            problems.append(f"the catalog contains {key}")
    names = root.get("/Names")
    if names is not None:
        for key in ("/JavaScript", "/EmbeddedFiles"):
            if key in names.get_object():
                problems.append(f"the name tree contains {key}")
    forbidden_actions = {"/JavaScript", "/Launch", "/SubmitForm", "/ImportData", "/GoToR", "/GoToE", "/Rendition"}
    for number, page in enumerate(pages, start=1):
        if "/AA" in page:
            problems.append(f"page {number} has page actions")
        for annotation in page.get("/Annots") or []:
            obj = annotation.get_object()
            action = obj.get("/A")
            if action is not None and str(action.get_object().get("/S")) in forbidden_actions:
                problems.append(f"page {number}: forbidden action {action.get_object().get('/S')}")
            if obj.get("/Subtype") in ("/FileAttachment", "/Widget", "/Movie", "/Sound", "/RichMedia", "/Screen"):
                problems.append(f"page {number}: forbidden annotation {obj.get('/Subtype')}")
    add("A14", "No active or embedded content", problems, "no scripts, launch actions, forms or attachments")

    # A15 metadata hygiene
    problems = []
    path_like = re.compile(r"(/Users/|/home/|/tmp/|/var/|[A-Za-z]:\\|\\\\)")
    if info is not None:
        for key, value in info.items():
            if path_like.search(str(value)):
                problems.append(f"{key} contains a local path")
    add("A15", "Metadata does not leak local paths", problems, "document information is clean")

    # A16 text integrity
    problems = []
    for number, text in enumerate(texts, start=1):
        if "\ufffd" in text or "(cid:" in text or any(ord(ch) < 32 and ch not in "\n\r\t\x0c" for ch in text):
            problems.append(f"page {number} has replacement or control characters")
    add("A16", "Text extracts cleanly", problems, "no replacement characters")

    return AuditReport(tuple(checks), tuple(fill), tuple(sorted(exempt)))
