"""Design tokens and paragraph styles. Page geometry and typography live here."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm

from ..brand import Brand

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN_LEFT = 22 * mm
MARGIN_RIGHT = 22 * mm
MARGIN_TOP = 26 * mm
MARGIN_BOTTOM = 24 * mm
CONTENT_WIDTH = PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT
CONTENT_HEIGHT = PAGE_HEIGHT - MARGIN_TOP - MARGIN_BOTTOM

BODY_SIZE = 10.5
BODY_LEADING = 15.5
CODE_SIZE = 8.6
CODE_LEADING = 11.6
CODE_PADDING = 6

TEXT = colors.HexColor("#1F2933")
MUTED = colors.HexColor("#5F6B7A")
RULE = colors.HexColor("#D5DBE3")
ZEBRA = colors.HexColor("#F4F6F8")
CODE_BACKGROUND = colors.HexColor("#F4F6F8")
WARNING = colors.HexColor("#B42318")

ALIGNMENT = {"left": TA_LEFT, "center": TA_CENTER, "right": TA_RIGHT}


def mix_with_white(color: colors.Color, amount: float) -> colors.Color:
    """Return color blended with white; amount 0 keeps color, 1 gives white."""
    return colors.Color(
        color.red + (1 - color.red) * amount,
        color.green + (1 - color.green) * amount,
        color.blue + (1 - color.blue) * amount,
    )


def readable_on(background: colors.Color) -> colors.Color:
    """Return white or near-black, whichever reads better on background."""
    luminance = 0.2126 * background.red + 0.7152 * background.green + 0.0722 * background.blue
    return colors.white if luminance < 0.6 else TEXT


@dataclass(frozen=True)
class Styles:
    """All styles used by the renderer."""

    primary: colors.Color
    accent: colors.Color
    on_primary: colors.Color
    body: ParagraphStyle
    list_item: ParagraphStyle
    h1: ParagraphStyle
    h2: ParagraphStyle
    h3: ParagraphStyle
    code: ParagraphStyle
    code_label: ParagraphStyle
    caption: ParagraphStyle
    table_cell: ParagraphStyle
    table_header: ParagraphStyle
    callout_text: ParagraphStyle
    callout_label: ParagraphStyle
    warning_label: ParagraphStyle
    cover_title: ParagraphStyle
    cover_subtitle: ParagraphStyle
    cover_meta: ParagraphStyle
    cover_meta_label: ParagraphStyle
    cover_tagline: ParagraphStyle
    toc_title: ParagraphStyle
    toc1: ParagraphStyle
    toc2: ParagraphStyle

    def aligned(self, base: ParagraphStyle, align: str) -> ParagraphStyle:
        """Return a copy of base with the given alignment (left, center, right)."""
        return ParagraphStyle(f"{base.name}-{align}", parent=base, alignment=ALIGNMENT[align])


def build_styles(brand: Brand) -> Styles:
    primary = colors.HexColor(brand.primary_color)
    accent = colors.HexColor(brand.accent_color)

    body = ParagraphStyle(
        "Body", fontName="Body", fontSize=BODY_SIZE, leading=BODY_LEADING, textColor=TEXT,
        alignment=TA_LEFT, spaceAfter=7, allowWidows=0, allowOrphans=0,
    )
    list_item = ParagraphStyle("ListItem", parent=body, spaceAfter=3)
    h1 = ParagraphStyle(
        "H1", parent=body, fontName="Body-Bold", fontSize=26, leading=31, textColor=primary,
        spaceBefore=0, spaceAfter=14, keepWithNext=1,
    )
    h2 = ParagraphStyle(
        "H2", parent=body, fontName="Body-Bold", fontSize=17, leading=22, textColor=primary,
        spaceBefore=16, spaceAfter=7, keepWithNext=1,
    )
    h3 = ParagraphStyle(
        "H3", parent=body, fontName="Body-Bold", fontSize=13, leading=18, textColor=TEXT,
        spaceBefore=12, spaceAfter=5, keepWithNext=1,
    )
    code = ParagraphStyle(
        "Code", fontName="Mono", fontSize=CODE_SIZE, leading=CODE_LEADING, textColor=TEXT,
        backColor=CODE_BACKGROUND, borderColor=RULE, borderWidth=0.5, borderPadding=CODE_PADDING,
        leftIndent=CODE_PADDING, rightIndent=CODE_PADDING, spaceBefore=2, spaceAfter=14,
    )
    code_label = ParagraphStyle(
        "CodeLabel", fontName="Mono-Bold", fontSize=7.5, leading=10, textColor=accent,
        spaceBefore=8, spaceAfter=5, keepWithNext=1,
    )
    caption = ParagraphStyle(
        "Caption", parent=body, fontName="Body-Italic", fontSize=9, leading=12, textColor=MUTED,
        alignment=TA_CENTER, spaceBefore=4, spaceAfter=12,
    )
    table_cell = ParagraphStyle(
        "TableCell", parent=body, fontSize=9.5, leading=13, spaceAfter=0,
    )
    table_header = ParagraphStyle(
        "TableHeader", parent=table_cell, fontName="Body-Bold", textColor=readable_on(primary),
    )
    callout_text = ParagraphStyle("CalloutText", parent=body, fontSize=10, leading=14.5, spaceAfter=0)
    callout_label = ParagraphStyle(
        "CalloutLabel", parent=callout_text, fontName="Body-Bold", fontSize=8.5, leading=11,
        textColor=accent, spaceAfter=3,
    )
    warning_label = ParagraphStyle("WarningLabel", parent=callout_label, textColor=WARNING)
    cover_title = ParagraphStyle(
        "CoverTitle", parent=body, fontName="Body-Bold", fontSize=34, leading=40, textColor=primary,
        spaceAfter=10,
    )
    cover_subtitle = ParagraphStyle(
        "CoverSubtitle", parent=body, fontSize=16, leading=22, textColor=MUTED, spaceAfter=6,
    )
    cover_meta = ParagraphStyle("CoverMeta", parent=body, fontSize=11, leading=16, spaceAfter=3)
    cover_meta_label = ParagraphStyle(
        "CoverMetaLabel", parent=cover_meta, fontName="Body-Bold", fontSize=8.5, leading=11,
        textColor=accent, spaceBefore=10, spaceAfter=1,
    )
    cover_tagline = ParagraphStyle(
        "CoverTagline", parent=body, fontSize=9.5, leading=13, textColor=MUTED, spaceBefore=10, spaceAfter=0,
    )
    toc_title = ParagraphStyle("TocTitle", parent=h1, spaceAfter=18)
    toc1 = ParagraphStyle(
        "Toc1", parent=body, fontName="Body-Bold", fontSize=11.5, leading=16, spaceBefore=7, spaceAfter=0,
    )
    toc2 = ParagraphStyle(
        "Toc2", parent=body, fontSize=10.5, leading=14.5, leftIndent=14, spaceBefore=1, spaceAfter=0,
        textColor=TEXT,
    )

    return Styles(
        primary=primary, accent=accent, on_primary=readable_on(primary), body=body, list_item=list_item, h1=h1, h2=h2, h3=h3,
        code=code, code_label=code_label, caption=caption, table_cell=table_cell,
        table_header=table_header, callout_text=callout_text, callout_label=callout_label,
        warning_label=warning_label, cover_title=cover_title, cover_subtitle=cover_subtitle,
        cover_meta=cover_meta, cover_meta_label=cover_meta_label, cover_tagline=cover_tagline,
        toc_title=toc_title,
        toc1=toc1, toc2=toc2,
    )
