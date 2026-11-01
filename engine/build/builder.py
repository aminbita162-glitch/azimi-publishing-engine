"""Build orchestration: validate inputs, render the PDF and write evidence."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Union

import reportlab

from .. import __version__
from ..brand import load_brand
from ..errors import ConfigError, ContentError
from ..paths import resolve_inside
from ..render.document import render_document
from ..render.fonts import register_fonts
from ..schemas.meta import load_meta
from .parser import parse

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
    font_checksums = register_fonts(root / "design-system" / "fonts")
    result = render_document(blocks, meta, brand, folder)

    inputs: Dict[str, str] = {
        "content.md": sha256_file(content_path),
        "meta.yaml": sha256_file(folder / "meta.yaml"),
        f"brand/{brand.name}/brand.yaml": sha256_file(brand.logo_path.parent / "brand.yaml"),
        f"brand/{brand.name}/logo.png": sha256_file(brand.logo_path),
    }
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
        "fonts": font_checksums,
        "inputs": dict(sorted(inputs.items())),
        "output": {"file": file_name, "sha256": pdf_hash, "bytes": len(result.pdf), "pages": result.pages},
    }

    _atomic_write(pdf_path, result.pdf)
    _atomic_write(manifest_path, (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    return BuildResult(pdf_path=pdf_path, manifest_path=manifest_path, sha256=pdf_hash, pages=result.pages)
