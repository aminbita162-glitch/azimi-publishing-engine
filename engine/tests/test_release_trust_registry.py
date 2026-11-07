import unittest
from engine.release.trust import active_public_key
from engine.release_security import ApprovalError

class TrustRegistryTests(unittest.TestCase):
    def setUp(self):
        self.key = b"k" * 32
        self.registry = {"owner-1": {"public_key": self.key, "status": "active"}}

    def test_active_key(self):
        self.assertEqual(active_public_key(self.registry, "owner-1"), self.key)

    def test_unknown_or_revoked(self):
        for registry, identifier in ((self.registry, "missing"), ({"owner-1": {"public_key": self.key, "status": "revoked"}}, "owner-1")):
            with self.subTest(identifier=identifier, registry=registry), self.assertRaises(ApprovalError):
                active_public_key(registry, identifier)

    def test_malformed_registry(self):
        cases = [None, [], {"owner-1": {"public_key": b"x", "status": "active"}}, {"owner-1": {"public_key": self.key, "status": "pending"}}, {"owner-1": {"public_key": self.key, "status": "active", "extra": 1}}, {"bad id": {"public_key": self.key, "status": "active"}}]
        for registry in cases:
            with self.subTest(registry=registry), self.assertRaises(ApprovalError):
                active_public_key(registry, "owner-1")

    def test_invalid_key_id(self):
        for identifier in ("", "../secret", "a b", None):
            with self.subTest(identifier=identifier), self.assertRaises(ApprovalError):
                active_public_key(self.registry, identifier)

if __name__ == "__main__":
    unittest.main()
