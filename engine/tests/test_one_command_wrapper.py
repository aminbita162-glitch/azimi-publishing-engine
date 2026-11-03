"""A-022B.1 build-only compatibility regression tests."""
import ast
import unittest
from pathlib import Path
from unittest.mock import patch
from engine import one_command

class OneCommandWrapperTests(unittest.TestCase):
    def test_delegates_only_to_build(self):
        with patch.object(one_command, "cli_main", return_value=0) as cli:
            self.assertEqual(one_command.main(["courses/doc"]), 0)
            cli.assert_called_once_with(["build", "courses/doc"])
    def test_propagates_failure(self):
        with patch.object(one_command, "cli_main", return_value=3) as cli:
            self.assertEqual(one_command.main(["courses/doc"]), 3)
            cli.assert_called_once_with(["build", "courses/doc"])
    def test_invalid_args_do_not_call_cli(self):
        with patch.object(one_command, "cli_main") as cli:
            self.assertEqual(one_command.main([]), 2)
            self.assertEqual(one_command.main(["a", "b"]), 2)
            cli.assert_not_called()
    def test_no_independent_publication_or_metadata_writes(self):
        source=Path(one_command.__file__).read_text(encoding="utf-8")
        tree=ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertFalse({a.name.split(".")[0] for a in node.names} & {"shutil", "os", "subprocess", "pathlib"})
        for forbidden in ("copy2(", "copyfile(", "write_text(", "mkdir(", "deliver_pdf(", "Publication ready", "meta.yaml"):
            self.assertNotIn(forbidden, source)
