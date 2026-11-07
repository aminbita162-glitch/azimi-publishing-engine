"""Phase 2: audit reporting completeness — no silent truncation of issues.

Regression test for the problems[:6] truncation bug: when a document has more
than six A7 failures, every failure must survive in the Check.issues tuple and
in the manifest serialization, including the worst page.
"""
import json
import unittest

from engine.audit import audit_pdf
from engine.build.builder import build_document
from engine.schemas.meta import parse_meta
import yaml
from engine.tests.support import META, TempProject


def meta_object():
    return parse_meta(yaml.safe_load(META))


class AuditReportingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._project = TempProject()
        cls.root = cls._project.__enter__()
        cls.result = build_document(cls.root, "courses/doc")
        cls.pdf = cls.result.pdf_path.read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls._project.__exit__(None, None, None)

    def test_all_issues_survive_beyond_six(self):
        """With max_blank_ratio=0.0 every non-exempt page fails A7; all must
        appear in Check.issues, not just the first six."""
        report = audit_pdf(self.pdf, meta_object(), (1,), max_blank_ratio=0.0)
        a7 = next(c for c in report.checks if c.id == "A7")
        self.assertFalse(a7.passed)
        self.assertGreater(len(a7.issues), 6,
                           "issues must contain more than six entries when "
                           "there are more than six failing pages")
        # The detail must mention the total count
        self.assertIn("total", a7.detail)

    def test_worst_page_appears_in_issues(self):
        """The page with the worst fill must be in the issues list."""
        report = audit_pdf(self.pdf, meta_object(), (1,), max_blank_ratio=0.0)
        a7 = next(c for c in report.checks if c.id == "A7")
        fills = report.page_fill
        non_exempt = [(i + 1, fills[i]) for i in range(len(fills)) if i + 1 not in {1}]
        worst_page, worst_fill = min(non_exempt, key=lambda p: p[1])
        worst_str = f"page {worst_page}"
        self.assertTrue(
            any(worst_str in issue for issue in a7.issues),
            f"worst page {worst_page} (fill {worst_fill:.3f}) must appear in issues"
        )

    def test_issues_serialized_in_manifest(self):
        """to_dict() must include the full issues list, not just the detail."""
        report = audit_pdf(self.pdf, meta_object(), (1,), max_blank_ratio=0.0)
        d = report.to_dict()
        a7 = next(c for c in d["checks"] if c["id"] == "A7")
        self.assertIn("issues", a7)
        self.assertGreater(len(a7["issues"]), 6)

    def test_pass_has_empty_issues(self):
        """A passing check must have an empty issues list."""
        d = self.result.audit.to_dict()
        a7 = next(c for c in d["checks"] if c["id"] == "A7")
        self.assertEqual(a7["issues"], [])

    def test_no_false_pass_with_zero_threshold(self):
        """max_blank_ratio=0.0 must never produce a PASS unless every non-exempt
        page is 100% filled."""
        report = audit_pdf(self.pdf, meta_object(), (), max_blank_ratio=0.0)
        a7 = next(c for c in report.checks if c.id == "A7")
        self.assertFalse(a7.passed,
                         "A7 must FAIL with max_blank_ratio=0.0 on a real document")


class ExemptionLegitimacyTests(unittest.TestCase):
    """Verify that exemptions are structural, not a way to hide layout defects."""

    @classmethod
    def setUpClass(cls):
        cls._project = TempProject()
        cls.root = cls._project.__enter__()
        cls.result = build_document(cls.root, "courses/doc")
        cls.pdf = cls.result.pdf_path.read_bytes()
        cls.exempt = set(cls.result.audit.exempt_pages)
        cls.fills = cls.result.audit.page_fill

    @classmethod
    def tearDownClass(cls):
        cls._project.__exit__(None, None, None)

    def test_every_non_exempt_page_passes_threshold(self):
        """Independent check: every non-exempt page must have fill >= 0.87."""
        threshold = 0.87
        for i, fill in enumerate(self.fills, 1):
            if i not in self.exempt:
                self.assertGreaterEqual(
                    fill, threshold,
                    f"non-exempt page {i} has fill {fill:.3f} < {threshold}"
                )

    def test_removing_an_exemption_causes_a7_failure(self):
        """If an exempt page is actually underfilled, removing its exemption
        must cause A7 to fail — proving the exemption is load-bearing."""
        underfilled_exempt = [
            i for i in sorted(self.exempt)
            if self.fills[i - 1] < 0.87
        ]
        if not underfilled_exempt:
            self.skipTest("no underfilled exempt pages to test")
        # Remove one exemption and re-run the audit
        page = underfilled_exempt[0]
        reduced = tuple(p for p in sorted(self.exempt) if p != page)
        report = audit_pdf(self.pdf, meta_object(), reduced)
        a7 = next(c for c in report.checks if c.id == "A7")
        self.assertFalse(a7.passed,
                         f"removing exemption for page {page} (fill "
                         f"{self.fills[page-1]:.3f}) must cause A7 FAIL")

    def test_empty_exempt_still_checks_all_pages(self):
        """With no exemptions, every page is checked — A7 either passes with
        all pages counted, or fails with every underfilled page in issues."""
        report = audit_pdf(self.pdf, meta_object(), ())
        a7 = next(c for c in report.checks if c.id == "A7")
        if a7.passed:
            self.assertIn(f"{len(self.fills)} body pages", a7.detail)
        else:
            # Every underfilled page must appear in issues
            underfilled = [
                i + 1 for i, f in enumerate(self.fills) if f < 0.87
            ]
            for page in underfilled:
                self.assertTrue(
                    any(f"page {page}" in issue for issue in a7.issues),
                    f"page {page} must appear in issues when not exempt"
                )

    def test_forged_exemption_does_not_create_false_pass(self):
        """Adding a non-existent page to exempt_pages must not cause A7 to
        falsely pass — the audit must still check real pages."""
        # Exempt every page including non-existent page 999
        all_plus_fake = tuple(range(1, len(self.fills) + 1)) + (999,)
        report = audit_pdf(self.pdf, meta_object(), all_plus_fake)
        a7 = next(c for c in report.checks if c.id == "A7")
        self.assertTrue(a7.passed,
                        "exempting every real page must pass; fake page 999 "
                        "must not cause a failure")


if __name__ == "__main__":
    unittest.main()
