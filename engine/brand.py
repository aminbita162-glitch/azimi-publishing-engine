"""Brand loading. A brand is a folder with logo.png and brand.yaml."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Tuple, Union

import yaml
from PIL import Image as PILImage

from .errors import ConfigError
from .paths import resolve_inside

MIN_LOGO_WIDTH = 1000
MAX_LOGO_WIDTH = 8000
MAX_LOGO_BYTES = 8 * 1024 * 1024
MAX_RIGHTS_BYTES = 64 * 1024

_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
_REQUIRED_KEYS = ("display_name", "primary_color", "accent_color")
_OPTIONAL_KEYS = ("tagline",)


@dataclass(frozen=True)
class Brand:
    """A validated brand."""

    name: str
    display_name: str
    primary_color: str
    accent_color: str
    logo_path: Path
    logo_size: Tuple[int, int]
    rights_path: Path
    tagline: Optional[str] = None


def _validate_logo(path: Path) -> Tuple[int, int]:
    if not path.is_file():
        raise ConfigError("brand: logo.png is missing")
    if path.stat().st_size > MAX_LOGO_BYTES:
        raise ConfigError("brand: logo.png is larger than 8 MB")
    try:
        with PILImage.open(path) as image:
            image.load()
            if image.format != "PNG":
                raise ConfigError("brand: logo.png is not a PNG file")
            width, height = image.size
            has_alpha = image.mode in ("RGBA", "LA") or "transparency" in image.info
    except ConfigError:
        raise
    except Exception as exc:  # image decoding failures of any kind
        raise ConfigError("brand: logo.png cannot be read as an image") from exc
    if width < MIN_LOGO_WIDTH:
        raise ConfigError(f"brand: logo.png must be at least {MIN_LOGO_WIDTH} px wide")
    if width > MAX_LOGO_WIDTH:
        raise ConfigError(f"brand: logo.png must be at most {MAX_LOGO_WIDTH} px wide")
    if not has_alpha:
        raise ConfigError("brand: logo.png must have a transparent background")
    return width, height


def load_brand(brand_root: Union[str, Path], name: str) -> Brand:
    """Load and validate the brand called name from brand_root."""
    if not isinstance(name, str) or not _NAME.match(name):
        raise ConfigError("brand: name must be lowercase letters, digits and hyphens")
    folder = resolve_inside(brand_root, name)
    if not folder.is_dir():
        raise ConfigError(f"brand: folder not found: {name}")

    config_path = resolve_inside(folder, "brand.yaml")
    try:
        data: Any = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError("brand: brand.yaml is missing or unreadable") from exc
    except yaml.YAMLError as exc:
        raise ConfigError("brand: brand.yaml has invalid YAML syntax") from exc

    if not isinstance(data, dict):
        raise ConfigError("brand: brand.yaml must be a mapping of keys to values")
    unknown = sorted(set(data) - set(_REQUIRED_KEYS) - set(_OPTIONAL_KEYS))
    if unknown:
        raise ConfigError("brand: unknown keys: " + ", ".join(str(k) for k in unknown))
    missing = [key for key in _REQUIRED_KEYS if key not in data]
    if missing:
        raise ConfigError("brand: missing keys: " + ", ".join(missing))

    display_name = data["display_name"]
    if not isinstance(display_name, str) or not display_name.strip() or len(display_name) > 120:
        raise ConfigError("brand: display_name must be non-empty text of at most 120 characters")
    for key in ("primary_color", "accent_color"):
        value = data[key]
        if not isinstance(value, str) or not _COLOR.match(value):
            raise ConfigError(f"brand: {key} must look like #1A2B3C")

    tagline = None
    if "tagline" in data:
        tagline = data["tagline"]
        if not isinstance(tagline, str) or not tagline.strip() or len(tagline) > 200:
            raise ConfigError("brand: tagline must be non-empty text of at most 200 characters")
        tagline = tagline.strip()

    rights_path = resolve_inside(folder, "rights.md")
    if not rights_path.is_file():
        raise ConfigError("brand: rights.md is missing; every document carries the rights and license text")
    if rights_path.stat().st_size > MAX_RIGHTS_BYTES:
        raise ConfigError("brand: rights.md is larger than 64 KB")

    logo_path = resolve_inside(folder, "logo.png")
    size = _validate_logo(logo_path)
    return Brand(
        name=name,
        display_name=display_name.strip(),
        primary_color=data["primary_color"].upper(),
        accent_color=data["accent_color"].upper(),
        logo_path=logo_path,
        logo_size=size,
        rights_path=rights_path,
        tagline=tagline,
    )
