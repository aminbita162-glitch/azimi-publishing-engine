# Azimi Publishing Engine

Deterministic, standards-driven engine for producing publication-grade PDF documents.

AI Architect Amin Azimi | End-to-End System Development and Business Challenges | Azimi Innovation Lab

## Purpose

Azimi Publishing Engine turns a structured content folder into a branded,
accessible, reproducible PDF. The same input always produces the same output.
It is built to produce the 16-session Agentic AI Masterclass and any later
educational or commercial document.

## Design principles

- Determinism: identical inputs produce identical PDFs, byte for byte. Every build renders twice and compares.
- Separation of concerns: fixed rules, content, brand and engine are separate.
- Evidence before release: every PDF passes an executable audit before it can be delivered.
- Security by default: content is untrusted data, never executable.
- Minimal context: every actor reads only what its task requires.

## What a document contains

- Cover with brand logo, title panel and document details
- Imprint page with edition, publisher, copyright and rights summary
- Linked contents with page numbers
- Running header with the current chapter and a footer with page X of Y
- Colored code with line numbers, tables that split cleanly, figures, and five kinds of boxes
- Clickable links, document outline and embedded fonts
- A mandatory Rights and License chapter supplied by the brand

## Architecture

- directive.txt : the Root Master Engineering Directive (fixed rules, audits, filters, release control)
- documentation/content-format.md : the only accepted input format (one folder per PDF with meta.yaml and content.md)
- brand/ : one folder per brand with logo.png, brand.yaml and rights.md; replacing them re-brands every PDF
- design-system/fonts : bundled fonts with license texts and checksums
- engine/ : paths, schemas, parser, brand loader, renderer, syntax coloring, audit, builder, command line and tests
- courses/ : course workspaces, one folder per session
- AGENTS.md : operating rules and duties for the three working agents (content composer, builder, auditor)
- TEST_LOG.md : evidence for every verification performed on this project
- CHANGELOG.md : release history

## Technology

Python 3 with ReportLab for rendering, pypdf for audit and metadata,
Pillow for images and PyYAML for configuration. Fonts are Carlito and
Liberation Mono under the SIL Open Font License. Versions are pinned in
requirements.txt.

## Status

Release 0.3.0 adds the layout engine that fills pages evenly, the executable
audit, colored code with line numbers, instructional boxes, linked addresses,
the imprint page and the mandatory rights chapter.

## Usage

    python3 -m engine build courses/NAME

The command reads meta.yaml and content.md from the document folder, renders the
PDF twice to prove reproducibility, runs the audit and writes the PDF, its manifest
and its audit into the build folder of that document. It exits with status 3 when
the audit fails.

## Roadmap

1. Delivery command with checksum verification into the output folder
2. Quality filters Q01 to Q30 as executable checks, extending the current audit
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
belongs to Amin Azimi and Azimi Innovation Lab, except the bundled fonts, which
keep their own open licenses.
