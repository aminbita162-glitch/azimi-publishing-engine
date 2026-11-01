"""Helper commands around a build: new document folders, page previews, font listing."""

from __future__ import annotations

import calendar
import shutil
import subprocess
import time
from pathlib import Path
from typing import List, Union

from .errors import ConfigError
from .paths import resolve_inside
from .render.fonts import available_families, load_registry

META_TEMPLATE = """title: {title}
author: {author}
audience: Describe the intended readers in one sentence
language: en
version: 1.0.0
date: {date}
output_name: {name}
numbered: true
"""

CONTENT_TEMPLATE = """# First chapter {{#ch-first}}

OBJECTIVES: State what the reader will be able to do. || Add one objective per line.

## First section

Write the text of the section here. Replace every line of this file before you release the document.

KEY: Chapter summary. State the idea of the chapter in two sentences.
"""

MAX_PREVIEW_PAGES = 12


def scaffold_document(project_root: Union[str, Path], document_dir: str, title: str, author: str) -> Path:
    """Create a new document folder with a valid meta.yaml and a starter content.md."""
    root = Path(project_root).resolve(strict=True)
    folder = resolve_inside(root, document_dir)
    if folder.exists():
        raise ConfigError(f"{document_dir} already exists; nothing was changed")
    if not title.strip() or not author.strip():
        raise ConfigError("title and author must not be empty")
    now = time.gmtime()
    date = f"{calendar.month_name[now.tm_mon]} {now.tm_year}"
    name = "".join(ch if ch.isalnum() else "_" for ch in title.strip())[:80].strip("_") or "Document"
    folder.mkdir(parents=True)
    (folder / "assets").mkdir()
    (folder / "meta.yaml").write_text(
        META_TEMPLATE.format(title=title.strip(), author=author.strip(), date=date, name=name), encoding="utf-8"
    )
    (folder / "content.md").write_text(CONTENT_TEMPLATE, encoding="utf-8")
    return folder


def render_previews(pdf_path: Path, output_dir: Path, pages: List[int], dpi: int = 80) -> List[Path]:
    """Write PNG images of the given pages (1-based). Uses PyMuPDF or pdftoppm, whichever exists."""
    if not pages or len(pages) > MAX_PREVIEW_PAGES or any(p < 1 for p in pages):
        raise ConfigError(f"choose between 1 and {MAX_PREVIEW_PAGES} pages, counted from 1")
    output_dir.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    try:
        import fitz  # PyMuPDF

        with fitz.open(str(pdf_path)) as document:
            for number in pages:
                if number > document.page_count:
                    raise ConfigError(f"the PDF has only {document.page_count} pages")
                target = output_dir / f"page-{number:03d}.png"
                document[number - 1].get_pixmap(dpi=dpi).save(str(target))
                written.append(target)
        return written
    except ImportError:
        pass
    tool = shutil.which("pdftoppm")
    if tool is None:
        raise ConfigError("previews need PyMuPDF (pip install pymupdf) or the pdftoppm tool")
    for number in pages:
        prefix = output_dir / f"page-{number:03d}"
        subprocess.run(
            [tool, "-r", str(dpi), "-f", str(number), "-l", str(number), "-png", "-singlefile", str(pdf_path), str(prefix)],
            check=True, capture_output=True,
        )
        target = prefix.with_suffix(".png")
        if not target.is_file():
            raise ConfigError(f"the PDF has no page {number}")
        written.append(target)
    return written


def describe_fonts(fonts_dir: Path) -> List[str]:
    registry = load_registry(fonts_dir)
    lines = []
    for name in available_families(fonts_dir):
        entry = registry["families"][name]
        files = ", ".join(entry[style] for style in ("regular", "bold", "italic", "bolditalic"))
        lines.append(f"{name}: {files}")
    mono = registry["mono"]
    lines.append(f"code font: {mono['regular']}, {mono['bold']}")
    return lines
