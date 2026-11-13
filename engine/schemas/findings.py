"""Optional findings.yaml: a list of findings recorded in the build manifest."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

from ..errors import ConfigError

_REQUIRED_FIELDS = ("id", "status", "source", "text")
_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,39}$")


def load_findings(path: Union[str, Path]) -> List[Dict[str, str]]:
    """Read and validate an optional findings.yaml file.

    Returns a list of dicts with keys id, status, source, text (all stripped strings).
    Raises ConfigError on malformed YAML or entries; the message names the line.
    """
    file_path = Path(path)
    try:
        raw = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"findings.yaml: cannot read {file_path.name}: {exc.strerror}") from exc

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError:
        raise ConfigError("findings.yaml: invalid YAML syntax")

    if data is None:
        return []
    if not isinstance(data, list):
        raise ConfigError("findings.yaml: the document must be a list of entries")

    # Attempt to recover per-entry line numbers from the YAML node tree.
    line_map: List[int] = []
    try:
        root = yaml.compose(raw, Loader=yaml.SafeLoader)
        if root is not None and isinstance(root, yaml.SequenceNode):
            line_map = [item.start_mark.line + 1 for item in root.value]
    except yaml.YAMLError:
        pass

    findings: List[Dict[str, str]] = []
    for i, entry in enumerate(data):
        line = line_map[i] if i < len(line_map) else i + 1

        if not isinstance(entry, dict):
            raise ConfigError(f"findings.yaml: line {line}: entry is not a mapping")

        for field in _REQUIRED_FIELDS:
            if field not in entry:
                raise ConfigError(f"findings.yaml: line {line}: missing field '{field}'")
            val = entry[field]
            if not isinstance(val, str) or isinstance(val, bool):
                raise ConfigError(f"findings.yaml: line {line}: field '{field}' must be text")
            if not val.strip():
                raise ConfigError(f"findings.yaml: line {line}: field '{field}' must not be empty")

        entry_id = entry["id"].strip()
        if not _ID_PATTERN.match(entry_id):
            raise ConfigError(
                f"findings.yaml: line {line}: id must be lowercase letters, digits and hyphens, "
                "starting with a letter"
            )

        findings.append(
            {
                "id": entry_id,
                "status": entry["status"].strip(),
                "source": entry["source"].strip(),
                "text": entry["text"].strip(),
            }
        )
    return findings


def load_findings_if_present(folder: Path) -> Optional[List[Dict[str, str]]]:
    """Return validated findings if findings.yaml exists in *folder*, else None."""
    path = folder / "findings.yaml"
    if not path.is_file():
        return None
    return load_findings(path)
