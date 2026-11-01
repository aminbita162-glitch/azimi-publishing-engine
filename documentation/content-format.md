# Content Format Specification

Version 1.2. This document defines the only input format accepted by the engine.

## Unit of work

One PDF equals one folder containing exactly two files:

- meta.yaml : document metadata
- content.md : document body

Assets (images) live in an assets subfolder of the same folder.

## meta.yaml

Required keys:

- title : document title, at most 200 characters
- author : author name, at most 120 characters
- audience : target reader description, at most 300 characters
- language : ISO code such as en or en-US
- version : semantic version such as 1.0.0
- date : month and year such as November 2026
- output_name : file name without extension; letters, digits, dot, underscore and hyphen

Optional keys:

- subtitle : at most 300 characters
- brand : name of a folder under brand/ (default: default)

Unknown keys are rejected. The date is the only date used by the engine: it fixes the
document timestamp, so a build never depends on the clock of the machine.

## content.md

Allowed block syntax:

- Headings: lines starting with #, ## or ### (maximum depth 3). Levels may not be skipped and the first heading must be level 1. Every level 1 heading starts a new page.
- Paragraphs: consecutive lines, separated from other blocks by one blank line.
- Lists: lines starting with a hyphen and a space, or with a number, a dot and a space. A list must be followed by a blank line.
- Code blocks: fenced with three tildes. The opening fence must carry a language label. Code content is kept verbatim; tabs are expanded to four spaces and lines longer than the page width are wrapped, with continuation lines indented by two spaces.
- Tables: pipe tables with a header row, a separator row and at least one data row. Every row has the same number of cells. Colons in the separator row set column alignment.
- Images: a line IMG: path | alt text | caption. Alt text is mandatory, the caption is optional. The path is relative to the document folder and the file is PNG or JPEG. Images are scaled to fit the page and never enlarged beyond their natural size at 150 dpi.
- Notes: a paragraph starting with NOTE: or WARNING:
- Page break: a line containing only PAGEBREAK. Consecutive page breaks collapse into one.

Allowed inline formatting inside text: bold between double asterisks, italic between single asterisks, inline code between backticks. An opening marker must be followed by a non-space character and a closing marker must follow a non-space character; otherwise the asterisk is literal.

Anything else is rejected with an error that names the line number.
No raw HTML. No remote URLs for images. No tab characters outside code blocks. No executable content.
Characters that the bundled fonts cannot draw are rejected, so no placeholder boxes can appear in a PDF.

## Brand

Each brand is a folder brand/NAME containing:

- logo.png : transparent PNG between 1000 and 8000 px wide, at most 8 MB; shown on the cover up to the full text width, so a wide header lockup with a tagline line is supported
- brand.yaml : display_name, primary_color and accent_color (colors as #RRGGBB); optional tagline of at most 200 characters, shown on the cover below the logo

Replacing the logo and brand.yaml re-brands every PDF built with that brand.

## Fonts

Fonts are bundled in design-system/fonts and verified against SHA256SUMS before every build.
System fonts are never used. All fonts are embedded in the PDF.

## Build

    python3 -m engine build PATH

PATH is the document folder. The PDF and its manifest are written to the build folder of that
document. The manifest records the engine and library versions, the checksum of every input,
font and brand file, and the checksum of the PDF.
