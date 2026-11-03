"""Offline Ed25519 approval primitives. Not connected to release delivery."""
from __future__ import annotations

import base64
import binascii
import json
import re
from collections.abc import Mapping

DOMAIN = b"AZIMI-PUBLISHING-ENGINE/RELEASE-APPROVAL/V1\x00"
FIELDS = frozenset({
    "schema", "action", "owner_id", "document_id", "artifact_sha256",
    "manifest_sha256", "policy_version", "key_id", "approval_id", "destination",
})
HEX = re.compile(r"[0-9a-f]{64}\Z")
IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}\Z")


class ApprovalError(ValueError):
    """Approval rejected or verification unavailable."""


def canonical_payload(payload: dict) -> bytes:
    if not isinstance(payload, dict) or set(payload) != FIELDS:
        raise ApprovalError("invalid approval field set")
    for key, value in payload.items():
        if not isinstance(value, str) or not value or len(value) > 256:
            raise ApprovalError("invalid approval field: " + key)
    if payload["schema"] != "azimi.release-approval.v1":
        raise ApprovalError("unsupported schema")
    if payload["action"] != "release":
        raise ApprovalError("unsupported action")
    for key in ("artifact_sha256", "manifest_sha256"):
        if HEX.fullmatch(payload[key]) is None:
            raise ApprovalError("invalid SHA-256: " + key)
    for key in FIELDS - {"schema", "action", "artifact_sha256", "manifest_sha256"}:
        if IDENT.fullmatch(payload[key]) is None:
            raise ApprovalError("invalid identifier: " + key)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")
    return DOMAIN + encoded


def verify_signature(payload: dict, signature_b64: str,
                     trusted_public_keys: Mapping[str, bytes]) -> None:
    """Fail-closed verification using caller-provided trusted public keys.

    Does NOT implement trust enrollment, revocation, replay, authorization,
    secure delivery, or persistent audit. Do not use as a release gate alone.
    """
    message = canonical_payload(payload)
    if not isinstance(signature_b64, str):
        raise ApprovalError("invalid signature encoding")
    if not isinstance(trusted_public_keys, Mapping):
        raise ApprovalError("invalid trust registry")
    public_key = trusted_public_keys.get(payload["key_id"])
    if not isinstance(public_key, bytes) or len(public_key) != 32:
        raise ApprovalError("unknown key or invalid public key")
    try:
        signature = base64.b64decode(signature_b64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ApprovalError("invalid base64 signature") from exc
    if len(signature) != 64:
        raise ApprovalError("invalid signature length")
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as exc:
        raise ApprovalError("cryptography unavailable; verification denied") from exc
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, message)
    except (InvalidSignature, ValueError, TypeError) as exc:
        raise ApprovalError("signature invalid") from exc
