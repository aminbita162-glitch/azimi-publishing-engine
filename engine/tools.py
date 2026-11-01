"""Helper commands around a build: new document folders, page previews, font listing."""

from __future__ import annotations

import calendar
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import List, Tuple, Union

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


AGENT_NAMES = ("amilus", "ali", "lili")
AGENTS_DIR = "agents"
AGENT_SUMS = "SHA256SUMS"
APPROVAL_FILE = "RELEASE_APPROVAL.txt"
OUTPUT_ENV = "AZIMI_OUTPUT_DIR"
OUTPUT_FOLDER = "Azimi-Publishing-Output"
DRAFTS_FOLDER = "Drafts"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_agents(project_root: Union[str, Path]) -> List[Tuple[str, bool, str, str]]:
    """Compare the agent definition files with agents/SHA256SUMS.

    Returns (name, ok, version line, sha256) for every agent. A missing file or a missing
    checksum line counts as not ok.
    """
    root = Path(project_root).resolve(strict=True)
    folder = root / AGENTS_DIR
    sums_path = folder / AGENT_SUMS
    if not sums_path.is_file():
        raise ConfigError("agents/SHA256SUMS is missing")
    expected = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 2:
            expected[parts[1].lstrip("*")] = parts[0].lower()
    results = []
    for name in AGENT_NAMES:
        file_name = f"{name}.txt"
        path = folder / file_name
        if not path.is_file():
            results.append((name, False, "missing", ""))
            continue
        actual = _sha256_file(path)
        lines = path.read_text(encoding="utf-8").splitlines()
        version = lines[1].strip() if len(lines) > 1 else "unknown"
        results.append((name, expected.get(file_name) == actual, version, actual))
    return results


def output_base() -> Path:
    """The delivery folder: AZIMI_OUTPUT_DIR if set, otherwise Desktop/Azimi-Publishing-Output of the current user."""
    override = os.environ.get(OUTPUT_ENV)
    if override:
        return Path(override)
    return Path.home() / "Desktop" / OUTPUT_FOLDER


def deliver_pdf(project_root: Union[str, Path], document_dir: str, mode: str) -> Path:
    """Copy a verified PDF to the draft or release folder and check the copy.

    draft   goes to the Drafts subfolder and needs a passing verify.
    release goes to the output folder, needs a passing verify and a RELEASE_APPROVAL.txt in the
            document folder that names the SHA-256 of this exact PDF.
    Nothing is ever overwritten with different content.
    """
    from .build.builder import BUILD_DIR, verify_document
    from .schemas.meta import load_meta

    if mode not in ("draft", "release"):
        raise ConfigError("delivery mode must be draft or release")
    root = Path(project_root).resolve(strict=True)
    folder = resolve_inside(root, document_dir)
    outcome = verify_document(root, document_dir)
    if not outcome.ok:
        raise ConfigError("delivery stopped: " + "; ".join(outcome.problems))
    meta = load_meta(folder / "meta.yaml")
    pdf = folder / BUILD_DIR / f"{meta.output_name}_v{meta.version}.pdf"
    checksum = _sha256_file(pdf)
    if mode == "release":
        approval = folder / APPROVAL_FILE
        if not approval.is_file():
            raise ConfigError(f"release stopped: {APPROVAL_FILE} is missing in the document folder")
        approved = re.findall(r"(?mi)^APPROVED\s+([0-9a-f]{64})\b", approval.read_text(encoding="utf-8"))
        if checksum not in approved:
            raise ConfigError("release stopped: the approval file does not name the checksum of this PDF")
    base = output_base()
    target_dir = base / DRAFTS_FOLDER if mode == "draft" else base
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / pdf.name
    if target.exists() and _sha256_file(target) != checksum:
        raise ConfigError(f"delivery stopped: {target.name} already exists with different content and was not overwritten")
    if not target.exists():
        shutil.copy2(pdf, target)
    if _sha256_file(target) != checksum:
        raise ConfigError("delivery failed: the copy does not match the built PDF")
    now = time.gmtime()
    record = {
        "file": pdf.name, "sha256": checksum, "mode": mode, "destination": str(target_dir),
        "month": f"{calendar.month_name[now.tm_mon]} {now.tm_year}", "verified": True,
    }
    (folder / BUILD_DIR / f"delivery-{mode}.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


TICKETS_DIR = "tickets"
TICKET_FIELDS = ("TICKET-ID", "DOCUMENT", "VERSION", "GOAL", "INPUTS", "ACCEPTANCE")
_TICKET_ID = re.compile(r"^T-[A-Z0-9]{2,8}-\d{3}$")
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
_DAY_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}[./]\d{1,2}[./]\d{2,4})\b")
MAX_TICKET_BYTES = 20 * 1024


def parse_ticket(text: str):
    """Return {field: value}; a value continues on the following lines that start with two spaces."""
    fields = {}
    current = None
    for number, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        if raw.startswith("  ") and current:
            fields[current] += " " + raw.strip()
            continue
        name, separator, value = raw.partition(":")
        if not separator or name != name.upper() or not name.replace("-", "").isalpha():
            raise ConfigError(f"ticket line {number} is not FIELD: value")
        if name in fields:
            raise ConfigError(f"ticket field {name} appears twice")
        fields[name] = value.strip()
        current = name
    return fields


def validate_ticket(project_root: Union[str, Path], ticket_path: str) -> List[str]:
    """Return the list of problems of a ticket file (empty when it is valid)."""
    from .schemas.meta import load_meta

    root = Path(project_root).resolve(strict=True)
    path = resolve_inside(root, ticket_path)
    problems: List[str] = []
    if path.parent != (root / TICKETS_DIR).resolve():
        problems.append("a ticket must be a file directly inside the tickets folder")
    if not path.is_file():
        raise ConfigError(f"ticket not found: {ticket_path}")
    if path.stat().st_size > MAX_TICKET_BYTES:
        raise ConfigError("ticket is larger than 20 KB")
    try:
        text = path.read_text(encoding="utf-8")
        text.encode("ascii")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return problems + ["a ticket must be plain ASCII text"]
    fields = parse_ticket(text)
    for name in TICKET_FIELDS:
        if not fields.get(name):
            problems.append(f"missing field {name}")
    unknown = sorted(set(fields) - set(TICKET_FIELDS) - {"OWNER-DECISIONS"})
    if unknown:
        problems.append("unknown fields: " + ", ".join(unknown))
    ticket_id = fields.get("TICKET-ID", "")
    if ticket_id and not _TICKET_ID.match(ticket_id):
        problems.append("TICKET-ID must look like T-S01-001")
    if ticket_id and path.name != f"{ticket_id}.txt":
        problems.append(f"the file name must be {ticket_id}.txt")
    version = fields.get("VERSION", "")
    if version and not _VERSION.match(version):
        problems.append("VERSION must look like 2.2.0")
    document = fields.get("DOCUMENT", "")
    if document:
        try:
            folder = resolve_inside(root, document)
            if not (folder / "meta.yaml").is_file():
                problems.append("DOCUMENT has no meta.yaml")
            elif version and load_meta(folder / "meta.yaml").version != version:
                problems.append("VERSION must equal the version in the meta.yaml of the document")
        except Exception:
            problems.append("DOCUMENT must be a document folder inside the project")
    if _DAY_DATE.search(text):
        problems.append("dates may show month and year only")
    return problems
