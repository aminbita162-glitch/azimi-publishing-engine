import os
import tempfile
import unittest
from pathlib import Path
from engine.release.replay import ReplayError, reserve_approval


class ReplayReservationTests(unittest.TestCase):
    def test_first_reservation_and_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "state"
            d.mkdir(mode=0o700)
            reserve_approval(d, "approval-001")
            self.assertEqual((d / "approval-001.used").read_bytes(), b"reserved\n")
            with self.assertRaises(ReplayError):
                reserve_approval(d, "approval-001")

    def test_invalid_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            for bad in ("", "../escape", "a/b", "a" * 129, None):
                with self.subTest(bad=bad), self.assertRaises(ReplayError):
                    reserve_approval(d, bad)

    def test_world_readable_state_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "state"
            d.mkdir()
            d.chmod(0o755)
            with self.assertRaises(ReplayError):
                reserve_approval(d, "approval-002")

    def test_symlink_state_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "state"
            d.mkdir(mode=0o700)
            link = Path(tmp) / "link"
            link.symlink_to(d, target_is_directory=True)
            with self.assertRaises(ReplayError):
                reserve_approval(link, "approval-003")


if __name__ == "__main__":
    unittest.main()
