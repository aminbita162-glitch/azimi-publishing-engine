"""Isolated contract tests; only ephemeral in-memory TEST keys."""
import base64
import unittest
from engine.release_security import ApprovalError, canonical_payload, verify_signature


def example():
    return {
        "schema": "azimi.release-approval.v1", "action": "release",
        "owner_id": "amin-azimi", "document_id": "fixture",
        "artifact_sha256": "a" * 64, "manifest_sha256": "b" * 64,
        "policy_version": "v1", "key_id": "test-key",
        "approval_id": "test-1", "destination": "local-release",
    }


class ReleaseSecurityTests(unittest.TestCase):
    def test_deterministic(self):
        p = example()
        self.assertEqual(canonical_payload(p),
                         canonical_payload(dict(reversed(list(p.items())))))

    def test_domain_separation(self):
        self.assertTrue(canonical_payload(example()).startswith(
            b"AZIMI-PUBLISHING-ENGINE/RELEASE-APPROVAL/V1\x00"))

    def test_reject_unknown_field(self):
        p = example()
        p["extra"] = "x"
        with self.assertRaises(ApprovalError):
            canonical_payload(p)

    def test_reject_wrong_action(self):
        p = example()
        p["action"] = "draft"
        with self.assertRaises(ApprovalError):
            canonical_payload(p)

    def test_reject_bad_digest(self):
        p = example()
        p["artifact_sha256"] = "not-a-hash"
        with self.assertRaises(ApprovalError):
            canonical_payload(p)

    def test_reject_unknown_key(self):
        with self.assertRaises(ApprovalError):
            verify_signature(example(), base64.b64encode(b"x"*64).decode(), {})

    def test_reject_invalid_signature_or_missing_dependency(self):
        with self.assertRaises(ApprovalError):
            verify_signature(example(), base64.b64encode(b"x"*64).decode(),
                             {"test-key": b"y"*32})

    def test_positive_and_tamper_when_crypto_available(self):
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        except ImportError:
            self.skipTest("cryptography not installed; real signature test pending")
        key = Ed25519PrivateKey.generate()  # temporary test key, never persisted
        pub = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        p = example()
        sig = base64.b64encode(key.sign(canonical_payload(p))).decode()
        verify_signature(p, sig, {"test-key": pub})
        p["document_id"] = "tampered"
        with self.assertRaises(ApprovalError):
            verify_signature(p, sig, {"test-key": pub})


if __name__ == "__main__":
    unittest.main()
