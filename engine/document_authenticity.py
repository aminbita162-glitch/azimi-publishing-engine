"""Offline, domain-separated document-content authenticity verification.

This module does not authorize release, prove exact PDF bytes, or check online revocation.
A QR payload is untrusted input; verification requires an independently enrolled key.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from collections.abc import Mapping

DOMAIN = b"AZIMI-PUBLISHING-ENGINE/CONTENT-AUTHENTICITY/V1\x00"
FIELDS = frozenset({"schema", "issuer_id", "document_id", "edition_id", "issuance_id", "key_id", "content_sha256", "policy_version"})
IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
HEX = re.compile(r"[0-9a-f]{64}\Z")
MAX_BYTES = 2048

class AuthenticityError(ValueError):
    """Malformed, unauthenticated, or unsupported content statement."""

def canonical_statement(statement: dict) -> bytes:
    if not isinstance(statement, dict) or set(statement) != FIELDS:
        raise AuthenticityError("invalid field set")
    for key, value in statement.items():
        if not isinstance(value, str) or not value or len(value) > 128 or not value.isascii():
            raise AuthenticityError("invalid field: " + key)
    if statement["schema"] != "azimi.content-authenticity.v1":
        raise AuthenticityError("unsupported schema")
    if HEX.fullmatch(statement["content_sha256"]) is None:
        raise AuthenticityError("invalid content hash")
    for key in FIELDS - {"schema", "content_sha256"}:
        if IDENT.fullmatch(statement[key]) is None:
            raise AuthenticityError("invalid identifier: " + key)
    encoded = json.dumps(statement, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
    if len(encoded) > MAX_BYTES:
        raise AuthenticityError("oversized statement")
    return DOMAIN + encoded

def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AuthenticityError("duplicate JSON key")
        result[key] = value
    return result

def parse_statement(raw: bytes) -> dict:
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES or not raw:
        raise AuthenticityError("invalid statement size")
    try:
        statement = json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=_no_duplicate_keys)
        canonical = canonical_statement(statement)
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise AuthenticityError("malformed statement") from exc
    if canonical[len(DOMAIN):] != raw:
        raise AuthenticityError("noncanonical encoding")
    return statement

def verify_content_statement(statement: dict, signature_b64: str, trusted_public_keys: Mapping[str, bytes]) -> str:
    """Return VALID_CONTENT only after signature verification; never VALID_FILE.

    Trust enrollment, key revocation and exact-file receipts are separate gates.
    """
    message = canonical_statement(statement)
    if not isinstance(trusted_public_keys, Mapping):
        raise AuthenticityError("invalid trust registry")
    key = trusted_public_keys.get(statement["key_id"])
    if not isinstance(key, bytes) or len(key) != 32:
        raise AuthenticityError("untrusted key")
    if not isinstance(signature_b64, str) or len(signature_b64) != 88:
        raise AuthenticityError("invalid signature encoding")
    try:
        signature = base64.b64decode(signature_b64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise AuthenticityError("invalid signature encoding") from exc
    if len(signature) != 64 or base64.b64encode(signature).decode("ascii") != signature_b64:
        raise AuthenticityError("noncanonical signature")
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as exc:
        raise AuthenticityError("cryptography unavailable") from exc
    try:
        Ed25519PublicKey.from_public_bytes(key).verify(signature, message)
    except (InvalidSignature, ValueError, TypeError) as exc:
        raise AuthenticityError("invalid signature") from exc
    return "VALID_CONTENT"

def statement_digest(statement: dict) -> str:
    return hashlib.sha256(canonical_statement(statement)).hexdigest()
