import base64
import unittest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from engine.release.authorization import authorize_release
from engine.release_security import ApprovalError, canonical_payload

class ReleaseAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.private=Ed25519PrivateKey.generate()
        pub=self.private.public_key().public_bytes(encoding=serialization.Encoding.Raw,format=serialization.PublicFormat.Raw)
        self.registry={"owner-key": {"public_key": pub, "status": "active"}}
        self.payload={"schema":"azimi.release-approval.v1","action":"release","owner_id":"owner-1","document_id":"doc-1","artifact_sha256":"a"*64,"manifest_sha256":"b"*64,"policy_version":"v1","key_id":"owner-key","approval_id":"approval-1","destination":"release-folder"}
        self.expected={k:self.payload[k] for k in ("owner_id","document_id","artifact_sha256","manifest_sha256","policy_version","destination")}
    def sign(self, payload):
        return base64.b64encode(self.private.sign(canonical_payload(payload))).decode("ascii")
    def test_valid(self):
        self.assertEqual(authorize_release(self.payload,self.sign(self.payload),self.registry,self.expected),"approval-1")
    def test_every_binding_mismatch(self):
        signature=self.sign(self.payload)
        for field in self.expected:
            with self.subTest(field=field), self.assertRaises(ApprovalError):
                expected=dict(self.expected); expected[field]="different"
                authorize_release(self.payload,signature,self.registry,expected)
    def test_tampered_signature(self):
        signature=self.sign(self.payload)
        with self.assertRaises(ApprovalError):
            authorize_release({**self.payload,"approval_id":"altered"},signature,self.registry,self.expected)
    def test_revoked_key(self):
        registry={"owner-key":{"public_key":self.registry["owner-key"]["public_key"],"status":"revoked"}}
        with self.assertRaises(ApprovalError):
            authorize_release(self.payload,self.sign(self.payload),registry,self.expected)
    def test_missing_context(self):
        with self.assertRaises(ApprovalError):
            authorize_release(self.payload,self.sign(self.payload),self.registry,{})

if __name__ == "__main__":
    unittest.main()
