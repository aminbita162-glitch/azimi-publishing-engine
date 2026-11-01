# About This Session

## Who this session is for

This session teaches software engineers how an AI agent can be allowed to *propose* a change without being able to *apply* it. You will learn one boundary and build it in code: the boundary between a **proposal**, an **approval**, and an **execution**.

The session assumes you can read basic Python or TypeScript, understand a JSON object, and know what a database transaction is. No cryptography background is required.

Everything is taught through one fixed, small scenario, so each new idea is attached to something you have already seen. The same scenario returns in the code, the diagrams, the exercises and the answer key.

## What you will be able to do

By the end of the session you will be able to:

1. Mark the trust boundary and the side-effect points of an agent workflow on a diagram.
2. Design and justify a proposal, approval and execution contract that binds tenant, scope, revision and digest.
3. Reject at least three misuse scenarios with repeatable checks: replay, a state change after approval, and cross-tenant access.
4. Propose where the gate attaches to an existing execution path, together with a rollback path.

## A 90-minute study plan

The plan below is a guide for self-study. Each block ends with a short written output that proves you understood the block. Exercises A to F take 30 minutes in total. Task G is optional and is done after the main plan.

| Minutes | Parts | Activity | Written output |
|:--------|:------|:---------|:---------------|
| 0-8 | 1, 2 | Read the core idea and name the authority boundary | One failure mode explained in your own words |
| 8-20 | 2, 3 | Draw proposal, approval and execution with the trust boundaries | A three-stage diagram with the owner of each decision |
| 20-32 | 4 | Study the contract, the canonical digest and invalid input | A list of bound fields and one tamper case |
| 32-45 | 4, 5 | Follow the gate evaluation order | A decision table with cause and control priority |
| 45-55 | 4, 5 | Understand atomicity, error handling and the commit point | An explanation of rollback and the commit point |
| 55-60 | 5 | Choose where the gate attaches in an existing backend | A three-step migration map without side effects |
| 60-75 | 7 | Exercises A to C | Three reasoned answers |
| 75-90 | 7 | Exercises D to F and the summary | A scenario table and two design limitations |

## How the material is labeled

Every code block and every claim carries a label so that you always know what you are looking at.

| Label | Meaning |
|:------|:--------|
| **REFERENCE CODE** | Complete, runnable code written for this course. It is not a quotation from any repository. |
| **SOURCE EXCERPT** | A short excerpt from a real repository, pinned to a commit and a file checksum. |
| **PSEUDOCODE** | Design notation that is not executable. |
| **HYPOTHETICAL SCENARIO** | An invented situation used only for teaching. |
| **SOURCE-REPORTED** | A statement taken from a repository's own documentation and not independently verified here. |

NOTE: The educational code in this session is an adaptation made for teaching. It makes no claim of commercial deployment and gives no guarantee of production security.

## How to check the code yourself

The reference code in Part 4 is complete. To check it, copy the pieces of Part 4 into one file named `session01_reference.py` and write your own tests for the seven scenarios in the decision table of Part 6. Nothing in this document reports test results on your behalf: running the checks and reading their output is part of the learning.

To run your tests, open a terminal in the folder that holds the file and run the standard library test runner.

~~~sh
python3 -m unittest -v
~~~

# The Core Idea

## The problem in one paragraph

Imagine a coding agent or a specialist agent that reads a service and concludes that a retry setting is too low. It proposes raising `retry_limit` from 3 to 5. The agent can *describe* this change. It must never be able to *authorize* it by writing the word "Approved" into its own output.

In an existing system, the output of an agent is only a **change proposal**. It is not a permit to apply a patch, run a migration, change production settings, or read another tenant's data. The point where agent design meets multi-agent architecture and layered guardrails is one explicit contract: the contract between **proposal**, **approval** and **execution**.

CHECKPOINT: If an agent says "I approved it myself", which trust boundary has been broken? Write your answer in one sentence before you continue.

## Three core terms

| Term | Meaning |
|:-----|:--------|
| **Proposal** | A description of a change. It is data from an untrusted source. |
| **Approval** | Conditional permission for one specific change, issued by an authority the agent cannot impersonate. |
| **Execution** | A controlled attempt to apply the change, which re-checks every condition independently. |

Approval must come from a person or a service that holds authority, through a trusted path. Even after approval, execution must check the conditions again, because the world may have changed in between.

## The three-stage model with a fixed example

The fixed example used throughout this session:

- **Proposal.** For tenant `tenant-01`, change the key `retry_limit` in the logical target `app-config.json` from 3 to 5. The expected revision is 3. This is data from an untrusted source.
- **Approval.** A trusted authority approves proposal `P-001` for a specific digest, a specific tenant and target, with the authority of a named approver and a valid expiration time. The agent must not be able to forge the approver identifier or the authoritative record.
- **Execution.** When execution is requested, the system re-checks the same conditions. Only if the request is authorized and the revision still matches can a local transaction change the state and consume the approval.

CHECKPOINT: An approval was valid yesterday but has expired today. Is the proposal still executable?

## Two outcome families that must not be mixed

The gate and the executor answer two different questions, and their answers must never be merged into one status.

| Family | Values | Meaning |
|:-------|:-------|:--------|
| **Gate decision** | ALLOW, DENY, REVALIDATION_REQUIRED | Whether the conditions for *attempting* execution are currently satisfied. |
| **Execution result** | SUCCEEDED, FAILED, UNKNOWN | What actually happened when the attempt was made. |

ALLOW means the conditions for attempting execution are currently satisfied. DENY means the authority or policy condition is not satisfied. REVALIDATION_REQUIRED means the state has become stale and must be evaluated again. SUCCEEDED means the commit or the defined effect has completed. FAILED means a definite failure occurred. UNKNOWN means it is not known whether the effect took place.

The rule to remember is short: **ALLOW is not SUCCEEDED.**

Suppose the gate permits execution, and the connection to an external service drops right after the request is sent. Without sufficient evidence the result is UNKNOWN. Repeating the request blindly is dangerous. It needs reconciliation and idempotency mechanisms. The SQLite example in this session is not a complete state machine for external effects.

## A common misconception: a digest is not a signature

A digest is a fingerprint of content. It can reveal that a proposal has changed, but only when it is compared with a value held by a trusted authority. A digest does not prove who approved anything.

CHECKPOINT: If the agent can change both the proposal and the stored digest, what guarantee remains?

# Architecture and Threats

## The educational path and the trust boundary

The figure below shows the path a proposal takes. The agent only builds the proposal. The schema and the digest control the shape and the integrity of the request. Authority comes from the approval store and the trusted policy. The current revision is checked before the state is changed. In the SQLite example, the state change, the consumption of the approval and the audit record happen in a single local transaction.

IMG: assets/trust-boundary.png | Seven numbered layers from the agent through schema and digest, approval store, policy gate, revision check and atomic transaction to the execution result, with a trust boundary drawn under the agent | The educational path and the trust boundary

**Trust assumption.** The integrity of the database and the protection of the approval records are environmental prerequisites. The model's text is not a substitute for these controls.

**Claim boundary.** The atomicity of a SQLite transaction does not mean that file operations or external-service operations are atomic.

## Threats, controls and residual limits

| Threat | Control in this session | Residual limit |
|:-------|:------------------------|:---------------|
| Payload tampering | Digest comparison | Only as strong as the protection of the trusted digest |
| Tenant confusion | Lookup restricted to the tenant | Needs a storage-isolation policy |
| Unauthorized approver | Check of the approver's authority reference | Real identity verification is outside this example |
| Replay | Atomic consumption of the approval | Shown only for a local SQLite example |
| Stale revision | Compare-and-swap on the revision | External state may change independently |
| Crash between changes | Commit or rollback of one transaction | No crash-recovery test is presented |

## The fixed scenario and its initial state

**HYPOTHETICAL SCENARIO.** The logical target is `app-config.json`, the tenant is `tenant-01`, the operation is `set_config`, the key is `retry_limit`, the current value is 3, the proposed value is 5, and the expected revision is 3.

First the agent builds proposal `P-001`. Then a valid approver approves exactly that proposal. When execution is requested, the system re-checks the tenant, the authority, the digest, the expiration and the revision. A role permission is not the same thing as an approval bound to a digest.

WARNING: The educational SQLite state only simulates the configuration revision. The code never opens, locks, rewrites or flushes a real `app-config.json` file, so any claim of atomic file replacement would be incorrect.

## Three outcome paths

- **A - VALID.** The value is 5, the digest matches, the approval is valid and the current revision is 3. The gate decision is ALLOW. Only a successful commit of the local transaction can lead to SUCCEEDED.
- **B - TAMPERED.** After approval, the value 5 is changed to 9. The digest no longer matches. The result is DENY and the state does not change.
- **C - STALE.** The proposal is the same, but the current revision has become 4. The result is REVALIDATION_REQUIRED and the state does not change. A new proposal on the fresh revision, a new digest and a new valid approval are required. The old approval must not be reused.

CHECKPOINT: For each path, first state the gate result, and then, separately, the possible execution result and the reason.

# Building the Contract in Python

This part builds the reference implementation piece by piece. Read the pieces in order; together they form one complete file. Long lines wrap in print, and the wrapped part is indented by two spaces.

## Step 1: Imports, results and the proposal contract

A proposal must say who is asking for what, on which target, with which value, in which tenant, and based on which revision. The contract below is a deliberately small educational example. It is not a complete authorization policy.

**REFERENCE CODE.** Defining a data structure is not the same as being authorized to execute it.

~~~python
"""Course-authored reference, NOT a verbatim excerpt from any GitHub repository.

Demonstrates SQLite-local authorization and state transition, not real file I/O.
"""
from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import sqlite3

SAFE_MAX = 2**53 - 1
~~~

~~~python
class GateDecision(str, Enum):
    ALLOW = 'ALLOW'
    DENY = 'DENY'
    REVALIDATION_REQUIRED = 'REVALIDATION_REQUIRED'

class ExecutionResult(str, Enum):
    SUCCEEDED = 'SUCCEEDED'
    FAILED = 'FAILED'
    UNKNOWN = 'UNKNOWN'
~~~

~~~python
@dataclass(frozen=True)
class Proposal:
    proposal_id: str
    tenant_id: str
    target: str
    operation: str
    key: str
    value: int
    revision: int
~~~

The `frozen=True` option stops ordinary reassignment of the attributes. It is not proof of identity, validity of the data, or permission to execute.

CHECKPOINT: If only the value is changed to 9, is the previous approval still valid? It is not: the proposal has changed, so the digest match and every approval condition must be checked again.

## Step 2: Validating the shape of the data

Before a digest is built, data that could be ambiguous or outside the contract must be rejected. Python treats `True` as an `int`. That is why the validator uses `type(value) is int` and not a plain `isinstance` check.

**REFERENCE CODE.**

~~~python
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
~~~

The object must be exactly a `Proposal`. The identifier strings must be non-empty and made only of visible ASCII characters, which excludes spaces. The value must be a genuine integer from 1 to 10, and the revision a genuine non-negative integer within the safe range.

**Three assessment questions.** Is `value=True` accepted? No. Is a Unicode string outside visible ASCII accepted? No. Does passing this validator mean the request is authorized? No: approval, authority, tenant, digest, expiration, revision and policy must still be checked.

NOTE: This validator belongs to one fixed dataclass. It is not a complete parser for network requests.

## Step 3: A deterministic digest

The approval must be bound to an exact, deterministic representation of the proposal. If two versions of a proposal differ only in the order of their JSON keys, they must not receive different digests without a reason.

For that reason the keys are sorted and the separators are fixed. Then SHA-256 is applied to the output bytes. The digest must be kept together with the approval record in a trusted store, and the agent must not be able to change the reference digest.

**REFERENCE CODE.**

~~~python
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
~~~

Line by line: `validate` runs first. The fields are listed explicitly, in one place, so that adding a field to the dataclass can never silently change what an approval covers. `sort_keys=True` fixes the key order, `separators` removes unnecessary whitespace, and `ensure_ascii=True` matches the limited ASCII contract. Finally SHA-256 produces a hexadecimal digest.

WARNING: The canonical form used in this course is custom. It makes no claim of conformance with RFC 8785, and an equal digest alone does not prove the identity or the authority of the approver.

**Short exercise.** Change the value from 5 to 9 and explain why the approval bound to the previous digest can no longer be used for the new proposal.

## Step 4: The state and the trusted records

The reference code keeps its state in an in-memory SQLite database with four tables. The configuration state holds the value and its revision. The approvals table holds the trusted approval records. The approver permissions table says which approver may approve which operation in which tenant. The audit table records what was done.

**REFERENCE CODE.**

~~~python
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
~~~

`isolation_level=None` puts the connection in autocommit mode, so the code controls the transaction boundary explicitly with `BEGIN IMMEDIATE`. The `timeout` limits how long a writer waits for the lock.

## Step 5: Seeding the fixture

The seed function creates the starting state of the fixed scenario: configuration value 3 at revision 3, one approval for proposal `P-001` bound to the digest of the original proposal, and the approver's permission.

**REFERENCE CODE.**

~~~python
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
~~~

## Step 6: The policy gate, where no control is optional

The gate decides whether an execution attempt may start. It never changes state. Its checks run in a fixed order.

1. The contract and type of the proposal
2. The allowlist of operation, key and target
3. A valid trusted time
4. An approval record restricted to the tenant
5. The proposal identifier
6. The digest
7. The approved status
8. Expiration and target
9. The authority of the approver
10. The revision. A revision mismatch produces REVALIDATION_REQUIRED.

A SQL column name cannot be parameterized with a placeholder. That is why only one exact triple (`set_config`, `retry_limit`, `app-config.json`) is allowed, and it maps to one fixed column.

**REFERENCE CODE.**

~~~python
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
~~~

Notice the shape of the function: every failed condition returns DENY immediately, so the safe answer is the default. Only the last comparison decides between ALLOW and REVALIDATION_REQUIRED. ALLOW is permission to *attempt* local execution, and nothing more.

## Step 7: Transactional execution

Execution is where side effects happen, so it is the part that must be atomic. The function opens an immediate transaction, runs the gate again inside that transaction, and then performs three changes together: the compare-and-swap update of the configuration, the consumption of the approval, and the audit record. If anything fails before the commit, everything is rolled back and the error is raised again. It is never swallowed.

The `WHERE revision=?` condition in the update is the compare-and-swap: the update succeeds only if nobody changed the revision since the gate looked at it.

**REFERENCE CODE.**

~~~python
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
~~~

~~~python
DEFAULT = Proposal(
    'P-001', 'tenant-01', 'app-config.json', 'set_config', 'retry_limit', 5, 3
)
~~~

**Why one transaction.** The approval is consumed, the state is changed and the audit is written in a single local transaction. If they were separate, a crash between them could leave an approval spent without a change, or a change without a record.

## What this code does and does not prove

**Replay.** The uniqueness of `approval_id` and the change of the approval to CONSUMED prevent the same identifier from being used again. But there is no uniqueness constraint on the pair (`tenant_id`, `proposal_id`). Preventing repeated execution of one proposal under *different* approvals cannot be concluded from this code. A real design must define the approval-issuance policy, a suitable unique key, and a duplicate-approval test.

**Transaction and trust.** `BEGIN IMMEDIATE` coordinates the consumption of the approval, the state update and the audit record only inside the same SQLite database. The approver's identity, the permissions and the trusted clock are assumed to be trusted application inputs. Identity verification, independence of two approvers, security of policy changes and tamper-resistant audit are not proven by this code.

**Cases to design yourself.** A suite built only from the seven scenarios of the decision table mainly exercises sequential execution. It does not cover a race between two executors, two approvals for one proposal, the exact boundary of expiration, or an unknown state after a commit. In an ambiguous commit error this example does not return UNKNOWN: it raises the error and requires external reconciliation. For each of these four cases, write a negative test and an acceptance criterion. Do not present them as tested until you have run them.

# From ALLOW to Execution

## Why ALLOW is not execution

With one fixed request, you should now be able to explain the order of the gate checks and the three outputs DENY, REVALIDATION_REQUIRED and ALLOW. The pseudocode below only describes the decision logic. It performs no real operation on a file or a database.

**PSEUDOCODE.** Not executable, not an executor.

~~~text
function evaluate(proposal, approval, trusted_authority, trusted_now, current_revision):
    if exact_schema_invalid(proposal): return DENY
    if policy_invalid(proposal) or time_invalid(trusted_now): return DENY
    if approval_missing_or_not_approved(approval): return DENY
    if digest_mismatch(proposal, approval): return DENY
    if tenant_or_scope_mismatch(proposal, approval): return DENY
    if expired(approval, trusted_now) or not trusted_authority: return DENY
    if current_revision != proposal.revision: return REVALIDATION_REQUIRED
    return ALLOW
~~~

First the shape of the data and the policy are checked. Then the existence and status of the approval, the digest binding, the scope of tenant and operation, the expiration and the approver's authority are assessed. Only after that is the current revision compared with the proposal's revision. If all controls succeed, ALLOW is permission to attempt execution. The success of the change is not yet proven.

CHECKPOINT: The proposed value is still 5, but the current revision has become 4. Why is the output not DENY? Because, assuming the earlier controls pass, the only thing that changed is the state, so the answer is REVALIDATION_REQUIRED.

NOTE: This pseudocode is not a TypeScript implementation. The runtime, the validator, the exact digest serialization, the trusted store, the atomic transaction, the consumption of the approval and the audit record are not shown in it. Equivalence of execution between Python and TypeScript has not been proven.

## Architecture workshop: attaching the gate to a brownfield system

**HYPOTHETICAL SCENARIO.** An existing backend service keeps the `retry_limit` setting in a table named `service_config`. A specialized coding agent proposes, to reduce errors, that the value change from 3 to 5. The agent may only read code and produce a proposal. It has no direct access to the production database, the migration runner or the approval signing key.

The agent's output is untrusted data even if it contains the word "approved". Only an approval issued through an independent channel that holds authority is valid, after the approver's identity, the tenant, the scope, the digest, the expiration and the revision all match. The change must also be executed in an independent transaction together with an audit record.

| Layer in the existing system | Testable responsibility | Failure control |
|:-----------------------------|:------------------------|:----------------|
| Specialized coding agent | Produces a versioned proposal with a limited diff | No write access and no execution of sensitive tools |
| Proposal API | Canonicalizes and computes the digest from valid data | Rejects unknown input and incompatible schemas |
| Approval service | Records the decision of a person or service authorized independently of the agent | Rejects self-approval and invalid scope |
| Policy gate | Checks tenant, digest, revision, expiration, replay and allowlist | Fails closed; ALLOW is not yet execution |
| Transactional executor | One-time consumption of the approval, compare-and-swap and audit in one transaction | Rollback on error, no partial change applied |

**PSEUDOCODE.** This is an integration design, not a replacement for the executable reference file.

~~~text
proposal = proposal_api.validate_and_digest(agent_output)
approval = approval_store.load(proposal.approval_id)   # independent channel
with db.transaction(immediate=True):
    gate.assert_authorized(proposal, approval, current_revision)
    approval_store.consume_once(approval.id)
    config_repo.compare_and_swap(
        tenant=proposal.tenant_id,
        key="retry_limit",
        expected_revision=proposal.expected_revision,
        new_value=5,
    )
    audit_repo.append_execution(proposal.digest, approval.id)
# COMMIT only if every operation succeeds; exceptions must propagate
~~~

**Six design tests for the migration.**

1. A different tenant produces DENY.
2. A value change after approval produces a digest mismatch.
3. A stale revision produces a conflict.
4. Repeated consumption of an approval is denied as replay.
5. An audit write error rolls back all changes.
6. The text "approved" in the agent's response, without an independent approval, produces DENY.

**Measurable output of the workshop.** One five-layer sequence diagram. One short architecture decision record on where the gate runs. One threat and control matrix with the six scenarios above. A migration plan that does not break the existing API, using a feature flag, regression tests, shadow evaluation and a rollback path.

**Acceptance criterion.** There is no direct execution path from the agent to the executor, and all six negative tests are covered.

WARNING: This is an educational architecture. Correctness in production requires review of real transactions, concurrency, idempotency, access levels and deployment.

## Three teachable scenarios

**CONCEPTUAL CLASSROOM DEMONSTRATIONS.** These are expectations to reason about, not reports of test runs.

- **Case 01 - valid approval.** Proposal `P-001` for `tenant-01`, value 5, revision 3, has a matching digest, a valid approval and an active approver. The expected gate result is ALLOW. SUCCEEDED may be reported only after the local transaction commits.
- **Case 02 - tampered proposal.** The approval remains for value 5, but the submitted value becomes 9. The digest no longer matches. The expected result is DENY and the state does not change.
- **Case 03 - replay.** A single-use approval is presented again after it has been used. The expected result of the second attempt is DENY, and the revision increases only once.

# The Pattern in Real Systems

This part connects the session to real code. Excerpts below come from repositories of the author, are pinned to a commit and a file checksum, and are short. They are shown to illustrate the pattern, not to certify the security of the projects they belong to.

## Source excerpt: approval levels in AEGIS Agent

**SOURCE EXCERPT.** Repository `aminazimi42-coder/aegis-agent`, file `core/human_authority.py`, commit `4f310113c49c`.

~~~python
class ApprovalLevel(Enum):
    AUTO = auto()
    SINGLE_APPROVAL = auto()
    DUAL_APPROVAL = auto()
    DENY = auto()
~~~

This excerpt shows a *classification* of approval levels. It is not automatic approval by an agent. AUTO is only the decision of a trusted policy, and DUAL_APPROVAL lies outside the single-approver example of this session. A risk classification alone is not an approval record bound to a digest.

## Source excerpt: a role check inside a tenant

**SOURCE EXCERPT.** Repository `aminazimi42-coder/aegis-agent`, file `core/authority_matrix.py`, commit `f845ab702fba`.

~~~python
def check_permission(self, tenant_id: str, actor: str, permission: str) -> bool:
    with self._lock:
        roles = self._assignments.get(tenant_id, {}).get(actor, [])
        for r in roles:
            role = self._roles.get(r)
            if role and permission in role.permissions:
                EvidenceLedgerSingleton.append_entry(
                    tenant_id=tenant_id,
                    actor="authority_matrix",
                    action="check_permission",
                    payload={"actor": actor, "permission": permission, "result": True},
                )
                return True
        EvidenceLedgerSingleton.append_entry(
            tenant_id=tenant_id,
            actor="authority_matrix",
            action="check_permission",
            payload={"actor": actor, "permission": permission, "result": False},
        )
        return False
~~~

This function only checks a role permission within a tenant. By itself it is not a substitute for an approval bound to a digest. For each of the three outcome paths of this session, ask yourself which check this function could answer and which it could not.

## Source excerpt: agent capabilities in AlinaMatrix Enterprise

**SOURCE EXCERPT.** Repository `aminbita162-glitch/AlinaMatrix-Enterprise`, file `packages/domain/src/agents.ts`, commit `47eb2c2a108f`.

~~~typescript
export const AGENT_CAPABILITIES: Readonly<Record<AgentName, ReadonlySet<AgentCapability>>> = {
  AlinaArchitect: new Set(["READ_SOURCE", "READ_EVIDENCE", "WRITE_DRAFT"]),
  AlinaGuard:     new Set(["READ_EVIDENCE", "RUN_VALIDATION"]),
  AlinaDocEngine: new Set(["COMPILE_ARTIFACT"]),
  AlinaOptimizer: new Set(["READ_USAGE", "WRITE_CACHE_METADATA"]),
};
~~~

`READ_SOURCE` and `WRITE_DRAFT` are *agent capabilities*. They are not a human's authority to approve a release or to execute a change. The types `AgentName` and `AgentCapability` are defined elsewhere in the code.

## The same pattern in four projects

The table maps this session's ideas to four public repositories. Each row is labeled SOURCE-REPORTED unless it points to a pinned excerpt above: it reflects what the repository's own documentation states, and it is the starting point for your own reading.

| Project | Where the pattern appears | Label |
|:--------|:--------------------------|:------|
| AEGIS Agent | A twin proposes actions and a human must approve before anything executes; approval levels and tenant-scoped permission checks | SOURCE EXCERPT and SOURCE-REPORTED |
| AlinaMatrix Enterprise | Agents with explicit capability sets; human review, four-eyes approval and a release gate between evidence and published artifacts | SOURCE EXCERPT and SOURCE-REPORTED |
| AminOpsTwin | Five agents behind two deterministic services: a policy gateway with deny-by-default checks and a durable executor; no agent holds a direct handle to the database or the executor store | SOURCE-REPORTED |
| Kian Trading Intelligence | A deterministic risk and safety kernel: no exposure-increasing order may reach an exchange adapter without valid authorization, and no model output directly authorizes or executes orders | SOURCE-REPORTED |

| Project | Repository | Further reading |
|:--------|:-----------|:----------------|
| AEGIS Agent | github.com/aminazimi42-coder/aegis-agent | Interactive API reference (Swagger UI): aegis-agent-haka.onrender.com/docs |
| AlinaMatrix Enterprise | github.com/aminbita162-glitch/AlinaMatrix-Enterprise | README and the documents in its docs folder |
| AminOpsTwin | github.com/aminbita162-glitch/AminOpsTwin | README, section on the two shared services |
| Kian Trading Intelligence | github.com/aminbita162-glitch/kian-trading-intelligence | README, architecture section |

NOTE: The Swagger page of AEGIS Agent runs on a free hosting tier. The first request after a period of inactivity can take a minute.

## What the evidence establishes

A good engineer separates what was observed from what may be claimed and from what is not proven. Use this table whenever you describe the reference code to someone else.

| Claim | Assessment and scope |
|:------|:---------------------|
| The classroom example binds an approval to a proposal and applies policy and revision controls | A limited educational claim, valid under the stated assumptions |
| Consumption of the approval happens inside a local SQLite transaction | True only for local SQLite, not for external side effects |
| The system is cryptographically identity-authenticated | Not proven. Do not claim it. |
| A real file was rewritten atomically | Not proven. Do not claim it. |
| Python and TypeScript behave identically at runtime | Not proven. Do not claim it. |
| Crash recovery was tested and verified | Not proven. Do not claim it. |

Identity assurance, management of authorities, multi-process concurrency, transaction durability, audit retention, distributed effects and resolution of the UNKNOWN state each need their own evaluation and their own evidence.

CHECKPOINT: If a SQLite test succeeds, can we say that a file change in the operating system is also atomic? No. These are two different test scopes.

## Decision table for the fixed scenarios

The execution result is SUCCEEDED only in the valid scenario, and only if the transaction completes successfully.

| Scenario | Gate | State change | Execution result | Reason |
|:---------|:-----|:-------------|:-----------------|:-------|
| Valid | ALLOW | Yes, on successful execution | SUCCEEDED | Digest, policy and revision are valid |
| Tampered: 9 | DENY | No | Not executed | Digest mismatch; 9 is within the policy range |
| Stale: revision 4 | REVALIDATION_REQUIRED | No | Not executed | The revision on which the approval is based is stale |
| Replay | DENY | No | Not executed | The approval is already CONSUMED |
| Tenant mismatch | DENY | No | Not executed | Tenant scope does not match |
| Expired | DENY | No | Not executed | The trusted validity period has passed |
| Unauthorized approver | DENY | No | Not executed | The authority reference does not allow it |

# Exercises and Self-Check

## The paper fixture

**HYPOTHETICAL, PAPER-BASED, NO DOWNLOAD REQUIRED.** The initial state: the tenant is `tenant-01`, the logical target is `app-config.json`, the value is `retry_limit=3`, and the revision is 3. Proposal `P-001` requests `set_config` for the key `retry_limit` with value 5 and expected revision 3.

Approval `A-001` exists in the trusted store. The proposal and tenant identifiers match. The operation and the target match. The stored digest is that of the original proposal with value 5. The status is APPROVED, the approval has not expired, the approver's authority is active, and the approval is single-use.

## First 15 minutes

**Task A - 5 minutes.** Identify the three stages proposal, approval and execution. Underline the fields that must be bound to the approval.

**Task B - 5 minutes.** For the original proposal, choose one of ALLOW, DENY or REVALIDATION_REQUIRED and explain why ALLOW is still not SUCCEEDED.

**Task C - 5 minutes.** Change only the submitted proposal value from 5 to 9 and keep the stored approval unchanged. State the gate decision and the single control that rejects this change.

## Second 15 minutes

**Task D - 5 minutes.** Restore the original `P-001` with value 5 and expected revision 3, but set the current revision to 4. First guess the gate result. Then explain why the old approval cannot be used automatically after the revision changes.

**Task E - 5 minutes.** Assume revision 3, and imagine that the first authorized local transaction has committed successfully, set `retry_limit` to 5, advanced the revision to 4 and marked `A-001` as CONSUMED. The same approval is submitted again. Analyze the result and whether a second state change is possible. Teaching point: the consumed status is checked before the revision mismatch.

**Task F - 5 minutes.** Build a three-row table with the rows original, tampered and replay. For each row write the gate decision, whether the state changes, and the reason. Then explain why the consumption of the approval and the protected state change must be in a single local transaction, and name two limitations of the example.

**Hand-in.** An annotated table and a short explanation of atomicity. This paper exercise needs no code download, no connection to a real system and no external side effect.

**Task G - optional, 5 minutes, after the main plan.** After the transaction reaches `commit()`, the connection is cut before the acknowledgement is received. What is the safe result to report? Why is automatic retry without reconciliation and idempotency unsafe?

## Answer key

Try every task on paper before you read this section.

**Task A.** The three stages are the proposal (untrusted data describing the change), the approval (a trusted record issued by an authority the agent cannot impersonate) and the execution (the controlled attempt). The fields bound to the approval are the proposal identifier, the tenant, the target, the operation, the key, the value and the revision, and the approval also carries the digest of all of them.

**Task B.** The gate decision is ALLOW: every condition is satisfied and the revision is current. ALLOW is not SUCCEEDED because it only says an attempt may start. The result is SUCCEEDED only if the local transaction then commits.

**Task C.** The gate decision is DENY. The control that rejects it is the digest comparison: the digest of the submitted proposal with value 9 differs from the digest stored with the approval. The value 9 is inside the policy range, so the policy check alone would not have caught it.

**Task D.** The gate decision is REVALIDATION_REQUIRED. The approval was issued for the state at revision 3. When the revision has moved to 4, the world the approver looked at no longer exists. A new proposal on the fresh revision, a new digest and a new approval are required.

**Task E.** The second attempt is DENY. The approval has the status CONSUMED, and that check comes before the revision comparison, so the answer is not REVALIDATION_REQUIRED. A second state change is not possible: the revision increased only once.

**Task F.**

| Row | Gate decision | State changes | Reason |
|:----|:--------------|:--------------|:-------|
| Original | ALLOW | Yes, only if the transaction commits | All conditions hold and the revision is current |
| Tampered | DENY | No | The digest does not match the approval |
| Replay | DENY | No | The approval is already CONSUMED |

The approval consumption and the state change must be in one local transaction. Otherwise a crash between them could spend the approval without changing the state, or change the state while the approval remains usable and can be replayed. Two limitations of the example: the atomicity covers only the local SQLite database, not a real file or an external service; and the approver identity, the permissions and the clock are assumed to be trusted inputs.

**Task G.** The safe result to report is UNKNOWN. Without evidence of whether the commit took effect, reporting SUCCEEDED or FAILED would be a guess. Automatic retry is unsafe because if the first attempt did succeed, a second attempt could apply the change twice. Safe recovery needs reconciliation, which means reading back the actual state, and idempotency, which means that repeating the request cannot repeat the effect.

# Summary, Sources, and Next Session

## Five key principles

1. A proposal is not an authority reference.
2. An approval must be bound to the exact data and the scope.
3. Authority is re-checked at the moment of execution.
4. The gate decision is separate from the execution result.
5. A single-use approval is consumed together with the protected state change.

## Provenance register of the three code excerpts

All three files were read at the stated commit on GitHub, and their blob identifiers were matched in November 2026. A blob match establishes that the excerpt corresponds to the pinned file. It does not certify the security of a whole project.

| Source | AEGIS Agent, core/human_authority.py |
|:-------|:-------------------------------------|
| Repository | aminazimi42-coder/aegis-agent |
| Commit | 4f310113c49c0ea17c865a5af2670c0a01707655 |
| Blob SHA | 8e3c6a4defe0b4263ccc8cba1ef87435eee26877 |
| License status | Proprietary, all rights reserved (LICENSE file of the repository). Excerpt reproduced by the rights holder. |

| Source | AEGIS Agent, core/authority_matrix.py |
|:-------|:--------------------------------------|
| Repository | aminazimi42-coder/aegis-agent |
| Commit | f845ab702fbafe1b6b6ea2abca842de50c7bb206 |
| Blob SHA | 9409ecd6046e6c3d03026c9f01c05fe57a05e7fc |
| License status | Proprietary, all rights reserved (LICENSE file of the repository). Excerpt reproduced by the rights holder. |

| Source | AlinaMatrix Enterprise, packages/domain/src/agents.ts |
|:-------|:------------------------------------------------------|
| Repository | aminbita162-glitch/AlinaMatrix-Enterprise |
| Commit | 47eb2c2a108f91bd2c8d3f0311a79d30cec26971 |
| Blob SHA | ca3ac3ce6672a0590a4198264aac0a298fbd3cb5 |
| License status | All rights reserved (stated in the repository README; the repository has no LICENSE file). Excerpt reproduced by the rights holder. |

## Official references

- Python sqlite3 module: docs.python.org/3/library/sqlite3.html
- Python json module: docs.python.org/3/library/json.html
- Python hashlib module: docs.python.org/3/library/hashlib.html
- JavaScript Number.isSafeInteger: developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Number/isSafeInteger

## Before you move on

Explain one decision path from this session out loud, with its reason, rather than only repeating the name of a status. Your explanation should show how the approval connects to the digest, the revision and the scope, and it should make clear that ALLOW is only permission to enter the execution stage.

For the replay scenario, state the difference between *consuming one approval* and *preventing the repeated execution of a proposal*. If your answer ignores the boundary of the SQLite transaction and of external side effects, revisit the section on what the code does and does not prove.

**Next session.** Session 02 - Proposal Contract and Structured Output.
