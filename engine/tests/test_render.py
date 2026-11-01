import io
import json
import shutil
import unittest
from pathlib import Path

from pypdf import PdfReader

from engine.build.builder import build_document
from engine.errors import ConfigError, ContentError
from engine.tests.support import CONTENT, META, TempProject, make_project


def read(path: Path) -> PdfReader:
    return PdfReader(io.BytesIO(path.read_bytes()))


def outline_titles(reader: PdfReader):
    titles = []

    def walk(items):
        for item in items:
            if isinstance(item, list):
                walk(item)
            else:
                titles.append(item.title)

    walk(reader.outline)
    return titles


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._project = TempProject()
        cls.root = cls._project.__enter__()
        cls.result = build_document(cls.root, "courses/doc")
        cls.reader = read(cls.result.pdf_path)

    @classmethod
    def tearDownClass(cls):
        cls._project.__exit__(None, None, None)

    def test_output_is_a_pdf_with_expected_name(self):
        self.assertEqual(self.result.pdf_path.name, "Sample_Session_v1.0.0.pdf")
        self.assertTrue(self.result.pdf_path.read_bytes().startswith(b"%PDF-"))

    def test_page_count_and_a4(self):
        self.assertEqual(len(self.reader.pages), self.result.pages)
        self.assertGreaterEqual(self.result.pages, 5)
        box = self.reader.pages[0].mediabox
        self.assertAlmostEqual(float(box.width), 595.27, delta=0.5)
        self.assertAlmostEqual(float(box.height), 841.89, delta=0.5)

    def test_metadata_and_language(self):
        info = self.reader.metadata
        self.assertEqual(info.title, "Agentic Systems Foundations")
        self.assertEqual(info.author, "Amin Azimi")
        self.assertEqual(info.subject, "Senior engineers")
        self.assertEqual(str(self.reader.trailer["/Root"]["/Lang"]), "en")

    def test_document_date_comes_from_metadata_not_the_clock(self):
        self.assertTrue(str(self.reader.metadata.get("/CreationDate")).startswith("D:20261101000000"))

    def test_outline_matches_headings(self):
        self.assertEqual(
            outline_titles(self.reader),
            ["Foundations", "Core ideas", "Second chapter", "Details"],
        )

    def test_cover_shows_brand_tagline(self):
        with TempProject() as other:
            brand_file = other / "brand" / "default" / "brand.yaml"
            brand_file.write_text(brand_file.read_text() + "tagline: AI Architect Amin Azimi\n", encoding="utf-8")
            result = build_document(other, "courses/doc")
            first_page = read(result.pdf_path).pages[0].extract_text()
        self.assertIn("AI Architect Amin Azimi", first_page)

    def test_text_content_is_extractable(self):
        text = " ".join(page.extract_text() for page in self.reader.pages)
        for expected in ("Agentic Systems Foundations", "Contents", "Closing text.", "Figure 1. The pipeline", "Page 3"):
            self.assertIn(expected, text)

    def test_all_fonts_are_embedded(self):
        found = 0
        for page in self.reader.pages:
            fonts = page["/Resources"].get("/Font", {})
            for ref in fonts.values():
                font = ref.get_object()
                self.assertIn("/FontDescriptor", font, f"{font.get('/BaseFont')} is not embedded")
                descriptor = font["/FontDescriptor"].get_object()
                self.assertTrue(
                    "/FontFile2" in descriptor or "/FontFile3" in descriptor,
                    f"{font.get('/BaseFont')} has no embedded font file",
                )
                found += 1
        self.assertGreater(found, 0)

    def test_no_page_is_blank(self):
        for number, page in enumerate(self.reader.pages, start=1):
            self.assertGreater(len(page.extract_text().strip()), 40, f"page {number}")

    def test_manifest_records_inputs_fonts_and_output(self):
        manifest = json.loads(self.result.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["output"]["sha256"], self.result.sha256)
        self.assertEqual(manifest["output"]["pages"], self.result.pages)
        self.assertIn("assets/flow.png", manifest["inputs"])
        self.assertIn("brand/default/logo.png", manifest["inputs"])
        self.assertEqual(len(manifest["fonts"]), 6)

    def test_rebuild_is_byte_identical(self):
        again = build_document(self.root, "courses/doc")
        self.assertEqual(again.sha256, self.result.sha256)

    def test_build_is_independent_of_location(self):
        with TempProject() as other_root:
            other = build_document(other_root, "courses/doc")
        self.assertEqual(other.sha256, self.result.sha256)


class RenderEdgeCaseTests(unittest.TestCase):
    def test_long_unbreakable_code_line_is_not_truncated(self):
        content = "# Title\n\n~~~text\n" + "x" * 400 + "\n~~~\n"
        with TempProject(content=content, with_image=False) as root:
            result = build_document(root, "courses/doc")
            text = "".join(p.extract_text() for p in read(result.pdf_path).pages)
        self.assertEqual(text.count("x"), 400)

    def test_document_without_headings_has_no_contents_page(self):
        with TempProject(content="Just a paragraph of text.\n", with_image=False) as root:
            result = build_document(root, "courses/doc")
            text = " ".join(p.extract_text() for p in read(result.pdf_path).pages)
        self.assertNotIn("Contents", text)
        self.assertEqual(result.pages, 2)

    def test_unsupported_character_is_rejected(self):
        with TempProject(content="# Title\n\nA character 漢 here.\n", with_image=False) as root:
            with self.assertRaisesRegex(ContentError, "line 3: character U\\+6F22"):
                build_document(root, "courses/doc")

    def test_missing_image_is_rejected(self):
        with TempProject(with_image=False) as root:
            with self.assertRaisesRegex(ContentError, "image file not found"):
                build_document(root, "courses/doc")

    def test_tampered_font_is_rejected(self):
        with TempProject() as root:
            font = root / "design-system" / "fonts" / "Carlito-Regular.ttf"
            font.write_bytes(font.read_bytes() + b"x")
            with self.assertRaisesRegex(ConfigError, "checksum mismatch"):
                build_document(root, "courses/doc")

    def test_missing_font_is_rejected(self):
        with TempProject() as root:
            (root / "design-system" / "fonts" / "LiberationMono-Bold.ttf").unlink()
            with self.assertRaisesRegex(ConfigError, "missing"):
                build_document(root, "courses/doc")

    def test_content_error_names_the_line(self):
        with TempProject(content="# Title\n\nGood.\n\n**broken\n", with_image=False) as root:
            with self.assertRaisesRegex(ContentError, "line 5: emphasis is not closed"):
                build_document(root, "courses/doc")

    def test_missing_document_folder(self):
        with TempProject() as root:
            with self.assertRaisesRegex(ConfigError, "not found"):
                build_document(root, "courses/other")

    def test_unknown_brand(self):
        with TempProject(meta=META + "brand: other\n") as root:
            with self.assertRaisesRegex(ConfigError, "folder not found"):
                build_document(root, "courses/doc")

    def test_consecutive_page_breaks_do_not_create_blank_pages(self):
        content = "# One\n\nText.\n\nPAGEBREAK\n\nPAGEBREAK\n\n# Two\n\nText two.\n"
        with TempProject(content=content, with_image=False) as root:
            result = build_document(root, "courses/doc")
            reader = read(result.pdf_path)
        for number, page in enumerate(reader.pages, start=1):
            self.assertGreater(len(page.extract_text().strip()), 40, f"page {number}")


if __name__ == "__main__":
    unittest.main()
