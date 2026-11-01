import tempfile
import unittest
from pathlib import Path

from engine.errors import ConfigError
from engine.schemas.meta import Meta, load_meta, parse_meta

VALID = {
    "title": "Agentic Systems Foundations",
    "author": "Amin Azimi",
    "audience": "Senior engineers with seven or more years of experience",
    "language": "en",
    "version": "1.0.0",
    "output_name": "session-01",
}


class ParseMetaTests(unittest.TestCase):
    def test_valid_minimal(self):
        meta = parse_meta(dict(VALID))
        self.assertIsInstance(meta, Meta)
        self.assertEqual(meta.brand, "default")
        self.assertIsNone(meta.subtitle)

    def test_valid_full(self):
        data = dict(VALID, subtitle="Session 01", brand="azimi-lab", language="en-US")
        meta = parse_meta(data)
        self.assertEqual(meta.subtitle, "Session 01")
        self.assertEqual(meta.brand, "azimi-lab")
        self.assertEqual(meta.language, "en-US")

    def test_text_is_stripped(self):
        meta = parse_meta(dict(VALID, title="  Title  "))
        self.assertEqual(meta.title, "Title")

    def test_missing_key(self):
        data = dict(VALID)
        del data["author"]
        with self.assertRaisesRegex(ConfigError, "missing required keys: author"):
            parse_meta(data)

    def test_unknown_key(self):
        with self.assertRaisesRegex(ConfigError, "unknown keys: extra"):
            parse_meta(dict(VALID, extra="x"))

    def test_not_a_mapping(self):
        with self.assertRaises(ConfigError):
            parse_meta(["a", "b"])

    def test_wrong_type(self):
        with self.assertRaisesRegex(ConfigError, "title must be text"):
            parse_meta(dict(VALID, title=5))

    def test_empty_text(self):
        with self.assertRaisesRegex(ConfigError, "must not be empty"):
            parse_meta(dict(VALID, title="   "))

    def test_title_too_long(self):
        with self.assertRaisesRegex(ConfigError, "exceeds 200"):
            parse_meta(dict(VALID, title="x" * 201))

    def test_control_characters(self):
        with self.assertRaisesRegex(ConfigError, "control characters"):
            parse_meta(dict(VALID, title="a\x00b"))

    def test_bad_version(self):
        for bad in ("1.0", "v1.0.0", "1.0.0-beta", "1.0.x"):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(ConfigError, "version"):
                    parse_meta(dict(VALID, version=bad))

    def test_bad_language(self):
        for bad in ("english", "EN", "e", "en_US"):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(ConfigError, "language"):
                    parse_meta(dict(VALID, language=bad))

    def test_bad_output_name(self):
        for bad in ("../x", "a/b", "a b", "-x", "a..b", ".hidden"):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(ConfigError, "output_name"):
                    parse_meta(dict(VALID, output_name=bad))

    def test_bad_brand(self):
        for bad in ("Azimi", "a/b", "-x", "a b"):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(ConfigError, "brand"):
                    parse_meta(dict(VALID, brand=bad))


class LoadMetaTests(unittest.TestCase):
    def test_load_valid_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "meta.yaml"
            path.write_text(
                "title: Agentic Systems\nauthor: Amin Azimi\naudience: Senior engineers\n"
                "language: en\nversion: 1.0.0\noutput_name: session-01\n",
                encoding="utf-8",
            )
            meta = load_meta(path)
            self.assertEqual(meta.output_name, "session-01")

    def test_version_written_as_float_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "meta.yaml"
            path.write_text(
                "title: T\nauthor: A\naudience: B\nlanguage: en\nversion: 1.0\noutput_name: x\n",
                encoding="utf-8",
            )
            with self.assertRaises(ConfigError):
                load_meta(path)

    def test_missing_file(self):
        with self.assertRaises(ConfigError):
            load_meta("/nonexistent/meta.yaml")

    def test_invalid_yaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "meta.yaml"
            path.write_text("title: [unclosed\n", encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "invalid YAML"):
                load_meta(path)


if __name__ == "__main__":
    unittest.main()
