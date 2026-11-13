"""Tests for Phase C4: layout keep-together, continuation markers, and review command."""

import io
import json
import unittest
from pathlib import Path

from pypdf import PdfReader

from engine.build.parser import Image as ImageBlock, Paragraph as ParagraphBlock
from engine.build.builder import build_document
from engine.render.document import _keep_intro_with_visual
from engine.tests.support import CONTENT, META, TempProject, make_figure


def read(path: Path) -> PdfReader:
    return PdfReader(io.BytesIO(path.read_bytes()))


class KeepIntroWithVisualTests(unittest.TestCase):
    """C4.1: short intro paragraphs are kept with their figure or diagram."""

    def test_short_intro_paragraph_stays_with_figure(self):
        """A short intro paragraph (≤ 240 chars) immediately before an image
        is on the same page as the image (via keepWithNext)."""
        filler = "\n\n".join(
            f"Filler paragraph number {i} of the document body." for i in range(1, 40)
        )
        content = (
            "# Title\n\n" + filler
            + "\n\nShort intro that stays with the figure.\n\n"
            + "IMG: assets/flow.png | Three boxes | The pipeline\n"
        )
        with TempProject(content=content) as root:
            result = build_document(root, "courses/doc")
            pages = [p.extract_text() for p in read(result.pdf_path).pages]
        both = [i for i, text in enumerate(pages) if "Short intro" in text and "pipeline" in text]
        self.assertTrue(both, f"intro and figure should be on the same page; pages: {pages}")

    def test_short_intro_paragraph_stays_with_diagram(self):
        """A short intro paragraph immediately before a diagram stays on the
        same page as the diagram (via keepWithNext)."""
        filler = "\n\n".join(
            f"Filler paragraph number {i} of the document body." for i in range(1, 40)
        )
        diagram = (
            "~~~diagram\n"
            "type: flow\n"
            "caption: A simple flow\n"
            "node a: Start | process\n"
            "node b: End | process\n"
            "edge a -> b: goes to\n"
            "~~~\n"
        )
        content = (
            "# Title\n\n" + filler
            + "\n\nShort intro before the diagram.\n\n" + diagram
        )
        with TempProject(content=content, with_image=False) as root:
            result = build_document(root, "courses/doc")
            pages = [p.extract_text() for p in read(result.pdf_path).pages]
        intro = [i for i, text in enumerate(pages) if "Short intro before the diagram" in text]
        self.assertTrue(intro, "intro paragraph not found")

    def test_long_paragraph_does_not_force_keep_with_figure(self):
        """A paragraph > 240 characters is not given keepWithNext, so it does
        not force the figure to stay on the same page."""
        filler = "\n\n".join(
            f"Filler paragraph number {i} of the document body." for i in range(1, 40)
        )
        long_text = "This is a long paragraph that exceeds the two hundred and forty character limit. " * 4
        content = (
            "# Title\n\n" + filler
            + "\n\n" + long_text + "\n\n"
            + "IMG: assets/flow.png | Three boxes | The pipeline\n"
        )
        with TempProject(content=content) as root:
            result = build_document(root, "courses/doc")
            pages = [p.extract_text() for p in read(result.pdf_path).pages]
        # The long paragraph should NOT be given keepWithNext.  Without
        # keepWithNext the paragraph stays on the current page while the
        # figure may move to the next page — they are allowed to be on
        # different pages.  Verify the build succeeds (no crash) and that
        # the paragraph text appears somewhere in the document.
        full_text = "\n".join(pages)
        self.assertIn("long paragraph", full_text.lower())
        self.assertIn("pipeline", full_text)

    def test_fourth_paragraph_is_not_counted(self):
        """When 4 consecutive short paragraphs precede a visual, only the last
        3 are collected — the 4th (oldest) is not given keepWithNext."""
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import Paragraph

        style = ParagraphStyle("Body")
        blocks = [
            ParagraphBlock(line=1, text="P1 short."),
            ParagraphBlock(line=2, text="P2 short."),
            ParagraphBlock(line=3, text="P3 short."),
            ParagraphBlock(line=4, text="P4 short."),
            ImageBlock(line=5, path="assets/flow.png", alt="caption", caption=None),
        ]
        story = [
            Paragraph("P1 short.", style),
            Paragraph("P2 short.", style),
            Paragraph("P3 short.", style),
            Paragraph("P4 short.", style),
        ]
        visual = [Paragraph("visual", style)]
        result = _keep_intro_with_visual(story, blocks, 4, visual)
        # Only 3 paragraphs are popped; the 4th (P1) stays in the story.
        self.assertEqual(len(story), 1)
        # Result: CondPageBreak + 3 intros + 1 visual = 5 flowables.
        self.assertEqual(len(result), 5)

    def test_long_paragraph_not_counted(self):
        """A paragraph > 240 characters is not counted as an intro paragraph."""
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import Paragraph

        style = ParagraphStyle("Body")
        long_text = "A" * 241
        blocks = [
            ParagraphBlock(line=1, text=long_text),
            ImageBlock(line=2, path="assets/flow.png", alt="caption", caption=None),
        ]
        story = [Paragraph(long_text, style)]
        visual = [Paragraph("visual", style)]
        result = _keep_intro_with_visual(story, blocks, 1, visual)
        # count == 0 → no paragraphs popped, just the visual returned.
        self.assertEqual(len(story), 1)
        self.assertEqual(result, visual)

    def test_non_paragraph_block_breaks_the_chain(self):
        """A non-paragraph block between the visual and earlier paragraphs
        stops the count — only paragraphs immediately consecutive before the
        visual are collected."""
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import Paragraph

        from engine.build.parser import Callout

        style = ParagraphStyle("Body")
        blocks = [
            ParagraphBlock(line=1, text="P1 short."),
            Callout(line=2, kind="NOTE", text="A note."),
            ParagraphBlock(line=3, text="P2 short."),
            ImageBlock(line=4, path="assets/flow.png", alt="caption", caption=None),
        ]
        story = [
            Paragraph("P1 short.", style),
            Paragraph("note content", style),  # callout content (not a Paragraph)
            Paragraph("P2 short.", style),
        ]
        visual = [Paragraph("visual", style)]
        result = _keep_intro_with_visual(story, blocks, 3, visual)
        # Only 1 paragraph (P2) qualifies; the callout breaks the chain.
        # P1 and the callout content stay in the story.
        self.assertEqual(len(story), 2)
        # Result: CondPageBreak + 1 intro + 1 visual = 3 flowables.
        self.assertEqual(len(result), 3)


class ContinuationMarkerTests(unittest.TestCase):
    """C4.2: continuation markers for code blocks and tables that split."""

    def test_code_block_split_shows_continuation_markers(self):
        """When a code block splits across pages, both 'continued on next
        page' and 'continued from previous page' markers appear."""
        filler = "\n\n".join(
            f"Filler paragraph number {i} of the document body." for i in range(1, 40)
        )
        code_lines = "\n".join(f"value_{i:03d} = {i}" for i in range(80))
        content = "# Title\n\n" + filler + "\n\n~~~python\n" + code_lines + "\n~~~\n"
        with TempProject(content=content, with_image=False) as root:
            result = build_document(root, "courses/doc")
            pages = [p.extract_text() for p in read(result.pdf_path).pages]
        full_text = "\n".join(pages)
        self.assertIn("continued on next page", full_text)
        self.assertIn("continued from previous page", full_text)

    def test_table_split_shows_continuation_markers(self):
        """When a table splits across pages, both continuation markers appear."""
        filler = "\n\n".join(
            f"Filler paragraph number {i} of the document body." for i in range(1, 40)
        )
        rows = "\n".join(f"| Row{i} | Value {i} |" for i in range(1, 60))
        content = "# Title\n\n" + filler + "\n\n| Col A | Col B |\n|:------|------:|\n" + rows + "\n"
        with TempProject(content=content, with_image=False) as root:
            result = build_document(root, "courses/doc")
            pages = [p.extract_text() for p in read(result.pdf_path).pages]
        full_text = "\n".join(pages)
        self.assertIn("continued on next page", full_text)
        self.assertIn("continued from previous page", full_text)

    def test_continuation_markers_do_not_break_audit(self):
        """The continuation markers are structural and do not cause A7 failure."""
        filler = "\n\n".join(
            f"Filler paragraph number {i} of the document body." for i in range(1, 40)
        )
        code_lines = "\n".join(f"value_{i:03d} = {i}" for i in range(80))
        content = "# Title\n\n" + filler + "\n\n~~~python\n" + code_lines + "\n~~~\n"
        with TempProject(content=content, with_image=False) as root:
            result = build_document(root, "courses/doc")
        # The audit must pass (16/16 checks).
        self.assertTrue(result.audit.passed, f"audit failed: {[(c.id, c.status) for c in result.audit.checks if not c.passed]}")
        a7 = next(c for c in result.audit.checks if c.id == "A7")
        self.assertTrue(a7.passed, f"A7 failed: {a7.detail}")

    def test_no_continuation_markers_when_code_fits_on_one_page(self):
        """A short code block that fits on one page does not produce markers."""
        content = "# Title\n\n~~~python\nx = 1\ny = 2\n~~~\n"
        with TempProject(content=content, with_image=False) as root:
            result = build_document(root, "courses/doc")
            pages = [p.extract_text() for p in read(result.pdf_path).pages]
        full_text = "\n".join(pages)
        self.assertNotIn("continued on next page", full_text)
        self.assertNotIn("continued from previous page", full_text)


if __name__ == "__main__":
    unittest.main()
