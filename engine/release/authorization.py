"""Verify signed owner approval and exact release context; no delivery side effects."""
from __future__ import annotations
import hmac
from collections.abc import Mapping
from engine.release.trust import active_public_key
from engine.release_security import ApprovalError, verify_signature

_REQUIRED = frozenset({"owner_id", "document_id", "artifact_sha256", "manifest_sha256", "policy_version", "destination"})

def authorize_release(payload: dict, signature_b64: str, registry: Mapping, expected: Mapping) -> str:
    """Fail closed on any mismatched binding; return approval ID only after signature check.

    Does not reserve replay state or authorize actual delivery. A caller must
    enforce immutable snapshot, durable replay, atomic placement and audit.
    """
    if not isinstance(payload, dict) or not isinstance(expected, Mapping) or set(expected) != _REQUIRED:
        raise ApprovalError("invalid authorization context")
    for field in _REQUIRED:
        actual, wanted = payload.get(field), expected[field]
        if not isinstance(actual, str) or not isinstance(wanted, str):
            raise ApprovalError("invalid binding: " + field)
        if not hmac.compare_digest(actual, wanted):
            raise ApprovalError("release binding mismatch: " + field)
    public_key = active_public_key(registry, payload.get("key_id"))
    verify_signature(payload, signature_b64, {payload["key_id"]: public_key})
    return payload["approval_id"]
