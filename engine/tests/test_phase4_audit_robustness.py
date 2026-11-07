"""Phase 4: robustness and adversarial input handling for audit_pdf.

The audit must never crash on truncated, encrypted, empty or malformed PDF
input: it must fail closed with a single A0 readability check and a
deterministic overall FAIL.
"""
import io
import unittest

import yaml
from pypdf import PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from engine.audit import audit_pdf
from engine.schemas.meta import parse_meta
from engine.tests.support import META


def _meta():
    return parse_meta(yaml.safe_load(META))


def _good_pdf() -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("Helvetica", 10)
    c.drawString(72, 700, "A valid one-page PDF.")
    c.showPage()
    c.save()
    return buf.getvalue()


def _truncated_pdf() -> bytes:
    return _good_pdf()[:-200]


def _empty_bytes() -> bytes:
    return b""


def _garbage_bytes() -> bytes:
    return b"%PDF-1.4\nthis is not a real pdf\n%%EOF"


def _encrypted_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(595, 842)
    writer.encrypt("secret")
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _zero_page_pdf() -> bytes:
    writer = PdfWriter()
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


class RobustnessTests(unittest.TestCase):
    def test_truncated_pdf_does_not_crash(self):
        report = audit_pdf(_truncated_pdf(), _meta(), ())
        self.assertFalse(report.passed)
        ids = [c.id for c in report.checks]
        self.assertEqual(ids, ["A0"])
        self.assertIn("unreadable", report.checks[0].detail)

    def test_empty_bytes_does_not_crash(self):
        report = audit_pdf(_empty_bytes(), _meta(), ())
        self.assertFalse(report.passed)
        ids = [c.id for c in report.checks]
        self.assertEqual(ids, ["A0"])
        self.assertIn("unreadable", report.checks[0].detail)

    def test_garbage_bytes_does_not_crash(self):
        report = audit_pdf(_garbage_bytes(), _meta(), ())
        self.assertFalse(report.passed)
        ids = [c.id for c in report.checks]
        self.assertEqual(ids, ["A0"])

    def test_encrypted_pdf_fails_closed(self):
        report = audit_pdf(_encrypted_pdf(), _meta(), ())
        self.assertFalse(report.passed)
        ids = [c.id for c in report.checks]
        self.assertEqual(ids, ["A0"])
        self.assertIn("encrypted", report.checks[0].detail)

    def test_zero_page_pdf_does_not_crash(self):
        report = audit_pdf(_zero_page_pdf(), _meta(), ())
        self.assertFalse(report.passed)
        # Zero-page is readable but empty: A1–A16 run (no pages to check),
        # metadata/outline checks fail — no crash.
        ids = [c.id for c in report.checks]
        self.assertEqual(ids[0], "A1")

    def test_unreadable_report_has_empty_page_fill(self):
        report = audit_pdf(_truncated_pdf(), _meta(), ())
        self.assertEqual(report.page_fill, ())

    def test_unreadable_report_preserves_exempt_pages(self):
        report = audit_pdf(_truncated_pdf(), _meta(), [3, 1, 2])
        self.assertEqual(report.exempt_pages, (1, 2, 3))

    def test_manifest_serialization_of_unreadable_report(self):
        report = audit_pdf(_empty_bytes(), _meta(), ())
        d = report.to_dict()
        self.assertEqual(d["result"], "FAIL")
        self.assertEqual(d["checks"][0]["id"], "A0")
        self.assertEqual(d["checks"][0]["status"], "FAIL")
        self.assertIn("issues", d["checks"][0])

    def test_valid_pdf_is_not_caught_by_guard(self):
        # Regression: a valid PDF must not trigger the A0 guard.
        report = audit_pdf(_good_pdf(), _meta(), ())
        ids = [c.id for c in report.checks]
        self.assertNotIn("A0", ids)
        self.assertEqual(ids, [f"A{n}" for n in range(1, 17)])


if __name__ == "__main__":
    unittest.main()
