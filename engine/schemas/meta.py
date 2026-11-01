"""Document metadata schema (meta.yaml)."""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Union

import yaml

from ..errors import ConfigError

REQUIRED_KEYS = ("title", "author", "audience", "language", "version", "date", "output_name")
OPTIONAL_KEYS = ("subtitle", "brand", "chapter_pages", "numbered", "font", "profile", "keywords")
DEFAULT_BRAND = "default"

_LANGUAGE = re.compile(r"^[a-z]{2,3}(-[A-Z]{2})?$")
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
_MONTHS = tuple(calendar.month_name)[1:]
_DATE = re.compile(r"^(" + "|".join(_MONTHS) + r") (\d{4})$")
_BRAND = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_OUTPUT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

_MAX_LENGTH = {"title": 200, "subtitle": 300, "author": 120, "audience": 300, "output_name": 120}


@dataclass(frozen=True)
class Meta:
    """Validated document metadata."""

    title: str
    author: str
    audience: str
    language: str
    version: str
    date: str
    output_name: str
    subtitle: Optional[str] = None
    brand: str = DEFAULT_BRAND
    chapter_pages: bool = False
    numbered: bool = False
    font: str = "carlito"
    profile: str = "plain"
    keywords: Optional[str] = None

    @property
    def epoch(self) -> int:
        """Seconds since 1970-01-01 UTC at the start of the document month.

        Used as the fixed document timestamp so that builds never depend on the clock.
        """
        match = _DATE.match(self.date)
        assert match is not None  # guaranteed by validation
        month = _MONTHS.index(match.group(1)) + 1
        return calendar.timegm((int(match.group(2)), month, 1, 0, 0, 0))


def _text(data: Dict[str, Any], key: str) -> str:
    value = data[key]
    if not isinstance(value, str):
        raise ConfigError(f"meta.yaml: {key} must be text")
    value = value.strip()
    if not value:
        raise ConfigError(f"meta.yaml: {key} must not be empty")
    limit = _MAX_LENGTH.get(key)
    if limit is not None and len(value) > limit:
        raise ConfigError(f"meta.yaml: {key} exceeds {limit} characters")
    if any(ord(ch) < 32 for ch in value):
        raise ConfigError(f"meta.yaml: {key} contains control characters")
    return value


def parse_meta(data: Any) -> Meta:
    """Validate a parsed mapping and return Meta."""
    if not isinstance(data, dict):
        raise ConfigError("meta.yaml: the document must be a mapping of keys to values")

    unknown = sorted(set(data) - set(REQUIRED_KEYS) - set(OPTIONAL_KEYS))
    if unknown:
        raise ConfigError("meta.yaml: unknown keys: " + ", ".join(str(k) for k in unknown))

    missing = [key for key in REQUIRED_KEYS if key not in data]
    if missing:
        raise ConfigError("meta.yaml: missing required keys: " + ", ".join(missing))

    values: Dict[str, Any] = {key: _text(data, key) for key in REQUIRED_KEYS}

    if not _LANGUAGE.match(values["language"]):
        raise ConfigError("meta.yaml: language must look like en or en-US")
    if not _VERSION.match(values["version"]):
        raise ConfigError("meta.yaml: version must look like 1.0.0")
    if not _DATE.match(values["date"]):
        raise ConfigError("meta.yaml: date must look like November 2026")
    if not _OUTPUT_NAME.match(values["output_name"]) or ".." in values["output_name"]:
        raise ConfigError("meta.yaml: output_name may contain only letters, digits, dot, underscore and hyphen")

    brand = DEFAULT_BRAND
    if "brand" in data:
        brand = _text(data, "brand")
        if not _BRAND.match(brand):
            raise ConfigError("meta.yaml: brand must be lowercase letters, digits and hyphens")

    subtitle = _text(data, "subtitle") if "subtitle" in data else None

    chapter_pages = False
    if "chapter_pages" in data:
        chapter_pages = data["chapter_pages"]
        if not isinstance(chapter_pages, bool):
            raise ConfigError("meta.yaml: chapter_pages must be true or false")
    numbered = False
    if "numbered" in data:
        numbered = data["numbered"]
        if not isinstance(numbered, bool):
            raise ConfigError("meta.yaml: numbered must be true or false")
    font = "carlito"
    if "font" in data:
        font = _text(data, "font")
        if not _BRAND.match(font):
            raise ConfigError("meta.yaml: font must be lowercase letters, digits and hyphens")
    profile = "plain"
    if "profile" in data:
        profile = _text(data, "profile")
        if profile not in ("plain", "course"):
            raise ConfigError("meta.yaml: profile must be plain or course")
    keywords = None
    if "keywords" in data:
        keywords = _text(data, "keywords")
        if len(keywords) > 300:
            raise ConfigError("meta.yaml: keywords exceed 300 characters")
    return Meta(
        subtitle=subtitle, brand=brand, chapter_pages=chapter_pages, numbered=numbered,
        font=font, profile=profile, keywords=keywords, **values,
    )


def load_meta(path: Union[str, Path]) -> Meta:
    """Read and validate a meta.yaml file."""
    file_path = Path(path)
    try:
        raw = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"meta.yaml: cannot read {file_path.name}: {exc.strerror}") from exc
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ConfigError("meta.yaml: invalid YAML syntax") from exc
    return parse_meta(data)
