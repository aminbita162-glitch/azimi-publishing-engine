"""Regression tests for immutable-source assumptions in release placement."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from engine.release.atomic_delivery import AtomicDeliveryError, place_verified_snapshot

class SourceConsistencyTests(unittest.TestCase):
    def test_valid_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            source = parent / "source.pdf"
            source.write_bytes(b"stable PDF snapshot")
            target = parent / "final.pdf"
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            self.assertEqual(place_verified_snapshot(source, target, digest), target)
            self.assertEqual(target.read_bytes(), source.read_bytes())

    def test_source_modified_during_copy_fails_without_final(self):
        import engine.release.atomic_delivery as module
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            source = parent / "source.pdf"
            source.write_bytes(b"stable PDF snapshot")
            target = parent / "final.pdf"
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            real_read = module.os.read
            modified = [False]
            def tamper(fd, count):
                result = real_read(fd, count)
                if result and not modified[0]:
                    modified[0] = True
                    source.write_bytes(b"changed after first read")
                return result
            with patch.object(module.os, "read", side_effect=tamper):
                with self.assertRaises(AtomicDeliveryError):
                    place_verified_snapshot(source, target, digest)
            self.assertFalse(target.exists())
            self.assertEqual(list(parent.glob(".ape-pending-*")), [])
