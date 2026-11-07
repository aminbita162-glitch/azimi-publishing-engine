"""Strict, fail-closed public-key trust registry primitives.

No key enrollment, key generation, signing, or release authorization is performed.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

from engine.release_security import ApprovalError

_KEY_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


def active_public_key(registry: Mapping, key_id: str) -> bytes:
    """Resolve an explicitly active Ed25519 key, rejecting malformed registries."""
    if not isinstance(registry, Mapping) or not isinstance(key_id, str):
        raise ApprovalError("invalid trust registry")
    if _KEY_ID.fullmatch(key_id) is None:
        raise ApprovalError("invalid key identifier")
    if len(registry) > 256:
        raise ApprovalError("trust registry too large")
    for identifier, record in registry.items():
        if not isinstance(identifier, str) or _KEY_ID.fullmatch(identifier) is None:
            raise ApprovalError("invalid registry identifier")
        if not isinstance(record, Mapping) or set(record) != {"public_key", "status"}:
            raise ApprovalError("invalid trust record")
        if type(record["public_key"]) is not bytes or len(record["public_key"]) != 32:
            raise ApprovalError("invalid public key")
        if record["status"] not in ("active", "revoked"):
            raise ApprovalError("invalid key status")
    record = registry.get(key_id)
    if record is None or record["status"] != "active":
        raise ApprovalError("key not trusted or revoked")
    return record["public_key"]
