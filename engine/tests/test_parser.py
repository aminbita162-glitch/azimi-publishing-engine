import unittest

from engine.build.parser import (
    BulletList,
    Callout,
    Code,
    Heading,
    Image,
    NumberedList,
    PageBreak,
    Paragraph,
    Table,
    parse,
)
from engine.errors import ContentError


class ParserTests(unittest.TestCase):
    def test_headings_and_paragraphs(self):
        blocks = parse("# One\n\nFirst line\ncontinues here.\n\n## Two\n")
        self.assertEqual(blocks[0], Heading(line=1, level=1, text="One"))
        self.assertEqual(blocks[1], Paragraph(line=3, text="First line continues here."))
        self.assertEqual(blocks[2], Heading(line=6, level=2, text="Two"))

    def test_bullet_and_numbered_lists(self):
        blocks = parse("- a\n- b\n\n1. x\n2. y\n")
        self.assertEqual(blocks[0], BulletList(line=1, items=("a", "b")))
        self.assertEqual(blocks[1], NumberedList(line=4, items=("x", "y")))

    def test_code_block_keeps_content_verbatim(self):
        text = "~~~python\ndef f():\n    return 1  # <b> not html here\n~~~\n"
        block = parse(text)[0]
        self.assertEqual(block, Code(line=1, language="python", lines=("def f():", "    return 1  # <b> not html here")))

    def test_code_block_requires_language(self):
        with self.assertRaisesRegex(ContentError, "line 1: code fence requires a language label"):
            parse("~~~\ncode\n~~~\n")

    def test_code_block_must_close(self):
        with self.assertRaisesRegex(ContentError, "line 1: code block is not closed"):
            parse("~~~python\ncode\n")

    def test_table(self):
        text = "| A | B |\n|---|:-:|\n| 1 | 2 |\n| 3 | 4 |\n"
        block = parse(text)[0]
        self.assertEqual(
            block,
            Table(line=1, header=("A", "B"), rows=(("1", "2"), ("3", "4")), align=("left", "center")),
        )

    def test_table_alignment_markers(self):
        block = parse("| A | B | C |\n|:--|:-:|--:|\n| 1 | 2 | 3 |\n")[0]
        self.assertEqual(block.align, ("left", "center", "right"))

    def test_table_requires_separator(self):
        with self.assertRaisesRegex(ContentError, "separator"):
            parse("| A | B |\n| 1 | 2 |\n| 3 | 4 |\n")

    def test_table_row_width_must_match(self):
        with self.assertRaisesRegex(ContentError, "line 4: table row has 3 cells, expected 2"):
            parse("| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 | 5 |\n")

    def test_table_needs_data_row(self):
        with self.assertRaisesRegex(ContentError, "at least one data row"):
            parse("| A | B |\n|---|---|\n")

    def test_image_with_caption(self):
        block = parse("IMG: assets/diagram.png | Pipeline overview | Figure 1\n")[0]
        self.assertEqual(block, Image(line=1, path="assets/diagram.png", alt="Pipeline overview", caption="Figure 1"))

    def test_image_without_caption(self):
        block = parse("IMG: assets/diagram.png | Pipeline overview\n")[0]
        self.assertIsNone(block.caption)

    def test_image_alt_is_mandatory(self):
        with self.assertRaisesRegex(ContentError, "alt text is mandatory"):
            parse("IMG: assets/diagram.png |  | caption\n")
        with self.assertRaises(ContentError):
            parse("IMG: assets/diagram.png\n")

    def test_image_path_rules(self):
        bad_paths = [
            "https://example.com/a.png",
            "/etc/a.png",
            "../a.png",
            "assets/../a.png",
            "assets\\a.png",
            "assets/a.gif",
            "assets/a.svg",
        ]
        for path in bad_paths:
            with self.subTest(path=path):
                with self.assertRaises(ContentError):
                    parse(f"IMG: {path} | alt\n")

    def test_callouts(self):
        blocks = parse("NOTE: Remember this.\n\nWARNING: Be careful.\n")
        self.assertEqual(blocks[0], Callout(line=1, kind="NOTE", text="Remember this."))
        self.assertEqual(blocks[1], Callout(line=3, kind="WARNING", text="Be careful."))

    def test_all_callout_kinds(self):
        for kind in ("NOTE", "WARNING", "TIP", "KEY", "CHECKPOINT"):
            with self.subTest(kind=kind):
                block = parse(f"{kind}: Text of the box.\n")[0]
                self.assertEqual(block, Callout(line=1, kind=kind, text="Text of the box."))

    def test_unknown_callout_label_is_plain_text(self):
        self.assertIsInstance(parse("DANGER: not a box.\n")[0], Paragraph)

    def test_page_break(self):
        blocks = parse("A\n\nPAGEBREAK\n\nB\n")
        self.assertIsInstance(blocks[1], PageBreak)

    def test_heading_depth_limit(self):
        with self.assertRaisesRegex(ContentError, "line 5: heading depth exceeds 3"):
            parse("# A\n\n## B\n\n#### C\n")

    def test_heading_level_may_not_skip(self):
        with self.assertRaisesRegex(ContentError, "line 3: heading level skips a level"):
            parse("# A\n\n### C\n")

    def test_first_heading_must_be_level_one(self):
        with self.assertRaisesRegex(ContentError, "skips a level"):
            parse("## A\n")

    def test_raw_html_rejected(self):
        for text in ("Hello <b>x</b>", "A <script>x</script>", "# Title <i>", "- item <br>", "| A |\n|---|\n| <a> |"):
            with self.subTest(text=text):
                with self.assertRaisesRegex(ContentError, "raw HTML"):
                    parse(text + "\n")

    def test_comparison_symbols_are_not_html(self):
        blocks = parse("Use a < b and 3 > 2 in the comparison.\n")
        self.assertEqual(len(blocks), 1)

    def test_tabs_rejected_outside_code(self):
        with self.assertRaisesRegex(ContentError, "tab characters"):
            parse("Hello\tworld\n")

    def test_paragraph_must_be_followed_by_blank_line(self):
        with self.assertRaisesRegex(ContentError, "line 2: a paragraph must be followed by a blank line"):
            parse("Text\n- item\n")

    def test_list_must_be_followed_by_blank_line(self):
        with self.assertRaisesRegex(ContentError, "line 3: a list must be followed by a blank line"):
            parse("- a\n- b\ntext\n")

    def test_line_endings_are_normalized(self):
        blocks = parse("# A\r\n\r\nText\r\n")
        self.assertEqual([type(b) for b in blocks], [Heading, Paragraph])

    def test_empty_content(self):
        self.assertEqual(parse(""), [])
        self.assertEqual(parse("\n\n  \n"), [])

    def test_parsing_is_deterministic(self):
        text = "# A\n\nText\n\n- a\n- b\n\n~~~sh\nls\n~~~\n"
        self.assertEqual(parse(text), parse(text))


if __name__ == "__main__":
    unittest.main()
