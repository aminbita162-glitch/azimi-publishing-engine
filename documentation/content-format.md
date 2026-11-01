# Content Format Specification

Version 1.3. This document defines the only input format accepted by the engine.

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
- chapter_pages : true to start every level 1 heading on a new page; false (default) lets chapters flow continuously

Unknown keys are rejected. The date is the only date used by the engine: it fixes the
document timestamp, so a build never depends on the clock of the machine.

## content.md

Allowed block syntax:

- Headings: lines starting with #, ## or ### (maximum depth 3). Levels may not be skipped and the first heading must be level 1.
- Paragraphs: consecutive lines, separated from other blocks by one blank line.
- Lists: lines starting with a hyphen and a space, or with a number, a dot and a space. A list must be followed by a blank line.
- Code blocks: fenced with three tildes. The opening fence must carry a language label. Code content is kept verbatim; tabs are expanded to four spaces and long lines are wrapped, with continuation lines indented by two spaces.
- Tables: pipe tables with a header row, a separator row and at least one data row. Every row has the same number of cells. Colons in the separator row set column alignment.
- Images: a line IMG: path | alt text | caption. Alt text is mandatory, the caption is optional. The path is relative to the document folder and the file is PNG or JPEG.
- Boxes: a paragraph that starts with one of the labels NOTE:, WARNING:, TIP:, KEY: or CHECKPOINT:
- Page break: a line containing only PAGEBREAK. Consecutive page breaks collapse into one.

Allowed inline formatting inside text: bold between double asterisks, italic between single asterisks, inline code between backticks. An opening marker must be followed by a non-space character and a closing marker must follow a non-space character; otherwise the asterisk is literal.

Web addresses such as github.com/owner/repo or https://example.com/page become clickable links automatically. Only http and https links are produced. Addresses inside inline code are never linked.

Anything else is rejected with an error that names the line number.
No raw HTML. No remote URLs for images. No tab characters outside code blocks. No executable content.
Characters that the bundled fonts cannot draw are rejected, so no placeholder boxes can appear in a PDF.

### Boxes

| Label | Printed as | Use |
|:------|:-----------|:----|
| NOTE | NOTE | Context the reader should not miss |
| WARNING | WARNING | A risk, a limit or a claim that must not be made |
| TIP | TIP | A practical shortcut |
| KEY | KEY POINT | The idea to remember |
| CHECKPOINT | CHECKPOINT | A question for the reader to answer before continuing |

### Code blocks

Python, TypeScript (also ts, js), shell (sh, bash), SQL, JSON and YAML are colored by a built-in, deterministic scanner. Any other label is printed without color. Blocks of four or more lines in Python, TypeScript, SQL, JSON and YAML carry line numbers; the numbers count lines inside the block.

## Document structure produced by the engine

1. Cover: brand logo, title panel, author, audience, version and date
2. Imprint: edition, author, publisher, copyright, rights summary and production note
3. Contents: two levels, linked, with page numbers
4. Body: the content of content.md
5. Rights and License: the text of the brand file rights.md, always the last chapter

Every page after the cover carries a running header (document title and current chapter) and a footer (publisher, version, date, page X of Y).

## Layout rules

- Chapters flow continuously. A new chapter starts a new page only when less than about 58 mm is left on the current page, or when chapter_pages is true.
- A heading is never left alone at the bottom of a page, and a code block keeps its label and first lines together.
- Tables split between rows and repeat the header row. Table columns never break a word.
- A figure shrinks to at most 75% of its size to fit the space that is left; otherwise it moves to the next page.
- Body pages must be filled to at least 72%. The audit fails the build otherwise.

## Brand

Each brand is a folder brand/NAME containing:

- logo.png : transparent PNG between 1000 and 8000 px wide, at most 8 MB; shown on the cover up to the full text width, so a wide header lockup with a tagline line is supported
- brand.yaml : display_name, primary_color and accent_color (colors as #RRGGBB); optional tagline of at most 200 characters, shown on the cover below the logo
- rights.md : the rights and license text in the same syntax as content.md, starting with a level 1 heading. It is mandatory: every document carries it as its last chapter.

Replacing the logo, brand.yaml and rights.md re-brands every PDF built with that brand.

## Fonts

Fonts are bundled in design-system/fonts and verified against SHA256SUMS before every build.
System fonts are never used. All fonts are embedded in the PDF.

## Build and audit

    python3 -m engine build PATH

PATH is the document folder. The PDF, its manifest and its audit are written to the build folder of that
document. Every build renders the document twice and fails if the two results differ.

The audit runs automatically:

| Check | Meaning |
|:------|:--------|
| A1 | Every page carries extractable text |
| A2 | All fonts are embedded |
| A3 | Title, author, subject, date and document language are set and match meta.yaml |
| A4 | Every outline entry points to the page where its heading is printed |
| A5 | Every link is http or https, and every internal link has a destination |
| A6 | Every page is A4 |
| A7 | Body pages are filled to at least 72% |
| A8 | The file size is reasonable |

The command exits with status 0 when the audit passes, 2 for an input error and 3 when the audit fails.
The manifest records the engine and library versions, the checksum of every input, font and brand file, the checksum of the PDF and the audit result.
