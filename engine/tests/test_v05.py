"""Tests for the 0.5.0 features: lint, font families, check, verify, new, preview, audit A14 to A16."""

import importlib.util
import io
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml
from pypdf import PdfReader, PdfWriter

from engine.audit import audit_pdf
from engine.build.builder import build_document, check_document, verify_document
from engine.build.parser import parse
from engine.cli import main
from engine.errors import ConfigError, ContentError
from engine.lint import lint, load_forbidden_terms
from engine.render.fonts import available_families, load_registry, register_fonts
from engine.schemas.meta import parse_meta
from engine.tests.support import CONTENT, META, TempProject


class LintTests(unittest.TestCase):
    def test_forbidden_terms_are_found_in_text_and_code(self):
        blocks = parse("# One\n\nWe use Secretword here.\n\n~~~text\nsecretword inside code\n~~~\n")
        issues = lint(blocks, ["secretword"])
        self.assertEqual([i.line for i in issues], [3, 5])

    def test_term_inside_a_longer_word_is_not_a_match(self):
        self.assertEqual(lint(parse("# One\n\nSecretwords are fine.\n"), ["secretword"]), [])

    def test_repeated_words_are_reported_but_allowed_pairs_are_not(self):
        self.assertEqual(len(lint(parse("# One\n\nThe the cat.\n"), [])), 1)
        self.assertEqual(lint(parse("# One\n\nI know that that works.\n"), []), [])

    def test_course_profile_requires_objectives_and_summary(self):
        issues = lint(parse("# One\n\nText.\n"), [], "course")
        self.assertEqual(len(issues), 2)
        good = "# One\n\nOBJECTIVES: Learn it.\n\nKEY: Chapter summary. Done.\n"
        self.assertEqual(lint(parse(good), [], "course"), [])
        self.assertEqual(lint(parse("# Appendix {.nonum}\n\nText.\n".replace("{.nonum}", "{#app .nonum}")), [], "course"), [])

    def test_forbidden_file_is_read_with_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "forbidden.txt").write_text("# note\nalpha\n\nbeta gamma\n", encoding="utf-8")
            self.assertEqual(load_forbidden_terms(Path(tmp)), ("alpha", "beta gamma"))
            self.assertEqual(load_forbidden_terms(Path(tmp) / "missing"), ())

    def test_build_stops_on_a_forbidden_term(self):
        with TempProject() as root:
            (root / "brand" / "default" / "forbidden.txt").write_text("foundations\n", encoding="utf-8")
            with self.assertRaises(ContentError) as raised:
                build_document(root, "courses/doc")
            self.assertIn("lint found", str(raised.exception))


class FontTests(unittest.TestCase):
    def make_family(self, root: Path):
        fonts = root / "design-system" / "fonts"
        names = {"regular": "Carlito-Regular.ttf", "bold": "Carlito-Bold.ttf",
                 "italic": "Carlito-Italic.ttf", "bolditalic": "Carlito-BoldItalic.ttf"}
        entry = {}
        sums = (fonts / "SHA256SUMS").read_text(encoding="utf-8")
        for style, name in names.items():
            copy = f"Alt-{name}"
            shutil.copy(fonts / name, fonts / copy)
            entry[style] = copy
            digest = next(line.split()[0] for line in sums.splitlines() if line.endswith(name))
            sums += f"{digest}  {copy}\n"
        (fonts / "SHA256SUMS").write_text(sums, encoding="utf-8")
        (fonts / "fonts.yaml").write_text(yaml.safe_dump({"families": {"alt-sans": entry}}), encoding="utf-8")

    def test_default_family_and_listing(self):
        with TempProject() as root:
            fonts = root / "design-system" / "fonts"
            self.assertEqual(available_families(fonts), ["carlito"])
            self.assertIn("Carlito-Regular.ttf", register_fonts(fonts))

    def test_a_registered_family_can_be_chosen_and_builds(self):
        with TempProject(meta=META + "font: alt-sans\n") as root:
            self.make_family(root)
            self.assertEqual(available_families(root / "design-system" / "fonts"), ["alt-sans", "carlito"])
            result = build_document(root, "courses/doc")
            self.assertTrue(result.audit.passed)
            names = PdfReader(io.BytesIO(result.pdf_path.read_bytes()))
            self.assertGreaterEqual(len(names.pages), 5)

    def test_unknown_family_is_rejected_with_the_choices(self):
        with TempProject(meta=META + "font: nothing\n") as root:
            with self.assertRaises(ConfigError) as raised:
                build_document(root, "courses/doc")
            self.assertIn("carlito", str(raised.exception))

    def test_family_file_with_a_wrong_checksum_is_rejected(self):
        with TempProject() as root:
            self.make_family(root)
            (root / "design-system" / "fonts" / "Alt-Carlito-Bold.ttf").write_bytes(b"not a font")
            with self.assertRaises(ConfigError):
                register_fonts(root / "design-system" / "fonts", "alt-sans")

    def test_registry_rejects_unsafe_entries(self):
        with TempProject() as root:
            fonts = root / "design-system" / "fonts"
            (fonts / "fonts.yaml").write_text(
                yaml.safe_dump({"families": {"bad": {"regular": "../x.ttf", "bold": "b", "italic": "i", "bolditalic": "bi"}}}),
                encoding="utf-8",
            )
            with self.assertRaises(ConfigError):
                register_fonts(fonts, "bad")
            (fonts / "fonts.yaml").write_text("other: 1\n", encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_registry(fonts)


class MetaOptionTests(unittest.TestCase):
    def test_font_profile_and_keywords(self):
        meta = parse_meta(dict(yaml.safe_load(META), font="alt-sans", profile="course", keywords="a, b"))
        self.assertEqual((meta.font, meta.profile, meta.keywords), ("alt-sans", "course", "a, b"))
        with self.assertRaises(ConfigError):
            parse_meta(dict(yaml.safe_load(META), profile="novel"))
        with self.assertRaises(ConfigError):
            parse_meta(dict(yaml.safe_load(META), font="Bad Font"))


class CommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._project = TempProject()
        cls.root = cls._project.__enter__()
        cls.result = build_document(cls.root, "courses/doc")

    @classmethod
    def tearDownClass(cls):
        cls._project.__exit__(None, None, None)

    def run_cli(self, *args):
        return main(list(args), root=self.root)

    def test_manifest_records_environment_stats_and_text_hash(self):
        import json
        manifest = json.loads(self.result.manifest_path.read_text(encoding="utf-8"))
        self.assertIn("reportlab", manifest["environment"])
        self.assertEqual(manifest["content_stats"]["chapters"], 2)
        self.assertEqual(len(manifest["text_sha256"]), 64)
        self.assertIn("contrast", manifest["audit_inputs"])

    def test_check_passes_and_writes_nothing_new(self):
        problems, pages = check_document(self.root, "courses/doc")
        self.assertEqual(problems, [])
        self.assertGreaterEqual(pages, 5)
        self.assertEqual(self.run_cli("check", str(self.root / "courses" / "doc")), 0)

    def test_verify_passes_then_detects_changes(self):
        folder = self.root / "courses" / "doc"
        self.assertTrue(verify_document(self.root, "courses/doc").ok)
        self.assertEqual(self.run_cli("verify", str(folder)), 0)
        content = folder / "content.md"
        original = content.read_text(encoding="utf-8")
        try:
            content.write_text(original + "\nAn extra paragraph.\n", encoding="utf-8")
            outcome = verify_document(self.root, "courses/doc")
            self.assertFalse(outcome.ok)
            self.assertTrue(any("content.md" in p for p in outcome.problems))
            self.assertEqual(self.run_cli("verify", str(folder)), 3)
        finally:
            content.write_text(original, encoding="utf-8")
        pdf = self.result.pdf_path
        data = pdf.read_bytes()
        try:
            pdf.write_bytes(data + b"\n%tampered\n")
            self.assertFalse(verify_document(self.root, "courses/doc").ok)
        finally:
            pdf.write_bytes(data)

    def test_new_creates_a_folder_that_passes_check(self):
        target = self.root / "courses" / "fresh"
        code = self.run_cli("new", str(target), "--title", "A Fresh Document", "--author", "Some Author")
        self.assertEqual(code, 0)
        self.assertTrue((target / "meta.yaml").is_file())
        self.assertEqual(self.run_cli("check", str(target)), 0)
        self.assertEqual(self.run_cli("new", str(target), "--title", "Again", "--author", "X"), 2)

    @unittest.skipUnless(
        shutil.which("pdftoppm") or importlib.util.find_spec("fitz"),
        "previews need PyMuPDF or pdftoppm",
    )
    def test_preview_writes_png_files(self):
        folder = self.root / "courses" / "doc"
        self.assertEqual(self.run_cli("preview", str(folder), "--pages", "1,2"), 0)
        images = sorted((folder / "build" / "preview").glob("page-*.png"))
        self.assertEqual([p.name for p in images], ["page-001.png", "page-002.png"])
        self.assertTrue(images[0].read_bytes().startswith(b"\x89PNG"))
        self.assertEqual(self.run_cli("preview", str(folder), "--pages", "x"), 2)
        self.assertEqual(self.run_cli("preview", str(folder), "--pages", "0"), 2)

    def test_fonts_command_lists_families(self):
        self.assertEqual(self.run_cli("fonts"), 0)


class SecurityAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._project = TempProject()
        cls.root = cls._project.__enter__()
        cls.result = build_document(cls.root, "courses/doc")
        cls.pdf = cls.result.pdf_path.read_bytes()
        cls.meta = parse_meta(yaml.safe_load(META))

    @classmethod
    def tearDownClass(cls):
        cls._project.__exit__(None, None, None)

    def failed(self, data):
        report = audit_pdf(data, self.meta, self.result.audit.exempt_pages)
        return {c.id for c in report.checks if not c.passed}

    def variant(self, change):
        writer = PdfWriter(clone_from=PdfReader(io.BytesIO(self.pdf)))
        change(writer)
        buffer = io.BytesIO()
        writer.write(buffer)
        return buffer.getvalue()

    def test_clean_build_passes_the_new_checks(self):
        ids = {c.id: c.passed for c in self.result.audit.checks}
        self.assertTrue(ids["A14"] and ids["A15"] and ids["A16"])

    def test_javascript_is_detected(self):
        data = self.variant(lambda w: w.add_js("app.alert('x');"))
        self.assertIn("A14", self.failed(data))

    def test_attachment_is_detected(self):
        data = self.variant(lambda w: w.add_attachment("a.txt", b"hello"))
        self.assertIn("A14", self.failed(data))

    def test_a_local_path_in_the_metadata_is_detected(self):
        data = self.variant(lambda w: w.add_metadata({"/Producer": "/Users/someone/tool"}))
        self.assertIn("A15", self.failed(data))


if __name__ == "__main__":
    unittest.main()
