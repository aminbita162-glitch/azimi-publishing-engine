import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engine.release.atomic_delivery import AtomicDeliveryError, place_verified_snapshot


class AtomicDeliverySecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.out = self.root / "private"
        self.out.mkdir(mode=0o700)
        self.src = self.root / "input.pdf"
        self.src.write_bytes(b"%PDF-test-snapshot")
        self.sha = hashlib.sha256(self.src.read_bytes()).hexdigest()
        self.dst = self.out / "final.pdf"

    def test_success_and_no_overwrite(self):
        self.assertEqual(place_verified_snapshot(self.src, self.dst, self.sha), self.dst)
        self.assertEqual(self.dst.read_bytes(), self.src.read_bytes())
        with self.assertRaises(AtomicDeliveryError):
            place_verified_snapshot(self.src, self.dst, self.sha)

    def test_digest_mismatch_leaves_no_final_or_temp(self):
        with self.assertRaisesRegex(AtomicDeliveryError, "digest mismatch"):
            place_verified_snapshot(self.src, self.dst, "0" * 64)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_existing_symlink_not_followed_or_deleted(self):
        victim = self.root / "victim"
        victim.write_bytes(b"safe")
        self.dst.symlink_to(victim)
        with self.assertRaises(AtomicDeliveryError):
            place_verified_snapshot(self.src, self.dst, self.sha)
        self.assertTrue(self.dst.is_symlink())
        self.assertEqual(victim.read_bytes(), b"safe")

    def test_private_directory_required(self):
        self.out.chmod(0o755)
        with self.assertRaisesRegex(AtomicDeliveryError, "private"):
            place_verified_snapshot(self.src, self.dst, self.sha)

    def test_final_file_not_deleted_on_post_link_fsync_failure(self):
        real_fsync = os.fsync
        count = [0]
        def failing_fsync(fd):
            count[0] += 1
            if count[0] == 2:
                raise OSError("simulated directory fsync failure")
            return real_fsync(fd)
        with patch("engine.release.atomic_delivery.os.fsync", side_effect=failing_fsync):
            with self.assertRaises(OSError):
                place_verified_snapshot(self.src, self.dst, self.sha)
        self.assertEqual(self.dst.read_bytes(), self.src.read_bytes())
