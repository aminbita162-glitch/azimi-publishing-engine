# Phase 6 WP5 — Security Assurance Matrix

**Date:** November 2026  
**Phase:** P6 — Release Security / Authenticity / Provenance  
**Status:** Assurance matrix for owner review; release remains DISABLED

---

## Security Assurance Matrix: Threat → Control → Negative Test

| # | Threat | Control | Negative Test | Result |
|---|--------|---------|---------------|--------|
| 1 | Path traversal in approval fields | IDENT regex rejects path separators; resolve_inside confines all paths | test_release_replay::test_invalid_ids ("../escape", "a/b") | PASS |
| 2 | Path traversal in trust registry key_id | _KEY_ID regex; resolve_inside | test_release_trust_registry::test_invalid_key_id ("", "../secret", "a b", None) | PASS |
| 3 | Unknown/extra approval fields | FIELDS frozenset; set equality check | test_release_security::test_reject_unknown_field; test_release_security_adversarial::test_invalid_payloads_rejected | PASS |
| 4 | Wrong action (draft instead of release) | action MUST be "release" | test_release_security::test_reject_wrong_action | PASS |
| 5 | Malformed SHA-256 digest | HEX regex (64 lowercase hex); not-a-hash rejected | test_release_security::test_reject_bad_digest; test_release_security_adversarial::test_invalid_payloads_rejected | PASS |
| 6 | Uppercase hex digest | HEX regex is lowercase-only | test_release_security_adversarial::test_invalid_payloads_rejected ("A"*64) | PASS |
| 7 | Unknown signing key | Trust registry lookup; key not found → ApprovalError | test_release_security::test_reject_unknown_key | PASS |
| 8 | Invalid signature (wrong key) | Ed25519 verification fails | test_release_security::test_reject_invalid_signature_or_missing_dependency | PASS |
| 9 | Tampered payload after signing | Every field verified via canonical_payload; signature covers full message | test_release_security_adversarial::test_every_signed_field_tamper_rejected (8 fields) | PASS |
| 10 | Truncated/oversized signature | Length check (64 bytes); base64 strict decode | test_release_security_adversarial::test_malformed_signatures_rejected (None, "", "!!!", 63-byte, 65-byte, non-string) | PASS |
| 11 | Invalid trust registry | Schema validation: {public_key, status}; size <= 256; key format | test_release_trust_registry::test_malformed_registry (wrong size, bad status, extra field, bad identifier) | PASS |
| 12 | Revoked key | status != "active" → ApprovalError | test_release_authorization::test_revoked_key; test_release_trust_registry::test_unknown_or_revoked | PASS |
| 13 | Binding mismatch (any of 6 fields) | hmac.compare_digest on {owner_id, document_id, artifact_sha256, manifest_sha256, policy_version, destination} | test_release_authorization::test_every_binding_mismatch (all 6) | PASS |
| 14 | Missing authorization context | set(expected) != _REQUIRED → ApprovalError | test_release_authorization::test_missing_context | PASS |
| 15 | Tampered signature (altered approval_id) | Signature covers full canonical payload including approval_id | test_release_authorization::test_tampered_signature | PASS |
| 16 | Replay (reuse approval_id) | O_EXCL reservation; second use → ReplayError | test_release_replay::test_first_reservation_and_replay | PASS |
| 17 | World-readable state directory | st_mode & 0o077 != 0 → ReplayError | test_release_replay::test_world_readable_state_rejected | PASS |
| 18 | Symlink state directory | is_symlink() check; O_NOFOLLOW | test_release_replay::test_symlink_state_rejected | PASS |
| 19 | Invalid approval ID format | _ID regex: [A-Za-z0-9][A-Za-z0-9._-]{0,127} | test_release_replay::test_invalid_ids (empty, path escape, too long, None) | PASS |
| 20 | Authorization fails before reservation | Gate ordering: authorize → reserve | test_release_gate::test_invalid_authorization_never_reserves | PASS |
| 21 | Replay failure propagates | reserve_approval error propagates; no silent success | test_release_gate::test_replay_failure_propagates | PASS |
| 22 | Gate has no delivery side effect | No shutil.copy2 call during gate | test_release_gate::test_gate_has_no_delivery_side_effect | PASS |
| 23 | Digest mismatch in placement | SHA-256 verified after streaming; mismatch → AtomicDeliveryError | test_release_atomic_delivery::test_digest_mismatch_leaves_no_final_or_temp; test_release_pipeline::test_digest_mismatch_consumes_and_records_failure | PASS |
| 24 | Source symlink at placement | is_symlink() check on source | test_release_atomic_boundary::test_source_symlink_denied | PASS |
| 25 | Destination symlink at placement | os.stat(follow_symlinks=False); O_NOFOLLOW; existing symlink not replaced | test_release_atomic_boundary::test_destination_symlink_preserved; test_release_atomic_delivery::test_existing_symlink_not_followed_or_deleted | PASS |
| 26 | Source changed during streaming | Inode identity check (st_dev, st_ino, st_size, st_mtime_ns, st_ctime_ns) | test_release_atomic_source_consistency::test_source_modified_during_copy_fails_without_final | PASS |
| 27 | Existing destination never replaced | os.stat before link; FileExistsError → error | test_release_atomic_boundary::test_existing_destination_never_replaced | PASS |
| 28 | Private directory required | st_uid == os.getuid(); st_mode & 0o077 == 0 | test_release_atomic_delivery::test_private_directory_required | PASS |
| 29 | Post-link fsync failure | File exists but durability uncertain; AtomicPlacementUncertain; file NOT deleted | test_release_atomic_delivery::test_final_file_not_deleted_on_post_link_fsync_failure | PASS |
| 30 | Pre-link failure cleans temp | os.link failure; temp file unlinked + fsync | test_release_atomic_boundary::test_failure_before_link_cleans_temporary | PASS |
| 31 | Audit replay (same event twice) | O_EXCL on event file; FileExistsError → AuditLedgerError | test_release_audit_ledger::test_rejects_replay_without_overwrite | PASS |
| 32 | Audit public directory | st_mode & 0o077 != 0 → AuditLedgerError | test_release_audit_ledger::test_rejects_public_directory | PASS |
| 33 | Audit symlink directory | is_symlink() check; O_NOFOLLOW | test_release_audit_ledger::test_rejects_symlink_directory | PASS |
| 34 | Invalid audit fields | _ID and _DIGEST regex; status in allowed set | test_release_audit_ledger::test_rejects_invalid_fields | PASS |
| 35 | Pipeline: bad signature no side effects | Authorize fails → no reserve, no audit, no placement | test_release_pipeline::test_bad_signature_no_side_effects | PASS |
| 36 | Pipeline: replay denied | Second run with same approval → error; destination unchanged | test_release_pipeline::test_replay_denied_no_overwrite | PASS |
| 37 | Pipeline: audit reservation failure | Reserve succeeds, audit fails → no placement | test_release_pipeline::test_audit_reservation_failure_prevents_delivery | PASS |
| 38 | Pipeline: delivery audit failure | Placement succeeds, audit fails → uncertain event; manual reconciliation | test_release_pipeline::test_delivery_audit_failure_requires_reconciliation | PASS |
| 39 | Pipeline: success records both events | Reserved + delivered audit events created | test_release_pipeline::test_success_records_both_events | PASS |
| 40 | Content authenticity: domain separation | Separate DOMAIN prefix; RELEASE-APPROVAL not in CONTENT-AUTHENTICITY | test_document_authenticity::test_domain_separation | PASS |
| 41 | Content authenticity: each field tampered | Every field verified via canonical_statement | test_document_authenticity::test_each_field_tampered (8 fields) | PASS |
| 42 | Content authenticity: unknown/wrong key | Trust registry lookup; wrong key size | test_document_authenticity::test_unknown_and_wrong_key | PASS |
| 43 | Content authenticity: bad signatures | Empty, wrong length, truncated, non-canonical | test_document_authenticity::test_bad_signatures | PASS |
| 44 | Content authenticity: bad fields | None, dict, extra field, path escape, Unicode, uppercase hex | test_document_authenticity::test_bad_fields | PASS |
| 45 | Content authenticity: noncanonical encoding | parse_statement checks raw == canonical; rejects whitespace/duplicate keys | test_document_authenticity::test_canonical_and_duplicate_json | PASS |
| 46 | Release mode unauthorized | ConfigError before any FS operation | test_v052 (deliver_pdf release raises) | PASS |
| 47 | Draft mode works independently | Draft copies to Drafts folder; not affected by release gate | test_v052 (deliver_pdf draft succeeds) | PASS |
| 48 | Empty/oversized approval fields | Non-empty check; max 256 chars; IDENT regex | test_release_security_adversarial::test_invalid_payloads_rejected (empty owner_id, 257-char policy_version, wrong type) | PASS |
| 49 | Deterministic canonical serialization | Key order independence | test_release_security::test_deterministic (reversed items) | PASS |
| 50 | Cryptography library unavailable | Fail-closed: ImportError → ApprovalError | test_release_security::test_reject_invalid_signature_or_missing_dependency | PASS |

---

## Gap Closure Status

### Closed Gaps (Regression tests added — commit dbc77b9, 390/390 pass)

| Gap | Risk Level | Description | Test Reference | Result |
|-----|-----------|-------------|----------------|--------|
| Concurrent request test (S12) | Low | Two simultaneous release attempts on the same approval ID | test_release_phase6_gaps::ConcurrentRaceTests::test_exactly_one_concurrent_reservation_succeeds — 2 threads on threading.Barrier(2), exactly one O_EXCL winner (.used file written), exactly one ReplayError("already reserved") loser | CLOSED — PASS |
| Permission denied test (S16 EACCES) | Low | EACCES from os.open on a read-only private directory | test_release_phase6_gaps::PermissionDeniedTests::test_eacces_from_os_open_raises_replay_error — real syscall: chmod(0o500) passes st_mode & 0o077 privacy pre-check but denies os.open(O_CREAT), ReplayError("cannot reserve approval"), no .used file created | CLOSED — PASS |
| Permission denied test (S16 EPERM) | Low | EPERM from os.open (errno=1, distinct from EACCES errno=13) | test_release_phase6_gaps::PermissionDeniedTests::test_eperm_from_os_open_raises_replay_error — mocked via patch("engine.release.replay.os.open", side_effect=PermissionError(1, ...)), ReplayError("cannot reserve approval"), no .used file created | CLOSED — PASS |
| Key rotation sequence test | Low | Old key revoked + new key active in the same two-key registry | test_release_phase6_gaps::KeyRotationTests::test_revoked_old_key_rejected, ::test_active_new_key_accepted, ::test_rotation_old_fails_new_succeeds — registry {owner-1: {revoked}, owner-2: {active}}, old → ApprovalError("key not trusted or revoked"), new → accepted, old != new | CLOSED — PASS |

### Open Gaps (Owner-decision-gated — deferred by design, NOT vulnerabilities)

| Gap | Risk Level | Description | Status |
|-----|-----------|-------------|--------|
| Timestamp/expiry field | N/A | Not in schema; requires contract amendment | OPEN — owner-decision-gated, UNIMPLEMENTED by design |
| Clock skew policy | N/A | No timestamp field; requires owner decision | OPEN — owner-decision-gated, UNIMPLEMENTED by design |
| Pipeline→CLI connection | N/A | Not connected to CLI delivery path; requires activation gate | OPEN — owner-decision-gated, release is hard-disabled (ConfigError) |

---

## Activation Decision

**Release mode status:** DISABLED (ConfigError in deliver_pdf)  
**Pipeline status:** Implemented but NOT connected to CLI  
**Owner decisions required for activation:**
1. Approve this assurance matrix
2. Approve the release-authorization contract (docs/security/release-authorization-contract-v1.0.txt)
3. Approve connecting the pipeline to the CLI delivery path
4. Approve removing the ConfigError guard in deliver_pdf

**Without all four, release remains disabled. No test passage authorizes release.**

### Current owner policy (November 2026)

| Decision | Status |
|----------|--------|
| Repository visibility | PRIVATE (GitHub) — no public repository publication authorized |
| Development status | DEVELOPMENT ONLY — no production deployment |
| Release/delivery activation | HARD-DISABLED (ConfigError guard in deliver_pdf NOT removed) |
| Pipeline→CLI connection | NOT connected (activation decision 3 NOT approved) |
| ConfigError guard removal | NOT approved (activation decision 4 NOT approved) |
| Activation decisions 1–4 | NONE approved |
| Phase 7 | NOT authorized |

Repository visibility (GitHub PRIVATE) is distinct from PDF delivery/release mode. A private repository does not authorize release activation; release remains hard-disabled regardless of repository visibility.
