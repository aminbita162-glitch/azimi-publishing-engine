"""Durable, fail-closed replay reservation for release approval IDs.

This is a primitive only: not yet wired to delivery. The caller must choose a
private, trusted state directory outside the repository and protect its access.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


class ReplayError(ValueError):
    """Approval cannot be safely reserved."""


def reserve_approval(state_dir: Path, approval_id: str) -> None:
    """Atomically reserve an approval ID; never silently reuse it.

    State directory must already exist, be private, and be owner-controlled.
    A reservation is intentionally not rolled back on later failure.
    """
    if not isinstance(approval_id, str) or not _ID.fullmatch(approval_id):
        raise ReplayError("invalid approval ID")
    directory = Path(state_dir)
    if directory.is_symlink() or not directory.is_dir():
        raise ReplayError("invalid state directory")
    if directory.stat().st_mode & 0o077:
        raise ReplayError("state directory is not private")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(directory / (approval_id + ".used"), flags, 0o600)
    except FileExistsError as exc:
        raise ReplayError("approval already reserved") from exc
    except OSError as exc:
        raise ReplayError("cannot reserve approval") from exc
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(b"reserved\n")
            stream.flush()
            os.fsync(stream.fileno())
        dfd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError as exc:
        raise ReplayError("reservation durability not confirmed") from exc
