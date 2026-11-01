# Changelog

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
