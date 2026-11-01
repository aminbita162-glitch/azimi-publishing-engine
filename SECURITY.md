# Security

This project is in active development and is not ready for production use.

## What the engine protects against

- Content that tries to act as code: raw HTML, tabs, control characters and unknown syntax are rejected.
- Path tricks: absolute paths, parent components and symbolic links are rejected for images, fonts and documents.
- Oversized input: content.md is limited to 2 MB, images to 40 million pixels.
- Active content in the output: the audit fails a PDF with scripts, launch actions, forms, attachments or external-file actions, and allows only http and https links.
- Tampered fonts: every font file is checked against SHA256SUMS before use.
- Silent changes: verify compares a built PDF and its inputs with the manifest.

## What it does not protect against

- A malicious person who can already edit the project files or the installed libraries.
- Flaws in the libraries it uses; keep them updated and review requirements.txt.
- Statements in a document that are wrong or misleading; the audit checks the file, not the writing.

## Reporting a problem

Send a private message to the author through the profile linked in README.md. Do not open a public issue with details of a vulnerability.
