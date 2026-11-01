# Content Format Specification

Version 1.1. This document defines the only input format accepted by the engine.

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
- output_name : file name without extension; letters, digits, dot, underscore and hyphen

Optional keys:

- subtitle : at most 300 characters
- brand : name of a folder under brand/ (default: default)

Unknown keys are rejected.

## content.md

Allowed block syntax:

- Headings: lines starting with #, ## or ### (maximum depth 3). Levels may not be skipped and the first heading must be level 1.
- Paragraphs: consecutive lines, separated from other blocks by one blank line.
- Lists: lines starting with a hyphen and a space, or with a number, a dot and a space. A list must be followed by a blank line.
- Code blocks: fenced with three tildes. The opening fence must carry a language label. Code content is kept verbatim.
- Tables: pipe tables with a header row, a separator row and at least one data row. Every row has the same number of cells.
- Images: a line IMG: path | alt text | caption. Alt text is mandatory, the caption is optional. The path is relative to the document folder and the file is PNG or JPEG.
- Notes: a paragraph starting with NOTE: or WARNING:
- Page break: a line containing only PAGEBREAK

Allowed inline formatting inside text: bold between double asterisks, italic between single asterisks, inline code between backticks.

Anything else is rejected with an error that names the line number.
No raw HTML. No remote URLs for images. No tab characters outside code blocks. No executable content.

## Brand

Each brand is a folder brand/NAME containing:

- logo.png : transparent PNG between 1000 and 8000 px wide, at most 8 MB
- brand.yaml : display_name, primary_color and accent_color (colors as #RRGGBB)

Replacing the logo and brand.yaml re-brands every PDF built with that brand.
