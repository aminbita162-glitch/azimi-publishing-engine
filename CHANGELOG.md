# Changelog

## 0.5.5 - November 2026 (Phase 4)

- A7 false-fill defence: a painted rectangle spanning at least 90% of the body-frame height (a decorative full-page background, watermark or rule) is no longer counted as body fill; real content rectangles (table cells, code frames, diagram nodes — all far shorter) are still counted
- Audit contract inventory: evidence/phase4_audit_contract.json documents every A1-A16 check (pass predicate, fail fields, negative fixture, false-positive/false-negative risk), thresholds, manifest fields, CLI exit codes and the exemption policy
- Adversarial tests: decorative full-frame background fails A7, short content rectangle is still counted, non-A4 page fails A6 (7 tests)
- Structural/semantic adversarial tests: unembedded font fails A2, javascript: link fails A5, unresolved internal link fails A9, gapped figure numbering fails A10, /AcroForm and /Launch action fail A14, control character fails A16 (8 tests)

## 0.5.4 - November 2026

- A7 page-fill threshold raised from 72% to 87% (MAX_BLANK_RATIO 0.35 → 0.13)
- Page-fill measurement now includes painted rectangles and XObject images, not just text baselines
- Audit reporting: Check.issues carries the full structured failure list; detail shows a bounded preview with an explicit total count (no silent truncation beyond six)
- Manifest verify hardened: validates digest format, rejects boolean byte counts, parent-directory traversal, backslash paths, wrong-brand paths and malformed audit metadata
- Layout calibration: H2/H3 spaceBefore 50/52 → 28, code_label spaceBefore 50 → 18, table_caption spaceBefore 50 → 24, CHAPTER_MIN_SPACE 58mm → 28mm, KeepTogether wrapper removed from code blocks, MIN_DIAGRAM_SCALE 0.85 → 0.78
- chapter_pages dual-page exemption: when chapter_pages is true, both the chapter-end page (KEY POINT summary) and the chapter-start page (heading + objectives) are exempt from A7 as structural boundaries
- TempProject test helper supports both context-manager and setUpClass/tearDownClass protocols
- Dead unreachable brand-namespace branch removed from verify_document
- Release delivery hard-disabled pending cryptographic owner authorization
- Regression tests: audit reporting (9), manifest negative (12), pagination contract (4)

## 0.5.3 - November 2026

- Tickets as files: the owner writes tickets/ID.txt, the agents exchange handoff, delivery, audit and report files in the tickets folder
- Command ticket validates a ticket file; template and first ticket added
- Agent role files version 2.3, 1.3 and 2.3 with the ticket rules and their narrow write permissions
- Session 01 prepared as version 2.2.0

## 0.5.2 - November 2026

- Command agents: checks the three agent role files against agents/SHA256SUMS
- Command deliver: draft copies go to the Drafts folder, releases need the owner approval file for the exact PDF; nothing is overwritten
- Agents read their own file from the project at the start of every ticket; Amilus reports the checksum result
- directive.txt updated to V1.2: third workflow, real workspace structure, drafts separated from releases

## 0.5.1 - November 2026

- The three agent role definitions are installed in agents/ (manager, composer, auditor)
- AGENTS.md rewritten: how the agents run, their limits and how to restore them
- README and HANDBOOK corrected: agents run in an external application, not inside the engine
- Tests check that every role file is complete, consistent and free of local paths

## 0.5.0 - November 2026

- Selectable font families (fonts.yaml, checksum verified)
- Content lint: forbidden terms per brand, repeated words, course structure
- Commands check, verify, new, preview and fonts
- Audit A14 to A16: no active content, no local paths in metadata, clean text extraction
- Manifest records tool versions, content statistics and a text hash
- Sequence diagram self-messages no longer clip at the page edge
- HANDBOOK, SECURITY and THIRD_PARTY_NOTICES added; README rewritten with the true status and roadmap

## 0.4.0 - November 2026

- Vector diagrams drawn from text: flow, sequence and layers
- Numbered chapters and sections, automatic cross-references, numbered figure and table captions
- Lists of figures and tables
- New boxes: learning objectives, worked example, common pitfall
- Audit A9 to A13: link targets, numbering, text size, image resolution, color contrast
- Body text 11 pt; label colors adjusted to a contrast ratio of at least 4.5 to 1

## 0.3.0 - November 2026

- Continuous chapter flow with conditional page breaks; no half-empty pages
- Executable audit A1 to A8 on every build, written into the manifest, exit status 3 on failure
- Every build renders twice and fails if the two results differ
- Code colored by a built-in deterministic scanner, with line numbers
- Boxes: note, warning, tip, key point and checkpoint
- Clickable web addresses, running chapter header, page X of Y
- Cover redesign, imprint page, mandatory Rights and License chapter supplied by the brand
- Flexible figures that shrink to fit before moving to the next page

## 0.2.1 - November 2026

- Code blocks drawn as framed panels that flow across pages
- Table columns never split words
- Introductions stay with the code, table or figure they introduce
- Course workspace for Session 01 of the Agentic AI Masterclass: source text, reference code, tests and figure

## 0.2.0 - November 2026

- Content parser with line-numbered errors
- Metadata and brand validation
- Confined path resolution
- Rendering engine: cover, contents, headers, code, tables, figures, callouts
- Bundled fonts verified by checksum and embedded in every PDF
- Reproducible builds with a manifest of input and output checksums
- Build command
- Automated tests

## 0.1.1 - November 2026

- Directive aligned with the ReportLab rendering pipeline
- Execution communication rewritten as tool-neutral terminal and automated modes
- Body text size fixed at 10.5 pt
- Agent rules cleaned

## 0.1.0 - November 2026

Foundation release by Amin Azimi, Azimi Innovation Lab.

- Root Master Engineering Directive
- Content format specification
- Agent operating rules
- License with full ownership statement
- Pinned dependencies
- Test log
