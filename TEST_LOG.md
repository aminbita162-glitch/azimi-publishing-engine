| T-004 | November 2026 | Dependencies | Installed packages have no conflicts | python3 -m pip check output | PASS |
| T-005 | November 2026 | Directive | Directive contains no tool-specific or workflow-specific references and no pending engine decision | grep over directive.txt returns no matches | PASS |
| T-006 | November 2026 | Engine | Unit tests for path confinement, metadata schema, content parser and brand loader | python3 -m unittest discover output | PASS |
| T-007 | November 2026 | Engine | Rendering: embedded fonts, outline, metadata, document language, reproducible builds, error reporting | python3 -m unittest discover output | PASS |
| T-008 | November 2026 | Brand | Optional tagline, wide header logo on the cover, default brand configuration | python3 -m unittest discover output | PASS |
