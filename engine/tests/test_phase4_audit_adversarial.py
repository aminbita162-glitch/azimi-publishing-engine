"""Phase 4: adversarial page-geometry and false-fill audit contracts.

The false-fill defence (DECORATIVE_FULL_FRAME_FRACTION) is the core Phase 4
page-geometry invariant: a decorative full-page background, watermark or rule
must not inflate the measured body fill, while real content rectangles (table
cells, code frames, diagram nodes) are always counted.
"""
import io
import unittest
from unittest import mock

import yaml
from pypdf import PdfReader
from reportlab.lib.pagesizes import A4, letter
from reportlab.pdfgen import canvas

from engine.audit import audit_pdf
from engine.audit.pdf_audit import DECORATIVE_FULL_FRAME_FRACTION, page_fill_ratios
from engine.render.styles import MARGIN_BOTTOM, MARGIN_TOP, PAGE_HEIGHT, PAGE_WIDTH
from engine.schemas.meta import parse_meta
from engine.tests.support import META


def _meta():
    return parse_meta(yaml.safe_load(META))


BODY_TOP = PAGE_HEIGHT - MARGIN_TOP
BODY_BOTTOM = MARGIN_BOTTOM
SPAN = BODY_TOP - BODY_BOTTOM


def _draw(canvas_obj, draw_body):
    draw_body(canvas_obj)
    canvas_obj.showPage()
    canvas_obj.save()


def decorative_background_pdf() -> bytes:
    """One page with a full-body-frame gray background and a single text line."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFillColorRGB(0.9, 0.9, 0.9)
    # A rectangle spanning the whole body frame: the false-fill pattern.
    c.rect(BODY_BOTTOM, BODY_BOTTOM, PAGE_WIDTH - 2 * BODY_BOTTOM, SPAN, fill=1, stroke=0)
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica", 10)
    c.drawString(BODY_BOTTOM + 10, BODY_TOP - 20, "Only one line of content at the very top.")
    _draw(c, lambda _c: None)
    return buf.getvalue()


def short_content_rect_pdf() -> bytes:
    """One page with a short content rectangle near the bottom and text at the top."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFillColorRGB(0.8, 0.8, 0.8)
    c.rect(100, 100, 200, 20, fill=1, stroke=0)  # short rect -> counts as content
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica", 10)
    c.drawString(110, BODY_TOP - 20, "Text at the top.")
    _draw(c, lambda _c: None)
    return buf.getvalue()


def letter_size_pdf() -> bytes:
    """A Letter-size page (not A4) with text."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setFont("Helvetica", 10)
    c.drawString(72, 700, "A Letter-size page is not A4.")
    _draw(c, lambda _c: None)
    return buf.getvalue()


class FalseFillTests(unittest.TestCase):
    def test_decorative_full_frame_background_does_not_inflate_fill(self):
        data = decorative_background_pdf()
        fills = page_fill_ratios(PdfReader(io.BytesIO(data)))
        self.assertEqual(len(fills), 1)
        self.assertLess(fills[0], 0.87, f"decorative background inflated fill to {fills[0]:.3f}")

    def test_decorative_background_fails_a7(self):
        data = decorative_background_pdf()
        report = audit_pdf(data, _meta(), ())
        a7 = next(c for c in report.checks if c.id == "A7")
        self.assertFalse(a7.passed, "A7 must fail on a decorative full-page background")
        self.assertTrue(any("page 1" in issue for issue in a7.issues))

    def test_short_content_rectangle_is_still_counted(self):
        data = short_content_rect_pdf()
        fills = page_fill_ratios(PdfReader(io.BytesIO(data)))
        # The short rect near the bottom must count: fill well above the threshold.
        self.assertGreater(fills[0], 0.5, f"short content rect undercounted to {fills[0]:.3f}")

    def test_decorative_threshold_fraction_is_above_real_content(self):
        # Sanity: the decorative threshold is high enough that no real short rect
        # is mistaken for a full-page background.
        self.assertGreater(DECORATIVE_FULL_FRAME_FRACTION, 0.5)
        self.assertLess(DECORATIVE_FULL_FRAME_FRACTION, 1.0)

    def test_a7_still_fails_with_max_blank_ratio_zero(self):
        # Regression: the zero threshold must still catch a real underfilled page.
        data = decorative_background_pdf()
        report = audit_pdf(data, _meta(), (), max_blank_ratio=0.0)
        a7 = next(c for c in report.checks if c.id == "A7")
        self.assertFalse(a7.passed)


class PageGeometryTests(unittest.TestCase):
    def test_non_a4_page_fails_a6(self):
        data = letter_size_pdf()
        report = audit_pdf(data, _meta(), ())
        a6 = next(c for c in report.checks if c.id == "A6")
        self.assertFalse(a6.passed, "A6 must fail on a non-A4 page")
        self.assertTrue(any("another size" in issue for issue in a6.issues))

    def test_a4_page_passes_a6(self):
        data = short_content_rect_pdf()
        report = audit_pdf(data, _meta(), ())
        a6 = next(c for c in report.checks if c.id == "A6")
        self.assertTrue(a6.passed, "A6 must pass on an A4 page")


if __name__ == "__main__":
    unittest.main()
