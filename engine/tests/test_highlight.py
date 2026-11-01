import unittest

from engine.render.document import _wrap_with_classes
from engine.render.highlight import PLAIN, classify, normalize_language, to_markup


def letters(source, language):
    return ["".join(line) for line in classify(source.split("\n"), language)]


class ClassifyTests(unittest.TestCase):
    def test_python_keywords_strings_comments_numbers(self):
        result = letters('x = 5 if a else "s"  # tail', "python")[0]
        self.assertEqual(result[4], "n")
        self.assertEqual(result[6:8], "kk")
        self.assertEqual(result[16:19], "sss")
        self.assertEqual(result[-6:], "cccccc")

    def test_python_definition_names(self):
        result = letters("def run(task):", "python")[0]
        self.assertEqual(result[:3], "kkk")
        self.assertEqual(result[4:7], "fff")
        result = letters("class Proposal:", "python")[0]
        self.assertEqual(result[6:14], "ffffffff")

    def test_python_multiline_docstring_is_one_string(self):
        lines = letters('"""one\ntwo"""\nx = 1', "python")
        self.assertEqual(set(lines[0]), {"s"})
        self.assertEqual(set(lines[1]), {"s"})
        self.assertEqual(lines[2][4], "n")

    def test_comment_marker_inside_a_string_is_not_a_comment(self):
        result = letters('print("a # b")', "python")[0]
        self.assertNotIn("c", result)

    def test_typescript(self):
        result = letters('export const A = new Set(["x"]); // note', "typescript")[0]
        self.assertEqual(result[:6], "kkkkkk")
        self.assertEqual(result[-6:], "cccccc")
        self.assertIn("s", result)

    def test_shell_comment_needs_a_space_before_it(self):
        self.assertIn("c", letters("ls  # list", "sh")[0])
        self.assertNotIn("c", letters("echo a#b", "sh")[0])

    def test_sql_keywords_are_case_insensitive(self):
        result = letters("select 1 FROM t", "sql")[0]
        self.assertEqual(result[:6], "kkkkkk")
        self.assertEqual(result[9:13], "kkkk")

    def test_json_and_yaml(self):
        self.assertEqual(letters('{"a": true, "b": 2}', "json")[0].count("k"), 4)
        yaml_result = letters("name: value  # c\nflag: true", "yaml")
        self.assertEqual(yaml_result[0][:4], "ffff")
        self.assertTrue(yaml_result[0].endswith("ccc"))

    def test_unknown_language_is_plain(self):
        self.assertEqual(set(letters("anything = 1", "text")[0]), {PLAIN})

    def test_language_aliases(self):
        self.assertEqual(normalize_language("PY"), "python")
        self.assertEqual(normalize_language("bash"), "sh")
        self.assertEqual(normalize_language("TS"), "typescript")

    def test_one_class_letter_per_character(self):
        source = 'def f(a):\n    """d\n    e"""\n    return a  # x\n'.rstrip("\n").split("\n")
        for line, line_classes in zip(source, classify(source, "python")):
            self.assertEqual(len(line), len(line_classes))

    def test_classification_is_deterministic(self):
        source = ['def f():', '    return "a"  # b']
        self.assertEqual(classify(source, "python"), classify(source, "python"))


class MarkupTests(unittest.TestCase):
    def test_markup_escapes_and_colors(self):
        markup = to_markup('a < "b"', ["p"] * 4 + ["s"] * 3, {"s": "#0F766E"})
        self.assertEqual(markup, 'a &lt; <font color="#0F766E">"b"</font>')

    def test_keywords_are_bold(self):
        self.assertEqual(to_markup("if", ["k", "k"], {"k": "#000000"}), '<font color="#000000"><b>if</b></font>')


class WrapTests(unittest.TestCase):
    def test_short_line_is_untouched(self):
        self.assertEqual(_wrap_with_classes("abc", list("ppp"), 10), [("abc", list("ppp"))])

    def test_wrap_prefers_spaces_and_keeps_classes_aligned(self):
        text = "alpha beta gamma delta"
        classes = list("kkkkk" + "p" + "ssss" + "p" + "nnnnn" + "p" + "ccccc")
        pieces = _wrap_with_classes(text, classes, 12)
        self.assertGreater(len(pieces), 1)
        for piece, piece_classes in pieces:
            self.assertEqual(len(piece), len(piece_classes))
            self.assertLessEqual(len(piece), 12)
        self.assertTrue(pieces[1][0].startswith("  "))
        joined = " ".join(piece.strip() for piece, _ in pieces)
        self.assertEqual(joined, text)

    def test_unbreakable_text_is_split_without_loss(self):
        text = "q" * 100
        pieces = _wrap_with_classes(text, ["p"] * 100, 30)
        self.assertEqual(sum(piece.count("q") for piece, _ in pieces), 100)


if __name__ == "__main__":
    unittest.main()
