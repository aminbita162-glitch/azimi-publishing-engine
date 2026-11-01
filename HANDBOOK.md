# Azimi Publishing Engine - Handbook

STATUS: ACTIVE DEVELOPMENT. This project is not finished and is not ready for production use. Read section 14 for what is missing.

This handbook is both the introduction and the user manual. Whoever opens the project should be able to read it from start to end and know what the project is, what it is not, how it works, and how to build a PDF with it. Version of the engine described here: 0.5.0, November 2026.

## 1. What this project is

Azimi Publishing Engine is a command-line program written in Python. It reads one folder per document (a small settings file and a text file in a strict Markdown-like format, plus pictures) and writes a finished PDF, a manifest that records exactly what went into it, and an audit report. It was created to typeset the 16 PDFs of the Agentic AI Masterclass of Azimi Innovation Lab, and it is meant to serve later documents as well.

## 2. What this project is not

- It is not a word processor, a design tool or a web service.
- It is not a general converter: it accepts only the format in documentation/content-format.md and rejects everything else with an error that names the line.
- It does not write content. A person writes content.md.
- It is not finished. Agents inside the engine, the delivery command, the container package and the desktop product do not exist yet (section 14). The agents that exist run outside the engine (see AGENTS.md).
- It does not produce tagged (PDF/UA) or archival (PDF/A) files (section 13).

## 3. What it is for, and what it is not for

For: long, structured, technical documents such as courses and manuals, in English, left-to-right Latin script, A4 portrait, with code, tables, diagrams, figures and a mandatory rights chapter.

Not for: posters, forms, books with several columns, right-to-left or non-Latin scripts, print production with bleed and crop marks, documents that need accessibility tagging, anything that must be signed or encrypted.

## 4. What it does, and what it does not do

It does:
- parse content strictly and reject anything outside the format;
- number chapters, sections, figures and tables and resolve cross-references;
- draw flow, sequence and layer diagrams from text as vector graphics;
- color code with a built-in scanner and add line numbers;
- build the cover, imprint, contents, lists of figures and tables, body, and the rights chapter;
- render twice and fail if the two results differ;
- run 16 audit checks and refuse to release a PDF that fails one;
- verify a stored PDF later against its manifest.

It does not:
- guess or repair content;
- use system fonts, the network, the clock or random numbers while building;
- run any code that appears in a document;
- make a legal or security claim about the content of a document.

## 5. How it works

1. The command reads meta.yaml (title, author, audience, language, version, month and year, output name, options) and content.md.
2. The parser turns content.md into blocks. Any syntax outside the specification is an error with a line number.
3. Lint checks forbidden terms, repeated words and, for the course profile, the chapter structure.
4. The brand folder supplies the logo, the colors and the rights text. The font family is verified against SHA256SUMS and registered.
5. The renderer lays the document out with ReportLab. Layout repeats until the page count and the running headers no longer change.
6. The document is rendered a second time. If the bytes differ, the build stops.
7. The audit reads the PDF back and checks it. A failed audit stops the build with exit status 3.
8. The PDF and a manifest (inputs and their checksums, fonts, tool versions, statistics, audit result, checksum of the PDF) are written to the build folder of the document.

The document date is the only date the engine uses. It fixes the PDF timestamp, so a build does not depend on the clock.

## 6. Map of the project

| Path | What it is |
|:-----|:-----------|
| README.md | Short description, status and roadmap |
| HANDBOOK.md | This file |
| LICENSE | All rights reserved |
| SECURITY.md | Security model and how to report a problem |
| THIRD_PARTY_NOTICES.md | Libraries and fonts used, with their licenses |
| CHANGELOG.md | Release history |
| TEST_LOG.md | Evidence for every verification performed |
| directive.txt | The fixed engineering rules of the project |
| AGENTS.md | How the three working agents are defined, run and limited |
| agents/ | The complete role definition of each agent: amilus.txt (manager), ali.txt (composer), lili.txt (auditor) |
| requirements.txt | Pinned Python libraries |
| documentation/content-format.md | The only accepted input format |
| engine/ | The program: paths, schemas, parser, lint, brand loader, renderer, diagrams, syntax coloring, audit, builder, tools, command line |
| engine/tests/ | The automated tests of the engine |
| brand/NAME/ | logo.png, brand.yaml, rights.md and optionally forbidden.txt |
| design-system/fonts/ | Bundled fonts, their licenses, SHA256SUMS and optionally fonts.yaml |
| courses/ | One folder per document: meta.yaml, content.md, assets/, and build/ for the output |

## 7. Install and first run

You need Python 3 and the libraries in requirements.txt, installed in a virtual environment.

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    python3 -m unittest discover -s engine/tests -t .

The tests must pass before you build anything.

## 8. Build a PDF step by step

1. Create the folder: python3 -m engine new courses/my-document --title "My Document" --author "Your Name"
2. Open courses/my-document/meta.yaml and set audience, version and date (month and year only). Keys are listed in documentation/content-format.md.
3. Write content.md. Every chapter of a course starts with an OBJECTIVES box and ends with a KEY box that starts with "Chapter summary" when profile: course is set.
4. Put pictures in the assets folder of the document and refer to them with IMG: lines. Use diagram blocks for flows, sequences and layers.
5. Check without building: python3 -m engine check courses/my-document
6. Build: python3 -m engine build courses/my-document
7. Read the audit lines. All 16 must be PASS. The PDF is in courses/my-document/build.
8. Look at pages: python3 -m engine preview courses/my-document --pages 1,2,3
9. Later, prove the file is unchanged: python3 -m engine verify courses/my-document

Exit status: 0 success, 2 input error, 3 audit failure.

## 9. Fonts, logo, rights and forbidden terms

- Font: font: NAME in meta.yaml. List the families with python3 -m engine fonts. Only carlito is bundled. To add a family, copy four TrueType files and their license into design-system/fonts, add their checksums to SHA256SUMS and declare the family in fonts.yaml (documentation/content-format.md, section Fonts).
- Logo and brand: put logo.png (transparent PNG, 1000 to 8000 pixels wide), brand.yaml (display_name, primary_color, accent_color, optional tagline) and rights.md in brand/NAME/ and select it with brand: NAME. Every document built with that brand gets the same cover, colors and rights chapter. Text colors are darkened automatically when needed to reach a contrast of 4.5 to 1.
- Rights: rights.md is mandatory for every brand. It is printed as the last chapter of every PDF.
- Forbidden terms: brand/NAME/forbidden.txt lists terms that must never appear in a document of that brand.

## 10. The audit

| Check | Meaning |
|:------|:--------|
| A1 | Every page has extractable text |
| A2 | All fonts are embedded |
| A3 | Title, author, subject, date and language are set and match meta.yaml |
| A4 | Every outline entry points to its heading |
| A5 | Links are http or https, or have a destination |
| A6 | Every page is A4 |
| A7 | Body pages are at least 72 percent filled |
| A8 | File size is reasonable |
| A9 | Internal links land on a page |
| A10 | Figure and table numbers have no gaps |
| A11 | Smallest text is at least 7.5 pt |
| A12 | Raster images have at least 140 dpi |
| A13 | Text contrast is at least 4.5 to 1 |
| A14 | No scripts, launch actions, forms or attachments |
| A15 | Metadata has no local file paths |
| A16 | Extracted text has no replacement characters |

The audit checks properties of the file. It does not judge the quality of the writing.

## 11. Reproducibility and its limit

On one machine with fixed software versions, building the same inputs twice gives the same bytes; the engine checks this on every build. Different Python, ReportLab, Pillow or pypdf versions, or a different operating system, can give a different byte sequence with the same visible text. The manifest therefore records the tool versions and a hash of the extracted text. Compare checksums only between builds made with the same recorded versions.

## 12. Security model

Content is data, never code. Paths are confined to the project folder, symbolic links are rejected, content size is limited, and links are limited to http and https. The audit refuses PDFs with scripts, launch actions, forms or attachments. See SECURITY.md.

## 13. Standards: what is applied and what is not claimed

Applied: PDF output through ReportLab with embedded subset fonts; document title, author, subject, language and outline; WCAG contrast ratio of 4.5 to 1 for text colors; reproducible timestamps; SIL Open Font License fonts with checksums.

Not claimed: PDF/UA (tagged, accessible PDF) and PDF/A (archival). ReportLab cannot write a structure tree, so no accessibility claim is made. These two are on the roadmap.

## 14. Status and roadmap

Built and tested: everything in sections 4 and 5, the commands in section 8, the audit in section 10.

Not built: agents that run inside the engine (the three agents exist as role definitions in agents/ and run in an external app on the owner's computer, see AGENTS.md); a gate command and JSON output; a delivery command that copies the PDF to an output folder with a checksum check; quality filters Q01 to Q30 as executable checks beyond the audit; PDF/UA tagging; PDF/A output; further bundled font families; hyphenation; right-to-left and non-Latin scripts; container packaging; a desktop product for users without a development agent; continuous integration. PyMuPDF, which can be used for previews, has a license (AGPL or commercial) that must be reviewed before the engine is distributed commercially.

Planned content: 16 sessions of the Agentic AI Masterclass, built one by one, named as a numbered series of Azimi Innovation Lab documents. The sessions currently in the courses folder are trials until they are approved.

## 15. How to change the project

Every change needs a test, an entry in CHANGELOG.md and, for each verification, a line in TEST_LOG.md. Run the whole test suite before a commit. Dates inside the project show month and year only. Nothing from private conversations, no leftover code and no placeholders belong in the project.

## 16. Troubleshooting

| Message | Cause and action |
|:--------|:-----------------|
| error: ... line N | The content breaks the format at that line; fix it |
| lint found N problem(s) | Run the check command to see all of them |
| unknown font family | The name is not in fonts.yaml or built in; run the fonts command |
| the document is not reproducible | Two builds differ; report it, do not release |
| the audit failed | Read the failing A-lines; a diagram or table that does not fit often leaves a page too empty |
| previews need PyMuPDF or pdftoppm | Install one of them; builds do not need them |
