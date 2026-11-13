import contextlib
import io
import json
import unittest

from engine.cli import main
from engine.tests.support import TempProject


class CliTests(unittest.TestCase):
    def run_cli(self, argv, root):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv, root=root)
        return code, out.getvalue(), err.getvalue()

    def test_build_success(self):
        with TempProject() as root:
            code, out, err = self.run_cli(["build", str(root / "courses" / "doc")], root)
            self.assertEqual(code, 0, err)
            self.assertIn("Sample_Session_v1.0.0.pdf", out)
            self.assertIn("SHA-256", out)
            self.assertTrue((root / "courses" / "doc" / "build" / "Sample_Session_v1.0.0.pdf").is_file())

    def test_relative_path_from_root(self):
        import os

        with TempProject() as root:
            previous = os.getcwd()
            os.chdir(root)
            try:
                code, _, err = self.run_cli(["build", "courses/doc"], root)
            finally:
                os.chdir(previous)
            self.assertEqual(code, 0, err)

    def test_root_reached_through_symbolic_link(self):
        import os

        with TempProject() as root:
            link = root.parent / "link-to-project"
            os.symlink(root, link)
            previous = os.getcwd()
            os.chdir(root)
            try:
                code, _, err = self.run_cli(["build", "courses/doc"], link)
            finally:
                os.chdir(previous)
            self.assertEqual(code, 0, err)

    def test_symbolic_link_inside_project_is_rejected(self):
        import os

        with TempProject() as root:
            os.symlink(root / "courses" / "doc", root / "courses" / "linked")
            code, _, err = self.run_cli(["build", str(root / "courses" / "linked")], root)
            self.assertEqual(code, 2)
            self.assertIn("symbolic links are not allowed", err)

    def test_folder_outside_project_is_rejected(self):
        with TempProject() as root:
            code, _, err = self.run_cli(["build", "/tmp"], root)
            self.assertEqual(code, 2)
            self.assertIn("inside the project", err)

    def test_content_error_is_reported_with_exit_code_two(self):
        with TempProject(content="# T\n\n**bad\n", with_image=False) as root:
            code, _, err = self.run_cli(["build", str(root / "courses" / "doc")], root)
            self.assertEqual(code, 2)
            self.assertIn("error: line 3: emphasis is not closed", err)

    def test_review_success(self):
        with TempProject() as root:
            code, out, err = self.run_cli(["review", str(root / "courses" / "doc")], root)
            self.assertEqual(code, 0, err)
            self.assertIn("Check     : PASS", out)
            self.assertIn("Audit     : PASS", out)
            self.assertIn("Verify     : PASS", out)
            self.assertIn("Review     : PASS", out)
            report_path = root / "courses" / "doc" / "build" / "review-report.json"
            self.assertTrue(report_path.is_file(), "review-report.json should exist")
            report = json.loads(report_path.read_text())
            self.assertEqual(report["command"], "review")
            self.assertEqual(report["overall"], "PASS")
            self.assertEqual(len(report["steps"]), 4)
            self.assertEqual(report["steps"][0]["step"], "check")
            self.assertEqual(report["steps"][1]["step"], "build")
            self.assertEqual(report["steps"][2]["step"], "verify")
            self.assertEqual(report["steps"][3]["step"], "audit")

    def test_review_lint_failure_exit_two(self):
        with TempProject(content="# T\n\n**bad\n", with_image=False) as root:
            code, out, err = self.run_cli(["review", str(root / "courses" / "doc")], root)
            self.assertEqual(code, 2, err)
            self.assertIn("Check     : FAIL", out)


if __name__ == "__main__":
    unittest.main()
