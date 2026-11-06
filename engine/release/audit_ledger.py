"""Durable, append-only-by-creation release event records; no release side effects."""
from __future__ import annotations
import hashlib
import json
import os
import re
import stat
from pathlib import Path

class AuditLedgerError(ValueError):
    pass

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")

def record_release_event(directory: Path, approval_id: str, artifact_sha256: str, status: str) -> Path:
    """Write one immutable event file; refuse overwrite, symlinks and public directories.

    An event is an observation, not authorization. Caller must ensure trusted ancestors.
    """
    if not isinstance(approval_id, str) or not _ID.fullmatch(approval_id):
        raise AuditLedgerError("invalid approval ID")
    if not isinstance(artifact_sha256, str) or not _DIGEST.fullmatch(artifact_sha256):
        raise AuditLedgerError("invalid artifact digest")
    if status not in ("reserved", "delivered", "failed", "uncertain"):
        raise AuditLedgerError("invalid event status")
    parent = Path(directory)
    if parent.is_symlink() or not parent.is_dir():
        raise AuditLedgerError("invalid audit directory")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    dfd = os.open(parent, flags)
    try:
        info = os.fstat(dfd)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise AuditLedgerError("audit directory not private and owned")
        name = approval_id + "." + status + ".json"
        content = json.dumps({"approval_id": approval_id, "artifact_sha256": artifact_sha256, "status": status}, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=dfd)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.fsync(dfd)
        except BaseException:
            # Never erase evidence after a failed durability confirmation.
            raise
        return parent / name
    except FileExistsError as exc:
        raise AuditLedgerError("audit event already exists") from exc
    finally:
        os.close(dfd)
