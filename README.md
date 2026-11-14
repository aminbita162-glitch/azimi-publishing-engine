# Azimi Publishing Engine

> # ACTIVE DEVELOPMENT COMPLETE — Production release remains disabled pending separate owner authorization
> The engine builds and audits PDFs from the terminal. It is a general-purpose PDF engine; the 16-session Agentic AI Masterclass in courses/ is a sample. See Roadmap for what is not built.

Deterministic, standards-driven engine for producing publication-grade PDF documents.

AI Architect Amin Azimi | End-to-End System Development and Business Challenges | Azimi Innovation Lab

Start with HANDBOOK.md. It explains what this project is and is not, how it works, every file, and how to build a PDF.

## Purpose

Azimi Publishing Engine turns a structured content folder into a branded PDF with a manifest and an audit report. It is built to typeset the 16-session Agentic AI Masterclass for senior engineers and later educational or commercial documents.

## What works today (version 0.6.1, November 2026)

- Strict input format with line-numbered errors; lint for forbidden terms, repeated words and course structure
- Numbered chapters, sections, figures and tables with automatic cross-references, lists of figures and tables
- Vector diagrams from text: flow, sequence and layers
- Cover, imprint, contents, running header, page X of Y, and a mandatory Rights and License chapter from the brand
- Colored code with line numbers, tables, figures and eight kinds of boxes
- Brand folder (logo, colors, rights) and selectable font families with checksum verification
- Reproducibility check on every build (two renders compared) and a manifest with inputs, tool versions and checksums
- Audit A1 to A16 on every build; a failed audit stops the release
- Keep-together for intro paragraphs before visuals; continuation markers for code and tables that split across pages
- Unified review command (check, build, verify, audit in one step with a JSON report)
- Findings registry, reference lists, series numbering, version history, glossary cross-references
- CycloneDX SBOM on every build; locked hashes (requirements.lock, fonts.lock) verified before every build; offline guarantee enforced
- Optional PyMuPDF renderer alternative (--renderer flag; default ReportLab with zero behavior change)
- Commands: build, check, verify, review, new, preview, fonts, agents, deliver, ticket

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
    python3 -m engine review courses/NAME
    python3 -m engine preview courses/NAME --pages 1,2,3
    python3 -m engine deliver draft courses/NAME
    python3 -m engine ticket tickets/T-S01-001.txt

Exit status: 0 success, 2 input error, 3 audit failure.

## Roadmap

The engine is a general-purpose PDF builder. Active development is complete as of 2026-11-14. The 16-session Agentic AI Masterclass in courses/ is a sample; it does not limit the engine to one course. Further changes require a new owner-approved plan.

Not built, in the order previously planned:

1. Quality filters Q01 to Q30 as executable checks, extending the audit
2. Agents inside the product: the three agents are defined (agents/) and run in an external app on the owner's computer since November 2026. Still to build: a gate command, JSON output and built-in agents for users who do not have that app
3. PDF/UA tagging and PDF/A output, which need a different or additional PDF writer than ReportLab
4. More bundled font families; hyphenation
5. Continuous integration
6. Container packaging for local use
7. Desktop distribution for users without a development agent; the license of the optional preview tool PyMuPDF must be reviewed first
8. Sessions 02 to 16 of the Agentic AI Masterclass, built one by one; Session 01 in courses/ is a validated sample, not a production release

## Author

Amin Azimi, AI Architect.
End-to-End System Development and Business Challenges.
Founder of Azimi Innovation Lab.

## License

All rights reserved. See the LICENSE file. All content in this repository belongs to Amin Azimi and Azimi Innovation Lab, except the bundled fonts, which keep their own open licenses.

<!-- AZIMI_ENGINEERING_ROADMAP_START -->

## Engineering Roadmap — Owner-Gated

**Status:** Planning and design; roadmap entries are not claims of implemented features or verified security. **Owner and release authority:** Amin Azimi (AI Architect | End-to-End System Development). No implementation, installation, key generation, build, publication, or deployment is authorized merely by inclusion in this roadmap. Each implementation phase requires separate owner approval and evidence-based acceptance.

### Completed and evidenced work

- **A-022A — Import contract repair:** preserve the `engine.tools` public import contract and its regression tests. Existing local changes remain subject to their own review and commit.
- **A-022B.1 — Build-only wrapper:** `engine.one_command` delegates only to the central CLI build command; no automatic metadata mutation or independent artifact delivery. Targeted local regression report: 27 tests passed. Existing local changes remain subject to their own review and commit.
- **A-022B.2 — Read-only security review:** inspected `deliver_pdf`, `verify_document`, `resolve_inside`, CLI, and relevant tests. Findings require remediation; the security implementation is **not complete**.

### Priority 1 — A-022B.2: Central release authorization hardening

1. Maintain exactly one release gate, separate from build, preview, verify, and draft workflows. Remove legacy plaintext approval as an acceptable authorization for release after a controlled migration.
2. Use **offline Ed25519 owner-signed release approvals** with a trusted public-key registry, controlled initial key enrollment, key identifiers, rotation and revocation. Keep private keys and sensitive operational state outside the repository. Confirm the supported macOS key custody mechanism before implementation.
3. Define a versioned, domain-separated, canonical-byte approval envelope bound to action, document ID, artifact name/version/hash, manifest hash, policy version, approval ID, and authorized channel/destination where required.
4. Define explicit replay/idempotency policy and durable operation state. Distinguish atomic artifact placement from durable recording of approval consumption and audit evidence; specify crash recovery.
5. Validate manifest schema, types, hashes, audit settings, and input paths before use; reject malformed or untrusted paths, traversal and forbidden symlinks. Preserve compatibility with existing document builds where safe.
6. Deliver only a verified immutable snapshot; address TOCTOU, path races, destination confinement, no-overwrite semantics, atomic placement, post-delivery verification, and safe cleanup. State filesystem and local-adversary assumptions explicitly.
7. Produce structured, bounded, non-secret audit evidence and fail closed on authorization, integrity, and mandatory evidence failures. Cover all entry points, not just `deliver_pdf`.
8. Select and pin a vetted Ed25519 implementation, verify compatibility with Python 3.12 and macOS arm64, and document supply-chain verification before any separately approved installation.
9. Test valid and invalid signatures, wrong or revoked keys, replay, modified PDF/manifest, malformed inputs, traversal, symlink races, concurrent modification, preexisting destination, interrupted delivery, recovery, and old-approval bypass. Preserve both PDF engines and regressions A-022A/A-022B.1.

**Observed baseline risks (read-only source inspection):** plaintext `RELEASE_APPROVAL.txt` SHA-256 authorization; unvalidated manifest field access; manifest input paths joined without `resolve_inside`; verify-to-copy race using `shutil.copy2`; non-atomic destination existence check; and delivery evidence written after copying. These are design/code-review findings, not claims of demonstrated exploitation. No Ed25519 Python package was installed in the inspected virtual environment.

### Priority 2 — Product-wide security architecture and hardening

Conduct an independent, owner-approved threat model and security program covering trust boundaries, agent/tool permissions, document and asset ingestion, secrets and key lifecycle, dependencies and SBOM, CI/CD and provenance, local filesystem security, release packaging, desktop/PWA surfaces if implemented, logging and privacy, backups and recovery, abuse cases, negative tests, and independent review. Define measurable security gates; never claim absolute or certified security without supporting evidence.

### Priority 3 — Three separate governance domains

Proposed root-level structure (design approved; not yet created):

```text
governance/
  document-licenses/
    catalog/
    templates/
    policies/
    jurisdictions/
    schemas/
  software-licenses/
    notices/
    third-party/
    distributions/
    compliance/
  release-authorization/
    policies/
    schemas/
    trust-registry/
```

- **Document licenses:** governed catalog of immutable, versioned, legally reviewed license templates; stable identifiers, language and jurisdiction metadata, provenance, allowed-use rules, document-metadata selection, accurate PDF insertion, and manifest binding to selected license ID/version/content hash. Do not silently alter standardized license texts or grant rights the publisher does not hold.
- **Software licenses:** distinct policy for engine source/distribution, third-party notices, dependency obligations, compatibility, and compliance. Do not conflate a PDF's usage license with the repository's software license.
- **Release authorization:** cryptographic owner approval and trust policy only; not a document license. Public trust policy may be versioned in the repository, while private keys, mutable consumption state, and secrets must remain outside it.

Implement these domains through separately approved, narrowly scoped phases; do not expand A-022B.2 into an unreviewed licensing rewrite.

### Priority 4 — First professionally verified PDF

After the relevant security gate is accepted, define measurable PDF acceptance criteria; create a representative controlled document; build locally; inspect all pages and technical properties (fonts, embedded assets, code blocks, tables, diagrams, links, pagination, accessibility where applicable, print suitability and content fidelity); correct defects; rerun tests; and authorize release only after evidence-backed acceptance. Preserve both rendering engines. A successful unit test or build alone does not certify publication quality.

### Change-control rules

- Owner approval is required separately for code edits, dependency installation, cryptographic key operations, tests/builds, publication, commits and pushes as applicable.
- Preserve the two PDF engines, original source documents, existing A-022A/A-022B.1 work, and unrelated Git changes.
- Prefer bounded changes, explicit preconditions, backups, rollback, and reproducible test evidence. README roadmap publication does not authorize implementation.

<!-- AZIMI_ENGINEERING_ROADMAP_END -->
