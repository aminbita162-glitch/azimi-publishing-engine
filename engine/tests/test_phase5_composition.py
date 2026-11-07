"""Phase 5 WP5: composition and visual regression tests.

Tests image+table+diagram adjacency, keepWithNext, page breaks, captions,
chapter boundaries with visual content, full audit (A1–A16), and build
performance on representative fixtures.
"""

import io
import time
import unittest
from pathlib import Path

from pypdf import PdfReader

from engine.build.builder import build_document
from engine.tests.support import META, TempProject

_FILLER = "\n\n".join(
    f"Filler paragraph number {i} of the document body for testing purposes."
    for i in range(1, 51)
)


def _read(path: Path) -> PdfReader:
    return PdfReader(io.BytesIO(path.read_bytes()))


class CompositionTests(unittest.TestCase):
    def test_image_and_table_on_same_page(self):
        """An image and a table adjacent on the same page render without error."""
        content = (
            "# Title\n\n"
            "IMG: assets/flow.png | Diagram | Figure caption\n\n"
            "| A | B |\n|---|---|\n| 1 | 2 |\n\n"
            + _FILLER
        )
        meta = META + "numbered: true\n"
        with TempProject(content=content, meta=meta) as root:
            result = build_document(root, "courses/doc")
            self.assertTrue(result.audit.passed)

    def test_diagram_and_table_on_same_page(self):
        """A diagram and a table adjacent on the same page render without error."""
        content = (
            "# Title\n\n"
            "~~~diagram\n"
            "type: flow\n"
            "caption: Flow\n"
            "node a: A | process\n"
            "node b: B | process\n"
            "edge a -> b\n"
            "~~~\n\n"
            "TABLE: tbl | Table caption\n"
            "| A | B |\n|---|---|\n| 1 | 2 |\n\n"
            + _FILLER
        )
        meta = META + "numbered: true\n"
        with TempProject(content=content, meta=meta, with_image=False) as root:
            result = build_document(root, "courses/doc")
            self.assertTrue(result.audit.passed)

    def test_figure_caption_appears_in_lof(self):
        """A figure with a caption appears in the list of figures."""
        content = (
            "# Title\n\n"
            "IMG: assets/flow.png | Alt | My figure caption\n\n"
            + _FILLER
        )
        meta = META + "numbered: true\n"
        with TempProject(content=content, meta=meta) as root:
            result = build_document(root, "courses/doc")
            self.assertTrue(result.audit.passed)
            text = "".join(p.extract_text() for p in _read(result.pdf_path).pages)
            self.assertIn("Figure 1", text)
            self.assertIn("List of Figures", text)

    def test_table_caption_appears_in_lot(self):
        """A table with a caption appears in the list of tables."""
        content = (
            "# Title\n\n"
            "TABLE: mytable | My table caption\n"
            "| A | B |\n|---|---|\n| 1 | 2 |\n\n"
            + _FILLER
        )
        meta = META + "numbered: true\n"
        with TempProject(content=content, meta=meta, with_image=False) as root:
            result = build_document(root, "courses/doc")
            self.assertTrue(result.audit.passed)
            text = "".join(p.extract_text() for p in _read(result.pdf_path).pages)
            self.assertIn("Table 1", text)
            self.assertIn("List of Tables", text)

    def test_chapter_boundary_with_visual_does_not_create_blank_pages(self):
        """A chapter break with visual content does not create blank pages."""
        filler_short = "\n\n".join(
            f"Chapter paragraph {i} for the body content." for i in range(1, 31)
        )
        content = (
            "# First\n\n"
            + filler_short
            + "\n\n# Second\n\n"
            "~~~diagram\n"
            "type: flow\n"
            "caption: Second chapter diagram\n"
            "node a: Start | process\n"
            "node b: End | process\n"
            "edge a -> b\n"
            "~~~\n\n"
            + filler_short
        )
        meta = META + "chapter_pages: true\n"
        with TempProject(content=content, meta=meta, with_image=False) as root:
            result = build_document(root, "courses/doc")
            self.assertTrue(result.audit.passed)
            pages = [p.extract_text() for p in _read(result.pdf_path).pages]
            for i, text in enumerate(pages):
                self.assertGreater(
                    len(text.strip()), 40,
                    f"page {i + 1} appears blank",
                )

    def test_heading_followed_by_table_renders_without_gap(self):
        """A heading followed by a table does not leave a large blank gap."""
        content = (
            "# Title\n\n"
            + "\n\n".join(
                f"Paragraph {i} before the section for filling." for i in range(1, 31)
            )
            + "\n\n## Section with table\n\n"
            "| Column A | Column B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n\n"
            + "\n\n".join(
                f"Paragraph {i} after the section for filling." for i in range(1, 21)
            )
        )
        with TempProject(content=content, with_image=False) as root:
            result = build_document(root, "courses/doc")
            self.assertTrue(result.audit.passed)

    def test_full_document_with_all_visual_types_passes_all_16_checks(self):
        """A document with image, diagram and table passes every audit check."""
        content = (
            "# Title\n\n"
            "IMG: assets/flow.png | Alt | Figure caption\n\n"
            "~~~diagram\n"
            "type: flow\n"
            "caption: Diagram caption\n"
            "node a: Start | process\n"
            "node b: End | process\n"
            "edge a -> b\n"
            "~~~\n\n"
            "TABLE: mytable | Table caption\n"
            "| A | B |\n|---|---|\n| 1 | 2 |\n\n"
            + _FILLER
        )
        meta = META + "numbered: true\n"
        with TempProject(content=content, meta=meta) as root:
            result = build_document(root, "courses/doc")
            for check in result.audit.checks:
                self.assertTrue(
                    check.passed,
                    f"{check.id} ({check.name}) failed: {check.detail}",
                )

    def test_build_performance_is_bounded(self):
        """Building a representative document completes within a reasonable time."""
        content = (
            "# Title\n\n"
            + _FILLER
            + "\n\n~~~diagram\n"
            "type: flow\n"
            "caption: Perf\n"
            "node a: A | process\n"
            "node b: B | process\n"
            "edge a -> b\n"
            "~~~\n"
        )
        with TempProject(content=content, with_image=False) as root:
            start = time.perf_counter()
            result = build_document(root, "courses/doc")
            elapsed = time.perf_counter() - start
            self.assertTrue(result.audit.passed)
            self.assertLess(elapsed, 30.0, f"build took {elapsed:.1f}s")

    def test_deterministic_rebuild_with_all_visual_types(self):
        """Two builds of a document with all visual types are byte-identical."""
        content = (
            "# Title\n\n"
            "IMG: assets/flow.png | Alt | Figure caption\n\n"
            "~~~diagram\n"
            "type: flow\n"
            "caption: Diagram\n"
            "node a: A | process\n"
            "node b: B | process\n"
            "edge a -> b\n"
            "~~~\n\n"
            "TABLE: tbl | Table caption\n"
            "| A | B |\n|---|---|\n| 1 | 2 |\n\n"
            + _FILLER
        )
        meta = META + "numbered: true\n"
        with TempProject(content=content, meta=meta) as root:
            first = build_document(root, "courses/doc")
            second = build_document(root, "courses/doc")
            self.assertEqual(first.sha256, second.sha256)


if __name__ == "__main__":
    unittest.main()
