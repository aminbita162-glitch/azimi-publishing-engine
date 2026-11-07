"""Phase 4: structural and semantic audit adversarial contracts (A2, A5, A9,
A10, A14, A16).

Each test crafts a malformed PDF and proves the audit fails the *correct*
check with a deterministic failure and no crash or silent PASS.
"""
import io
import unittest

import yaml
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from engine.audit import audit_pdf
from engine.schemas.meta import parse_meta
from engine.tests.support import META


def _meta():
    return parse_meta(yaml.safe_load(META))


def _failed(report):
    return {c.id for c in report.checks if not c.passed}


def _helvetica_pdf() -> bytes:
    """A page using the standard-14 Helvetica font (no FontDescriptor / no embedding)."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("Helvetica", 10)
    c.drawString(72, 700, "Standard fourteen font, not embedded.")
    c.showPage()
    c.save()
    return buf.getvalue()


def _unsafe_link_pdf() -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("Helvetica", 10)
    c.drawString(72, 700, "link target")
    c.linkURL("javascript:alert(1)", (72, 690, 200, 710), relative=0)
    c.showPage()
    c.save()
    return buf.getvalue()


def _gapped_numbering_pdf() -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("Helvetica", 10)
    c.drawString(72, 760, "Figure 1. First caption.")
    c.drawString(72, 740, "Figure 3. Third caption.")
    c.drawString(72, 720, "Body text fills the rest of this page.")
    c.showPage()
    c.save()
    return buf.getvalue()


def _ghost_dest_acroform_pdf() -> bytes:
    """A page with an internal link whose destination does not resolve, plus a
    catalog /AcroForm key (forbidden active content)."""
    base = _helvetica_pdf()
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(base)))
    page = writer.pages[0]
    annot = DictionaryObject()
    annot[NameObject("/Subtype")] = NameObject("/Link")
    annot[NameObject("/Dest")] = NameObject("/ghost-destination")
    ref = writer._add_object(annot)
    page[NameObject("/Annots")] = ArrayObject([ref])
    writer._root_object[NameObject("/AcroForm")] = DictionaryObject()
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _launch_action_pdf() -> bytes:
    base = _helvetica_pdf()
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(base)))
    page = writer.pages[0]
    action = DictionaryObject()
    action[NameObject("/S")] = NameObject("/Launch")
    action[NameObject("/F")] = NameObject("/usr/bin/open")
    annot = DictionaryObject()
    annot[NameObject("/Subtype")] = NameObject("/Link")
    annot[NameObject("/A")] = writer._add_object(action)
    page[NameObject("/Annots")] = ArrayObject([writer._add_object(annot)])
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _control_char_pdf() -> bytes:
    """A page whose content stream shows a literal control character (\\x01),
    which extracts as a disallowed control character."""
    writer = PdfWriter()
    writer.add_blank_page(A4[0], A4[1])
    page = writer.pages[0]
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 10 Tf 72 700 Td (hello\x01world) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    resources = DictionaryObject()
    resources[NameObject("/Font")] = DictionaryObject({
        NameObject("/F1"): DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
    })
    page[NameObject("/Resources")] = writer._add_object(resources)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


class StructuralAdversarialTests(unittest.TestCase):
    def test_unembedded_font_fails_a2(self):
        report = audit_pdf(_helvetica_pdf(), _meta(), ())
        self.assertIn("A2", _failed(report))
        a2 = next(c for c in report.checks if c.id == "A2")
        self.assertTrue(any("Helvetica" in i for i in a2.issues))

    def test_unsafe_link_fails_a5(self):
        report = audit_pdf(_unsafe_link_pdf(), _meta(), ())
        self.assertIn("A5", _failed(report))
        a5 = next(c for c in report.checks if c.id == "A5")
        self.assertTrue(any("unsafe link" in i for i in a5.issues))

    def test_broken_internal_link_fails_a9(self):
        report = audit_pdf(_ghost_dest_acroform_pdf(), _meta(), ())
        self.assertIn("A9", _failed(report))
        a9 = next(c for c in report.checks if c.id == "A9")
        self.assertTrue(any("points nowhere" in i for i in a9.issues))

    def test_gapped_figure_numbering_fails_a10(self):
        report = audit_pdf(_gapped_numbering_pdf(), _meta(), ())
        self.assertIn("A10", _failed(report))
        a10 = next(c for c in report.checks if c.id == "A10")
        self.assertTrue(any("1, 3" in i for i in a10.issues))

    def test_acroform_in_catalog_fails_a14(self):
        report = audit_pdf(_ghost_dest_acroform_pdf(), _meta(), ())
        self.assertIn("A14", _failed(report))
        a14 = next(c for c in report.checks if c.id == "A14")
        self.assertTrue(any("AcroForm" in i for i in a14.issues))

    def test_launch_action_fails_a14(self):
        report = audit_pdf(_launch_action_pdf(), _meta(), ())
        self.assertIn("A14", _failed(report))

    def test_control_character_fails_a16(self):
        report = audit_pdf(_control_char_pdf(), _meta(), ())
        self.assertIn("A16", _failed(report))
        a16 = next(c for c in report.checks if c.id == "A16")
        self.assertTrue(any("control characters" in i for i in a16.issues))

    def test_every_adversarial_report_is_an_overall_fail(self):
        """No adversarial fixture may silently PASS the whole audit."""
        for data in (
            _helvetica_pdf(),
            _unsafe_link_pdf(),
            _ghost_dest_acroform_pdf(),
            _gapped_numbering_pdf(),
            _launch_action_pdf(),
            _control_char_pdf(),
        ):
            self.assertFalse(audit_pdf(data, _meta(), ()).passed)


if __name__ == "__main__":
    unittest.main()
