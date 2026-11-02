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

BODY_SIZE = 11.0
BODY_LEADING = 16.4
CODE_SIZE = 8.6
CODE_LEADING = 11.6
CODE_PADDING_LEFT = 12
CODE_PADDING_RIGHT = 8
CODE_PADDING_VERTICAL = 9
CODE_CHUNK_LINES = 8

TEXT = colors.HexColor("#1F2933")
MUTED = colors.HexColor("#5F6B7A")
RULE = colors.HexColor("#D5DBE3")
ZEBRA = colors.HexColor("#F4F6F8")
CODE_BACKGROUND = colors.HexColor("#F4F6F8")
WARNING = colors.HexColor("#B42318")
TIP = colors.HexColor("#0F766E")
CHECKPOINT = colors.HexColor("#1D6FA5")
EXAMPLE = colors.HexColor("#5B4B9A")
PITFALL = colors.HexColor("#B54708")
GUTTER_BACKGROUND = colors.HexColor("#E9EDF2")

CODE_COLORS = {
    "k": "#0B2A43",
    "f": "#0B2A43",
    "s": "#0F766E",
    "c": "#5F6B7A",
    "n": "#9A4A06",
}

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


def _linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4


def luminance(color: colors.Color) -> float:
    return 0.2126 * _linear(color.red) + 0.7152 * _linear(color.green) + 0.0722 * _linear(color.blue)


def contrast_ratio(foreground: colors.Color, background: colors.Color) -> float:
    """WCAG contrast ratio between two colors (1 to 21)."""
    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


MIN_CONTRAST = 4.5


def ensure_contrast(color: colors.Color, background: colors.Color = colors.white) -> colors.Color:
    """Darken color step by step until it reads on background with a WCAG ratio of at least 4.5."""
    result = color
    for step in range(1, 40):
        if contrast_ratio(result, background) >= MIN_CONTRAST:
            return result
        factor = 1 - step * 0.02
        result = colors.Color(color.red * factor, color.green * factor, color.blue * factor)
    return result


@dataclass(frozen=True)
class Styles:
    """All styles used by the renderer."""

    primary: colors.Color
    accent: colors.Color
    on_primary: colors.Color
    body: ParagraphStyle
    body_keep: ParagraphStyle
    list_item: ParagraphStyle
    h1: ParagraphStyle
    h2: ParagraphStyle
    h3: ParagraphStyle
    code: ParagraphStyle
    code_label: ParagraphStyle
    code_number: ParagraphStyle
    caption: ParagraphStyle
    table_caption: ParagraphStyle
    list_entry: ParagraphStyle
    list_heading: ParagraphStyle
    table_cell: ParagraphStyle
    table_header: ParagraphStyle
    callout_text: ParagraphStyle
    callout_label: ParagraphStyle
    callout_item: ParagraphStyle
    warning_label: ParagraphStyle
    cover_title: ParagraphStyle
    cover_subtitle: ParagraphStyle
    cover_meta: ParagraphStyle
    cover_meta_label: ParagraphStyle
    cover_tagline: ParagraphStyle
    imprint_title: ParagraphStyle
    imprint_subtitle: ParagraphStyle
    imprint_label: ParagraphStyle
    imprint_text: ParagraphStyle
    toc_title: ParagraphStyle
    toc1: ParagraphStyle
    toc2: ParagraphStyle

    def aligned(self, base: ParagraphStyle, align: str) -> ParagraphStyle:
        """Return a copy of base with the given alignment (left, center, right)."""
        return ParagraphStyle(f"{base.name}-{align}", parent=base, alignment=ALIGNMENT[align])


def build_styles(brand: Brand) -> Styles:
    primary = colors.HexColor(brand.primary_color)
    accent = colors.HexColor(brand.accent_color)
    accent_text = ensure_contrast(accent)

    body = ParagraphStyle(
        "Body", fontName="Body", fontSize=BODY_SIZE, leading=BODY_LEADING, textColor=TEXT,
        alignment=TA_LEFT, spaceAfter=7, allowWidows=0, allowOrphans=0,
    )
    body_keep = ParagraphStyle("BodyKeep", parent=body, keepWithNext=1)
    list_item = ParagraphStyle("ListItem", parent=body, spaceAfter=3)
    h1 = ParagraphStyle(
        "H1", parent=body, fontName="Body-Bold", fontSize=26, leading=31, textColor=primary,
        spaceBefore=54, spaceAfter=14, keepWithNext=1,
    )
    h2 = ParagraphStyle(
        "H2", parent=body, fontName="Body-Bold", fontSize=17, leading=22, textColor=primary,
        spaceBefore=50, spaceAfter=7, keepWithNext=1,
    )
    h3 = ParagraphStyle(
        "H3", parent=body, fontName="Body-Bold", fontSize=13, leading=18, textColor=TEXT,
        spaceBefore=52, spaceAfter=5, keepWithNext=1,
    )
    code = ParagraphStyle(
        "Code", fontName="Mono", fontSize=CODE_SIZE, leading=CODE_LEADING, textColor=TEXT,
    )
    code_label = ParagraphStyle(
        "CodeLabel", fontName="Mono-Bold", fontSize=8, leading=10.5, textColor=accent_text,
        spaceBefore=50, spaceAfter=5, keepWithNext=1,
    )
    code_number = ParagraphStyle(
        "CodeNumber", fontName="Mono", fontSize=CODE_SIZE, leading=CODE_LEADING, textColor=MUTED,
    )
    caption = ParagraphStyle(
        "Caption", parent=body, fontName="Body-Italic", fontSize=9, leading=12, textColor=MUTED,
        alignment=TA_CENTER, spaceBefore=5, spaceAfter=8,
    )
    table_caption = ParagraphStyle(
        "TableCaption", parent=body, fontName="Body-Bold", fontSize=9.5, leading=12.5, textColor=primary,
        alignment=TA_LEFT, spaceBefore=50, spaceAfter=3,
    )
    list_entry = ParagraphStyle(
        "ListEntry", parent=body, fontSize=10, leading=14.7, spaceBefore=5, spaceAfter=3, textColor=TEXT,
    )
    list_heading = ParagraphStyle(
        "ListHeading", parent=h2, spaceBefore=58, spaceAfter=8,
    )
    table_cell = ParagraphStyle(
        "TableCell", parent=body, fontSize=9.5, leading=14.7, spaceAfter=3,
    )
    table_header = ParagraphStyle(
        "TableHeader", parent=table_cell, fontName="Body-Bold", textColor=readable_on(primary),
    )
    callout_text = ParagraphStyle("CalloutText", parent=body, fontSize=10, leading=14.7, spaceAfter=3)
    callout_item = ParagraphStyle(
        "CalloutItem", parent=callout_text, leftIndent=12, bulletIndent=0, spaceAfter=2,
        bulletFontName="Body", bulletFontSize=10, bulletColor=accent,
    )
    callout_label = ParagraphStyle(
        "CalloutLabel", parent=callout_text, fontName="Body-Bold", fontSize=8.5, leading=11,
        textColor=accent_text, spaceAfter=3,
    )
    warning_label = ParagraphStyle("WarningLabel", parent=callout_label, textColor=WARNING)
    cover_title = ParagraphStyle(
        "CoverTitle", parent=body, fontName="Body-Bold", fontSize=34, leading=40, textColor=primary,
        spaceAfter=10,
    )
    cover_subtitle = ParagraphStyle(
        "CoverSubtitle", parent=body, fontSize=16, leading=22, textColor=MUTED, spaceAfter=8,
    )
    cover_meta = ParagraphStyle("CoverMeta", parent=body, fontSize=11, leading=14.7, spaceAfter=3)
    cover_meta_label = ParagraphStyle(
        "CoverMetaLabel", parent=cover_meta, fontName="Body-Bold", fontSize=8.5, leading=11,
        textColor=accent_text, spaceBefore=50, spaceAfter=1,
    )
    cover_tagline = ParagraphStyle(
        "CoverTagline", parent=body, fontSize=9.5, leading=14.7, textColor=MUTED, spaceBefore=50, spaceAfter=3,
    )
    imprint_title = ParagraphStyle(
        "ImprintTitle", parent=body, fontName="Body-Bold", fontSize=18, leading=23, textColor=primary, spaceAfter=3,
    )
    imprint_subtitle = ParagraphStyle(
        "ImprintSubtitle", parent=body, fontSize=11.5, leading=14.7, textColor=MUTED, spaceAfter=10,
    )
    imprint_label = ParagraphStyle(
        "ImprintLabel", parent=body, fontName="Body-Bold", fontSize=8, leading=11, textColor=accent_text,
        spaceBefore=52, spaceAfter=1,
    )
    imprint_text = ParagraphStyle("ImprintText", parent=body, fontSize=10, leading=14.7, spaceAfter=2)
    toc_title = ParagraphStyle("TocTitle", parent=h1, spaceAfter=10)
    toc1 = ParagraphStyle(
        "Toc1", parent=body, fontName="Body-Bold", fontSize=11.5, leading=14.7, spaceBefore=7, spaceAfter=3,
    )
    toc2 = ParagraphStyle(
        "Toc2", parent=body, fontSize=10.5, leading=14.7, leftIndent=14, spaceBefore=5, spaceAfter=3,
        textColor=TEXT,
    )

    return Styles(
        primary=primary, accent=accent, on_primary=readable_on(primary), body=body, body_keep=body_keep, list_item=list_item, h1=h1, h2=h2, h3=h3,
        code=code, code_label=code_label, code_number=code_number, caption=caption, table_caption=table_caption, list_entry=list_entry, list_heading=list_heading, table_cell=table_cell,
        table_header=table_header, callout_text=callout_text, callout_label=callout_label, callout_item=callout_item,
        warning_label=warning_label, cover_title=cover_title, cover_subtitle=cover_subtitle,
        cover_meta=cover_meta, cover_meta_label=cover_meta_label, cover_tagline=cover_tagline,
        imprint_title=imprint_title, imprint_subtitle=imprint_subtitle, imprint_label=imprint_label,
        imprint_text=imprint_text, toc_title=toc_title,
        toc1=toc1, toc2=toc2,
    )
