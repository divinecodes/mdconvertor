# mdconvertor

A tiny CLI wrapper around [microsoft/markitdown](https://github.com/microsoft/markitdown).
Point it at a file, tell it where to put the result, get Markdown.

```
mdconv <source> [dest]
```

## Install

```bash
uv tool install --prerelease=allow ".[mcp]"
```

That installs two commands globally: `mdconv` (the CLI) and `mdconv-mcp` (the
[MCP server](#mcp-server)). Drop `[mcp]` for the CLI alone.

`--prerelease=allow` is required: `markitdown[all]` depends on a beta Azure SDK,
and the `[tool.uv]` setting in `pyproject.toml` only covers `uv sync`, not
`uv tool install`. Without it the install fails to resolve.

Python 3.10 through 3.13 are supported and tested. 3.14 works for a direct
install on Linux and macOS but is not supported: `markitdown` pins
`magika~=0.6.1`, which caps `onnxruntime` at 1.20.1 on Windows, and that release
has no 3.14 wheels.

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

Exit codes: `0` success, `1` conversion failure or overwrite refusal, `2` source file
not found, `141` the pipe was closed downstream (`mdconv report.pdf - | head`).

The `wrote …` message goes to stderr, so `mdconv report.pdf - > out.md` and piping
into `head` both stay clean.

## MCP server

`mdconv-mcp` exposes conversion to an LLM agent over MCP (stdio), so you can point
an agent at a PDF and have it work from Markdown without paying for the document
in context.

Once installed with the `[mcp]` extra above:

```json
{
  "mcpServers": {
    "mdconv": { "command": "mdconv-mcp" }
  }
}
```

In Claude Code that is:

```bash
claude mcp add mdconv -- mdconv-mcp
```

To run it from a checkout instead of a global install:

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
  "bytes": 37303, "lines": 705, "est_tokens": 9266,
  "outline": [ {"level": 1, "line": 5, "text": "1. Introduction"}, ... ],
  "preview": "Shared MIME-info Database …",
  "cached": false
}
```

The agent then reads only the lines it needs from `path` using its own file tools,
guided by the outline:

```
convert_to_markdown("/docs/spec.pdf")   ->  receipt, ~1,000 tokens
read /docs/spec.md lines 330-395        ->  just "2.5. The magic files"
```

On that 37KB spec the receipt is ~1,000 tokens instead of ~9,300, and it stays
roughly that size no matter how large the document gets, because the outline is
capped at 40 entries and the preview at 200 characters.

### The tool

One tool: `convert_to_markdown(source, force=False)`. `source` is a local path or
an `http(s)` URL; `force=true` bypasses the cache. It returns:

| Field | Meaning |
| --- | --- |
| `path` | Absolute path to the converted Markdown — the thing to read |
| `bytes`, `lines` | Size of the Markdown, and the upper bound for a read offset. `lines` counts `\n` the way a file reader does, so line numbers here and in `outline` match what you read from `path` |
| `est_tokens` | Approximate cost of reading it whole (`chars / 4`, a heuristic) |
| `title` | Document title, when markitdown detects one |
| `outline` | `{level, line, text}` per heading — the index for selective reads |
| `outline_truncated` | `true` when there were more headings than the cap |
| `preview` | First 200 characters, to confirm the conversion looks sane |
| `cached` | `true` when served from cache without reconverting |
| `warning` | Set when the output looks unusable — see below |

Failures (missing file, unsupported source, a blocked path) come back as MCP tool
errors with a readable message, so the agent can correct itself rather than
crashing the session.

### Scanned PDFs

markitdown does not raise on an image-only PDF — it returns almost no text and
reports success, which otherwise costs an agent a whole turn to discover. When the
output is nearly empty for a large source, `warning` says so explicitly. There is
no OCR fallback; those documents need a different tool.

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

Clear it with `mdconv --clear-cache`. Only files named by the cache key are
removed, so pointing `MDCONVERTOR_CACHE_DIR` at a directory holding other things
is safe.

### What the server can reach

Worth knowing before you point an agent at it, because both of these are
deliberate and neither is restricted by default:

- **Any file the server's user can read.** `MDCONVERTOR_ALLOWED_ROOTS` is the
  containment mechanism and it is unset by default. Set it if the agent driving
  the server is one whose instructions you do not fully control.
- **Any URL, including private ones.** `MDCONVERTOR_ALLOWED_ROOTS` does *not*
  apply to `http(s)` sources — it only guards local paths. A prompt-injected
  agent could aim the server at an internal host or a cloud metadata endpoint,
  and the request goes out with your network position. Sandbox the server, or
  leave URL sources unused, if that matters to you.

## Supported formats

Whatever markitdown supports — this installs `markitdown[all]`: PDF, Word, PowerPoint,
Excel, HTML, CSV, JSON, XML, images, audio (transcription), Outlook messages, EPUB,
and ZIP archives.

`http(s)` sources, including YouTube URLs, work through the [MCP server](#mcp-server)
only. The CLI takes local files and rejects a URL with a message saying so.

## Development

```bash
uv sync --extra mcp
uv run pytest -q
```

The project pins Python 3.12 via `.python-version` (a transitive dependency,
`onnxruntime`, has no 3.14 wheels yet), and enables pre-release resolution
because `markitdown[all]` depends on a beta Azure SDK package.

Layout:

| Path | Contains |
| --- | --- |
| `src/mdconvertor/core.py` | Conversion, outline parsing and caching — shared by both front ends |
| `src/mdconvertor/cli.py` | The `mdconv` CLI |
| `src/mdconvertor/mcp_server.py` | The `mdconv-mcp` server and its single tool |

`tests/test_mcp.py` drives the server in-process over the real protocol via
`mcp.Client`, so no subprocess is needed.
