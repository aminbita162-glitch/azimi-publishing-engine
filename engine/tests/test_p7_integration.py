"""Phase 7: end-to-end integration tests.

P7.WP2 — One-command lifecycle: check, build, verify, review on a minimal
document, with reproducibility and SBOM verification.

P7.WP3 — Cross-product: a second document with all visual element types
(flow diagram, table, image, code block, callouts, rights chapter) to prove
the engine is not limited to Session 01.
"""

import contextlib
import io
import json
import shutil
import unittest
from pathlib import Path

from pypdf import PdfReader

from engine.cli import main
from engine.tests.support import (
    CONTENT,
    META,
    REAL_ROOT,
    RIGHTS,
    make_figure,
    make_logo,
    make_project,
    TempProject,
)

_FILLER = "\n\n".join(
    f"Filler paragraph number {i} of the document body for testing purposes."
    for i in range(1, 51)
)


class _CliHarness:
    """Run CLI commands against a project root and capture output."""

    def run_cli(self, argv, root):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv, root=root)
        return code, out.getvalue(), err.getvalue()


class LifecycleIntegrationTests(unittest.TestCase, _CliHarness):
    """P7.WP2 — Full CLI lifecycle: check, build, verify, review."""

    def test_full_lifecycle_check_build_verify_review(self):
        with TempProject() as root:
            doc = str(root / "courses" / "doc")

            # Step 1: check
            code, out, err = self.run_cli(["check", doc], root)
            self.assertEqual(code, 0, err)

            # Step 2: build
            code, out, err = self.run_cli(["build", doc], root)
            self.assertEqual(code, 0, err)
            pdf_path = root / "courses" / "doc" / "build" / "Sample_Session_v1.0.0.pdf"
            self.assertTrue(pdf_path.is_file())
            manifest_path = root / "courses" / "doc" / "build" / "Sample_Session_v1.0.0.pdf.manifest.json"
            manifest = json.loads(manifest_path.read_text())
            self.assertEqual(manifest["audit"]["result"], "PASS")
            self.assertEqual(len(manifest["audit"]["checks"]), 16)
            for check in manifest["audit"]["checks"]:
                self.assertEqual(check["status"], "PASS", f"Audit check {check['id']} failed")

            # Step 3: verify
            code, out, err = self.run_cli(["verify", doc], root)
            self.assertEqual(code, 0, err)
            self.assertIn("PASS", out)

            # Step 4: review (one command, full sequence)
            code, out, err = self.run_cli(["review", doc], root)
            self.assertEqual(code, 0, err)
            self.assertIn("Check", out)
            self.assertIn("Audit", out)
            self.assertIn("Verify", out)
            report_path = root / "courses" / "doc" / "build" / "review-report.json"
            self.assertTrue(report_path.is_file())
            report = json.loads(report_path.read_text())
            self.assertEqual(report["overall"], "PASS")
            self.assertEqual(len(report["steps"]), 4)

    def test_reproducibility_two_builds_identical(self):
        """Two consecutive builds produce the same SHA-256."""
        with TempProject() as root:
            doc = str(root / "courses" / "doc")
            code, _, _ = self.run_cli(["build", doc], root)
            self.assertEqual(code, 0)
            manifest_path = root / "courses" / "doc" / "build" / "Sample_Session_v1.0.0.pdf.manifest.json"
            sha1 = json.loads(manifest_path.read_text())["output"]["sha256"]

            # Build again — manifest should report the same SHA
            code, _, _ = self.run_cli(["build", doc], root)
            self.assertEqual(code, 0)
            sha2 = json.loads(manifest_path.read_text())["output"]["sha256"]

            self.assertEqual(sha1, sha2, "Two builds produced different SHA-256")


class CrossProductIntegrationTests(unittest.TestCase, _CliHarness):
    """P7.WP3 — A second document with all visual element types."""

    CROSS_CONTENT = (
        "# Cross-Product Validation\n\n"
        "This document exercises every visual element type: headings, "
        "paragraphs, bullet lists, numbered lists, code, a table, an "
        "image, a flow diagram, and callout boxes.\n\n"
        "## Sections and structure\n\n"
        "- First bullet point about the engine\n"
        "- Second bullet point about the audit\n"
        "- Third bullet point about reproducibility\n\n"
        "1. Parse the content file\n"
        "2. Lint for forbidden terms\n"
        "3. Render with ReportLab\n"
        "4. Audit A1 through A16\n\n"
        "NOTE: This callout box is rendered as a note-style box.\n\n"
        "~~~python\n"
        "def build(path):\n"
        "    return render(path)\n"
        "~~~\n\n"
        "| Feature | Status |\n"
        "|:--------|:------:|\n"
        "| Fonts | OK |\n"
        "| Images | OK |\n"
        "| Diagrams | OK |\n"
        "| Tables | OK |\n"
        "| Rights | OK |\n\n"
        "IMG: assets/flow.png | Three boxes in a row | The pipeline\n\n"
        "~~~diagram\n"
        "type: flow\n"
        "caption: Build pipeline flow\n"
        "node start: Start | process\n"
        "node parse: Parse | process\n"
        "node render: Render | process\n"
        "node audit: Audit | process\n"
        "node done: Done | process\n"
        "edge start -> parse\n"
        "edge parse -> render\n"
        "edge render -> audit\n"
        "edge audit -> done: pass\n"
        "~~~\n\n"
        "WARNING: This callout box is rendered as a warning-style box.\n\n"
        + _FILLER
        + "\n\n"
        "## Second section\n\n"
        "Closing text for the second section of the document.\n\n"
        + _FILLER
    )

    CROSS_META = (
        "title: Cross-Product Validation Document\n"
        "subtitle: A second document\n"
        "author: Test Author\n"
        "audience: Engineers\n"
        "language: en\n"
        "version: 1.0.0\n"
        "date: November 2026\n"
        "output_name: Cross_Product_Validation\n"
        "numbered: true\n"
        "chapter_pages: true\n"
    )

    def test_second_document_builds_with_all_features(self):
        """A document with diagrams, tables, images, code, callouts, and
        a rights chapter builds and passes all 16 audit checks."""
        with TempProject(
            content=self.CROSS_CONTENT,
            meta=self.CROSS_META,
        ) as root:
            doc = str(root / "courses" / "doc")
            code, out, err = self.run_cli(["build", doc], root)
            self.assertEqual(code, 0, err)

            manifest_path = (
                root / "courses" / "doc" / "build"
                / "Cross_Product_Validation_v1.0.0.pdf.manifest.json"
            )
            manifest = json.loads(manifest_path.read_text())
            self.assertEqual(manifest["audit"]["result"], "PASS")
            for check in manifest["audit"]["checks"]:
                self.assertEqual(
                    check["status"], "PASS",
                    f"Check {check['id']} ({check['name']}) failed: {check.get('detail', '')}",
                )

            # Verify the PDF has the expected content
            pdf_path = (
                root / "courses" / "doc" / "build"
                / "Cross_Product_Validation_v1.0.0.pdf"
            )
            reader = PdfReader(io.BytesIO(pdf_path.read_bytes()))
            text = "".join(p.extract_text() for p in reader.pages)
            # Rights chapter is present
            self.assertIn("Rights", text)
            # Table content is present
            self.assertIn("Fonts", text)
            # Callout content is present
            self.assertIn("callout", text.lower())
            # Page count is reasonable
            self.assertGreater(len(reader.pages), 3)

    def test_second_document_reproducible(self):
        """The cross-product document is reproducible across two builds."""
        with TempProject(
            content=self.CROSS_CONTENT,
            meta=self.CROSS_META,
        ) as root:
            doc = str(root / "courses" / "doc")
            code, _, _ = self.run_cli(["build", doc], root)
            self.assertEqual(code, 0)
            manifest_path = (
                root / "courses" / "doc" / "build"
                / "Cross_Product_Validation_v1.0.0.pdf.manifest.json"
            )
            sha1 = json.loads(manifest_path.read_text())["output"]["sha256"]

            code, _, _ = self.run_cli(["build", doc], root)
            self.assertEqual(code, 0)
            sha2 = json.loads(manifest_path.read_text())["output"]["sha256"]
            self.assertEqual(sha1, sha2)


if __name__ == "__main__":
    unittest.main()
