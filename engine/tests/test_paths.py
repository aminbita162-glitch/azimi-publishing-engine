import os
import tempfile
import unittest
from pathlib import Path

from engine.errors import PathError
from engine.paths import resolve_inside


class ResolveInsideTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "a").mkdir()
        (self.root / "a" / "file.txt").write_text("x", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_resolves_file_inside_root(self):
        result = resolve_inside(self.root, "a/file.txt")
        self.assertEqual(result, (self.root / "a" / "file.txt").resolve())

    def test_allows_not_yet_existing_target(self):
        result = resolve_inside(self.root, "a/new.txt")
        self.assertEqual(result.parent, (self.root / "a").resolve())

    def test_rejects_parent_reference(self):
        with self.assertRaises(PathError):
            resolve_inside(self.root, "a/../../etc/passwd")

    def test_rejects_absolute_path(self):
        with self.assertRaises(PathError):
            resolve_inside(self.root, "/etc/passwd")

    def test_rejects_empty_path(self):
        with self.assertRaises(PathError):
            resolve_inside(self.root, "")

    def test_rejects_symbolic_link(self):
        outside = tempfile.TemporaryDirectory()
        try:
            os.symlink(outside.name, self.root / "link")
            with self.assertRaises(PathError):
                resolve_inside(self.root, "link/secret.txt")
        finally:
            outside.cleanup()


if __name__ == "__main__":
    unittest.main()
