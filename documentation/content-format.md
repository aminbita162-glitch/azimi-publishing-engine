# Content Format Specification

Version 1.0. This document defines the only input format accepted by the engine.

## Unit of work

One PDF equals one folder containing exactly two files:

- meta.yaml : document metadata
- content.md : document body

Assets (images) live in an assets subfolder of the same folder.

## meta.yaml (required keys)

- title : document title
- subtitle : optional
- author : author name
- audience : target reader description
- language : ISO code, for example en
- version : semantic version, for example 1.0.0
- brand : name of a folder under brand/ (default: default)
- output_name : file name without extension

## content.md (allowed syntax)

- Headings: lines starting with #, ##, ### (maximum depth 3)
- Paragraphs separated by one blank line
- Lists: lines starting with - or with 1.
- Code blocks: fenced with three tildes, language label required on the opening fence
- Tables: pipe tables with a header row
- Images: a line IMG: path | alt text | caption (alt text is mandatory)
- Notes: a paragraph starting with NOTE: or WARNING:
- Page break: a line containing only PAGEBREAK

Anything else is rejected with an error that names the line number.
No raw HTML. No remote URLs for images. No executable content.

## Brand

Each brand is a folder brand/NAME containing:

- logo.png : transparent PNG, at least 1000 px wide
- brand.yaml : display name, primary color, accent color

Replacing the logo and brand.yaml re-brands every PDF built with that brand.
