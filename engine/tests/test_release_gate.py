"""Independent fail-closed gate orchestration tests; never deliver a PDF."""
import unittest
from unittest.mock import patch
from pathlib import Path

from engine.release.gate import validate_and_reserve_release


class GateOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.args = ({"approval_id": "approval-1"}, "signature", {}, {}, Path("/unused"))

    @patch("engine.release.gate.reserve_approval")
    @patch("engine.release.gate.authorize_release", return_value="approval-1")
    def test_authorizes_before_reserving(self, authorize, reserve):
        events = []
        authorize.side_effect = lambda *args: events.append("authorize") or "approval-1"
        reserve.side_effect = lambda *args: events.append("reserve")
        self.assertEqual(validate_and_reserve_release(*self.args), "approval-1")
        self.assertEqual(events, ["authorize", "reserve"])
        reserve.assert_called_once_with(Path("/unused"), "approval-1")

    @patch("engine.release.gate.reserve_approval")
    @patch("engine.release.gate.authorize_release", side_effect=ValueError("bad signature"))
    def test_invalid_authorization_never_reserves(self, authorize, reserve):
        with self.assertRaisesRegex(ValueError, "bad signature"):
            validate_and_reserve_release(*self.args)
        reserve.assert_not_called()

    @patch("engine.release.gate.reserve_approval", side_effect=ValueError("replay"))
    @patch("engine.release.gate.authorize_release", return_value="approval-1")
    def test_replay_failure_propagates(self, authorize, reserve):
        with self.assertRaisesRegex(ValueError, "replay"):
            validate_and_reserve_release(*self.args)
        reserve.assert_called_once()

    @patch("engine.release.gate.reserve_approval")
    @patch("engine.release.gate.authorize_release", return_value="approval-1")
    def test_gate_has_no_delivery_side_effect(self, authorize, reserve):
        with patch("shutil.copy2", side_effect=AssertionError("delivery attempted")):
            validate_and_reserve_release(*self.args)
        reserve.assert_called_once()


if __name__ == "__main__":
    unittest.main()
