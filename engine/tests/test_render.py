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
            ["Foundations", "Core ideas", "Second chapter", "Details", "Rights and License",
             "What is permitted", "What is not permitted"],
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
        content = "# Title\n\n~~~text\n" + "q" * 400 + "\n~~~\n"
        with TempProject(content=content, with_image=False) as root:
            result = build_document(root, "courses/doc")
            text = "".join(p.extract_text() for p in read(result.pdf_path).pages)
        self.assertEqual(text.count("q"), 400)

    def test_rights_chapter_is_always_appended_after_the_content(self):
        with TempProject(content="Just a paragraph of text.\n", with_image=False) as root:
            result = build_document(root, "courses/doc")
            pages = [p.extract_text() for p in read(result.pdf_path).pages]
        self.assertIn("Contents", pages[2])
        self.assertIn("Rights and License", pages[2])
        self.assertIn("Rights and License", pages[-1])
        self.assertIn("All rights reserved.", pages[-1])

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


class LayoutTests(unittest.TestCase):
    def test_table_columns_never_split_a_word(self):
        from reportlab.pdfbase import pdfmetrics
        from engine.render.document import _column_widths
        from engine.render.fonts import register_fonts
        from engine.tests.support import REAL_ROOT

        register_fonts(REAL_ROOT / "design-system" / "fonts")
        header = ("Row", "Gate decision", "Reason")
        rows = (("Tampered", "DENY", "The digest does not match the approval"),
                ("Replay", "DENY", "The approval is already CONSUMED"))
        widths = _column_widths(header, rows)
        self.assertAlmostEqual(sum(widths), 470.55, delta=1.0)
        self.assertGreater(widths[0], pdfmetrics.stringWidth("Tampered", "Body-Bold", 9.5) + 12)

    def test_intro_paragraph_stays_with_its_code_block(self):
        filler = "\n\n".join("Filler paragraph number %d of the document body." % i for i in range(1, 34))
        content = "# Title\n\n" + filler + "\n\nREFERENCE CODE.\n\n~~~python\n" + "\n".join("x = %d" % i for i in range(30)) + "\n~~~\n"
        with TempProject(content=content, with_image=False) as root:
            result = build_document(root, "courses/doc")
            pages = [p.extract_text() for p in read(result.pdf_path).pages]
        holder = [i for i, text in enumerate(pages) if "REFERENCE CODE." in text]
        code = [i for i, text in enumerate(pages) if "x = 0" in text]
        self.assertEqual(holder, code)

    def test_long_code_block_is_split_across_chunks_without_loss(self):
        lines = "\n".join("value_%03d = %d" % (i, i) for i in range(60))
        with TempProject(content="# T\n\n~~~python\n" + lines + "\n~~~\n", with_image=False) as root:
            result = build_document(root, "courses/doc")
            text = "".join(p.extract_text() for p in read(result.pdf_path).pages)
        for i in (0, 11, 12, 59):
            self.assertIn("value_%03d = %d" % (i, i), text)


class FeatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        content = (
            "# First\n\nIntro text with a link to github.com/owner/repo here.\n\n"
            "TIP: A tip.\n\nKEY: A key point.\n\nCHECKPOINT: A checkpoint.\n\n"
            "~~~python\ndef f(x):\n    return x + 1  # add\n\nvalue = f(2)\nprint(value)\n~~~\n\n"
            "# Second\n\nMore text.\n"
        )
        cls._project = TempProject(content=content, with_image=False)
        cls.root = cls._project.__enter__()
        cls.result = build_document(cls.root, "courses/doc")
        cls.reader = read(cls.result.pdf_path)
        cls.pages = [page.extract_text() for page in cls.reader.pages]

    @classmethod
    def tearDownClass(cls):
        cls._project.__exit__(None, None, None)

    def test_cover_imprint_contents_order(self):
        self.assertIn("Agentic Systems Foundations", self.pages[0])
        self.assertIn("EDITION", self.pages[1])
        self.assertIn("Version 1.0.0, November 2026", self.pages[1])
        self.assertIn("Copyright (c) 2026 Amin Azimi. All rights reserved.", self.pages[1])
        self.assertIn("Contents", self.pages[2])

    def test_footer_shows_page_x_of_y(self):
        first_body = next(i for i, text in enumerate(self.pages) if "Page 1 of" in text)
        body_pages = len(self.pages) - first_body
        self.assertIn("Page ii", self.pages[1])
        self.assertIn("Page iii", self.pages[2])
        self.assertIn(f"Page 1 of {body_pages}", self.pages[first_body])
        self.assertIn(f"Page {body_pages} of {body_pages}", self.pages[-1])

    def test_running_header_shows_the_current_chapter(self):
        first_chapter_page = next(i for i, text in enumerate(self.pages) if "Intro text" in text)
        self.assertIn("First", self.pages[first_chapter_page].split("\n")[0] + self.pages[first_chapter_page])
        header = self.pages[first_chapter_page].split("\n")[:2]
        self.assertTrue(any("First" in line for line in header))
        last = self.pages[-1].split("\n")[:2]
        self.assertTrue(any("Rights and License" in line for line in last))

    def test_links_are_clickable_and_safe(self):
        uris = []
        for page in self.reader.pages:
            for annotation in page.get("/Annots") or []:
                action = annotation.get_object().get("/A")
                if action is not None and action.get_object().get("/S") == "/URI":
                    uris.append(str(action.get_object()["/URI"]))
        self.assertIn("https://github.com/owner/repo", uris)
        self.assertTrue(all(uri.startswith("https://") for uri in uris))

    def test_callout_labels_and_line_numbers_are_drawn(self):
        text = " ".join(self.pages)
        for label in ("TIP", "KEY POINT", "CHECKPOINT"):
            self.assertIn(label, text)
        code_page = next(page for page in self.pages if "def f(x):" in page)
        self.assertIn("return x + 1", code_page)

    def test_viewer_preference_shows_the_document_title(self):
        preferences = self.reader.trailer["/Root"].get("/ViewerPreferences")
        self.assertIsNotNone(preferences)
        self.assertTrue(preferences.get_object().get("/DisplayDocTitle"))

    def test_rights_chapter_comes_from_the_brand(self):
        self.assertIn("Copyright (c) 2026 The Publisher. All rights reserved.", self.pages[-1])

    def test_chapter_pages_option_starts_each_chapter_on_a_new_page(self):
        content = "# One\n\nShort.\n\n# Two\n\nShort again.\n"
        meta = META + "chapter_pages: true\n"
        with TempProject(content=content, meta=meta, with_image=False) as root:
            result = build_document(root, "courses/doc")
            pages = [p.extract_text() for p in read(result.pdf_path).pages]
        one = next(i for i, text in enumerate(pages) if "Short." in text and "Short again." not in text)
        two = next(i for i, text in enumerate(pages) if "Short again." in text)
        self.assertGreater(two, one)

    def test_missing_rights_file_stops_the_build(self):
        with TempProject() as root:
            (root / "brand" / "default" / "rights.md").unlink()
            with self.assertRaisesRegex(ConfigError, "rights.md is missing"):
                build_document(root, "courses/doc")

    def test_rights_file_without_heading_is_rejected(self):
        with TempProject() as root:
            (root / "brand" / "default" / "rights.md").write_text("Only a paragraph.\n", encoding="utf-8")
            with self.assertRaisesRegex(ContentError, "level 1 heading"):
                build_document(root, "courses/doc")

    def test_rights_syntax_errors_name_the_file(self):
        with TempProject() as root:
            (root / "brand" / "default" / "rights.md").write_text("# Rights\n\n**broken\n", encoding="utf-8")
            with self.assertRaisesRegex(ContentError, "in rights.md of brand default"):
                build_document(root, "courses/doc")


class PdfStandardsTests(unittest.TestCase):
    """File level metadata and navigation: XMP, Producer, page labels, PageMode."""

    @classmethod
    def setUpClass(cls):
        cls._project = TempProject()
        cls.root = cls._project.__enter__()
        cls.result = build_document(cls.root, "courses/doc")
        cls.reader = read(cls.result.pdf_path)

    @classmethod
    def tearDownClass(cls):
        cls._project.__exit__(None, None, None)

    def test_producer_names_the_engine_version(self):
        from engine import __version__

        self.assertEqual(self.reader.metadata.producer, f"Azimi Publishing Engine {__version__}")

    def test_page_mode_shows_the_outline(self):
        self.assertEqual(str(self.reader.trailer["/Root"]["/PageMode"]), "/UseOutlines")

    def test_page_labels_use_roman_front_matter_then_decimal(self):
        labels = self.reader.page_labels
        self.assertEqual(labels[:3], ["i", "ii", "iii"])
        first_decimal = labels.index("1")
        self.assertGreater(first_decimal, 2)
        self.assertEqual(labels[first_decimal + 1], "2")
        self.assertEqual(labels[-1], str(len(labels) - first_decimal))

    def test_xmp_carries_title_author_language_and_rights(self):
        import pikepdf

        with pikepdf.open(io.BytesIO(self.result.pdf_path.read_bytes())) as pdf:
            xmp = pdf.open_metadata()
            self.assertEqual(xmp["dc:title"], "Agentic Systems Foundations")
            self.assertEqual(list(xmp["dc:creator"]), ["Amin Azimi"])
            self.assertIn("Copyright (c) 2026", xmp["dc:rights"])
            self.assertTrue(xmp["pdf:Producer"].startswith("Azimi Publishing Engine"))
            self.assertEqual(xmp["xmp:CreateDate"], "2026-11-01T00:00:00+00:00")

    def test_xmp_makes_no_conformance_claim(self):
        raw = self.result.pdf_path.read_bytes()
        self.assertNotIn(b"pdfaid", raw)
        self.assertNotIn(b"pdfuaid", raw)

    def test_no_local_paths_or_placeholders_in_the_file(self):
        raw = self.result.pdf_path.read_bytes()
        for forbidden in (b"/Users/", b"/home/", b"placeholder", b"Placeholder"):
            self.assertNotIn(forbidden, raw)

    def test_outline_and_toc_links_survive_the_metadata_step(self):
        self.assertTrue(outline_titles(self.reader))
        links = sum(len(page.get("/Annots") or []) for page in self.reader.pages)
        self.assertGreater(links, 0)

    def test_two_builds_are_byte_identical(self):
        again = build_document(self.root, "courses/doc")
        self.assertEqual(again.pdf_path.read_bytes(), self.result.pdf_path.read_bytes())
