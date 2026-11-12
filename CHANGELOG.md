# Changelog

## 0.5.9 - November 2026 (PDF standards, metadata and navigation)

- XMP metadata packet in every PDF (title, author, description, language, rights, producer, creator tool, fixed dates from the document month); written with pikepdf; no conformance claim of any kind
- Producer is now "Azimi Publishing Engine <version>"; PageMode UseOutlines opens the outline panel
- PDF page labels: lowercase roman numerals for the front matter, decimal numbers from 1 at the first chapter; printed footers and the contents, list of figures and list of tables use the same labels
- Removed the unused function post_process_pdf and two placeholder comments
- New dependency pikepdf (pinned in requirements.txt, listed in THIRD_PARTY_NOTICES.md); 8 new tests, 2 test assertions updated for the new page numbering
- Not included: tagged PDF structure; release delivery remains hard-disabled

## 0.5.8 - November 2026 (Cleanup)

- README banner now states the real status (active development, unfinished, production release disabled); the earlier banner named a version that does not exist; the heading of the capabilities list shows the current version
- Engine version identifiers in engine/__init__.py and pyproject.toml aligned with this changelog (they still said 0.5.3 while entries 0.5.4 to 0.5.7 existed); the version text printed in the PDF imprint and recorded in build manifests changes accordingly
- Session 01 source folder metadata synchronized with the validated settings (version 2.5.0, chapter_pages true): the folder now builds 61 pages with audit 16 of 16, as recorded in TEST_LOG T-022; before this it failed audit A7 on the previous metadata; the duplicate validation folder courses/ape-v2-5-0-87-cpgmre9g is unchanged and its future is an open owner decision
- Removed engine/render/frontmatter_patch.py: four constants that nothing imported or used
- No change to rendering, audit, release security, brand, agents or tests; release delivery remains hard-disabled

## 0.5.7 - November 2026 (Phase 6)

- Release security threat model and current-state audit: evidence/phase6_threat_model.md documents assets, principals, trust boundaries, attackers, failure modes, filesystem attacks, replay/rollback/substitution threats, existing controls inventory (15 modules, 13 test files, ~61 release-security test cases) and the release fail-closed invariant
- Release authorization contract v1.0: docs/security/release-authorization-contract-v1.0.txt specifies the existing implementation (canonical payload, Ed25519 signature, trust registry, binding, replay, atomic delivery, audit ledger, pipeline ordering, fail-closed release gate) for owner approval — supersedes the v0.1 draft
- Security assurance matrix: evidence/phase6_security_assurance_matrix.md maps 50 threats to controls and negative tests, all PASS; identifies 6 gaps requiring owner approval (concurrent test, permission denied, key rotation sequence, timestamp/expiry, clock skew, pipeline-to-CLI connection)
- Release mode remains HARD-DISABLED: deliver_pdf raises ConfigError before any filesystem operation; cryptographic pipeline not connected to CLI delivery; no release enablement
- Phase 6 evidence: 384 tests pass, 61-page course A1-A16 all PASS (16/16), no code changes

## 0.5.6 - November 2026 (Phase 5)

- Image safety: EXIF orientation transpose in _figure_size via ImageOps.exif_transpose; Figure accepts path string or PIL image source; non-EXIF images use existing path-based behaviour (no change to existing PDFs)
- Image safety tests: corrupt image, huge image (>MAX_PIXELS), transparent RGBA, JPEG acceptance, symlink rejection, EXIF orientation (dimension + build), image-with-id-requires-caption, aspect ratio, non-PNG/JPEG rejection (11 tests)
- Table engine tests: multi-page header repetition, wide table (8 columns), Unicode cells, empty cells, long text wrapping, nested formatting (bold/italic/code), caption/numbering end-to-end, content correspondence, deterministic rebuild (9 tests)
- Diagram engine tests: flow/sequence/layers rendering, too-tall rejection, too-many-nodes rejection, long label wrapping, cycles/back-edges, caption with list-of-figures, flowable scaling, vector-not-raster (10 tests)
- Composition tests: image+table+diagram adjacency, figure/table caption LOF/LOT, chapter boundary with visual content, all-16-check audit, build performance, deterministic rebuild (9 tests)
- Phase 5 closure: 384 tests pass, 61-page course A1-A16 all PASS (16/16), visual QA 30/61 vision-inspected (PARTIAL) + 61/61 pixel + text extraction, zero defects

## 0.5.5 - November 2026 (Phase 4)

- A7 false-fill defence: a painted rectangle spanning at least 90% of the body-frame height (a decorative full-page background, watermark or rule) is no longer counted as body fill; real content rectangles (table cells, code frames, diagram nodes — all far shorter) are still counted
- Audit contract inventory: evidence/phase4_audit_contract.json documents every A1-A16 check (pass predicate, fail fields, negative fixture, false-positive/false-negative risk), thresholds, manifest fields, CLI exit codes and the exemption policy
- Adversarial tests: decorative full-frame background fails A7, short content rectangle is still counted, non-A4 page fails A6 (7 tests)
- Structural/semantic adversarial tests: unembedded font fails A2, javascript: link fails A5, unresolved internal link fails A9, gapped figure numbering fails A10, /AcroForm and /Launch action fail A14, control character fails A16 (8 tests)
- Audit robustness: audit_pdf no longer crashes on truncated, empty, encrypted or malformed PDF input; it fails closed with a single A0 readability check and a deterministic overall FAIL (9 tests)
- Phase 4 closure: 345 tests pass, 61-page course A1-A16 all PASS (16/16), visual QA 24/61 pages vision-inspected (PARTIAL), 61/61 pixel-analyzed and text-extracted, zero defects

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
