"""Adversarial boundary tests for standalone atomic placement."""
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from engine.release.atomic_delivery import AtomicDeliveryError, place_verified_snapshot

class AtomicBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.private = self.root / "private"
        self.private.mkdir(mode=0o700)
        self.src = self.root / "input.pdf"
        self.src.write_bytes(b"%PDF-1.7\ncontrolled snapshot")
        self.digest = hashlib.sha256(self.src.read_bytes()).hexdigest()
        self.dst = self.private / "output.pdf"

    def test_source_symlink_denied(self):
        link = self.root / "alias.pdf"
        link.symlink_to(self.src)
        with self.assertRaises(AtomicDeliveryError):
            place_verified_snapshot(link, self.dst, self.digest)
        self.assertFalse(self.dst.exists())

    def test_destination_symlink_preserved(self):
        victim = self.root / "victim"
        victim.write_bytes(b"untouched")
        self.dst.symlink_to(victim)
        with self.assertRaises(AtomicDeliveryError):
            place_verified_snapshot(self.src, self.dst, self.digest)
        self.assertEqual(victim.read_bytes(), b"untouched")

    def test_changed_source_rejected(self):
        self.src.write_bytes(b"changed")
        with self.assertRaises(AtomicDeliveryError):
            place_verified_snapshot(self.src, self.dst, self.digest)
        self.assertFalse(self.dst.exists())
        self.assertFalse(list(self.private.glob(".ape-pending-*")))

    def test_existing_destination_never_replaced(self):
        self.dst.write_bytes(b"prior")
        with self.assertRaises(AtomicDeliveryError):
            place_verified_snapshot(self.src, self.dst, self.digest)
        self.assertEqual(self.dst.read_bytes(), b"prior")

    def test_failure_before_link_cleans_temporary(self):
        with patch('engine.release.atomic_delivery.os.link', side_effect=OSError('injected failure')):
            with self.assertRaises(OSError):
                place_verified_snapshot(self.src, self.dst, self.digest)
        self.assertFalse(self.dst.exists())
        self.assertFalse(list(self.private.glob(".ape-pending-*")))

    def test_success_snapshot_integrity(self):
        place_verified_snapshot(self.src, self.dst, self.digest)
        self.assertEqual(hashlib.sha256(self.dst.read_bytes()).hexdigest(), self.digest)
        self.assertFalse(list(self.private.glob(".ape-pending-*")))

if __name__ == '__main__':
    unittest.main()
