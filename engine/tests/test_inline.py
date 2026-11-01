import unittest

from engine.errors import ContentError
from engine.render.inline import to_markup, to_plain


class InlineTests(unittest.TestCase):
    def test_plain_text_is_escaped(self):
        self.assertEqual(to_markup("A & B < C > D"), "A &amp; B &lt; C &gt; D")

    def test_bold_and_italic(self):
        self.assertEqual(to_markup("a **b** c *d* e"), "a <b>b</b> c <i>d</i> e")

    def test_nesting(self):
        self.assertEqual(to_markup("*a **b** c*"), "<i>a <b>b</b> c</i>")

    def test_inline_code_is_literal(self):
        self.assertEqual(
            to_markup("use `a * b < c` here"),
            'use <font face="Mono" size="9.2">a * b &lt; c</font> here',
        )

    def test_spaced_asterisks_are_literal(self):
        self.assertEqual(to_markup("2 * 3 * 4"), "2 * 3 * 4")

    def test_unclosed_emphasis(self):
        for text in ("**bold", "*italic", "a **b"):
            with self.subTest(text=text):
                with self.assertRaisesRegex(ContentError, "not closed"):
                    to_markup(text)

    def test_unclosed_code(self):
        with self.assertRaisesRegex(ContentError, "inline code is not closed"):
            to_markup("a `b")
        with self.assertRaisesRegex(ContentError, "inline code is not closed"):
            to_markup("a `` b")

    def test_crossing_markers(self):
        with self.assertRaisesRegex(ContentError, "cross"):
            to_markup("**a *b** c*")

    def test_ambiguous_triple_marker(self):
        with self.assertRaisesRegex(ContentError, "ambiguous"):
            to_markup("***a***")

    def test_error_carries_line_number(self):
        with self.assertRaisesRegex(ContentError, "line 7:"):
            to_markup("**a", line=7)

    def test_plain_text_strips_markers(self):
        self.assertEqual(to_plain("The **core** of `code` & more"), "The core of code & more")

    def test_markup_is_deterministic(self):
        text = "a **b** *c* `d` & e"
        self.assertEqual(to_markup(text), to_markup(text))


if __name__ == "__main__":
    unittest.main()
