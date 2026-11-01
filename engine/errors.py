"""Exception types raised by the engine. Every error is explicit and carries its location."""

from __future__ import annotations

from typing import Optional


class EngineError(Exception):
    """Base class for all engine errors."""


class ConfigError(EngineError):
    """Raised when metadata or brand configuration is invalid."""


class PathError(EngineError):
    """Raised when a path leaves its allowed root or traverses a symbolic link."""


class ContentError(EngineError):
    """Raised when document content violates the content format specification."""

    def __init__(self, message: str, line: Optional[int] = None) -> None:
        self.message = message
        self.line = line
        prefix = f"line {line}: " if line is not None else ""
        super().__init__(f"{prefix}{message}")
