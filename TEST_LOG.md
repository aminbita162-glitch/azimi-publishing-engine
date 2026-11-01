| T-004 | November 2026 | Dependencies | Installed packages have no conflicts | python3 -m pip check output | PASS |
| T-005 | November 2026 | Directive | Directive contains no tool-specific or workflow-specific references and no pending engine decision | grep over directive.txt returns no matches | PASS |
| T-006 | November 2026 | Engine | Unit tests for path confinement, metadata schema, content parser and brand loader | python3 -m unittest discover output | PASS |
