"""Build orchestration: validate inputs, render the PDF and write evidence."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Union

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
from .parser import Code, Diagram, Heading, Image, Table, parse

MAX_CONTENT_BYTES = 2 * 1024 * 1024
BUILD_DIR = "build"
MANIFEST_SUFFIX = ".manifest.json"


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


def build_document(project_root: Union[str, Path], document_dir: Union[str, Path]) -> BuildResult:
    """Build the PDF for one document folder (relative to project_root)."""
    root = Path(project_root).resolve(strict=True)
    folder = resolve_inside(root, document_dir)
    if not folder.is_dir():
        raise ConfigError(f"document folder not found: {document_dir}")

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
    result = render_document(blocks, meta, brand, folder, rights_blocks)
    again = render_document(blocks, meta, brand, folder, rights_blocks)
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
    pages = render_document(blocks, meta, brand, folder, rights_blocks).pages
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
    pdf = pdf_path.read_bytes()
    problems = []
    if sha256_bytes(pdf) != manifest["output"]["sha256"]:
        problems.append("the PDF differs from the checksum in its manifest")
    for relative, expected in manifest["inputs"].items():
        base = root if relative.startswith("brand/") else folder
        target = base / relative
        if not target.is_file():
            problems.append(f"input missing: {relative}")
        elif sha256_file(target) != expected:
            problems.append(f"input changed since the build: {relative}")
    inputs = manifest.get("audit_inputs", {})
    report = audit_pdf(
        pdf, meta, manifest["audit"]["exempt_pages"],
        min_image_dpi=inputs.get("min_image_dpi"),
        contrast=[(n, r) for n, r in inputs.get("contrast", [])],
    )
    if not report.passed:
        problems.append("the audit fails on the stored PDF")
    return VerifyResult(not problems, tuple(problems), report)


def post_process_pdf(pdf_path: str) -> None:
    """Add basic structure and XMP using pikepdf."""
    import pikepdf
    with pikepdf.open(pdf_path, allow_overwriting_input=True) as pdf:
        # Basic XMP foundation
        if pdf.docinfo is not None:
            pdf.docinfo["/Producer"] = "Azimi Publishing Engine"
        pdf.save(pdf_path)
 for tagging and XMP
# TODO: apply structure tree and XMP packet after ReportLab render
