"""Confined path resolution. All file access by the engine goes through this module."""

from __future__ import annotations

from pathlib import Path, PurePath
from typing import Union

from .errors import PathError

PathLike = Union[str, PurePath]


def resolve_inside(root: PathLike, relative: PathLike) -> Path:
    """Resolve relative beneath root.

    The result is guaranteed to stay inside root. Absolute paths, parent
    references and symbolic links in any component are rejected.
    """
    root_path = Path(root).resolve(strict=True)
    rel = PurePath(relative)

    if rel.is_absolute():
        raise PathError(f"absolute path is not allowed: {relative}")
    if not rel.parts:
        raise PathError("empty path is not allowed")

    current = root_path
    for part in rel.parts:
        if part in ("..", "."):
            raise PathError(f"path component is not allowed: {relative}")
        current = current / part
        if current.is_symlink():
            raise PathError(f"symbolic links are not allowed: {relative}")

    resolved = current.resolve(strict=False)
    if resolved != root_path and root_path not in resolved.parents:
        raise PathError(f"path leaves the allowed root: {relative}")
    return resolved
