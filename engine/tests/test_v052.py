"""Tests for the agent checksum command and the delivery command."""

import hashlib
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine.build.builder import build_document
from engine.cli import main
from engine.errors import ConfigError
from engine.tests.support import REAL_ROOT, TempProject
from engine.tools import APPROVAL_FILE, deliver_pdf, verify_agents


class AgentChecksumTests(unittest.TestCase):
    def test_the_installed_files_match_their_checksums(self):
        results = verify_agents(REAL_ROOT)
        self.assertEqual([r[0] for r in results], ["amilus", "ali", "lili"])
        for name, ok, version, digest in results:
            self.assertTrue(ok, name)
            self.assertTrue(version.startswith("Version "), name)
            self.assertEqual(len(digest), 64)

    def test_a_changed_file_is_a_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(REAL_ROOT / "agents", root / "agents")
            self.assertTrue(all(r[1] for r in verify_agents(root)))
            target = root / "agents" / "ali.txt"
            target.write_text(target.read_text(encoding="utf-8") + "extra line\n", encoding="utf-8")
            outcome = {r[0]: r[1] for r in verify_agents(root)}
            self.assertEqual(outcome, {"amilus": True, "ali": False, "lili": True})
            self.assertEqual(main(["agents"], root=root), 2)
            (root / "agents" / "lili.txt").unlink()
            self.assertFalse(dict((r[0], r[1]) for r in verify_agents(root))["lili"])

    def test_missing_checksum_file_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "agents").mkdir()
            with self.assertRaises(ConfigError):
                verify_agents(tmp)

    def test_the_command_succeeds_on_the_project(self):
        self.assertEqual(main(["agents"], root=REAL_ROOT), 0)


class DeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._project = TempProject()
        cls.root = cls._project.__enter__()
        cls.result = build_document(cls.root, "courses/doc")
        cls.checksum = hashlib.sha256(cls.result.pdf_path.read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls._project.__exit__(None, None, None)

    def setUp(self):
        self.out = tempfile.TemporaryDirectory()
        self.patch = mock.patch.dict(os.environ, {"AZIMI_OUTPUT_DIR": self.out.name})
        self.patch.start()
        self.approval = self.root / "courses" / "doc" / APPROVAL_FILE
        if self.approval.exists():
            self.approval.unlink()

    def tearDown(self):
        self.patch.stop()
        self.out.cleanup()

    def test_draft_goes_to_the_drafts_folder_and_is_recorded(self):
        target = deliver_pdf(self.root, "courses/doc", "draft")
        self.assertEqual(target.parent, Path(self.out.name) / "Drafts")
        self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), self.checksum)
        record = (self.root / "courses" / "doc" / "build" / "delivery-draft.json").read_text(encoding="utf-8")
        self.assertIn(self.checksum, record)
        import json
        import re
        month = json.loads(record)["month"]
        self.assertRegex(month, r"^[A-Z][a-z]+ \d{4}$")
        self.assertEqual(deliver_pdf(self.root, "courses/doc", "draft"), target)

    def test_release_needs_the_owner_approval_of_this_exact_pdf(self):
        # Legacy plaintext approval must never bypass the temporary fail-closed gate.
        for approval_text in (
            None,
            "APPROVED " + "0" * 64 + "\n",
            f"APPROVED {self.checksum} by the owner, November 2026\n",
        ):
            if approval_text is not None:
                self.approval.write_text(approval_text, encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "release temporarily disabled"):
                deliver_pdf(self.root, "courses/doc", "release")
            self.assertEqual(list(Path(self.out.name).rglob("*.pdf")), [])

    def test_different_content_is_never_overwritten(self):
        target = Path(self.out.name) / "Drafts" / self.result.pdf_path.name
        target.parent.mkdir(parents=True)
        target.write_bytes(b"something else")
        with self.assertRaises(ConfigError) as raised:
            deliver_pdf(self.root, "courses/doc", "draft")
        self.assertIn("not overwritten", str(raised.exception))
        self.assertEqual(target.read_bytes(), b"something else")

    def test_a_changed_input_stops_delivery(self):
        content = self.root / "courses" / "doc" / "content.md"
        original = content.read_text(encoding="utf-8")
        try:
            content.write_text(original + "\nAn extra paragraph.\n", encoding="utf-8")
            with self.assertRaises(ConfigError):
                deliver_pdf(self.root, "courses/doc", "draft")
            self.assertEqual(list(Path(self.out.name).rglob("*.pdf")), [])
        finally:
            content.write_text(original, encoding="utf-8")

    def test_cli_delivers_and_rejects_bad_modes(self):
        folder = str(self.root / "courses" / "doc")
        self.assertEqual(main(["deliver", "draft", folder], root=self.root), 0)
        self.assertEqual(main(["deliver", "release", folder], root=self.root), 2)
        with self.assertRaises(SystemExit):
            main(["deliver", "publish", folder], root=self.root)


@unittest.skipUnless((REAL_ROOT / "directive.txt").is_file(), "the directive is only present in the project repository")
class DirectiveTests(unittest.TestCase):
    def test_directive_describes_the_three_workflows_and_the_real_structure(self):
        text = (REAL_ROOT / "directive.txt").read_text(encoding="utf-8")
        self.assertIn("ROOT MASTER ENGINEERING DIRECTIVE", text)
        self.assertIn("V1.2", text)
        self.assertIn("THREE WORKFLOWS", text)
        self.assertIn("Three-agent workflow", text)
        self.assertIn("agents/{amilus.txt,ali.txt,lili.txt,SHA256SUMS}", text)
        self.assertIn("Drafts subfolder", text)
        self.assertNotIn("TWO DISTINCT WORKFLOWS", text)


if __name__ == "__main__":
    unittest.main()
