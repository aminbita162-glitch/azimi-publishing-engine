"""P0 regression checks for public tools imports and fail-closed delivery."""
import tempfile
import unittest
from pathlib import Path

from engine import tools
from engine import tools_core
from engine.errors import EngineError


class ToolsImportContractTests(unittest.TestCase):
    def test_public_exports_are_original_implementations(self):
        for name in ('deliver_pdf', 'validate_ticket', 'verify_agents',
                     'describe_fonts', 'render_previews', 'scaffold_document',
                     'parse_ticket'):
            self.assertIs(getattr(tools, name), getattr(tools_core, name))
        self.assertEqual(tools.APPROVAL_FILE, tools_core.APPROVAL_FILE)
        self.assertEqual(tools.TICKET_FIELDS, tools_core.TICKET_FIELDS)

    def test_public_all_exports(self):
        expected = {'APPROVAL_FILE', 'TICKET_FIELDS', 'parse_ticket',
                    'validate_ticket', 'deliver_pdf', 'describe_fonts',
                    'render_previews', 'scaffold_document', 'verify_agents'}
        self.assertEqual(set(tools.__all__), expected)
        self.assertTrue(all(hasattr(tools, name) for name in expected))
        namespace = {}
        exec('from engine.tools import *', namespace)
        self.assertEqual({name for name in namespace if not name.startswith('_')}, expected)

    def test_delivery_invalid_mode_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(EngineError):
                tools.deliver_pdf(Path(temp), 'missing', 'invalid')

    def test_missing_document_does_not_return_success(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(EngineError):
                tools.deliver_pdf(Path(temp), 'missing', 'release')


if __name__ == '__main__':
    unittest.main()
