| T-004 | November 2026 | Dependencies | Installed packages have no conflicts | python3 -m pip check output | PASS |
| T-005 | November 2026 | Directive | Directive contains no tool-specific or workflow-specific references and no pending engine decision | grep over directive.txt returns no matches | PASS |
| T-006 | November 2026 | Engine | Unit tests for path confinement, metadata schema, content parser and brand loader | python3 -m unittest discover output | PASS |
| T-007 | November 2026 | Engine | Rendering: embedded fonts, outline, metadata, document language, reproducible builds, error reporting | python3 -m unittest discover output | PASS |
| T-008 | November 2026 | Brand | Optional tagline, wide header logo on the cover, default brand configuration | python3 -m unittest discover output | PASS |
| T-009 | November 2026 | Brand | Default brand loads with the header logo (transparent PNG, width within limits) | engine.brand.load_brand output | PASS |
| T-010 | November 2026 | Course code | Session 01 reference code: eleven unit tests kept as course source (valid, tampered, stale, replay, tenant, expiry, approver, rollback, boolean, allowlist, digest) | python3 -m unittest -v tests.test_session01_reference | PASS |
| T-011 | November 2026 | Document | Session 01 PDF: build, page-by-page visual review, delivery checksum match | build manifest and delivery checksum | PASS |
| T-012 | November 2026 | Engine | Layout engine, audit A1-A8, syntax coloring, boxes, links, imprint, mandatory rights chapter, reproducibility check | python3 -m unittest discover output | PASS |
| T-013 | November 2026 | Document | Session 01 v1.1.0: build, audit PASS, delivery checksum match | build manifest and delivery checksum | PASS |
| T-014 | November 2026 | Engine | Diagrams, numbering, cross-references, captions, new boxes, audit A9-A13 | python3 -m unittest discover output | PASS |
| T-015 | November 2026 | Document | Session 01 v2.0.0: build, audit 13 of 13 PASS, delivery checksum match | build manifest and delivery checksum | PASS |
