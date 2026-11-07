"""Course-authored reference, NOT a verbatim excerpt from any GitHub repository.

Demonstrates SQLite-local authorization and state transition, not real file I/O.
"""
from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import sqlite3

SAFE_MAX = 2**53 - 1


class GateDecision(str, Enum):
    ALLOW = 'ALLOW'
    DENY = 'DENY'
    REVALIDATION_REQUIRED = 'REVALIDATION_REQUIRED'


class ExecutionResult(str, Enum):
    SUCCEEDED = 'SUCCEEDED'
    FAILED = 'FAILED'
    UNKNOWN = 'UNKNOWN'


@dataclass(frozen=True)
class Proposal:
    proposal_id: str
    tenant_id: str
    target: str
    operation: str
    key: str
    value: int
    revision: int


def validate(p):
    if not isinstance(p, Proposal):
        raise ValueError('invalid proposal')
    identifiers = (p.proposal_id, p.tenant_id, p.target, p.operation, p.key)
    for text in identifiers:
        if not isinstance(text, str) or not text:
            raise ValueError('invalid ASCII field')
        if any(ord(char) < 33 or ord(char) > 126 for char in text):
            raise ValueError('invalid ASCII field')
    if type(p.value) is not int or not 1 <= p.value <= 10:
        raise ValueError('invalid value')
    if type(p.revision) is not int or not 0 <= p.revision <= SAFE_MAX:
        raise ValueError('invalid revision')


def digest(p):
    validate(p)
    fields = ('proposal_id', 'tenant_id', 'target',
              'operation', 'key', 'value', 'revision')
    payload = {name: getattr(p, name) for name in fields}
    encoded = json.dumps(
        payload, sort_keys=True, separators=(',', ':'),
        ensure_ascii=True
    ).encode('ascii')
    return hashlib.sha256(encoded).hexdigest()


def connect():
    c = sqlite3.connect(':memory:', isolation_level=None, timeout=5)
    c.executescript('''
    CREATE TABLE config_state(tenant_id TEXT PRIMARY KEY,
        retry_limit INTEGER NOT NULL,
        revision INTEGER NOT NULL);
    CREATE TABLE approvals(approval_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        proposal_id TEXT NOT NULL,
        digest TEXT NOT NULL,
        status TEXT NOT NULL,
        expires_at INTEGER NOT NULL,
        approver TEXT NOT NULL,
        target TEXT NOT NULL);
    CREATE TABLE approver_permissions(tenant_id TEXT NOT NULL,
        approver TEXT NOT NULL,
        operation TEXT NOT NULL,
        PRIMARY KEY(tenant_id, approver, operation));
    CREATE TABLE audit(id INTEGER PRIMARY KEY,
        approval_id TEXT NOT NULL,
        tenant_id TEXT NOT NULL,
        proposal_id TEXT NOT NULL,
        digest TEXT NOT NULL,
        old_value INTEGER,
        new_value INTEGER,
        revision_before INTEGER,
        revision_after INTEGER,
        at INTEGER NOT NULL,
        result TEXT NOT NULL);
    ''')
    return c


def seed(c, p, expiry=2000, approver='approver-01', approval_id='A-001'):
    c.execute('INSERT INTO config_state VALUES (?,?,?)', (p.tenant_id, 3, 3))
    c.execute(
        'INSERT INTO approvals VALUES (?,?,?,?,?,?,?,?)',
        (approval_id, p.tenant_id, p.proposal_id,
         digest(p), 'APPROVED', expiry, approver, p.target)
    )
    c.execute(
        'INSERT INTO approver_permissions VALUES (?,?,?)',
        (p.tenant_id, approver, p.operation)
    )


def gate(c, p, approval_id, trusted_now):
    try:
        validate(p)
    except (ValueError, TypeError):
        return GateDecision.DENY
    if type(trusted_now) is not int or trusted_now < 0:
        return GateDecision.DENY
    allowed = ('set_config', 'retry_limit', 'app-config.json')
    if (p.operation, p.key, p.target) != allowed:
        return GateDecision.DENY
    record = c.execute(
        'SELECT proposal_id, digest, status, expires_at, '
        'approver, target FROM approvals '
        'WHERE approval_id=? AND tenant_id=?',
        (approval_id, p.tenant_id)
    ).fetchone()
    if not record:
        return GateDecision.DENY
    proposal_id, stored_digest, status, expiry, approver, target = record
    if (proposal_id != p.proposal_id
            or stored_digest != digest(p)
            or status != 'APPROVED'
            or expiry < trusted_now
            or target != p.target):
        return GateDecision.DENY
    permission = c.execute(
        'SELECT 1 FROM approver_permissions '
        'WHERE tenant_id=? AND approver=? AND operation=?',
        (p.tenant_id, approver, p.operation)
    ).fetchone()
    if not permission:
        return GateDecision.DENY
    state = c.execute(
        'SELECT revision FROM config_state WHERE tenant_id=?',
        (p.tenant_id,)
    ).fetchone()
    if not state:
        return GateDecision.DENY
    if state[0] == p.revision:
        return GateDecision.ALLOW
    return GateDecision.REVALIDATION_REQUIRED


def execute(c, p, approval_id='A-001', trusted_now=1000):
    """Errors before commit: rollback and raise.

    Ambiguous commit errors: raise and reconcile externally. Do not report
    UNKNOWN for an arbitrary sqlite3 exception: ambiguity must be evidenced.
    """
    c.execute('BEGIN IMMEDIATE')
    try:
        decision = gate(c, p, approval_id, trusted_now)
        if decision != GateDecision.ALLOW:
            c.rollback()
            return decision, None
        old = c.execute(
            'SELECT retry_limit, revision FROM config_state '
            'WHERE tenant_id=?', (p.tenant_id,)
        ).fetchone()
        updated = c.execute(
            'UPDATE config_state SET retry_limit=?, '
            'revision=revision+1 '
            'WHERE tenant_id=? AND revision=?',
            (p.value, p.tenant_id, p.revision)
        )
        if updated.rowcount != 1:
            c.rollback()
            return GateDecision.REVALIDATION_REQUIRED, None
        consumed = c.execute(
            "UPDATE approvals SET status='CONSUMED' "
            "WHERE approval_id=? AND tenant_id=? "
            "AND status='APPROVED'",
            (approval_id, p.tenant_id)
        )
        if consumed.rowcount != 1:
            c.rollback()
            return GateDecision.DENY, None
        c.execute(
            'INSERT INTO audit('
            'approval_id, tenant_id, proposal_id, digest, old_value, '
            'new_value, revision_before, revision_after, at, result) '
            'VALUES (?,?,?,?,?,?,?,?,?,?)',
            (approval_id, p.tenant_id, p.proposal_id, digest(p),
             old[0], p.value, old[1], old[1] + 1, trusted_now, 'SUCCEEDED')
        )
        c.commit()
        return GateDecision.ALLOW, ExecutionResult.SUCCEEDED
    except Exception:
        if c.in_transaction:
            c.rollback()
        raise


DEFAULT = Proposal(
    'P-001', 'tenant-01', 'app-config.json', 'set_config', 'retry_limit', 5, 3
)
