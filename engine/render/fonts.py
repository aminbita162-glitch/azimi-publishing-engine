"""Font registration with checksum verification.

Fonts are bundled with the project under design-system/fonts and verified
against SHA256SUMS before use, so rendering never depends on system fonts.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Dict, Union

import yaml
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from ..errors import ConfigError

DEFAULT_FAMILY = "carlito"
REGISTRY_FILE = "fonts.yaml"
STYLES = ("regular", "bold", "italic", "bolditalic")

BUILT_IN = {
    "families": {
        DEFAULT_FAMILY: {
            "regular": "Carlito-Regular.ttf",
            "bold": "Carlito-Bold.ttf",
            "italic": "Carlito-Italic.ttf",
            "bolditalic": "Carlito-BoldItalic.ttf",
            "license": "LICENSE-Carlito.txt",
        }
    },
    "mono": {
        "regular": "LiberationMono-Regular.ttf",
        "bold": "LiberationMono-Bold.ttf",
        "license": "LICENSE-LiberationMono.txt",
    },
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


def load_registry(fonts_dir: Union[str, Path]) -> Dict:
    """Return the font registry: the built-in entries plus any families listed in fonts.yaml."""
    registry = {"families": dict(BUILT_IN["families"]), "mono": dict(BUILT_IN["mono"])}
    path = Path(fonts_dir) / REGISTRY_FILE
    if not path.is_file():
        return registry
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"fonts: {REGISTRY_FILE} cannot be read") from exc
    if not isinstance(data, dict) or set(data) - {"families", "mono"}:
        raise ConfigError(f"fonts: {REGISTRY_FILE} may only contain families and mono")
    for name, entry in (data.get("families") or {}).items():
        if not isinstance(name, str) or not re.match(r"^[a-z0-9][a-z0-9-]*$", name):
            raise ConfigError("fonts: a family name must be lowercase letters, digits and hyphens")
        if not isinstance(entry, dict) or not all(isinstance(entry.get(style), str) for style in STYLES):
            raise ConfigError(f"fonts: family {name} needs regular, bold, italic and bolditalic files")
        registry["families"][name] = entry
    if "mono" in data:
        mono = data["mono"]
        if not isinstance(mono, dict) or not all(isinstance(mono.get(k), str) for k in ("regular", "bold")):
            raise ConfigError("fonts: mono needs regular and bold files")
        registry["mono"] = mono
    return registry


def available_families(fonts_dir: Union[str, Path]) -> list:
    return sorted(load_registry(fonts_dir)["families"])


def register_fonts(fonts_dir: Union[str, Path], family: str = DEFAULT_FAMILY) -> Dict[str, str]:
    """Verify and register the document fonts of one family. Returns file name to SHA-256."""
    directory = Path(fonts_dir)
    registry = load_registry(directory)
    if family not in registry["families"]:
        raise ConfigError(
            f"fonts: unknown font family '{family}'; available: " + ", ".join(sorted(registry["families"]))
        )
    expected = _read_checksums(directory)
    verified: Dict[str, str] = {}
    chosen = registry["families"][family]
    mono = registry["mono"]
    files = {
        "Body": chosen["regular"],
        "Body-Bold": chosen["bold"],
        "Body-Italic": chosen["italic"],
        "Body-BoldItalic": chosen["bolditalic"],
        "Mono": mono["regular"],
        "Mono-Bold": mono["bold"],
    }
    for logical, file_name in files.items():
        if "/" in file_name or "\\" in file_name or file_name.startswith("."):
            raise ConfigError(f"fonts: unsafe file name {file_name}")
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
