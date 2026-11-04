"""Adversarial regression tests for isolated content-authenticity primitives."""
import base64
import json
import unittest

from engine.document_authenticity import (
    AuthenticityError, DOMAIN, canonical_statement, parse_statement,
    statement_digest, verify_content_statement,
)

class DocumentAuthenticityTests(unittest.TestCase):
    def setUp(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization
        self.private = Ed25519PrivateKey.generate()  # ephemeral test-only key
        self.public = self.private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.data = dict(schema="azimi.content-authenticity.v1", issuer_id="issuer1",
                         document_id="doc1", edition_id="v1", issuance_id="issue1",
                         key_id="key1", content_sha256="a" * 64, policy_version="p1")
        self.signature = base64.b64encode(self.private.sign(canonical_statement(self.data))).decode()

    def test_valid_and_digest(self):
        self.assertEqual(verify_content_statement(self.data, self.signature, {"key1": self.public}), "VALID_CONTENT")
        self.assertEqual(len(statement_digest(self.data)), 64)

    def test_each_field_tampered(self):
        for field in self.data:
            with self.subTest(field=field):
                altered = dict(self.data)
                altered[field] = "b" * 64 if field == "content_sha256" else ("p2" if field == "policy_version" else "changed")
                with self.assertRaises(AuthenticityError):
                    verify_content_statement(altered, self.signature, {"key1": self.public})

    def test_unknown_and_wrong_key(self):
        for keys in ({}, {"key1": b"x" * 32}, {"key1": b"x"}):
            with self.assertRaises(AuthenticityError):
                verify_content_statement(self.data, self.signature, keys)

    def test_bad_signatures(self):
        for signature in ("", "!" * 88, base64.b64encode(b"x" * 64).decode(), self.signature[:-2]):
            with self.assertRaises(AuthenticityError):
                verify_content_statement(self.data, signature, {"key1": self.public})

    def test_bad_fields(self):
        for value in (None, {}, {**self.data, "extra": "x"}, {**self.data, "content_sha256": "A" * 64},
                      {**self.data, "issuer_id": "../bad"}, {**self.data, "document_id": "é"}):
            with self.assertRaises(AuthenticityError):
                canonical_statement(value)

    def test_canonical_and_duplicate_json(self):
        raw = canonical_statement(self.data)[len(DOMAIN):]
        self.assertEqual(parse_statement(raw), self.data)
        for bad in (b'{"a":1,"a":2}', b'{"x":', b'[]', b'\xff', b' ' + raw, raw + b' ',
                    json.dumps(self.data).encode(), b'x' * 2049):
            with self.assertRaises(AuthenticityError):
                parse_statement(bad)

    def test_domain_separation(self):
        self.assertTrue(canonical_statement(self.data).startswith(DOMAIN))
        self.assertNotIn(b"RELEASE-APPROVAL", DOMAIN)

if __name__ == "__main__":
    unittest.main()
