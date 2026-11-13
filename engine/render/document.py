"""PDF composition with ReportLab.

render_document turns parsed blocks, validated metadata and a brand into PDF
bytes. Rendering is deterministic: the document timestamp comes from the
document metadata, never from the clock.
"""

from __future__ import annotations

import io
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from PIL import Image as PILImage, ImageOps
from reportlab import rl_config
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Flowable,
    Frame,
    HRFlowable,
    Image,
    KeepTogether,
    ListFlowable,
    ListItem,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    XPreformatted,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

from ..brand import Brand
from ..build.parser import (
    Block,
    BulletList,
    Callout,
    Code,
    Diagram as DiagramBlock,
    Heading,
    Image as ImageBlock,
    NumberedList,
    PageBreak as PageBreakBlock,
    Paragraph as ParagraphBlock,
    Table as TableBlock,
)
from .. import __version__
from ..errors import ConfigError, ContentError, EngineError
from ..paths import resolve_inside
from ..schemas.meta import Meta
from .diagram import DiagramFlowable, build_layout
from .fonts import check_glyphs
from .highlight import NUMBERED_LANGUAGES, PLAIN, classify, normalize_language
from .highlight import to_markup as highlight_markup
from .xmp import apply_xmp
from .inline import LINK_COLOR, NBSP, reference_ids, to_markup, to_plain
from .styles import (
    CHECKPOINT,
    CODE_BACKGROUND,
    CODE_CHUNK_LINES,
    CODE_COLORS,
    CODE_PADDING_LEFT,
    CODE_PADDING_RIGHT,
    CODE_PADDING_VERTICAL,
    CODE_SIZE,
    EXAMPLE,
    PITFALL,
    CONTENT_HEIGHT,
    CONTENT_WIDTH,
    GUTTER_BACKGROUND,
    MARGIN_BOTTOM,
    MARGIN_LEFT,
    MARGIN_RIGHT,
    MARGIN_TOP,
    MUTED,
    PAGE_HEIGHT,
    PAGE_WIDTH,
    RULE,
    TIP,
    WARNING,
    ZEBRA,
    Styles,
    build_styles,
    contrast_ratio,
    ensure_contrast,
    mix_with_white,
)

DEFAULT_IMAGE_DPI = 150.0
IMAGE_DPI: List[float] = []
MAX_IMAGE_HEIGHT = CONTENT_HEIGHT * 0.36
MIN_FIGURE_SCALE = 0.75
MIN_LAST_CHUNK = 3
FIGURE_SPACE_AFTER = 12.0
FIGURE_CAPTION_GAP = 6.0
CHAPTER_MIN_SPACE = 28 * mm  # minimum space for a chapter heading + first line (< 13% of body)
HEADING_TABLE_MIN_SPACE = 24 * mm  # heading + first row of a table or top of a figure
MAX_LAYOUT_ATTEMPTS = 5
MAX_PIXELS = 40_000_000
CONTINUATION_INDENT = "  "
KEEP_WITH_NEXT_MAX = 240


@dataclass(frozen=True)
class RenderResult:
    """Output of render_document."""

    pdf: bytes
    pages: int
    images: Tuple[str, ...]
    exempt_pages: Tuple[int, ...]
    min_image_dpi: Optional[float] = None
    contrast: Tuple[Tuple[str, float], ...] = ()


class HeadingParagraph(Paragraph):
    """A heading that carries its level and plain text for outline and contents."""

    def __init__(self, markup: str, style, level: int, plain: str) -> None:
        super().__init__(markup, style)
        self.level = level
        self.plain = plain


class ForcedBreak(PageBreak):
    """A page break that is intentional; the audit does not count its page as underfilled."""


class CaptionParagraph(Paragraph):
    """A table caption that is also an entry of the list of tables."""

    def __init__(self, markup: str, style, entry_text: str, key: str) -> None:
        super().__init__(markup, style)
        self.list_entry = ("LOTEntry", entry_text, key)


class _ListOf(TableOfContents):
    """A list of figures or tables, filled from captions of one kind."""

    def __init__(self, kind: str, style: ParagraphStyle, body_start: Optional[int] = None) -> None:
        super().__init__()
        self.formatter = lambda page: page_label(page, body_start)
        self.kind = kind
        self.levelStyles = [style]
        self.dotsMinLevel = 0
        self.tableStyle = TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Body"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )

    def notify(self, kind, stuff):
        if kind == self.kind:
            self.addEntry(*stuff)


@dataclass(frozen=True)
class Analysis:
    """Numbers and cross-reference labels of one block sequence, independent of page layout."""

    headings: Dict[int, Optional[str]]
    figures: Dict[int, int]
    tables: Dict[int, int]
    refs: Dict[str, str]
    figure_entries: Tuple[Tuple[int, str], ...]
    table_entries: Tuple[Tuple[int, str], ...]


def analyze(blocks: Sequence[Block], numbered: bool, known: Optional[Dict[str, str]] = None) -> Analysis:
    """Number headings, figures and tables and collect the labels of every id.

    known holds ids that are already taken elsewhere; a repeated id is an error.
    """
    counters = [0, 0, 0]
    figure = table = 0
    headings: Dict[int, Optional[str]] = {}
    figures: Dict[int, int] = {}
    tables: Dict[int, int] = {}
    refs: Dict[str, str] = {}
    taken = dict(known or {})
    figure_entries: List[Tuple[int, str]] = []
    table_entries: List[Tuple[int, str]] = []

    def register(ref_id: Optional[str], label: str, line: int) -> None:
        if ref_id is None:
            return
        if ref_id in taken or ref_id in refs:
            raise ContentError(f"the id '{ref_id}' is used more than once", line)
        refs[ref_id] = label

    for position, block in enumerate(blocks):
        if isinstance(block, Heading):
            number: Optional[str] = None
            if numbered and block.numbered:
                counters[block.level - 1] += 1
                for deeper in range(block.level, 3):
                    counters[deeper] = 0
                number = ".".join(str(n) for n in counters[: block.level])
            headings[position] = number
            if number:
                label = f"Chapter{NBSP}{number}" if block.level == 1 else f"Section{NBSP}{number}"
            else:
                label = "\u201c" + to_plain(block.text, block.line) + "\u201d"
            register(block.ref_id, label, block.line)
        elif isinstance(block, (ImageBlock, DiagramBlock)) and block.caption:
            figure += 1
            figures[position] = figure
            figure_entries.append((figure, block.caption))
            register(block.ref_id, f"Figure{NBSP}{figure}", block.line)
        elif isinstance(block, TableBlock) and block.caption:
            table += 1
            tables[position] = table
            table_entries.append((table, block.caption))
            register(block.ref_id, f"Table{NBSP}{table}", block.line)
    return Analysis(headings, figures, tables, refs, tuple(figure_entries), tuple(table_entries))


def _roman(number: int) -> str:
    """Lowercase roman numeral of a positive integer (page labels of the front matter)."""
    result = ""
    for value, symbol in ((1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"),
                          (50, "l"), (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")):
        while number >= value:
            result += symbol
            number -= value
    return result


def page_label(page: int, body_start: Optional[int]) -> str:
    """Printed page label: roman numerals before the first chapter, then decimal from 1."""
    if body_start is None or body_start <= 1:
        return str(page)
    if page < body_start:
        return _roman(page)
    return str(page - body_start + 1)


class _Document(BaseDocTemplate):
    def __init__(
        self,
        target,
        meta: Meta,
        brand: Brand,
        styles: Styles,
        total_pages: Optional[int],
        header_map: Dict[int, str],
        body_start: Optional[int] = None,
    ) -> None:
        super().__init__(
            target,
            pagesize=(PAGE_WIDTH, PAGE_HEIGHT),
            leftMargin=MARGIN_LEFT,
            rightMargin=MARGIN_RIGHT,
            topMargin=MARGIN_TOP,
            bottomMargin=MARGIN_BOTTOM,
            title=meta.title,
            author=meta.author,
            subject=meta.audience,
            keywords=meta.keywords or "",
            creator="Azimi Publishing Engine",
            invariant=1,
            initialFontName="Body",
        )
        self.meta = meta
        self.brand = brand
        self.styles = styles
        self.total_pages = total_pages
        self.header_map = header_map
        self.known_body_start = body_start
        self.forced_pages: set = set()
        self.body_start_page: Optional[int] = None
        self._heading_count = 0
        self._chapter = ""
        self._start_chapter: Dict[int, str] = {}
        self._header_override: Dict[int, str] = {}
        self._count_on_page: Dict[int, int] = {}

        cover_frame = Frame(
            MARGIN_LEFT, MARGIN_BOTTOM, CONTENT_WIDTH, PAGE_HEIGHT - 40 * mm - MARGIN_BOTTOM,
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="cover",
        )
        body_frame = Frame(
            MARGIN_LEFT, MARGIN_BOTTOM, CONTENT_WIDTH, CONTENT_HEIGHT,
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="body",
        )
        self.addPageTemplates(
            [
                PageTemplate(id="Cover", frames=[cover_frame], onPage=self._draw_cover),
                PageTemplate(id="Front", frames=[body_frame], onPage=self._draw_front),
                PageTemplate(id="Body", frames=[body_frame], onPage=self._draw_page),
            ]
        )

    def beforeDocument(self):
        canvas = self.canv
        canvas.setViewerPreference("DisplayDocTitle", "true")
        canvas.setProducer(f"Azimi Publishing Engine {__version__}")
        canvas.showOutline()
        start = self.known_body_start
        if start is not None and start > 1:
            canvas.addPageLabel(0, style="ROMAN_LOWER", start=1)
            canvas.addPageLabel(start - 1, style="ARABIC", start=1)
        else:
            canvas.addPageLabel(0, style="ARABIC", start=1)

    def handle_documentBegin(self):
        self._heading_count = 0
        self._chapter = ""
        self._start_chapter = {}
        self._header_override = {}
        self._count_on_page = {}
        self.forced_pages = set()
        self.body_start_page = None
        super().handle_documentBegin()

    def afterFlowable(self, flowable):
        page = self.page
        if isinstance(flowable, ForcedBreak):
            # A ForcedBreak ends the current page and starts a new one.
            # When chapter_pages is enabled, both the chapter-end page
            # (which may hold only a KEY POINT summary) and the chapter-start
            # page (which holds only the heading and objectives) are structural
            # boundaries exempt from the A7 fill check.
            self.forced_pages.add(page)
            if self.meta.chapter_pages:
                self.forced_pages.add(page + 1)
            return
        self._count_on_page[page] = self._count_on_page.get(page, 0) + 1
        self._start_chapter.setdefault(page, self._chapter)
        entry = getattr(flowable, "list_entry", None)
        if entry is not None:
            kind, text, key = entry
            self.canv.bookmarkPage(key)
            self.notify(kind, (0, text, page, key))
        if isinstance(flowable, HeadingParagraph):
            if self.body_start_page is None:
                self.body_start_page = page
            self._heading_count += 1
            key = f"heading-{self._heading_count}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(flowable.plain, key, level=flowable.level - 1, closed=False)
            if flowable.level <= 2:
                self.notify("TOCEntry", (flowable.level - 1, flowable.plain, self.page, key))
            if flowable.level == 1:
                self._chapter = flowable.plain
                if self._count_on_page[page] <= 3:
                    self._header_override[page] = flowable.plain

    @property
    def header_map_next(self) -> Dict[int, str]:
        """Running header title of every page, as measured during the latest pass."""
        return {
            page: self._header_override.get(page) or chapter
            for page, chapter in self._start_chapter.items()
        }

    @property
    def _year(self) -> str:
        return self.meta.date.split()[-1]

    def _footer(self, canvas, doc, with_page: bool = True) -> None:
        canvas.setFont("Body", 8.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(
            MARGIN_LEFT, 12 * mm,
            f"{self.brand.display_name}  |  Version {self.meta.version}  |  {self.meta.date}",
        )
        if with_page:
            start = self.known_body_start
            label = f"Page {page_label(doc.page, start)}"
            if self.total_pages and start is not None and doc.page >= start:
                label += f" of {self.total_pages - start + 1}"
            canvas.drawRightString(PAGE_WIDTH - MARGIN_RIGHT, 12 * mm, label)

    def _draw_cover(self, canvas, doc):
        canvas.saveState()
        canvas.setFillColor(self.styles.primary)
        canvas.rect(0, PAGE_HEIGHT - 14 * mm, PAGE_WIDTH, 14 * mm, stroke=0, fill=1)
        canvas.setFillColor(self.styles.accent)
        canvas.rect(0, PAGE_HEIGHT - 17 * mm, PAGE_WIDTH, 3 * mm, stroke=0, fill=1)
        canvas.setFillColor(MUTED)
        canvas.setFont("Body", 8.5)
        canvas.drawString(
            MARGIN_LEFT, 12 * mm, f"Copyright (c) {self._year} {self.meta.author}. All rights reserved."
        )
        canvas.drawRightString(PAGE_WIDTH - MARGIN_RIGHT, 12 * mm, f"Version {self.meta.version}  |  {self.meta.date}")
        canvas.restoreState()

    def _draw_front(self, canvas, doc):
        canvas.saveState()
        canvas.setFillColor(self.styles.accent)
        canvas.rect(MARGIN_LEFT, PAGE_HEIGHT - 14 * mm, 18 * mm, 1.2 * mm, stroke=0, fill=1)
        self._footer(canvas, doc)
        canvas.restoreState()

    def _draw_page(self, canvas, doc):
        canvas.saveState()
        top = PAGE_HEIGHT - 14 * mm
        canvas.setFont("Body", 8.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(MARGIN_LEFT, top, self.meta.title)
        chapter = self.header_map.get(doc.page) or self.brand.display_name
        canvas.drawRightString(PAGE_WIDTH - MARGIN_RIGHT, top, chapter)
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN_LEFT, top - 2.6 * mm, PAGE_WIDTH - MARGIN_RIGHT, top - 2.6 * mm)
        canvas.setFillColor(self.styles.accent)
        canvas.rect(MARGIN_LEFT, top - 3.2 * mm, 18 * mm, 1.2 * mm, stroke=0, fill=1)
        self._footer(canvas, doc)
        canvas.restoreState()


def _wrap_with_classes(text: str, classes: Sequence[str], limit: int) -> List[Tuple[str, List[str]]]:
    """Wrap one code line at limit characters, keeping the class letter of every character."""
    if len(text) <= limit:
        return [(text, list(classes))]
    pieces: List[Tuple[str, List[str]]] = []
    position = 0
    first = True
    while position < len(text):
        remaining = text[position:]
        width = limit if first else limit - len(CONTINUATION_INDENT)
        if len(remaining) <= width:
            head_length, advance = len(remaining), len(remaining)
        else:
            cut = remaining.rfind(" ", 0, width + 1)
            if cut > width // 3 and remaining[:cut].strip():
                head_length, advance = cut, cut + 1
            else:
                head_length, advance = width, width
        piece = remaining[:head_length].rstrip()
        piece_classes = list(classes[position:position + len(piece)])
        if not first:
            piece = CONTINUATION_INDENT + piece
            piece_classes = [PLAIN] * len(CONTINUATION_INDENT) + piece_classes
        pieces.append((piece, piece_classes))
        position += advance
        first = False
    return pieces


def _code_flowables(block: Code, styles: Styles) -> List:
    language = normalize_language(block.language)
    lines = [line.expandtabs(4).rstrip() for line in block.lines] or [""]
    for text in lines:
        check_glyphs(text, "Mono", block.line)

    numbered = language in NUMBERED_LANGUAGES and len(lines) >= 4
    char_width = pdfmetrics.stringWidth("M", "Mono", CODE_SIZE)
    digits = len(str(len(lines)))
    gutter_width = (digits + 1) * char_width + 12 if numbered else 0.0
    available = CONTENT_WIDTH - CODE_PADDING_LEFT - CODE_PADDING_RIGHT - gutter_width
    limit = max(20, int(available // char_width))

    rows: List[Tuple[Optional[int], str, List[str]]] = []
    for number, (text, line_classes) in enumerate(zip(lines, classify(lines, language)), start=1):
        for index, (piece, piece_classes) in enumerate(_wrap_with_classes(text, line_classes, limit)):
            rows.append((number if index == 0 else None, piece, piece_classes))

    chunks = [rows[i:i + CODE_CHUNK_LINES] for i in range(0, len(rows), CODE_CHUNK_LINES)]
    if len(chunks) > 1 and len(chunks[-1]) < MIN_LAST_CHUNK:
        last_chunk = chunks.pop()
        chunks[-1] = chunks[-1] + last_chunk
    tables: List[Table] = []
    for index, chunk in enumerate(chunks):
        markup = "\n".join(highlight_markup(piece, piece_classes, CODE_COLORS) for _, piece, piece_classes in chunk)
        code_cell = XPreformatted(markup, styles.code)
        top = CODE_PADDING_VERTICAL if index == 0 else 0
        bottom = CODE_PADDING_VERTICAL if index == len(chunks) - 1 else 0
        if numbered:
            numbers = "\n".join(f"{number:>{digits}}" if number else "" for number, _, _ in chunk)
            table = Table(
                [[XPreformatted(numbers, styles.code_number), code_cell]],
                colWidths=[gutter_width, CONTENT_WIDTH - gutter_width],
                hAlign="LEFT",
            )
            commands = [
                ("BACKGROUND", (0, 0), (0, -1), GUTTER_BACKGROUND),
                ("BACKGROUND", (1, 0), (1, -1), CODE_BACKGROUND),
                ("LEFTPADDING", (0, 0), (0, -1), 8),
                ("RIGHTPADDING", (0, 0), (0, -1), 6),
                ("LEFTPADDING", (1, 0), (1, -1), 10),
                ("RIGHTPADDING", (1, 0), (1, -1), CODE_PADDING_RIGHT),
                ("LINEAFTER", (0, 0), (0, -1), 0.5, RULE),
            ]
        else:
            table = Table([[code_cell]], colWidths=[CONTENT_WIDTH], hAlign="LEFT")
            commands = [
                ("BACKGROUND", (0, 0), (-1, -1), CODE_BACKGROUND),
                ("LEFTPADDING", (0, 0), (-1, -1), CODE_PADDING_LEFT),
                ("RIGHTPADDING", (0, 0), (-1, -1), CODE_PADDING_RIGHT),
            ]
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "Mono"),
                    ("LINEBEFORE", (0, 0), (0, -1), 2.5, styles.accent),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), top),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), bottom),
                ]
                + commands
            )
        )
        tables.append(table)
    label = Paragraph(to_markup(block.language.upper()), styles.code_label)
    return [label] + tables + [Spacer(1, 12)]


TABLE_FONT_SIZE = 9.5
TABLE_CELL_PADDING = 12


def _column_widths(header: Sequence[str], rows: Sequence[Sequence[str]]) -> List[float]:
    """Proportional widths that never break a word in the middle of a column."""
    count = len(header)
    weights: List[float] = []
    minimums: List[float] = []
    for column in range(count):
        texts = [to_plain(header[column])] + [to_plain(row[column]) for row in rows]
        longest = max(len(text) for text in texts)
        weights.append(min(max(longest, 6), 42) + 4)
        longest_word = max(
            (pdfmetrics.stringWidth(word, "Body-Bold", TABLE_FONT_SIZE) for text in texts for word in text.split()),
            default=0.0,
        )
        minimums.append(longest_word + TABLE_CELL_PADDING + 2)

    if sum(minimums) >= CONTENT_WIDTH:
        total_minimum = float(sum(minimums))
        return [CONTENT_WIDTH * value / total_minimum for value in minimums]

    total_weight = float(sum(weights))
    widths = [CONTENT_WIDTH * weight / total_weight for weight in weights]
    for _ in range(count):
        short = [i for i in range(count) if widths[i] < minimums[i]]
        if not short:
            break
        deficit = sum(minimums[i] - widths[i] for i in short)
        for i in short:
            widths[i] = minimums[i]
        donors = [i for i in range(count) if i not in short and widths[i] > minimums[i]]
        spare = sum(widths[i] - minimums[i] for i in donors)
        for i in donors:
            widths[i] -= deficit * (widths[i] - minimums[i]) / spare
    return widths


def _table_flowable(block: TableBlock, styles: Styles, refs: Dict[str, str]) -> Table:
    for cell in list(block.header) + [c for row in block.rows for c in row]:
        check_glyphs(cell, "Body", block.line)
    header_styles = [styles.aligned(styles.table_header, a) for a in block.align]
    cell_styles = [styles.aligned(styles.table_cell, a) for a in block.align]
    data = [[Paragraph(to_markup(text, block.line, refs), header_styles[i]) for i, text in enumerate(block.header)]]
    for row in block.rows:
        data.append([Paragraph(to_markup(text, block.line, refs), cell_styles[i]) for i, text in enumerate(row)])
    table = Table(data, colWidths=_column_widths(block.header, block.rows), repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Body"),
                ("BACKGROUND", (0, 0), (-1, 0), styles.primary),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ZEBRA]),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, RULE),
                ("BOX", (0, 0), (-1, -1), 0.5, RULE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


CALLOUT_LABELS = {
    "NOTE": "NOTE",
    "WARNING": "WARNING",
    "TIP": "TIP",
    "KEY": "KEY POINT",
    "CHECKPOINT": "CHECKPOINT",
    "OBJECTIVES": "LEARNING OBJECTIVES",
    "EXAMPLE": "WORKED EXAMPLE",
    "PITFALL": "COMMON PITFALL",
}
CALLOUT_PART_SEPARATOR = " || "


def callout_colors(styles: Styles) -> Dict[str, colors.Color]:
    return {
        "NOTE": styles.accent,
        "WARNING": WARNING,
        "TIP": TIP,
        "KEY": styles.primary,
        "CHECKPOINT": CHECKPOINT,
        "OBJECTIVES": styles.primary,
        "EXAMPLE": EXAMPLE,
        "PITFALL": PITFALL,
    }


def _callout_flowable(block: Callout, styles: Styles, refs: Dict[str, str]) -> Table:
    check_glyphs(block.text, "Body", block.line)
    color = callout_colors(styles)[block.kind]
    label = CALLOUT_LABELS[block.kind]
    tint = mix_with_white(color, 0.92)
    label_style = ParagraphStyle(
        f"{block.kind}Label", parent=styles.callout_label, textColor=ensure_contrast(color, tint)
    )
    parts = [part.strip() for part in block.text.split(CALLOUT_PART_SEPARATOR) if part.strip()]
    content = [Paragraph(label, label_style)]
    for part in parts:
        markup = to_markup(part, block.line, refs)
        if block.kind == "OBJECTIVES":
            content.append(Paragraph(markup, styles.callout_item, bulletText="\u2022"))
        else:
            content.append(Paragraph(markup, styles.callout_text))
    table = Table([[content]], colWidths=[CONTENT_WIDTH], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Body"),
                ("BACKGROUND", (0, 0), (-1, -1), mix_with_white(color, 0.92)),
                ("LINEBEFORE", (0, 0), (0, -1), 3, color),
                ("LEFTPADDING", (0, 0), (-1, -1), 11),
                ("RIGHTPADDING", (0, 0), (-1, -1), 11),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ]
        )
    )
    return table


def _scaled_size(pixel_width: int, pixel_height: int, dpi: float, max_width: float, max_height: float):
    width = pixel_width * 72.0 / dpi
    height = pixel_height * 72.0 / dpi
    scale = min(1.0, max_width / width, max_height / height)
    return width * scale, height * scale


class Figure(Flowable):
    """An image with an optional caption that shrinks a little to fit the space that is left.

    The image is never reduced below MIN_FIGURE_SCALE of its normal size; if it would not fit even
    then, the whole figure moves to the next page.
    """

    def __init__(
        self, source, width: float, height: float, caption: Optional[Paragraph], entry=None
    ) -> None:
        super().__init__()
        self.list_entry = entry
        self._source = source
        self._width = width
        self._height = height
        self._caption = caption
        self._draw_width = width
        self._draw_height = height
        self._caption_height = 0.0
        self.hAlign = "CENTER"

    def wrap(self, available_width, available_height):
        self._caption_height = 0.0
        gap = 0.0
        if self._caption is not None:
            _, self._caption_height = self._caption.wrap(available_width, available_height)
            gap = FIGURE_CAPTION_GAP
        self._reserved = FIGURE_SPACE_AFTER + self._caption_height + gap
        room = available_height - self._reserved
        scale = 1.0
        if room < self._height:
            scale = max(MIN_FIGURE_SCALE, room / self._height) if room > 0 else MIN_FIGURE_SCALE
        self._draw_width = self._width * scale
        self._draw_height = self._height * scale
        self._box_width = available_width
        return available_width, self._draw_height + self._reserved

    def draw(self):
        canvas = self.canv
        left = (self._box_width - self._draw_width) / 2
        image_bottom = FIGURE_SPACE_AFTER + self._caption_height + (FIGURE_CAPTION_GAP if self._caption is not None else 0.0)
        canvas.drawImage(ImageReader(self._source), left, image_bottom, self._draw_width, self._draw_height, mask="auto")
        if self._caption is not None:
            self._caption.drawOn(canvas, 0, FIGURE_SPACE_AFTER)


def _figure_size(block: ImageBlock, doc_dir: Path) -> Tuple[object, float, float]:
    try:
        path = resolve_inside(doc_dir, block.path)
    except Exception as exc:
        raise ContentError(f"image path is not allowed: {block.path}", block.line) from exc
    if not path.is_file():
        raise ContentError(f"image file not found: {block.path}", block.line)
    try:
        image = PILImage.open(path)
        image.load()
        exif = image.getexif()
        orientation = exif.get(0x0112, 1) if exif else 1
        if orientation != 1:
            oriented = ImageOps.exif_transpose(image)
            source = oriented
            width_px, height_px = oriented.size
        else:
            source = str(path)
            width_px, height_px = image.size
        raw_dpi = image.info.get("dpi", (DEFAULT_IMAGE_DPI, DEFAULT_IMAGE_DPI))[0]
    except Exception as exc:
        raise ContentError(f"image cannot be read: {block.path}", block.line) from exc
    if width_px * height_px > MAX_PIXELS:
        raise ContentError(f"image is too large: {block.path}", block.line)
    dpi = float(raw_dpi) if raw_dpi and float(raw_dpi) >= 36 else DEFAULT_IMAGE_DPI
    width, height = _scaled_size(width_px, height_px, dpi, CONTENT_WIDTH, MAX_IMAGE_HEIGHT)
    IMAGE_DPI.append(width_px / (width / 72.0))
    return source, width, height


def short_caption(text: str) -> str:
    """The first sentence of a caption, used in the lists of figures and tables."""
    cut = text.find(". ")
    return text if cut == -1 else text[: cut + 1]


def _caption_markup(label: str, number: int, text: str, line: int, refs: Dict[str, str], ref_id: Optional[str]) -> str:
    check_glyphs(text, "Body", line)
    anchor = f'<a name="{ref_id}"/>' if ref_id else ""
    return f"{anchor}{label}{NBSP}{number}. {to_markup(text, line, refs)}"


def _image_flowable(
    block: ImageBlock, doc_dir: Path, styles: Styles, number: Optional[int], used: List[str], refs: Dict[str, str]
) -> List:
    source, width, height = _figure_size(block, doc_dir)
    used.append(block.path)
    caption = None
    entry = None
    if block.caption and number is not None:
        markup = _caption_markup("Figure", number, block.caption, block.line, refs, block.ref_id)
        caption = Paragraph(markup, styles.caption)
        entry = ("LOFEntry", f"Figure{NBSP}{number}. {short_caption(to_plain(block.caption, block.line))}", f"list-figure-{number}")
    return [Figure(source, width, height, caption, entry)]


def _diagram_flowable(
    block: DiagramBlock, styles: Styles, number: Optional[int], refs: Dict[str, str]
) -> List:
    layout = build_layout(block.spec, styles.primary, styles.accent, block.line)
    caption = None
    entry = None
    if block.caption and number is not None:
        markup = _caption_markup("Figure", number, block.caption, block.line, refs, block.ref_id)
        caption = Paragraph(markup, styles.caption)
        entry = ("LOFEntry", f"Figure{NBSP}{number}. {short_caption(to_plain(block.caption, block.line))}", f"list-figure-{number}")
    flowable = DiagramFlowable(layout, caption, block.caption or "")
    flowable.list_entry = entry
    return [flowable]


def _table_caption(block: TableBlock, styles: Styles, number: int, refs: Dict[str, str]) -> Paragraph:
    markup = _caption_markup("Table", number, block.caption or "", block.line, refs, block.ref_id)
    return CaptionParagraph(
        markup, styles.table_caption, f"Table{NBSP}{number}. {short_caption(to_plain(block.caption or '', block.line))}",
        f"list-table-{number}",
    )


def _list_flowable(block, styles: Styles, numbered: bool, refs: Dict[str, str]) -> List:
    for item in block.items:
        check_glyphs(item, "Body", block.line)
    items = [
        ListItem(Paragraph(to_markup(text, block.line, refs), styles.list_item), leftIndent=18) for text in block.items
    ]
    common = dict(
        leftIndent=18, bulletFontName="Body-Bold" if numbered else "Body", bulletFontSize=11,
        bulletColor=styles.accent,
    )
    if numbered:
        flow = ListFlowable(items, bulletType="1", bulletFormat="%s.", start=1, **common)
    else:
        flow = ListFlowable(items, bulletType="bullet", start="•", **common)
    return [flow, Spacer(1, 4)]


def _cover(meta: Meta, brand: Brand, styles: Styles) -> List:
    aspect = brand.logo_size[0] / float(brand.logo_size[1])
    logo_width = min(CONTENT_WIDTH, 40 * mm * aspect)
    logo_height = logo_width / aspect
    logo = Image(str(brand.logo_path), width=logo_width, height=logo_height, mask="auto")
    logo.hAlign = "LEFT"
    story: List = [Spacer(1, 10 * mm), logo]
    if brand.tagline:
        story.append(Paragraph(to_markup(brand.tagline), styles.cover_tagline))
    story.append(Spacer(1, 26 * mm))

    title_style = ParagraphStyle("CoverTitleOnPanel", parent=styles.cover_title, textColor=styles.on_primary)
    subtitle_color = mix_with_white(styles.primary, 0.72) if styles.on_primary == colors.white else MUTED
    subtitle_style = ParagraphStyle(
        "CoverSubtitleOnPanel", parent=styles.cover_subtitle, textColor=subtitle_color, spaceAfter=0,
    )
    panel = [Paragraph(to_markup(meta.title), title_style)]
    if meta.subtitle:
        panel.append(Paragraph(to_markup(meta.subtitle), subtitle_style))
    panel_table = Table([[panel]], colWidths=[CONTENT_WIDTH], hAlign="LEFT")
    panel_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Body"),
                ("BACKGROUND", (0, 0), (-1, -1), styles.primary),
                ("LINEBELOW", (0, 0), (-1, -1), 4, styles.accent),
                ("LEFTPADDING", (0, 0), (-1, -1), 20),
                ("RIGHTPADDING", (0, 0), (-1, -1), 20),
                ("TOPPADDING", (0, 0), (-1, -1), 22),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 22),
            ]
        )
    )
    story.append(panel_table)
    story.append(Spacer(1, 12 * mm))

    def cell(label: str, value: str) -> List:
        return [Paragraph(label, styles.cover_meta_label), Paragraph(to_markup(value), styles.cover_meta)]

    grid = Table(
        [
            [cell("AUTHOR", meta.author), cell("VERSION", meta.version)],
            [cell("AUDIENCE", meta.audience), cell("DATE", meta.date)],
        ],
        colWidths=[CONTENT_WIDTH * 0.64, CONTENT_WIDTH * 0.36],
        hAlign="LEFT",
    )
    grid.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Body"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(grid)
    return story


def _imprint(meta: Meta, brand: Brand, styles: Styles) -> List:
    year = meta.date.split()[-1]
    story: List = [Paragraph(to_markup(meta.title), styles.imprint_title)]
    if meta.subtitle:
        story.append(Paragraph(to_markup(meta.subtitle), styles.imprint_subtitle))
    story.append(HRFlowable(width="100%", thickness=0.5, color=RULE, spaceBefore=2, spaceAfter=4))
    entries = [
        ("EDITION", f"Version {meta.version}, {meta.date}"),
        ("AUTHOR", meta.author),
        ("PUBLISHER", brand.display_name),
        ("INTENDED READERS", meta.audience),
    ]
    for label, value in entries:
        story.append(Paragraph(label, styles.imprint_label))
        story.append(Paragraph(to_markup(value), styles.imprint_text))
    story.append(Spacer(1, 15 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=RULE, spaceBefore=0, spaceAfter=4))
    closing = [
        ("COPYRIGHT", f"Copyright (c) {year} {meta.author}. All rights reserved."),
        (
            "RIGHTS",
            "No part of this document may be reproduced, stored or transmitted in any form without the prior "
            "written permission of the publisher, except as stated in the Rights and License section at the "
            "end of this document.",
        ),
        (
            "PRODUCTION",
            f"Typeset with Azimi Publishing Engine {__version__}. Fonts: Carlito and Liberation Mono, "
            "licensed under the SIL Open Font License 1.1.",
        ),
    ]
    for label, value in closing:
        story.append(Paragraph(label, styles.imprint_label))
        story.append(Paragraph(to_markup(value), styles.imprint_text))
    return story


def _toc(styles: Styles, body_start: Optional[int]) -> TableOfContents:
    toc = TableOfContents()
    toc.formatter = lambda page: page_label(page, body_start)
    toc.levelStyles = [styles.toc1, styles.toc2]
    toc.dotsMinLevel = 0
    toc.tableStyle = TableStyle(
        [
            ("FONTNAME", (0, 0), (-1, -1), "Body"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]
    )
    return toc


def _inline_texts(block: Block) -> List[str]:
    texts: List[str] = []
    if isinstance(block, (Heading, ParagraphBlock)):
        texts.append(block.text)
    elif isinstance(block, Callout):
        texts.extend(part for part in block.text.split(CALLOUT_PART_SEPARATOR) if part.strip())
    elif isinstance(block, (BulletList, NumberedList)):
        texts.extend(block.items)
    elif isinstance(block, TableBlock):
        texts.extend(block.header)
        texts.extend(cell for row in block.rows for cell in row)
        if block.caption:
            texts.append(block.caption)
    elif isinstance(block, (ImageBlock, DiagramBlock)) and block.caption:
        texts.append(block.caption)
    return texts


def validate_inline(blocks: Sequence[Block], refs: Optional[Dict[str, str]] = None) -> None:
    """Raise ContentError for the first block whose inline markers or cross-references are not valid."""
    for block in blocks:
        for text in _inline_texts(block):
            if isinstance(block, Heading) and reference_ids(text):
                raise ContentError("a heading cannot contain a cross-reference", block.line)
            to_markup(text, block.line, refs)


def _break_page(story: List) -> None:
    """Append an intentional page break unless the story already ends with one."""
    if story and isinstance(story[-1], (PageBreak, CondPageBreak)):
        return
    story.append(ForcedBreak())


def _heading_markup(block: Heading, number: Optional[str]) -> Tuple[str, str]:
    markup = to_markup(block.text, block.line)
    plain = to_plain(block.text, block.line)
    anchor = f'<a name="{block.ref_id}"/>' if block.ref_id else ""
    if number:
        return f"{anchor}{number}&nbsp;&nbsp;{markup}", f"{number}  {plain}"
    return f"{anchor}{markup}", plain


def _story(
    blocks: Sequence[Block],
    doc_dir: Path,
    styles: Styles,
    chapter_pages: bool,
    analysis: Analysis,
    refs: Dict[str, str],
) -> Tuple[List, List[str]]:
    story: List = []
    images: List[str] = []
    seen_h1 = False
    visual = (TableBlock, ImageBlock, DiagramBlock)

    for position, block in enumerate(blocks):
        following = blocks[position + 1] if position + 1 < len(blocks) else None
        if isinstance(block, Heading):
            check_glyphs(block.text, "Body", block.line)
            style = {1: styles.h1, 2: styles.h2, 3: styles.h3}[block.level]
            if block.level == 1:
                if seen_h1:
                    if chapter_pages:
                        _break_page(story)
                    elif not isinstance(story[-1], PageBreak):
                        story.append(CondPageBreak(CHAPTER_MIN_SPACE))
                seen_h1 = True
            second = blocks[position + 2] if position + 2 < len(blocks) else None
            if isinstance(following, visual):
                # A table or a figure may split or shrink, so the heading is not chained to it as one
                # unbreakable group; instead there must be room for the heading and the first rows.
                style = ParagraphStyle(f"{style.name}Free", parent=style, keepWithNext=0)
                if story and not isinstance(story[-1], (PageBreak, CondPageBreak)):
                    story.append(CondPageBreak(HEADING_TABLE_MIN_SPACE))
            elif isinstance(following, ParagraphBlock) and isinstance(second, visual):
                # The paragraph between the heading and the visual may not fit
                # alongside the heading.  Release keepWithNext and reduce spaceBefore
                # so the heading can stay on the current page even if the paragraph
                # spills over, preventing a large blank gap at the page bottom.
                style = ParagraphStyle(f"{style.name}Free", parent=style, keepWithNext=0)
            markup, plain = _heading_markup(block, analysis.headings.get(position))
            story.append(HeadingParagraph(markup, style, block.level, plain))
        elif isinstance(block, ParagraphBlock):
            check_glyphs(block.text, "Body", block.line)
            introduces = isinstance(following, Code) and len(block.text) <= KEEP_WITH_NEXT_MAX
            style = styles.body_keep if introduces else styles.body
            story.append(Paragraph(to_markup(block.text, block.line, refs), style))
        elif isinstance(block, BulletList):
            story.extend(_list_flowable(block, styles, False, refs))
        elif isinstance(block, NumberedList):
            story.extend(_list_flowable(block, styles, True, refs))
        elif isinstance(block, Code):
            story.extend(_code_flowables(block, styles))
        elif isinstance(block, TableBlock):
            number = analysis.tables.get(position)
            if number is not None:
                story.append(_table_caption(block, styles, number, refs))
            story.append(_table_flowable(block, styles, refs))
            story.append(Spacer(1, 12))
        elif isinstance(block, ImageBlock):
            story.extend(_image_flowable(block, doc_dir, styles, analysis.figures.get(position), images, refs))
        elif isinstance(block, DiagramBlock):
            story.extend(_diagram_flowable(block, styles, analysis.figures.get(position), refs))
        elif isinstance(block, Callout):
            story.append(_callout_flowable(block, styles, refs))
            story.append(Spacer(1, 12))
        elif isinstance(block, PageBreakBlock):
            _break_page(story)
        else:  # pragma: no cover - guarded by the parser's closed set of block types
            raise ContentError("unsupported block type", getattr(block, "line", None))
    return story, images


def _assemble(
    blocks: Sequence[Block],
    rights_blocks: Sequence[Block],
    meta: Meta,
    brand: Brand,
    doc_dir: Path,
    styles: Styles,
    body_analysis: Analysis,
    rights_analysis: Analysis,
    refs: Dict[str, str],
    body_start: Optional[int] = None,
) -> Tuple[List, List[str]]:
    body_story, images = _story(blocks, doc_dir, styles, meta.chapter_pages, body_analysis, refs)
    rights_story, _ = _story(rights_blocks, brand.rights_path.parent, styles, True, rights_analysis, refs)
    has_contents = any(isinstance(b, Heading) for b in list(blocks) + list(rights_blocks))

    story: List = _cover(meta, brand, styles)
    story.append(NextPageTemplate("Front"))
    story.append(ForcedBreak())
    story.extend(_imprint(meta, brand, styles))
    story.append(NextPageTemplate("Body"))
    story.append(ForcedBreak())
    if has_contents:
        story.append(Paragraph("Contents", styles.toc_title))
        story.append(_toc(styles, body_start))
        story.append(ForcedBreak())
    if body_analysis.figure_entries or body_analysis.table_entries:
        if body_analysis.figure_entries:
            story.append(Paragraph("List of Figures", styles.list_heading))
            story.append(_ListOf("LOFEntry", styles.list_entry, body_start))
        if body_analysis.table_entries:
            story.append(Paragraph("List of Tables", styles.list_heading))
            story.append(_ListOf("LOTEntry", styles.list_entry, body_start))
        story.append(ForcedBreak())
    story.extend(body_story)
    if rights_story:
        story.append(ForcedBreak())
        story.extend(rights_story)
    return story, images


def contrast_pairs(styles: Styles) -> Tuple[Tuple[str, float], ...]:
    """Contrast ratios of the text and background combinations the renderer uses."""
    pairs = [
        ("body text on white", contrast_ratio(styles.body.textColor, colors.white)),
        ("muted text on white", contrast_ratio(MUTED, colors.white)),
        ("link on white", contrast_ratio(colors.HexColor(LINK_COLOR), colors.white)),
        ("heading on white", contrast_ratio(styles.primary, colors.white)),
        ("label on white", contrast_ratio(styles.callout_label.textColor, colors.white)),
        ("text on primary", contrast_ratio(styles.on_primary, styles.primary)),
    ]
    for kind, color in callout_colors(styles).items():
        tint = mix_with_white(color, 0.92)
        pairs.append((f"{kind.lower()} label", contrast_ratio(ensure_contrast(color, tint), tint)))
    return tuple((name, round(ratio, 2)) for name, ratio in pairs)


def render_document(
    blocks: Sequence[Block],
    meta: Meta,
    brand: Brand,
    doc_dir: Path,
    rights_blocks: Sequence[Block],
) -> RenderResult:
    """Render blocks to PDF bytes. Fonts must already be registered."""
    for text in (
        meta.title, meta.subtitle or "", meta.author, meta.audience, meta.date, brand.display_name, brand.tagline or "",
    ):
        check_glyphs(text, "Body")

    styles = build_styles(brand)
    IMAGE_DPI.clear()
    body_analysis = analyze(blocks, meta.numbered)
    rights_analysis = analyze(rights_blocks, False, body_analysis.refs)
    refs = {**body_analysis.refs, **rights_analysis.refs}
    validate_inline(blocks, refs)
    validate_inline(rights_blocks, refs)

    previous_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    previous_lang = rl_config.documentLang
    previous_font = rl_config.canvas_basefontname
    os.environ["SOURCE_DATE_EPOCH"] = str(meta.epoch)
    rl_config.documentLang = meta.language
    rl_config.canvas_basefontname = "Body"
    try:
        total: Optional[int] = None
        header_map: Dict[int, str] = {}
        body_start: Optional[int] = None
        for _attempt in range(MAX_LAYOUT_ATTEMPTS):
            story, images = _assemble(
                blocks, rights_blocks, meta, brand, doc_dir, styles, body_analysis, rights_analysis, refs,
                body_start,
            )
            buffer = io.BytesIO()
            document = _Document(buffer, meta, brand, styles, total, header_map, body_start)
            document.multiBuild(story, maxPasses=6)
            settled = (
                document.page == total
                and document.header_map_next == header_map
                and document.body_start_page == body_start
            )
            total, header_map = document.page, document.header_map_next
            body_start = document.body_start_page
            if settled:
                break
        else:
            raise EngineError("page layout did not settle; the document is too unstable to typeset")
    finally:
        rl_config.documentLang = previous_lang
        rl_config.canvas_basefontname = previous_font
        if previous_epoch is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = previous_epoch

    body_start = document.body_start_page or (document.page + 1)
    pdf_bytes = apply_xmp(buffer.getvalue(), meta, brand, f"Azimi Publishing Engine {__version__}")
    dpi = min(IMAGE_DPI) if IMAGE_DPI else None
    exempt = {page for page in range(1, body_start)} | set(document.forced_pages) | {document.page}
    return RenderResult(
        pdf=pdf_bytes, pages=document.page, images=tuple(images), exempt_pages=tuple(sorted(exempt)),
        min_image_dpi=dpi, contrast=contrast_pairs(styles),
    )

