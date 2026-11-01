"""Command line interface: python3 -m engine build PATH"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__
from .build.builder import build_document
from .errors import EngineError

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _relative_to_root(root: Path, argument: str) -> str:
    """Return argument relative to root, comparing both the plain and the resolved root.

    Symbolic links inside the project are not resolved here; they are rejected later
    by the confined path resolution.
    """
    absolute = os.path.abspath(argument)
    for candidate in (os.path.abspath(str(root)), os.path.realpath(str(root))):
        prefix = candidate.rstrip(os.sep) + os.sep
        if absolute == candidate or absolute.startswith(prefix):
            return os.path.relpath(absolute, candidate)
    raise EngineError("document folder must be inside the project")


def main(argv: Optional[List[str]] = None, root: Optional[Path] = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m engine", description="Azimi Publishing Engine")
    parser.add_argument("-V", "-v", action="version", version=f"Azimi Publishing Engine {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="build the PDF of one document folder")
    build.add_argument("path", help="document folder containing meta.yaml and content.md")
    args = parser.parse_args(argv)

    project_root = Path(root) if root is not None else PROJECT_ROOT
    try:
        relative = _relative_to_root(project_root, args.path)
        result = build_document(project_root, relative)
    except EngineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"PDF       : {result.pdf_path}")
    print(f"Manifest  : {result.manifest_path}")
    print(f"Pages     : {result.pages}")
    print(f"SHA-256   : {result.sha256}")
    return 0
