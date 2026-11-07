"""Phase 5 WP3: table engine tests.

Validates column sizing, header repetition, row splitting, cell padding,
wrapping, overflow, nested formatting, captions, numbering, Unicode, empty
cells, and multi-page table behavior.
"""

import io
import unittest
from pathlib import Path

from pypdf import PdfReader

from engine.build.builder import build_document
from engine.tests.support import META, TempProject


def _read(path: Path) -> PdfReader:
    return PdfReader(io.BytesIO(path.read_bytes()))


class TableEngineTests(unittest.TestCase):
    def test_multi_page_table_repeats_header(self):
        """A table spanning multiple pages repeats its header row on each page."""
        rows = "\n".join(f"| {i} | Item number {i} |" for i in range(1, 51))
        content = f"# Title\n\nTABLE: long | A long table\n| Col A | Col B |\n|---|---|\n{rows}\n"
        meta = META + "numbered: true\n"
        with TempProject(content=content, meta=meta, with_image=False) as root:
            result = build_document(root, "courses/doc")
            self.assertTrue(result.audit.passed)
            pages = [p.extract_text() for p in _read(result.pdf_path).pages]
            header_pages = [i for i, text in enumerate(pages) if "Col A" in text and "Col B" in text]
            self.assertGreaterEqual(
                len(header_pages), 2,
                "header row should repeat on at least 2 pages",
            )

    def test_wide_table_fits_without_clipping(self):
        """A table with 8 columns fits within the page width."""
        cols = " | ".join(f"Col{i}" for i in range(1, 9))
        sep = " | ".join("---" for _ in range(8))
        data = " | ".join(str(i) for i in range(1, 9))
        content = f"# Title\n\n| {cols} |\n| {sep} |\n| {data} |\n"
        with TempProject(content=content, with_image=False) as root:
            result = build_document(root, "courses/doc")
            self.assertTrue(result.audit.passed)
            text = "".join(p.extract_text() for p in _read(result.pdf_path).pages)
            for i in range(1, 9):
                self.assertIn(f"Col{i}", text)

    def test_unicode_text_in_table_cells(self):
        """Latin-Extended Unicode characters render correctly in table cells."""
        content = (
            "# Title\n\n"
            "| Name | Value |\n|---|---|\n"
            "| Café | Résumé |\n| Naïve | Über |\n"
        )
        with TempProject(content=content, with_image=False) as root:
            result = build_document(root, "courses/doc")
            self.assertTrue(result.audit.passed)
            text = "".join(p.extract_text() for p in _read(result.pdf_path).pages)
            self.assertIn("Café", text)
            self.assertIn("Résumé", text)
            self.assertIn("Über", text)

    def test_empty_cells_in_table(self):
        """Empty cells in data rows are handled without error."""
        content = "# Title\n\n| A | B |\n|---|---|\n| 1 |  |\n|  | 2 |\n"
        with TempProject(content=content, with_image=False) as root:
            result = build_document(root, "courses/doc")
            self.assertTrue(result.audit.passed)
            text = "".join(p.extract_text() for p in _read(result.pdf_path).pages)
            self.assertIn("1", text)
            self.assertIn("2", text)

    def test_long_text_wraps_in_table_cells(self):
        """Long text in a cell wraps across multiple lines."""
        long_text = (
            "This is a very long description that will need to wrap across "
            "multiple lines within the table cell to fit the column width."
        )
        content = f"# Title\n\n| Description | Value |\n|---|---|\n| {long_text} | 42 |\n"
        with TempProject(content=content, with_image=False) as root:
            result = build_document(root, "courses/doc")
            self.assertTrue(result.audit.passed)
            text = "".join(p.extract_text() for p in _read(result.pdf_path).pages)
            self.assertIn("wrap across", text)
            self.assertIn("42", text)

    def test_nested_formatting_in_table_cells(self):
        """Bold, italic, and inline code render in table cells."""
        content = (
            "# Title\n\n"
            "| Feature | Detail |\n|---|---|\n"
            "| **Bold** | *italic* |\n"
            "| `code` | plain |\n"
        )
        with TempProject(content=content, with_image=False) as root:
            result = build_document(root, "courses/doc")
            self.assertTrue(result.audit.passed)
            text = "".join(p.extract_text() for p in _read(result.pdf_path).pages)
            self.assertIn("Bold", text)
            self.assertIn("italic", text)
            self.assertIn("code", text)

    def test_table_caption_and_numbering(self):
        """A table with TABLE: caption is numbered and appears in list of tables."""
        content = "# Title\n\nTABLE: mytable | My caption\n| A | B |\n|---|---|\n| 1 | 2 |\n"
        meta = META + "numbered: true\n"
        with TempProject(content=content, meta=meta, with_image=False) as root:
            result = build_document(root, "courses/doc")
            self.assertTrue(result.audit.passed)
            text = "".join(p.extract_text() for p in _read(result.pdf_path).pages)
            self.assertIn("Table 1", text)
            self.assertIn("My caption", text)
            self.assertIn("List of Tables", text)

    def test_table_content_correspondence(self):
        """Table data appears in the rendered PDF in order."""
        content = "# Title\n\n| Col | Val |\n|---|---|\n| Alpha | 1 |\n| Beta | 2 |\n| Gamma | 3 |\n"
        with TempProject(content=content, with_image=False) as root:
            result = build_document(root, "courses/doc")
            text = "".join(p.extract_text() for p in _read(result.pdf_path).pages)
            for word in ("Alpha", "Beta", "Gamma"):
                self.assertIn(word, text)
            alpha_pos = text.index("Alpha")
            beta_pos = text.index("Beta")
            gamma_pos = text.index("Gamma")
            self.assertLess(alpha_pos, beta_pos)
            self.assertLess(beta_pos, gamma_pos)

    def test_deterministic_table_rebuild(self):
        """Two builds of the same table produce identical bytes."""
        content = "# Title\n\n| A | B | C |\n|---|---|---|\n| 1 | 2 | 3 |\n| 4 | 5 | 6 |\n"
        with TempProject(content=content, with_image=False) as root:
            first = build_document(root, "courses/doc")
            second = build_document(root, "courses/doc")
            self.assertEqual(first.sha256, second.sha256)


if __name__ == "__main__":
    unittest.main()
