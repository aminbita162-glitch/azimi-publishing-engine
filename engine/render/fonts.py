"""Font registration with checksum verification.

Fonts are bundled with the project under design-system/fonts and verified
against SHA256SUMS before use, so rendering never depends on system fonts.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Dict, Union

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from ..errors import ConfigError

FONT_FILES = {
    "Body": "Carlito-Regular.ttf",
    "Body-Bold": "Carlito-Bold.ttf",
    "Body-Italic": "Carlito-Italic.ttf",
    "Body-BoldItalic": "Carlito-BoldItalic.ttf",
    "Mono": "LiberationMono-Regular.ttf",
    "Mono-Bold": "LiberationMono-Bold.ttf",
}

CHECKSUM_FILE = "SHA256SUMS"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_checksums(fonts_dir: Path) -> Dict[str, str]:
    sums_path = fonts_dir / CHECKSUM_FILE
    try:
        raw = sums_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"fonts: {CHECKSUM_FILE} is missing in {fonts_dir.name}") from exc
    sums: Dict[str, str] = {}
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) == 2:
            sums[parts[1].lstrip("*")] = parts[0].lower()
    return sums


def register_fonts(fonts_dir: Union[str, Path]) -> Dict[str, str]:
    """Verify and register all document fonts. Returns file name to SHA-256."""
    directory = Path(fonts_dir)
    expected = _read_checksums(directory)
    verified: Dict[str, str] = {}

    for logical, file_name in FONT_FILES.items():
        path = directory / file_name
        if not path.is_file():
            raise ConfigError(f"fonts: {file_name} is missing")
        if file_name not in expected:
            raise ConfigError(f"fonts: {file_name} is not listed in {CHECKSUM_FILE}")
        actual = _sha256(path)
        if actual != expected[file_name]:
            raise ConfigError(f"fonts: checksum mismatch for {file_name}")
        verified[file_name] = actual
        pdfmetrics.registerFont(TTFont(logical, str(path)))

    pdfmetrics.registerFontFamily(
        "Body", normal="Body", bold="Body-Bold", italic="Body-Italic", boldItalic="Body-BoldItalic"
    )
    pdfmetrics.registerFontFamily(
        "Mono", normal="Mono", bold="Mono-Bold", italic="Mono", boldItalic="Mono-Bold"
    )
    return dict(sorted(verified.items()))


def check_glyphs(text: str, font_name: str, line: int | None = None) -> None:
    """Reject characters the font cannot draw, so no placeholder boxes reach a PDF."""
    from ..errors import ContentError

    face = pdfmetrics.getFont(font_name).face
    available = face.charToGlyph
    for char in text:
        code = ord(char)
        if code < 32 or code in available:
            continue
        raise ContentError(f"character U+{code:04X} is not available in the document font", line)
