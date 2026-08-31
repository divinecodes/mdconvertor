# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-08-31

First public release.

### Added

- `mdconv`, a CLI wrapping [markitdown](https://github.com/microsoft/markitdown):
  give it a source file and a destination (or `.`) and it writes Markdown.
  Refuses to overwrite without `--force`, and handles a closed pipe cleanly.
- `mdconv-mcp`, an MCP server (stdio) exposing one tool,
  `convert_to_markdown`. Conversion is a side effect: the tool returns a
  receipt — path, size, token estimate, heading outline with line numbers, and
  a short preview — never the document body. On a 37KB PDF that is roughly
  1,000 tokens instead of 9,300, and it stays flat as documents grow.
- A content-addressed conversion cache under `~/.cache/mdconvertor/`, so a
  renamed or moved file still hits it. Cleared with `mdconv --clear-cache`.
- Outline fallback to numbered sections (`2.3. The Magic Files`) for PDFs,
  which markitdown converts without any `#` headings.
- A warning on the silent failure mode: a large source that converts to almost
  no text, which usually means scanned images needing OCR.
- Optional `MDCONVERTOR_ALLOWED_ROOTS` to restrict which paths the server may
  read.

[Unreleased]: https://github.com/divinecodes/mdconvertor/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/divinecodes/mdconvertor/releases/tag/v0.1.0
