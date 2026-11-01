# Azimi Publishing Engine

Deterministic, standards-driven engine for producing publication-grade PDF documents.

AI Architect Amin Azimi | End-to-End System Development and Business Challenges | Azimi Innovation Lab

## Purpose

Azimi Publishing Engine turns a structured content folder into a branded,
accessible, reproducible PDF. The same input always produces the same output.
It is built to produce the 16-session Agentic AI Masterclass and any later
educational or commercial document.

## Design principles

- Determinism: identical inputs produce identical page images.
- Separation of concerns: fixed rules, content, brand and engine are separate.
- Evidence before release: every PDF passes audit layers and quality filters.
- Security by default: content is untrusted data, never executable.
- Minimal context: every actor reads only what its task requires.

## Architecture

- directive.txt : the Root Master Engineering Directive (fixed rules, audits, filters, release control)
- documentation/content-format.md : the only accepted input format (one folder per PDF with meta.yaml and content.md)
- brand/ : one folder per brand with logo.png and brand.yaml; replacing the logo re-brands every PDF
- engine/ : render, build, audit, accessibility, schemas and tests
- standards/ and design-system/ : versioned standards and design tokens
- courses/ : course workspaces, one folder per session
- AGENTS.md : operating rules and duties for the three working agents (content composer, builder, auditor)
- TEST_LOG.md : evidence for every verification performed on this project
- CHANGELOG.md : release history

## Technology

Python 3 with ReportLab for rendering, PyMuPDF for page verification, pypdf for
structure and metadata, Pillow for images and PyYAML for configuration.
Versions are pinned in requirements.txt.

## Status

Release 0.1.0 is the foundation release: governing directive, input
specification, operating rules, license and pinned dependencies. The rendering
engine, the three agents and container packaging are delivered in following
releases in the order shown in the roadmap.

## Roadmap

1. Rendering engine with brand loader and content parser
2. Audit layers A1 to A9 and quality filters Q01 to Q30 as executable checks
3. Three working agents under the rules in AGENTS.md
4. Container packaging for local use
5. Desktop distribution for users without a development agent
6. Session 01 to Session 16 of the Agentic AI Masterclass

## Author

Amin Azimi, AI Architect.
End-to-End System Development and Business Challenges.
Founder of Azimi Innovation Lab.

## License

All rights reserved. See the LICENSE file. All content in this repository
belongs to Amin Azimi and Azimi Innovation Lab.
