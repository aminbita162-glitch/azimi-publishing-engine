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
from typing import Dict, List, Sequence, Tuple

from PIL import Image as PILImage
from reportlab import rl_config
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import (
    BaseDocTemplate,
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
    Preformatted,
    Spacer,
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
    Heading,
    Image as ImageBlock,
    NumberedList,
    PageBreak as PageBreakBlock,
    Paragraph as ParagraphBlock,
    Table as TableBlock,
)
from ..errors import ConfigError, ContentError
from ..paths import resolve_inside
from ..schemas.meta import Meta
from .fonts import check_glyphs
from .inline import to_markup, to_plain
from .styles import (
    CODE_BACKGROUND,
    CODE_CHUNK_LINES,
    CODE_PADDING_LEFT,
    CODE_PADDING_RIGHT,
    CODE_PADDING_VERTICAL,
    CODE_SIZE,
    CONTENT_HEIGHT,
    CONTENT_WIDTH,
    MARGIN_BOTTOM,
    MARGIN_LEFT,
    MARGIN_RIGHT,
    MARGIN_TOP,
    MUTED,
    PAGE_HEIGHT,
    PAGE_WIDTH,
    RULE,
    WARNING,
    ZEBRA,
    Styles,
    build_styles,
    mix_with_white,
)

DEFAULT_IMAGE_DPI = 150.0
MAX_IMAGE_HEIGHT = CONTENT_HEIGHT * 0.6
MAX_PIXELS = 40_000_000
CONTINUATION_INDENT = "  "
KEEP_WITH_NEXT_MAX = 240


@dataclass(frozen=True)
class RenderResult:
    """Output of render_document."""

    pdf: bytes
    pages: int
    images: Tuple[str, ...]


class HeadingParagraph(Paragraph):
    """A heading that carries its level and plain text for outline and contents."""

    def __init__(self, markup: str, style, level: int, plain: str) -> None:
        super().__init__(markup, style)
        self.level = level
        self.plain = plain


class _Document(BaseDocTemplate):
    def __init__(self, target, meta: Meta, brand: Brand, styles: Styles) -> None:
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
            creator="Azimi Publishing Engine",
            invariant=1,
            initialFontName="Body",
        )
        self.meta = meta
        self.brand = brand
        self.styles = styles
        self._heading_count = 0

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
                PageTemplate(id="Body", frames=[body_frame], onPage=self._draw_page),
            ]
        )

    def handle_documentBegin(self):
        self._heading_count = 0
        super().handle_documentBegin()

    def afterFlowable(self, flowable):
        if isinstance(flowable, HeadingParagraph):
            self._heading_count += 1
            key = f"heading-{self._heading_count}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(flowable.plain, key, level=flowable.level - 1, closed=False)
            if flowable.level <= 2:
                self.notify("TOCEntry", (flowable.level - 1, flowable.plain, self.page, key))

    def _draw_cover(self, canvas, doc):
        canvas.saveState()
        canvas.setFillColor(self.styles.primary)
        canvas.rect(0, PAGE_HEIGHT - 14 * mm, PAGE_WIDTH, 14 * mm, stroke=0, fill=1)
        canvas.setFillColor(self.styles.accent)
        canvas.rect(0, PAGE_HEIGHT - 17 * mm, PAGE_WIDTH, 3 * mm, stroke=0, fill=1)
        canvas.setFillColor(MUTED)
        canvas.setFont("Body", 8.5)
        canvas.drawString(MARGIN_LEFT, 12 * mm, self.brand.display_name)
        canvas.drawRightString(PAGE_WIDTH - MARGIN_RIGHT, 12 * mm, f"Version {self.meta.version}")
        canvas.restoreState()

    def _draw_page(self, canvas, doc):
        canvas.saveState()
        top = PAGE_HEIGHT - 14 * mm
        canvas.setFont("Body", 8.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(MARGIN_LEFT, top, self.meta.title)
        canvas.drawRightString(PAGE_WIDTH - MARGIN_RIGHT, top, self.brand.display_name)
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN_LEFT, top - 2.6 * mm, PAGE_WIDTH - MARGIN_RIGHT, top - 2.6 * mm)
        canvas.setFillColor(self.styles.accent)
        canvas.rect(MARGIN_LEFT, top - 3.2 * mm, 18 * mm, 1.2 * mm, stroke=0, fill=1)
        canvas.setFillColor(MUTED)
        canvas.drawString(MARGIN_LEFT, 12 * mm, f"Version {self.meta.version}  |  {self.meta.date}")
        canvas.drawRightString(PAGE_WIDTH - MARGIN_RIGHT, 12 * mm, f"Page {doc.page}")
        canvas.restoreState()


def _split_at_word(text: str, limit: int) -> Tuple[str, str]:
    """Split text into a head of at most limit characters and the rest, preferring a space."""
    if len(text) <= limit:
        return text, ""
    cut = text.rfind(" ", 0, limit + 1)
    if cut > limit // 2 and text[:cut].strip():
        return text[:cut].rstrip(), text[cut + 1:]
    return text[:limit], text[limit:]


def _wrap_code_line(line: str, limit: int) -> List[str]:
    """Wrap one code line at limit characters; continuation lines are indented."""
    line = line.expandtabs(4).rstrip()
    if len(line) <= limit:
        return [line]
    head, rest = _split_at_word(line, limit)
    parts = [head]
    width = limit - len(CONTINUATION_INDENT)
    while rest:
        head, rest = _split_at_word(rest, width)
        parts.append(CONTINUATION_INDENT + head)
    return parts


def _code_flowables(block: Code, styles: Styles) -> List:
    available = CONTENT_WIDTH - CODE_PADDING_LEFT - CODE_PADDING_RIGHT
    char_width = pdfmetrics.stringWidth("M", "Mono", CODE_SIZE)
    limit = max(20, int(available // char_width))
    for text in block.lines:
        check_glyphs(text.expandtabs(4), "Mono", block.line)
    wrapped: List[str] = []
    for text in block.lines:
        wrapped.extend(_wrap_code_line(text, limit))
    if not wrapped:
        wrapped = [" "]
    chunks = [wrapped[i:i + CODE_CHUNK_LINES] for i in range(0, len(wrapped), CODE_CHUNK_LINES)]
    tables: List[Table] = []
    for index, chunk in enumerate(chunks):
        table = Table([[Preformatted("\n".join(chunk), styles.code)]], colWidths=[CONTENT_WIDTH], hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "Mono"),
                    ("BACKGROUND", (0, 0), (-1, -1), CODE_BACKGROUND),
                    ("LINEBEFORE", (0, 0), (0, -1), 2.5, styles.accent),
                    ("LEFTPADDING", (0, 0), (-1, -1), CODE_PADDING_LEFT),
                    ("RIGHTPADDING", (0, 0), (-1, -1), CODE_PADDING_RIGHT),
                    ("TOPPADDING", (0, 0), (-1, -1), CODE_PADDING_VERTICAL if index == 0 else 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), CODE_PADDING_VERTICAL if index == len(chunks) - 1 else 0),
                ]
            )
        )
        tables.append(table)
    label = Paragraph(to_markup(block.language.upper()), styles.code_label)
    return [KeepTogether([label, tables[0]])] + tables[1:] + [Spacer(1, 12)]


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


def _table_flowable(block: TableBlock, styles: Styles) -> Table:
    for cell in list(block.header) + [c for row in block.rows for c in row]:
        check_glyphs(cell, "Body", block.line)
    header_styles = [styles.aligned(styles.table_header, a) for a in block.align]
    cell_styles = [styles.aligned(styles.table_cell, a) for a in block.align]
    data = [[Paragraph(to_markup(text, block.line), header_styles[i]) for i, text in enumerate(block.header)]]
    for row in block.rows:
        data.append([Paragraph(to_markup(text, block.line), cell_styles[i]) for i, text in enumerate(row)])
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


def _callout_flowable(block: Callout, styles: Styles) -> Table:
    check_glyphs(block.text, "Body", block.line)
    warning = block.kind == "WARNING"
    color = WARNING if warning else styles.accent
    label_style = styles.warning_label if warning else styles.callout_label
    content = [
        Paragraph("WARNING" if warning else "NOTE", label_style),
        Paragraph(to_markup(block.text, block.line), styles.callout_text),
    ]
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


def _image_flowable(block: ImageBlock, doc_dir: Path, styles: Styles, figure: int, used: List[str]) -> List:
    try:
        path = resolve_inside(doc_dir, block.path)
    except Exception as exc:
        raise ContentError(f"image path is not allowed: {block.path}", block.line) from exc
    if not path.is_file():
        raise ContentError(f"image file not found: {block.path}", block.line)
    try:
        with PILImage.open(path) as image:
            image.load()
            width_px, height_px = image.size
            raw_dpi = image.info.get("dpi", (DEFAULT_IMAGE_DPI, DEFAULT_IMAGE_DPI))[0]
    except Exception as exc:
        raise ContentError(f"image cannot be read: {block.path}", block.line) from exc
    if width_px * height_px > MAX_PIXELS:
        raise ContentError(f"image is too large: {block.path}", block.line)
    dpi = float(raw_dpi) if raw_dpi and float(raw_dpi) >= 36 else DEFAULT_IMAGE_DPI
    width, height = _scaled_size(width_px, height_px, dpi, CONTENT_WIDTH, MAX_IMAGE_HEIGHT)
    used.append(block.path)
    picture = Image(str(path), width=width, height=height, mask="auto")
    picture.hAlign = "CENTER"
    parts: List = [picture]
    if block.caption:
        check_glyphs(block.caption, "Body", block.line)
        parts.append(Paragraph(f"Figure {figure}. {to_markup(block.caption, block.line)}", styles.caption))
    else:
        parts.append(Spacer(1, 10))
    return [KeepTogether(parts)]


def _list_flowable(block, styles: Styles, numbered: bool) -> List:
    for item in block.items:
        check_glyphs(item, "Body", block.line)
    items = [
        ListItem(Paragraph(to_markup(text, block.line), styles.list_item), leftIndent=18) for text in block.items
    ]
    common = dict(
        leftIndent=18, bulletFontName="Body-Bold" if numbered else "Body", bulletFontSize=10.5,
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
    story: List = [Spacer(1, 12 * mm), logo]
    if brand.tagline:
        story.append(Paragraph(to_markup(brand.tagline), styles.cover_tagline))
    story.append(Spacer(1, 34 * mm))
    story.append(Paragraph(to_markup(meta.title), styles.cover_title))
    if meta.subtitle:
        story.append(Paragraph(to_markup(meta.subtitle), styles.cover_subtitle))
    story.append(HRFlowable(width="22%", thickness=3, color=styles.accent, hAlign="LEFT", spaceBefore=8, spaceAfter=18))
    for label, value in (
        ("AUTHOR", meta.author),
        ("AUDIENCE", meta.audience),
        ("VERSION", meta.version),
        ("DATE", meta.date),
    ):
        story.append(Paragraph(label, styles.cover_meta_label))
        story.append(Paragraph(to_markup(value), styles.cover_meta))
    return story


def _toc(styles: Styles) -> TableOfContents:
    toc = TableOfContents()
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


def _break_page(story: List) -> None:
    """Append a page break unless the story already ends with one."""
    if story and isinstance(story[-1], PageBreak):
        return
    story.append(PageBreak())


def _story(blocks: Sequence[Block], doc_dir: Path, styles: Styles) -> Tuple[List, List[str]]:
    story: List = []
    images: List[str] = []
    figure = 0
    seen_h1 = False

    for position, block in enumerate(blocks):
        following = blocks[position + 1] if position + 1 < len(blocks) else None
        if isinstance(block, Heading):
            check_glyphs(block.text, "Body", block.line)
            style = {1: styles.h1, 2: styles.h2, 3: styles.h3}[block.level]
            if block.level == 1:
                if seen_h1:
                    _break_page(story)
                seen_h1 = True
            story.append(
                HeadingParagraph(to_markup(block.text, block.line), style, block.level, to_plain(block.text, block.line))
            )
        elif isinstance(block, ParagraphBlock):
            check_glyphs(block.text, "Body", block.line)
            introduces = isinstance(following, (Code, TableBlock, ImageBlock)) and len(block.text) <= KEEP_WITH_NEXT_MAX
            style = styles.body_keep if introduces else styles.body
            story.append(Paragraph(to_markup(block.text, block.line), style))
        elif isinstance(block, BulletList):
            story.extend(_list_flowable(block, styles, numbered=False))
        elif isinstance(block, NumberedList):
            story.extend(_list_flowable(block, styles, numbered=True))
        elif isinstance(block, Code):
            story.extend(_code_flowables(block, styles))
        elif isinstance(block, TableBlock):
            story.append(_table_flowable(block, styles))
            story.append(Spacer(1, 12))
        elif isinstance(block, ImageBlock):
            figure += 1
            story.extend(_image_flowable(block, doc_dir, styles, figure, images))
        elif isinstance(block, Callout):
            story.append(_callout_flowable(block, styles))
            story.append(Spacer(1, 12))
        elif isinstance(block, PageBreakBlock):
            _break_page(story)
        else:  # pragma: no cover - guarded by the parser's closed set of block types
            raise ContentError("unsupported block type", getattr(block, "line", None))
    return story, images


def render_document(blocks: Sequence[Block], meta: Meta, brand: Brand, doc_dir: Path) -> RenderResult:
    """Render blocks to PDF bytes. Fonts must already be registered."""
    for text in (
        meta.title, meta.subtitle or "", meta.author, meta.audience, meta.date, brand.display_name, brand.tagline or "",
    ):
        check_glyphs(text, "Body")

    styles = build_styles(brand)
    body_story, images = _story(blocks, doc_dir, styles)
    has_contents = any(isinstance(b, Heading) for b in blocks)

    story: List = _cover(meta, brand, styles)
    story.append(NextPageTemplate("Body"))
    story.append(PageBreak())
    if has_contents:
        story.append(Paragraph("Contents", styles.toc_title))
        story.append(_toc(styles))
        story.append(PageBreak())
    story.extend(body_story)

    buffer = io.BytesIO()
    document = _Document(buffer, meta, brand, styles)

    previous_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    previous_lang = rl_config.documentLang
    previous_font = rl_config.canvas_basefontname
    os.environ["SOURCE_DATE_EPOCH"] = str(meta.epoch)
    rl_config.documentLang = meta.language
    rl_config.canvas_basefontname = "Body"
    try:
        document.multiBuild(story, maxPasses=6)
    finally:
        rl_config.documentLang = previous_lang
        rl_config.canvas_basefontname = previous_font
        if previous_epoch is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = previous_epoch

    return RenderResult(pdf=buffer.getvalue(), pages=document.page, images=tuple(images))
