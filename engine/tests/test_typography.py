import io
import unittest

from pypdf import PdfReader

from engine.build.builder import build_document
from engine.render.inline import NBSP, to_markup, to_plain
from engine.tests.support import TempProject

CONTENT = """# Alpha {#alpha}

He said "stop" and it's final - really. See `don't "quote"` and [[alpha]].

The `x - y` stays. **"Bold" quote** and (the "end").
"""


class TypographyTests(unittest.TestCase):
    def test_double_quotes_become_curly_pairs(self):
        self.assertEqual(to_plain('say "go" now'), "say \u201cgo\u201d now")

    def test_quote_after_emphasis_marker_opens(self):
        self.assertEqual(to_plain('**"Bold" quote**'), "\u201cBold\u201d quote")

    def test_quote_after_bracket_opens(self):
        self.assertEqual(to_plain('(the "end")'), "(the \u201cend\u201d)")

    def test_apostrophe_is_curly(self):
        self.assertEqual(to_plain("it's final"), "it\u2019s final")

    def test_spaced_hyphen_becomes_en_dash(self):
        self.assertEqual(to_plain("A - VALID"), "A \u2013 VALID")

    def test_hyphen_inside_words_and_flags_is_kept(self):
        self.assertEqual(to_plain("well-known"), "well-known")
        self.assertEqual(to_plain("a --flag"), "a --flag")

    def test_inline_code_and_addresses_are_not_changed(self):
        self.assertIn("don't \"quote\"", to_markup("`don't \"quote\"`").replace("&quot;", '"'))
        self.assertIn("https://example.com/a-b", to_markup("see https://example.com/a-b now"))

    def test_number_labels_use_a_non_breaking_space(self):
        self.assertEqual(NBSP, "\u00a0")
        markup = to_markup("[[fig]]", refs={"fig": f"Figure{NBSP}1"})
        self.assertIn(f"Figure{NBSP}1", markup)

    def test_built_pdf_uses_typographic_characters_in_prose(self):
        with TempProject(content=CONTENT, with_image=False) as root:
            result = build_document(root, "courses/doc")
            text = " ".join(page.extract_text() for page in PdfReader(io.BytesIO(result.pdf_path.read_bytes())).pages)
        self.assertIn("\u201cstop\u201d", text)
        self.assertIn("it\u2019s final", text)
        self.assertIn("final \u2013 really", text)
        self.assertNotIn('"stop"', text)


if __name__ == "__main__":
    unittest.main()
