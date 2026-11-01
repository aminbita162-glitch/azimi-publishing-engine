# Azimi Publishing Engine

> # ACTIVE DEVELOPMENT - NOT FINISHED - NOT READY FOR PRODUCTION USE
> The engine builds and audits PDFs from the terminal today. Several planned parts do not exist yet. The exact list is under Roadmap.

Deterministic, standards-driven engine for producing publication-grade PDF documents.

AI Architect Amin Azimi | End-to-End System Development and Business Challenges | Azimi Innovation Lab

Start with HANDBOOK.md. It explains what this project is and is not, how it works, every file, and how to build a PDF.

## Purpose

Azimi Publishing Engine turns a structured content folder into a branded PDF with a manifest and an audit report. It is built to typeset the 16-session Agentic AI Masterclass for senior engineers and later educational or commercial documents.

## What works today (version 0.5.0, November 2026)

- Strict input format with line-numbered errors; lint for forbidden terms, repeated words and course structure
- Numbered chapters, sections, figures and tables with automatic cross-references, lists of figures and tables
- Vector diagrams from text: flow, sequence and layers
- Cover, imprint, contents, running header, page X of Y, and a mandatory Rights and License chapter from the brand
- Colored code with line numbers, tables, figures and eight kinds of boxes
- Brand folder (logo, colors, rights) and selectable font families with checksum verification
- Reproducibility check on every build (two renders compared) and a manifest with inputs, tool versions and checksums
- Audit A1 to A16 on every build; a failed audit stops the release
- Commands: build, check, verify, new, preview, fonts, agents, deliver, ticket

## What this project is not

Not a word processor, not a web service, not a content writer, not an accessibility-tagged (PDF/UA) or archival (PDF/A) producer, and not suitable for right-to-left or non-Latin scripts. See the Handbook, sections 2 and 13.

## Design principles

- Determinism: on the same software versions, identical inputs give identical bytes. Every build renders twice and compares. Across different software versions the bytes can differ with the same visible text; the manifest records the versions.
- Separation of concerns: fixed rules, content, brand and engine are separate.
- Evidence before release: every PDF passes an executable audit before it can be delivered.
- Security by default: content is untrusted data, never executable.

## Architecture

- directive.txt : the fixed engineering rules of the project
- documentation/content-format.md : the only accepted input format
- brand/ : one folder per brand with logo.png, brand.yaml, rights.md and optionally forbidden.txt
- design-system/fonts : bundled fonts, license texts, checksums, optional fonts.yaml
- engine/ : paths, schemas, parser, lint, brand loader, renderer, diagrams, syntax coloring, audit, builder, tools, command line and tests
- courses/ : one folder per document
- AGENTS.md and agents/ : the three working agents (manager, composer, auditor): their complete role definitions and how they are run. They run in an external agent app on the owner's computer, not inside the engine
- TEST_LOG.md : evidence for every verification; CHANGELOG.md : release history
- SECURITY.md and THIRD_PARTY_NOTICES.md

## Technology

Python 3 with ReportLab for rendering, pypdf for audit and metadata, Pillow for images and PyYAML for configuration. Fonts are Carlito and Liberation Mono under the SIL Open Font License. Versions are pinned in requirements.txt.

## Usage

    python3 -m engine new courses/NAME --title "Title" --author "Author"
    python3 -m engine check courses/NAME
    python3 -m engine build courses/NAME
    python3 -m engine verify courses/NAME
    python3 -m engine preview courses/NAME --pages 1,2,3
    python3 -m engine deliver draft courses/NAME
    python3 -m engine ticket tickets/T-S01-001.txt

Exit status: 0 success, 2 input error, 3 audit failure.

## Roadmap

Not built yet, in the order currently planned:

1. Quality filters Q01 to Q30 as executable checks, extending the audit
2. Agents inside the product: the three agents are defined (agents/) and run in an external app on the owner's computer since November 2026. Still to build: a gate command, JSON output and built-in agents for users who do not have that app
3. PDF/UA tagging and PDF/A output, which need a different or additional PDF writer than ReportLab
4. More bundled font families; hyphenation
5. Continuous integration
6. Container packaging for local use
7. Desktop distribution for users without a development agent; the license of the optional preview tool PyMuPDF must be reviewed first
8. Sessions 01 to 16 of the Agentic AI Masterclass, built one by one; the sessions in courses/ today are trials

## Author

Amin Azimi, AI Architect.
End-to-End System Development and Business Challenges.
Founder of Azimi Innovation Lab.

## License

All rights reserved. See the LICENSE file. All content in this repository belongs to Amin Azimi and Azimi Innovation Lab, except the bundled fonts, which keep their own open licenses.
