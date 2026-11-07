"""Negative verification contracts for tampered build manifests (Phase 2)."""
import json
import unittest
from copy import deepcopy

from engine.build.builder import build_document, verify_document
from engine.errors import ConfigError
from engine.tests.support import TempProject


class ManifestNegativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project = TempProject(); cls.project.init()
        cls.root = cls.project.enter()
        cls.result = build_document(cls.root, "courses/doc")
        cls.path = cls.result.manifest_path
        cls.original_bytes = cls.path.read_bytes()
        cls.original = json.loads(cls.original_bytes)

    @classmethod
    def tearDownClass(cls):
        cls.path.write_bytes(cls.original_bytes)
        cls.project.exit(None, None, None)

    def tearDown(self):
        self.path.write_bytes(self.original_bytes)

    def verify_rejects(self, mutated):
        self.path.write_text(json.dumps(mutated), encoding="utf-8")
        with self.assertRaises(ConfigError):
            verify_document(self.root, "courses/doc")

    def test_non_object_manifest(self):
        self.verify_rejects([])

    def test_missing_output(self):
        value = deepcopy(self.original)
        value.pop("output", None)
        self.verify_rejects(value)

    def test_invalid_pdf_digest(self):
        value = deepcopy(self.original)
        value["output"]["sha256"] = "not-a-sha256"
        self.verify_rejects(value)

    def test_boolean_pdf_size(self):
        value = deepcopy(self.original)
        value["output"]["bytes"] = True
        self.verify_rejects(value)

    def test_missing_inputs(self):
        value = deepcopy(self.original)
        value["inputs"] = {}
        self.verify_rejects(value)

    def test_parent_directory_traversal(self):
        value = deepcopy(self.original)
        value["inputs"]["../outside.txt"] = "0" * 64
        self.verify_rejects(value)

    def test_absolute_input_path(self):
        value = deepcopy(self.original)
        value["inputs"]["/tmp/outside.txt"] = "0" * 64
        self.verify_rejects(value)

    def test_backslash_input_path(self):
        value = deepcopy(self.original)
        value["inputs"][r"..\outside.txt"] = "0" * 64
        self.verify_rejects(value)

    def test_wrong_brand_namespace(self):
        value = deepcopy(self.original)
        value["inputs"]["brand/other/forbidden.txt"] = "0" * 64
        self.verify_rejects(value)

    def test_missing_audit_exempt_pages(self):
        value = deepcopy(self.original)
        value["audit"].pop("exempt_pages", None)
        self.verify_rejects(value)

    def test_invalid_audit_inputs_type(self):
        value = deepcopy(self.original)
        value["audit_inputs"] = []
        self.verify_rejects(value)

    def test_malformed_json_fails_closed(self):
        self.path.write_text('{"output":', encoding="utf-8")
        with self.assertRaises((ConfigError, json.JSONDecodeError)):
            verify_document(self.root, "courses/doc")


if __name__ == "__main__":
    unittest.main()
