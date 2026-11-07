# Phase 6 WP1 — Threat Model and Current-State Audit

**Date:** November 2026  
**Phase:** P6 — Release Security / Authenticity / Provenance  
**Status:** Evidence document; no release-mode enablement

---

## 1. Current-State Inventory

### 1.1 Source modules

| Module | Path | Purpose | Lines |
|--------|------|---------|-------|
| release_security | engine/release_security.py | Offline Ed25519 approval primitives: canonical_payload, verify_signature, ApprovalError | 73 |
| trust | engine/release/trust.py | Fail-closed public-key trust registry: active_public_key, rejects malformed/revoked/oversized | 35 |
| authorization | engine/release/authorization.py | Signed owner approval + exact release context binding: authorize_release, hmac.compare_digest | 26 |
| replay | engine/release/replay.py | Durable, atomic replay reservation: reserve_approval, O_EXCL, fsync, symlink rejection | 52 |
| gate | engine/release/gate.py | Preflight-only signed release gate: validate_and_reserve_release, no delivery | 30 |
| atomic_delivery | engine/release/atomic_delivery.py | Fail-closed no-overwrite PDF placement: place_verified_snapshot, O_NOFOLLOW, source-change detection | 105 |
| audit_ledger | engine/release/audit_ledger.py | Durable append-only-by-creation event records: record_release_event, O_EXCL, fsync | 52 |
| pipeline | engine/release/pipeline.py | Owner-gated release pipeline: execute_authorized_release, authorize→reserve→audit→place→audit | 54 |
| document_authenticity | engine/document_authenticity.py | Content authenticity (QR-level, separate domain): canonical_statement, verify_content_statement | 93 |
| tools_core | engine/tools_core.py | deliver_pdf: draft works, release HARD-DISABLED (ConfigError) | 283 |
| cli | engine/cli.py | deliver subcommand with draft/release modes | 129 |
| gates | engine/gates/__init__.py | Placeholder stub (verify_release_package returns True) | 3 |

### 1.2 Existing test files (all PASSING, 390 total — 384 at WP1 + 6 P6 regression tests, commit dbc77b9)

| Test file | Tests | Coverage |
|-----------|-------|----------|
| test_release_security.py | 8 | Canonical payload determinism, domain separation, field validation, unknown key, invalid signature, positive+tamper |
| test_release_security_adversarial.py | 5 | Every-field tamper, malformed signatures (None/empty/short/long/non-string), invalid registries, invalid payloads (missing field, extra field, path escape, bad hash, empty value, wrong type, oversized) |
| test_release_authorization.py | 5 | Valid authorization, every binding mismatch, tampered signature, revoked key, missing context |
| test_release_trust_registry.py | 4 | Active key, unknown/revoked, malformed registry (wrong key size, bad status, extra field, bad identifier), invalid key_id |
| test_release_replay.py | 4 | First reservation+replay, invalid IDs, world-readable state rejection, symlink state rejection |
| test_release_gate.py | 4 | Authorizes before reserving, invalid auth never reserves, replay propagation, no delivery side effect |
| test_release_pipeline.py | 6 | Success records both events, replay denied, bad signature no side effects, digest mismatch consumes+records failure, audit reservation failure prevents delivery, delivery audit failure requires reconciliation |
| test_release_atomic_delivery.py | 5 | Success+no overwrite, digest mismatch leaves no temp, symlink not followed, private directory required, no delete on post-link fsync failure |
| test_release_atomic_boundary.py | 6 | Source symlink denied, destination symlink preserved, changed source rejected, existing destination never replaced, failure before link cleans temp, success snapshot integrity |
| test_release_atomic_source_consistency.py | 2 | Valid source, source modified during copy rejected |
| test_release_audit_ledger.py | 5 | Records exact event, replay rejected, public directory rejected, symlink rejected, invalid fields |
| test_document_authenticity.py | 7 | Valid+digest, each field tampered, unknown/wrong key, bad signatures, bad fields, canonical+duplicate JSON, domain separation |
| test_v052.py | 10 | Draft delivery, release disabled, delivery JSON, no overwrite, exit codes |
| test_release_phase6_gaps.py | 6 | S12 concurrent race (Barrier(2), exactly one O_EXCL winner), S16 EACCES (real chmod 0o500) + EPERM (mocked errno=1), key rotation (revoked→rejected, active→accepted, old≠new) |

### 1.3 Release-mode fail-closed invariant (REQUIRED)

`deliver_pdf()` in `engine/tools_core.py` line 190:
```python
if mode == "release":
    raise ConfigError("release temporarily disabled pending cryptographic owner authorization")
```

This is a **hard gate** — release mode raises before any filesystem operation. The cryptographic pipeline (`engine/release/pipeline.py`) is NOT connected to the public delivery CLI. Draft mode operates independently and is not affected by the release gate. This invariant is tested by `test_v052.py`.

---

## 2. Threat Model

### 2.1 Assets

| Asset | Description | Sensitivity |
|-------|-------------|-------------|
| PDF artifact | Built document; must be immutable after release | High — tampering changes content |
| Manifest | JSON manifest with input/output hashes, audit results | High — spoofing hides failures |
| Release approval | Ed25519-signed authorization payload | Critical — authorizes release |
| Signing private key | Ed25519 private key for release approval | Critical — never in repo/logs/PDF |
| Trust registry | Mapping key_id → {public_key, status} | High — substitution enables forged releases |
| Replay state | O_EXCL reservation files per approval_id | High — deletion enables replay |
| Audit ledger | Append-only event records | High — deletion hides evidence |
| Destination filesystem | Release output directory | High — symlink/overwrite attacks |

### 2.2 Principals

| Principal | Role | Trust level |
|-----------|------|-------------|
| Owner (Amin Azimi) | Holds signing key, approves releases, controls trust registry | Trusted root |
| Engine | Executes build/audit/delivery pipeline | Trusted within boundaries |
| Attacker | Adversary with filesystem access, network access, or signing-key theft | Untrusted |
| Build system | CI/CD or local build environment | Semi-trusted (can be compromised) |

### 2.3 Trust Boundaries

1. **Owner → Engine:** Owner provides signed approval + trusted public keys. Engine verifies but never generates signatures.
2. **Engine → Filesystem:** Engine writes to controlled directories. All paths are confined (resolve_inside). Symlinks are rejected at every entry point.
3. **Build output → Release pipeline:** Build produces PDF + manifest. Release pipeline independently verifies digest before placement. No trust inheritance from build to release.
4. **Network → Local:** No network calls in release pipeline. All verification is offline. No online revocation checking.

### 2.4 Attackers and Failure Modes

| Attacker capability | Attack vector | Existing control |
|---------------------|---------------|-------------------|
| Filesystem traversal | `../escape` in approval_id, document_id, destination | IDENT regex rejects path separators; resolve_inside confines all paths |
| Symlink substitution | Symlink at destination, source, or state dir | O_NOFOLLOW on all file ops; is_symlink() checks in replay, atomic_delivery, audit_ledger |
| TOCTOU race | Source changed between read and placement | Source inode identity check (st_dev, st_ino, st_size, st_mtime_ns, st_ctime_ns) |
| Replay attack | Reuse consumed approval_id | O_EXCL reservation; no rollback on failure; approval remains consumed |
| Rollback attack | Replace trust registry with old version | Registry must be caller-provided; no persistent registry in repo; status field rejects revoked keys |
| Key substitution | Replace public key in registry | Registry record schema validated: {public_key: 32 bytes, status: active\|revoked}; no extra fields |
| Digest spoofing | Tampered artifact with matching hash | SHA-256 64-hex validation; hmac.compare_digest for binding; source-change detection |
| Manifest tampering | Modify manifest after build | Manifest hash bound in approval payload; verify_document checks manifest |
| Truncated signature | Short signature, wrong base64 | Length checks (64 bytes), base64 strict decode, noncanonical rejection |
| World-readable state | Leaked replay/audit files | Permission checks: st_mode & 0o077 must be zero; directories must be 0o700 |
| Concurrent release | Two simultaneous release attempts | O_EXCL on reservation and audit events; only one wins |
| Crash mid-delivery | Power failure or crash during fsync | No destination cleanup on failure; fsync of file + directory; AtomicPlacementUncertain for manual reconciliation |
| Forged approval | Self-signed payload with unknown key | Trust registry lookup by key_id; unknown key → ApprovalError |
| Empty/oversized fields | Empty owner_id, 257-char policy_version | String validation: non-empty, max 256 chars, IDENT regex |
| Domain confusion | Release-approval signature used for content authenticity | Separate DOMAIN prefixes (RELEASE-APPROVAL/V1 vs CONTENT-AUTHENTICITY/V1) |

### 2.5 Existing Controls Already Implemented

| Control | Implementation | Test |
|---------|----------------|------|
| Canonical JSON serialization | json.dumps(sort_keys, separators, ensure_ascii, allow_nan=False) + DOMAIN prefix | test_release_security::test_deterministic |
| Domain separation | DOMAIN = b"AZIMI-PUBLISHING-ENGINE/RELEASE-APPROVAL/V1\x00" | test_release_security::test_domain_separation |
| Field validation | FIELDS frozenset, HEX regex, IDENT regex, length limits | test_release_security_adversarial::test_invalid_payloads_rejected |
| Ed25519 signature verification | verify_signature with trusted public keys | test_release_security::test_positive_and_tamper_when_crypto_available |
| Trust registry validation | active_public_key: size, schema, key format, status | test_release_trust_registry |
| Binding to expected context | authorize_release: hmac.compare_digest on 6 required fields | test_release_authorization::test_every_binding_mismatch |
| Key revocation | status: "revoked" → ApprovalError | test_release_authorization::test_revoked_key |
| Atomic replay reservation | O_EXCL, O_NOFOLLOW, fsync, private dir check | test_release_replay |
| Atomic PDF placement | O_NOFOLLOW, private temp inode, fsync, hard-link, no-overwrite | test_release_atomic_delivery + test_release_atomic_boundary |
| Source change detection | Inode identity check after streaming | test_release_atomic_source_consistency |
| Audit ledger | O_EXCL, fsync, private dir, append-only | test_release_audit_ledger |
| Pipeline ordering | authorize → reserve → audit → place → audit | test_release_pipeline |
| Pipeline failure recovery | Record failed/uncertain; no destination cleanup | test_release_pipeline::test_delivery_audit_failure_requires_reconciliation |
| Release hard-disabled | ConfigError before any FS operation | test_v052 |
| Content authenticity (separate domain) | canonical_statement, verify_content_statement | test_document_authenticity |

---

## 3. Gap Analysis (WP3-WP4 Coverage)

### Already covered by existing tests:
- Path traversal (S09): IDENT regex + resolve_inside
- Corrupt artifact (S10): digest mismatch in atomic_delivery and pipeline
- Interrupted write (S11): fsync failure, crash recovery
- Tampered metadata (S13): every-field tamper in adversarial tests
- Silent false-PASS (S19): existing destination never replaced
- Stale/forged approval (S20): binding mismatch, revoked key
- Wrong context (S32): binding mismatch on all 6 fields
- Unauthorized release (S33): release disabled, draft works
- Symlink swap (S38): source/dest/state/audit symlink rejection
- Domain separation (S35): separate DOMAIN prefixes, tested

### Gap status after regression tests (commit dbc77b9, 390/390 pass):

- **S12 (concurrency/race):** CLOSED by regression test. `test_release_phase6_gaps::ConcurrentRaceTests::test_exactly_one_concurrent_reservation_succeeds` — two threads synchronized on `threading.Barrier(2)` both call `reserve_approval` on the same approval ID; O_EXCL atomicity guarantees exactly one winner (the `.used` file is written) and exactly one loser (`ReplayError("already reserved")`). Asserts `len(winners) == 1` and `len(losers) == 1`.
- **S16 (permission denied):** CLOSED by regression tests. `test_release_phase6_gaps::PermissionDeniedTests::test_eacces_from_os_open_raises_replay_error` — real EACCES via `chmod(0o500)` on a private directory (passes `st_mode & 0o077 == 0` privacy pre-check but denies `os.open(O_CREAT)` at the syscall level); `test_eperm_from_os_open_raises_replay_error` — mocked EPERM (errno=1, distinct from EACCES errno=13) via `patch("engine.release.replay.os.open", side_effect=PermissionError(1, ...))`. Both surface as `ReplayError("cannot reserve approval")` with no `.used` file created.
- **Key rotation (lifecycle):** CLOSED by regression tests. `test_release_phase6_gaps::KeyRotationTests` — a two-key registry `{owner-1: {public_key: old, status: revoked}, owner-2: {public_key: new, status: active}}`; old key raises `ApprovalError("key not trusted or revoked")`, new key returns its bytes, `old != new`. Three tests: `test_revoked_old_key_rejected`, `test_active_new_key_accepted`, `test_rotation_old_fails_new_succeeds`.
- **Stale timestamp / expiry:** OPEN — owner-decision-gated. No timestamp field in current schema. The contract v1.0 proposes clock skew and offline expiration policy as open decisions. **This requires owner approval per WP2 before implementing.** Not a vulnerability — deferred by design.

---

## 4. Required Invariant: Release Fail-Closed

**INVARIANT:** `deliver_pdf(mode="release")` MUST raise `ConfigError` before any filesystem operation until the owner separately approves the cryptographic release gate and activates release mode.

**Evidence:** `engine/tools_core.py:190` — `raise ConfigError("release temporarily disabled pending cryptographic owner authorization")`  
**Test:** `test_v052.py` — `deliver_pdf(root, "courses/doc", "release")` raises  
**Status:** PASSING (390/390 tests, release remains disabled)
