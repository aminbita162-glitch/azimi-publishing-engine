"""Tests for Phase C6: SBOM, locked hashes, supply-chain enforcement, renderer flag."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from engine.build.builder import _generate_sbom, _verify_locks, build_document
from engine.errors import ConfigError, ContentError
from engine.tests.support import REAL_ROOT, TempProject, CONTENT

import io
from pypdf import PdfReader

# --------------------------------------------------------------------------- #
# C6.1 — SBOM (CycloneDX JSON)
# --------------------------------------------------------------------------- #


def _copy_locks(root: Path) -> None:
    """Copy requirements.lock and fonts.lock from the real project to *root*."""
    shutil.copy(REAL_ROOT / "requirements.lock", root / "requirements.lock")
    shutil.copy(REAL_ROOT / "fonts.lock", root / "fonts.lock")


class SbomTests(unittest.TestCase):
    def test_sbom_generated_when_lock_exists(self):
        """A build with requirements.lock produces a CycloneDX SBOM file."""
        with TempProject() as root:
            _copy_locks(root)
            result = build_document(root, "courses/doc")
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertIn("sbom", manifest)
            self.assertTrue(manifest["sbom"]["present"])
            sbom_name = manifest["sbom"]["file"]
            sbom_path = result.pdf_path.parent / sbom_name
            self.assertTrue(sbom_path.is_file(), f"SBOM file {sbom_path} should exist")

    def test_sbom_cyclonedx_format(self):
        """The SBOM is valid CycloneDX JSON with bomFormat and components."""
        with TempProject() as root:
            _copy_locks(root)
            result = build_document(root, "courses/doc")
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            sbom_name = manifest["sbom"]["file"]
            sbom_path = result.pdf_path.parent / sbom_name
            sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
            self.assertEqual(sbom["bomFormat"], "CycloneDX")
            self.assertIn("specVersion", sbom)
            self.assertIn("components", sbom)
            self.assertIsInstance(sbom["components"], list)
            self.assertGreater(len(sbom["components"]), 0)

    def test_sbom_contains_package_hashes(self):
        """The SBOM includes SHA-256 hashes for Python packages."""
        with TempProject() as root:
            _copy_locks(root)
            result = build_document(root, "courses/doc")
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            sbom_name = manifest["sbom"]["file"]
            sbom_path = result.pdf_path.parent / sbom_name
            sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
            library_components = [c for c in sbom["components"] if c["type"] == "library"]
            self.assertGreater(len(library_components), 0)
            for comp in library_components:
                self.assertIn("hashes", comp)
                hash_entry = comp["hashes"][0]
                self.assertEqual(hash_entry["alg"], "SHA-256")
                self.assertEqual(len(hash_entry["content"]), 64)
                self.assertIn("name", comp)
                self.assertIn("version", comp)

    def test_sbom_contains_font_hashes(self):
        """The SBOM includes SHA-256 hashes for bundled fonts."""
        with TempProject() as root:
            _copy_locks(root)
            result = build_document(root, "courses/doc")
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            sbom_name = manifest["sbom"]["file"]
            sbom_path = result.pdf_path.parent / sbom_name
            sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
            font_components = [c for c in sbom["components"] if c["type"] == "file"]
            self.assertGreater(len(font_components), 0)
            for comp in font_components:
                self.assertIn("hashes", comp)
                self.assertEqual(comp["hashes"][0]["alg"], "SHA-256")
                self.assertTrue(comp["name"].endswith(".ttf"))

    def test_sbom_hash_in_manifest(self):
        """The manifest records the SBOM file's SHA-256 hash."""
        with TempProject() as root:
            _copy_locks(root)
            result = build_document(root, "courses/doc")
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            sbom_name = manifest["sbom"]["file"]
            sbom_path = result.pdf_path.parent / sbom_name
            import hashlib
            expected_hash = hashlib.sha256(sbom_path.read_bytes()).hexdigest()
            self.assertEqual(manifest["sbom"]["sha256"], expected_hash)

    def test_sbom_omitted_without_lock(self):
        """Without requirements.lock, the SBOM is omitted with an explicit note."""
        with TempProject() as root:
            result = build_document(root, "courses/doc")
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertIn("sbom", manifest)
            self.assertFalse(manifest["sbom"]["present"])
            self.assertIn("note", manifest["sbom"])
            # No .sbom.json file in the build folder
            sbom_files = list(result.pdf_path.parent.glob("*.sbom.json"))
            self.assertEqual(len(sbom_files), 0)


# --------------------------------------------------------------------------- #
# C6.2 — Locked hashes
# --------------------------------------------------------------------------- #


class LockVerificationTests(unittest.TestCase):
    def test_lock_passes_when_hashes_match(self):
        """Lock verification passes when requirements.lock and fonts.lock match."""
        with TempProject() as root:
            _copy_locks(root)
            lock_data = _verify_locks(root)
            self.assertIsNotNone(lock_data)
            assert lock_data is not None  # type narrowing
            self.assertIn("packages", lock_data)
            self.assertIn("fonts", lock_data)
            self.assertGreater(len(lock_data["packages"]), 0)

    def test_no_lock_returns_none(self):
        """Without requirements.lock, _verify_locks returns None."""
        with TempProject() as root:
            lock_data = _verify_locks(root)
            self.assertIsNone(lock_data)

    def test_requirements_lock_hash_mismatch_fails(self):
        """A wrong hash in requirements.lock causes ConfigError."""
        with TempProject() as root:
            _copy_locks(root)
            # Corrupt the first package hash
            lines = (root / "requirements.lock").read_text().splitlines()
            for i, line in enumerate(lines):
                if line.strip() and not line.startswith("#"):
                    parts = line.split()
                    lines[i] = f"{parts[0]} sha256={'0' * 64}"
                    break
            (root / "requirements.lock").write_text("\n".join(lines), encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "lock verification failed"):
                build_document(root, "courses/doc")

    def test_fonts_lock_hash_mismatch_fails(self):
        """A wrong hash in fonts.lock causes ConfigError."""
        with TempProject() as root:
            _copy_locks(root)
            # Corrupt the first font hash
            lines = (root / "fonts.lock").read_text().splitlines()
            for i, line in enumerate(lines):
                if line.strip() and not line.startswith("#"):
                    parts = line.split(maxsplit=1)
                    lines[i] = f"{'0' * 64}  {parts[1]}"
                    break
            (root / "fonts.lock").write_text("\n".join(lines), encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "lock verification failed"):
                build_document(root, "courses/doc")

    def test_missing_locked_font_fails(self):
        """A fonts.lock entry for a non-existent font file causes ConfigError."""
        with TempProject() as root:
            _copy_locks(root)
            # Add a non-existent font entry
            content = (root / "fonts.lock").read_text()
            content += "\n" + "a" * 64 + "  NonExistent.ttf\n"
            (root / "fonts.lock").write_text(content, encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "lock verification failed"):
                build_document(root, "courses/doc")

    def test_build_succeeds_with_correct_locks(self):
        """A full build with correct lock files produces a valid PDF and SBOM."""
        with TempProject() as root:
            _copy_locks(root)
            result = build_document(root, "courses/doc")
            self.assertEqual(result.audit.passed, True)
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertTrue(manifest["sbom"]["present"])


# --------------------------------------------------------------------------- #
# C6.3 — Supply-chain enforcement (no network during build)
# --------------------------------------------------------------------------- #


class SupplyChainTests(unittest.TestCase):
    def test_network_call_in_test_block_is_blocked(self):
        """A ```test block that attempts a network call fails because network is blocked."""
        content = CONTENT + "\n\n~~~test\nimport socket\nsocket.create_connection(('example.com', 80))\n~~~\n"
        with TempProject(content=content) as root:
            with self.assertRaisesRegex(ContentError, "exited with code"):
                build_document(root, "courses/doc")

    def test_socket_in_test_block_is_blocked(self):
        """A ```test block that creates a raw socket fails because network is blocked."""
        content = CONTENT + "\n\n~~~test\nimport socket\ns = socket.socket()\ns.connect(('example.com', 80))\n~~~\n"
        with TempProject(content=content) as root:
            with self.assertRaisesRegex(ContentError, "exited with code"):
                build_document(root, "courses/doc")

    def test_non_network_test_block_still_passes(self):
        """A ```test block without network access still passes with the preamble."""
        content = CONTENT + "\n\n~~~test\nassert 1 + 1 == 2\nprint('ok')\n~~~\n"
        with TempProject(content=content) as root:
            result = build_document(root, "courses/doc")
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertIn("test_blocks", manifest)
            self.assertTrue(any(t["exit_code"] == 0 for t in manifest["test_blocks"]))

    def test_build_makes_no_network_calls(self):
        """The build process itself does not import or use urllib or requests."""
        # This is a static check: the build module does not import any network module.
        from engine.build import builder
        import inspect
        source = inspect.getsource(builder)
        self.assertNotIn("import urllib", source)
        self.assertNotIn("import requests", source)
        self.assertNotIn("import http", source)


# --------------------------------------------------------------------------- #
# C6.4 — Optional PyMuPDF alternative (--renderer flag)
# --------------------------------------------------------------------------- #


class RendererTests(unittest.TestCase):
    def test_default_renderer_builds(self):
        """The default renderer (reportlab) builds successfully with zero change."""
        with TempProject() as root:
            result = build_document(root, "courses/doc", renderer="reportlab")
            self.assertTrue(result.pdf_path.is_file())
            self.assertEqual(result.audit.passed, True)

    def test_pymupdf_without_install_fails(self):
        """Selecting pymupdf without the package installed fails with a clear message."""
        with TempProject() as root:
            with self.assertRaisesRegex(ConfigError, "pymupdf"):
                build_document(root, "courses/doc", renderer="pymupdf")

    def test_pymupdf_error_mentions_manual_install(self):
        """The pymupdf error message says to install it manually, never automatically."""
        with TempProject() as root:
            with self.assertRaisesRegex(ConfigError, "manually"):
                build_document(root, "courses/doc", renderer="pymupdf")

    def test_unknown_renderer_fails(self):
        """An unknown renderer name is rejected with a clear error."""
        with TempProject() as root:
            with self.assertRaisesRegex(ConfigError, "unknown renderer"):
                build_document(root, "courses/doc", renderer="weasyprint")

    def test_default_path_identical_sha(self):
        """Building with renderer='reportlab' produces the same SHA as the default path."""
        with TempProject() as root:
            result_default = build_document(root, "courses/doc")
            result_explicit = build_document(root, "courses/doc", renderer="reportlab")
            self.assertEqual(result_default.sha256, result_explicit.sha256)

    def test_cli_renderer_flag(self):
        """The CLI build command accepts --renderer reportlab and exits 0."""
        import contextlib
        from engine.cli import main

        with TempProject() as root:
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = main(["build", str(root / "courses" / "doc"), "--renderer", "reportlab"], root=root)
            self.assertEqual(code, 0, err.getvalue())
            self.assertIn("SHA-256", out.getvalue())

    def test_cli_pymupdf_without_install_exit_two(self):
        """The CLI build command with --renderer pymupdf exits 2 when pymupdf is missing."""
        import contextlib
        from engine.cli import main

        with TempProject() as root:
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = main(["build", str(root / "courses" / "doc"), "--renderer", "pymupdf"], root=root)
            self.assertEqual(code, 2)
            self.assertIn("pymupdf", err.getvalue())


if __name__ == "__main__":
    unittest.main()
