"""Backward-compatible build-only entry point; never publishes or edits sources."""
from __future__ import annotations
import sys
from typing import Optional, Sequence
from .cli import main as cli_main

def main(argv: Optional[Sequence[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("Usage: python3 -m engine.one_command <document-folder>", file=sys.stderr)
        return 2
    return cli_main(["build", args[0]])

if __name__ == "__main__":
    raise SystemExit(main())
