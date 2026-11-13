"""Command line interface: python3 -m engine build PATH"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__
from .build.builder import build_document, check_document, verify_document
from .tools import validate_ticket, deliver_pdf, describe_fonts, render_previews, scaffold_document, verify_agents
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


def _write_review_report(project_root: Path, relative: str, steps: list, build_dir: str, json_module, overall: bool = True) -> None:
    """Write a machine-readable JSON review report to the document's build folder."""
    report = {
        "command": "review",
        "path": relative,
        "steps": steps,
        "overall": "PASS" if overall else "FAIL",
    }
    report_path = Path(project_root) / relative / build_dir / "review-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json_module.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Report    : {report_path}")


def main(argv: Optional[List[str]] = None, root: Optional[Path] = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m engine", description="Azimi Publishing Engine")
    parser.add_argument("-V", "-v", action="version", version=f"Azimi Publishing Engine {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="build the PDF of one document folder")
    build.add_argument("path", help="document folder containing meta.yaml and content.md")
    build.add_argument(
        "--renderer", default="reportlab", choices=["reportlab", "pymupdf"],
        help="PDF renderer (default: reportlab)",
    )
    check = commands.add_parser("check", help="validate and lint a document without writing anything")
    check.add_argument("path")
    verify = commands.add_parser("verify", help="check a built PDF against its manifest and run the audit again")
    verify.add_argument("path")
    review = commands.add_parser("review", help="check, build, verify and audit a document in one step")
    review.add_argument("path")
    new = commands.add_parser("new", help="create a new document folder")
    new.add_argument("path")
    new.add_argument("--title", required=True)
    new.add_argument("--author", required=True)
    preview = commands.add_parser("preview", help="write PNG images of some pages of a built PDF")
    preview.add_argument("path")
    preview.add_argument("--pages", default="1,2,3", help="comma-separated page numbers (default 1,2,3)")
    commands.add_parser("fonts", help="list the font families that can be used in meta.yaml")
    ticket = commands.add_parser("ticket", help="validate a ticket file in the tickets folder")
    ticket.add_argument("path")
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
        if args.command == "ticket":
            problems = validate_ticket(project_root, relative)
            for problem in problems:
                print(f"problem   : {problem}")
            print(f"Ticket    : {'FAIL' if problems else 'PASS'} ({relative})")
            return 2 if problems else 0
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
        if args.command == "review":
            import json as _json

            from .build.builder import BUILD_DIR

            steps: list = []
            # Step 1: check
            try:
                problems, pages = check_document(project_root, relative)
            except EngineError as exc:
                steps.append({"step": "check", "status": "FAIL", "error": str(exc), "exit_code": 2})
                print(f"Check     : FAIL ({exc})")
                _write_review_report(project_root, relative, steps, BUILD_DIR, _json, overall=False)
                return 2
            check_ok = not problems
            steps.append({"step": "check", "status": "PASS" if check_ok else "FAIL",
                          "exit_code": 0 if check_ok else 2,
                          "pages": pages, "lint_problems": len(problems)})
            for issue in problems:
                print(f"lint  {issue}")
            print(f"Check     : {'PASS' if check_ok else 'FAIL'} ({pages} pages, {len(problems)} lint problems)")
            if not check_ok:
                _write_review_report(project_root, relative, steps, BUILD_DIR, _json)
                return 2
            # Step 2: build
            result = build_document(project_root, relative)
            audit_ok = result.audit.passed
            steps.append({"step": "build", "status": "PASS" if audit_ok else "FAIL",
                          "exit_code": 0 if audit_ok else 3,
                          "pages": result.pages, "sha256": result.sha256,
                          "audit_checks": sum(c.passed for c in result.audit.checks)})
            print(f"PDF       : {result.pdf_path}")
            print(f"Manifest  : {result.manifest_path}")
            print(f"Pages     : {result.pages}")
            print(f"SHA-256   : {result.sha256}")
            print(f"Audit     : {'PASS' if audit_ok else 'FAIL'} ({sum(c.passed for c in result.audit.checks)}/{len(result.audit.checks)} checks)")
            if not audit_ok:
                for check in result.audit.checks:
                    if not check.passed:
                        print(f"  {check.id} {check.status}  {check.name}: {check.detail}")
                print("error: the audit failed; the document must not be released", file=sys.stderr)
                _write_review_report(project_root, relative, steps, BUILD_DIR, _json)
                return 3
            # Step 3: verify
            outcome = verify_document(project_root, relative)
            verify_ok = outcome.ok
            steps.append({"step": "verify", "status": "PASS" if verify_ok else "FAIL",
                          "exit_code": 0 if verify_ok else 3,
                          "verify_problems": len(outcome.problems),
                          "audit_checks": sum(c.passed for c in outcome.audit.checks)})
            for problem in outcome.problems:
                print(f"problem   : {problem}")
            print(f"Verify     : {'PASS' if verify_ok else 'FAIL'} (audit {sum(c.passed for c in outcome.audit.checks)}/{len(outcome.audit.checks)})")
            # Step 4: full audit
            steps.append({"step": "audit", "status": "PASS" if outcome.audit.passed else "FAIL",
                          "exit_code": 0 if outcome.audit.passed else 3,
                          "checks": [{"id": c.id, "name": c.name, "status": c.status, "detail": c.detail}
                                     for c in outcome.audit.checks]})
            for check in outcome.audit.checks:
                print(f"  {check.id} {check.status}  {check.name}: {check.detail}")
            overall_ok = check_ok and audit_ok and verify_ok and outcome.audit.passed
            _write_review_report(project_root, relative, steps, BUILD_DIR, _json, overall_ok)
            print(f"Review     : {'PASS' if overall_ok else 'FAIL'}")
            return 0 if overall_ok else 3
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
        result = build_document(project_root, relative, renderer=getattr(args, "renderer", "reportlab"))
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
