"""Unit tests for session01_reference.py (run from the session folder)."""
import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import session01_reference as ref  # noqa: E402

PROPOSAL = ref.DEFAULT


def fresh_connection(**seed_args):
    connection = ref.connect()
    ref.seed(connection, PROPOSAL, **seed_args)
    return connection


def current_state(connection):
    return connection.execute(
        'SELECT retry_limit, revision FROM config_state'
    ).fetchone()


class ReferenceTests(unittest.TestCase):
    def test_valid_proposal_is_executed_once(self):
        c = fresh_connection()
        result = ref.execute(c, PROPOSAL)
        self.assertEqual(result, (ref.GateDecision.ALLOW, ref.ExecutionResult.SUCCEEDED))
        self.assertEqual(current_state(c), (5, 4))
        self.assertEqual(c.execute('SELECT COUNT(*) FROM audit').fetchone()[0], 1)

    def test_tampered_value_is_denied(self):
        c = fresh_connection()
        result = ref.execute(c, replace(PROPOSAL, value=9))
        self.assertEqual(result, (ref.GateDecision.DENY, None))
        self.assertEqual(current_state(c), (3, 3))

    def test_stale_revision_requires_revalidation(self):
        c = fresh_connection()
        c.execute('UPDATE config_state SET revision = 4')
        result = ref.execute(c, PROPOSAL)
        self.assertEqual(result, (ref.GateDecision.REVALIDATION_REQUIRED, None))
        self.assertEqual(current_state(c), (3, 4))

    def test_replay_of_a_consumed_approval_is_denied(self):
        c = fresh_connection()
        ref.execute(c, PROPOSAL)
        result = ref.execute(c, PROPOSAL)
        self.assertEqual(result, (ref.GateDecision.DENY, None))
        self.assertEqual(current_state(c), (5, 4))

    def test_tenant_mismatch_is_denied(self):
        c = fresh_connection()
        result = ref.execute(c, replace(PROPOSAL, tenant_id='tenant-02'))
        self.assertEqual(result, (ref.GateDecision.DENY, None))

    def test_expired_approval_is_denied(self):
        c = fresh_connection()
        result = ref.execute(c, PROPOSAL, trusted_now=3000)
        self.assertEqual(result, (ref.GateDecision.DENY, None))
        self.assertEqual(current_state(c), (3, 3))

    def test_unauthorized_approver_is_denied(self):
        c = fresh_connection()
        c.execute('DELETE FROM approver_permissions')
        result = ref.execute(c, PROPOSAL)
        self.assertEqual(result, (ref.GateDecision.DENY, None))

    def test_error_while_writing_the_audit_record_rolls_everything_back(self):
        c = fresh_connection()
        c.execute('DROP TABLE audit')
        with self.assertRaises(Exception):
            ref.execute(c, PROPOSAL)
        self.assertEqual(current_state(c), (3, 3))
        status = c.execute('SELECT status FROM approvals').fetchone()[0]
        self.assertEqual(status, 'APPROVED')

    def test_boolean_value_is_rejected(self):
        with self.assertRaises(ValueError):
            ref.validate(replace(PROPOSAL, value=True))

    def test_operation_key_target_allowlist(self):
        c = fresh_connection()
        decision = ref.gate(c, replace(PROPOSAL, key='other_key'), 'A-001', 1000)
        self.assertEqual(decision, ref.GateDecision.DENY)

    def test_digest_changes_when_content_changes(self):
        self.assertNotEqual(ref.digest(PROPOSAL), ref.digest(replace(PROPOSAL, value=9)))
        self.assertEqual(ref.digest(PROPOSAL), ref.digest(replace(PROPOSAL)))


if __name__ == '__main__':
    unittest.main()
