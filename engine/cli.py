"""Command line interface: python3 -m engine build PATH"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__
from .build.builder import build_document, check_document, verify_document
from .tools import deliver_pdf, describe_fonts, render_previews, scaffold_document, verify_agents
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
    check = commands.add_parser("check", help="validate and lint a document without writing anything")
    check.add_argument("path")
    verify = commands.add_parser("verify", help="check a built PDF against its manifest and run the audit again")
    verify.add_argument("path")
    new = commands.add_parser("new", help="create a new document folder")
    new.add_argument("path")
    new.add_argument("--title", required=True)
    new.add_argument("--author", required=True)
    preview = commands.add_parser("preview", help="write PNG images of some pages of a built PDF")
    preview.add_argument("path")
    preview.add_argument("--pages", default="1,2,3", help="comma-separated page numbers (default 1,2,3)")
    commands.add_parser("fonts", help="list the font families that can be used in meta.yaml")
    commands.add_parser("agents", help="check the agent role files against agents/SHA256SUMS")
    deliver = commands.add_parser("deliver", help="copy a verified PDF to the draft or release folder (owner only)")
    deliver.add_argument("mode", choices=["draft", "release"])
    deliver.add_argument("path")
    args = parser.parse_args(argv)

    project_root = Path(root) if root is not None else PROJECT_ROOT
    try:
        if args.command == "fonts":
            for line in describe_fonts(project_root / "design-system" / "fonts"):
                print(line)
            return 0
        if args.command == "agents":
            results = verify_agents(project_root)
            for name, ok, version, digest in results:
                print(f"{'OK      ' if ok else 'MISMATCH'} {name:7s} {version}  {digest[:16]}")
            return 0 if all(ok for _, ok, _, _ in results) else 2
        relative = _relative_to_root(project_root, args.path)
        if args.command == "deliver":
            target = deliver_pdf(project_root, relative, args.mode)
            print(f"Delivered : {target}")
            return 0
        if args.command == "check":
            problems, pages = check_document(project_root, relative)
            for issue in problems:
                print(f"lint  {issue}")
            print(f"Check     : {'FAIL' if problems else 'PASS'} ({pages} pages, {len(problems)} lint problems)")
            return 2 if problems else 0
        if args.command == "verify":
            outcome = verify_document(project_root, relative)
            for problem in outcome.problems:
                print(f"problem   : {problem}")
            report = outcome.audit
            print(f"Verify    : {'PASS' if outcome.ok else 'FAIL'} (audit {sum(c.passed for c in report.checks)}/{len(report.checks)})")
            return 0 if outcome.ok else 3
        if args.command == "new":
            folder = scaffold_document(project_root, relative, args.title, args.author)
            print(f"Created   : {folder}")
            return 0
        if args.command == "preview":
            try:
                pages = [int(part) for part in args.pages.split(",") if part.strip()]
            except ValueError:
                raise EngineError("pages must be numbers separated by commas")
            from .build.builder import BUILD_DIR
            from .schemas.meta import load_meta
            folder = project_root / relative
            meta = load_meta(folder / "meta.yaml")
            pdf = folder / BUILD_DIR / f"{meta.output_name}_v{meta.version}.pdf"
            if not pdf.is_file():
                raise EngineError("build the document first")
            for image in render_previews(pdf, folder / BUILD_DIR / "preview", pages):
                print(f"Preview   : {image}")
            return 0
        result = build_document(project_root, relative)
    except EngineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"PDF       : {result.pdf_path}")
    print(f"Manifest  : {result.manifest_path}")
    print(f"Pages     : {result.pages}")
    print(f"SHA-256   : {result.sha256}")
    report = result.audit
    print(f"Audit     : {'PASS' if report.passed else 'FAIL'} ({sum(c.passed for c in report.checks)}/{len(report.checks)} checks)")
    for check in report.checks:
        print(f"  {check.id} {check.status}  {check.name}: {check.detail}")
    if not report.passed:
        print("error: the audit failed; the document must not be released", file=sys.stderr)
        return 3
    return 0
