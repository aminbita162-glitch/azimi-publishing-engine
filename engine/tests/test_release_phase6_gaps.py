"""Phase 6 regression tests closing three assurance-matrix gaps:
S12 concurrent race, S16 EACCES/EPERM permission denial, and key rotation
(old revoked / new active). No production code is changed; no release is enabled.
"""
import os
import tempfile
import threading
import unittest
from pathlib import Path

from engine.release.replay import ReplayError, reserve_approval
from engine.release.trust import active_public_key
from engine.release_security import ApprovalError


class ConcurrentRaceTests(unittest.TestCase):
    """S12: two simultaneous release attempts on the same approval ID.

    O_EXCL provides a kernel-level atomic guarantee, so exactly one thread
    wins the reservation and the other is rejected with ReplayError.
    """

    def test_exactly_one_concurrent_reservation_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "state"
            d.mkdir(mode=0o700)
            results = {}
            errors = {}
            barrier = threading.Barrier(2)

            def attempt(tag):
                barrier.wait()
                try:
                    reserve_approval(d, "race-001")
                    results[tag] = True
                except ReplayError as exc:
                    errors[tag] = str(exc)

            threads = [
                threading.Thread(target=attempt, args=(tag,))
                for tag in ("A", "B")
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            self.assertEqual(
                len(results), 1,
                f"expected exactly one winner, got {results!r} errors={errors!r}",
            )
            self.assertEqual(
                len(errors), 1,
                f"expected exactly one loser, got {errors!r} results={results!r}",
            )
            self.assertIn("already reserved", next(iter(errors.values())))
            self.assertTrue((d / "race-001.used").read_bytes(), b"reserved\n")


class PermissionDeniedTests(unittest.TestCase):
    """S16: EACCES/EPERM from os.open is caught and surfaced as ReplayError.

    A read-only private directory passes the st_mode & 0o077 pre-check but
    causes os.open(O_CREAT) to fail with EACCES at the syscall level.
    """

    def test_eacces_from_os_open_raises_replay_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "state"
            d.mkdir(mode=0o700)
            d.chmod(0o500)  # r-x: passes privacy check, denies write
            try:
                self.assertEqual(d.stat().st_mode & 0o077, 0)
                with self.assertRaisesRegex(ReplayError, "cannot reserve approval"):
                    reserve_approval(d, "approval-eacces")
            finally:
                d.chmod(0o700)  # restore for cleanup
            self.assertFalse((d / "approval-eacces.used").exists())

    def test_eperm_from_os_open_raises_replay_error(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "state"
            d.mkdir(mode=0o700)
            with patch("engine.release.replay.os.open",
                       side_effect=PermissionError(
                           1, "Operation not permitted")):
                with self.assertRaisesRegex(
                        ReplayError, "cannot reserve approval"):
                    reserve_approval(d, "approval-eperm")
            self.assertEqual(list(d.iterdir()), [])


class KeyRotationTests(unittest.TestCase):
    """Key rotation sequence: old key revoked, new key active.

    Revocation is tested individually in test_release_trust_registry; this
    test exercises the rotation sequence where the old key is revoked and a
    new key is active in the same registry.
    """

    def setUp(self):
        self.old_key = b"k" * 32
        self.new_key = b"n" * 32
        self.registry = {
            "owner-1": {"public_key": self.old_key, "status": "revoked"},
            "owner-2": {"public_key": self.new_key, "status": "active"},
        }

    def test_revoked_old_key_rejected(self):
        with self.assertRaisesRegex(ApprovalError, "key not trusted or revoked"):
            active_public_key(self.registry, "owner-1")

    def test_active_new_key_accepted(self):
        self.assertEqual(
            active_public_key(self.registry, "owner-2"), self.new_key)

    def test_rotation_old_fails_new_succeeds(self):
        # Old key is revoked → rejected; new key is active → accepted.
        with self.assertRaises(ApprovalError):
            active_public_key(self.registry, "owner-1")
        self.assertEqual(
            active_public_key(self.registry, "owner-2"), self.new_key)
        self.assertNotEqual(self.old_key, self.new_key)


if __name__ == "__main__":
    unittest.main()
