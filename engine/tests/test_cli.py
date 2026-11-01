import contextlib
import io
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


if __name__ == "__main__":
    unittest.main()
