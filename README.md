# mdconvertor

A tiny CLI wrapper around [microsoft/markitdown](https://github.com/microsoft/markitdown).
Point it at a file, tell it where to put the result, get Markdown.

```
mdconv <source> [dest]
```

## Install

```bash
uv tool install .        # installs the `mdconv` command globally
```

Or run it from a checkout without installing:

```bash
uv run mdconv report.pdf .
```

## Usage

```bash
mdconv report.pdf .                 # -> ./report.md
mdconv report.pdf out/              # -> out/report.md (created if missing)
mdconv report.pdf out/notes.md      # -> out/notes.md
mdconv report.pdf -                 # -> Markdown on stdout
mdconv report.pdf                   # dest defaults to .
```

The destination is treated as a directory when it already is one, ends with a
`/`, or has no file extension. Otherwise it is used as the output file path.

### Options

| Flag | Meaning |
| --- | --- |
| `-f`, `--force` | Overwrite the output file if it already exists |
| `-q`, `--quiet` | Don't print the `wrote …` line |
| `--plugins` | Enable markitdown plugins |
| `--clear-cache` | Delete the conversion cache used by the MCP server |
| `--version` | Print the version |

By default an existing output file is left alone:

```
$ mdconv report.pdf .
error: report.md already exists (use --force to overwrite)
```

Exit codes: `0` success, `1` conversion or overwrite refusal, `2` source file not found.
The `wrote …` message goes to stderr, so `mdconv file.pdf -` pipes cleanly.

## MCP server

`mdconv-mcp` exposes conversion to an LLM agent over MCP (stdio). Install with the
extra and register it:

```bash
uv sync --extra mcp
```

```json
{
  "mcpServers": {
    "mdconv": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/mdconvertor", "mdconv-mcp"]
    }
  }
}
```

### Why it returns a path, not the text

Returning the converted Markdown from the tool would put the whole document into
the model's context on every call — a 37KB PDF costs ~9,300 tokens, paid again on
every retry. That is the cost this server exists to avoid.

So conversion is a side effect. The Markdown is written to a cache file and the
tool returns only a receipt:

```jsonc
{
  "path": "~/.cache/mdconvertor/70da76c4f6c5120b.md",
  "bytes": 37303, "lines": 812, "est_tokens": 9266,
  "outline": [ {"level": 1, "line": 5, "text": "1. Introduction"}, ... ],
  "preview": "Shared MIME-info Database …",
  "cached": false
}
```

The agent then reads only the lines it needs from `path` using its own file tools,
guided by the outline. On that 37KB spec the receipt is ~1,000 tokens instead of
~9,300, and it stays roughly that size no matter how large the document gets —
the outline is capped at 40 entries.

There is one tool, `convert_to_markdown(source, force=False)`. `source` is a local
path or an `http(s)` URL. Repeat calls hit the cache; `force=true` reconverts.

### Outlines from PDFs

markitdown's PDF converter emits plain text with no `#` headings, so for documents
with no Markdown structure the outline falls back to detecting numbered sections
(`2.3. The Magic Files`). It is a heuristic: strict enough to avoid sending an
agent to the wrong lines, so it will miss unnumbered headings entirely.

### Cache and access

Converted files live in `~/.cache/mdconvertor/`, keyed by a hash of the source
*content*, so renaming or moving a file still hits the cache. URL entries are keyed
on the URL and do not notice upstream changes — pass `force=true` to re-fetch.

| Env var | Effect |
| --- | --- |
| `MDCONVERTOR_CACHE_DIR` | Override the cache location (also honours `XDG_CACHE_HOME`) |
| `MDCONVERTOR_ALLOWED_ROOTS` | Colon-separated roots the server may read from. Unset means unrestricted, which is fine for a server you launch yourself |

Clear it with `mdconv --clear-cache`.

## Supported formats

Whatever markitdown supports — this installs `markitdown[all]`: PDF, Word, PowerPoint,
Excel, HTML, CSV, JSON, XML, images, audio (transcription), Outlook messages, EPUB,
ZIP archives, and YouTube URLs.

## Development

```bash
uv sync --extra mcp
uv run pytest -q
```

The project pins Python 3.12 via `.python-version` (a transitive dependency,
`onnxruntime`, has no 3.14 wheels yet), and enables pre-release resolution
because `markitdown[all]` depends on a beta Azure SDK package.
