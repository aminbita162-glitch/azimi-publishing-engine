import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from engine.release.audit_ledger import AuditLedgerError, record_release_event

class AuditLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / "audit"
        self.folder.mkdir(mode=0o700)
        self.digest = hashlib.sha256(b"pdf").hexdigest()

    def test_records_exact_event(self):
        path = record_release_event(self.folder, "approval-1", self.digest, "reserved")
        self.assertTrue(path.is_file())
        self.assertIn(self.digest, path.read_text())

    def test_rejects_replay_without_overwrite(self):
        path = record_release_event(self.folder, "approval-1", self.digest, "delivered")
        original = path.read_bytes()
        with self.assertRaises(AuditLedgerError):
            record_release_event(self.folder, "approval-1", self.digest, "delivered")
        self.assertEqual(path.read_bytes(), original)

    def test_rejects_public_directory(self):
        self.folder.chmod(0o755)
        with self.assertRaises(AuditLedgerError):
            record_release_event(self.folder, "approval-1", self.digest, "reserved")

    def test_rejects_symlink_directory(self):
        link = Path(self.tmp.name) / "alias"
        link.symlink_to(self.folder, target_is_directory=True)
        with self.assertRaises(AuditLedgerError):
            record_release_event(link, "approval-1", self.digest, "reserved")

    def test_rejects_invalid_fields(self):
        for approval, digest, status in [("../escape", self.digest, "reserved"), ("ok", "bad", "reserved"), ("ok", self.digest, "success")]:
            with self.subTest(approval=approval, status=status):
                with self.assertRaises(AuditLedgerError):
                    record_release_event(self.folder, approval, digest, status)
