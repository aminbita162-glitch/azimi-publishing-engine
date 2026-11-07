"""Phase 2: layout and page-fill contract regressions."""
import unittest
from pathlib import Path
from engine.audit.pdf_audit import MAX_BLANK_RATIO
from engine.render.styles import PAGE_HEIGHT, MARGIN_TOP, MARGIN_BOTTOM

class PaginationContractTests(unittest.TestCase):
    def test_minimum_body_coverage_is_87_percent(self):
        self.assertAlmostEqual(MAX_BLANK_RATIO, 0.13)
    def test_body_area_is_positive(self):
        self.assertGreater(PAGE_HEIGHT - MARGIN_TOP - MARGIN_BOTTOM, 0)
    def test_forced_chapter_break_option_is_preserved(self):
        source = (Path(__file__).resolve().parents[1] / "render" / "document.py").read_text()
        self.assertIn("if chapter_pages:", source)
        self.assertIn("_break_page(story)", source)
    def test_conditional_chapter_break_remains(self):
        source = (Path(__file__).resolve().parents[1] / "render" / "document.py").read_text()
        self.assertIn("CondPageBreak(CHAPTER_MIN_SPACE)", source)

if __name__ == "__main__":
    unittest.main()
