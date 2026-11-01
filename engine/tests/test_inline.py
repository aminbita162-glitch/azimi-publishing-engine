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

    def test_addresses_become_links(self):
        markup = to_markup("see github.com/owner/repo, and docs.python.org/3/library/json.html.")
        self.assertIn('<a href="https://github.com/owner/repo" color="#0B5CAD">github.com/owner/repo</a>,', markup)
        self.assertIn('href="https://docs.python.org/3/library/json.html"', markup)
        self.assertTrue(markup.endswith("</a>."))

    def test_full_urls_keep_their_scheme_and_escape_ampersands(self):
        markup = to_markup("open http://example.com/a?b=1&c=2 now")
        self.assertIn('href="http://example.com/a?b=1&amp;c=2"', markup)

    def test_file_names_are_not_links(self):
        for text in ("session01_reference.py", "app-config.json", "core/human_authority.py", "Number.isSafeInteger"):
            with self.subTest(text=text):
                self.assertNotIn("<a ", to_markup(text))

    def test_inline_code_is_never_linked(self):
        self.assertNotIn("<a ", to_markup("use `github.com/owner/repo` here"))

    def test_only_http_schemes_are_produced(self):
        self.assertNotIn('href="javascript', to_markup("javascript:alert(1) and ftp://example.com"))
        self.assertNotIn('href="ftp', to_markup("javascript:alert(1) and ftp://example.com"))

    def test_markup_is_deterministic(self):
        text = "a **b** *c* `d` & e"
        self.assertEqual(to_markup(text), to_markup(text))


if __name__ == "__main__":
    unittest.main()
