"""Owner-gated release pipeline primitive. Not connected to the public delivery CLI."""
from __future__ import annotations
from collections.abc import Mapping
from pathlib import Path
from engine.release.authorization import authorize_release
from engine.release.replay import reserve_approval
from engine.release.audit_ledger import record_release_event
from engine.release.atomic_delivery import place_verified_snapshot, AtomicPlacementUncertain

class ReleasePipelineError(RuntimeError):
    pass

def execute_authorized_release(*, payload: dict, signature_b64: str,
    registry: Mapping, expected: Mapping, replay_state_dir: Path,
    audit_dir: Path, snapshot: Path, destination: Path) -> Path:
    """Consume approval before placement; preserve replay and audit evidence on failure.

    Caller must independently verify immutable snapshot and expected context,
    and protect every ancestor of state/audit/output directories.
    """
    approval_id = authorize_release(payload, signature_b64, registry, expected)
    digest = expected["artifact_sha256"]
    # Refuse any filesystem mutation before authorization succeeds.
    reserve_approval(replay_state_dir, approval_id)
    try:
        record_release_event(audit_dir, approval_id, digest, "reserved")
    except BaseException as exc:
        # Approval remains consumed. Never place without durable reservation audit.
        raise ReleasePipelineError("reservation audit failed; approval consumed") from exc
    try:
        result = place_verified_snapshot(snapshot, destination, digest)
    except AtomicPlacementUncertain as exc:
        try:
            record_release_event(audit_dir, approval_id, digest, "uncertain")
        except BaseException:
            raise ReleasePipelineError("placement uncertain and uncertainty audit unavailable; manual reconciliation required") from exc
        raise ReleasePipelineError("placement uncertain; manual reconciliation required") from exc
    except BaseException as exc:
        try:
            record_release_event(audit_dir, approval_id, digest, "failed")
        except BaseException:
            raise ReleasePipelineError("placement failed and failure audit unavailable; manual reconciliation required") from exc
        raise ReleasePipelineError("placement failed; approval consumed") from exc
    try:
        record_release_event(audit_dir, approval_id, digest, "delivered")
    except BaseException as exc:
        # Destination may exist. Best-effort separate durable uncertainty marker;
        # never retry placement or claim successful delivery.
        try:
            record_release_event(audit_dir, approval_id, digest, "uncertain")
        except Exception:
            pass  # The original failure remains authoritative; manual review required.
        raise ReleasePipelineError("delivery status uncertain; manual reconciliation required") from exc
    return result
