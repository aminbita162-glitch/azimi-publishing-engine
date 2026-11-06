"""Fail-closed, no-overwrite PDF placement primitive; not a release authorization."""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import stat
from pathlib import Path


class AtomicPlacementUncertain(OSError):
    """Placement or cleanup outcome requires manual reconciliation."""


class AtomicDeliveryError(ValueError):
    """Snapshot cannot be placed safely."""


def place_verified_snapshot(source: Path, destination: Path, expected_sha256: str) -> Path:
    """Copy to private temporary inode, verify, fsync, then hard-link exclusively.

    Never removes the final destination on failure. The caller must control all
    ancestor directories, hold a trusted immutable source, and authorize release.
    """
    if not isinstance(expected_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
        raise AtomicDeliveryError("invalid digest")
    src, dst = Path(source), Path(destination)
    parent = dst.parent
    if src.is_symlink() or not src.is_file() or parent.is_symlink() or not parent.is_dir():
        raise AtomicDeliveryError("unsafe source or destination directory")
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory_fd = source_fd = temporary_fd = None
    temporary_name = None
    try:
        directory_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | nofollow)
        directory_stat = os.fstat(directory_fd)
        if not stat.S_ISDIR(directory_stat.st_mode) or directory_stat.st_uid != os.getuid() or directory_stat.st_mode & 0o077:
            raise AtomicDeliveryError("destination directory must be private and owned")
        source_fd = os.open(src, os.O_RDONLY | nofollow)
        source_stat = os.fstat(source_fd)
        if not stat.S_ISREG(source_stat.st_mode):
            raise AtomicDeliveryError("source must be regular")
        # Existing destination, including a symlink, must never be replaced.
        try:
            os.stat(dst.name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise AtomicDeliveryError("destination already exists")
        for _ in range(10):
            candidate = ".ape-pending-" + secrets.token_hex(16)
            try:
                temporary_fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow, 0o600, dir_fd=directory_fd)
                temporary_name = candidate
                break
            except FileExistsError:
                continue
        if temporary_fd is None:
            raise AtomicDeliveryError("cannot allocate temporary file")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(source_fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(temporary_fd, view)
                if written <= 0:
                    raise AtomicDeliveryError("short write")
                view = view[written:]
        # Detect a source inode changed during streaming, even if a digest happens
        # to match the requested content. The caller must still own the source tree.
        source_after = os.fstat(source_fd)
        identity = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(source_stat, field) != getattr(source_after, field) for field in identity):
            raise AtomicDeliveryError("source changed during snapshot")
        if digest.hexdigest() != expected_sha256:
            raise AtomicDeliveryError("snapshot digest mismatch")
        os.fsync(temporary_fd)
        os.close(temporary_fd)
        temporary_fd = None
        # Atomic no-clobber publication. No destination cleanup on later errors.
        os.link(temporary_name, dst.name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd, follow_symlinks=False)
        try:
            os.fsync(directory_fd)
        except OSError as exc:
            raise AtomicPlacementUncertain("post-link durability uncertain") from exc
        return dst
    except FileExistsError as exc:
        raise AtomicDeliveryError("destination already exists") from exc
    finally:
        if temporary_fd is not None:
            os.close(temporary_fd)
        if temporary_name is not None and directory_fd is not None:
            try:
                os.unlink(temporary_name, dir_fd=directory_fd)
                os.fsync(directory_fd)
            except OSError as exc:
                raise AtomicPlacementUncertain("temporary cleanup failed; manual reconciliation required") from exc
        if source_fd is not None:
            os.close(source_fd)
        if directory_fd is not None:
            os.close(directory_fd)
