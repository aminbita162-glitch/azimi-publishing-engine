"""Tests for Phase C5: findings registry, references, series, test execution, version history, glossary."""

import json
import tempfile
import unittest
from pathlib import Path

from engine.build.parser import Glossary, References, parse
from engine.errors import ConfigError, ContentError
from engine.schemas.findings import load_findings
from engine.schemas.meta import parse_meta
from engine.tests.support import TempProject, META, CONTENT, make_figure

import io
from pypdf import PdfReader

# --------------------------------------------------------------------------- #
# C5.1 — Findings registry
# --------------------------------------------------------------------------- #

VALID_FINDINGS = """\
- id: f01
  status: open
  source: audit-2026
  text: The cache layer has no invalidation.
- id: f02
  status: closed
  source: review-2026
  text: Missing input validation on form.
"""

MALFORMED_FINDINGS = """\
- id: f01
  status: open
  source: audit-2026
  text: Fine.
- bad_entry
"""

MISSING_FIELD_FINDINGS = """\
- id: f01
  status: open
  text: Missing source.
"""


class FindingsRegistryTests(unittest.TestCase):
    def test_load_valid_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "findings.yaml"
            path.write_text(VALID_FINDINGS, encoding="utf-8")
            findings = load_findings(path)
            self.assertEqual(len(findings), 2)
            self.assertEqual(findings[0]["id"], "f01")
            self.assertEqual(findings[0]["status"], "open")
            self.assertEqual(findings[1]["source"], "review-2026")

    def test_load_findings_returns_empty_for_empty_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "findings.yaml"
            path.write_text("", encoding="utf-8")
            findings = load_findings(path)
            self.assertEqual(findings, [])

    def test_reject_non_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "findings.yaml"
            path.write_text("id: f01\nstatus: open\n", encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "must be a list"):
                load_findings(path)

    def test_reject_malformed_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "findings.yaml"
            path.write_text(MALFORMED_FINDINGS, encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "not a mapping"):
                load_findings(path)

    def test_reject_missing_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "findings.yaml"
            path.write_text(MISSING_FIELD_FINDINGS, encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "missing field 'source'"):
                load_findings(path)

    def test_reject_bad_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "findings.yaml"
            path.write_text(
                "- id: 'Bad ID'\n  status: open\n  source: s\n  text: t\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfigError, "id must be"):
                load_findings(path)

    def test_findings_in_manifest(self):
        """A findings.yaml in the document folder appears in the build manifest."""
        with TempProject() as root:
            doc = root / "courses" / "doc"
            (doc / "findings.yaml").write_text(VALID_FINDINGS, encoding="utf-8")
            from engine.build.builder import build_document
            result = build_document(root, "courses/doc")
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertIn("findings", manifest)
            self.assertEqual(len(manifest["findings"]), 2)
            self.assertIn("findings.yaml", manifest["inputs"])

    def test_no_findings_key_when_absent(self):
        """Without findings.yaml, the manifest has no 'findings' key."""
        with TempProject() as root:
            from engine.build.builder import build_document
            result = build_document(root, "courses/doc")
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertNotIn("findings", manifest)


# --------------------------------------------------------------------------- #
# C5.2 — Reference list
# --------------------------------------------------------------------------- #

class ReferencesParserTests(unittest.TestCase):
    def test_parse_references(self):
        text = (
            "REFERENCES:\n"
            "1. Author A, Title. Journal, 2024. https://example.com/paper\n"
            "2. Author B, Other Title. 2023\n"
        )
        blocks = parse(text)
        ref = [b for b in blocks if isinstance(b, References)]
        self.assertEqual(len(ref), 1)
        self.assertEqual(len(ref[0].items), 2)
        text0, url0 = ref[0].items[0]
        text1, url1 = ref[0].items[1]
        self.assertIn("Author A", text0)
        self.assertEqual(url0, "https://example.com/paper")
        self.assertIsNone(url1)

    def test_references_without_numbering(self):
        text = (
            "REFERENCES:\n"
            "Plain reference line\n"
            "Another reference https://example.org\n"
        )
        blocks = parse(text)
        ref = [b for b in blocks if isinstance(b, References)]
        self.assertEqual(len(ref), 1)
        self.assertEqual(len(ref[0].items), 2)
        self.assertIsNone(ref[0].items[0][1])
        self.assertEqual(ref[0].items[1][1], "https://example.org")

    def test_references_empty_rejected(self):
        with self.assertRaisesRegex(ContentError, "at least one entry"):
            parse("REFERENCES:\n\n# Heading\n")

    def test_references_in_pdf(self):
        """References appear in the built PDF as a numbered list."""
        content = CONTENT + "\n\nREFERENCES:\nTest reference https://example.com\nAnother ref\n"
        with TempProject(content=content) as root:
            from engine.build.builder import build_document
            result = build_document(root, "courses/doc")
            reader = PdfReader(io.BytesIO(result.pdf_path.read_bytes()))
            full_text = "\n".join(page.extract_text() or "" for page in reader.pages)
            self.assertIn("References", full_text)
            self.assertIn("Test reference", full_text)
            self.assertIn("Another ref", full_text)


# --------------------------------------------------------------------------- #
# C5.3 — Series support
# --------------------------------------------------------------------------- #

VALID_META = {
    "title": "Agentic Systems Foundations",
    "author": "Amin Azimi",
    "audience": "Senior engineers with seven or more years of experience",
    "language": "en",
    "version": "1.0.0",
    "date": "November 2026",
    "output_name": "session-01",
}


class SeriesMetaTests(unittest.TestCase):
    def test_series_and_number_accepted(self):
        meta = parse_meta(dict(VALID_META, series="Agentic AI Masterclass", series_number=3))
        self.assertEqual(meta.series, "Agentic AI Masterclass")
        self.assertEqual(meta.series_number, 3)

    def test_series_without_number(self):
        meta = parse_meta(dict(VALID_META, series="Some Series"))
        self.assertEqual(meta.series, "Some Series")
        self.assertIsNone(meta.series_number)

    def test_number_without_series_rejected(self):
        with self.assertRaisesRegex(ConfigError, "series_number requires series"):
            parse_meta(dict(VALID_META, series_number=5))

    def test_bad_series_number_type(self):
        for bad in ("3", 3.5, True, "three"):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(ConfigError, "series_number"):
                    parse_meta(dict(VALID_META, series="S", series_number=bad))

    def test_zero_series_number_rejected(self):
        with self.assertRaisesRegex(ConfigError, "series_number"):
            parse_meta(dict(VALID_META, series="S", series_number=0))

    def test_absent_series_no_change(self):
        meta = parse_meta(dict(VALID_META))
        self.assertIsNone(meta.series)
        self.assertIsNone(meta.series_number)

    def test_series_in_imprint(self):
        meta = dict(VALID_META, series="Agentic AI Masterclass", series_number=7)
        with TempProject(meta="title: T\nsubtitle: S\nauthor: A\naudience: B\nlanguage: en\n"
                         "version: 1.0.0\ndate: November 2026\noutput_name: X\n"
                         "series: Agentic AI Masterclass\nseries_number: 7\n") as root:
            from engine.build.builder import build_document
            result = build_document(root, "courses/doc")
            reader = PdfReader(io.BytesIO(result.pdf_path.read_bytes()))
            # The imprint is on page 2 (after cover).
            imprint_text = reader.pages[1].extract_text() or ""
            self.assertIn("SERIES", imprint_text)
            self.assertIn("Agentic AI Masterclass", imprint_text)
            self.assertIn("Document 7", imprint_text)

    def test_no_series_no_imprint_change(self):
        with TempProject() as root:
            from engine.build.builder import build_document
            result = build_document(root, "courses/doc")
            reader = PdfReader(io.BytesIO(result.pdf_path.read_bytes()))
            imprint_text = reader.pages[1].extract_text() or ""
            self.assertNotIn("SERIES", imprint_text)


# --------------------------------------------------------------------------- #
# C5.4 — Test code execution
# --------------------------------------------------------------------------- #

class TestExecutionTests(unittest.TestCase):
    def test_passing_test_block(self):
        """A ```test block that exits 0 is recorded in the manifest."""
        content = CONTENT + "\n\n~~~test\nassert 1 + 1 == 2\nprint('ok')\n~~~\n"
        with TempProject(content=content) as root:
            from engine.build.builder import build_document
            result = build_document(root, "courses/doc")
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertIn("test_blocks", manifest)
            self.assertTrue(any(t["exit_code"] == 0 for t in manifest["test_blocks"]))

    def test_failing_test_block(self):
        """A ```test block that exits non-zero fails the build."""
        content = CONTENT + "\n\n~~~test\nassert False, 'deliberate failure'\n~~~\n"
        with TempProject(content=content) as root:
            from engine.build.builder import build_document
            with self.assertRaises(ContentError) as exc:
                build_document(root, "courses/doc")
            self.assertIn("exited with code", str(exc.exception))

    def test_no_test_blocks_no_manifest_key(self):
        """Without test blocks, the manifest has no 'test_blocks' key."""
        with TempProject() as root:
            from engine.build.builder import build_document
            result = build_document(root, "courses/doc")
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertNotIn("test_blocks", manifest)

    def test_other_languages_not_executed(self):
        """A ```python block is never executed during build."""
        content = CONTENT + "\n\n~~~python\nimport sys; sys.exit(42)\n~~~\n"
        with TempProject(content=content) as root:
            from engine.build.builder import build_document
            # Should succeed — python blocks are not executed.
            result = build_document(root, "courses/doc")
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertNotIn("test_blocks", manifest)


# --------------------------------------------------------------------------- #
# C5.5 — Version history
# --------------------------------------------------------------------------- #

VH_CONTENT = """\
# Changelog

## 1.0.0 - November 2026

- Initial release.

## 0.9.0 - October 2026

- Beta release.
"""


class VersionHistoryTests(unittest.TestCase):
    def test_version_history_in_pdf(self):
        """A CHANGELOG.md in the document folder renders a Version History section."""
        with TempProject() as root:
            doc = root / "courses" / "doc"
            (doc / "CHANGELOG.md").write_text(VH_CONTENT, encoding="utf-8")
            from engine.build.builder import build_document
            result = build_document(root, "courses/doc")
            reader = PdfReader(io.BytesIO(result.pdf_path.read_bytes()))
            full_text = "\n".join(page.extract_text() or "" for page in reader.pages)
            self.assertIn("Version History", full_text)
            self.assertIn("1.0.0", full_text)
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertIn("CHANGELOG.md", manifest["inputs"])

    def test_version_history_absent_no_change(self):
        """Without a version-history file, the PDF is unchanged."""
        with TempProject() as root:
            from engine.build.builder import build_document
            result = build_document(root, "courses/doc")
            reader = PdfReader(io.BytesIO(result.pdf_path.read_bytes()))
            full_text = "\n".join(page.extract_text() or "" for page in reader.pages)
            self.assertNotIn("Version History", full_text)

    def test_version_history_file_in_manifest_inputs(self):
        with TempProject() as root:
            doc = root / "courses" / "doc"
            (doc / "version-history.md").write_text(VH_CONTENT, encoding="utf-8")
            from engine.build.builder import build_document
            result = build_document(root, "courses/doc")
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertIn("version-history.md", manifest["inputs"])


# --------------------------------------------------------------------------- #
# C5.6 — Glossary links
# --------------------------------------------------------------------------- #

class GlossaryParserTests(unittest.TestCase):
    def test_parse_glossary(self):
        text = (
            "GLOSSARY: Agentic AI | AI that takes actions autonomously\n"
            "GLOSSARY: LLM | Large Language Model\n"
        )
        blocks = parse(text)
        gloss = [b for b in blocks if isinstance(b, Glossary)]
        self.assertEqual(len(gloss), 1)
        self.assertEqual(len(gloss[0].entries), 2)
        self.assertEqual(gloss[0].entries[0][0], "Agentic AI")
        self.assertEqual(gloss[0].entries[0][1], "AI that takes actions autonomously")
        self.assertEqual(gloss[0].entries[1][0], "LLM")

    def test_glossary_bad_syntax(self):
        with self.assertRaisesRegex(ContentError, "glossary syntax"):
            parse("GLOSSARY: missing pipe\n")

    def test_glossary_empty_definition(self):
        with self.assertRaisesRegex(ContentError, "glossary syntax"):
            parse("GLOSSARY: term | \n")


class GlossaryRenderingTests(unittest.TestCase):
    def test_glossary_in_pdf(self):
        """A GLOSSARY block renders a Glossary section in the PDF."""
        content = (
            CONTENT
            + "\n\nThe Agentic AI system uses an LLM for reasoning.\n\n"
            + "GLOSSARY: Agentic AI | AI that takes actions autonomously\n"
            + "GLOSSARY: LLM | Large Language Model\n"
        )
        with TempProject(content=content) as root:
            from engine.build.builder import build_document
            result = build_document(root, "courses/doc")
            reader = PdfReader(io.BytesIO(result.pdf_path.read_bytes()))
            full_text = "\n".join(page.extract_text() or "" for page in reader.pages)
            self.assertIn("Glossary", full_text)
            self.assertIn("Agentic AI", full_text)
            self.assertIn("Large Language Model", full_text)

    def test_glossary_term_linked_in_body(self):
        """Occurrences of a glossary term in body text become a clickable link."""
        content_with_glossary = (
            CONTENT
            + "\n\nAn Agentic AI can act autonomously in the world.\n\n"
            + "GLOSSARY: Agentic AI | AI that takes actions autonomously\n"
        )
        content_without_glossary = CONTENT + "\n\nAn Agentic AI can act autonomously in the world.\n"

        def _count_internal_links(pdf_bytes):
            reader = PdfReader(io.BytesIO(pdf_bytes))
            count = 0
            for page in reader.pages:
                for annot in (page.get("/Annots") or []):
                    obj = annot.get_object() if hasattr(annot, "get_object") else annot
                    if obj.get("/Subtype") == "/Link" and obj.get("/Dest"):
                        count += 1
            return count

        with TempProject(content=content_with_glossary) as root:
            from engine.build.builder import build_document
            result = build_document(root, "courses/doc")
            links_with = _count_internal_links(result.pdf_path.read_bytes())
            # The audit must still pass (all links resolve, including the glossary link).
            self.assertTrue(result.audit.passed)
            self.assertIn("Agentic AI", "\n".join(
                p.extract_text() or "" for p in PdfReader(io.BytesIO(result.pdf_path.read_bytes())).pages
            ))

        with TempProject(content=content_without_glossary) as root:
            from engine.build.builder import build_document
            result2 = build_document(root, "courses/doc")
            links_without = _count_internal_links(result2.pdf_path.read_bytes())

        # The glossary term adds at least one internal link that was not present without the glossary.
        self.assertGreater(links_with, links_without,
                           f"Expected more links with glossary ({links_with}) than without ({links_without})")

    def test_unknown_terms_stay_plain(self):
        """Text without matching glossary terms does not get links."""
        content = (
            CONTENT
            + "\n\nSome unrelated text about coffee and tea.\n\n"
            + "GLOSSARY: Agentic AI | AI that takes actions autonomously\n"
        )
        with TempProject(content=content) as root:
            from engine.build.builder import build_document
            result = build_document(root, "courses/doc")
            reader = PdfReader(io.BytesIO(result.pdf_path.read_bytes()))
            # The body text should not contain [[gloss-...]] literal markers.
            full_text = "\n".join(page.extract_text() or "" for page in reader.pages)
            self.assertNotIn("[[gloss-", full_text)
            self.assertIn("coffee and tea", full_text)


if __name__ == "__main__":
    unittest.main()
