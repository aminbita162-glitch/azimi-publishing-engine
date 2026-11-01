import json
import unittest
from unittest import mock

from engine.audit import MAX_BLANK_RATIO, audit_pdf
from engine.audit.pdf_audit import page_fill_ratios
from engine.build.builder import build_document
from engine.schemas.meta import parse_meta
from engine.tests.support import META, TempProject
from pypdf import PdfReader
import io
import yaml


def meta_object():
    return parse_meta(yaml.safe_load(META))


class AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._project = TempProject()
        cls.root = cls._project.__enter__()
        cls.result = build_document(cls.root, "courses/doc")
        cls.pdf = cls.result.pdf_path.read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls._project.__exit__(None, None, None)

    def test_build_audit_passes_and_is_recorded_in_the_manifest(self):
        self.assertTrue(self.result.audit.passed)
        manifest = json.loads(self.result.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["audit"]["result"], "PASS")
        self.assertTrue(manifest["reproducible"])
        self.assertEqual(len(manifest["audit"]["page_fill"]), self.result.pages)

    def test_all_check_ids_are_present(self):
        ids = [check.id for check in self.result.audit.checks]
        self.assertEqual(ids, ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8"])

    def test_metadata_mismatch_is_detected(self):
        wrong = parse_meta(dict(yaml.safe_load(META), title="A different title"))
        report = audit_pdf(self.pdf, wrong, self.result.audit.exempt_pages)
        failed = {check.id for check in report.checks if not check.passed}
        self.assertIn("A3", failed)
        self.assertFalse(report.passed)

    def test_page_fill_threshold_is_enforced(self):
        report = audit_pdf(self.pdf, meta_object(), (1,), max_blank_ratio=0.0)
        self.assertIn("A7", {check.id for check in report.checks if not check.passed})

    def test_exempt_pages_are_not_counted_as_underfilled(self):
        everything = tuple(range(1, self.result.pages + 1))
        report = audit_pdf(self.pdf, meta_object(), everything, max_blank_ratio=0.0)
        self.assertTrue(next(c for c in report.checks if c.id == "A7").passed)

    def test_fill_ratios_are_fractions(self):
        ratios = page_fill_ratios(PdfReader(io.BytesIO(self.pdf)))
        self.assertEqual(len(ratios), self.result.pages)
        self.assertTrue(all(0.0 <= value <= 1.0 for value in ratios))

    def test_default_threshold_is_a_sensible_value(self):
        self.assertGreater(MAX_BLANK_RATIO, 0.1)
        self.assertLess(MAX_BLANK_RATIO, 0.4)

    def test_a_failed_audit_stops_the_command_line_with_exit_code_three(self):
        import contextlib
        from engine.cli import main

        real = audit_pdf

        def strict(*args, **kwargs):
            kwargs["max_blank_ratio"] = 0.0
            return real(*args, **kwargs)

        out, err = io.StringIO(), io.StringIO()
        with TempProject() as root, mock.patch("engine.build.builder.audit_pdf", side_effect=strict):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = main(["build", str(root / "courses" / "doc")], root=root)
        self.assertEqual(code, 3)
        self.assertIn("Audit     : FAIL", out.getvalue())
        self.assertIn("the audit failed", err.getvalue())


if __name__ == "__main__":
    unittest.main()
