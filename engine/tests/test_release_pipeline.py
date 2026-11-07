"""Integration sequencing and fail-closed tests; no real release."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from engine.release.pipeline import execute_authorized_release, ReleasePipelineError

MOD = "engine.release.pipeline"

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.state = root / "state"; self.state.mkdir(mode=0o700)
        self.audit = root / "audit"; self.audit.mkdir(mode=0o700)
        self.out = root / "out"; self.out.mkdir(mode=0o700)
        self.src = root / "source.pdf"; self.src.write_bytes(b"%PDF-1.4\nexample")
        import hashlib
        self.digest = hashlib.sha256(self.src.read_bytes()).hexdigest()
        self.dst = self.out / "result.pdf"
        self.expected = {"artifact_sha256": self.digest}
        self.kw = dict(payload={}, signature_b64="", registry={}, expected=self.expected,
                       replay_state_dir=self.state, audit_dir=self.audit,
                       snapshot=self.src, destination=self.dst)

    def run_authorized(self):
        with patch(MOD + ".authorize_release", return_value="approval-1"):
            return execute_authorized_release(**self.kw)

    def test_success_records_both_events(self):
        self.assertEqual(self.run_authorized(), self.dst)
        self.assertEqual(self.dst.read_bytes(), self.src.read_bytes())
        self.assertTrue((self.state / "approval-1.used").exists())
        self.assertTrue((self.audit / "approval-1.reserved.json").exists())
        self.assertTrue((self.audit / "approval-1.delivered.json").exists())

    def test_replay_denied_no_overwrite(self):
        self.run_authorized()
        with self.assertRaises(Exception): self.run_authorized()
        self.assertEqual(self.dst.read_bytes(), self.src.read_bytes())

    def test_bad_signature_no_side_effects(self):
        with patch(MOD + ".authorize_release", side_effect=ValueError("bad signature")):
            with self.assertRaises(ValueError): execute_authorized_release(**self.kw)
        self.assertFalse(self.dst.exists())
        self.assertEqual(list(self.state.iterdir()), [])
        self.assertEqual(list(self.audit.iterdir()), [])

    def test_digest_mismatch_consumes_and_records_failure(self):
        self.expected["artifact_sha256"] = "0" * 64
        with self.assertRaises(ReleasePipelineError): self.run_authorized()
        self.assertFalse(self.dst.exists())
        self.assertTrue((self.state / "approval-1.used").exists())
        self.assertTrue((self.audit / "approval-1.failed.json").exists())

    def test_audit_reservation_failure_prevents_delivery(self):
        with patch(MOD + ".record_release_event", side_effect=OSError("disk full")):
            with self.assertRaises(ReleasePipelineError): self.run_authorized()
        self.assertFalse(self.dst.exists())
        self.assertTrue((self.state / "approval-1.used").exists())

    def test_delivery_audit_failure_requires_reconciliation(self):
        original = __import__(MOD, fromlist=["record_release_event"]).record_release_event
        def fail_delivered(directory, approval, digest, status):
            if status == "delivered": raise OSError("disk full")
            return original(directory, approval, digest, status)
        with patch(MOD + ".record_release_event", side_effect=fail_delivered):
            with self.assertRaisesRegex(ReleasePipelineError, "uncertain"):
                self.run_authorized()
        self.assertTrue(self.dst.exists())
        self.assertTrue((self.state / "approval-1.used").exists())

if __name__ == "__main__": unittest.main()
