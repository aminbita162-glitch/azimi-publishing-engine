"""Build orchestration: validate inputs, render the PDF and write evidence."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Union

import reportlab

from .. import __version__
from ..audit import AuditReport, audit_pdf
from ..brand import load_brand
from ..lint import Issue, block_texts, lint, load_forbidden_terms
from ..errors import ConfigError, ContentError, EngineError
from ..paths import resolve_inside
from ..render.document import render_document, validate_inline
from ..render.fonts import register_fonts
from ..schemas.meta import load_meta
from ..schemas.findings import load_findings_if_present
from .parser import Code, Diagram, Glossary, Heading, Image, References, Table, parse

MAX_CONTENT_BYTES = 2 * 1024 * 1024
BUILD_DIR = "build"
MANIFEST_SUFFIX = ".manifest.json"
TEST_TIMEOUT = 10
MAX_TEST_OUTPUT = 500
MAX_VH_BLOCKS = 30

# C6.3 — Network block preamble: monkey-patch socket in the test-block subprocess
# so any attempt to open a network connection raises OSError.  The build process
# itself never makes network calls; this enforces the same guarantee for
# ````test`` code blocks executed during the build.
_NETWORK_BLOCK_PREAMBLE = (
    "import socket as _sock\n"
    "def _blocked(*a, **k):\n"
    "    raise OSError('network access blocked: offline build')\n"
    "_sock.socket = _blocked\n"
    "_sock.create_connection = _blocked\n"
    "del _sock, _blocked\n"
)


@dataclass(frozen=True)
class BuildResult:
    """Paths and facts of a finished build."""

    pdf_path: Path
    manifest_path: Path
    sha256: str
    pages: int
    audit: AuditReport


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        os.replace(temp_name, path)
    except BaseException:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
        raise


def _environment() -> Dict[str, str]:
    """Versions that influence the bytes of a PDF; byte-equal output needs equal versions."""
    import PIL
    import pypdf
    import yaml

    return {
        "python": platform.python_version(),
        "system": platform.system(),
        "reportlab": reportlab.Version,
        "pillow": PIL.__version__,
        "pypdf": pypdf.__version__,
        "pyyaml": yaml.__version__,
    }


def _stats(blocks) -> Dict[str, int]:
    words = sum(len(text.split()) for b in blocks if not isinstance(b, Code) for text in block_texts(b))
    code_blocks = [b for b in blocks if isinstance(b, Code)]
    return {
        "words": words,
        "chapters": sum(1 for b in blocks if isinstance(b, Heading) and b.level == 1),
        "sections": sum(1 for b in blocks if isinstance(b, Heading) and b.level == 2),
        "diagrams": sum(1 for b in blocks if isinstance(b, Diagram)),
        "images": sum(1 for b in blocks if isinstance(b, Image)),
        "tables": sum(1 for b in blocks if isinstance(b, Table)),
        "code_blocks": len(code_blocks),
        "code_lines": sum(len(b.lines) for b in code_blocks),
    }


def _text_hash(pdf: bytes) -> str:
    """Hash of the extracted text, to compare documents built in different environments."""
    import io

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf))
    text = "\n".join(re.sub(r"\s+", " ", page.extract_text() or "").strip() for page in reader.pages)
    return sha256_bytes(text.encode("utf-8"))


def _execute_test_blocks(blocks: List) -> List[Dict]:
    """Execute Code blocks whose language is exactly 'test' in a restricted subprocess.

    Returns a list of result dicts with language, exit_code, stdout, stderr and line.
    Raises ContentError if any test block exits non-zero (the build fails).
    Never executes blocks of any other language.
    """
    results: List[Dict] = []
    for block in blocks:
        if not (isinstance(block, Code) and block.language == "test"):
            continue
        code = _NETWORK_BLOCK_PREAMBLE + "\n".join(block.lines)
        try:
            proc = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                timeout=TEST_TIMEOUT,
                env={"PATH": os.environ.get("PATH", "")},
            )
        except subprocess.TimeoutExpired:
            raise ContentError(
                f"test block at line {block.line} timed out after {TEST_TIMEOUT}s", block.line
            )
        output = (proc.stderr or proc.stdout or "").strip()
        result = {
            "language": "test",
            "line": block.line,
            "exit_code": proc.returncode,
            "stdout": (proc.stdout or "")[:MAX_TEST_OUTPUT],
            "stderr": (proc.stderr or "")[:MAX_TEST_OUTPUT],
        }
        results.append(result)
        if proc.returncode != 0:
            raise ContentError(
                f"test block at line {block.line} exited with code {proc.returncode}: {output}",
                block.line,
            )
    return results


def _load_version_history(folder: Path) -> Optional[tuple]:
    """Return (filename, blocks) if a version-history file exists in *folder*, else None."""
    for name in ("CHANGELOG.md", "version-history.md"):
        path = folder / name
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                raise ContentError(f"{name} is not valid UTF-8")
            blocks = parse(text)
            return name, blocks[:MAX_VH_BLOCKS]
    return None


# --------------------------------------------------------------------------- #
# C6.2 — Locked hashes: verify requirements.lock and fonts.lock before build
# --------------------------------------------------------------------------- #

def _sha256_path(path: Path) -> str:
    """SHA-256 of a file's bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_locks(root: Path) -> Optional[Dict]:
    """Verify requirements.lock and fonts.lock against installed packages and fonts.

    Returns a dict ``{"packages": [...], "fonts": {name: hash}}`` if
    requirements.lock exists, or ``None`` if it does not (existing documents
    without lock files still build).

    Raises ConfigError on any mismatch (version, hash, missing file).
    All verification is local; no network access is needed.
    """
    lock_path = root / "requirements.lock"
    if not lock_path.is_file():
        return None

    import importlib.metadata as ilm

    errors: List[str] = []
    packages: List[Dict] = []

    for line in lock_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 2 or "==" not in parts[0] or not parts[1].startswith("sha256="):
            errors.append(f"invalid lock line: {line}")
            continue
        name_version = parts[0]
        expected_hash = parts[1][len("sha256="):]
        name, _, version = name_version.partition("==")
        try:
            dist = ilm.distribution(name)
        except ilm.PackageNotFoundError:
            errors.append(f"locked package not installed: {name}")
            continue
        if dist.version != version:
            errors.append(
                f"version mismatch for {name}: locked {version}, installed {dist.version}"
            )
            continue
        metadata_path = Path(getattr(dist, "_path")) / "METADATA"
        if not metadata_path.is_file():
            errors.append(f"cannot find METADATA for {name}")
            continue
        actual_hash = _sha256_path(metadata_path)
        if actual_hash != expected_hash:
            errors.append(f"hash mismatch for {name}")
            continue
        packages.append({"name": name, "version": version, "sha256": actual_hash})

    font_hashes: Dict[str, str] = {}
    fonts_lock_path = root / "fonts.lock"
    if fonts_lock_path.is_file():
        fonts_dir = root / "design-system" / "fonts"
        for line in fonts_lock_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(maxsplit=1)
            if len(parts) != 2:
                errors.append(f"invalid fonts.lock line: {line}")
                continue
            expected, filename = parts
            font_path = fonts_dir / filename
            if not font_path.is_file():
                errors.append(f"locked font not found: {filename}")
                continue
            actual = _sha256_path(font_path)
            if actual != expected:
                errors.append(f"hash mismatch for font {filename}")
                continue
            font_hashes[filename] = actual

    if errors:
        raise ConfigError(f"lock verification failed: {'; '.join(errors)}")

    return {"packages": packages, "fonts": dict(sorted(font_hashes.items()))}


# --------------------------------------------------------------------------- #
# C6.1 — SBOM: CycloneDX JSON from lock data
# --------------------------------------------------------------------------- #

def _generate_sbom(lock_data: Optional[Dict], version: str) -> Optional[Dict]:
    """Generate a CycloneDX JSON SBOM from lock data.

    Returns ``None`` when ``lock_data`` is ``None`` (no requirements.lock —
    SBOM omitted with an explicit note in the manifest).
    """
    if lock_data is None:
        return None

    components: List[Dict] = []
    for pkg in lock_data["packages"]:
        components.append(
            {
                "type": "library",
                "name": pkg["name"],
                "version": pkg["version"],
                "purl": f"pkg:pypi/{pkg['name'].lower()}@{pkg['version']}",
                "hashes": [{"alg": "SHA-256", "content": pkg["sha256"]}],
            }
        )
    for fname, fhash in lock_data["fonts"].items():
        components.append(
            {
                "type": "file",
                "name": fname,
                "hashes": [{"alg": "SHA-256", "content": fhash}],
            }
        )

    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "tools": [{"name": "Azimi Publishing Engine", "version": version}],
        },
        "components": components,
    }


def build_document(
    project_root: Union[str, Path], document_dir: Union[str, Path], renderer: str = "reportlab"
) -> BuildResult:
    """Build the PDF for one document folder (relative to project_root)."""
    root = Path(project_root).resolve(strict=True)
    folder = resolve_inside(root, document_dir)
    if not folder.is_dir():
        raise ConfigError(f"document folder not found: {document_dir}")

    # C6.4 — Validate renderer choice (default reportlab; zero behavior change)
    if renderer not in ("reportlab", "pymupdf"):
        raise ConfigError(
            f"unknown renderer '{renderer}'; available: reportlab, pymupdf"
        )
    if renderer == "pymupdf":
        try:
            import pymupdf  # noqa: F401
        except ImportError:
            raise ConfigError(
                "renderer 'pymupdf' requires the pymupdf package; "
                "install it manually (pip install pymupdf); "
                "the engine never installs packages automatically"
            )

    # C6.2 — Verify locked hashes before any build (exit 2 on mismatch)
    lock_data = _verify_locks(root)

    meta = load_meta(resolve_inside(folder, "meta.yaml"))

    content_path = resolve_inside(folder, "content.md")
    if not content_path.is_file():
        raise ConfigError("content.md is missing")
    if content_path.stat().st_size > MAX_CONTENT_BYTES:
        raise ContentError("content.md is larger than 2 MB")
    try:
        content_text = content_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ContentError("content.md is not valid UTF-8") from exc
    blocks = parse(content_text)

    brand = load_brand(root / "brand", meta.brand)
    try:
        rights_blocks = parse(brand.rights_path.read_text(encoding="utf-8"))
        validate_inline(rights_blocks)
    except UnicodeDecodeError as exc:
        raise ContentError("rights.md is not valid UTF-8") from exc
    except ContentError as exc:
        raise ContentError(f"in rights.md of brand {brand.name}, {exc}") from exc
    if not any(isinstance(block, Heading) for block in rights_blocks):
        raise ContentError(f"rights.md of brand {brand.name} must start with a level 1 heading")

    problems = lint(blocks, load_forbidden_terms(brand.logo_path.parent), meta.profile)
    if problems:
        raise ContentError(f"lint found {len(problems)} problem(s): {problems[0].message}", problems[0].line)

    font_checksums = register_fonts(root / "design-system" / "fonts", meta.font)

    # C5.1 — Load findings registry if present
    findings = load_findings_if_present(folder)

    # C5.4 — Execute marked test code blocks
    test_results = _execute_test_blocks(blocks)

    # C5.5 — Load version history if present
    vh = _load_version_history(folder)
    vh_blocks = vh[1] if vh is not None else None
    vh_name = vh[0] if vh is not None else None

    result = render_document(blocks, meta, brand, folder, rights_blocks, vh_blocks)
    again = render_document(blocks, meta, brand, folder, rights_blocks, vh_blocks)
    if again.pdf != result.pdf:
        raise EngineError("the document is not reproducible: two builds of the same input differ")

    audit = audit_pdf(
        result.pdf, meta, result.exempt_pages, min_image_dpi=result.min_image_dpi, contrast=result.contrast
    )

    inputs: Dict[str, str] = {
        "content.md": sha256_file(content_path),
        "meta.yaml": sha256_file(folder / "meta.yaml"),
        f"brand/{brand.name}/brand.yaml": sha256_file(brand.logo_path.parent / "brand.yaml"),
        f"brand/{brand.name}/logo.png": sha256_file(brand.logo_path),
        f"brand/{brand.name}/rights.md": sha256_file(brand.rights_path),
    }
    forbidden_file = brand.logo_path.parent / "forbidden.txt"
    if forbidden_file.is_file():
        inputs[f"brand/{brand.name}/forbidden.txt"] = sha256_file(forbidden_file)
    for relative in sorted(set(result.images)):
        inputs[relative] = sha256_file(resolve_inside(folder, relative))
    if findings is not None:
        inputs["findings.yaml"] = sha256_file(folder / "findings.yaml")
    if vh_name is not None:
        inputs[vh_name] = sha256_file(folder / vh_name)

    output_dir = folder / BUILD_DIR
    file_name = f"{meta.output_name}_v{meta.version}.pdf"
    pdf_path = output_dir / file_name
    manifest_path = output_dir / (file_name + MANIFEST_SUFFIX)
    pdf_hash = sha256_bytes(result.pdf)

    manifest = {
        "document": {
            "title": meta.title,
            "version": meta.version,
            "date": meta.date,
            "language": meta.language,
            "brand": brand.name,
        },
        "engine": {
            "name": "Azimi Publishing Engine",
            "version": __version__,
            "reportlab": reportlab.Version,
            "python": platform.python_version(),
        },
        "environment": _environment(),
        "content_stats": _stats(blocks),
        "text_sha256": _text_hash(result.pdf),
        "fonts": font_checksums,
        "inputs": dict(sorted(inputs.items())),
        "output": {"file": file_name, "sha256": pdf_hash, "bytes": len(result.pdf), "pages": result.pages},
        "reproducible": True,
        "audit": audit.to_dict(),
        "audit_inputs": {
            "min_image_dpi": result.min_image_dpi,
            "contrast": [[name, ratio] for name, ratio in result.contrast],
        },
    }
    if findings is not None:
        manifest["findings"] = findings
    if test_results:
        manifest["test_blocks"] = test_results

    # C6.1 — Generate and write SBOM (CycloneDX JSON) to the build folder
    sbom = _generate_sbom(lock_data, __version__)
    if sbom is not None:
        sbom_name = file_name + ".sbom.json"
        sbom_path = output_dir / sbom_name
        sbom_bytes = (json.dumps(sbom, indent=2, sort_keys=True) + "\n").encode("utf-8")
        manifest["sbom"] = {
            "file": sbom_name,
            "sha256": sha256_bytes(sbom_bytes),
            "present": True,
        }
        _atomic_write(sbom_path, sbom_bytes)
    else:
        manifest["sbom"] = {
            "present": False,
            "note": "no requirements.lock found; SBOM omitted",
        }

    _atomic_write(pdf_path, result.pdf)
    _atomic_write(manifest_path, (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    return BuildResult(
        pdf_path=pdf_path, manifest_path=manifest_path, sha256=pdf_hash, pages=result.pages, audit=audit
    )


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    problems: tuple
    audit: AuditReport


def _load_inputs(project_root, document_dir):
    root = Path(project_root).resolve(strict=True)
    folder = resolve_inside(root, document_dir)
    if not folder.is_dir():
        raise ConfigError(f"document folder not found: {document_dir}")
    meta = load_meta(resolve_inside(folder, "meta.yaml"))
    return root, folder, meta


def check_document(project_root, document_dir):
    """Validate a document without writing anything. Returns (lint problems, page count)."""
    root, folder, meta = _load_inputs(project_root, document_dir)
    content_path = resolve_inside(folder, "content.md")
    if not content_path.is_file():
        raise ConfigError("content.md is missing")
    blocks = parse(content_path.read_text(encoding="utf-8"))
    brand = load_brand(root / "brand", meta.brand)
    problems = lint(blocks, load_forbidden_terms(brand.logo_path.parent), meta.profile)
    rights_blocks = parse(brand.rights_path.read_text(encoding="utf-8"))
    register_fonts(root / "design-system" / "fonts", meta.font)
    vh = _load_version_history(folder)
    vh_blocks = vh[1] if vh is not None else None
    pages = render_document(blocks, meta, brand, folder, rights_blocks, vh_blocks).pages
    return problems, pages


def verify_document(project_root, document_dir) -> VerifyResult:
    """Check a built PDF against its manifest: checksums of PDF and inputs, then the audit again."""
    root, folder, meta = _load_inputs(project_root, document_dir)
    file_name = f"{meta.output_name}_v{meta.version}.pdf"
    pdf_path = folder / BUILD_DIR / file_name
    manifest_path = folder / BUILD_DIR / (file_name + MANIFEST_SUFFIX)
    if not pdf_path.is_file() or not manifest_path.is_file():
        raise ConfigError("no built PDF with a manifest was found; build the document first")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ConfigError("invalid manifest structure")
    output = manifest.get("output")
    recorded_inputs = manifest.get("inputs")
    if not isinstance(output, dict) or not isinstance(recorded_inputs, dict):
        raise ConfigError("invalid manifest structure")
    import re
    digest_pattern = re.compile(r"[0-9a-f]{64}\Z")
    if (output.get("file") != file_name or
            not isinstance(output.get("sha256"), str) or
            not digest_pattern.fullmatch(output["sha256"]) or
            not isinstance(output.get("bytes"), int) or isinstance(output.get("bytes"), bool) or
            output["bytes"] < 0):
        raise ConfigError("invalid manifest output")
    if not recorded_inputs:
        raise ConfigError("manifest has no inputs")
    validated_inputs = []
    for relative, expected in recorded_inputs.items():
        if not isinstance(relative, str) or not isinstance(expected, str) or not digest_pattern.fullmatch(expected):
            raise ConfigError("invalid manifest input entry")
        from pathlib import PurePosixPath
        parts = PurePosixPath(relative).parts
        if (not parts or relative.startswith("/") or "\\" in relative or
                any(part in (".", "..", "") for part in relative.split("/"))):
            raise ConfigError("unsafe manifest input path")
        if parts[0] == "brand":
            if len(parts) < 3 or parts[1] != meta.brand:
                raise ConfigError("unsafe manifest brand path")
            base = root
        else:
            base = folder
        try:
            target = resolve_inside(base, relative)
        except (ValueError, OSError) as exc:
            raise ConfigError("unsafe manifest input path") from exc
        validated_inputs.append((relative, expected, target))
    pdf = pdf_path.read_bytes()
    problems = []
    if len(pdf) != output["bytes"] or sha256_bytes(pdf) != output["sha256"]:
        problems.append("the PDF differs from the checksum in its manifest")
    for relative, expected, target in validated_inputs:
        if not target.is_file():
            problems.append(f"input missing: {relative}")
        elif sha256_file(target) != expected:
            problems.append(f"input changed since the build: {relative}")
    inputs = manifest.get("audit_inputs", {})
    if not isinstance(inputs, dict) or not isinstance(manifest.get("audit"), dict) or not isinstance(manifest["audit"].get("exempt_pages"), list):
        raise ConfigError("invalid manifest audit metadata")
    report = audit_pdf(
        pdf, meta, manifest["audit"]["exempt_pages"],
        min_image_dpi=inputs.get("min_image_dpi"),
        contrast=[(n, r) for n, r in inputs.get("contrast", [])],
    )
    if not report.passed:
        problems.append("the audit fails on the stored PDF")
    return VerifyResult(not problems, tuple(problems), report)
