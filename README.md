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
| `--version` | Print the version |

By default an existing output file is left alone:

```
$ mdconv report.pdf .
error: report.md already exists (use --force to overwrite)
```

Exit codes: `0` success, `1` conversion or overwrite refusal, `2` source file not found.
The `wrote …` message goes to stderr, so `mdconv file.pdf -` pipes cleanly.

## Supported formats

Whatever markitdown supports — this installs `markitdown[all]`: PDF, Word, PowerPoint,
Excel, HTML, CSV, JSON, XML, images, audio (transcription), Outlook messages, EPUB,
ZIP archives, and YouTube URLs.

## Development

```bash
uv sync
uv run pytest -q
```

The project pins Python 3.12 via `.python-version` (a transitive dependency,
`onnxruntime`, has no 3.14 wheels yet), and enables pre-release resolution
because `markitdown[all]` depends on a beta Azure SDK package.
