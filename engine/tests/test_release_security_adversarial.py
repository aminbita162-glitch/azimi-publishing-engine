"""Adversarial contract checks for offline signature primitives; no release enabled."""
import base64
import copy
import unittest
from engine.release_security import ApprovalError, canonical_payload, verify_signature


def payload():
    return dict(schema="azimi.release-approval.v1", action="release",
                owner_id="owner", document_id="document", artifact_sha256="a" * 64,
                manifest_sha256="b" * 64, policy_version="v1", key_id="test-key",
                approval_id="approval-1", destination="local-release")


class AdversarialSignatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        cls.key = Ed25519PrivateKey.generate()
        cls.pub = cls.key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

    def signature(self, p):
        return base64.b64encode(self.key.sign(canonical_payload(p))).decode("ascii")

    def test_valid_signature(self):
        p = payload()
        verify_signature(p, self.signature(p), {"test-key": self.pub})

    def test_every_signed_field_tamper_rejected(self):
        original = payload()
        signature = self.signature(original)
        substitutions = {"owner_id": "other", "document_id": "other",
                         "artifact_sha256": "c" * 64, "manifest_sha256": "d" * 64,
                         "policy_version": "v2", "key_id": "other",
                         "approval_id": "approval-2", "destination": "other"}
        for field, value in substitutions.items():
            with self.subTest(field=field):
                changed = copy.deepcopy(original)
                changed[field] = value
                with self.assertRaises(ApprovalError):
                    verify_signature(changed, signature, {"test-key": self.pub})

    def test_malformed_signatures_rejected(self):
        p = payload()
        for signature in (None, "", "!!!", "====", base64.b64encode(b"x" * 63).decode(),
                          base64.b64encode(b"x" * 65).decode(), 17):
            with self.subTest(signature=str(signature)[:24]):
                with self.assertRaises(ApprovalError):
                    verify_signature(p, signature, {"test-key": self.pub})

    def test_invalid_registry_rejected(self):
        p = payload()
        sig = self.signature(p)
        for registry in (None, {}, {"test-key": "string"}, {"test-key": b"x" * 31}):
            with self.subTest(registry=str(registry)[:30]):
                with self.assertRaises(ApprovalError):
                    verify_signature(p, sig, registry)

    def test_invalid_payloads_rejected(self):
        p = payload()
        variants = [None, [], {}, {**p, "unexpected": "x"},
                    {k: v for k, v in p.items() if k != "owner_id"},
                    {**p, "document_id": "../escape"},
                    {**p, "artifact_sha256": "A" * 64},
                    {**p, "owner_id": ""}, {**p, "key_id": 42},
                    {**p, "policy_version": "x" * 257}]
        for bad in variants:
            with self.subTest(case=str(bad)[:60]):
                with self.assertRaises(ApprovalError):
                    canonical_payload(bad)


if __name__ == "__main__":
    unittest.main()
